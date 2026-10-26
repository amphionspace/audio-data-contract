import json
import os
import time
from pathlib import Path

from audio_data_contract.cli import main
from audio_data_contract.declarations import write_declarations
from audio_data_contract.storage_audit import (
    find_issues,
    load_zones,
    read_snapshot,
    scan,
)


def _write(path: Path, size: int, mtime: float | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    if mtime is not None:
        os.utime(path, (mtime, mtime))


def _setup(tmp_path):
    ws = tmp_path / "ws"
    data = ws / "data"
    _write(data / "datasets/a/versions/v1/train/rec.jsonl.gz", 10)
    _write(data / "datasets/a/versions/v1/audio/big.tar", 500)  # sibling of artifact
    _write(data / "datasets/a/source/wav/x.wav", 150)  # shared by a's versions
    _write(data / "datasets/b/raw/huge.tar", 300)
    _write(data / "registry/catalog.yaml", 5)
    _write(data / "scratch/tmp.bin", 20)  # below min_bytes, data is strict
    _write(data / "stray.tar", 7)  # loose file in a strict container
    old = time.time() - 400 * 86400
    _write(data / "packages/old-pkg/shard.tar", 200, mtime=old)
    os.utime(data / "packages/old-pkg", (old, old))
    _write(ws / "home/alice/ckpt.pt", 900)
    _write(ws / "home/bob/notes.txt", 1)
    _write(ws / "stray/dump.bin", 120)
    os.link(ws / "stray/dump.bin", ws / "stray/dump-link.bin")

    catalog = tmp_path / "catalog.yaml"
    write_declarations(
        catalog,
        [
            {
                "schema_version": "dataset-catalog/2.0",
                "dataset_id": "a",
                "version": "v1",
                "languages": ["en"],
                "tasks": ["asr"],
                "artifacts": [
                    {
                        "name": "rec",
                        "kind": "lhotse-recordings",
                        "root_alias": "data",
                        "relative_path": "datasets/a/versions/v1/train/rec.jsonl.gz",
                    },
                    {
                        "name": "gone",
                        "kind": "lhotse-recordings",
                        "root_alias": "data",
                        "relative_path": "datasets/a/versions/v1/gone.jsonl.gz",
                    },
                ],
                "splits": {},
            }
        ],
    )
    roots = tmp_path / "roots.json"
    roots.write_text(json.dumps({"data": str(data)}))
    zones = tmp_path / "zones.yaml"
    zones.write_text(
        f"""
schema_version: storage-zones/1.0
scan_root: {ws}
catalog:
  path: {catalog}
  roots: {roots}
  unit_patterns: ["{data}/datasets/*/*/*"]
  shared_patterns: ["{data}/datasets/*/source"]
thresholds: {{min_bytes: 100, growth_min_bytes: 400}}
entries:
  - {{path: {ws}, contents: listed}}
  - {{path: {data}, contents: listed, strict: true, owner: data-team}}
  - {{path: {data}/registry}}
  - {{path: {data}/packages, stale_days: 30}}
  - {{path: {ws}/home, contents: per-child, budget: 1000, child_budget: 800}}
""",
        encoding="utf-8",
    )
    return ws, zones


def test_scan_rolls_up_and_counts_hard_links_once(tmp_path):
    ws, zones_path = _setup(tmp_path)
    nodes, errors = scan(load_zones(zones_path), workers=4)

    assert errors == []
    assert nodes[str(ws)]["bytes"] == (
        10 + 500 + 150 + 300 + 5 + 20 + 7 + 200 + 900 + 1 + 120
    )
    assert nodes[str(ws / "stray")]["bytes"] == 120
    # Children of a catalog unit are rolled into the unit, not kept separately.
    unit = ws / "data/datasets/a/versions/v1"
    assert nodes[str(unit)]["bytes"] == 510
    assert str(unit / "audio") not in nodes
    # Personal directories are kept per user, never deeper.
    assert nodes[str(ws / "home/alice")]["bytes"] == 900


def test_findings_flag_unregistered_budget_stale_missing_and_growth(tmp_path):
    ws, zones_path = _setup(tmp_path)
    zones = load_zones(zones_path)
    nodes, _ = scan(zones, workers=4)
    previous = {path: dict(node) for path, node in nodes.items()}
    previous[str(ws / "home/alice")]["bytes"] = 0
    previous[str(ws / "home")]["bytes"] -= 900

    findings = find_issues(zones, nodes, previous)
    found = {(row["category"], row["path"]) for row in findings}

    assert found == {
        ("unregistered", str(ws / "data/datasets/b")),
        ("unregistered", str(ws / "data/scratch")),
        ("unregistered", str(ws / "data")),
        ("unregistered", str(ws / "stray")),
        ("over_budget", str(ws / "home/alice")),
        ("stale", str(ws / "data/packages/old-pkg")),
        ("missing", str(ws / "data/datasets/a/versions/v1/gone.jsonl.gz")),
        ("growth", str(ws / "home/alice")),
    }


def test_cli_scan_then_report(tmp_path, capsys):
    _, zones_path = _setup(tmp_path)
    out = tmp_path / "audit"

    assert main(["storage-audit", "scan", "--zones", str(zones_path),
                 "--output-dir", str(out), "--workers", "2"]) == 0
    snapshot = json.loads(capsys.readouterr().out)["snapshot"]
    meta, nodes, _ = read_snapshot(snapshot)
    assert meta["files"] == 11 and len(nodes) == meta["nodes"]

    assert main(["storage-audit", "report", "--zones", str(zones_path),
                 "--output-dir", str(out)]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["unregistered"] == 4
    text = Path(summary["report"]).read_text(encoding="utf-8")
    assert "未注册（4）" in text
    assert "## 用量概览" in text and f"`{tmp_path}/ws/home/alice` | 900 B" in text

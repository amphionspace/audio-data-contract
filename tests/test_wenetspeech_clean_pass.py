import gzip
import json
import runpy
from pathlib import Path

script = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/wenetspeech_clean_pass.py"))


def row(sid, clean):
    return {"id": sid, "recording_id": "r", "start": 0.0, "duration": 2.5, "channel": 0, "text": "你好",
            "custom": {"clean": clean} if clean is not None else {}}


def test_only_rows_whose_upstream_marker_passed_are_kept_unchanged(tmp_path):
    rows = [row("a", {"pass": True, "action": "keep_original"}), row("b", {"pass": False, "action": "reject"}),
            row("c", None), row("d", {"pass": "true"}), row("e", {"pass": True, "action": "restore_disfluency"})]
    lines = [json.dumps(r, ensure_ascii=False) for r in rows]
    source = tmp_path / "in.jsonl.gz"
    with gzip.open(source, "wt", encoding="utf-8") as stream:
        stream.write("\n".join(lines) + "\n\n")
    destination = tmp_path / "out" / "train.jsonl.gz"
    facts = script["filter_supervisions"](source, destination)
    assert facts == {"rows": 5, "kept": 2, "hours": 5.0 / 3600}
    with gzip.open(destination, "rt", encoding="utf-8") as stream:
        assert stream.read().splitlines() == [lines[0], lines[4]]


def test_output_is_deterministic(tmp_path):
    source = tmp_path / "in.jsonl.gz"
    with gzip.open(source, "wt", encoding="utf-8") as stream:
        stream.write(json.dumps(row("a", {"pass": True})) + "\n")
    first, second = tmp_path / "1" / "t.jsonl.gz", tmp_path / "2" / "t.jsonl.gz"
    script["filter_supervisions"](source, first)
    script["filter_supervisions"](source, second)
    assert first.read_bytes() == second.read_bytes()


def test_declaration_marks_the_version_clean_pass_only(tmp_path):
    path = tmp_path / "train.jsonl.gz"
    path.write_bytes(b"x")
    source = {"schema_version": "dataset-catalog/2.0", "languages": ["zh"], "tasks": ["asr"],
              "artifacts": [{"name": "train_recordings", "kind": "lhotse-recordings", "root_alias": "aidc_data",
                             "relative_path": "rec.jsonl.gz"}],
              "recipe_parameters": {"filter_rules": "consensus-v6", "rewrite_rules": "wenetspeech-faithful-v5"}}
    spec = script["declaration"](source, {"rows": 3, "kept": 2, "hours": 1.0}, path, "out/train.jsonl.gz")
    assert spec["recipe_parameters"]["clean_pass_only"] is True
    assert spec["derived_from"] == "wenetspeech_clean@clean-v3-20260828"
    assert spec["splits"]["train"]["artifacts"] == {"recordings": ["train_recordings"], "supervisions": ["train_supervisions"]}
    assert spec["artifacts"][1]["metadata"]["record_count"] == 2

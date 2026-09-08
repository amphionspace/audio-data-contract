import gzip
import json
from pathlib import Path

from prepare_police_mixture_v9 import build_subset


def _write_rows(path: Path, rows: list[dict]) -> None:
    with gzip.open(path, "wt", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def test_build_subset_keeps_only_verified_restorations(tmp_path):
    source = tmp_path / "source.jsonl.gz"
    output = tmp_path / "selected.jsonl.gz"
    rows = [
        {
            "id": "final-a",
            "text": "收到啊。",
            "custom": {"clean": {"action": "restore_disfluency", "pass": True}},
        },
        {
            "id": "initial-en",
            "text": "嗯明白",
            "custom": {"clean": {"action": "restore_disfluency", "pass": True}},
        },
        {
            "id": "unchanged",
            "text": "好的",
            "custom": {"clean": {"action": "keep_original", "pass": True}},
        },
        {
            "id": "rejected",
            "text": "哦",
            "custom": {"clean": {"action": "restore_disfluency", "pass": False}},
        },
    ]
    _write_rows(source, rows)

    summary = build_subset(source, output)

    with gzip.open(output, "rt", encoding="utf-8") as f:
        selected = [json.loads(line) for line in f]
    assert [row["id"] for row in selected] == ["final-a", "initial-en"]
    assert summary["source_rows"] == 4
    assert summary["selected_rows"] == 2
    assert summary["rows_with_fillers"] == 2
    assert summary["final_fillers"] == {"啊": 1}

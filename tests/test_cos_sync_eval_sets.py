import datetime
import importlib.util
import json
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
spec = importlib.util.spec_from_file_location(
    "cos_sync_eval_sets", SCRIPTS / "cos_sync_eval_sets.py"
)
mirror = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mirror)


def test_pending_mirrors_dedicated_roots_and_skips_shared_ones(tmp_path):
    directory = tmp_path / "project" / "set@v1"
    directory.mkdir(parents=True)
    (directory / "eval-set.yaml").write_text(
        "evaluation:\n- {dataset_id: done, version: v1, split: a}\n"
        "- {dataset_id: fresh, version: v2, split: a}\n"
        "- {dataset_id: fresh, version: v2, split: b}\n"
        "- {dataset_id: inside, version: v1, split: a}\n"
        "validation:\n- {dataset_id: dev, version: v1, split: a}\n"
    )
    keys = mirror.eval_set_datasets(tmp_path)
    ledger = {"datasets": {"done@v1": {"alias": "done", "synced": "2026-10-26"}}}
    roots = {"fresh@v2": {"fresh"}, "inside@v1": {"aidc_data"}, "dev@v1": {"dev"}}

    aliases, shared = mirror.pending(keys, ledger, lambda key: roots[key])

    assert aliases == {"dev@v1": "dev", "fresh@v2": "fresh"}
    assert shared == ["inside@v1"]


def test_ledger_format_round_trips(tmp_path):
    ledger = {"bucket": "b", "prefix": "p/", "datasets": {"a@v1": {"alias": "a"}}}
    path = tmp_path / "ab-datasets.json"
    path.write_text(json.dumps(ledger))
    assert json.loads(path.read_text()) == ledger


def test_receipts_serialize_catalog_dates():
    spec = importlib.util.spec_from_file_location("cos_backup", SCRIPTS / "cos_backup.py")
    backup = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(backup)

    assert backup.encoded({"extracted_at": datetime.date(2026, 10, 1)}) == (
        b'{"extracted_at":"2026-10-01"}'
    )

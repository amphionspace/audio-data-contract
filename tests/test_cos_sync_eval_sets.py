import datetime
import importlib.util
import json
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
spec = importlib.util.spec_from_file_location("cos_sync_eval_sets", SCRIPTS / "cos_sync_eval_sets.py")
eval_sets = importlib.util.module_from_spec(spec)
spec.loader.exec_module(eval_sets)


def test_pending_lists_eval_set_datasets_without_a_binding(tmp_path):
    directory = tmp_path / "eval-sets" / "project" / "set@v1"
    directory.mkdir(parents=True)
    (directory / "eval-set.yaml").write_text(
        "evaluation:\n- {dataset_id: bound, version: v1, split: a}\n"
        "- {dataset_id: fresh, version: v2, split: a}\n"
        "- {dataset_id: fresh, version: v2, split: b}\n"
        "validation:\n- {dataset_id: dev, version: v1, split: a}\n"
    )
    backups = tmp_path / "backups"
    backups.mkdir()
    (backups / "cos-1.json").write_text(json.dumps({"dataset_bindings": {"bound@v1": {}}}))
    (backups / "receipt.json").write_text(json.dumps({"shards": []}))

    assert eval_sets.pending(tmp_path / "eval-sets", backups) == ["dev@v1", "fresh@v2"]


def test_receipts_serialize_catalog_dates():
    spec = importlib.util.spec_from_file_location("cos_backup", SCRIPTS / "cos_backup.py")
    backup = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(backup)

    assert backup.encoded({"extracted_at": datetime.date(2026, 10, 1)}) == (
        b'{"extracted_at":"2026-10-01"}'
    )

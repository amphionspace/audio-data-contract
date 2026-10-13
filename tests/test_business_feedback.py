import json
import runpy
import wave
from pathlib import Path

import pytest

from audio_data_contract import load_records
from audio_data_contract.types import DatasetSpec

pytest.importorskip("soundfile")
pytest.importorskip("yaml")
REPO = Path(__file__).resolve().parents[1]
ingest = runpy.run_path(str(REPO / "scripts/business_feedback/ingest.py"))


def write_wav(path, seconds, value=0):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(16000)
        out.writeframes(int(seconds * 16000) * value.to_bytes(2, "little", signed=True))


def make_case(source, name, source_seconds, output, enrollment_value=100):
    directory = source / "cases" / name
    write_wav(directory / "registration-reference.wav", 3, enrollment_value)
    write_wav(directory / "source-audio.wav", source_seconds, 7)
    (directory / "attempt-1").mkdir(parents=True)
    (directory / "manifest.json").write_text(json.dumps({"trace_id": "t", "segment_id": 1, "model": "m"}))
    reply = {"choices": [{"message": {"content": output}, "finish_reason": "stop"}]}
    (directory / "attempt-1" / "response.json").write_text(json.dumps(reply))


@pytest.fixture
def batch(tmp_path):
    source = tmp_path / "feedback"
    make_case(source, "case-01", 2.0, "language Chinese<asr_text>你好。")
    make_case(source, "case-02", 1.5, "language Chinese<asr_text>谢谢。")
    make_case(source, "case-03", 0.5, "language Chinese<asr_text>嗯。")
    (source / "packages").mkdir()
    (source / "packages" / "case-01--model-feedback-abc.zip").write_bytes(b"")
    labels = {"version": "ts-test", "language": "zh", "source": "feedback", "description": "测试批次",
              "cases": {
                  "case-01": {"split": "target_speaker", "target_present": False, "issue": "pad_voice"},
                  "case-02": {"split": "target_speaker", "target_present": False, "issue": "pad_voice"},
                  "case-03": {"split": "pending_labels", "issue": "short_segment"}}}
    return source, labels, tmp_path / "data"


def test_batch_becomes_negative_and_pending_records(batch):
    source, labels, data_root = batch
    by_split, index = ingest["build"](source, labels, data_root)
    spec = DatasetSpec.from_dict(ingest["declaration"](labels, by_split, index, data_root))

    assert set(spec.splits) == {"target_speaker", "pending_labels"}
    negatives = list(load_records(data_root / "versions/ts-test/records/target_speaker.jsonl.gz"))
    assert [r.target for r in negatives] == ["", ""]
    assert all(r.labels["target_present"] is False and r.task == "ts_asr" for r in negatives)
    assert [s.name for s in negatives[0].audio_slots] == ["enrollment", "mixture"]
    assert negatives[0].metadata["package"] == "model-feedback-abc.zip"
    assert negatives[0].metadata["reported_output"].endswith("你好。")
    (pending,) = load_records(data_root / "versions/ts-test/records/pending_labels.jsonl.gz")
    assert "target_present" not in pending.labels and pending.labels["label_status"] == "unlabeled"
    # The shared enrollment is stored once; mixtures are per case.
    assert len(index) == 4


def test_registered_version_is_never_replaced(batch):
    source, labels, data_root = batch
    ingest["build"](source, labels, data_root)
    with pytest.raises(FileExistsError):
        ingest["build"](source, labels, data_root)

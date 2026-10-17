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


def make_case(source, name, source_seconds, output, enrollment_value=100, stream=False):
    directory = source / "cases" / name
    write_wav(directory / "registration-reference.wav", 3, enrollment_value)
    write_wav(directory / "source-audio.wav", source_seconds, 7)
    (directory / "attempt-1").mkdir(parents=True)
    (directory / "manifest.json").write_text(json.dumps({"trace_id": "t", "segment_id": 1, "model": "m"}))
    if stream:
        chunks = [{"choices": [{"delta": {"content": piece}, "finish_reason": None}]} for piece in output]
        if stream != "cancelled":
            chunks.append({"choices": [{"delta": {}, "finish_reason": "stop"}]})
        (directory / "attempt-1" / "response.json").write_text(
            "".join(f"data: {json.dumps(c, ensure_ascii=False)}\n\n" for c in chunks))
    else:
        reply = {"choices": [{"message": {"content": output}, "finish_reason": "stop"}]}
        (directory / "attempt-1" / "response.json").write_text(json.dumps(reply))
    request = {"max_tokens": 256, "messages": [], "mm_processor_kwargs": {"target_speaker": True}}
    (directory / "attempt-1" / "request.json").write_text(json.dumps(request))


@pytest.fixture
def batch(tmp_path):
    source = tmp_path / "feedback"
    make_case(source, "case-01", 2.0, "language Chinese<asr_text>你好。")
    make_case(source, "case-02", 1.5, ["language", " None"], stream="cancelled")
    make_case(source, "case-03", 0.5, ["language", " Chinese", "<asr_text>", "嗯。"], stream=True)
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


def test_confirmed_target_speech_and_row_named_packages(batch):
    source, labels, data_root = batch
    make_case(source, "row-04", 3.0, "language Chinese<asr_text>是啊。")
    (source / "packages" / "row-04--model-feedback-def.zip").write_bytes(b"")
    labels["cases"]["row-04"] = {"split": "target_present", "target_present": True, "target": "嗯，是啊",
                                 "issue": "loop"}
    by_split, index = ingest["build"](source, labels, data_root)
    spec = DatasetSpec.from_dict(ingest["declaration"](labels, by_split, index, data_root))

    assert "target_present" in spec.splits
    (present,) = load_records(data_root / "versions/ts-test/records/target_present.jsonl.gz")
    assert present.target == "嗯，是啊" and present.labels["target_present"] is True
    assert present.metadata["package"] == "model-feedback-def.zip"


def test_registered_version_is_never_replaced(batch):
    source, labels, data_root = batch
    ingest["build"](source, labels, data_root)
    with pytest.raises(FileExistsError):
        ingest["build"](source, labels, data_root)


def test_streamed_and_cancelled_responses_are_recorded_as_reported(batch):
    source, labels, data_root = batch
    ingest["build"](source, labels, data_root)
    negatives = {r.id: r for r in load_records(data_root / "versions/ts-test/records/target_speaker.jsonl.gz")}
    cancelled = negatives["ts-test:case-02"].metadata
    assert cancelled["reported_output"] == "language None" and cancelled["reported_finish_reason"] is None
    assert cancelled["reported_streamed"] is True
    (pending,) = load_records(data_root / "versions/ts-test/records/pending_labels.jsonl.gz")
    assert pending.metadata["reported_output"] == "language Chinese<asr_text>嗯。"
    assert pending.metadata["reported_finish_reason"] == "stop"
    assert pending.metadata["request_params"]["mm_processor_kwargs"] == {"target_speaker": True}

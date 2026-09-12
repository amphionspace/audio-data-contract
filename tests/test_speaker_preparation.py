import io
import json
import runpy
import sys
import tarfile
import wave
from contextlib import ExitStack
from pathlib import Path

import pytest

from audio_data_contract import load_catalog, load_records, load_view_catalog

pytest.importorskip("soundfile")
pytest.importorskip("orjson")
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts/speaker"))
extract = runpy.run_path(str(REPO / "scripts/speaker/extract.py"))
prepare = runpy.run_path(str(REPO / "scripts/speaker/prepare.py"))
reader = runpy.run_path(str(REPO / "scripts/speaker/read.py"))


def wav():
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as stream:
        stream.setparams((1, 2, 16000, 0, "NONE", "none"))
        stream.writeframes(b"\0\0" * 16000)
    return buffer.getvalue()


def archive(path, entries):
    with tarfile.open(path, "w:gz") as stream:
        for name, content in entries.items():
            content = content.encode() if isinstance(content, str) else content
            info = tarfile.TarInfo(name)
            info.size = len(content)
            stream.addfile(info, io.BytesIO(content))
    return {"name": "audio_archive", "kind": "source-archive", "root_alias": "legacy_asr",
            "relative_path": path.name, "expected_bytes": path.stat().st_size,
            "sha256": extract["sha256"](path)}


def test_cnceleb_official_split_trials_publish_and_portable_read(tmp_path):
    root, repo = tmp_path / "data", tmp_path / "repo"
    root.mkdir()
    (repo / "catalog").mkdir(parents=True)
    (repo / "views").mkdir()
    entries = {
        "CN-Celeb_flac/dev/dev.lst": "id00000\n",
        "CN-Celeb_flac/data/id00000/speech-1.wav": wav(),
        "CN-Celeb_flac/data/id00800/speech-1.wav": wav(),
        "CN-Celeb_flac/eval/enroll/id00800-enroll.flac": wav(),
        "CN-Celeb_flac/eval/test/id00800-speech-1.flac": wav(),
        "CN-Celeb_flac/eval/test/id00801-speech-1.flac": wav(),
        "CN-Celeb_flac/eval/lists/enroll.lst": "id00800-enroll enroll/id00800-enroll.wav\n",
        "CN-Celeb_flac/eval/lists/test.lst": "test/id00800-speech-1.wav\ntest/id00801-speech-1.wav\n",
        "CN-Celeb_flac/eval/lists/trials.lst":
            "id00800-enroll test/id00800-speech-1.wav 1\nid00800-enroll test/id00801-speech-1.wav 0\n",
    }
    artifact = archive(root / "source.tar.gz", entries)
    spec = {"schema_version": "dataset-catalog/1.0", "dataset_id": "cnceleb1",
            "version": "source-1", "languages": ["zh"], "tasks": ["speaker_verification"],
            "artifacts": [artifact], "splits": {}, "provenance": {"source": "fixture"}}
    (repo / "catalog/cnceleb1.jsonl").write_text(json.dumps(spec) + "\n")
    extract["extract_dataset"](repo, root, "cnceleb1")
    work, final = extract["paths"](root, "cnceleb1")
    # Resuming a completed extraction uses its verified inventory.
    extract["extract_dataset"](repo, root, "cnceleb1")
    report = prepare["prepare_dataset"](repo, root, "cnceleb1")
    prepare["register"](repo, report)
    prepare["register"](repo, report)
    assert not work.exists()
    assert report["dataset"]["splits"]["train"]["statistics"]["records"] == 1
    catalog = load_catalog(repo / "catalog")
    assert len(load_view_catalog(repo / "views", catalog)) == 1
    records = list(load_records(final / "test_trials.jsonl.gz"))
    assert [r.labels["same_speaker"] for r in records] == [True, False]
    assert records[0].slot("enrollment").ref.split == "test_enrollment"
    assert len(list(load_records(final / "train.jsonl.gz"))) == 1
    moved = tmp_path / "moved"
    root.rename(moved)
    result = reader["resolve_audio"](records[0], catalog, {"legacy_asr": str(moved)})
    assert Path(result["enrollment"]["path"]).read_bytes() == wav()
    assert result["test"]["duration"] == 1


def item(name, split="test", speaker="SV0001"):
    return {"path": "extracted/" + name, "member": name, "archive": split + "_archive",
            "split": split, "speaker": speaker, "duration": 5, "sample_rate": 16000,
            "channels": 1, "num_frames": 80000, "bytes": 160044}


def test_himia_template_expansion_preserves_microphones_and_pair_labels(tmp_path):
    audio = [item(f"SV0001_2_{channel}_N0001.wav") for channel in ("00", "01")]
    audio += [item(f"SV0002_5_{channel}_N0002.wav", speaker="SV0002") for channel in ("00", "01")]
    audio += [item("SV0001_7_01_N0001.wav")]
    metadata = []
    for name, text in {
        "trials_1m": "SV0001_2_{}_N0001.wav SV0002_5_{}_N0002.wav nontarget\n",
        "trials_mic": "SV0001_7_01_N0001.wav SV0001_2_{}_N0001.wav target\n",
    }.items():
        (tmp_path / name).write_text(text)
        metadata.append({"member": name, "path": name})
    with ExitStack() as stack:
        builder = prepare["Builder"](tmp_path, tmp_path, tmp_path / "final", "hi_mia", stack, audio)
        prepare["verification_trials"](builder, tmp_path, metadata)
    negative = list(load_records(tmp_path / "test_trials_1m.jsonl.gz"))
    positive = list(load_records(tmp_path / "test_trials_mic.jsonl.gz"))
    assert len(negative) == len(positive) == 2
    assert all(not row.labels["same_speaker"] for row in negative)
    assert all(row.labels["same_speaker"] for row in positive)
    assert {row.metadata["channel_variant"] for row in positive} == {"00", "01"}
    assert positive[0].slot("enrollment").ref.cut_id == positive[1].slot("enrollment").ref.cut_id


def test_chime_invalid_times_are_reported_and_valid_segments_remain(tmp_path):
    audio = [item("S01_U02.CH1.wav")]
    audio[0]["session"] = "S01"
    annotation = {"session_id": "S01", "speaker": "P01", "ref": "U02", "words": "Keep punctuation!",
                  "start_time": "00:00:01.00", "end_time": "00:00:02.00"}
    (tmp_path / "S01.json").write_text(json.dumps([
        annotation, {**annotation, "start_time": "00:00:03.00"},
    ]))
    metadata = [{"archive": "transcriptions_repaired_archive", "path": "S01.json", "member": "S01.json"}]
    with ExitStack() as stack:
        builder = prepare["Builder"](tmp_path, tmp_path, tmp_path / "final", "chime6", stack, audio)
        prepare["chime_records"](builder, tmp_path, metadata)
        assert len(builder.rejects) == 1
        assert builder.counts["test"] + len(builder.rejects) == 2
    record = next(load_records(tmp_path / "test.jsonl.gz"))
    assert record.target == "Keep punctuation!"
    assert record.slot("speech").ref.start == 1
    assert record.slot("speech").ref.duration == 1
    diarization = next(load_records(tmp_path / "test_diarization.jsonl.gz"))
    assert len(diarization.labels["segments"]) == 1


def test_trial_label_conflict_and_unsafe_tar_are_rejected(tmp_path):
    with ExitStack() as stack:
        left, right = item("a.wav"), item("b.wav", speaker="SV0002")
        builder = prepare["Builder"](tmp_path, tmp_path, tmp_path / "final", "hi_mia", stack, [left, right])
        with pytest.raises(ValueError, match="disagrees"):
            builder.pair("test_trials", 1, left, right, "target", "trials")
    bad = archive(tmp_path / "bad.tar.gz", {"../escape": b"x"})
    with pytest.raises(ValueError, match="unsafe archive path"):
        extract["extract_archive"](tmp_path, tmp_path / "work", "bad", [bad])
    assert not (tmp_path / "escape").exists()


def test_split_cnceleb2_archive_is_streamed_in_order(tmp_path):
    original = archive(tmp_path / "whole.tar.gz", {"CN-Celeb2_flac/data/id10000/a.wav": wav()})
    data = (tmp_path / original["relative_path"]).read_bytes()
    artifacts = []
    boundary = len(data) // 3
    for i, suffix in enumerate(("aa", "ab", "ac")):
        path = tmp_path / ("cn2.tar.gz" + suffix)
        path.write_bytes(data[i * boundary:(i + 1) * boundary] if i < 2 else data[i * boundary:])
        artifacts.append({"relative_path": path.name, "expected_bytes": path.stat().st_size,
                          "sha256": extract["sha256"](path)})
    result = extract["extract_archive"](tmp_path, tmp_path / "work", "audio", artifacts)
    assert result["audio_files"] == 1
    assert (tmp_path / "work/extracted/audio/CN-Celeb2_flac/data/id10000/a.wav").read_bytes() == wav()

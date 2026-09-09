import copy
import gzip
import hashlib
import io
import json
import tarfile
import wave
from pathlib import Path

import pytest

from audio_data_contract import audio_prepare as prepare
from audio_data_contract.cli import main


def wav_bytes():
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b"\x01\x00\x02\x00" * 800)
    return buffer.getvalue()


def recording(source, kind="file", identifier="r"):
    return {
        "id": identifier,
        "sources": [{"type": kind, "channels": [0], "source": str(source)}],
        "sampling_rate": 16000,
        "num_samples": 1600,
        "duration": 0.1,
        "channel_ids": [0],
    }


def cut(rec, identifier="c"):
    return {
        "id": identifier,
        "type": "MonoCut",
        "start": 0.01,
        "duration": 0.05,
        "channel": 0,
        "recording": rec,
        "supervisions": [
            {
                "id": "s",
                "recording_id": rec["id"],
                "start": 0,
                "duration": 0.05,
                "channel": 0,
                "text": "测试",
            }
        ],
        "custom": {"preserve": [1, "unknown"]},
    }


def write_manifest(path, rows):
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "wt", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row) + "\n")
    return path


def read_manifest(path):
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream]


def invoke(tmp_path, capsys, inputs, mode="localize-audio", output="out", extra=()):
    result = main(
        [
            mode,
            "--manifest",
            *map(str, inputs),
            "--cache-dir",
            str(tmp_path / "cache"),
            "--output-dir",
            str(tmp_path / output),
            *extra,
        ]
    )
    return result, json.loads(capsys.readouterr().out)


def make_tar(path, entries):
    with tarfile.open(path, "w") as archive:
        for name, data in entries:
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return path


def test_localize_preserves_nested_structure_and_deduplicates(tmp_path, capsys):
    source = tmp_path / "speech.wav"
    source.write_bytes(wav_bytes())
    rec = recording(source)
    rec["transforms"] = [
        {
            "name": "ReverbWithImpulseResponse",
            "kwargs": {
                "rir": recording(source, identifier="rir"),
                "normalize_output": True,
            },
        }
    ]
    mixed = {
        "id": "mix",
        "type": "MixedCut",
        "tracks": [
            {"cut": cut(rec), "offset": 0, "snr": None},
            {"cut": {"type": "PaddingCut", "id": "pad", "duration": 0.1}, "offset": 0},
        ],
    }
    inputs = [
        write_manifest(tmp_path / "cuts.jsonl.gz", [mixed, cut(rec, "other")]),
        write_manifest(tmp_path / "rir.jsonl", [recording(source)]),
    ]
    originals = [p.read_bytes() for p in inputs]
    result, report = invoke(tmp_path, capsys, inputs)
    assert result == 0
    assert report["references"] == 5
    assert report["unique_files"] == report["copied"] == 1
    assert report["copied_bytes"] == source.stat().st_size
    for manifest in inputs:
        before = read_manifest(manifest)
        after = read_manifest(tmp_path / "out" / manifest.name)
        for original, localized in zip(before, after):
            for old, new in zip(
                prepare._sources(original), prepare._sources(localized)
            ):
                assert (
                    Path(new["source"]).read_bytes() == Path(old["source"]).read_bytes()
                )
                new["source"] = old["source"]
            assert original == localized
    assert [p.read_bytes() for p in inputs] == originals
    result, report = invoke(tmp_path, capsys, inputs, output="rerun")
    assert result == 0
    assert report["reused"] == 1 and report["copied"] == 0


def test_tar_dd_bytes_and_one_tar_open(tmp_path, capsys, monkeypatch):
    data = wav_bytes()
    archive = make_tar(
        tmp_path / "audio space.tar", [("a.wav", data), ("b.wav", data[::-1])]
    )
    with tarfile.open(archive) as stream:
        offset = stream.getmember("a.wav").offset_data
    rows = [
        recording(f"tar -xOf '{archive}' a.wav", "command"),
        recording(
            f"timeout --signal=TERM --kill-after=5s 30s tar -xOf '{archive}' b.wav",
            "command",
            "b",
        ),
        recording(
            f"timeout --signal=TERM --kill-after=5s 30s dd if='{archive}' "
            f"iflag=skip_bytes,count_bytes skip={offset} count={len(data)} status=none",
            "command",
            "dd",
        ),
    ]
    manifest = write_manifest(tmp_path / "recordings.jsonl", rows)
    opened = []
    real_open = tarfile.open

    def counted_open(*args, **kwargs):
        opened.append(args[0])
        return real_open(*args, **kwargs)

    monkeypatch.setattr(tarfile, "open", counted_open)
    result, report = invoke(tmp_path, capsys, [manifest], "extract-audio")
    assert result == 0 and report["extracted"] == 3
    assert len(opened) == 1
    after = read_manifest(tmp_path / "out" / manifest.name)
    for row, expected in zip(after, [data, data[::-1], data]):
        source = row["sources"][0]
        assert source["type"] == "file"
        assert (
            hashlib.sha256(Path(source["source"]).read_bytes()).digest()
            == hashlib.sha256(expected).digest()
        )
    result, report = invoke(
        tmp_path, capsys, [manifest], "extract-audio", output="again"
    )
    assert result == 0 and report["reused"] == 3


@pytest.mark.parametrize(
    "command",
    [
        "echo hello",
        "tar -xOf a.tar x.wav | cat",
        "tar -xOf a.tar x.wav; touch marker",
        "timeout 30 tar -xOf a.tar x.wav",
        "dd if=a.tar bs=1 skip=0 count=4",
    ],
)
def test_reject_commands_without_execution(tmp_path, capsys, command):
    manifest = write_manifest(tmp_path / "r.jsonl", [recording(command, "command")])
    result, report = invoke(tmp_path, capsys, [manifest], "extract-audio")
    assert result == 1 and report["failures"][0]["record_id"] == "r"
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("problem", ["missing", "duplicate", "symlink", "broken"])
def test_tar_failure_never_publishes(tmp_path, capsys, problem):
    entries = [("a.wav", wav_bytes())]
    if problem == "duplicate":
        entries *= 2
    archive = make_tar(tmp_path / "a.tar", entries)
    if problem == "symlink":
        with tarfile.open(archive, "a") as stream:
            info = tarfile.TarInfo("link.wav")
            info.type, info.linkname = tarfile.SYMTYPE, "a.wav"
            stream.addfile(info)
    if problem == "broken":
        archive.write_bytes(b"not a tar")
    member = {"missing": "missing.wav", "symlink": "link.wav"}.get(problem, "a.wav")
    manifest = write_manifest(
        tmp_path / "r.jsonl", [recording(f"tar -xOf {archive} {member}", "command")]
    )
    result, report = invoke(tmp_path, capsys, [manifest], "extract-audio")
    assert result == 1 and report["failures"]
    assert not (tmp_path / "out").exists()


def test_failed_copy_resume_and_truncated_target(tmp_path, capsys, monkeypatch):
    source = tmp_path / "a.wav"
    source.write_bytes(wav_bytes())
    manifest = write_manifest(tmp_path / "r.jsonl", [recording(source)])
    actual = prepare.os.replace

    def interrupted(temporary, target):
        assert Path(temporary).name.startswith(".partial-")
        assert Path(temporary).read_bytes() == source.read_bytes()
        assert not Path(target).exists()
        raise OSError("disk full")

    monkeypatch.setattr(prepare.os, "replace", interrupted)
    result, _ = invoke(tmp_path, capsys, [manifest])
    assert result == 1 and not (tmp_path / "out").exists()
    assert not list((tmp_path / "cache").rglob("*.complete.json"))
    (tmp_path / "cache" / ".partial-leftover").write_bytes(b"partial")
    monkeypatch.setattr(prepare.os, "replace", actual)
    result, report = invoke(tmp_path, capsys, [manifest])
    assert result == 0 and report["copied"] == 1
    cached = Path(
        read_manifest(tmp_path / "out" / manifest.name)[0]["sources"][0]["source"]
    )
    cached.write_bytes(b"truncated")
    result, report = invoke(tmp_path, capsys, [manifest], output="again")
    assert result == 0 and report["copied"] == 1 and report["reused"] == 0
    assert cached.read_bytes() == source.read_bytes()


def test_publish_failure_reuses_completed_audio(tmp_path, capsys, monkeypatch):
    source = tmp_path / "a.wav"
    source.write_bytes(wav_bytes())
    manifest = write_manifest(tmp_path / "r.jsonl", [recording(source)])
    rename = Path.rename

    def fail(*args, **kwargs):
        raise OSError("publication interrupted")

    monkeypatch.setattr(Path, "rename", fail)
    result, report = invoke(tmp_path, capsys, [manifest])
    assert result == 1 and report["copied"] == 1
    assert not (tmp_path / "out").exists()
    monkeypatch.setattr(Path, "rename", rename)
    result, report = invoke(tmp_path, capsys, [manifest])
    assert result == 0 and report["reused"] == 1
    result, report = invoke(tmp_path, capsys, [manifest])
    assert result == 1 and "already exists" in report["failures"][0]["error"]


def test_missing_file_prevents_batch_publication(tmp_path, capsys):
    source = tmp_path / "a.wav"
    source.write_bytes(wav_bytes())
    first = write_manifest(tmp_path / "first.jsonl", [recording(source)])
    second = write_manifest(
        tmp_path / "second.jsonl", [recording(tmp_path / "missing.wav")]
    )
    result, report = invoke(tmp_path, capsys, [first, second])
    assert result == 1 and report["failures"][0]["manifest"] == str(second)
    assert not (tmp_path / "out").exists()


def test_relative_paths_same_basename_and_dd_bounds(tmp_path, capsys):
    for name in ("one", "two"):
        folder = tmp_path / name
        folder.mkdir()
        (folder / "a.wav").write_bytes(name.encode())
    manifest = write_manifest(
        tmp_path / "r.jsonl",
        [recording("one/a.wav"), recording("two/a.wav", identifier="two")],
    )
    result, report = invoke(
        tmp_path, capsys, [manifest], extra=("--source-root", str(tmp_path))
    )
    assert result == 0 and report["unique_files"] == 2
    paths = [r["sources"][0]["source"] for r in read_manifest(tmp_path / "out/r.jsonl")]
    assert len(set(paths)) == 2
    manifest = write_manifest(
        tmp_path / "dd.jsonl",
        [
            recording(
                f"dd if={tmp_path / 'one/a.wav'} iflag=skip_bytes,count_bytes skip=2 count=20 status=none",
                "command",
            )
        ],
    )
    result, report = invoke(
        tmp_path, capsys, [manifest], "extract-audio", output="dd-out"
    )
    assert result == 1 and "exceeds" in report["failures"][0]["error"]


def test_lhotse_waveforms_with_transform_and_nested_rir(tmp_path, capsys):
    lhotse = pytest.importorskip("lhotse")
    np = pytest.importorskip("numpy")
    source = tmp_path / "a.wav"
    source.write_bytes(wav_bytes())
    rec = lhotse.Recording.from_file(source, recording_id="speech")
    rir = lhotse.Recording.from_file(source, recording_id="rir")
    transformed = rec.reverb_rir(rir).perturb_volume(0.8)
    manifest = write_manifest(tmp_path / "r.jsonl", [transformed.to_dict()])
    original = copy.deepcopy(transformed.to_dict())
    result, _ = invoke(tmp_path, capsys, [manifest])
    assert result == 0
    localized = next(iter(lhotse.RecordingSet.from_file(tmp_path / "out/r.jsonl")))
    np.testing.assert_array_equal(transformed.load_audio(), localized.load_audio())
    assert transformed.to_dict() == original


def test_multicut_channels_and_lhotse_cut_loading(tmp_path, capsys):
    lhotse = pytest.importorskip("lhotse")
    np = pytest.importorskip("numpy")
    source = tmp_path / "stereo.wav"
    with wave.open(str(source), "wb") as audio:
        audio.setnchannels(2)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b"\x01\x00\x03\x00" * 1600)
    original = lhotse.Recording.from_file(source).to_cut().perturb_volume(0.7)
    manifest = write_manifest(tmp_path / "cuts.jsonl.gz", [original.to_dict()])
    result, _ = invoke(tmp_path, capsys, [manifest])
    assert result == 0
    localized = next(iter(lhotse.CutSet.from_file(tmp_path / "out/cuts.jsonl.gz")))
    assert localized.channel == original.channel
    np.testing.assert_array_equal(localized.load_audio(), original.load_audio())


def test_source_change_and_missing_receipt_force_copy(tmp_path, capsys):
    source = tmp_path / "a.wav"
    source.write_bytes(wav_bytes())
    manifest = write_manifest(tmp_path / "r.jsonl", [recording(source)])
    assert invoke(tmp_path, capsys, [manifest])[0] == 0
    source.write_bytes(b"new bytes")
    result, report = invoke(tmp_path, capsys, [manifest], output="changed")
    assert result == 0 and report["copied"] == 1
    for receipt in (tmp_path / "cache").rglob("*.complete.json"):
        receipt.unlink()
    result, report = invoke(tmp_path, capsys, [manifest], output="no-receipt")
    assert result == 0 and report["copied"] == 1


def test_keyboard_interrupt_does_not_publish(tmp_path, capsys, monkeypatch):
    source = tmp_path / "a.wav"
    source.write_bytes(wav_bytes())
    manifest = write_manifest(tmp_path / "r.jsonl", [recording(source)])

    def interrupt(*args):
        raise KeyboardInterrupt

    monkeypatch.setattr(prepare, "_materialize", interrupt)
    result, report = invoke(tmp_path, capsys, [manifest])
    assert result == 1 and "interrupted" in report["failures"][0]["error"]
    assert not (tmp_path / "out").exists()


def test_name_collision_and_localize_command_rejection(tmp_path, capsys):
    one, two = tmp_path / "one", tmp_path / "two"
    one.mkdir()
    two.mkdir()
    first = write_manifest(one / "r.jsonl", [recording("missing")])
    second = write_manifest(two / "r.jsonl", [recording("missing")])
    result, report = invoke(tmp_path, capsys, [first, second])
    assert result == 1 and "collide" in report["failures"][0]["error"]
    manifest = write_manifest(
        tmp_path / "tar.jsonl", [recording("tar -xOf a.tar b.wav", "command")]
    )
    result, report = invoke(tmp_path, capsys, [manifest])
    assert result == 1 and "unsupported audio source" in report["failures"][0]["error"]


def test_extract_leaves_existing_file_source_unchanged(tmp_path, capsys):
    source = tmp_path / "a.wav"
    source.write_bytes(wav_bytes())
    row = recording(source)
    manifest = write_manifest(tmp_path / "r.jsonl", [row])
    result, report = invoke(tmp_path, capsys, [manifest], "extract-audio")
    assert result == 0 and report["unchanged"] == 1 and report["copied"] == 0
    assert read_manifest(tmp_path / "out/r.jsonl") == [row]


def test_truncated_gzip_manifest_reports_cause_without_publishing(tmp_path, capsys):
    manifest = write_manifest(
        tmp_path / "cuts.jsonl.gz", [{"type": "PaddingCut", "id": "padding"}]
    )
    manifest.write_bytes(manifest.read_bytes()[:-6])
    result, report = invoke(tmp_path, capsys, [manifest])
    assert result == 1
    assert report["failures"][0]["manifest"] == str(manifest)
    assert "end-of-stream" in report["failures"][0]["error"]
    assert not (tmp_path / "out").exists()

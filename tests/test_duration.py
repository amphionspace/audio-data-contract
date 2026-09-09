import gzip
import json
import wave

import pytest

from audio_data_contract import ArtifactRef, DatasetSpec
from audio_data_contract.cli import main
from audio_data_contract.duration import _run_job, catalog_sources, measure


def test_concurrent_gzip_producers_match_serial(tmp_path, monkeypatch):
    monkeypatch.setattr("audio_data_contract.duration.PIPELINE_BYTES", 0)
    sources = {}
    for index in range(3):
        path = tmp_path / f"{index}.jsonl.gz"
        path.write_bytes(gzip.compress(b'{"duration":0.25}\n' * 1001))
        sources[str(path)] = {"path": str(path), "mode": "manifest"}
    report = measure(sources, 8)
    for result in report["sources"].values():
        assert result["status"] == "ok"
        assert result["count"] == 1001
        assert result["seconds"] == 250.25


def test_manifest_ranges_and_gzip_match_serial(tmp_path):
    plain = tmp_path / "cuts.jsonl"
    rows = [
        {"duration": 0.125, "text": "中文"},
        {
            "type": "MixedCut",
            "tracks": [
                {"offset": 0, "cut": {"duration": 3}},
                {"offset": 1.5, "cut": {"duration": 2}},
            ],
        },
        {"duration": 1.75},
    ]
    content = ("\n" + "\n\n".join(json.dumps(r) for r in rows)).encode()
    plain.write_bytes(content)
    compressed = tmp_path / "cuts.jsonl.gz"
    compressed.write_bytes(gzip.compress(content))
    # Every byte is a possible partition boundary, including the final line.
    seconds = count = 0
    for start in range(0, len(content), 7):
        _, result = _run_job(("x", "range", (str(plain), start, start + 7), False))
        assert not result["errors"]
        seconds += result["seconds"]
        count += result["count"]
    assert count == 3
    assert seconds == 5.375
    sources = {
        str(p): {"path": str(p), "mode": "manifest"} for p in (plain, compressed)
    }
    for workers in (1, 2):
        report = measure(sources, workers)
        for result in report["sources"].values():
            assert result["status"] == "ok"
            assert result["count"] == 3
            assert result["seconds"] == 5.375
    # Exercise the decompression -> process pool path for one gzip input.
    report = measure({str(compressed): sources[str(compressed)]}, 2)
    assert report["sources"][str(compressed)]["seconds"] == 5.375


@pytest.mark.parametrize("value", [None, True, -1, 0, "2"])
def test_invalid_duration_is_an_error(value):
    _, result = _run_job(
        ("x", "block", json.dumps({"duration": value}).encode(), False)
    )
    assert result["errors"]


def test_clean_filter_and_corrupt_gzip(tmp_path):
    content = (
        b'{"duration":10,"custom":{"clean":{"pass":false}}}\n'
        b'{"duration":2,"custom":{"clean":{"pass":true}}}\n'
    )
    _, result = _run_job(("x", "block", content, True))
    assert result["seconds"] == 2
    assert result["count"] == result["skipped"] == 1
    _, result = _run_job(("x", "block", b'{"duration":2}', True))
    assert result["errors"]
    path = tmp_path / "bad.jsonl.gz"
    path.write_bytes(b"broken gzip")
    result = measure({"x": {"path": str(path), "mode": "manifest"}}, 2)
    assert result["sources"]["x"]["status"] == "error"


def test_audio_cli_counts_stereo_once_and_reports_bad_file(tmp_path):
    audio = tmp_path / "audio"
    audio.mkdir()
    path = audio / "stereo.wav"
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(2)
        stream.setsampwidth(2)
        stream.setframerate(16000)
        stream.writeframes(b"\0" * 64000)
    (audio / "alias.wav").symlink_to(path)
    output = tmp_path / "report.json"
    assert (
        main(
            [
                "stats-duration",
                "--audio-dir",
                str(audio),
                "--workers",
                "2",
                "--output",
                str(output),
            ]
        )
        == 0
    )
    result = next(iter(json.loads(output.read_text())["sources"].values()))
    assert result["seconds"] == 1
    assert result["count"] == 1
    (audio / "bad.wav").write_bytes(b"invalid")
    assert (
        main(
            [
                "stats-duration",
                "--audio-dir",
                str(audio),
                "--workers",
                "1",
                "--output",
                str(output),
            ]
        )
        == 1
    )
    result = next(iter(json.loads(output.read_text())["sources"].values()))
    assert "bad.wav" in result["errors"][0]


def test_catalog_reuses_sources_and_only_writes_complete_missing_splits(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "views").mkdir()
    (tmp_path / "views" / "empty.jsonl").write_text("")
    manifest = tmp_path / "segments.jsonl"
    manifest.write_text('{"duration":3600}\n')
    spec = DatasetSpec(
        dataset_id="demo",
        version="1",
        languages=("en",),
        tasks=("asr",),
        artifacts=(
            ArtifactRef("sup", "lhotse-supervisions", "data", manifest.name),
            ArtifactRef("missing", "lhotse-supervisions", "data", "absent.jsonl"),
            ArtifactRef("rec", "lhotse-recordings", "data", "long.jsonl"),
        ),
        splits={
            "train": {
                "supervisions_artifacts": ["sup", "sup"],
                "recordings_artifact": "rec",
            },
            "alias": {"supervisions_artifact": "sup"},
            "bad": {"supervisions_artifacts": ["sup", "missing"]},
            "known": {"statistics": {"duration_hours": 7}},
            "child": {"group": "train", "supervisions_artifact": "sup"},
        },
    )
    catalog = tmp_path / "catalog.jsonl"
    catalog.write_text(json.dumps(spec.to_dict()) + "\n")
    roots = tmp_path / "roots.json"
    roots.write_text(json.dumps({"data": str(tmp_path)}))
    sources, targets = catalog_sources(catalog, {"data": tmp_path})
    assert len(sources) == 2
    assert len(targets) == 3
    output = tmp_path / "report.json"
    args = [
        "stats-duration",
        "--catalog",
        str(catalog),
        "--roots",
        str(roots),
        "--workers",
        "2",
        "--output",
        str(output),
    ]
    before = catalog.read_bytes()
    assert main(args) == 1
    assert catalog.read_bytes() == before
    assert main([*args, "--write"]) == 1
    splits = json.loads(catalog.read_text())["splits"]
    assert splits["train"]["statistics"]["duration_hours"] == 1
    assert splits["alias"]["statistics"]["duration_hours"] == 1
    assert splits["known"]["statistics"]["duration_hours"] == 7
    assert "statistics" not in splits["bad"]
    assert "statistics" not in splits["child"]
    assert (tmp_path / "docs/data-overview.md").is_file()


def test_cli_rejects_zero_workers_and_write_without_catalog(tmp_path):
    for extra in (["--workers", "0"], ["--write"]):
        with pytest.raises(SystemExit):
            main(["stats-duration", "--audio-dir", str(tmp_path), *extra])

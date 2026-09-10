import gzip
import json
import runpy
import subprocess
import sys
import wave
from pathlib import Path

import pytest

from audio_data_contract import load_catalog, load_records, load_view_catalog

pytest.importorskip("orjson")
REPO = Path(__file__).resolve().parents[1]
convert = runpy.run_path(str(REPO / "scripts/target_asr/convert.py"))
reader = runpy.run_path(str(REPO / "scripts/target_asr/read.py"))
verifier = runpy.run_path(str(REPO / "scripts/target_asr/verify.py"))


def row(rid="positive", target="language English<asr_text>Keep Case", negative=False):
    return {"id": rid, "text": target, "enroll_wav": "/audio/enroll.wav",
            "mix_wav": "/audio/mix.wav", "n_spk": 2,
            **({"sample_type": "negative_distractor"} if negative else {})}


@pytest.mark.parametrize(("text", "language", "expected"), [
    ("language English<asr_text>Keep Case", "en", "Keep Case"),
    ("language Chinese<asr_text>你好，世界。", "zh", "你好，世界。"),
    ("UNCHANGED", "en", "UNCHANGED"),
])
def test_unwrap_preserves_transcript(text, language, expected):
    assert convert["normalize"](row(target=text), language)[1] == expected


def test_negative_empty_is_explicit_and_conflicts_fail():
    assert convert["normalize"](
        row(target="language None<asr_text>", negative=True), "en",
    )[1:] == ("", True)
    for bad in [row(target=""), row(negative=True), row(target="language None<asr_text>"),
                row(target="language Chinese<asr_text>中文"), row(target="<think>x")]:
        with pytest.raises(ValueError):
            convert["normalize"](bad, "en")


def test_sharegpt_extracts_only_target_and_audio():
    sample = {"messages": [{"role": "system", "content": "model prompt"},
                           {"role": "assistant", "content": "language English<asr_text>Hello"}],
              "audios": ["/audio/enroll.wav"],
              "chat_template_kwargs": {"id": "a", "n_spk": 2, "mix_wav": "/audio/mix.wav"}}
    data, text, negative = convert["normalize"](sample, "en")
    assert (text, negative, data["enroll_wav"]) == ("Hello", False, "/audio/enroll.wav")
    assert "messages" not in data


def test_root_mapping_uses_directory_boundaries_and_longest_root():
    roots = {"audio": "/data", "project": "/data/project"}
    assert convert["location"]("/data/project/x.wav", roots) == {
        "root_alias": "project", "relative_path": "x.wav",
    }
    for path in ("/database/x.wav", "/data/../private/x.wav"):
        with pytest.raises(ValueError):
            convert["location"](path, roots)


def fixture_job(tmp_path):
    pytest.importorskip("soundfile")
    audio = tmp_path / "audio"
    project = tmp_path / "project"
    audio.mkdir()
    project.mkdir()
    for filename in ("enroll.wav", "mix.wav"):
        with wave.open(str(audio / filename), "wb") as stream:
            stream.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
            stream.writeframes(b"\x00\x00" * 16000)
    samples = [row(), row("negative", "language None<asr_text>", True)]
    for sample in samples:
        sample["enroll_wav"] = str(audio / "enroll.wav")
        sample["mix_wav"] = str(audio / "mix.wav")
    src = project / "source.jsonl"
    src.write_text("".join(json.dumps(r) + "\n" for r in samples))
    roots = {"legacy_asr": str(audio), "amphion_asr_project": str(project)}
    job = {"dataset_id": "fixture", "version": "records-1", "source_version": "source-1",
           "view_id": "fixture/target-asr", "date": "2026-09-10", "language": "en",
           "description": "fixture", "sources": [{"name": "source",
               "kind": "target-asr-jsonl", "root_alias": "amphion_asr_project",
               "relative_path": "source.jsonl"}]}
    return job, roots


def test_conversion_registration_and_portable_reader(tmp_path):
    job, roots = fixture_job(tmp_path)
    job["sources"].append({**job["sources"][0], "name": "aggregate",
                           "equivalent_to": ["train_2spk", "train_neg"]})
    convert["convert_job"](job, roots, 1, {})
    out = Path(roots["amphion_asr_project"]) / "data/audio-records/fixture/records-1"
    report = json.loads((out / "registration.json").read_text())
    cat = tmp_path / "catalog.jsonl"
    cat.write_text("".join(json.dumps(d) + "\n" for d in report["datasets"]))
    view = tmp_path / "views.jsonl"
    view.write_text(json.dumps(report["view"]) + "\n")
    catalog = load_catalog(cat)
    assert len(load_view_catalog(view, catalog)) == 1
    spec = catalog.get("fixture", "records-1")
    assert spec.splits["train"]["statistics"]["records"] == 2
    stats = spec.splits["train"]["statistics"]
    assert stats["duration_hours"] == pytest.approx(2 / 3600)
    assert stats["unique_mixture_duration_hours"] == pytest.approx(1 / 3600)
    with gzip.open(out / "audio-index.jsonl.gz", "rt") as stream:
        assert len(list(stream)) == 2
    records = list(load_records(out / "train_2spk.jsonl.gz"))
    assert records[0].target == "Keep Case"
    assert records[0].slot("mixture").ref.cut_id != records[0].slot("enrollment").ref.cut_id
    negative = next(load_records(out / "train_neg.jsonl.gz"))
    assert negative.target == "" and negative.labels["target_present"] is False
    assert verifier["verify"](spec, catalog, roots)["records"] == 2
    moved = tmp_path / "moved-audio"
    Path(roots["legacy_asr"]).rename(moved)
    roots["legacy_asr"] = str(moved)
    assert reader["resolve_audio"](records[0], catalog, roots)["mixture"]["path"] == str(moved / "mix.wav")
    with pytest.raises(FileExistsError):
        convert["convert_job"](job, roots, 1, {})


@pytest.mark.parametrize("failure", ["missing", "duplicate", "aggregate"])
def test_bad_sources_do_not_publish(tmp_path, failure):
    job, roots = fixture_job(tmp_path)
    project = Path(roots["amphion_asr_project"])
    if failure == "missing":
        (Path(roots["legacy_asr"]) / "mix.wav").unlink()
    elif failure == "duplicate":
        path = project / "source.jsonl"
        path.write_text(path.read_text() * 2)
    else:
        job["sources"].append({**job["sources"][0], "name": "incomplete",
                               "equivalent_to": ["train_2spk"]})
    with pytest.raises((ValueError, RuntimeError)):
        convert["convert_job"](job, roots, 1, {})
    assert not (project / "data/audio-records/fixture/records-1").exists()


def test_cli_with_multiple_audio_workers(tmp_path):
    job, roots = fixture_job(tmp_path)
    recipe = tmp_path / "recipe.json"
    recipe.write_text(json.dumps({"jobs": [job]}))
    root_file = tmp_path / "roots.json"
    root_file.write_text(json.dumps(roots))
    subprocess.run([
        sys.executable, str(REPO / "scripts/target_asr/convert.py"), "convert",
        "--recipe", str(recipe), "--roots", str(root_file), "--workers", "2",
    ], check=True, capture_output=True, text=True)
    out = Path(roots["amphion_asr_project"]) / "data/audio-records/fixture/records-1"
    assert len(list(load_records(out / "train_2spk.jsonl.gz"))) == 1


def test_train_and_test_parent_statistics_are_separate(tmp_path):
    job, roots = fixture_job(tmp_path)
    job["sources"].append({**job["sources"][0], "name": "test_source", "split": "test_2mix"})
    convert["convert_job"](job, roots, 1, {})
    out = Path(roots["amphion_asr_project"]) / "data/audio-records/fixture/records-1"
    spec = json.loads((out / "registration.json").read_text())["datasets"][1]
    assert spec["splits"]["train"]["statistics"]["records"] == 2
    assert spec["splits"]["test"]["statistics"]["records"] == 2
    assert spec["splits"]["test"]["records_artifacts"] == ["test_2mix"]

"""Verify RealMAN audio-to-manifest preparation with actual small FLAC files."""

import pytest

pytest.importorskip("lhotse")

import importlib.util
import json
from pathlib import Path

import numpy as np
import soundfile as sf
from lhotse import load_manifest


def test_realman_official_splits_and_transcript_keys(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "prepare_farfield",
        (Path(__file__).resolve().parents[2] / "scripts/icefall").joinpath(
            "prepare_farfield_manifests.py"
        ),
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    corpus = tmp_path / "RealMAN"
    names = {
        "train": "TRAIN_M_BAD2_0010_0003_CH0.flac",
        "val": "VAL_S_CARE_P0002_P0002W0001_CH0.flac",
        "test": "TEST_M_BAD2_0010_0003_CH0.flac",
    }
    for split, name in names.items():
        directory = corpus / "asr_mono" / split
        directory.mkdir(parents=True)
        sf.write(directory / name, np.zeros(1600, dtype=np.float32), 16000)
    (corpus / "asr_mono/.complete.json").write_text(
        json.dumps({"counts": {s: 1 for s in names}})
    )
    (corpus / "transcriptions.trn").write_text(
        "你 好 Open AI (S0010-0003)\n会 议 (SP0002-P0002W0001)\n"
    )
    result = module.prepare_realman(tmp_path, tmp_path / "lhotse")
    assert set(result) == {"train", "dev", "test"}
    for split, stats in result.items():
        assert stats["recordings"] == stats["supervisions"] == 1
        rec = next(iter(load_manifest(stats["recordings_path"])))
        sup = next(iter(load_manifest(stats["supervisions_path"])))
        assert rec.load_audio().shape == (1, 1600)
        assert sup.text == ("会议" if split == "dev" else "你好 Open AI")
        assert sup.recording_id == rec.id and sup.channel == 0

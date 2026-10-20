import random
import runpy
from pathlib import Path

import pytest

pytest.importorskip("soundfile")
pytest.importorskip("yaml")
v3 = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/ts_robust/build_ts_real_train_v3.py"))
real = v3["real"]


def emilia2_entry():
    # S1 alone 0-12, S2 13-18, S1 19-24, S2 25-30: windows of one speaker exist, and both speak outside them.
    e = {"cut_id": "x_dlg_00000", "offset": 10.0, "duration": 40.0, "file": {},
         "sups": [(0.0, 5.5, "w:S1", "一"), (6.0, 12.0, "w:S1", "二"), (13.0, 18.0, "w:S2", "三"),
                  (19.0, 24.0, "w:S1", "四"), (25.0, 30.0, "w:S2", "五")]}
    real.finish_entry(e)
    return e


def test_emilia2_windows_have_one_speaker_and_an_absent_speaker_enrolled_from_outside():
    entries = {f"w{i}": emilia2_entry() for i in range(20)}
    plans, _ = v3["plan_emilia2"](entries, random.Random(0), quota=20)
    assert plans
    for plan in plans:
        window = plan["window"]
        assert {u[2] for u in window["utts"]} == {plan["target"]}
        assert plan["absent"] != plan["target"]
        rec = entries[plan["entry"]]
        for who in (plan["target"], plan["absent"]):
            assert real.eligible_enrollments(rec, who, window["lo"], window["hi"])


def test_records_point_into_the_diarization_window_of_the_source_file():
    entries = {"w0": emilia2_entry()}
    entries["w0"]["file"] = {"relative_path": "datasets/emilia2/x.flac", "sample_rate": 16000, "channels": 1,
                             "num_frames": 16000 * 100}
    plans, _ = v3["plan_emilia2"](entries, random.Random(1), quota=1)
    audio = {}
    records = v3["emilia2_records"](plans, entries, random.Random(0), audio)
    pos, neg = records
    # write() looks the audio index up by the refs' cut_id
    assert {s["ref"]["cut_id"] for r in records for s in r["audio_slots"]} <= set(audio)
    assert pos["labels"]["target_present"] and not neg["labels"]["target_present"]
    assert pos["audio_slots"][1]["ref"] == neg["audio_slots"][1]["ref"]  # one window, two enrollments
    assert pos["audio_slots"][1]["ref"]["start"] == pytest.approx(10.0 + plans[0]["window"]["lo"])
    assert neg["target"] == "" and pos["target"]


def test_speaker_check_drops_pairs_that_contradict_their_labels():
    qc = {str(i): [0.8 + 0.01 * (i % 10), 0.2 + 0.01 * (i % 10)] for i in range(100)}
    qc["7"] = [0.85, 0.9]  # the "absent" speaker sounds like the window's speaker
    qc["8"] = [0.25, 0.1]  # the "present" speaker does not
    records = [{"labels": {"pair": int(k), "target_present": t}} for k in qc for t in (True, False)]
    kept, stats = v3["qc_filter"](records, qc)
    pairs = {r["labels"]["pair"] for r in kept}
    assert 7 not in pairs and 8 not in pairs and 0 in pairs
    assert stats["negative_too_similar"] >= 1 and stats["positive_too_different"] >= 1

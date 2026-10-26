import itertools
import runpy
from pathlib import Path

import pytest

pytest.importorskip("soundfile")
pytest.importorskip("yaml")
SCRIPTS = Path(__file__).resolve().parents[1] / "scripts" / "ts_real"
real = runpy.run_path(str(SCRIPTS / "build.py"))


def entry(utts):
    from collections import defaultdict

    utts = sorted(utts)
    e = {"sups": utts, "starts": [u[0] for u in utts], "longest": max(u[1] - u[0] for u in utts),
         "eligible": defaultdict(list)}
    for s, t, spk, text in utts:
        if t - s >= real["ENROLL_MIN"]:
            others = sum(max(0.0, min(t, oe) - max(s, os_)) for os_, oe, ospk, _ in real["overlapping"](e, s, t) if ospk != spk)
            if others <= real["ENROLL_MAX_OVERLAP"] * (t - s):
                e["eligible"][spk].append((s, t, text))
    return e


# A speaks 0-5 and 30-36; B speaks 4-9 (overlapping A) and 20-26; C speaks 50-56.
UTTS = [(0.0, 5.0, "A", "甲一"), (30.0, 36.0, "A", "甲二"), (4.0, 9.0, "B", "乙一"), (20.0, 26.0, "B", "乙二"),
        (50.0, 56.0, "C", "丙一")]


def test_a_window_never_cuts_an_utterance_and_keeps_overlaps_together():
    e = entry(UTTS)
    lo, hi, inside = real["closure"](e, 1.0, 6.0)
    assert (lo, hi) == (0.0, 9.0) and {u[2] for u in inside} == {"A", "B"}
    lo, hi, inside = real["closure"](e, 21.0, 24.0)
    assert (lo, hi) == (20.0, 26.0) and [u[2] for u in inside] == ["B"]


def test_enrollment_comes_from_outside_the_window_and_is_little_overlapped():
    e = entry(UTTS)
    # A's first utterance is overlapped by B for 1 s of 5 s, which is within the 20% allowance.
    assert real["eligible_enrollments"](e, "A", 20.0, 26.0) == [(0.0, 5.0, "甲一"), (30.0, 36.0, "甲二")]
    assert real["eligible_enrollments"](e, "A", 29.0, 37.0) == [(0.0, 5.0, "甲一")]
    # B's first utterance is overlapped by A for 1 s: still eligible; its second one is inside the window.
    assert [u[2] for u in real["eligible_enrollments"](e, "B", 19.0, 27.0)] == ["乙一"]


def test_overlap_ratio_counts_time_with_another_speaker_active():
    window = [(0.0, 5.0, "A", ""), (4.0, 9.0, "B", "")]
    assert real["overlap_ratio"]([window[0]], window) == pytest.approx(0.2)
    assert real["overlap_ratio"]([window[1]], window) == pytest.approx(0.2)
    assert real["overlap_ratio"]([], window) == 0.0


def test_candidate_windows_do_not_overlap_and_stay_within_the_service_limit():
    import random

    e = entry(UTTS)
    windows = real["candidate_windows"](e, random.Random(0))
    assert windows and all(w["hi"] - w["lo"] <= real["MAX_WINDOW"] for w in windows)
    assert all(a["hi"] <= b["lo"] for a, b in itertools.pairwise(windows))


def test_a_window_cannot_extend_past_the_end_of_the_audio():
    import random

    e = entry(UTTS)
    e["duration"] = 12.0
    assert all(w["hi"] <= 12.0 for w in real["candidate_windows"](e, random.Random(1)))


def test_target_windows_keep_the_target_whole_and_clip_everyone_else():
    import random

    e = entry(UTTS)
    whole = {u[:3] for u in UTTS}
    for seed in range(20):
        for w in real["target_windows"](e, random.Random(seed)):
            assert w["hi"] - w["lo"] <= real["MAX_WINDOW"]
            for u in w["utts"]:
                assert w["lo"] <= u[0] < u[1] <= w["hi"]
                if u[2] == w["target"]:
                    assert u[:3] in whole and u not in w["clipped"]
                else:
                    assert (u[:3] not in whole) == (u in w["clipped"])
            # The target's first utterance in the window is preceded by at most 4 s.
            first = min(u[0] for u in w["utts"] if u[2] == w["target"])
            assert 0.0 <= first - w["lo"] <= 4.0


def test_overlap_buckets_split_at_5_20_and_50_percent():
    bucket = real["overlap_bucket"]
    assert [bucket(r) for r in (0.0, 0.05, 0.06, 0.2, 0.21, 0.5, 0.51, 1.0)] == [
        "o0", "o0", "o20", "o20", "o50", "o50", "o100", "o100"]


def test_stored_enrollment_appends_clean_utterances_outside_the_window():
    import random

    # A: 0-5 (B talks over 4-5), 30-36, 40-43 (C talks over 41-42), 60-64, 70-72; window 28-38.
    e = entry(UTTS + [(40.0, 43.0, "A", "甲三"), (41.0, 42.0, "C", "丙二"), (60.0, 64.0, "A", "甲四"),
                      (70.0, 72.0, "A", "甲五")])
    pieces = real["enrollment_pieces"](e, "A", (0.0, 5.0), 28.0, 38.0, random.Random(0))
    assert pieces[0] == (0.0, 5.0)
    # Never the window's utterance, never one someone else talks in; up to ENROLL_STORE (10 s).
    assert set(pieces[1:]) <= {(60.0, 64.0), (70.0, 72.0)} and len(pieces) == 3
    # Others are counted over the first ENROLL_CROP (5 s) of the joined pieces: B's 1 s inside A's first utterance.
    assert real["pieces_others"](e, "A", pieces) == (1.0, ["B"])
    assert real["pieces_others"](e, "A", [(60.0, 64.0), (0.0, 5.0)]) == (0.0, [])

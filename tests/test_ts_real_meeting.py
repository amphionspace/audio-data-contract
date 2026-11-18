import runpy
from pathlib import Path

import pytest

pytest.importorskip("soundfile")
pytest.importorskip("yaml")
meeting = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts" / "ts_real" / "meeting_segments.py"))
real = meeting["real"]


def entry(utts):
    e = {"sups": [tuple(u) for u in utts]}
    real.finish_entry(e)
    return e


def spans(segs):
    return [(s, e, spk) for s, e, spk, _ in segs]


def test_segments_merge_one_speakers_close_utterances_until_someone_else_starts_or_the_cap():
    e = entry([(0.0, 3.0, "A", "一"), (3.5, 6.0, "A", "二"),  # gap 0.5: merged
               (10.0, 13.0, "A", "三"), (13.2, 13.4, "B", "嗯"), (13.6, 16.0, "A", "四"),  # B starts in the gap
               (20.0, 26.0, "A", "五"), (26.5, 32.0, "A", "六"),  # merged would be 12 s > MERGE_CAP
               (40.0, 40.8, "C", "对")])  # shorter than MIN_SEGMENT
    assert spans(meeting["segments"](e)) == [(0.0, 6.0, "A"), (10.0, 13.0, "A"), (13.6, 16.0, "A"),
                                             (20.0, 26.0, "A"), (26.5, 32.0, "A")]


def test_absent_needs_silence_within_half_a_second_and_present_needs_whole_utterances():
    e = entry([(0.0, 6.0, "A", "甲"), (2.0, 2.3, "B", "嗯"), (3.0, 4.0, "C", "对的"), (5.5, 7.0, "D", "我说"),
               (6.4, 8.0, "E", "好"), (20.0, 25.0, "F", "后来")])
    classify = meeting["classify"]
    assert classify(e, "F", 0.0, 6.0)[0] == "neg"
    assert classify(e, "E", 0.0, 6.0)[0] == "borderline"  # starts 0.4 s after the segment: within the margin
    assert classify(e, "B", 0.0, 6.0)[0] == "borderline"  # 0.3 s < PRESENT_MIN
    assert classify(e, "D", 0.0, 6.0)[0] == "clipped"  # 0.5 s inside, the rest after the segment
    kind, seconds, own = classify(e, "C", 0.0, 6.0)
    assert (kind, seconds, [u[3] for u in own]) == ("pos", 1.0, ["对的"])


def test_a_box_starts_one_segment_before_its_first_words_and_skips_its_enrollment():
    e = entry([(0.0, 4.0, "A", "一"), (10.0, 14.0, "B", "二"), (20.0, 24.0, "A", "三"), (30.0, 35.0, "C", "四"),
               (40.0, 44.0, "A", "五")])
    segs = meeting["segments"](e)
    plans, dropped = meeting["plan_requests"](e, segs, {"C": [(30.0, 35.0)]})
    assert [(segs[i][0], kind) for i, _, kind, _, _ in plans] == [(20.0, "neg"), (40.0, "neg")]
    assert dropped == {"before_first_talk": 2, "holds_enrollment": 1}


def test_overlap_seconds_counts_time_with_two_or_more_speakers():
    utts = [(0.0, 5.0, "A", ""), (4.0, 9.0, "B", ""), (4.5, 6.0, "C", "")]
    assert meeting["overlap_seconds"](utts, 0.0, 9.0) == pytest.approx(2.0)
    assert meeting["overlap_seconds"](utts, 4.8, 9.0) == pytest.approx(1.2)


quarantine = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts" / "ts_real" / "meeting_quarantine.py"))


def test_missing_run_counts_consecutive_transcript_characters_the_annotation_lacks():
    run = quarantine["longest_missing_run"]
    assert run("我们开始吧", "我们开始吧") == 0
    assert run("我们吧", "我们现在开始吧") == 4
    assert run("开会", "嗯开会呃好") == 2  # two separate runs of 1 and 2
    assert quarantine["chars"]("好的，我们 开始吧。OK") == "好的我们开始吧OK"


def test_segments_are_rejected_for_missing_speech_or_a_wrong_speaker_only_when_judgeable():
    reasons = quarantine["reasons"]
    alone = {"owner": "A", "utts": [{"speaker": "aishell4:A", "text": "我们吧"}]}
    shared = {"owner": "A", "utts": [{"speaker": "aishell4:A", "text": "我们吧"}, {"speaker": "aishell4:B", "text": "对"}]}
    fine = {"solo_s": 5.0, "owner_sim": 0.7, "best_other": "B", "best_other_sim": 0.65}
    wrong = {"solo_s": 5.0, "owner_sim": 0.3, "best_other": "B", "best_other_sim": 0.6}
    assert [r["reason"] for r in reasons(alone, "我们现在开始吧", fine)] == ["annotation_missing_speech"]
    assert reasons(shared, "我们现在开始吧", fine) == []  # someone else is annotated: the text check does not apply
    assert [r["reason"] for r in reasons(alone, "我们吧。", wrong)] == ["speaker_label"]
    assert reasons(alone, "我们吧", {**wrong, "solo_s": 2.0}) == []  # too little solo speech to judge


nested = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts" / "ts_real" / "meeting_nested.py"))


def test_a_segment_is_nested_when_one_utterance_of_someone_else_covers_most_of_it():
    inside = nested["inside_other"]
    interjection = [{"speaker": "aishell4:B", "start": 0.0, "duration": 2.0},  # B's long turn, clipped to the segment
                    {"speaker": "aishell4:A", "start": 0.5, "duration": 1.0}]
    assert inside("A", 2.0, interjection) == 1.0
    crosstalk = [{"speaker": "aishell4:A", "start": 0.0, "duration": 6.0}, {"speaker": "aishell4:B", "start": 0.0, "duration": 1.0},
                 {"speaker": "aishell4:C", "start": 4.0, "duration": 2.0}]
    assert inside("A", 6.0, crosstalk) == pytest.approx(1 / 3)  # the longest single other utterance, not their sum
    assert inside("A", 3.0, [{"speaker": "aishell4:A", "start": 0.0, "duration": 3.0}]) == 0.0

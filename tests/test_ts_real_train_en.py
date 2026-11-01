import importlib.util
import random
from collections import Counter
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
sf = pytest.importorskip("soundfile")
pytest.importorskip("yaml")

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts/ts_robust"


def load(name):
    spec = importlib.util.spec_from_file_location(f"test_{name}", SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


en = load("build_ts_real_train_en")
real = en.real


class FakeCheck:
    """Voice check stand-in: an enrollment fails when it starts at one of ``bad`` times."""

    def __init__(self, bad=()):
        self.bad, self.calls = set(bad), []

    def check(self, recordings, recording, speaker, pieces):
        self.calls.append((recording, speaker, pieces[0]))
        return {"passed": pieces[0][0] not in self.bad, "audio": "mixture_channel"}


def wav(path, seconds):
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), np.zeros(int(seconds * 16000), dtype="float32"), 16000, subtype="PCM_16")
    return str(path)


def session(tmp_path, name, speakers, extra=()):
    """A meeting where ``speakers`` take turns (4 s each, 0.5 s apart, up to 140 s), then the ``extra`` utterances."""
    sups, t, i = [], 0.0, 0
    while t < 140.0:
        sups.append((round(t, 3), round(t + 4.0, 3), speakers[i % len(speakers)], f"words of turn {i} here"))
        t, i = t + 4.5, i + 1
    sups += list(extra)
    entry = {"path": wav(tmp_path / f"{name}.wav", 200), "sups": sups, "duration": 200.0, "excluded": {},
             "source": "Array1-01", "language": "en", "enrollmix": False, "channels": 1}
    real.finish_entry(entry)
    return entry


@pytest.fixture
def recordings(tmp_path, monkeypatch):
    monkeypatch.setattr(en, "DATA", tmp_path)
    monkeypatch.setattr(en, "_ROWS", {})
    late = [(150.0, 154.5, "D", "the late speaker talks"), (160.0, 164.5, "D", "and talks again here")]
    return {"M90": session(tmp_path, "M90", ["A", "B", "C"], late), "M91": session(tmp_path, "M91", ["A", "B", "C"])}


def test_icsi_meetings_sharing_a_participant_with_a_held_out_meeting_are_dropped():
    participants = {"Bmr013": {"me013", "fe008"}, "Bmr021": {"me018"}, "Bmr001": {"me013", "mn005"},
                    "Bed005": {"mn005", "fn002x"}, "Bed006": {"me018x"}}
    kept, dropped = en.disjoint_meetings(participants, ["Bmr013", "Bmr021"])
    assert kept == ["Bed005", "Bed006"] and dropped == ["Bmr001"]


def test_notsofar_meeting_ignores_the_device():
    assert en.meeting_of("notsofar", "MTG_30830_sc_meetup_0") == "MTG_30830"
    assert en.meeting_of("ami", "ES2004a") == "ES2004a"


def test_records_pair_up_and_never_enroll_a_speaker_of_the_window(recordings):
    plans = real.plan_samples("ami", {"windows": en.UNLIMITED, "language": "en"}, recordings, random.Random(0))
    plans = {k.rsplit("-", 1)[1]: v for k, v in plans.items()}
    audio = {}
    records = en.make_records("ami", plans, recordings, random.Random(1), audio, FakeCheck(), Counter())
    assert records and len(records) % 2 == 0
    sources = set()
    for pos, neg in zip(records[::2], records[1::2]):
        assert pos["labels"]["target_present"] and not neg["labels"]["target_present"]
        assert pos["labels"]["pair"] == neg["labels"]["pair"]
        assert pos["audio_slots"][1]["ref"] == neg["audio_slots"][1]["ref"]
        utts = pos["metadata"]["window_utts"]
        speakers = {u["speaker"] for u in utts}
        assert pos["metadata"]["target_speaker"] in speakers
        assert neg["metadata"]["target_speaker"] not in speakers  # speaker IDs repeat across the two sessions
        own = [u["text"] for u in utts if u["speaker"] == pos["metadata"]["target_speaker"]]
        assert pos["target"] == " ".join(own) and neg["target"] == ""
        assert pos["language"] == "en" and all(s["ref"]["channel"] == 0 for r in (pos, neg) for s in r["audio_slots"])
        sources.add(neg["labels"]["absent_source"])
        assert {s["ref"]["cut_id"] for r in (pos, neg) for s in r["audio_slots"]} <= set(audio)
    assert sources == {"same_recording", "other_recording"}


def test_window_utts_keep_speech_without_a_transcript_marked_excluded(recordings):
    entry = recordings["M91"]
    first = entry["sups"][0]
    entry["excluded"] = {first[:3]: "unintelligible"}
    window = {"lo": 0.0, "hi": 9.0, "utts": entry["sups"][:2]}
    utts = en.window_utterances("ami", entry, window)
    assert utts[0]["excluded"] == "unintelligible" and "excluded" not in utts[1]
    assert utts[0]["speaker"] == "ami:A" and utts[1]["start"] == 4.5


def test_an_enrollment_that_fails_the_voice_check_is_replaced_and_a_pair_without_one_is_dropped(recordings):
    plans = real.plan_samples("ami", {"windows": en.UNLIMITED, "language": "en"}, recordings, random.Random(0))
    plans = {k.rsplit("-", 1)[1]: v for k, v in plans.items()}
    # D has two utterances: failing one of them replaces it with the other; failing both drops D's pairs.
    for bad, kept in (({150.0}, True), ({150.0, 160.0}, False)):
        stats = Counter()
        records = en.make_records("ami", plans, recordings, random.Random(1), {}, FakeCheck(bad), stats)
        enrolled_d = [r for r in records if r["metadata"]["target_speaker"] == "ami:D"]
        assert bool(enrolled_d) == kept
        for r in enrolled_d:
            assert r["audio_slots"][0]["ref"]["start"] == 160.0
            if "enrollment_replaced" in r["metadata"]:
                assert not r["metadata"]["enrollment_replaced"]["voice_check"]["passed"]
        dropped = stats["neg/dropped/closer_to_another_speaker"]
        assert stats["pairs_dropped"] == (0 if kept else dropped) and (kept or dropped) and len(records) % 2 == 0
        assert all(r["metadata"]["enroll_voice_check"]["passed"] for r in records)


def test_notsofar_train_tags_pause_is_dropped_and_sn_marks_missing_words():
    english = real._english()
    assert english.clean("Ah, that's an issue. <PAUSE/> Fire station. <FILL/>", "notsofar") == (
        "Ah, that's an issue. Fire station.", None)
    assert english.clean("<ST/> has to be <SN/> we have to be on point", "notsofar")[1] == "undocumented_tag"

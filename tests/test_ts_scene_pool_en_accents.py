import random
import runpy
import sys
from collections import Counter
from pathlib import Path

import pytest

pytest.importorskip("lance")
pytest.importorskip("yaml")
SCRIPTS = Path(__file__).resolve().parents[1] / "scripts/ts_robust"
pool = runpy.run_path(str(SCRIPTS / "build_ts_scene_pool.py"))


def corpus(name, speakers, groups=None, target=True, utterances=8):
    """A Corpus with ``utterances`` 3 s utterances per speaker, drawn by accent share when ``groups`` is given."""
    c = object.__new__(pool["Corpus"])
    c.name, c.weight, c.target = name, 1.0, target
    c.speakers = [f"{name}:{s}" for s in speakers]
    total = len(speakers) * utterances
    c.rows = {"cut_id": [f"u{i}" for i in range(total)], "text": [f"sentence {i}" for i in range(total)],
              "root_alias": ["aidc_data"] * total, "relative_path": [f"x/u{i}.wav" for i in range(total)],
              "sample_rate": [16000] * total, "start_frame": [0] * total, "num_frames": [48000] * total,
              "channels": [1] * total}
    c.plain = list(c.rows["text"])
    c.duration = [3.0] * total
    c.session = None
    c.by_speaker = [list(range(i * utterances, (i + 1) * utterances)) for i in range(len(speakers))]
    c.accent, c.cum_weights = {}, None
    if groups:
        counts = Counter(groups)
        shares = pool["accent_shares"](counts)
        c.accent = dict(zip(c.speakers, groups))
        c.cum_weights = list(pool["accumulate"](shares[g] / counts[g] for g in groups))
    return c


def builder(corpora):
    b = object.__new__(pool["Builder"])
    b.language, b.rng, b.xsession = "en", random.Random(0), False
    b.corpora, b.targets = corpora, [c for c in corpora if c.target]
    b.neighbors, b.hard_rank = None, 10
    b.where = {name: (c, i) for c in corpora for i, name in enumerate(c.speakers)}
    b.accent = {n: g for c in corpora for n, g in c.accent.items()}
    b.alike = {}
    b.audio, b.pending = {}, {}
    return b


@pytest.mark.parametrize(("answer", "group"), [
    ("Scottish English", "scotland"),
    ("India and South Asia (India, Pakistan, Sri Lanka)", "south_asia"),  # commas inside one preset answer
    ("India and South Asia (India, Pakistan, Sri Lanka),bangladesh", "south_asia"),
    ("United States English,Midwestern,Chicago", "us"),  # free text next to a preset adds nothing
    ("Northern Irish", "ireland"),
    ("German English", "other"),
    ("United States English,England English", None),  # two groups: no single accent
    ("", None),
])
def test_accent_groups_come_from_the_cv_answers(answer, group):
    assert pool["accent_group"](answer) == group


def test_accent_shares_are_capped_and_flatter_than_speaker_counts():
    counts = {"us": 3600, "england": 1060, "south_asia": 750, "canada": 460, "aus_nz": 390, "africa": 130,
              "ireland": 95, "scotland": 80, "southeast_asia": 150, "hong_kong": 47, "wales": 26, "caribbean": 13,
              "other": 100}
    shares = pool["accent_shares"](counts)
    assert sum(shares.values()) == pytest.approx(1.0)
    assert max(shares.values()) <= pool["MAX_ACCENT_SHARE"] + 1e-9
    assert shares["us"] == pytest.approx(pool["MAX_ACCENT_SHARE"])
    assert shares["scotland"] > counts["scotland"] / sum(counts.values()) * 2  # rare accents gain
    uncapped = sorted((g for g in counts if shares[g] < pool["MAX_ACCENT_SHARE"] - 1e-9), key=counts.get)
    assert [shares[g] for g in uncapped] == sorted(shares[g] for g in uncapped)  # order kept
    ratio = shares["scotland"] / shares["wales"]
    assert ratio == pytest.approx((counts["scotland"] / counts["wales"]) ** pool["ACCENT_EXPONENT"])
    with pytest.raises(ValueError):
        pool["accent_shares"]({"a": 1, "b": 2})  # two groups cannot both stay under the cap


def test_cs_dialogue_text_loses_tags_and_marked_utterances_are_skipped():
    assert pool["tagless"]("<NON/> Yeah, I think they <SPK/> like it <FIL/> .") == "Yeah, I think they like it."
    skip = pool["SKIP_TEXT"]["cs_dialogue_en"]
    assert skip.search("he said <NPS/> no") and skip.search("I ** went")
    assert not skip.search("<FIL/> uh okay")


def test_uniform_draws_match_the_existing_pools_and_weighted_draws_follow_the_shares():
    plain = corpus("librispeech", [str(i) for i in range(50)])
    a, b = random.Random(7), random.Random(7)
    assert [plain.draw_speaker(a) for _ in range(100)] == [b.randrange(50) for _ in range(100)]
    groups = ["us"] * 90 + ["scotland"] * 5 + ["wales"] * 5 + [f"g{i}" for i in range(7) for _ in range(10)]
    cv = corpus("common_voice_en", [str(i) for i in range(len(groups))], groups)
    rng = random.Random(1)
    drawn = Counter(groups[cv.draw_speaker(rng)] for _ in range(20000))
    shares = pool["accent_shares"](Counter(groups))
    for group, share in shares.items():
        assert drawn[group] / 20000 == pytest.approx(share, abs=0.015)
    assert drawn["us"] / 20000 < 0.2  # 90 of 175 speakers, capped


def test_twins_enroll_a_speaker_drawn_like_the_targets_and_records_name_the_accent():
    groups = ["us"] * 40 + ["scotland"] * 4 + [f"g{i}" for i in range(6) for _ in range(4)]
    cv = corpus("common_voice_en", [str(i) for i in range(len(groups))], groups)
    other = corpus("librispeech", [str(i) for i in range(30)], target=False)
    b = builder([other, cv])
    twins = Counter()
    for number in range(600):
        scene, twin = b.solo_pair(True)
        assert twin["targets"] == [] and twin["target_speaker"] != scene["target_speaker"]
        assert twin["target_speaker"].startswith("common_voice_en:")  # same corpus as the targets
        twins[b.accent[twin["target_speaker"]]] += 1
        present = pool["record"]("en", number, scene, " ", pair=number, accent=b.accent[scene["target_speaker"]])
        absent = pool["record"]("en", number + 1, twin, " ", pair=number, accent=b.accent[twin["target_speaker"]])
        assert present["labels"]["accent"] in groups and absent["labels"]["accent"] in groups
        assert absent["target"] == "" and present["target"]
    shares = pool["accent_shares"](Counter(groups))
    assert twins["us"] / 600 == pytest.approx(shares["us"], abs=0.05)
    assert "accent" not in pool["record"]("en", 0, scene, " ")["labels"]  # other pools keep their labels


def test_lhotse_splits_become_rows_with_spans_inside_their_recordings(monkeypatch):
    recordings = [{"id": "r1", "sources": [{"type": "file", "channels": [0], "source": "/workspace/data/datasets/c/a.wav"}],
                   "sampling_rate": 16000, "num_samples": 32000, "duration": 2.0, "channel_ids": [0]}]
    supervisions = [{"id": "s1", "recording_id": "r1", "start": 0.0, "duration": 2.0004, "speaker": "0001", "text": "Hi."}]
    rows = {"recordings": recordings, "supervisions": supervisions}
    monkeypatch.setitem(pool["lhotse_table"].__globals__, "lhotse_rows", lambda entry, split, role: iter(rows[role]))
    table = pool["lhotse_table"]({}, "train").to_pydict()
    assert table["relative_path"] == ["datasets/c/a.wav"] and table["root_alias"] == ["aidc_data"]
    assert table["cut_id"] == ["s1"] and table["speaker"] == ["0001"]
    assert table["start_frame"][0] + table["num_frames"][0] <= 32000  # never past the recording


def test_neighbour_candidates_of_the_accent_pools_are_the_corpora_they_draw_from():
    sys.path.insert(0, str(SCRIPTS))
    try:
        neighbors = runpy.run_path(str(SCRIPTS / "speaker_neighbors.py"))
    finally:
        sys.path.remove(str(SCRIPTS))
    for mode, corpora in (("cv", pool["CV_ACCENT_CORPORA"]), ("csd", pool["CS_DIALOGUE_CORPORA"])):
        target = next(c[0] for c in corpora if c[4])
        assert neighbors["POOL_PEERS"][target] == {c[0] for c in corpora}, mode
    assert {c[0] for c in neighbors["EN_ACCENT_CORPORA"]["en"]} == set(pool["HELD_OUT_SPEAKERS"]) - {"common_voice_es"}
    assert neighbors["POOL_PEERS"]["common_voice_es"] == {c[0] for c in pool["ES_CORPORA"]}
    assert [c[:3] for c in neighbors["ES_ACCENT_CORPORA"]["es"]] == [c[:3] for c in pool["ES_CORPORA"]]


@pytest.mark.parametrize("answer, group", [
    ("México", "mexico"), ("Ciudad de México", "mexico"), ("España: Islas Canarias", "canary"),
    ("Chileno: Chile, Cuyo,neutral", "chile"), ("Cuban", "other"), ("México,Chileno: Chile, Cuyo", None), ("", None),
])
def test_spanish_accent_groups_come_from_the_cv_es_answers(answer, group):
    assert pool["accent_group"](answer, "common_voice_es") == group

import random
import runpy
from pathlib import Path

import numpy as np
import pytest

yaml = pytest.importorskip("yaml")
pytest.importorskip("soundfile")
pytest.importorskip("scipy")
SCRIPTS = Path(__file__).resolve().parents[1] / "scripts" / "ts_benchmark"
build = runpy.run_path(str(SCRIPTS / "build.py"))
mixer = build["mixer"]
SR = mixer.SAMPLE_RATE


def pools():
    def speaker(name, count=12):
        return [mixer.Utt(f"{name}-{i}", name, f"文本{name}{i}", 3.0 + (i % 5), f"/x/{name}-{i}.wav")
                for i in range(count)]

    speakers = {f"s{i}": speaker(f"s{i}") for i in range(8)}
    short = {s: [mixer.Utt(f"{s}-short-{i}", s, f"好{i}", 0.8, "/x") for i in range(3)] for s in speakers}
    return {"mixed": {"speakers": speakers, "short": short}, "__rirs__": ["rir0"],
            "__noise__": {"musan_noise": ["n0"], "musan_music": ["m0"]}}


def plan(params, seed=0, **kwargs):
    """Like the builder: a scene the draw cannot satisfy is redrawn."""
    base = {"kind": "pos", "schedule": "full", "k": 2, "duration": [10, 16]}
    for attempt in range(40):
        try:
            return mixer.plan_scene(random.Random(f"{seed}:{attempt}"), {**base, **params}, pools(), **kwargs)
        except mixer.PlanError:
            continue
    raise AssertionError("no scene could be planned")


def test_recipe_expands_to_unique_scenarios():
    recipe = yaml.safe_load((SCRIPTS / "recipe.yaml").read_text())
    splits = build["expand_splits"](recipe)

    assert len({s["name"] for s in splits}) == len(splits)
    assert {s["group"] for s in splits} == {"enroll", "dynamics", "absent", "nonspeech", "domain"}
    assert sum(s["name"].startswith("enroll-") for s in splits) == 18
    assert all(s["params"]["kind"] in {"pos", "neg", "nonspeech"} for s in splits)


@pytest.mark.parametrize("seed", range(20))
def test_target_enters_and_leaves_where_the_schedule_says(seed):
    enter, leave = plan({"schedule": "enter"}, seed), plan({"schedule": "leave"}, seed)

    first = min(s for _, s in enter["tracks"][0].items)
    last = max(s + u.duration for u, s in leave["tracks"][0].items)
    assert first >= 0.5 * enter["total"] - 1e-6
    assert last <= 0.5 * leave["total"] + 1e-6


@pytest.mark.parametrize("schedule", ["full", "burst", "enter", "leave", "alternate", "overlap"])
def test_target_utterances_are_whole_and_inside_the_segment(schedule):
    for seed in range(15):
        scene = plan({"schedule": schedule, "k": 2}, seed)
        target = scene["tracks"][0]
        assert target.role == "target" and target.items
        for utt, start in target.items:
            assert start >= 0 and start + utt.duration <= scene["total"] + 1e-6
        # The enrollment never reuses an utterance that is part of the scene.
        used = {u.id for t in scene["tracks"] for u, _ in t.items}
        assert scene["enroll_utt"].id not in used


def test_absent_target_never_speaks_in_the_mixture():
    for seed in range(20):
        scene = plan({"kind": "neg", "k": 2}, seed)
        speakers = {t.speaker for t in scene["tracks"]}
        assert scene["target_speaker"] not in speakers
        assert all(t.role == "interferer" for t in scene["tracks"])


def test_hard_negatives_need_embeddings_and_pick_similar_speakers():
    with pytest.raises(ValueError, match="embeddings"):
        plan({"kind": "neg", "hard": True})
    similarity = lambda a, b: -abs(int(a[1:]) - int(b[1:]))
    scene = plan({"kind": "neg", "hard": True, "k": 1}, 3, similarity=similarity)
    anchor = scene["hard_anchor"]
    ranked = sorted((s for s in pools()["mixed"]["speakers"] if s != anchor), key=lambda s: -similarity(anchor, s))
    assert scene["target_speaker"] in ranked[:5]


def test_plans_are_reproducible_from_the_seed():
    assert plan({"schedule": "burst"}, 7)["tracks"][0].items == plan({"schedule": "burst"}, 7)["tracks"][0].items


def loaders():
    rng = np.random.default_rng(0)
    cache = {}

    def load(utt):
        if utt.id not in cache:
            cache[utt.id] = (rng.standard_normal(int(utt.duration * SR)) * 0.1).astype(np.float32)
        return cache[utt.id]

    noise = lambda kind, file: (np.random.default_rng(1).standard_normal(SR * 5) * 0.05).astype(np.float32)
    rir = lambda path: np.concatenate([[1.0], np.zeros(200), [0.3], np.zeros(800)]).astype(np.float32)
    return load, rir, noise


def test_mixture_is_peak_limited_and_has_the_planned_length():
    load, rir, noise = loaders()
    for params in ({}, {"rir": True}, {"noise": {"kind": "musan_noise", "snr_db": [5, 5]}}):
        scene = plan(params, 2)
        mix = mixer.render_mixture(scene, load, rir, noise)
        assert len(mix) == int(scene["total"] * SR)
        assert np.abs(mix).max() == pytest.approx(0.5, rel=1e-3)


def test_sir_follows_the_interferer_gain():
    scene = plan({"sir_db": [6, 6], "k": 1}, 4)
    _, interferer = scene["tracks"]
    assert interferer.gain_db == pytest.approx(-6, abs=2.0 + 1e-6)
    scene2 = plan({"sir_db": [-6, -6], "k": 1}, 4)
    assert scene2["tracks"][1].gain_db == pytest.approx(6, abs=2.0 + 1e-6)


@pytest.mark.parametrize("cond", ["short1", "lead_silence", "lp4k", "noise10", "reverb", "contam10", "contam0", "quiet"])
def test_degraded_enrollment_is_exactly_three_seconds(cond):
    load, rir, noise = loaders()
    scene = plan({"enroll": cond}, 5)
    w = mixer.render_enrollment(scene, load, rir, noise)
    assert len(w) == int(mixer.ENROLL_SECONDS * SR) and np.isfinite(w).all()


def test_clean_enrollment_is_the_whole_utterance():
    load, rir, noise = loaders()
    scene = plan({"enroll": "clean"}, 5)
    assert len(mixer.render_enrollment(scene, load, rir, noise)) == int(scene["enroll_utt"].duration * SR)


def test_short_enrollment_has_one_second_of_speech_and_silence_padding():
    load, rir, noise = loaders()
    w = mixer.render_enrollment(plan({"enroll": "short1"}, 5), load, rir, noise)
    assert np.abs(w[SR:]).max() == 0 and np.abs(w[:SR]).max() > 0


def test_nonspeech_has_no_speakers_and_is_quiet_when_asked():
    load, rir, noise = loaders()
    scene = plan({"kind": "nonspeech", "duration": [2, 3], "noise": {"kind": "musan_noise", "level_dbfs": [-50, -50]}}, 1)
    mix = mixer.render_mixture(scene, load, rir, noise)
    assert not scene["tracks"] and 20 * np.log10(mixer.rms(mix)) == pytest.approx(-50, abs=0.1)


def scene_items(scene):
    return [(t.speaker, [(u.id, s) for u, s in t.items], round(t.gain_db, 6)) for t in scene["tracks"]]


@pytest.mark.parametrize("kind", ["pos", "neg"])
def test_scenes_that_differ_only_in_the_enrollment_condition_share_the_mixture(kind):
    for seed in range(10):
        clean = plan({"kind": kind, "enroll": "clean"}, seed)
        for cond in ("short1", "noise10", "contam0", "reverb"):
            degraded = plan({"kind": kind, "enroll": cond}, seed)
            assert scene_items(clean) == scene_items(degraded)
            assert clean["enroll_utt"] == degraded["enroll_utt"] and clean["total"] == degraded["total"]


def test_background_and_room_do_not_change_who_speaks_when():
    for seed in range(10):
        dry = plan({}, seed)
        wet = plan({"noise": {"kind": "musan_music", "snr_db": [5, 5]}}, seed)
        assert scene_items(dry) == scene_items(wet) and "noise" in wet and "noise" not in dry


def test_hard_negatives_keep_the_interferers_of_the_random_negative():
    similarity = lambda a, b: -abs(int(a[1:]) - int(b[1:]))
    for seed in range(10):
        easy = plan({"kind": "neg", "k": 2}, seed)
        hard = plan({"kind": "neg", "k": 2, "hard": True}, seed, similarity=similarity)
        assert scene_items(easy) == scene_items(hard)


analyze = None


def _analyze():
    global analyze
    if analyze is None:
        pytest.importorskip("rapidfuzz")
        analyze = runpy.run_path(str(SCRIPTS / "analyze.py"))
    return analyze


def record(target, interferer_text, present=True, scenario="s", pair=None, index=0):
    labels = {"target_present": present, "scenario": scenario, "kind": "pos" if present else "neg"}
    if pair:
        labels["pair"] = pair
    return {"target": target, "labels": labels,
            "metadata": {"index": index, "interferers": [{"utts": [{"text": interferer_text}]}]}}


def test_scoring_separates_wrong_speaker_leak_and_loops():
    a = _analyze()
    wrong = a["score"](record("今天天气很好", "明天去北京玩"), "明天去北京玩")
    assert wrong["wrong_speaker"] is True and wrong["errors"] == 5
    leak = a["score"](record("", "明天去北京玩", present=False), "明天去北京")
    assert leak["leak"] is True and not leak["empty"]
    assert a["score"](record("你好", "他们"), "你" * 40)["looped"] is True
    assert a["score"](record("", "他们", present=False), "")["empty"] is True


def test_paired_deltas_compare_the_same_scenes():
    a = _analyze()
    records, scored = {}, {}
    for i in range(20):
        for name, hyp in (("enroll-clean-neg", ""), ("enroll-short1-neg", "有字" if i % 2 else "")):
            rid = f"{name}:{i}"
            records[rid] = record("", "他们", present=False, scenario=name, pair="enroll-neg", index=i)
            scored[rid] = a["score"](records[rid], hyp)
    delta = a["paired"](records, scored, random.Random(0))["enroll-short1-neg"]
    assert delta["metric"] == "dFA" and delta["delta"] == pytest.approx(0.5)

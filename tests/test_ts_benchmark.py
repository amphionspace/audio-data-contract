import itertools
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
    return {"mixed": {"speakers": speakers, "short": short}, "__rirs__": ["rir0", "rir1"],
            "__rir_pools__": {"real": ["rir0"], "sim": ["rir1"]},
            "__noise__": {"musan_noise": ["n0"], "musan_music": ["m0"], "wham": ["w0"], "wham_stationary": ["w0"]}}


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
    assert {s["group"] for s in splits} == {"enroll", "dynamics", "absent", "nonspeech", "domain", "realreg", "panel", "stress"}
    assert sum(s["name"].startswith("enroll-") for s in splits) == 24  # 12 conditions incl. len2/3/4 (v4)
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


@pytest.mark.parametrize("kind", ["pos", "neg"])
def test_long_enrollment_chains_other_utterances_of_the_enrolled_speaker(kind):
    load, rir, noise = loaders()
    scene = plan({"kind": kind, "enroll": "long", "enroll_long_seconds": 20}, 3)
    used = {u.id for t in scene["tracks"] for u, _ in t.items}
    speaker = scene["enroll_utt"].speaker
    assert all(u.speaker == speaker and u.id not in used for u, _ in scene["enroll_extra"])
    w = mixer.render_enrollment(scene, load, rir, noise)
    assert len(w) == 20 * SR and np.abs(w[:SR]).max() > 0


STORE = {"enroll_store_seconds": 10}


@pytest.mark.parametrize("cond", ["clean", "short1", "lead_silence", "lp4k", "noise10", "reverb", "contam10", "quiet"])
@pytest.mark.parametrize("kind", ["pos", "neg"])
def test_stored_enrollment_keeps_the_scene_and_the_first_utterance(cond, kind):
    for seed in range(5):
        plain, stored = plan({"kind": kind, "enroll": cond}, seed), plan({"kind": kind, "enroll": cond, **STORE}, seed)
        assert scene_items(plain) == scene_items(stored)
        assert plain["enroll_utt"] == stored["enroll_utt"]
        assert plain.get("enroll_other") == stored.get("enroll_other")
        used = {u.id for t in stored["tracks"] for u, _ in t.items} | {stored["enroll_utt"].id}
        speaker = stored["enroll_utt"].speaker
        assert all(u.speaker == speaker and u.id not in used for u, _ in stored["enroll_extra"])


@pytest.mark.parametrize("cond", ["clean", "short1", "lead_silence", "lp4k", "noise10", "reverb", "contam10", "contam0", "quiet"])
def test_stored_enrollment_has_the_stored_length(cond):
    load, rir, noise = loaders()
    w = mixer.render_enrollment(plan({"enroll": cond, **STORE}, 5), load, rir, noise)
    assert len(w) == 10 * SR and np.isfinite(w).all()


@pytest.mark.parametrize("cond, seconds", [("len2", 2), ("len3", 3), ("len4", 4)])
def test_short_registration_is_only_that_long_and_starts_like_the_stored_one(cond, seconds):
    load, rir, noise = loaders()
    short = mixer.render_enrollment(plan({"enroll": cond, **STORE}, 5), load, rir, noise)
    full = mixer.render_enrollment(plan({"enroll": "clean", **STORE}, 5), load, rir, noise)
    assert len(short) == seconds * SR
    np.testing.assert_array_equal(short, full[: seconds * SR])


def test_stored_short1_has_one_second_of_speech_in_a_full_length_recording():
    load, rir, noise = loaders()
    w = mixer.render_enrollment(plan({"enroll": "short1", **STORE}, 5), load, rir, noise)
    assert len(w) == 10 * SR and np.abs(w[SR:]).max() == 0 and np.abs(w[:SR]).max() > 0


def test_a_speaker_short_of_speech_keeps_what_there_is():
    scene = plan({"enroll": "clean", "enroll_store_seconds": 1000}, 2)
    assert scene["enroll_extra"]  # no PlanError, so the scene was not redrawn
    assert scene_items(scene) == scene_items(plan({"enroll": "clean"}, 2))


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


def test_a_noise_floor_never_changes_the_scene_and_is_applied_to_both_waveforms():
    load, rir, noise = loaders()
    floor = {"dbfs": [-50, -50], "kinds": ["white"]}
    for seed in range(8):
        base = plan({}, seed)
        floored = plan({"noise_floor": floor}, seed)
        assert scene_items(base) == scene_items(floored) and "floor" not in base
        mix = mixer.render_mixture(floored, load, rir, noise)
        silent = floored["total"] > 0 and mixer.render_mixture(base, load, rir, noise)
        assert len(mix) == len(silent) and np.abs(mix - silent).mean() > 0
        assert 20 * np.log10(mixer.rms(mix - silent)) == pytest.approx(-50, abs=0.2)
        enrollment = mixer.render_enrollment(floored, load, rir, noise)
        assert len(enrollment) == int(floored["enroll_utt"].duration * SR)


def test_pink_floor_is_dominated_by_low_frequencies():
    spec = {"kind": "pink", "dbfs": -40.0, "seed": 1}
    noise = mixer.floor_noise(SR * 4, spec)
    spectrum = np.abs(np.fft.rfft(noise)) ** 2
    assert spectrum[: len(spectrum) // 8].sum() > spectrum[len(spectrum) // 2:].sum()
    assert 20 * np.log10(mixer.rms(noise)) == pytest.approx(-40.0, abs=0.01)


def test_recorded_registration_is_the_enrollment_of_an_absent_target():
    _, rir, noise = loaders()
    base = {"kind": "neg", "k": 2, "enroll_file": "realreg1"}
    pool = pools()
    pool["__enroll_files__"] = {"realreg1": "/x/reg.wav"}
    scene = mixer.plan_scene(random.Random(3), {"duration": [10, 12], **base}, pool)
    assert scene["enroll_file"]["id"] == "realreg1" and scene["params"]["enroll"] == "file"
    assert scene["enroll_utt"].text == "" and all(t.role == "interferer" for t in scene["tracks"])
    recorded = (np.random.default_rng(5).standard_normal(SR * 2) * 0.1).astype(np.float32)
    w = mixer.render_enrollment(scene, lambda utt: recorded, rir, noise)
    assert len(w) == 3 * SR and np.array_equal(w[: 2 * SR], recorded) and not w[2 * SR:].any()
    music = mixer.plan_scene(random.Random(3), {"kind": "nonspeech", "duration": [2, 3], "enroll_file": "realreg1",
                                                "noise": {"kind": "musan_noise", "level_dbfs": [-30, -30]}}, pool)
    assert music["enroll_file"]["id"] == "realreg1"


def test_runs_are_compared_on_the_same_samples():
    a = _analyze()
    records, base, cand = {}, {}, {}
    for i in range(20):
        rid = f"s:{i}"
        records[rid] = record("", "他们", present=False, scenario="s", index=i)
        base[rid] = a["score"](records[rid], "")
        cand[rid] = a["score"](records[rid], "有字" if i < 5 else "")
    change = a["compare"](records, cand, base, random.Random(0))["s"]
    assert change["metric"] == "dFA" and change["delta"] == pytest.approx(0.25) and change["n"] == 20


def test_a_real_noise_floor_uses_a_steady_clip_at_the_requested_level():
    spec = {"dbfs": [-45, -45], "kinds": ["wham"]}
    scene = plan({"noise_floor": spec}, 2)
    floor = scene["floor"]["mix"]
    assert floor["pool"] == "wham" and floor["file"] == "w0" and floor["dbfs"] == -45
    clip = (np.random.default_rng(3).standard_normal(SR * 2) * 0.3).astype(np.float32)
    noise = mixer.floor_noise(SR * 5, floor, lambda pool, file: clip)
    assert len(noise) == SR * 5 and 20 * np.log10(mixer.rms(noise)) == pytest.approx(-45, abs=0.01)


def test_a_floor_kind_without_steady_clips_is_rejected():
    with pytest.raises(ValueError, match="steady"):
        plan({"noise_floor": {"dbfs": [-50, -50], "kinds": ["dns5_audioset"]}}, 1)


def test_floors_do_not_depend_on_the_room_or_the_background():
    spec = {"dbfs": [-65, -35], "kinds": {"white": 0.5, "pink": 0.5}}
    for seed in range(8):
        dry = plan({"noise_floor": spec}, seed)
        wet = plan({"noise_floor": spec, "rir": "real", "noise": {"kind": "musan_music", "snr_db": [5, 5]}}, seed)
        assert dry["floor"] == wet["floor"] and scene_items(dry) == scene_items(wet)


def test_rirs_come_from_the_named_pool():
    scene = plan({"rir": "real"}, 4)
    assert scene["rir_pool"] == "real" and {t.rir for t in scene["tracks"]} == {"rir0"}
    scene = plan({"rir": True}, 4)
    assert scene["rir_pool"] == "all" and {t.rir for t in scene["tracks"]} <= {"rir0", "rir1"}


def test_recording_chain_effects():
    t = np.arange(SR) / SR
    high, low = np.sin(2 * np.pi * 6000 * t).astype(np.float32), np.sin(2 * np.pi * 500 * t).astype(np.float32)
    assert mixer.rms(mixer.apply_effect(high, "lp3400")) < 0.05 * mixer.rms(high)
    assert mixer.rms(mixer.apply_effect(low, "lp3400")) > 0.9 * mixer.rms(low)
    loud = np.clip(low * 4, -4, 4)
    assert np.abs(mixer.apply_effect(loud, "clip")).max() == pytest.approx(0.9)
    coded = mixer.mulaw(low * 0.5)
    assert coded.shape == low.shape and 0 < np.abs(coded - low * 0.5).max() < 0.05
    assert mixer.apply_effect(low, None) is low


def test_mixture_gain_sets_the_speech_level_before_the_floor():
    load, rir, noise = loaders()
    base = plan({}, 3)
    quiet = plan({"mix_gain_db": -20}, 3)
    a, b = mixer.render_mixture(base, load, rir, noise), mixer.render_mixture(quiet, load, rir, noise)
    assert quiet["mix_gain_db"] == -20 and scene_items(base) == scene_items(quiet)
    assert 20 * np.log10(mixer.rms(b) / mixer.rms(a)) == pytest.approx(-20, abs=0.01)


def test_two_samples_may_not_share_an_audio_index_entry(tmp_path):
    entry = {"cut_id": "dup", "relative_path": "audio/x.wav", "num_frames": 1, "duration": 0.1, "sha256": "0"}
    results = [{"split": "a", "index": i, "target": "", "labels": {"target_present": False}, "metadata": {},
                "entries": [dict(entry), dict(entry, cut_id="dup")]} for i in range(2)]
    recipe = {"version": "v", "dataset_id": "ts_asr_benchmark", "pools": {}}
    split = {"name": "a", "group": "g", "params": {}, "n": 2}
    with pytest.raises(ValueError, match="duplicate cut ids"):
        build["register"](recipe, [split], results, tmp_path, "ts_asr_benchmark")


def room_pools():
    full = pools()
    full["__rir_pools__"] = {"real": [f"rir{i}" for i in range(10)]}
    return full


def plan_rooms(rir, seed, **params):
    base = {"kind": "pos", "schedule": "full", "k": 2, "duration": [10, 16], "rir": rir, **params}
    for attempt in range(40):
        try:
            return mixer.plan_scene(random.Random(f"{seed}:{attempt}"), base, room_pools())
        except mixer.PlanError:
            continue
    raise AssertionError("no scene could be planned")


@pytest.mark.parametrize("seed", range(10))
def test_role_rirs_change_only_the_rooms(seed):
    dry = plan_rooms(None, seed)
    target_only = plan_rooms({"target": "real"}, seed)
    diff = plan_rooms({"target": "real", "interferer": "real"}, seed)
    same = plan_rooms({"target": "real", "interferer": "real", "share": True}, seed)

    assert [t.rir for t in dry["tracks"]] == [None] * len(dry["tracks"])
    assert [t.rir is not None for t in target_only["tracks"]] == [t.role == "target" for t in target_only["tracks"]]
    assert len({t.rir for t in diff["tracks"]}) == len(diff["tracks"])
    assert len({t.rir for t in same["tracks"]}) == 1
    assert diff["rir_roles"] == {"target": "real", "interferer": "real", "share": False}
    for scene in (target_only, diff, same):  # the same speakers and placements as the dry scene
        assert [(t.role, t.speaker, [(u.id, s) for u, s in t.items]) for t in scene["tracks"]] == [
            (t.role, t.speaker, [(u.id, s) for u, s in t.items]) for t in dry["tracks"]]


def test_far_field_recipe_expands_to_unique_scenarios():
    recipe = yaml.safe_load((SCRIPTS / "recipe-farfield.yaml").read_text())
    splits = build["expand_splits"](recipe)

    assert len({s["name"] for s in splits}) == len(splits) == 14
    assert {s["params"].get("pair") for s in splits} == {"panel-pos", "panel-neg"}


def test_enrollment_length_recipe_keeps_twenty_seconds_and_short_mixtures():
    recipe = yaml.safe_load((SCRIPTS / "recipe-enroll-len.yaml").read_text())
    splits = build["expand_splits"](recipe)
    assert len({s["name"] for s in splits}) == len(splits) == 4
    for s in splits:
        assert s["params"]["enroll"] == "long" and s["params"]["enroll_long_seconds"] == 20
        assert s["params"]["enroll_long_seconds"] + s["params"]["duration"][1] <= 30


def test_handover_recipe_expands_to_unique_scenarios():
    recipe = yaml.safe_load((SCRIPTS / "recipe-handover.yaml").read_text())
    splits = build["expand_splits"](recipe)

    assert len({s["name"] for s in splits}) == len(splits) == 10
    assert {s["params"]["handover"] for s in splits if s["name"].startswith("handover-")} == set(mixer.HANDOVER_VARIANTS)
    assert {s["params"].get("pair") for s in splits if s["name"].startswith("handover-")} == {"handover"}


def handover_pools():
    openings = ["现在我开始说话", "我现在是在旁边", "大家一起来唱歌", "今天天气很好啊"]
    speakers = {f"s{i}": [mixer.Utt(f"s{i}-{j}", f"s{i}", f"{openings[j % 4]}{i}{j}", 2.0 + 0.2 * j, f"/x/s{i}-{j}.wav")
                          for j in range(12)] for i in range(4)}
    return {"mixed": {"speakers": speakers, "short": {}}, "__noise__": {}}


def handover(variant, seed):
    for attempt in range(40):
        try:
            return mixer.plan_scene(random.Random(f"{seed}:{attempt}"),
                                    {"kind": "pos", "schedule": "handover", "handover": variant}, handover_pools())
        except mixer.PlanError:
            continue
    raise AssertionError("no handover could be planned")


@pytest.mark.parametrize("seed", range(10))
def test_handover_variants_share_the_target_sentence_and_the_timing(seed):
    same, rand, rev = (handover(v, seed) for v in mixer.HANDOVER_VARIANTS)
    spans = {}
    for name, scene in (("same", same), ("rand", rand), ("rev", rev)):
        (target,), (other,) = (t.items for t in scene["tracks"])
        assert scene["tracks"][0].role == "target" and scene["target_overlap_ratio"] == 0.0
        first, second = sorted([target, other], key=lambda item: item[1])
        assert first[1] + first[0].duration < second[1] and second[1] + second[0].duration < scene["total"]
        spans[name] = (target, other, first, second)
    (t_same, o_same, f_same, s_same), (t_rand, o_rand, _, _), (t_rev, o_rev, f_rev, s_rev) = (
        spans["same"], spans["rand"], spans["rev"])
    assert t_same == t_rand and t_same[0] == t_rev[0] and o_rev == (o_same[0], f_same[1])
    assert o_rand[0].speaker == o_same[0].speaker and o_rand[1] == o_same[1]
    assert f_rev == (o_same[0], f_same[1])
    assert s_rev[1] - (f_rev[1] + f_rev[0].duration) == pytest.approx(s_same[1] - (f_same[1] + f_same[0].duration))
    assert mixer.same_opening(t_same[0].text, o_same[0].text) and mixer.shares_no_opening(t_same[0].text, o_rand[0].text)
    assert same["enroll_utt"] == rand["enroll_utt"] == rev["enroll_utt"] != t_same[0]
    assert same["enroll_utt"].speaker == t_same[0].speaker


def test_handover_openings():
    assert mixer.same_opening("现在我开始说话，可以吗？", "我现在是在旁边干扰的人。")
    assert mixer.same_opening("我们走吧", "我们明天见") and not mixer.same_opening("我们走吧", "明天你们走")
    assert mixer.shares_no_opening("现在我开始说话", "大家一起来唱歌")
    assert not mixer.shares_no_opening("现在我开始说话", "今天我们")


def test_hard_negatives_of_a_recorded_registration_are_its_nearest_speakers():
    pool = pools()
    speakers = {f"s{i}": pool["mixed"]["speakers"]["s0"] for i in range(14)}
    pool["mixed"] = {"speakers": speakers, "short": {}}
    pool["__enroll_files__"] = {"realreg3": "/x/reg.wav"}
    base = {"kind": "neg", "k": [1, 2], "duration": [6, 18], "enroll_file": "realreg3"}
    with pytest.raises(ValueError, match="embeddings"):
        mixer.plan_scene(random.Random(0), {**base, "hard": True}, pool)
    similarity = lambda a, b: int(b[1:]) / 20 if a == "file:realreg3" else 0.0
    nearest = {f"s{i}" for i in range(4, 14)}
    for seed in range(10):
        easy = mixer.plan_scene(random.Random(seed), base, pool, similarity)
        hard = mixer.plan_scene(random.Random(seed), {**base, "hard": True}, pool, similarity)
        chosen = [t.speaker for t in hard["tracks"]]
        assert set(chosen) <= nearest and hard["total"] == easy["total"] and len(chosen) == len(easy["tracks"])
        assert hard["hard_cosine"] == max(similarity("file:realreg3", s) for s in chosen)
        assert hard["target_speaker"] == "file:realreg3" and hard["enroll_file"]["id"] == "realreg3"


def test_dialogue_interferers_take_turns_without_the_target():
    for seed in range(10):
        scene = plan({"kind": "neg", "k": 3, "interferer_schedule": "dialogue"}, seed)
        turns = sorted((s, s + u.duration, t.speaker) for t in scene["tracks"] for u, s in t.items)
        assert all(t.role == "interferer" for t in scene["tracks"]) and len(turns) >= 2
        # One speaker at a time, the next turn by someone else (at most 0.2 s of overlap).
        assert all(b[0] >= a[1] - 0.2 - 1e-6 and b[2] != a[2] for a, b in itertools.pairwise(turns))
        assert turns[-1][1] <= scene["total"] + 1e-6


def test_a_long_recorded_registration_keeps_the_stored_length():
    _, rir, noise = loaders()
    pool = pools()
    pool["__enroll_files__"] = {"realreg5": "/x/reg.wav"}
    scene = mixer.plan_scene(random.Random(3), {"kind": "neg", "k": 2, "duration": [10, 12], "enroll_file": "realreg5",
                                                "enroll_store_seconds": 10}, pool)
    for seconds, stored in ((8.3, 8.3), (12.0, 10.0), (3.0, 3.0)):
        recorded = (np.random.default_rng(5).standard_normal(int(SR * seconds)) * 0.1).astype(np.float32)
        w = mixer.render_enrollment(scene, lambda utt, recorded=recorded: recorded, rir, noise)
        assert len(w) == int(SR * stored) and np.array_equal(w, recorded[: len(w)])

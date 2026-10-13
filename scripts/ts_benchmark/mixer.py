"""Scene planning and rendering for the target-speaker ASR benchmark.

Planning only needs utterance durations and speaker identities, so it is cheap and
deterministic. Rendering loads audio, applies room, noise and enrollment
degradations, and returns the waveforms. Both steps take explicit random
generators, so a scene is reproducible from its seed.

Conventions
-----------
* Every utterance is RMS-normalized to ``UTT_DBFS`` before any gain, so the
  signal-to-interference ratio (SIR) of a scene is set by the gains alone.
* ``sir_db`` is target level minus interferer level; a negative value means the
  interferer is louder than the target.
* The target speaker only ever speaks whole utterances, so the reference is the
  concatenation of the placed target utterances in time order.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

import numpy as np

SAMPLE_RATE = 16000
UTT_DBFS = -25.0
ENROLL_SECONDS = 3.0
MAX_MIXTURE_SECONDS = 27.0
FADE_SECONDS = 0.03
# Interferer pauses between utterances: dense (near-continuous), medium and sparse talk, so the
# overlap with the target varies within a scenario; the realized overlap is recorded per sample.
GAP_PROFILES = [(0.2, 1.0), (0.2, 1.0), (1.0, 3.0), (2.5, 6.0)]
CONTINUOUS_SCHEDULES = ("burst", "enter", "leave", "short")


@dataclass(frozen=True)
class Utt:
    id: str
    speaker: str
    text: str
    duration: float
    path: str
    corpus: str = ""
    gender: str | None = None


@dataclass
class Track:
    role: str  # "target" or "interferer"
    speaker: str
    items: list = field(default_factory=list)  # [(Utt, start_seconds)]
    gain_db: float = 0.0
    rir: str | None = None


def rms(x):
    return float(np.sqrt(np.mean(np.square(x, dtype=np.float64)) + 1e-12))


def db(value):
    return 20.0 * math.log10(max(value, 1e-9))


def normalize_rms(x, dbfs=UTT_DBFS):
    return (x * (10.0 ** (dbfs / 20.0) / rms(x))).astype(np.float32)


def trim_leading_silence(w, sr=SAMPLE_RATE, threshold_db=-35.0, frame=0.02):
    """Drop leading frames more than ``threshold_db`` below the loudest frame."""
    step = int(sr * frame)
    n = len(w) // step
    if n == 0:
        return w
    levels = np.array([db(rms(w[i * step:(i + 1) * step])) for i in range(n)])
    voiced = np.nonzero(levels > levels.max() + threshold_db)[0]
    return w[voiced[0] * step:] if len(voiced) else w


# --- planning -------------------------------------------------------------


def _uniform(rng, bounds):
    return rng.uniform(bounds[0], bounds[1])


def fill_stream(rng, speaker_utts, total, gap, start_range=(0.0, 1.5)):
    """Back-to-back utterances of one speaker with random gaps until ``total``.

    The last utterance may run past ``total``; rendering truncates it.
    """
    items, now = [], _uniform(rng, start_range)
    used = set()
    while now < total:
        choices = [u for u in speaker_utts if u.id not in used] or speaker_utts
        utt = rng.choice(choices)
        used.add(utt.id)
        items.append((utt, now))
        now += utt.duration + _uniform(rng, gap)
    return items


def _place_target(rng, schedule, utts, total, others, gap=(0.2, 1.0)):
    """Target utterance placements for a schedule; always whole utterances."""

    def sequential(first, limit, gap, count):
        placed, now = [], first
        for utt in rng.sample(utts, min(count, len(utts))):
            if now + utt.duration > limit:
                break
            placed.append((utt, now))
            now += utt.duration + _uniform(rng, gap)
        return placed

    utts = [u for u in utts if u.duration <= total * 0.6]
    if not utts:
        raise PlanError("no target utterance fits the segment")
    if schedule == "full":
        return sequential(_uniform(rng, (0.0, 1.0)), total, gap, 12)
    if schedule == "burst":  # others talk throughout, target cuts in once or twice
        count = rng.choice([1, 1, 2])
        return sequential(_uniform(rng, (0.3 * total, 0.5 * total)), 0.85 * total, (0.4, 1.2), count)
    if schedule == "enter":  # target joins in the second half
        return sequential(_uniform(rng, (0.5 * total, 0.62 * total)), total, (0.2, 0.8), 3)
    if schedule == "leave":  # target speaks at the start, then stops
        return sequential(_uniform(rng, (0.0, 0.8)), 0.5 * total, (0.2, 0.8), 3)
    if schedule == "short":  # one very short utterance somewhere in the segment
        utt = rng.choice(utts)
        return [(utt, _uniform(rng, (0.2 * total, max(0.2 * total, total - utt.duration - 0.2))))]
    if schedule == "overlap":  # starts together with an interferer utterance
        anchors = [(u, s) for track in others for u, s in track.items
                   if u.duration >= 1.5 and s + u.duration < total]
        if not anchors:
            return []
        anchor, start = rng.choice(anchors)
        fit = [u for u in utts if u.duration <= anchor.duration] or utts
        utt = rng.choice(fit)
        return [(utt, min(start + _uniform(rng, (0.0, 0.4)), total - utt.duration - 0.05))]
    raise ValueError(f"unknown schedule: {schedule}")


def _alternate(rng, target_utts, interferer_utts, total):
    """Dialog-like turns, mostly non-overlapping; returns target track and others."""
    speakers = ["target", *interferer_utts]
    turns, now, last = [], _uniform(rng, (0.0, 0.5)), None
    while now < total - 1.0:
        order = [s for s in speakers if s != last]
        who = rng.choice(order)
        pool = target_utts if who == "target" else interferer_utts[who]
        utt = rng.choice([u for u in pool if now + u.duration <= total] or pool)
        if now + utt.duration > total:
            break
        turns.append((who, utt, now))
        now += utt.duration + _uniform(rng, (-0.2, 0.7))
        last = who
    target = [(u, s) for who, u, s in turns if who == "target"]
    others = {who: [] for who in interferer_utts}
    for who, u, s in turns:
        if who != "target":
            others[who].append((u, s))
    return target, others


def overlap_ratio(target_items, other_tracks):
    """Fraction of target-utterance time during which any interferer utterance is active."""
    covered = total = 0.0
    spans = sorted((s, s + u.duration) for t in other_tracks for u, s in t.items)
    merged = []
    for a, b in spans:
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    for utt, start in target_items:
        end = start + utt.duration
        total += utt.duration
        covered += sum(max(0.0, min(end, b) - max(start, a)) for a, b in merged)
    return covered / total if total else 0.0


def plan_scene(rng, params, pools, similarity=None):
    """Choose speakers, utterances, timings and degradations for one sample.

    ``pools`` maps a pool name to ``{"speakers": {speaker: [Utt]}, "short": {speaker: [Utt]}}``.
    ``similarity(a, b)`` is the speaker-embedding cosine, only used for hard negatives.

    Three independent random streams keep paired scenarios comparable: the scene (speakers,
    timings, gains) never depends on the enrollment condition or on the background, so two splits
    that differ only in those share the same scene when they share a seed.
    """
    kind = params["kind"]
    scene = random.Random(rng.getrandbits(64))
    enroll = random.Random(rng.getrandbits(64))
    background = random.Random(rng.getrandbits(64))
    floors = random.Random(rng.getrandbits(64))  # its own stream: floors do not depend on rooms or noise
    plan = {"kind": kind, "params": params, "tracks": []}
    plan["total"] = round(_uniform(scene, params["duration"]), 3)
    total = plan["total"]
    target_pool = pools[params.get("target_pool", "mixed")]
    interferer_pool = pools[params.get("interferer_pool", params.get("target_pool", "mixed"))]
    if kind == "nonspeech":
        enroll_speaker = enroll.choice(sorted(target_pool["speakers"]))
        plan["enroll_speaker"] = enroll_speaker
        plan["enroll_utt"] = _enroll_utt(enroll, target_pool["speakers"][enroll_speaker], [])
        _plan_recorded_enrollment(params, pools, plan)
        plan["noise"] = {**plan_noise(background, params["noise"]["kind"], pools),
                         "level_dbfs": round(_uniform(background, params["noise"].get("level_dbfs", (-35.0, -20.0))), 2)}
        _plan_enrollment(enroll, params, pools, target_pool, plan, enroll_speaker)
        _plan_floors(floors, params, plan, pools)
        return plan

    k = params["k"]
    k = scene.choice(k) if isinstance(k, list) else k
    speaker_utts = target_pool["short"] if params.get("schedule") == "short" else target_pool["speakers"]
    target = scene.choice(sorted(speaker_utts)) if kind == "pos" else None
    taken = {target} if target else set()
    candidates = [s for s in sorted(interferer_pool["speakers"]) if s not in taken]
    interferers = scene.sample(candidates, k)
    if kind == "neg":  # the enrollment speaker is absent from the mixture
        if params.get("hard"):
            if similarity is None:
                raise ValueError("hard negatives need speaker embeddings")
            anchor = enroll.choice(interferers)
            ranked = sorted((s for s in sorted(target_pool["speakers"])
                             if s != anchor and s not in interferers),
                            key=lambda s: -similarity(anchor, s))
            target = ranked[enroll.randrange(min(5, len(ranked)))]
            plan["hard_anchor"] = anchor
            plan["hard_cosine"] = round(float(similarity(anchor, target)), 4)
        elif not params.get("enroll_file"):
            target = enroll.choice([s for s in sorted(target_pool["speakers"]) if s not in interferers])
    plan["target_speaker"] = target
    if kind == "neg":
        _plan_recorded_enrollment(params, pools, plan)

    interferer_tracks = []
    gap = params.get("interferer_gap")
    if gap is None:
        gap = (0.0, 0.5) if params.get("schedule") in CONTINUOUS_SCHEDULES else scene.choice(GAP_PROFILES)
    plan["interferer_gap"] = list(gap)
    sir = params.get("sir_db", (-3.0, 3.0))
    for speaker in interferers:
        interferer_tracks.append(Track(
            "interferer", speaker,
            fill_stream(scene, interferer_pool["speakers"][speaker], total, gap,
                        params.get("interferer_start", (0.0, 1.5))),
            gain_db=-_uniform(scene, sir) + scene.uniform(-2.0, 2.0)))
    target_track = Track("target", target, [], 0.0)
    if kind == "pos":
        schedule = params.get("schedule", "full")
        if schedule == "alternate":
            target_items, others = _alternate(
                scene, speaker_utts[target],
                {t.speaker: interferer_pool["speakers"][t.speaker] for t in interferer_tracks}, total)
            for track in interferer_tracks:
                track.items = others[track.speaker]
        else:
            target_gap = params.get("target_gap") or scene.choice(GAP_PROFILES)
            plan["target_gap"] = list(target_gap)
            target_items = _place_target(scene, schedule, speaker_utts[target], total, interferer_tracks, target_gap)
        if not target_items or any(
                start < 0 or start + utt.duration > total + 1e-6 for utt, start in target_items):
            raise PlanError("no target placement")
        target_track.items = target_items
        plan["target_overlap_ratio"] = round(overlap_ratio(target_items, interferer_tracks), 3)
        plan["tracks"].append(target_track)
    plan["tracks"].extend(interferer_tracks)

    if "enroll_file" not in plan:
        used = {u.id for t in plan["tracks"] for u, _ in t.items}
        plan["enroll_utt"] = _enroll_utt(enroll, target_pool["speakers"][target], used)
        _plan_enrollment(enroll, params, pools, target_pool, plan, target)
    if params.get("rir"):
        pool = pools.get("__rir_pools__", {}).get(params["rir"]) if isinstance(params["rir"], str) else None
        plan["rir_pool"] = params["rir"] if pool else "all"
        for track in plan["tracks"]:
            track.rir = background.choice(pool or pools["__rirs__"])
    if params.get("noise"):
        plan["noise"] = {**plan_noise(background, params["noise"]["kind"], pools),
                         "snr_db": round(_uniform(background, params["noise"]["snr_db"]), 2)}
    _plan_floors(floors, params, plan, pools)
    return plan


def _plan_recorded_enrollment(params, pools, plan):
    """A real registration recording as the enrollment of an absent target (``enroll_file``)."""
    name = params.get("enroll_file")
    if name:
        path = pools["__enroll_files__"][name]
        plan["enroll_file"] = {"id": name, "path": path}
        plan["enroll_utt"] = Utt(f"file:{name}", f"file:{name}", "", ENROLL_SECONDS, path)
        plan["target_speaker"] = f"file:{name}"
        plan["params"] = {**params, "enroll": "file"}


def _plan_floors(rng, params, plan, pools):
    """Drawn last from the background stream, so a floor never changes an existing scene."""
    spec = params.get("noise_floor")
    if spec:
        plan["floor"] = {"mix": plan_floor(rng, spec, pools), "enroll": plan_floor(rng, spec, pools)}
    gain = params.get("mix_gain_db")
    if gain is not None:
        plan["mix_gain_db"] = round(_uniform(rng, gain if isinstance(gain, list) else [gain, gain]), 2)


def _plan_enrollment(rng, params, pools, target_pool, plan, speaker):
    """Resources the enrollment condition needs, drawn at plan time so rendering is deterministic."""
    cond = params.get("enroll", "clean")
    if cond == "reverb":
        plan["enroll_rir"] = rng.choice(pools["__rirs__"])
    elif cond == "noise10":
        plan["enroll_noise"] = plan_noise(rng, "musan_noise", pools)
    elif cond in ("contam10", "contam0"):
        others = [s for s in sorted(target_pool["speakers"]) if s != speaker]
        voiced = [u for u in target_pool["speakers"][rng.choice(others)] if u.duration >= ENROLL_SECONDS]
        plan["enroll_other"] = rng.choice(voiced)


class PlanError(ValueError):
    """The drawn speakers could not satisfy the scene; the caller redraws."""


def _enroll_utt(rng, utts, used):
    longer = [u for u in utts if u.duration >= ENROLL_SECONDS + 0.5 and u.id not in used]
    if not longer:
        raise PlanError("no enrollment utterance")
    return rng.choice(longer)


# --- rendering ------------------------------------------------------------


def apply_rir(w, rir, tail=0.4):
    """Convolve with a room response and keep the dry level; the tail is kept."""
    from scipy.signal import fftconvolve

    ir = rir / (np.abs(rir).max() + 1e-9)
    out = fftconvolve(w, ir)[: len(w) + int(tail * SAMPLE_RATE)]
    return (out * (rms(w) / rms(out))).astype(np.float32)


def _fit(noise, n, offset):
    """``n`` samples of ``noise`` starting at fraction ``offset`` of the slack; loops short files."""
    if len(noise) < n:
        noise = np.tile(noise, n // len(noise) + 1)
    return noise[int(offset * (len(noise) - n)):][:n]


def add_noise(signal, noise, snr_db, offset):
    segment = _fit(noise, len(signal), offset)
    scale = rms(signal) / rms(segment) * 10.0 ** (-snr_db / 20.0)
    return signal + segment * scale


def plan_floor(rng, spec, pools):
    """Noise floor for one waveform: real recordings always have one, digital silence does not.

    ``spec['kinds']`` maps a kind to a weight (a list means equal weights). ``white`` and ``pink``
    are synthetic; ``real`` draws one of ``spec['real_pools']``; any other name is a prepared noise
    pool (``wham``, ``dns5_audioset``, ...). Only steady clips are used as a floor.
    """
    kinds = spec.get("kinds", ["white", "pink"])
    kinds = {k: 1.0 for k in kinds} if isinstance(kinds, list) else dict(kinds)
    kind = rng.choices(sorted(kinds), weights=[kinds[k] for k in sorted(kinds)])[0]
    out = {"kind": kind, "dbfs": round(_uniform(rng, spec["dbfs"]), 2), "seed": rng.getrandbits(32)}
    if kind in ("white", "pink"):
        return out
    names = spec.get("real_pools", []) if kind == "real" else [kind]
    available = [n for n in names if pools["__noise__"].get(n + "_stationary")]
    if not available:
        raise ValueError(f"no steady noise clips for floor kind {kind!r}")
    pool = rng.choice(available)
    out.update(pool=pool, file=rng.choice(pools["__noise__"][pool + "_stationary"]), offset=round(rng.random(), 4))
    return out


def floor_noise(n, spec, load_noise=None):
    """``n`` samples of floor noise at ``spec['dbfs']`` RMS."""
    if "file" in spec:
        return normalize_rms(_fit(load_noise(spec["pool"], spec["file"]), n, spec["offset"]).astype(np.float32),
                             spec["dbfs"])
    g = np.random.default_rng(spec["seed"])
    noise = g.standard_normal(n)
    if spec["kind"] == "pink":
        spectrum = np.fft.rfft(noise)
        spectrum[1:] /= np.sqrt(np.arange(1, len(spectrum)))
        noise = np.fft.irfft(spectrum, n)
    elif spec["kind"] != "white":
        raise ValueError(f"unknown floor kind: {spec['kind']}")
    return normalize_rms(noise.astype(np.float32), spec["dbfs"])


def apply_floor(w, spec, load_noise=None):
    return w if spec is None else (w + floor_noise(len(w), spec, load_noise)).astype(np.float32)


# --- recording-chain effects on the speech mixture (before the noise floor) ---


def mulaw(w, mu=255.0):
    """8-bit mu-law companding, as in telephony."""
    y = np.sign(w) * np.log1p(mu * np.abs(w)) / np.log1p(mu)
    q = np.round(y * 127) / 127
    return (np.sign(q) * ((1 + mu) ** np.abs(q) - 1) / mu).astype(np.float32)


def apply_effect(w, effect):
    if effect is None:
        return w
    if effect == "lp3400":
        from scipy.signal import butter, sosfilt

        return sosfilt(butter(8, 3400, "low", fs=SAMPLE_RATE, output="sos"), w).astype(np.float32)
    if effect == "mulaw":
        return mulaw(w)
    if effect == "clip":  # hard saturation of an over-driven microphone, set by the gain
        return np.clip(w, -0.9, 0.9).astype(np.float32)
    raise ValueError(f"unknown mixture effect: {effect}")


def plan_noise(rng, kind, pools):
    """Noise file and crop offset for one use; ``quiet`` is generated at render time."""
    files = pools["__noise__"].get(kind)
    return {"kind": kind, "file": rng.choice(files) if files else None, "offset": round(rng.random(), 4)}


def render_mixture(plan, load, load_rir, load_noise):
    """Mixture waveform (float32) for a planned scene."""
    total = int(plan["total"] * SAMPLE_RATE)
    floor = (plan.get("floor") or {}).get("mix")
    if plan["kind"] == "nonspeech":
        spec = plan["noise"]
        segment = _fit(load_noise(spec["kind"], spec["file"]), total, spec["offset"])
        return apply_floor(normalize_rms(segment.astype(np.float32), spec["level_dbfs"]), floor, load_noise)
    mix = np.zeros(total + int(0.4 * SAMPLE_RATE), dtype=np.float32)
    for track in plan["tracks"]:
        rir = load_rir(track.rir) if track.rir else None
        for utt, start in track.items:
            w = normalize_rms(load(utt))
            if rir is not None:
                w = apply_rir(w, rir)
            w = w * 10.0 ** (track.gain_db / 20.0)
            begin = int(start * SAMPLE_RATE)
            end = min(begin + len(w), total)
            if end <= begin:
                continue
            truncated = end - begin < len(w)
            w = w[: end - begin].copy()
            if truncated:
                fade = min(len(w), int(FADE_SECONDS * SAMPLE_RATE))
                w[-fade:] *= np.linspace(1.0, 0.0, fade, dtype=np.float32)
            mix[begin:end] += w
    mix = mix[:total]
    spec = plan.get("noise")
    if spec:
        mix = add_noise(mix, load_noise(spec["kind"], spec["file"]), spec["snr_db"], spec["offset"])
    peak = np.abs(mix).max()
    mix = (mix * (0.5 / peak)).astype(np.float32) if peak > 0 else mix
    mix = apply_effect(mix * 10.0 ** (plan.get("mix_gain_db", 0.0) / 20.0), plan["params"].get("mix_effect"))
    return apply_floor(mix, floor, load_noise)


def render_enrollment(plan, load, load_rir, load_noise):
    """(waveform, condition) for the planned enrollment utterance.

    The ``clean`` condition keeps the whole utterance, as a deployed client would
    send it; every degraded condition is exactly 3 s, the length the model consumes.
    """
    cond = plan["params"].get("enroll", "clean")
    floor = (plan.get("floor") or {}).get("enroll")
    utt = plan["enroll_utt"]
    n = int(ENROLL_SECONDS * SAMPLE_RATE)
    if cond == "file":  # a recorded registration is used as it is
        w = load(utt).astype(np.float32)
        return apply_floor(np.pad(w[:n], (0, max(0, n - len(w)))), floor, load_noise)
    w = normalize_rms(load(utt))
    if cond == "clean":
        return apply_floor(w, floor, load_noise)
    voiced = trim_leading_silence(w)
    if cond == "short1":
        seg = voiced[:SAMPLE_RATE]
    elif cond == "lead_silence":
        seg = np.concatenate([np.zeros(int(1.5 * SAMPLE_RATE), np.float32), voiced[: int(1.5 * SAMPLE_RATE)]])
    elif cond == "lp4k":
        from scipy.signal import butter, sosfilt

        seg = sosfilt(butter(8, 4000, "low", fs=SAMPLE_RATE, output="sos"), w[:n]).astype(np.float32)
    elif cond == "noise10":
        spec = plan["enroll_noise"]
        seg = add_noise(w[:n], load_noise(spec["kind"], spec["file"]), 10.0, spec["offset"])
    elif cond == "reverb":
        seg = apply_rir(w[:n], load_rir(plan["enroll_rir"]))
    elif cond in ("contam10", "contam0"):
        other = normalize_rms(load(plan["enroll_other"]))[:n]
        other = np.pad(other, (0, n - len(other)))
        sir = 10.0 if cond == "contam10" else 0.0
        seg = w[:n] + other * 10.0 ** (-sir / 20.0)
    elif cond == "quiet":
        seg = w[:n] * 10.0 ** (-25.0 / 20.0)
    else:
        raise ValueError(f"unknown enrollment condition: {cond}")
    seg = np.asarray(seg, dtype=np.float32)[:n]
    return apply_floor(np.pad(seg, (0, n - len(seg))), floor, load_noise)

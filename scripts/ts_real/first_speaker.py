#!/usr/bin/env python3
"""Who speaks first: real-meeting TS windows that open with a non-target speaker (ts_asr_nearfar firstother-v1).

Reproduces an internally returned TS-ASR badcase: a 45 s room recording with three people taking turns, the target
enrolled with a separately recorded voiceprint, and a non-target who speaks clearly in the first seconds. Every
model version transcribed the speaker who opened the recording. Moving that opening to the end, or enrolling with
the target's own speech from the session, fixed it, so two factors stack: a weak enrollment match (another
recording, another channel) and a mixture that opens with someone else.

Windows are cut as in ``build.py`` (whole utterances, AliMeeting Test far-field channel 0, human annotation), but
25-45 s long, with at least three speakers and at least 5 s of the target:

* ``firstother``: the first speaker of the window is not the target, and before the target's first utterance a
  non-target says a whole utterance of at least ``LEAD_SECONDS`` that others overlap for at most
  ``LEAD_MAX_OVERLAP`` of its length (the "lead");
* ``firsttarget``: the same rule with the target as the lead (the target opens the window), the control.

Both come from the same meetings with the same number of windows per (meeting, speaker count), so only who speaks
first differs. Each window gives a positive and a negative (an enrollment of someone not talking in the window), as
in ``build.py``. Enrollments follow ``ts_asr_real@v4`` (first utterance outside the window, more of the speaker up to
10 s stored, the client sends 5 s, ``-enrollmix`` when others talk >= 0.3 s in those 5 s) and pass the voice check
on the headsets (``voice_check.py``); the lead utterance must also sound like its labelled speaker, or the window is
quarantined. One window is stored under three enrollment conditions, the mixture always far-field channel 0:

* ``ef-mf``: enrollment from far-field channel 0 (same channel as the mixture);
* ``en-mf``: the same spans from the speaker's headset (cross-channel, like a separately recorded voiceprint);
* ``ed-mf``: ``en`` degraded like the badcase's voiceprint, which is noisier and duller than the session: a band
  limit (low-pass 3.5-5 kHz or a 6 dB high-shelf cut above 4 kHz), then steady WHAM! test noise at 15-25 dB SNR,
  drawn per record from a seeded stream and written to ``metadata.enroll_degradation``. The voice check stays on the
  clean enrollment; the verdict on the degraded copy is kept in ``metadata.enroll_degraded_voice_check``.

``first_speaker_windows`` and ``match_windows`` take the corpus split and thresholds as arguments, so the rule can
cut training windows too; this script only builds the evaluation version.

    python scripts/ts_real/first_speaker.py --roots /workspace/data/registry/roots.json \\
        --embed-python /workspace/workspace/mingdong/miniconda3/envs/k2/bin/python
"""

from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import random
import shutil
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import soundfile as sf
import yaml

from audio_data_contract import load_catalog
from audio_data_contract.catalog import validate_catalog
from audio_data_contract.types import DatasetSpec

HERE = Path(__file__).resolve().parent


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


real = _load("ts_real_build", "build.py")  # imports ts_benchmark/build.py itself as ``build``
near_far = _load("ts_real_near_far", "near_far.py")
voice = real._sibling("voice_check")
synth = real.synth
mixer = synth.mixer
REPO = HERE.parents[1]
SR = real.SR
DATASET_ID = "ts_asr_nearfar"
VERSION = "firstother-v1-20261104"
SEED = 20261104
CORPUS = {**real.RECIPE["corpora"]["alimeeting"], "label": "AliMeeting 远场会议"}

# Window rule (the badcase: 45 s, three speakers).
WINDOW_SPAN = (25.0, 40.0)  # drawn from an utterance start, then closed over whole utterances
WINDOW_RANGE = (25.0, 45.0)  # kept after the closure
MIN_SPEAKERS = 3
MIN_TARGET_SECONDS = 5.0
LEAD_SECONDS = 1.2  # whole utterance of the lead before the other party's first word
LEAD_MAX_OVERLAP = 0.2  # share of the lead utterance others may talk in (the enrollment rule)
KINDS = {"firstother": "other", "firsttarget": "target"}

# Enrollment degradation (badcase voiceprint vs. the target in the session: SNR about 21 vs 46 dB, energy above
# 4 kHz -23.3 vs -16.9 dB of the total, spectral centroid 458 vs 585 Hz).
NOISE_CACHE = Path("/workspace/data/datasets/ts_asr_benchmark/source/v4-20261022/noise")
NOISE_POOL = "wham"  # WHAM! tt (test) clips that prepare_noise.py marked steady
DEGRADE_SNR_DB = (15.0, 25.0)
LOWPASS_HZ = (3500.0, 5000.0)
SHELF_HZ, SHELF_DB, SHELF_WIDTH_HZ = 4000.0, -6.0, 1000.0  # gain ramps in dB over SHELF_HZ +- width / 2
PEAK_LIMIT = 0.99
CELLS = {"ef-mf": ("far", False), "en-mf": ("near", False), "ed-mf": ("near", True)}


# --- windows -----------------------------------------------------------------


def others_overlap(entry, utt):
    return sum(max(0.0, min(utt[1], o[1]) - max(utt[0], o[0])) for o in real.overlapping(entry, utt[0], utt[1])
               if o[2] != utt[2])


def lead_utterance(entry, utts, speakers, until, seconds=LEAD_SECONDS, max_overlap=LEAD_MAX_OVERLAP):
    """The first whole utterance of one of ``speakers`` that ends by ``until``, lasts ``seconds`` and is overlapped
    by others for at most ``max_overlap`` of its length; None if there is none."""
    return next((u for u in utts if u[2] in speakers and u[1] <= until and u[1] - u[0] >= seconds
                 and others_overlap(entry, u) <= max_overlap * (u[1] - u[0])), None)


def first_speaker_windows(entry, rng, span=WINDOW_SPAN, window_range=WINDOW_RANGE, min_speakers=MIN_SPEAKERS,
                          min_target_seconds=MIN_TARGET_SECONDS, lead_seconds=LEAD_SECONDS,
                          lead_max_overlap=LEAD_MAX_OVERLAP, enrollable=None):
    """Windows of whole utterances from every utterance start, with the targets that make them a ``firstother``
    and a ``firsttarget`` window. Windows overlap each other; ``match_windows`` picks disjoint ones.

    ``enrollable(speaker, lo, hi)`` says whether a speaker can be enrolled outside the window (default: an eligible
    utterance of ``build.eligible_enrollments``). Each window carries ``firstother``: {target: lead utterance} and
    ``firsttarget``: {lead speaker: their lead utterance} (empty when the rule does not hold).
    """
    enrollable = enrollable or (lambda s, lo, hi: bool(real.eligible_enrollments(entry, s, lo, hi)))
    out = []
    for start, *_ in entry["sups"]:
        lo, hi, inside = real.closure(entry, start, start + rng.uniform(*span))
        if not window_range[0] <= hi - lo <= window_range[1] or hi > entry.get("duration", float("inf")):
            continue
        utts = sorted(inside)
        present = real.speaker_seconds(utts)
        if len(present) < min_speakers:
            continue
        first = {}
        for u in utts:
            first.setdefault(u[2], u[0])
        opener = min(first, key=first.get)
        targets = [s for s, sec in sorted(present.items()) if sec >= min_target_seconds and enrollable(s, lo, hi)]
        firstother = {}
        for target in targets:
            lead = lead_utterance(entry, utts, set(present) - {target}, first[target], lead_seconds, lead_max_overlap)
            if target != opener and lead is not None:
                firstother[target] = lead
        firsttarget = {}
        if opener in targets:
            lead = lead_utterance(entry, utts, {opener}, min(v for s, v in first.items() if s != opener),
                                  lead_seconds, lead_max_overlap)
            if lead is not None:
                firsttarget[opener] = lead
        out.append({"lo": lo, "hi": hi, "utts": utts, "present": present, "speakers": len(present),
                    "opener": opener, "firstother": firstother, "firsttarget": firsttarget})
    return out


def match_windows(windows_by_recording, rng):
    """{kind: [window]}: per kind, disjoint windows per recording (random order); then per (recording, speaker
    count) the same number of windows of each kind, so the two kinds share meetings and speaker counts."""
    picked = {kind: defaultdict(list) for kind in KINDS}
    for recording, windows in sorted(windows_by_recording.items()):
        for kind in KINDS:
            pool = [w for w in windows if w[kind]]
            rng.shuffle(pool)
            taken = []
            for w in pool:
                if any(w["lo"] < b and w["hi"] > a for a, b in taken):
                    continue
                taken.append((w["lo"], w["hi"]))
                picked[kind][(recording, w["speakers"])].append({**w, "recording": recording})
    out = {kind: [] for kind in KINDS}
    for key in sorted(set(picked["firstother"]) & set(picked["firsttarget"])):
        n = min(len(picked[kind][key]) for kind in KINDS)
        for kind in KINDS:
            out[kind] += sorted(picked[kind][key], key=lambda w: w["lo"])[:n]
    return out


# --- enrollment conditions -----------------------------------------------------


def near_enrollment(recording, speaker, pieces, near_dir=near_far.NEAR_DIR):
    path = near_dir / f"{recording}_N_SPK{speaker}.wav"
    return np.concatenate([near_far.cut_near(path, s, e) for s, e in pieces])[: int(real.ENROLL_STORE * SR)]


def high_shelf(w, corner=SHELF_HZ, gain_db=SHELF_DB, width=SHELF_WIDTH_HZ):
    """Zero-phase shelf: 0 dB below ``corner - width/2``, ``gain_db`` above ``corner + width/2``, linear in dB between."""
    spectrum = np.fft.rfft(w)
    freqs = np.fft.rfftfreq(len(w), 1.0 / SR)
    ramp = np.clip((freqs - (corner - width / 2)) / width, 0.0, 1.0)
    return np.fft.irfft(spectrum * 10.0 ** (gain_db * ramp / 20.0), len(w)).astype(np.float32)


def plan_degradation(rng, noise_files):
    spec = {"order": "band_limit_then_noise", "snr_db": round(rng.uniform(*DEGRADE_SNR_DB), 2),
            "noise": {"pool": NOISE_POOL, "file": Path(rng.choice(noise_files)).name, "offset": round(rng.random(), 4)}}
    if rng.random() < 0.5:
        spec["band_limit"] = {"kind": "lowpass", "cutoff_hz": round(rng.uniform(*LOWPASS_HZ)), "order": 8}
    else:
        spec["band_limit"] = {"kind": "high_shelf", "corner_hz": SHELF_HZ, "gain_db": SHELF_DB, "width_hz": SHELF_WIDTH_HZ}
    return spec


def degrade(w, spec):
    from scipy.signal import butter, sosfilt

    band = spec["band_limit"]
    if band["kind"] == "lowpass":
        y = sosfilt(butter(band["order"], band["cutoff_hz"], "low", fs=SR, output="sos"), w).astype(np.float32)
    else:
        y = high_shelf(w, band["corner_hz"], band["gain_db"], band["width_hz"])
    noise, rate = sf.read(NOISE_CACHE / NOISE_POOL / spec["noise"]["file"], dtype="float32")
    assert rate == SR, (spec["noise"]["file"], rate)
    y = mixer.add_noise(y, noise, spec["snr_db"], spec["noise"]["offset"]).astype(np.float32)
    peak = float(np.abs(y).max())
    return y * (PEAK_LIMIT / peak) if peak > PEAK_LIMIT else y


def steady_noise_files():
    manifest = json.loads((NOISE_CACHE / "manifest.json").read_text())
    return sorted(str(NOISE_CACHE / e["path"]) for e in manifest if e["pool"] == NOISE_POOL and e.get("stationary"))


# --- build ---------------------------------------------------------------------


def write_entry(partial, split, cut_id, w):
    relative = f"audio/{split}/{cut_id}.wav"
    synth.write_wav(partial / relative, w)
    return {"cut_id": cut_id, "relative_path": relative, "num_frames": len(w), "duration": round(len(w) / SR, 4),
            "sha256": synth.sha256_file(partial / relative)}


def window_labels(window, kind, lead):
    first = min(u[0] for u in window["utts"] if u[2] != lead[2]) if kind == "firsttarget" else None
    return {"first_speaker": KINDS[kind], "opener_speaker": window["opener"],
            "lead_start_s": round(lead[0] - window["lo"], 3), "lead_seconds": round(lead[1] - lead[0], 3),
            **({"others_first_start_s": round(first - window["lo"], 3)} if first is not None else {})}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--roots", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, default=Path("/workspace/data/registry/catalog"))
    parser.add_argument("--embed-python", type=Path, required=True, help="Python with onnxruntime and torchaudio")
    parser.add_argument("--speaker-model", type=Path, default=Path(real.SPEAKER_MODEL))
    parser.add_argument("--limit", type=int, help="windows per kind (smoke runs)")
    parser.add_argument("--no-register", action="store_true")
    args = parser.parse_args()
    roots = json.loads(args.roots.read_text())
    data_root = Path(roots[DATASET_ID])
    final = data_root / "source" / VERSION
    if (data_root / "versions" / VERSION).exists() or final.exists():
        raise FileExistsError(f"refusing to replace registered version {VERSION}")
    partial = data_root / "source" / (VERSION + ".partial")
    if partial.exists():
        shutil.rmtree(partial)
    catalog = load_catalog(args.catalog)
    recordings = real.load_corpus(CORPUS, catalog, roots)
    for rid, entry in recordings.items():  # voice check on the sum of the headsets (build.check_cut)
        entry["close_talk"] = [str(p) for p in sorted(near_far.NEAR_DIR.glob(f"{rid}_N_SPK*.wav"))]
        if not entry["close_talk"]:
            raise FileNotFoundError(f"{rid}: no headset recordings in {near_far.NEAR_DIR}")
    windows = {rid: first_speaker_windows(entry, random.Random(f"{SEED}:{rid}:windows"))
               for rid, entry in sorted(recordings.items())}
    matched = match_windows(windows, random.Random(f"{SEED}:match"))
    checker = voice.VoiceCheck(voice.Embedder(args.embed_python, args.speaker_model), real.check_cut, real.ENROLL_CROP,
                               real.ENROLL_STORE, real.check_view)
    noise_files = steady_noise_files()
    report = {"candidate_windows": {k: sum(bool(w[k]) for ws in windows.values() for w in ws) for k in KINDS},
              "matched_windows": {k: len(v) for k, v in matched.items()}, "quarantined": [], "degraded_voice_check": Counter()}
    results, counts = [], Counter()
    for kind, chosen in matched.items():
        if args.limit:
            chosen = chosen[: args.limit]
        index = 0
        for number, window in enumerate(chosen):
            rid = window["recording"]
            rng = random.Random(f"{SEED}:{kind}:{rid}:{window['lo']:.2f}")
            target = rng.choice(sorted(window[kind]))
            lead = window[kind][target]
            where = {"kind": kind, "window": number, "recording": rid, "start_s": round(window["lo"], 3),
                     "duration_s": round(window["hi"] - window["lo"], 3), "target": target}
            lead_check = checker.check(recordings, rid, lead[2], [lead[:2]])
            if not lead_check["passed"]:
                report["quarantined"].append({**where, "reason": "lead_voice_check", "lead_speaker": lead[2],
                                              "verdict": lead_check})
                continue
            absent = real.pick_absent(window, recordings, rng)
            missing = [f"{r}:{s}" for r, s in ((rid, target), absent[:2])
                       if not (near_far.NEAR_DIR / f"{r}_N_SPK{s}.wav").exists()] if absent else ["absent"]
            if missing:
                report["quarantined"].append({**where, "reason": "no_headset_or_absent", "missing": missing})
                continue
            plan = {"window": window, "target": target, "absent": absent}
            scratch = partial / "_render"
            split = f"{kind}-ef-mf"
            rendered = real.render(plan, "alimeeting", CORPUS, recordings, rng, scratch, split, index, checker)
            if len(rendered) != 2:  # an enrollment failed the voice check with every alternative: drop the pair
                report["quarantined"].append({**where, "reason": "enroll_voice_check",
                                              "kept": [r["labels"]["kind"] for r in rendered]})
                shutil.rmtree(scratch, ignore_errors=True)
                continue
            mix = sf.read(scratch / rendered[0]["entries"][0]["relative_path"], dtype="float32")[0]
            for result in rendered:
                pk = result["labels"]["kind"]
                meta, labels = result["metadata"], result["labels"]
                speaker = meta["target_speaker"].split(":", 1)[1]
                pieces = [tuple(p) for p in meta["enrollment_pieces"]]
                far = sf.read(scratch / result["entries"][1]["relative_path"], dtype="float32")[0]
                near = near_enrollment(meta["enrollment"]["recording"], speaker, pieces)
                spec = plan_degradation(random.Random(f"{SEED}:{kind}:{index:04d}:{pk}:degrade"), noise_files)
                degraded = degrade(near, spec)
                degraded_check = checker.check(recordings, meta["enrollment"]["recording"], speaker, pieces, degraded)
                report["degraded_voice_check"][f"{kind}/{pk}/{'passed' if degraded_check['passed'] else 'failed'}"] += 1
                suffix = "" if labels["enroll_condition"] == "clean" else real.ENROLLMIX
                for cell, (domain, degraded_cell) in CELLS.items():
                    name = f"{kind}-{cell}-{pk}{suffix}"
                    base = f"{kind}-{cell}-{index:04d}-{pk}"
                    enroll = degraded if degraded_cell else near if domain == "near" else far
                    out = copy.deepcopy(result)
                    out["split"] = name
                    out["entries"] = [write_entry(partial, name, f"{base}-mix", mix),
                                      write_entry(partial, name, f"{base}-enroll", enroll)]
                    out["labels"].update(scenario=name, group="firstother", cell=cell, enroll_domain=domain,
                                         enroll_degraded=degraded_cell, mix_domain="far",
                                         window_id=f"{kind}:{index:04d}", enroll_seconds=round(len(enroll) / SR, 3),
                                         **window_labels(window, kind, lead))
                    out["metadata"].update(split=name, lead_utterance={
                        "speaker": f"alimeeting:{lead[2]}", "start": round(lead[0] - window["lo"], 3),
                        "duration": round(lead[1] - lead[0], 3), "text": lead[3], "voice_check": lead_check})
                    if degraded_cell:
                        out["metadata"].update(enroll_degradation=spec, enroll_degraded_voice_check=degraded_check)
                    results.append(out)
                    counts[name] += 1
            shutil.rmtree(scratch)
            index += 1
    checker.embed.close()
    report["voice_check"] = {"/".join(k): v for k, v in sorted(checker.stats.items())}
    report["voice_check_dropped"] = checker.events
    report["records"] = dict(sorted(counts.items()))
    pos = [r for r in results if r["labels"]["kind"] == "pos" and r["labels"]["cell"] == "ef-mf"]
    report["windows"] = {kind: {
        "count": len(rs), "mean_duration_s": round(float(np.mean([r["labels"]["duration_s"] for r in rs])), 2),
        "speakers_in_window": dict(sorted(Counter(r["labels"]["speakers_in_window"] for r in rs).items())),
        "mean_target_seconds": round(float(np.mean([r["labels"]["target_seconds"] for r in rs])), 2),
        "mean_lead_seconds": round(float(np.mean([r["labels"]["lead_seconds"] for r in rs])), 2),
        "recordings": len({r["labels"]["recording"] for r in rs}),
        "absent_source": dict(Counter(n["labels"]["absent_source"] for n in results
                                      if n["labels"]["kind"] == "neg" and n["labels"]["cell"] == "ef-mf"
                                      and n["labels"]["first_speaker"] == KINDS[kind]))}
        for kind in KINDS for rs in [[r for r in pos if r["labels"]["first_speaker"] == KINDS[kind]]] if rs}
    report["degraded_voice_check"] = dict(sorted(report["degraded_voice_check"].items()))
    report["rule"] = {"window_span_s": WINDOW_SPAN, "window_range_s": WINDOW_RANGE, "min_speakers": MIN_SPEAKERS,
                      "min_target_seconds": MIN_TARGET_SECONDS, "lead_seconds": LEAD_SECONDS,
                      "lead_max_overlap": LEAD_MAX_OVERLAP, "degrade_snr_db": DEGRADE_SNR_DB, "lowpass_hz": LOWPASS_HZ,
                      "shelf": {"corner_hz": SHELF_HZ, "gain_db": SHELF_DB, "width_hz": SHELF_WIDTH_HZ},
                      "noise": f"{NOISE_CACHE}/{NOISE_POOL} (stationary)", "seed": SEED}
    partial.mkdir(parents=True, exist_ok=True)
    (partial / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, default=list) + "\n")
    print(json.dumps({k: report[k] for k in ("matched_windows", "records", "windows", "degraded_voice_check")},
                     ensure_ascii=False, indent=1), "\nquarantined:", Counter(q["reason"] for q in report["quarantined"]),
          flush=True)
    partial.rename(final)
    splits = []
    for name in sorted(counts, key=lambda n: (n.removesuffix(real.ENROLLMIX), n.endswith(real.ENROLLMIX))):
        kind, cell = name.split("-", 1)[0], name.split("-")[1] + "-mf"
        splits.append({"name": name, "group": kind, "n": counts[name],
                       "params": {"corpus": "alimeeting", "cell": cell,
                                  **({"enroll_condition": "others_speech"} if name.endswith(real.ENROLLMIX) else {})}})
    declaration = synth.register({"version": VERSION, "dataset_id": DATASET_ID, "pools": {}}, splits, results,
                                 data_root, DATASET_ID)
    for name, split in declaration["splits"].items():
        kind, cell, pk = name.split("-")[0], "-".join(name.split("-")[1:3]), name.split("-")[3]
        split["provenance"]["description"] = (
            ("窗口里第一个开口的是非目标说话人，且目标第一句之前已有他人一整句清晰语句" if kind == "firstother"
             else "目标说话人第一个开口（对照）")
            + {"ef-mf": "；注册取远场通道 0", "en-mf": "；注册取本人头戴麦（跨通道）",
               "ed-mf": "；注册取本人头戴麦并加噪、限带（劣化注册）"}[cell]
            + ("；目标在场" if pk == "pos" else "；目标缺席")
            + (f"；注册前 {real.ENROLL_CROP:g} 秒里他人说话不少于 {real.ENROLL_CROP_OTHERS_MAX} 秒" if name.endswith(real.ENROLLMIX) else ""))
    declaration["provenance"] = {
        "status": "complete", "synthetic": "partial",
        "description": (
            "“谁先开口”对照：复现一条内部返回的 TS-ASR badcase（45 秒三人同屋交替说话，注册是另一次单独录的 5 秒声纹，"
            "会话开头是非目标说话人清晰发言，所有版本都整段转写了先开口的人；把那句挪到末尾或改用会话内语音注册都能认对），"
            "原因是两个因素叠加：注册与会话不同录音、匹配信号弱，以及混合开头先是非目标说话人。"
            "从 AliMeeting Test 远场通道 0 的人工标注里按完整语句切 25–45 秒窗口，窗口内至少 3 人说话、目标累计说话至少 5 秒，不做混合。"
            f"firstother：窗口第一个开口的不是目标，且目标第一句之前已有非目标一整句不少于 {LEAD_SECONDS} 秒、被他人重叠不超过 "
            f"{LEAD_MAX_OVERLAP:.0%} 的语句；firsttarget：同样规则下目标先开口，作对照，与 firstother 同一批会议、每个（会议，说话人数）取相同窗口数。"
            "每个窗口一对样本：目标在场，和目标缺席（注册取同会议不在窗口里说话的人，没有时取其他会议的人，labels.absent_source）。"
            "注册沿用 ts_asr_real@v4-20261022：窗外第一句，后接同一人窗外无他人重叠的语句共存 10 秒，客户端取前 5 秒，"
            "前 5 秒他人说话不少于 0.3 秒的在 -enrollmix 划分；注册和开头那句都过声纹核对（头戴麦之和建档），不过的换句或整窗隔离，"
            "见 source/<版本>/report.json。注册三种：ef 远场通道 0（同通道）、en 本人头戴麦同样片段（跨通道，接近单独录的声纹）、"
            "ed 为 en 加限带（3.5–5 kHz 低通或 4 kHz 以上 −6 dB 高架）后再加 WHAM! 测试集稳态噪声（SNR 15–25 dB），"
            "参数逐条记在 metadata.enroll_degradation，劣化后的声纹核对结果在 metadata.enroll_degraded_voice_check；混合一律远场通道 0（mf）。"
            "窗口长于 ts_asr_real 的 26 秒上限，评测需整段送入。只用于评测，不进训练。生成脚本 scripts/ts_real/first_speaker.py。"),
        "sources": [f"{CORPUS['dataset']}@{CORPUS['version']}:{CORPUS['split']}", "alimeeting:Test_Ali_near",
                    f"ts_asr_benchmark/source/v4-20261022/noise/{NOISE_POOL}"],
    }
    if args.no_register:
        return
    path = REPO / "catalog" / f"{DATASET_ID}.yaml"
    rows = list(yaml.safe_load(path.read_text()))
    validate_catalog([*load_catalog(REPO / "catalog"), DatasetSpec.from_dict(declaration)])
    path.write_text(yaml.safe_dump([*rows, declaration], allow_unicode=True, sort_keys=False, width=512), encoding="utf-8")
    print("registered", VERSION, len(results), "records", flush=True)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""ts_asr_real meeting-v4: AliMeeting and MagicData-RAMC test recordings sent the way speaker-enroll sends them, with
controls that each change one thing of a request, to locate why absent targets get output.

Downstream badcase ``tsasr-farfield-target-absent-20261124``: in a phone far-field company meeting with 2-3 people,
AmphionASR 11.17 produced output for 47.9% of the requests whose box's person did not speak (MOSS-judged), against
3.8% on AISHELL-4 (``meeting-v3-20261117``, 24,342 absent requests). On meeting-v3, 11.17's absent false alarms rise
from 2% to 20% as the ECAPA cosine of the enrollment with the closest other talker goes from below 0.3 to 0.5 and
above, from 0.9% (segments of 10 s and more) to 8.9% (under 2 s), and from 2.4% to about 8% with overlap. One
meeting cannot tell which factor reached 48%, nor whether the model takes "the enrollment comes from this recording"
as evidence of the target. Each recording here is sent with meeting-v3's rules (``meeting_segments.py`` segments,
enrollment and voice check; ``meeting_nested.py``'s interjection rule; ``meeting_quarantine.py``'s speaker-label
check, run here on the far-field audio) and every request is also sent under controls:

* base, ``meeting-<corpus>-<pos|neg>``: AliMeeting far-field channel 0, RAMC the phone recording; enrollment from the
  same recording (meeting-v3's way). A person without an utterance that rule allows gets no box; in AliMeeting
  R8005_M8009 (everyone) and R8004_M8006 (three of four) every utterance is talked over, by the annotation;
* ``-xrec`` (absent requests): the enrollment of a person from another recording of the corpus (test or dev; the
  speakers of the two splits are distinct) replaces the box's, chosen so that its cosine with the closest talker of
  the segment is nearest to the in-meeting enrollment's (``labels.base_impostor_sim``, ``labels.xrec_sim_gap``).
  Same segment, matched similarity, only the recording of the enrollment differs;
* ``-enear`` (AliMeeting): the same enrollment pieces cut from the person's own headset, segment unchanged: the
  enrollment no longer carries the room's far-field acoustics;
* ``-near`` (AliMeeting): headset enrollment and the segment as the sum of all headsets over it, scaled to the
  far-field RMS (``near_far.py``): close-talk on both sides;
* ``-snr`` (AliMeeting): base audio plus one real meeting-room noise recording per meeting
  (``meeting_room_noise@v2-20261014``, rooms of the train splits) at one gain per meeting, set so that the meeting's
  median segment is ``SNR_DB`` dB above the noise (the downstream phone recording is 6-10 dB above its floor). The
  enrollment and the segment take the noise at their own times, as one recorder would; an enrollment takes it turned
  down as far as needed to stay ``ENROLL_SNR_MIN`` dB above it (speaker-enroll only keeps such pieces).

Controls carry ``labels.control`` and ``metadata.base`` (split, recording, segment index, target) to pair them with
their base request; for ``-enear``/``-near``/``-snr`` the similarity labels are the base's (far-field, no noise).
RAMC test and dev recordings with a speaker of the train split are left out (9 test speakers are in train).
The annotation text check of meeting_quarantine.py needs a plain-ASR transcript per segment and is applied in a
later version.

    python scripts/ts_real/meeting_controls.py --roots /workspace/data/registry/roots.json \\
        --embed-python /workspace/workspace/mingdong/miniconda3/envs/k2/bin/python
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.util
import json
import shutil
import statistics
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import soundfile as sf
import yaml

from audio_data_contract import AudioRecord, load_catalog, resolve_split
from audio_data_contract.catalog import validate_catalog
from audio_data_contract.types import DatasetSpec

HERE = Path(__file__).resolve().parent


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ms = _load("ts_real_meeting_segments", "meeting_segments.py")
nf = _load("ts_real_near_far", "near_far.py")
real, voice, synth = ms.real, ms.voice, ms.synth
REPO = HERE.parents[1]
SR = real.SR
DATASET_ID = real.DATASET_ID
VERSION = "meeting-v4-20261125"
CORPORA = {name: real.RECIPE["corpora"][name] for name in ("alimeeting", "ramc")}
POOL_SPLIT = "dev"  # further strangers for -xrec
HEADSET_DIR = nf.NEAR_DIR  # AliMeeting Test headsets, <recording>_N_SPK<speaker>.wav
HEADSET_SOURCE = "alimeeting@openslr-119-local-20260826:test"
NOISE = ("meeting_room_noise", "v2-20261014", "train")
NOISE_MIN = 30.0  # s; shorter noise recordings loop too often
NOISE_XFADE = 0.05  # s crossfade where the noise loops
SNR_DB = 8.0
ENROLL_SNR_MIN = 6.0  # speaker-enroll keeps enrollment pieces at least this far above the noise
INSIDE_OTHER = 0.5  # meeting_nested.py
SPEAKER_SOLO, SPEAKER_MARGIN = 3.0, 0.1  # meeting_quarantine.py
PEAK_LIMIT = 0.99
NAMES = {"alimeeting": "AliMeeting 远场会议", "ramc": "MagicData-RAMC 手机对话"}
CONTROLS = {
    "alimeeting": ("xrec", "enear", "near", "snr"),
    "ramc": ("xrec",),
}


def db(x):
    return float(20 * np.log10(nf.rms(x)))


def limit(w):
    peak = float(np.abs(w).max()) if len(w) else 0.0
    return w * (PEAK_LIMIT / peak) if peak > PEAK_LIMIT else w


class NoiseLoop:
    """One noise recording as an endless seamless loop (the tail crossfades into the head)."""

    def __init__(self, path):
        x, rate = sf.read(path, dtype="float32", always_2d=True)
        if rate != SR:
            raise ValueError(f"{path}: expected {SR} Hz, got {rate}")
        x, f = x[:, 0], int(NOISE_XFADE * SR)
        ramp = np.linspace(0.0, 1.0, f, dtype=np.float32)
        loop = x[f:].copy()
        loop[-f:] = x[-f:] * (1.0 - ramp) + x[:f] * ramp
        self.loop, self.db = loop, db(loop)

    def at(self, start_s, n):
        first = round(start_s * SR)
        return self.loop[np.arange(first, first + n) % len(self.loop)]


def noise_recordings(catalog, roots):
    out = []
    for path in resolve_split(catalog, *NOISE, "recordings", roots):
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            for line in stream:
                row = json.loads(line)
                if row["duration"] >= NOISE_MIN:
                    out.append((row["id"], row["sources"][0]["source"]))
    return sorted(out)


def pick(items, key):
    return items[int(hashlib.sha256(f"{VERSION}:{key}".encode()).hexdigest(), 16) % len(items)]


def nested_share(owner, lo, hi, utts):
    """Largest share of [lo, hi] that one utterance of someone other than ``owner`` covers."""
    return max((min(hi, e) - max(lo, s) for s, e, spk, _ in utts if spk != owner), default=0.0) / (hi - lo)


def speaker_label_check(checker, mix, lo, owner, utts, profiles):
    """meeting_quarantine.py's speaker check on the far-field segment: embedding of the part where only ``owner`` is
    annotated (the whole segment when that is under 1 s) against every speaker's meeting profile."""
    keep = np.ones(len(mix), dtype=bool)
    for s, e, spk, _ in utts:
        if spk != owner:
            keep[max(0, round((s - lo) * SR)):max(0, round((e - lo) * SR))] = False
    solo = mix[keep] if keep.sum() >= SR else mix
    vector = checker.embed(solo)
    sims = {spk: float(vector @ v) for spk, v in profiles.items() if v is not None}
    others = {spk: v for spk, v in sims.items() if spk != owner}
    best = max(others, key=others.get) if others else None
    row = {"solo_s": round(float(keep.sum()) / SR, 2), "owner_sim": round(sims.get(owner, float("nan")), 3),
           "best_other": best, "best_other_sim": round(others[best], 3) if best else None}
    row["rejected"] = bool(best is not None and owner in sims and row["solo_s"] >= SPEAKER_SOLO
                           and others[best] - sims[owner] >= SPEAKER_MARGIN)
    return row


def headset_pieces(rid, speaker, pieces, far):
    """The enrollment pieces from the speaker's own headset, scaled to the far-field enrollment's RMS (only the
    acoustics differ, as near_far.py does for mixtures)."""
    path = HEADSET_DIR / f"{rid}_N_SPK{speaker}.wav"
    if not path.exists():
        return None
    w = np.concatenate([nf.cut_near(path, s, e) for s, e in pieces])[: int(real.ENROLL_STORE * SR)]
    return limit(w * (nf.rms(far) / nf.rms(w))) if nf.rms(w) > 1e-6 else None


class Writer:
    """Audio files of the version (written once, shared by every record that uses them)."""

    def __init__(self, partial):
        self.partial, self.rows = partial, {}

    def __call__(self, folder, cut_id, w):
        if cut_id not in self.rows:
            self.rows[cut_id] = ms._write(self.partial, folder, cut_id, w)
        return self.rows[cut_id]


def enroll_meeting(checker, recordings, rid, crop):
    """{speaker: box} of one recording (meeting_segments.py's enrollment and voice check) and its profiles."""
    entry = recordings[rid]
    speakers = sorted({u[2] for u in entry["sups"]})
    profiles = {spk: checker.profile(recordings, rid, spk)[0] for spk in speakers}
    boxes, no_box = {}, []
    for speaker in speakers:
        picked = ms.enroll(checker, recordings, rid, speaker)
        if picked is None:
            no_box.append({"recording": rid, "speaker": speaker, "eligible": len(entry["eligible"].get(speaker, []))})
            continue
        pieces, audio, verdict, tried = picked
        vector = checker.embed(audio[:crop])
        sims = {}
        for other in speakers:
            profile = checker.profile(recordings, rid, other, pieces)[0] if other == speaker else profiles[other]
            if profile is not None:
                sims[other] = round(float(vector @ profile), 3)
        boxes[speaker] = {"pieces": pieces, "audio": audio, "verdict": verdict, "tried": tried, "sims": sims,
                          "vector": vector, "others_s": real.pieces_others(entry, speaker, pieces)[0]}
    return boxes, profiles, no_box


def stranger(pool, rid, talkers, profiles, target_sim):
    """(pool item, its cosine with the closest talker, that talker) nearest to ``target_sim`` among people of other
    recordings."""
    best = None
    for item in pool:
        if item["recording"] == rid:
            continue
        sims = {spk: float(item["vector"] @ profiles[spk]) for spk in talkers if profiles.get(spk) is not None}
        closest = max(sims, key=sims.get)
        key = (abs(sims[closest] - target_sim), item["recording"], item["speaker"])
        if best is None or key < best[0]:
            best = (key, item, round(sims[closest], 3), closest)
    return best[1:]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--roots", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, default=Path("/workspace/data/registry/catalog"))
    parser.add_argument("--embed-python", type=Path, required=True, help="Python with onnxruntime and torchaudio")
    parser.add_argument("--speaker-model", type=Path, default=Path(real.SPEAKER_MODEL))
    parser.add_argument("--threads", type=int, default=16)
    parser.add_argument("--corpora", nargs="*", default=list(CORPORA))
    parser.add_argument("--recordings", nargs="*", help="only these test recordings (smoke runs; never registered)")
    parser.add_argument("--pool-recordings", type=int, help="at most this many dev recordings per corpus (smoke runs)")
    parser.add_argument("--no-register", action="store_true")
    args = parser.parse_args()
    smoke = bool(args.recordings or args.pool_recordings)
    roots = json.loads(args.roots.read_text())
    data_root = Path(roots[DATASET_ID])
    final = data_root / "source" / VERSION
    if (data_root / "versions" / VERSION).exists() or final.exists():
        raise FileExistsError(f"refusing to replace registered version {VERSION}")
    partial = data_root / "source" / (VERSION + ".partial")
    if partial.exists():
        shutil.rmtree(partial)
    catalog = load_catalog(args.catalog)
    checker = voice.VoiceCheck(voice.Embedder(args.embed_python, args.speaker_model, threads=args.threads),
                               real.check_cut, real.ENROLL_CROP, real.ENROLL_STORE, real.check_view)
    crop = int(real.ENROLL_CROP * SR)
    write = Writer(partial)
    noises = noise_recordings(catalog, roots)
    results = []
    report = {"rule": {"turn_gap_s": ms.TURN_GAP, "merge_cap_s": ms.MERGE_CAP, "min_segment_s": ms.MIN_SEGMENT,
                       "absent_margin_s": ms.ABSENT_MARGIN, "present_min_s": ms.PRESENT_MIN,
                       "enroll_crop_s": real.ENROLL_CROP, "enroll_store_s": real.ENROLL_STORE,
                       "inside_other": INSIDE_OTHER, "speaker_solo_s": SPEAKER_SOLO, "speaker_margin": SPEAKER_MARGIN,
                       "snr_db": SNR_DB, "enroll_snr_min_db": ENROLL_SNR_MIN, "noise_min_s": NOISE_MIN, "speaker_model": str(args.speaker_model)},
              "corpora": {}, "no_box": [], "speaker_label_rejected": []}
    for name in args.corpora:
        corpus = CORPORA[name]
        trained = real.train_speakers(corpus, catalog, roots)
        recordings, held_out = {}, []
        for split in (corpus["split"], POOL_SPLIT):
            loaded = real.load_corpus(corpus, catalog, roots, split=split)
            for rid, entry in sorted(loaded.items()):
                if {u[2] for u in entry["sups"]} & trained:
                    held_out.append(rid)
                    continue
                entry["split"] = split
                recordings[rid] = entry
        tests = sorted(r for r, e in recordings.items() if e["split"] == corpus["split"])
        pool_ids = sorted(r for r, e in recordings.items() if e["split"] == POOL_SPLIT)
        if args.recordings:
            tests = [r for r in tests if r in args.recordings]
        if args.pool_recordings is not None:
            pool_ids = pool_ids[: args.pool_recordings]
        meetings, pool = {}, []
        for rid in tests + pool_ids:
            boxes, profiles, no_box = enroll_meeting(checker, recordings, rid, crop)
            meetings[rid] = (boxes, profiles)
            report["no_box"] += [{"corpus": name, **x} for x in no_box]
            pool += [{"recording": rid, "speaker": spk, "vector": box["vector"], "box": box} for spk, box in boxes.items()]
            print(name, rid, recordings[rid]["split"], "boxes", len(boxes), "of", len(profiles), flush=True)
        summary = {"test_recordings": len(tests), "pool_recordings": len(pool_ids), "held_out_train_speakers": held_out,
                   "pool_people": len(pool), "dropped": Counter(), "meetings": {}}
        report["corpora"][name] = summary
        prefix = f"meeting-{name}"

        def enroll_entry(rid, speaker, view="far", meetings=meetings, prefix=prefix):
            box = meetings[rid][0][speaker]
            if view == "far":
                return write(f"{prefix}-enroll", f"{prefix}-{rid}-{speaker}-enroll", box["audio"])
            return write(f"{prefix}-enroll-headset", f"{prefix}-{rid}-{speaker}-enroll-headset", box["headset"])

        for rid in tests:
            entry = recordings[rid]
            boxes, profiles = meetings[rid]
            segs = ms.segments(entry)
            plans, dropped = ms.plan_requests(entry, segs, {spk: b["pieces"] for spk, b in boxes.items()})
            summary["dropped"].update(dropped)
            mixes, rejected = {}, set()
            for i in sorted({p[0] for p in plans}):
                lo, hi, owner, _ = segs[i]
                inside = sorted(real.overlapping(entry, lo, hi))
                if nested_share(owner, lo, hi, inside) >= INSIDE_OTHER:
                    rejected.add(i)
                    summary["dropped"]["nested_segment"] += 1
                    continue
                mix = real.cut(recordings, rid, lo, hi)
                if abs(len(mix) / SR - (hi - lo)) > 0.05:
                    raise ValueError(f"{rid}: the audio is shorter than its annotation at {lo:.2f}")
                check = speaker_label_check(checker, mix, lo, owner, inside, profiles)
                if check["rejected"]:
                    rejected.add(i)
                    summary["dropped"]["speaker_label_segment"] += 1
                    report["speaker_label_rejected"].append({"corpus": name, "recording": rid, "start": round(lo, 3),
                                                             "duration": round(hi - lo, 3), "owner": owner, **check})
                    continue
                mixes[i] = {"audio": mix, "utts": inside, "rms": round(db(mix), 2), "check": check,
                            "talk": {spk: round(sec, 3) for spk, sec in sorted(real.speaker_seconds(
                                [(max(lo, s), min(hi, e), spk, t) for s, e, spk, t in inside]).items())},
                            "overlap": round(ms.overlap_seconds(inside, lo, hi), 3)}
            summary["dropped"]["requests_in_dropped_segments"] += sum(p[0] in rejected for p in plans)
            plans = [p for p in plans if p[0] not in rejected]
            controls = CONTROLS[name]
            if "enear" in controls or "near" in controls:
                for spk, box in boxes.items():
                    box["headset"] = headset_pieces(rid, spk, box["pieces"], box["audio"])
            if "snr" in controls and mixes:
                noise_id, noise_path = pick(noises, rid)
                noise = NoiseLoop(noise_path)
                median_db = statistics.median(m["rms"] for m in mixes.values())
                gain_db = median_db - SNR_DB - noise.db
                gain = 10 ** (gain_db / 20)
            counts = Counter()
            for i, speaker, kind, seconds, own in plans:
                lo, hi, owner, _ = segs[i]
                m, box = mixes[i], boxes[speaker]
                present = kind == "pos"
                others = {spk: sec for spk, sec in m["talk"].items() if spk != speaker and sec >= ms.PRESENT_MIN}
                impostor = max(others, key=lambda s: box["sims"].get(s, -1.0), default=None)
                labels = {
                    "scenario": f"{prefix}-{kind}", "group": "meeting", "control": "base", "kind": kind,
                    "target_present": present, "corpus": name, "recording": rid, "duration_s": round(hi - lo, 3),
                    "window_start_s": round(lo, 3), "speakers_in_window": len(m["talk"]),
                    "n_interferers": len(m["talk"]) - (1 if present else 0), "meeting_boxes": len(boxes),
                    "segment_speaker": owner, "target_is_segment_speaker": owner == speaker, "overlap_s": m["overlap"],
                    "mixture_rms_dbfs": m["rms"], "annotation": "human", "enroll_seconds": round(len(box["audio"]) / SR, 3),
                    "enroll_others_s": box["others_s"], "enroll_condition": "clean",
                    "enroll_own_sim": box["sims"].get(speaker), "impostor_speaker": impostor,
                    "impostor_sim": box["sims"].get(impostor) if impostor else None,
                    "owner_sim": box["sims"].get(owner) if owner != speaker else None,
                    "segment_owner_check_sim": m["check"]["owner_sim"],
                }
                if present:
                    labels.update(target_seconds=round(seconds, 3),
                                  target_overlap_ratio=round(real.overlap_ratio(own, m["utts"]), 3))
                else:
                    labels["absent_source"] = "same_recording"
                metadata = {
                    "target_speaker": f"{name}:{speaker}", "segment_index": i,
                    "enrollment": {"recording": rid, "start": round(box["pieces"][0][0], 3),
                                   "end": round(box["pieces"][0][1], 3)},
                    "enrollment_pieces": [[round(s, 3), round(e, 3)] for s, e in box["pieces"]],
                    "enroll_voice_check": box["verdict"], "enroll_attempts": box["tried"],
                    "enroll_sims": {f"{name}:{s}": v for s, v in box["sims"].items()},
                    "talk": {f"{name}:{s}": v for s, v in m["talk"].items()},
                    "window_utts": [{"speaker": f"{name}:{spk}", "start": round(max(s, lo) - lo, 3),
                                     "duration": round(min(e, hi) - max(s, lo), 3), "text": text,
                                     **({"clipped": True} if s < lo or e > hi else {})}
                                    for s, e, spk, text in m["utts"]],
                }
                target = "".join(u[3] for u in own) if present else ""
                base = {"split": f"{prefix}-{kind}", "recording": rid, "segment_index": i, "target_speaker": f"{name}:{speaker}"}
                mix_entry = write(f"{prefix}-mix", f"{prefix}-{rid}-{i:04d}-mix", m["audio"])

                def add(split, mix_e, enroll_e, extra_labels=None, extra_meta=None,
                        target=target, labels=labels, metadata=metadata, base=base, counts=counts):
                    results.append({"split": split, "target": target,
                                    "labels": {**labels, **(extra_labels or {}), "scenario": split},
                                    "metadata": {**metadata, **({"base": base} if split != base["split"] else {}),
                                                 **(extra_meta or {})},
                                    "entries": [mix_e, enroll_e]})
                    counts[split] += 1

                add(base["split"], mix_entry, enroll_entry(rid, speaker))
                if "xrec" in controls and not present and labels["impostor_sim"] is not None:
                    talkers = sorted(others)
                    item, sim, closest = stranger(pool, rid, talkers, profiles, labels["impostor_sim"])
                    add(f"{prefix}-neg-xrec", mix_entry, enroll_entry(item["recording"], item["speaker"]),
                        {"control": "xrec", "absent_source": "other_recording", "impostor_speaker": closest,
                         "impostor_sim": sim, "base_impostor_sim": labels["impostor_sim"],
                         "xrec_sim_gap": round(sim - labels["impostor_sim"], 3), "owner_sim": None, "enroll_own_sim": None,
                         "xrec_recording": item["recording"], "xrec_speaker": f"{name}:{item['speaker']}",
                         "xrec_split": recordings[item["recording"]]["split"],
                         "enroll_seconds": round(len(item["box"]["audio"]) / SR, 3), "enroll_others_s": item["box"]["others_s"]},
                        {"enrollment": {"recording": item["recording"], "start": round(item["box"]["pieces"][0][0], 3),
                                        "end": round(item["box"]["pieces"][0][1], 3)},
                         "enrollment_pieces": [[round(s, 3), round(e, 3)] for s, e in item["box"]["pieces"]],
                         "enroll_voice_check": item["box"]["verdict"], "enroll_sims": None,
                         "xrec_sims": {f"{name}:{s}": round(float(item["vector"] @ profiles[s]), 3)
                                       for s in sorted(m["talk"]) if profiles.get(s) is not None}})
                if box.get("headset") is not None:
                    if "enear" in controls:
                        add(f"{prefix}-{kind}-enear", mix_entry, enroll_entry(rid, speaker, "headset"),
                            {"control": "enear", "enroll_view": "headset", "mixture_view": "far"})
                    if "near" in controls:
                        if "near_entry" not in m:
                            near = nf.near_mixture(rid, lo, hi, nf.rms(m["audio"]))
                            m["near_entry"] = None if near is None else write(
                                f"{prefix}-mix-headsets", f"{prefix}-{rid}-{i:04d}-mix-headsets", near)
                        if m["near_entry"] is not None:
                            add(f"{prefix}-{kind}-near", m["near_entry"], enroll_entry(rid, speaker, "headset"),
                                {"control": "near", "enroll_view": "headset", "mixture_view": "headset_sum"})
                if "snr" in controls:
                    if "snr_entry" not in m:
                        noisy = limit(m["audio"] + gain * noise.at(lo, len(m["audio"])))
                        m["snr_entry"] = write(f"{prefix}-mix-snr", f"{prefix}-{rid}-{i:04d}-mix-snr", noisy)
                    noisy_entry = m["snr_entry"]
                    if "snr_audio" not in box:
                        # The service picks enrollment pieces >= ENROLL_SNR_MIN dB above the noise: a quiet person's
                        # enrollment takes the same noise, turned down as far as needed (a quieter stretch of it).
                        level = db(box["audio"][:crop])
                        box["snr_gain_db"] = min(gain_db, level - ENROLL_SNR_MIN - noise.db)
                        g = 10 ** (box["snr_gain_db"] / 20)
                        parts = [real.cut(recordings, rid, s, e) for s, e in box["pieces"]]
                        parts = [p + g * noise.at(s, len(p)) for p, (s, _) in zip(parts, box["pieces"])]
                        box["snr_audio"] = limit(np.concatenate(parts)[: int(real.ENROLL_STORE * SR)])
                        box["snr_db"] = round(level - noise.db - box["snr_gain_db"], 2)
                    snr_enroll = write(f"{prefix}-enroll-snr", f"{prefix}-{rid}-{speaker}-enroll-snr", box["snr_audio"])
                    add(f"{prefix}-{kind}-snr", noisy_entry, snr_enroll,
                        {"control": "snr", "snr_db": round(m["rms"] - noise.db - gain_db, 2),
                         "enroll_snr_db": box["snr_db"], "noise_gain_db": round(gain_db, 2),
                         "enroll_noise_gain_db": round(box["snr_gain_db"], 2)},
                        {"noise": {"recording": noise_id, "meeting_median_dbfs": round(median_db, 2)}})
            summary["meetings"][rid] = {"segments": len(segs), "sent_segments": len(mixes), "speakers": len(profiles),
                                        "boxes": len(boxes), **dict(sorted(counts.items()))}
            print(name, rid, summary["meetings"][rid], flush=True)
        summary["dropped"] = dict(summary["dropped"])
    checker.embed.close()

    def deciles(values):
        values = [v for v in values if v is not None]
        return [round(v, 3) for v in statistics.quantiles(values, n=10)] if len(values) > 1 else values

    splits = sorted({r["split"] for r in results})
    report["records"] = dict(Counter(r["split"] for r in results))
    report["deciles"] = {s: {k: deciles([r["labels"].get(k) for r in results if r["split"] == s])
                             for k in ("duration_s", "impostor_sim", "xrec_sim_gap", "snr_db", "overlap_s")} for s in splits}
    report["voice_check"] = {"/".join(map(str, k)): v for k, v in sorted(checker.stats.items())}
    partial.mkdir(parents=True, exist_ok=True)
    (partial / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, default=list) + "\n")
    print(json.dumps({k: report[k] for k in ("records", "no_box")}, ensure_ascii=False, indent=1), flush=True)
    if smoke:  # kept apart from the version's directory, never registered
        with (partial / "results.jsonl").open("w", encoding="utf-8") as stream:
            for r in results:
                stream.write(json.dumps(r, ensure_ascii=False) + "\n")
        out = data_root / "source" / (VERSION + ".smoke")
        shutil.rmtree(out, ignore_errors=True)
        partial.rename(out)
        print("smoke run written to", out, flush=True)
        return
    partial.rename(final)
    register(results, write.rows, data_root, args)


SPLIT_TEXT = {
    "pos": "目标在场（本人在这段里说话 ≥0.5 秒，且所说语句都完整落在段内）",
    "neg": "目标缺席（本人在这段前后 0.5 秒内都没有说话）",
    "neg-xrec": "目标缺席，注册换成同语料另一场录音里的人：与段内最像的在场人的声纹相似度最接近原注册（labels.base_impostor_sim、xrec_sim_gap），段不变",
    "pos-enear": "目标在场，注册取同一批语句的本人头戴麦录音，段仍为远场通道 0",
    "neg-enear": "目标缺席，注册取同一批语句的本人头戴麦录音，段仍为远场通道 0",
    "pos-near": "目标在场，注册取本人头戴麦，段为全部头戴麦之和（按远场 RMS 缩放）",
    "neg-near": "目标缺席，注册取本人头戴麦，段为全部头戴麦之和（按远场 RMS 缩放）",
    "pos-snr": f"目标在场，段与注册都加同一条真实会议室底噪（按会议时间对齐），每场一个增益，使段的中位信噪比为 {SNR_DB:g} dB",
    "neg-snr": f"目标缺席，段与注册都加同一条真实会议室底噪（按会议时间对齐），每场一个增益，使段的中位信噪比为 {SNR_DB:g} dB",
}


def register(results, index_rows, data_root, args):
    """Records, audio index (one row per file; files are shared across records) and catalog entry."""
    def rel(*parts):
        return "/".join(("versions", VERSION, *parts))

    by_split = defaultdict(list)
    for r in results:
        by_split[r["split"]].append(r)
    artifacts, split_decl = [], {}
    for name in sorted(by_split):
        records = []
        for number, r in enumerate(sorted(by_split[name], key=lambda r: (r["labels"]["recording"], r["metadata"]["segment_index"],
                                                                          r["metadata"]["target_speaker"]))):
            mix, enrollment = r["entries"]

            def ref(e, split_name=name):
                return {"dataset_id": DATASET_ID, "version": VERSION, "split": split_name, "cut_id": e["cut_id"],
                        "duration": e["duration"]}

            r["metadata"]["index"] = number
            records.append(AudioRecord.from_dict({
                "schema_version": "audio-record/1.0", "id": f"{name}:{number:05d}", "task": "ts_asr",
                "audio_slots": [{"name": "enrollment", "purpose": "enrollment", "ref": ref(enrollment)},
                                {"name": "mixture", "purpose": "mixture", "ref": ref(mix)}],
                "target": r["target"], "language": "zh", "labels": r["labels"], "metadata": r["metadata"],
            }).to_dict())
        path = rel("records", f"{name}.jsonl.gz")
        synth.write_jsonl_gz(data_root / path, records)
        artifacts.append({"name": f"{name}-records", "kind": "audio-records", "root_alias": DATASET_ID, "relative_path": path,
                          "sha256": synth.sha256_file(data_root / path), "metadata": {"record_count": len(records)}})
        seconds = sum(r["audio_slots"][1]["ref"]["duration"] for r in records)
        corpus, rest = name[len("meeting-"):].split("-", 1)
        split_decl[name] = {"artifacts": {"records": [f"{name}-records"], "audio_index": ["audio-index"]}, "task": "ts_asr",
                            "statistics": {"records": len(records), "duration_hours": round(seconds / 3600, 4),
                                           "duration_basis": "Mixture duration"},
                            "provenance": {"description": f"{NAMES[corpus]} test 整场，按人工标注切的每一段发给会上每个注册人；"
                                                          + SPLIT_TEXT[rest]}}
    rows = [{**e, "root_alias": DATASET_ID, "sample_rate": SR, "channels": 1,
             "relative_path": f"source/{VERSION}/{e['relative_path']}"} for e in index_rows.values()]
    synth.write_jsonl_gz(data_root / rel("audio-index.jsonl.gz"), sorted(rows, key=lambda e: e["cut_id"]))
    artifacts.insert(0, {"name": "audio-index", "kind": "audio-index", "root_alias": DATASET_ID,
                         "relative_path": rel("audio-index.jsonl.gz"),
                         "sha256": synth.sha256_file(data_root / rel("audio-index.jsonl.gz")),
                         "metadata": {"record_count": len(rows)}})
    sources = [f"{c['dataset']}@{c['version']}:{s}" for c in CORPORA.values() for s in (c["split"], POOL_SPLIT)]
    declaration = {"schema_version": "dataset-catalog/2.0", "dataset_id": DATASET_ID, "version": VERSION, "languages": ["zh"],
                   "tasks": ["ts_asr"], "artifacts": artifacts, "splits": split_decl}
    declaration["provenance"] = {
        "summary": "目标说话人评测：整场会议逐段发送与定位对照", "status": "complete",
        "synthetic": "none",
        "description": (
            "下游 badcase tsasr-farfield-target-absent-20261124：手机远场的 2–3 人会议里，目标人不在场时 11.17 有 47.9% 的请求仍有输出，"
            "AISHELL-4（meeting-v3-20261117）是 3.8%。这一版按 meeting-v3 的规则（meeting_segments.py 的分段、注册与声纹核对，"
            f"meeting_nested.py 去掉插话段，meeting_quarantine.py 的说话人核对在远场音频上做：段内独自说话 ≥{SPEAKER_SOLO:g} 秒且另一人"
            f"声纹比标注的人高 ≥{SPEAKER_MARGIN:g} 则去掉该段）发送 AliMeeting 与 MagicData-RAMC test 整场录音，"
            "每条请求另按对照各发一次，每个对照只改一处："
            "基础（meeting-<语料>-<pos|neg>）：AliMeeting 远场通道 0、RAMC 原录音，注册取同一录音，没有可作注册的语句的人不建框"
            "（AliMeeting R8005_M8009 全部 4 人、R8004_M8006 3 人：按标注每句话都有人同时在说）；"
            "-xrec（目标缺席）：注册换成同语料另一场录音（test 或 dev，两划分说话人不重合）的人，选与段内最像的在场人的声纹相似度"
            "最接近原注册的那位，检验同一录音的注册是否被当成目标的证据；"
            "-enear（AliMeeting）：同一批注册语句改取本人头戴麦，段不变，注册不再带会议室远场声学；"
            "-near（AliMeeting）：注册取头戴麦，段为全部头戴麦之和（按远场 RMS 缩放，同 near_far.py），两边都是近讲；"
            f"-snr（AliMeeting）：段与注册都加同一条真实会议室底噪（meeting_room_noise@v2-20261014，训练划分的房间，≥{NOISE_MIN:g} 秒，"
            f"循环处交叉淡化），按会议时间对齐，每场一个增益，使该场段的中位信噪比为 {SNR_DB:g} dB（下游手机录音比底噪高 6–10 dB）；"
            f"注册用同一条底噪，必要时调轻到注册比底噪高 ≥{ENROLL_SNR_MIN:g} dB（下游服务只取信噪比 ≥6 dB 的注册片段）；"
            "-enear/-near 的头戴麦注册按远场注册的 RMS 缩放，只差声学不差音量。"
            "对照记录有 labels.control 和 metadata.base（基础记录的划分、录音、段号、目标人），可逐条配对；"
            "-enear/-near/-snr 的声纹相似度标签沿用基础记录（远场、无噪声）。RAMC 去掉含训练划分说话人的录音（test 9 人在 train 里）。"
            "meeting_quarantine.py 的文本核对需要每段的普通识别转写，在下一版做。只用于评测，不进训练。"
            "生成脚本 scripts/ts_real/meeting_controls.py，统计见 source/<版本>/report.json。"),
        "sources": [*sources, HEADSET_SOURCE, f"{NOISE[0]}@{NOISE[1]}:{NOISE[2]}"],
    }
    path = REPO / "catalog" / f"{DATASET_ID}.yaml"
    text = path.read_text()
    new_text = text + yaml.safe_dump([declaration], allow_unicode=True, sort_keys=False, width=512)
    validate_catalog([*load_catalog(REPO / "catalog"), DatasetSpec.from_dict(declaration)])
    path.write_text(new_text, encoding="utf-8")
    print("registered", VERSION, len(results), "records", flush=True)


if __name__ == "__main__":
    main()

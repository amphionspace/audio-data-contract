#!/usr/bin/env python3
"""Whole AISHELL-4 test meetings sent the way the speaker-enroll service sends them (ts_asr_real meeting-v1).

Downstream badcase ``tsasr-cross-speaker-output-20261116``: the service replays a meeting, enrolls every person once
from their own speech in that meeting, and sends each segment of the meeting to every enrolled person's box (one
request per segment and box: 5 s of enrollment, then the segment, as one clip). When the box's person does not
speak in the segment, AmphionASR still transcribed a similar-voiced person in the room 3.8% of the time (11.06,
12 meetings, 8787 such requests), and the same text appeared under two names. ``ts_asr_real`` v4 has 149 of these
requests for AISHELL-4 (one random absent speaker per window), too few to see which pairs of people fail. This
version sends every segment to every enrolled person of the meeting instead:

* segments: the human annotation's utterances of one speaker, merged while the next one starts within
  ``TURN_GAP`` s, no one else starts an utterance in between and the merged segment stays within ``MERGE_CAP`` s
  (a longer single utterance stays whole); kept from ``MIN_SEGMENT`` s. That matches the MOSS segments the
  downstream sent (median 6.7 vs. 6.6-7.0 s, 90th percentile 10.8 vs. 9.9-12.3 s). The audio is far-field
  channel 0 over the segment, with everyone else's speech in it as recorded;
* enrollment, per (meeting, speaker): their earliest utterance in the meeting that ``build.py`` allows as an
  enrollment (>= 3 s, others overlap <= 20% and < 0.3 s of the first 5 s), first 6 s of it, then their next
  utterances that nobody else talks in, in time order, up to 10 s stored (the client sends 5 s). It passes the
  voice check (``voice_check.py`` on channel 0); if not, their next allowed utterance is tried. Speakers without
  a passing enrollment get no box (as the downstream drops mixed enrollments);
* requests: a box gets the segments from the one before its person's first utterance on, except segments that
  overlap the enrollment's pieces (they would hold the enrollment itself). By the annotation, like the downstream:
  absent (``-neg``) when the person has no speech within the segment +- ``ABSENT_MARGIN`` s; present (``-pos``)
  when they talk >= ``PRESENT_MIN`` s in it and every utterance of theirs that the segment touches lies wholly
  inside it (the reference is their text); everything else is not sent (counted in the report).

Every request gets ``labels.impostor_sim`` (ECAPA cosine of the 5 s enrollment crop with the meeting profile of
the closest other speaker talking >= ``PRESENT_MIN`` s in the segment), ``impostor_speaker``, ``owner_sim`` (with
the segment's speaker when that is not the target) and ``enroll_own_sim`` (with the target's own profile);
``metadata.enroll_sims`` has the enrollment's cosine with every speaker of the meeting.

    python scripts/ts_real/meeting_segments.py --roots /workspace/data/registry/roots.json \\
        --embed-python /workspace/workspace/mingdong/miniconda3/envs/k2/bin/python
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import statistics
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import yaml

from audio_data_contract import AudioRecord, load_catalog
from audio_data_contract.catalog import validate_catalog
from audio_data_contract.types import DatasetSpec

HERE = Path(__file__).resolve().parent


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


real = _load("ts_real_build", "build.py")
voice = real._sibling("voice_check")
synth = real.synth
REPO = HERE.parents[1]
SR = real.SR
DATASET_ID = real.DATASET_ID
VERSION = "meeting-v1-20261117"
CORPUS = real.RECIPE["corpora"]["aishell4"]
SPLIT = "meeting-aishell4"
TURN_GAP = 1.0  # s between two utterances of one speaker merged into one segment
MERGE_CAP = 10.0  # s a merged segment may reach
MIN_SEGMENT = 1.0
ABSENT_MARGIN = 0.5  # the downstream's rule: no speech of the target within the segment +- 0.5 s
PRESENT_MIN = 0.5  # the downstream's rule: the target talks >= 0.5 s in the segment


def segments(entry, gap=TURN_GAP, cap=MERGE_CAP, min_seconds=MIN_SEGMENT):
    """[(start, end, speaker, [utterances])] of a recording, by start time (see the module docstring)."""
    by_speaker = defaultdict(list)
    for u in entry["sups"]:
        by_speaker[u[2]].append(u)
    out = []
    for speaker, own in by_speaker.items():
        current = None
        for u in sorted(own):
            if (current is not None and u[0] - current[1] <= gap and u[1] - current[0] <= cap
                    and not any(o[2] != speaker and current[1] < o[0] < u[0]
                                for o in real.overlapping(entry, current[1], u[0]))):
                current[1] = max(current[1], u[1])
                current[3].append(u)
            else:
                if current is not None:
                    out.append(current)
                current = [u[0], u[1], speaker, [u]]
        out.append(current)
    return sorted((s, e, spk, utts) for s, e, spk, utts in out if e - s >= min_seconds)


def talk(entry, speaker, lo, hi):
    return sum(max(0.0, min(hi, e) - max(lo, s)) for s, e, spk, _ in real.overlapping(entry, lo, hi) if spk == speaker)


def classify(entry, speaker, lo, hi):
    """("neg" | "pos" | "borderline" | "clipped", seconds the speaker talks in [lo, hi], their utterances in it)."""
    if talk(entry, speaker, lo - ABSENT_MARGIN, hi + ABSENT_MARGIN) == 0:
        return "neg", 0.0, []
    seconds = talk(entry, speaker, lo, hi)
    own = sorted(u for u in real.overlapping(entry, lo, hi) if u[2] == speaker)
    if seconds < PRESENT_MIN:
        return "borderline", seconds, own
    if any(u[0] < lo or u[1] > hi for u in own):
        return "clipped", seconds, own
    return "pos", seconds, own


def enrollment_pieces(entry, speaker, first):
    """``first``, then the speaker's next utterances (>= 1 s, nobody else annotated in them) up to ENROLL_STORE s."""
    pieces, have = [first], first[1] - first[0]
    for s, e, spk, _ in entry["sups"]:
        if have >= real.ENROLL_STORE:
            break
        if (spk == speaker and s >= first[1] and e - s >= real.ENROLL_PIECE_MIN
                and not any(o[2] != speaker for o in real.overlapping(entry, s, e))):
            pieces.append((s, e))
            have += e - s
    return pieces


def enroll(checker, recordings, rid, speaker):
    """(pieces, audio, verdict, tried) of the speaker's earliest enrollment that passes the voice check, or None."""
    entry = recordings[rid]
    for tried, (s, e, _) in enumerate(sorted(entry["eligible"].get(speaker, []))[: real.VOICE_ATTEMPTS], 1):
        pieces = enrollment_pieces(entry, speaker, (s, min(e, s + real.ENROLL_MAX)))
        verdict = checker.check(recordings, rid, speaker, pieces)
        if verdict["passed"]:
            return pieces, real.cut_pieces(recordings, rid, pieces), verdict, tried
    return None


def plan_requests(entry, segs, boxes):
    """[(segment index, speaker, kind, seconds, utterances)] of the boxes' requests and a Counter of the dropped ones.

    ``boxes``: {speaker: enrollment pieces}."""
    plans, dropped = [], Counter()
    for speaker, pieces in sorted(boxes.items()):
        first_talk = min(u[0] for u in entry["sups"] if u[2] == speaker)
        start = max(0, next((i for i, seg in enumerate(segs) if seg[1] > first_talk), len(segs)) - 1)
        for i, (lo, hi, _, _) in enumerate(segs):
            if i < start:
                dropped["before_first_talk"] += 1
                continue
            if any(s < hi and e > lo for s, e in pieces):
                dropped["holds_enrollment"] += 1
                continue
            kind, seconds, own = classify(entry, speaker, lo, hi)
            if kind in ("borderline", "clipped"):
                dropped[kind] += 1
                continue
            plans.append((i, speaker, kind, seconds, own))
    return plans, dropped


def overlap_seconds(utts, lo, hi):
    """Seconds of [lo, hi] in which at least two speakers talk."""
    events = sorted([(max(lo, s), 1) for s, e, *_ in utts if e > lo and s < hi]
                    + [(min(hi, e), -1) for s, e, *_ in utts if e > lo and s < hi])
    total, active, last = 0.0, 0, lo
    for t, step in events:
        if active >= 2:
            total += t - last
        active, last = active + step, t
    return total


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--roots", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, default=Path("/workspace/data/registry/catalog"))
    parser.add_argument("--embed-python", type=Path, required=True, help="Python with onnxruntime and torchaudio")
    parser.add_argument("--speaker-model", type=Path, default=Path(real.SPEAKER_MODEL))
    parser.add_argument("--recordings", nargs="*", help="only these meetings (smoke runs; implies --no-register)")
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
    recordings = real.load_corpus(CORPUS, catalog=load_catalog(args.catalog), roots=roots)
    if args.recordings:
        recordings = {r: recordings[r] for r in args.recordings}
    checker = voice.VoiceCheck(voice.Embedder(args.embed_python, args.speaker_model), real.check_cut, real.ENROLL_CROP,
                               real.ENROLL_STORE, real.check_view)
    crop = int(real.ENROLL_CROP * SR)
    results, index_rows = [], {}
    report = {"rule": {"turn_gap_s": TURN_GAP, "merge_cap_s": MERGE_CAP, "min_segment_s": MIN_SEGMENT,
                       "absent_margin_s": ABSENT_MARGIN, "present_min_s": PRESENT_MIN, "enroll_crop_s": real.ENROLL_CROP,
                       "enroll_store_s": real.ENROLL_STORE, "speaker_model": str(args.speaker_model)},
              "meetings": {}, "no_box": [], "dropped": Counter()}
    counters = Counter()
    for rid, entry in sorted(recordings.items()):
        segs = segments(entry)
        speakers = sorted({u[2] for u in entry["sups"]})
        boxes, enrollments = {}, {}
        for speaker in speakers:
            picked = enroll(checker, recordings, rid, speaker)
            if picked is None:
                report["no_box"].append({"recording": rid, "speaker": speaker,
                                         "eligible": len(entry["eligible"].get(speaker, []))})
                continue
            pieces, audio, verdict, tried = picked
            boxes[speaker] = pieces
            vector = checker.embed(audio[:crop])
            sims = {}
            for other in speakers:
                profile, _ = checker.profile(recordings, rid, other, pieces if other == speaker else ())
                if profile is not None:
                    sims[other] = round(float(vector @ profile), 3)
            cut_id = f"{SPLIT}-{rid}-{speaker}-enroll"
            enrollments[speaker] = {"entry": _write(partial, f"{SPLIT}-enroll", cut_id, audio), "pieces": pieces, "verdict": verdict, "tried": tried, "sims": sims,
                                    "others_s": real.pieces_others(entry, speaker, pieces)[0]}
        plans, dropped = plan_requests(entry, segs, boxes)
        report["dropped"].update(dropped)
        mixes = {}
        for i, speaker, kind, seconds, own in plans:
            lo, hi, owner, _ = segs[i]
            if i not in mixes:
                mix = real.cut(recordings, rid, lo, hi)
                if abs(len(mix) / SR - (hi - lo)) > 0.05:
                    raise ValueError(f"{rid}: the audio is shorter than its annotation at {lo:.2f}")
                inside = sorted(real.overlapping(entry, lo, hi))
                mixes[i] = {"entry": _write(partial, f"{SPLIT}-mix", f"{SPLIT}-{rid}-{i:04d}-mix", mix),
                            "rms": round(float(20 * np.log10(np.sqrt(np.mean(mix ** 2)) + 1e-9)), 2),
                            "utts": inside, "talk": {spk: round(sec, 3) for spk, sec in sorted(real.speaker_seconds(
                                [(max(lo, s), min(hi, e), spk, t) for s, e, spk, t in inside]).items())},
                            "overlap": round(overlap_seconds(inside, lo, hi), 3)}
            m, en = mixes[i], enrollments[speaker]
            present = kind == "pos"
            others = {spk: sec for spk, sec in m["talk"].items() if spk != speaker and sec >= PRESENT_MIN}
            impostor = max(others, key=lambda s: en["sims"].get(s, -1.0), default=None)
            split = f"{SPLIT}-{kind}"
            labels = {
                "scenario": split, "group": "meeting", "kind": kind, "target_present": present, "corpus": "aishell4",
                "recording": rid, "duration_s": round(hi - lo, 3), "window_start_s": round(lo, 3),
                "speakers_in_window": len(m["talk"]), "n_interferers": len(m["talk"]) - (1 if present else 0),
                "segment_speaker": owner, "target_is_segment_speaker": owner == speaker, "overlap_s": m["overlap"],
                "mixture_rms_dbfs": m["rms"], "annotation": "human", "enroll_seconds": round(en["entry"]["duration"], 3),
                "enroll_others_s": en["others_s"], "enroll_condition": "clean",
                "enroll_own_sim": en["sims"].get(speaker), "impostor_speaker": impostor,
                "impostor_sim": en["sims"].get(impostor) if impostor else None,
                "owner_sim": en["sims"].get(owner) if owner != speaker else None,
            }
            if present:
                labels.update(target_seconds=round(seconds, 3),
                              target_overlap_ratio=round(real.overlap_ratio(own, m["utts"]), 3))
            else:
                labels["absent_source"] = "same_recording"
            metadata = {
                "split": split, "target_speaker": f"aishell4:{speaker}", "segment_index": i,
                "enrollment": {"recording": rid, "start": round(en["pieces"][0][0], 3), "end": round(en["pieces"][0][1], 3)},
                "enrollment_pieces": [[round(s, 3), round(e, 3)] for s, e in en["pieces"]],
                "enroll_voice_check": en["verdict"], "enroll_attempts": en["tried"],
                "enroll_sims": {f"aishell4:{s}": v for s, v in en["sims"].items()},
                "talk": {f"aishell4:{s}": v for s, v in m["talk"].items()},
                "window_utts": [{"speaker": f"aishell4:{spk}", "start": round(max(s, lo) - lo, 3),
                                 "duration": round(min(e, hi) - max(s, lo), 3), "text": text,
                                 **({"clipped": True} if s < lo or e > hi else {})}
                                for s, e, spk, text in m["utts"]],
            }
            results.append({"split": split, "target": "".join(u[3] for u in own) if present else "",
                            "labels": labels, "metadata": metadata, "entries": [m["entry"], en["entry"]]})
            counters[(rid, kind)] += 1
        for row in [m["entry"] for m in mixes.values()] + [en["entry"] for en in enrollments.values()]:
            index_rows[row["cut_id"]] = row
        report["meetings"][rid] = {"segments": len(segs), "speakers": len(speakers), "boxes": len(boxes),
                                   "neg": counters[(rid, "neg")], "pos": counters[(rid, "pos")],
                                   "enroll_own_sim": {s: e["sims"].get(s) for s, e in sorted(enrollments.items())}}
        print(rid, report["meetings"][rid], dict(dropped), flush=True)
    checker.embed.close()

    def quantiles(values):
        values = [v for v in values if v is not None]
        return [round(v, 3) for v in statistics.quantiles(values, n=10)] if len(values) > 1 else values

    report["dropped"] = dict(report["dropped"])
    report["records"] = dict(Counter(r["split"] for r in results))
    report["deciles"] = {split: {k: quantiles([r["labels"].get(k) for r in results if r["split"] == split])
                                 for k in ("duration_s", "impostor_sim", "enroll_own_sim", "overlap_s", "target_seconds")}
                         for split in sorted(report["records"])}
    report["voice_check"] = {"/".join(map(str, k)): v for k, v in sorted(checker.stats.items())}
    partial.mkdir(parents=True, exist_ok=True)
    (partial / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, default=list) + "\n")
    print(json.dumps({k: report[k] for k in ("records", "dropped", "no_box")}, ensure_ascii=False, indent=1), flush=True)
    if args.recordings:  # smoke run: kept apart from the version's directory, not registered
        with (partial / "results.jsonl").open("w", encoding="utf-8") as stream:
            for r in results:
                stream.write(json.dumps(r, ensure_ascii=False) + "\n")
        smoke = data_root / "source" / (VERSION + ".smoke")
        shutil.rmtree(smoke, ignore_errors=True)
        partial.rename(smoke)
        print("smoke run written to", smoke, flush=True)
        return
    partial.rename(final)
    register(results, index_rows, data_root, args)


def _write(partial, folder, cut_id, w):
    relative = f"audio/{folder}/{cut_id}.wav"
    synth.write_wav(partial / relative, w)
    return {"cut_id": cut_id, "relative_path": relative, "num_frames": len(w), "duration": round(len(w) / SR, 4),
            "sha256": synth.sha256_file(partial / relative)}


def register(results, index_rows, data_root, args):
    """Records, audio index (one row per file; a segment's audio is shared by its requests) and catalog entry."""
    def rel(*parts):
        return "/".join(("versions", VERSION, *parts))

    by_split = defaultdict(list)
    for r in results:
        by_split[r["split"]].append(r)
    artifacts, split_decl = [], {}
    texts = {"pos": "目标在场（本人在这段里说话 ≥0.5 秒，且所说语句都完整落在段内）",
             "neg": "目标缺席（本人在这段前后 0.5 秒内都没有说话）"}
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
        split_decl[name] = {"artifacts": {"records": [f"{name}-records"], "audio_index": ["audio-index"]}, "task": "ts_asr",
                            "statistics": {"records": len(records), "duration_hours": round(seconds / 3600, 4),
                                           "duration_basis": "Mixture duration"},
                            "provenance": {"description": "AISHELL-4 test 20 场会议远场通道 0，按人工标注切的每一段发给会上每个注册人；"
                                                          + texts[name.rsplit("-", 1)[1]]}}
    rows = [{**e, "root_alias": DATASET_ID, "sample_rate": SR, "channels": 1,
             "relative_path": f"source/{VERSION}/{e['relative_path']}"} for e in index_rows.values()]
    synth.write_jsonl_gz(data_root / rel("audio-index.jsonl.gz"), sorted(rows, key=lambda e: e["cut_id"]))
    artifacts.insert(0, {"name": "audio-index", "kind": "audio-index", "root_alias": DATASET_ID,
                         "relative_path": rel("audio-index.jsonl.gz"),
                         "sha256": synth.sha256_file(data_root / rel("audio-index.jsonl.gz")),
                         "metadata": {"record_count": len(rows)}})
    declaration = {"schema_version": "dataset-catalog/2.0", "dataset_id": DATASET_ID, "version": VERSION, "languages": ["zh"],
                   "tasks": ["ts_asr"], "artifacts": artifacts, "splits": split_decl}
    declaration["provenance"] = {
        "summary": "目标说话人评测：AISHELL-4 整场会议逐段发送", "status": "complete",
        "synthetic": "none",
        "description": (
            "复现下游 speaker-enroll 回放会议时的发送方式（badcase tsasr-cross-speaker-output-20261116：目标人不在场时，"
            "11.06 在 3.8% 的请求里输出了同场声音相近的人的话）。AISHELL-4 test 全部 20 场会议、远场通道 0、人工标注，不做混合。"
            f"分段：同一人相邻语句间隔 ≤{TURN_GAP:g} 秒、中间没有别人开口、合并后不超过 {MERGE_CAP:g} 秒时并成一段（更长的单句保持完整），"
            f"保留 ≥{MIN_SEGMENT:g} 秒的段，段长分布与下游的 MOSS 分段相当。注册：每人一份，取本人在会上最早一条可作注册的语句"
            "（≥3 秒、他人重叠 ≤20%、前 5 秒他人说话 <0.3 秒）的前 6 秒，后接本人之后无人重叠的语句，按时间顺序存到 10 秒，客户端取前 5 秒；"
            "过声纹核对（通道 0 上与本人在会上其他语句的平均声纹比和其他人更像），不过的换下一条，都不过的人不建框。"
            "请求：每个框收到从本人第一次说话的前一段起的每一段，跳过与本人注册片段重叠的段。"
            f"目标缺席（-neg）：本人在段前后 {ABSENT_MARGIN:g} 秒内都没说话；目标在场（-pos）：本人在段内说话 ≥{PRESENT_MIN:g} 秒，"
            "且本人碰到这段的语句都完整在段内，参考文本为这些语句；其余不发送（统计见 source/<版本>/report.json）。"
            "同一段的音频由它的所有请求共用。labels.impostor_sim 为 5 秒注册与段内说话 ≥0.5 秒的其他人会上平均声纹（ECAPA）的最大余弦，"
            "impostor_speaker 为对应的人，owner_sim 为与这段的说话人的余弦，enroll_own_sim 为与本人的余弦；"
            "metadata.enroll_sims 为注册与会上每个人的余弦。只用于评测，不进训练。生成脚本 scripts/ts_real/meeting_segments.py。"),
        "sources": [f"{CORPUS['dataset']}@{CORPUS['version']}:{CORPUS['split']}"],
    }
    path = REPO / "catalog" / f"{DATASET_ID}.yaml"
    existing = list(yaml.safe_load(path.read_text()))
    validate_catalog([*load_catalog(REPO / "catalog"), DatasetSpec.from_dict(declaration)])
    path.write_text(yaml.safe_dump([*existing, declaration], allow_unicode=True, sort_keys=False, width=512), encoding="utf-8")
    print("registered", VERSION, len(results), "records", flush=True)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Crowded vs. clear target windows in real meetings (ts_asr_nearfar firstother-v3).

Follows the internally returned TS-ASR badcase (``first_speaker.py``). Mining the wrong-speaker outputs of four
releases on ``firstother-v2`` (output covers < 60% of the target text and > 40% of it is someone else's) showed that
the drivers are not who opens the window nor the enrollment chain, but how much the target is talked over, how little
they say and how weakly the enrollment matches them: 0% wrong speaker when the target is overlapped < 5% of the time
or talks > 20 s, 12% at overlap >= 0.3, 10% under 10 s of target speech, 21% at target_sim < 0.4, and 27-30% for
overlap >= 0.3 with target_sim < 0.5 (same for all four releases); other-first 6.2% vs. target-first 3.6%.

So this version samples by those conditions instead of by the opener:

* windows as in ``first_speaker_windows``'s closure (25-45 s of whole utterances, >= 3 speakers, target >= 5 s), with
  no requirement on the opening utterance; per (window, target) the stratum is ``crowded`` (target overlap ratio >= 0.3
  and target speech < 15 s) or ``control`` (overlap < 0.15 and target speech >= 20 s), others are not used;
* per stratum, items of the same target in a recording may share at most half of the shorter window (as recipe
  ``overlap`` of ``build.py``); different targets may use the same stretch. Items are taken alternately from the
  other-first and target-first queues, so ``labels.first_speaker`` is balanced where the data allows;
* ``control`` takes per (corpus, recording, speakers in window) at most as many items as ``crowded`` there.

Corpora: AliMeeting Test and Eval (far-field channel 0; ``ef``, ``en`` headset and ``ed`` degraded headset
enrollments as in v1) and AISHELL-4 test (far-field channel 0; ``ef`` only, it has no headsets). Pairs, enrollments,
voice check and the degradation follow v1; every record gets ``target_sim`` / ``impostor_sim`` / ``sim_margin`` /
``opener_sim`` as in v2 (``first_speaker_near.py``, scored on the far-field mixture). Positive crowded records with
``target_sim < LOWSIM`` are also listed in ``crowded-lowsim-<family>-<cell>-pos``.

    python scripts/ts_real/first_speaker_crowded.py --roots /workspace/data/registry/roots.json \\
        --embed-python /workspace/workspace/mingdong/miniconda3/envs/k2/bin/python
"""

from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import random
import shutil
import statistics
from collections import Counter, defaultdict
from pathlib import Path

import soundfile as sf
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


first = _load("ts_real_first_speaker", "first_speaker.py")
scores = _load("ts_real_first_speaker_near", "first_speaker_near.py")
real, voice, synth = first.real, first.voice, first.synth
REPO = HERE.parents[1]
SR = real.SR
DATASET_ID = first.DATASET_ID
VERSION = "firstother-v3-20261105"
SEED = 20261105
ALI = Path("/workspace/data/datasets/alimeeting/source/openslr-119-local-20260826")
ALIMEETING = real.RECIPE["corpora"]["alimeeting"]
CORPORA = {  # name: (family, corpus spec, headset directory or None)
    "alimeeting": ("alimeeting", ALIMEETING, ALI / "Test_Ali/Test_Ali_near/audio_dir"),
    "alimeeting_eval": ("alimeeting", {**ALIMEETING, "split": "dev"}, ALI / "Eval_Ali/Eval_Ali_near/audio_dir"),
    "aishell4": ("aishell4", real.RECIPE["corpora"]["aishell4"], None),
}
CELLS = {"ef-mf": ("far", False), "en-mf": ("near", False), "ed-mf": ("near", True)}
# Strata of a (window, target): (overlap ratio range, target seconds range), lower bound inclusive.
STRATA = {"crowded": ((0.3, 1.01), (first.MIN_TARGET_SECONDS, 15.0)), "control": ((0.0, 0.15), (20.0, 1e9))}
MAX_SHARED = 0.5  # share of the shorter window two items of one target may have in common
LOWSIM = 0.5
LOWSIM_SPLIT = "crowded-lowsim"


def stratum_of(ratio, seconds):
    return next((name for name, ((olo, ohi), (slo, shi)) in STRATA.items()
                 if olo <= ratio < ohi and slo <= seconds < shi), None)


def stratified_items(entry, rng, span=first.WINDOW_SPAN, window_range=first.WINDOW_RANGE,
                     min_speakers=first.MIN_SPEAKERS, enrollable=None):
    """Candidate (window, target) items of one recording with their stratum; windows overlap each other."""
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
        opener = utts[0][2]
        for target, seconds in sorted(present.items()):
            ratio = real.overlap_ratio([u for u in utts if u[2] == target], utts)
            stratum = stratum_of(ratio, seconds)
            if stratum is None or not enrollable(target, lo, hi):
                continue
            out.append({"lo": lo, "hi": hi, "utts": utts, "present": present, "speakers": len(present),
                        "target": target, "opener": opener, "overlap": ratio, "stratum": stratum,
                        "first_speaker": "target" if opener == target else "other"})
    return out


def select_items(items, rng):
    """Per stratum: items of one target share at most MAX_SHARED of a window, alternating other/target first;
    control capped per (corpus, recording, speakers) at the crowded count."""
    chosen = {}
    for stratum in STRATA:
        queues = {k: [i for i in items if i["stratum"] == stratum and i["first_speaker"] == k] for k in ("other", "target")}
        for q in queues.values():
            rng.shuffle(q)
        taken, picked, turn = defaultdict(list), [], "other"
        cap = (Counter((i["corpus"], i["recording"], i["speakers"]) for i in chosen["crowded"])
               if stratum == "control" else None)
        while any(queues.values()):
            if not queues[turn]:
                turn = "target" if turn == "other" else "other"
            item = queues[turn].pop()
            key = (item["corpus"], item["recording"], item["speakers"])
            spans = taken[(item["corpus"], item["recording"], item["target"])]
            if any(min(item["hi"], b) - max(item["lo"], a) > MAX_SHARED * min(item["hi"] - item["lo"], b - a)
                   for a, b in spans) or (cap is not None and cap[key] <= 0):
                continue
            spans.append((item["lo"], item["hi"]))
            if cap is not None:
                cap[key] -= 1
            picked.append(item)
            turn = "target" if turn == "other" else "other"
        chosen[stratum] = sorted(picked, key=lambda i: (i["corpus"], i["recording"], i["lo"], i["target"]))
    return chosen


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--roots", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, default=Path("/workspace/data/registry/catalog"))
    parser.add_argument("--embed-python", type=Path, required=True, help="Python with onnxruntime and torchaudio")
    parser.add_argument("--speaker-model", type=Path, default=Path(real.SPEAKER_MODEL))
    parser.add_argument("--limit", type=int, help="items per stratum (smoke runs)")
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
    recordings, items = {}, []
    for name, (_, spec, near_dir) in CORPORA.items():
        recs = real.load_corpus(spec, catalog, roots)
        if near_dir is not None:  # voice check on the sum of the headsets (build.check_cut)
            for rid, entry in recs.items():
                entry["close_talk"] = [str(p) for p in sorted(near_dir.glob(f"{rid}_N_SPK*.wav"))]
                if not entry["close_talk"]:
                    raise FileNotFoundError(f"{rid}: no headset recordings in {near_dir}")
        recordings[name] = recs
        for rid, entry in sorted(recs.items()):
            for item in stratified_items(entry, random.Random(f"{SEED}:{name}:{rid}:windows")):
                items.append({**item, "corpus": name, "recording": rid})
    chosen = select_items(items, random.Random(f"{SEED}:select"))
    checker = voice.VoiceCheck(voice.Embedder(args.embed_python, args.speaker_model), real.check_cut, real.ENROLL_CROP,
                               real.ENROLL_STORE, real.check_view)
    noise_files = first.steady_noise_files()
    crop = int(real.ENROLL_CROP * SR)
    report = {"candidates": dict(Counter(f"{i['corpus']}/{i['stratum']}" for i in items)),
              "selected": dict(Counter(f"{i['corpus']}/{i['stratum']}" for s in chosen.values() for i in s)),
              "quarantined": [], "degraded_voice_check": Counter()}
    results, counts, indexes = [], Counter(), Counter()
    for stratum, picked in chosen.items():
        if args.limit:
            picked = picked[: args.limit]
        for number, item in enumerate(picked):
            name, rid = item["corpus"], item["recording"]
            family, spec, near_dir = CORPORA[name]
            recs = recordings[name]
            rng = random.Random(f"{SEED}:{stratum}:{name}:{rid}:{item['lo']:.2f}:{item['target']}")
            where = {"stratum": stratum, "corpus": name, "recording": rid, "start_s": round(item["lo"], 3),
                     "duration_s": round(item["hi"] - item["lo"], 3), "target": item["target"]}
            absent = real.pick_absent(item, recs, rng)
            cells = CELLS if near_dir is not None else {"ef-mf": CELLS["ef-mf"]}
            missing = (["absent"] if absent is None else [
                f"{r}:{s}" for r, s in ((rid, item["target"]), absent[:2])
                if near_dir is not None and not (near_dir / f"{r}_N_SPK{s}.wav").exists()])
            if missing:
                report["quarantined"].append({**where, "reason": "no_headset_or_absent", "missing": missing})
                continue
            index = indexes[(stratum, family)]
            plan = {"window": item, "target": item["target"], "absent": absent}
            scratch = partial / "_render"
            rendered = real.render(plan, name, spec, recs, rng, scratch, f"{stratum}-{family}-ef-mf", index, checker)
            if len(rendered) != 2:  # an enrollment failed the voice check with every alternative: drop the pair
                report["quarantined"].append({**where, "reason": "enroll_voice_check",
                                              "kept": [r["labels"]["kind"] for r in rendered]})
                shutil.rmtree(scratch, ignore_errors=True)
                continue
            mix = sf.read(scratch / rendered[0]["entries"][0]["relative_path"], dtype="float32")[0]
            # One mixture file per item, shared by its cells and by the positive and the negative.
            mix_entry = first.write_entry(partial, f"{stratum}-{family}-mix", f"{stratum}-{family}-{index:04d}-mix", mix)
            vectors = scores.speaker_vectors(checker.embed, mix, rendered[0]["metadata"]["window_utts"])
            for result in rendered:
                pk = result["labels"]["kind"]
                meta, labels = result["metadata"], result["labels"]
                speaker = meta["target_speaker"].split(":", 1)[1]
                pieces = [tuple(p) for p in meta["enrollment_pieces"]]
                enrolls = {"far": sf.read(scratch / result["entries"][1]["relative_path"], dtype="float32")[0]}
                spec_degrade = None
                if near_dir is not None:
                    enrolls["near"] = first.near_enrollment(meta["enrollment"]["recording"], speaker, pieces, near_dir)
                    spec_degrade = first.plan_degradation(
                        random.Random(f"{SEED}:{stratum}:{family}:{index:04d}:{pk}:degrade"), noise_files)
                    enrolls["degraded"] = first.degrade(enrolls["near"], spec_degrade)
                    degraded_check = checker.check(recs, meta["enrollment"]["recording"], speaker, pieces,
                                                   enrolls["degraded"])
                    report["degraded_voice_check"][
                        f"{stratum}/{pk}/{'passed' if degraded_check['passed'] else 'failed'}"] += 1
                suffix = "" if labels["enroll_condition"] == "clean" else real.ENROLLMIX
                for cell, (domain, degraded) in cells.items():
                    split = f"{stratum}-{family}-{cell}-{pk}{suffix}"
                    base = f"{stratum}-{family}-{cell}-{index:04d}-{pk}"
                    enroll = enrolls["degraded"] if degraded else enrolls[domain]
                    sims, per_speaker = scores.similarity_labels(
                        checker.embed(enroll[:crop]), vectors, meta["target_speaker"], f"{name}:{item['opener']}", pk == "pos")
                    out = copy.deepcopy(result)
                    out["split"] = split
                    out["entries"] = [mix_entry,
                                      first.write_entry(partial, split, f"{base}-enroll", enroll)]
                    out["labels"].update(scenario=split, group="firstother", stratum=stratum, family=family, cell=cell,
                                         enroll_domain=domain, enroll_degraded=degraded, mix_domain="far",
                                         window_id=f"{stratum}-{family}:{index:04d}", enroll_seconds=round(len(enroll) / SR, 3),
                                         first_speaker=item["first_speaker"], opener_speaker=item["opener"],
                                         **sims)
                    out["metadata"].update(split=split, speaker_sims=per_speaker)
                    if degraded:
                        out["metadata"].update(enroll_degradation=spec_degrade, enroll_degraded_voice_check=degraded_check)
                    results.append(out)
                    counts[split] += 1
                    if (stratum == "crowded" and pk == "pos" and sims["target_sim"] is not None
                            and sims["target_sim"] < LOWSIM):
                        low = copy.deepcopy(out)
                        low["split"] = f"{LOWSIM_SPLIT}-{family}-{cell}-pos{suffix}"
                        low["labels"]["scenario"] = low["metadata"]["split"] = low["split"]
                        results.append(low)
                        counts[low["split"]] += 1
            shutil.rmtree(scratch)
            indexes[(stratum, family)] += 1
            if number % 50 == 0:
                print(stratum, number, len(picked), flush=True)
    checker.embed.close()

    def median(values):
        values = [v for v in values if v is not None]
        return round(statistics.median(values), 3) if values else None

    report["records"] = dict(sorted(counts.items()))
    report["medians"] = {split: {k: median([r["labels"].get(k) for r in results if r["split"] == split])
                                 for k in ("target_sim", "impostor_sim", "sim_margin", "target_overlap_ratio",
                                           "target_seconds", "duration_s")}
                         for split in sorted(counts)}
    report["first_speaker"] = {split: dict(Counter(r["labels"]["first_speaker"] for r in results if r["split"] == split))
                               for split in sorted(counts) if split.endswith("-pos")}
    report["degraded_voice_check"] = dict(sorted(report["degraded_voice_check"].items()))
    report["voice_check"] = {"/".join(k): v for k, v in sorted(checker.stats.items())}
    report["voice_check_dropped"] = checker.events
    partial.mkdir(parents=True, exist_ok=True)
    (partial / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, default=list) + "\n")
    print(json.dumps({k: report[k] for k in ("selected", "records", "degraded_voice_check")}, ensure_ascii=False, indent=1),
          "\nquarantined:", Counter(q["reason"] for q in report["quarantined"]), flush=True)
    partial.rename(final)
    register(results, data_root, args)


def _register(by_split, index_rows, data_root):
    """Records, audio index and catalog entry (``ts_benchmark/build.py register`` with one index row per cut)."""
    def rel(*parts):
        return "/".join(("versions", VERSION, *parts))

    artifacts, split_decl = [], {}
    for name in sorted(by_split, key=lambda n: (n.removesuffix(real.ENROLLMIX), n.endswith(real.ENROLLMIX))):
        records = []
        for r in sorted(by_split[name], key=lambda r: r["index"]):
            mix, enroll = r["entries"]

            def ref(e, split_name=name):
                return {"dataset_id": DATASET_ID, "version": VERSION, "split": split_name, "cut_id": e["cut_id"],
                        "duration": e["duration"]}

            records.append(AudioRecord.from_dict({
                "schema_version": "audio-record/1.0", "id": f"{name}:{r['index']:04d}", "task": "ts_asr",
                "audio_slots": [{"name": "enrollment", "purpose": "enrollment", "ref": ref(enroll)},
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
                            "provenance": {"description": ""}}
    synth.write_jsonl_gz(data_root / rel("audio-index.jsonl.gz"), sorted(index_rows.values(), key=lambda e: e["cut_id"]))
    artifacts.insert(0, {"name": "audio-index", "kind": "audio-index", "root_alias": DATASET_ID,
                         "relative_path": rel("audio-index.jsonl.gz"),
                         "sha256": synth.sha256_file(data_root / rel("audio-index.jsonl.gz")),
                         "metadata": {"record_count": len(index_rows)}})
    return {"schema_version": "dataset-catalog/2.0", "dataset_id": DATASET_ID, "version": VERSION, "languages": ["zh"],
            "tasks": ["ts_asr"], "artifacts": artifacts, "splits": split_decl}


def register(results, data_root, args):
    """Like ``ts_benchmark/build.py register``, but the crowded-lowsim subsets share the audio of their source records."""
    by_split = defaultdict(list)
    for r in results:
        by_split[r["split"]].append(r)
    index_rows = {}
    for r in results:
        for entry in r["entries"]:
            index_rows[entry["cut_id"]] = {**entry, "root_alias": DATASET_ID, "sample_rate": SR, "channels": 1,
                                           "relative_path": f"source/{VERSION}/{entry['relative_path']}"}
    declaration = _register(by_split, index_rows, data_root)
    texts = {"crowded": "拥挤：目标语音被他人重叠 ≥30%、目标说话 <15 秒", "control": "对照：目标被重叠 <15%、目标说话 ≥20 秒",
             LOWSIM_SPLIT: "拥挤且注册与目标独自说话的 ECAPA 相似度 <0.5（拥挤划分的子集）"}
    cells = {"ef-mf": "注册取远场通道 0", "en-mf": "注册取本人头戴麦（跨通道）", "ed-mf": "注册取本人头戴麦并加噪、限带（劣化注册）"}
    for name, split in declaration["splits"].items():
        stratum = LOWSIM_SPLIT if name.startswith(LOWSIM_SPLIT) else name.split("-")[0]
        rest = name.removeprefix(stratum + "-").split("-")
        family, cell, pk = rest[0], f"{rest[1]}-{rest[2]}", rest[3]
        split["provenance"]["description"] = (
            f"{'AliMeeting Test/Eval' if family == 'alimeeting' else 'AISHELL-4 test'} 远场通道 0 的 25–45 秒窗口；"
            f"{texts[stratum]}；{cells[cell]}；{'目标在场' if pk == 'pos' else '目标缺席'}"
            + (f"；注册前 {real.ENROLL_CROP:g} 秒里他人说话不少于 {real.ENROLL_CROP_OTHERS_MAX} 秒" if name.endswith(real.ENROLLMIX) else ""))
    declaration["provenance"] = {
        "summary": "目标说话人评测：AliMeeting 近远场对照与谁先开口对照", "status": "complete", "synthetic": "partial",
        "description": (
            "复现内部返回的 TS-ASR badcase（模型整段转写了另一个说话人）的拥挤窗口版。对 firstother-v2 四个版本的错人输出"
            "（输出覆盖目标文本不到 60%、40% 以上不是目标说的）挖掘显示，主因不是谁先开口或注册链路，而是目标被重叠多、说得少、"
            "注册与目标匹配弱：目标被重叠 <5% 或说话 >20 秒时错人 0%，重叠 ≥0.3 时 12%，目标说话 <10 秒时 10%，target_sim <0.4 时 21%，"
            "重叠 ≥0.3 且 target_sim <0.5 时 27–30%（四个版本一致）；非目标先开口 6.2%、目标先开口 3.6%。"
            "本版按这些条件取样：AliMeeting Test 与 Eval、AISHELL-4 test 远场通道 0 的人工标注，按完整语句切 25–45 秒窗口（≥3 人、"
            "目标 ≥5 秒，不再要求开头有清晰的一句），每个（窗口，目标）分层：crowded 为目标被重叠 ≥30% 且说话 <15 秒，control 为"
            "重叠 <15% 且说话 ≥20 秒；同一目标在同一录音里的样本窗口重合不超过较短者的一半（不同目标可以用同一段），"
            "非目标先开口与目标先开口交替取以求均衡（labels.first_speaker），control 每个（语料，会议，人数）不超过 crowded 的个数。"
            "每个样本一对：目标在场，和目标缺席（同会议不在窗口里的人，没有则取同语料其他会议，labels.absent_source）。"
            "注册、声纹核对、-enrollmix 与 ed 劣化同 firstother-v1；AliMeeting 有 ef、en、ed 三种注册，AISHELL-4 没有头戴麦只有 ef，混合都是远场通道 0。"
            "每条有 labels.target_sim / impostor_sim / sim_margin / opener_sim（同 v2，在远场混合上算）和 target_overlap_ratio、target_seconds；"
            f"crowded 正样本中 target_sim <{LOWSIM} 的另列为 crowded-lowsim-<语料>-<注册>-pos（子集）。"
            "AliMeeting Eval（icefall dev）只在部分训练里作验证集，没有进训练数据。统计见 source/<版本>/report.json。"
            "生成脚本 scripts/ts_real/first_speaker_crowded.py。只用于评测，不进训练。"),
        "sources": [f"{s['dataset']}@{s['version']}:{s['split']}" for _, s, _ in CORPORA.values()]
                   + ["alimeeting:Test_Ali_near", "alimeeting:Eval_Ali_near", f"ts_asr_benchmark/source/v4-20261022/noise/{first.NOISE_POOL}"],
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

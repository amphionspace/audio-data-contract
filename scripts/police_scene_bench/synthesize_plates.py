#!/usr/bin/env python3
"""Synthesize plate readings the police data lacks, for police_scene_bench (test only).

The registered police synthetic data reads ordinary car plates of a few provinces only. This
adds three kinds, each in a short police sentence read by one of the test accent speakers:

* ordinary plates of all 31 provinces (province + city letter + 5 characters);
* new-energy plates (8 characters: D/F first for small cars, last for large ones);
* electric-bike plates. Their formats differ between cities and no national format exists; the
  ones used here (city name + letter + 5 digits, or province + city letter + 6 digits) are
  approximations and are marked so.

Stages (run in order; ``tts`` needs the qwen-tts environment, ``asr`` one with qwen-asr, both a GPU):

    jobs    texts and speakers (seeded)
    tts     Qwen3-TTS 1.7B Base voice cloning from the speaker's reference
    asr     transcribe every take with Qwen3-ASR 1.7B (offline, no server)
    qc      keep a take only when the transcript contains the exact plate and the sentence
            otherwise matches (character error rate after mapping spoken digits <= 0.3)
    export  Lhotse recordings/supervisions of the kept takes

    python scripts/police_scene_bench/synthesize_plates.py jobs
    CUDA_VISIBLE_DEVICES=6 /path/to/qwen-tts/bin/python scripts/police_scene_bench/synthesize_plates.py tts
    CUDA_VISIBLE_DEVICES=6 /path/to/env-with-qwen-asr/bin/python scripts/police_scene_bench/synthesize_plates.py asr
    python scripts/police_scene_bench/synthesize_plates.py qc export
"""

from __future__ import annotations

import argparse
import gzip
import json
import random
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

RUN = Path("/workspace/data/datasets/police_scene_bench/tts/plates-20261028")
# 48 test accent speakers of the police reference split, with prompt texts re-transcribed by Qwen3-ASR
REFERENCES = Path("/workspace/workspace/mingdong/data/amphiondata/police-terms-single-20261022/references/references.jsonl")
EXCLUDED_SPEAKERS = {  # same exclusions as the police terms single set: unstable clones and Cantonese references
    "wenetspeech-wu:223327123748_MfrAo", "wenetspeech-chuan:cq00005305", "kespeech:1025593",
    "wenetspeech-wu:223327126399_FbqAg", "wenetspeech-chuan:cq00007784", "wenetspeech-chuan:cq00005155",
    "wenetspeech-yue:034-红楼梦034_converted_SPEAKER_00", "wenetspeech-yue:08-五_converted_SPEAKER_00",
    "wenetspeech-yue:096-西西里岛战役_converted_SPEAKER_00", "wenetspeech-yue:gd0029497_SPEAKER_06",
    "wenetspeech-yue:gd0048624_SPEAKER_00", "wenetspeech-yue:gd0052975_SPEAKER_03",
}
MODEL = "/workspace/model/Qwen3-TTS-12Hz-1.7B-Base"
ASR_MODEL = "/workspace/model/Qwen3-ASR-1.7B"
SEED = 20261028
PROVINCES = "京津冀晋蒙辽吉黑沪苏浙皖闽赣鲁豫鄂湘粤桂琼渝川贵云藏陕甘青宁新"
LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ"  # plates skip I and O
EBIKE_CITIES = ["杭州", "宁波", "温州", "苏州", "南京", "无锡", "广州", "深圳", "成都", "郑州", "武汉", "长沙",
                "合肥", "济南", "西安", "昆明", "南宁", "福州", "南昌", "石家庄"]
COUNTS = {"普通车牌": 5, "新能源车牌": 5}  # per province
EBIKE_COUNT = 160
TEMPLATES = {
    "普通车牌": ["帮我核查一下车牌号{p}", "前面那辆{p}，靠边停车", "涉案车辆号牌{p}，登记扣押", "查一下{p}的车主信息",
              "{p}这辆车有没有违章记录", "肇事车辆号牌是{p}，往东边跑了", "车牌{p}，跟我们回所里做个笔录"],
    "新能源车牌": ["新能源车{p}，核查一下车主", "这辆绿牌车{p}登记一下", "查一下新能源车牌{p}的通行记录",
               "事故一方是新能源车，号牌{p}", "涉案车辆是辆电车，牌照{p}"],
    "电动车号牌": ["电动车号牌{p}，登记一下", "这辆电动车备案号牌是{p}", "核查电动车防盗号牌{p}",
               "查获一辆电动自行车，号牌{p}", "电动车牌照{p}，车主联系不上"],
}
# spoken digits: plain, radio style (幺两拐洞), or the common mix (幺 for 1 only)
STYLES = {"plain": "零一二三四五六七八九", "radio": "洞幺两三四五六拐八九", "mixed": "零幺二三四五六七八九"}
SPOKEN_DIGITS = {c: str(i) for style in STYLES.values() for i, c in enumerate(style)} | {"〇": "0"}


def read_jsonl(path):
    with open(path, encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "wt", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")


# --- plates ------------------------------------------------------------------------------


def ordinary(rng, province):
    tail = [rng.choice("0123456789") for _ in range(5)]
    for i in rng.sample(range(5), rng.choice([0, 0, 1, 2])):  # up to two letters among the five
        tail[i] = rng.choice(LETTERS)
    return province + rng.choice(LETTERS) + "".join(tail)


def new_energy(rng, province):
    city = rng.choice(LETTERS)
    if rng.random() < 0.75:  # small car: D/F, a letter or digit, four digits
        body = rng.choice("DF") + rng.choice(LETTERS + "0123456789") + "".join(rng.choice("0123456789") for _ in range(4))
    else:  # large car: five digits, then D/F
        body = "".join(rng.choice("0123456789") for _ in range(5)) + rng.choice("DF")
    return province + city + body


def ebike(rng):
    if rng.random() < 0.5:
        return rng.choice(EBIKE_CITIES) + rng.choice(LETTERS) + "".join(rng.choice("0123456789") for _ in range(5)), "城市名+字母+5位数字"
    return (rng.choice(PROVINCES) + rng.choice(LETTERS) + "".join(rng.choice("0123456789") for _ in range(6)),
            "省简称+城市字母+6位数字")


def spoken(plate, style):
    return "".join(STYLES[style][int(c)] if c.isdigit() else c for c in plate)


def make_jobs():
    rng = random.Random(SEED)
    speakers = sorted(r["speaker_id"] for r in read_jsonl(REFERENCES) if r["speaker_id"] not in EXCLUDED_SPEAKERS)
    items = []
    for province in PROVINCES:
        for kind, count in COUNTS.items():
            for _ in range(count):
                items.append((kind, (ordinary if kind == "普通车牌" else new_energy)(rng, province), None))
    for _ in range(EBIKE_COUNT):
        plate, fmt = ebike(rng)
        items.append(("电动车号牌", plate, fmt))
    seen, jobs = set(), []
    for index, (kind, plate, fmt) in enumerate(items):
        if plate in seen:
            continue
        seen.add(plate)
        style = rng.choice(["plain", "radio", "mixed", "mixed"])
        text = rng.choice(TEMPLATES[kind]).format(p=spoken(plate, style))
        job_id = f"plate-{index:04d}"
        jobs.append({"id": job_id, "kind": kind, "plate": plate, "format": fmt, "digit_style": style, "text": text,
                     "tts_text": text, "speaker_id": speakers[index % len(speakers)],
                     "output_path": str(RUN / "audio" / f"{job_id}.wav")})
    write_jsonl(RUN / "jobs.jsonl", jobs)
    return {"jobs": len(jobs), "speakers": len(speakers), "kinds": Counter(j["kind"] for j in jobs)}


# --- synthesis and checks ------------------------------------------------------------------


def token_cap(text):
    """Same max_new_tokens as the police TTS workers, so short texts cannot run on."""
    return min(360, max(64, len(text) * 5))


def synthesize(batch_size):
    import numpy as np
    import soundfile as sf
    import torch
    from qwen_tts import Qwen3TTSModel
    from scipy.signal import resample_poly

    jobs = [j for j in read_jsonl(RUN / "jobs.jsonl") if not Path(j["output_path"]).exists()]
    model = Qwen3TTSModel.from_pretrained(MODEL, device_map="cuda:0", dtype=torch.bfloat16)
    references = {r["speaker_id"]: r for r in read_jsonl(REFERENCES)}
    by_speaker = defaultdict(list)
    for job in jobs:
        by_speaker[job["speaker_id"]].append(job)
    done = 0
    for speaker_id, items in sorted(by_speaker.items()):
        reference = references[speaker_id]
        prompt = model.create_voice_clone_prompt(ref_audio=reference["path"], ref_text=reference["prompt_text"])
        for start in range(0, len(items), batch_size):
            batch = items[start:start + batch_size]
            texts = [j["tts_text"] for j in batch]
            waves, rate = model.generate_voice_clone(text=texts, language=["Chinese"] * len(batch),
                                                     voice_clone_prompt=prompt * len(batch),
                                                     max_new_tokens=max(map(token_cap, texts)))
            for job, wave in zip(batch, waves):
                audio = resample_poly(np.asarray(wave, dtype=np.float32), 16000, rate)
                path = Path(job["output_path"])
                path.parent.mkdir(parents=True, exist_ok=True)
                sf.write(path.with_suffix(".tmp.wav"), audio, 16000, subtype="PCM_16")
                path.with_suffix(".tmp.wav").rename(path)
            done += len(batch)
        print(json.dumps({"speaker": speaker_id, "done": done, "total": len(jobs)}), flush=True)
    return {"synthesized": done}


def transcribe(batch_size):
    import torch
    from qwen_asr import Qwen3ASRModel

    jobs = [j for j in read_jsonl(RUN / "jobs.jsonl") if Path(j["output_path"]).exists()]
    model = Qwen3ASRModel.from_pretrained(ASR_MODEL, dtype=torch.bfloat16, device_map="cuda:0",
                                          max_inference_batch_size=batch_size, max_new_tokens=256)
    results = []
    for start in range(0, len(jobs), batch_size):
        batch = jobs[start:start + batch_size]
        outputs = model.transcribe(audio=[j["output_path"] for j in batch], language="Chinese")
        results += [{"id": j["id"], "hypothesis": o.text.strip()} for j, o in zip(batch, outputs)]
    write_jsonl(RUN / "asr.jsonl", results)
    return {"transcribed": len(results)}


def normalize(text):
    """NFKC, upper case, spoken digits to digits, only CJK letters and alphanumerics kept."""
    text = unicodedata.normalize("NFKC", text).upper()
    text = "".join(SPOKEN_DIGITS.get(c, c) for c in text)
    return re.sub(r"[^0-9A-Z一-鿿]", "", text)


def cer(reference, hypothesis):
    previous = list(range(len(hypothesis) + 1))
    for i, r in enumerate(reference, 1):
        current = [i]
        for j, h in enumerate(hypothesis, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (r != h)))
        previous = current
    return previous[-1] / max(len(reference), 1)


def check():
    asr = {r["id"]: r for r in read_jsonl(RUN / "asr.jsonl")}
    rows = []
    for job in read_jsonl(RUN / "jobs.jsonl"):
        result = asr.get(job["id"], {})
        hypothesis = result.get("hypothesis")
        row = {"id": job["id"], "hypothesis": hypothesis}
        if hypothesis is None:
            row.update(passed=False, reason=result.get("error", "not transcribed"))
        else:
            got, want = normalize(hypothesis), normalize(job["text"])
            row["cer"] = round(cer(want, got), 4)
            row["plate_found"] = job["plate"] in got
            row["passed"] = row["plate_found"] and row["cer"] <= 0.3
            row["reason"] = "" if row["passed"] else ("plate" if not row["plate_found"] else "cer")
        rows.append(row)
    write_jsonl(RUN / "qc.jsonl", rows)
    by_kind = Counter()
    jobs = {j["id"]: j for j in read_jsonl(RUN / "jobs.jsonl")}
    for row in rows:
        by_kind[(jobs[row["id"]]["kind"], row["passed"])] += 1
    return {"passed": sum(r["passed"] for r in rows), "total": len(rows),
            "by_kind": {f"{k}:{p}": v for (k, p), v in sorted(by_kind.items())}}


def export():
    import soundfile as sf

    references = {r["speaker_id"]: r for r in read_jsonl(REFERENCES)}
    passed = {r["id"] for r in read_jsonl(RUN / "qc.jsonl") if r["passed"]}
    recordings, supervisions = [], []
    for job in read_jsonl(RUN / "jobs.jsonl"):
        if job["id"] not in passed:
            continue
        info = sf.info(job["output_path"])
        reference = references[job["speaker_id"]]
        recordings.append({"id": job["id"], "sources": [{"type": "file", "channels": [0], "source": job["output_path"]}],
                           "sampling_rate": 16000, "num_samples": info.frames, "duration": round(info.duration, 4),
                           "channel_ids": [0]})
        supervisions.append({"id": job["id"], "recording_id": job["id"], "start": 0.0, "duration": round(info.duration, 4),
                             "channel": 0, "text": job["text"], "language": "zh", "speaker": job["speaker_id"],
                             "custom": {"synthetic": True, "tts_provider": "qwen3_tts", "accent": reference.get("accent"),
                                        "gender": reference.get("gender"), "speech_profile": "concise_command",
                                        "target_terms": [], "plate": job["plate"], "plate_format": job["format"],
                                        "digit_style": job["digit_style"],
                                        "source_metadata": {"category": job["kind"]}}})
    write_jsonl(RUN / "manifests" / "recordings.jsonl.gz", recordings)
    write_jsonl(RUN / "manifests" / "supervisions.jsonl.gz", supervisions)
    return {"exported": len(supervisions), "kinds": Counter(s["custom"]["source_metadata"]["category"] for s in supervisions)}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("stages", nargs="+", choices=["jobs", "tts", "asr", "qc", "export"])
    parser.add_argument("--batch-size", type=int, default=16)
    args = parser.parse_args()
    for stage in args.stages:
        result = {"jobs": make_jobs, "tts": lambda: synthesize(args.batch_size),
                  "asr": lambda: transcribe(args.batch_size), "qc": check, "export": export}[stage]()
        print(json.dumps({stage: result}, ensure_ascii=False, default=dict), flush=True)


if __name__ == "__main__":
    main()

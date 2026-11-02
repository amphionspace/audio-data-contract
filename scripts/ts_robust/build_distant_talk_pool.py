#!/usr/bin/env python3
"""Render real conversations as distant background talkers, for the plain-ASR "no text for background talk" target.

Plain-ASR training has empty targets only for noise, music and 16-24-talker babble. Nothing teaches that a real
conversation at the far side of a room transcribes as nothing, and models trained that way write text on it. This renders
that case: windows of a real near-field conversation, sometimes two conversations at once, each conversation at its own
position in one simulated room, then dulled above a few kHz and laid on real meeting-room noise at a low SNR.

A room response and a level alone leave the clips intelligible: on a first pilot (2000 clips at frame p95 -38 to -18 dBFS
on a -65 to -45 dBFS floor) base Qwen3-ASR and FireRed never both returned empty, and level made no difference. Against
recordings of real distant office talk those clips had too much dynamic range (p95 - p5 21.7 dB against 14.8) and too
much energy above 4 kHz (-15.6 dB against -26.5, relative to 200-1000 Hz), so both are rendered now. Matching those two
statistics was not enough either: at 4-18 dB SNR (800 clips) the two models still followed the conversation (median CER
0.09-0.29, FireRed empty 49 times, base Qwen3 never), while FireRed is empty on about 2/3 of the real recordings. So SNR
now reaches below 0 dB and the room response loses part of its direct path, as a talker behind furniture or a partition
does. Rendered dynamic range ends up lower than the real recordings' (9.1 dB against 14.8).

Whether a clip is intelligible is not decided here: distance and level do not settle it, and far-field meeting
corpora already teach text on similar audio. label_distant_talk_pool.py asks two independent models and
finalize_distant_talk_pool.py turns the answers into targets.

    python scripts/ts_robust/build_distant_talk_pool.py --version V --zh 24000 --en 10000 [--workers 24]

Writes source/<version>/audio/<language>/*.flac and source/<version>/manifest.jsonl under
/workspace/data/datasets/asr_distant_talk_pool.
"""

import argparse
import importlib.util
import json
import random
import sys
import xml.etree.ElementTree as ET
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import soundfile as sf

DATA = Path("/workspace/data")
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
_spec = importlib.util.spec_from_file_location("babble_bench", REPO / "scripts" / "asr_babble_bench" / "build.py")
bench = importlib.util.module_from_spec(_spec)
sys.modules["babble_bench"] = bench
_spec.loader.exec_module(bench)

_spec = importlib.util.spec_from_file_location("ts_real_english", REPO / "scripts" / "ts_real" / "english.py")
english = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(english)

from audio_data_contract import load_catalog, resolve_split
from audio_data_contract.roots import load_roots

DATASET_ID = "asr_distant_talk_pool"
SEED = 20261102
SR = bench.SR
SOURCES = {"zh": {"dataset": "magicdata_ramc", "version": "legacy-20260804", "split": "train"},
           "en": {"dataset": "icsi", "version": "modelscope-argmaxinc-20261025", "split": "test"}}
# Headset mixes already decoded for ts_real_train@en-v1-20261101; none is a benchmark or dev meeting.
ICSI_AUDIO = DATA / "datasets/ts_real_train/source/en-v1-20261101/icsi"
RIR = {"dataset": "sim_rir_slr28", "version": "legacy-20260804", "split": "all", "rooms": ["mediumroom", "largeroom"]}
SECONDS = (3.0, 20.0)
SECOND_CONVERSATION_PROB = 0.3  # an office often holds more than one conversation
SECOND_CONVERSATION_GAIN_DB = (-6.0, 6.0)
# Measured on recordings of real distant office talk (30 ms frames; quartiles): p95 -32.6 to -24.1 dBFS,
# p95 - p5 13.5 to 16.4 dB, energy above 4 kHz -29.3 to -25.4 dB relative to 200-1000 Hz. The ranges extend past the
# quartiles so that the labels, not the render, set the intelligibility boundary.
FRAME_P95_DBFS = (-36.0, -21.0)
FRAME_SECONDS = 0.03
SNR_DB = (-8.0, 8.0)  # speech frame p95 over room-noise RMS
DIRECT_PATH_CUT_DB = (0.0, 15.0)
DIRECT_PATH_SAMPLES = 40  # 2.5 ms past the response peak
DULL_ABOVE_HZ = (2500.0, 4000.0)
DULL_DB = (6.0, 14.0)
NOISE = {"dataset": "meeting_room_noise", "version": "v2-20261014"}
NOISE_SPLITS = ("train",)
FLOOR_DBFS = (-70.0, -60.0)
FLOOR_KINDS = ("white", "pink")
MIN_SPEECH_FRACTION = 0.3  # of the window under supervisions, so a clip is talk and not a long pause
G = {}


def frame_p95_dbfs(wave):
    size = int(FRAME_SECONDS * SR)
    frames = wave[:len(wave) // size * size].reshape(-1, size)
    return 20.0 * np.log10(np.percentile(np.sqrt((frames ** 2).mean(axis=1)), 95) + 1e-12)


def load_conversations(source, language, catalog, roots):
    """{recording: {path, duration, turns}} of near-field conversations, with supervisions in time order."""
    paths = {role: resolve_split(catalog, source["dataset"], source["version"], source["split"], role, roots)
             for role in ("recordings", "supervisions")}
    conversations = {}
    for path in paths["recordings"]:
        for row in bench.ts_build._rows(path):
            conversations[row["id"]] = {"path": row["sources"][0]["source"], "duration": float(row["duration"]),
                                        "turns": []}
    for path in paths["supervisions"]:
        for row in bench.ts_build._rows(path):
            text = " ".join((row.get("text") or "").split())
            text = text.replace(" ", "") if language == "zh" else text.lower()
            if row["recording_id"] in conversations and text:
                conversations[row["recording_id"]]["turns"].append(
                    (float(row["start"]), float(row["duration"]), text, row["speaker"]))
    for conversation in conversations.values():
        conversation["turns"].sort(key=lambda t: t[:2])
    return {k: v for k, v in sorted(conversations.items()) if v["turns"]}


def load_icsi_conversations(source, catalog, roots):
    """The same shape from the ICSI headset mixes; excluded segments stay as text-less turns, so no window holds one."""
    transcripts = next(p for p in resolve_split(catalog, source["dataset"], source["version"], source["split"],
                                                "transcriptions", roots) if (p / "transcripts").is_dir())
    conversations = {}
    for path in sorted(ICSI_AUDIO.glob("*.interaction.wav")):
        meeting = path.name.removesuffix(".interaction.wav")
        turns = []
        for segment in ET.parse(transcripts / "transcripts" / f"{meeting}.mrt").getroot().iter("Segment"):
            if not segment.get("Participant"):
                continue
            start, end = float(segment.get("StartTime")), float(segment.get("EndTime"))
            text, reason = english.icsi_segment(segment)
            if text or reason:
                turns.append((start, end - start, None if reason else text, segment.get("Participant")))
        conversations[meeting] = {"path": str(path), "duration": sf.info(str(path)).duration, "turns": sorted(
            turns, key=lambda t: t[:2])}
    return conversations


def pick_window(rng, conversations, names, seconds, language):
    """A window of one conversation from a turn start, ended at a turn end so the gold text matches the audio."""
    name = rng.choice(names)
    conversation = conversations[name]
    start = rng.choice(conversation["turns"])[0]
    if start + seconds > conversation["duration"]:
        return None
    inside = [t for t in conversation["turns"] if t[0] >= start and t[0] + t[1] <= start + seconds]
    if not inside or not all(t[2] for t in inside):
        return None
    end = max(t[0] + t[1] for t in inside)
    crossing = [t for t in conversation["turns"] if t not in inside and t[0] < end and t[0] + t[1] > start]
    spoken = sum(t[1] for t in inside)
    if crossing or end - start < SECONDS[0] or spoken < MIN_SPEECH_FRACTION * (end - start):
        return None
    return {"recording": name, "path": conversation["path"], "start": round(start, 3), "seconds": round(end - start, 3),
            "text": ("" if language == "zh" else " ").join(t[2] for t in inside),
            "speakers": sorted({t[3] for t in inside})}


def plan(language, index, conversations, names, rooms, noises):
    rng = random.Random(f"{SEED}:{language}:{index}")
    room = rng.choice(sorted(rooms))
    count = 2 if rng.random() < SECOND_CONVERSATION_PROB else 1
    streams = []
    while not streams:
        window = pick_window(rng, conversations, names, round(rng.uniform(*SECONDS), 3), language)
        if window:
            streams.append(window)
    seconds = streams[0]["seconds"]
    while len(streams) < count:  # the first conversation sets the clip length; the second may be cut off by it
        name = rng.choice(names)
        conversation = conversations[name]
        start = round(rng.uniform(0.0, conversation["duration"] - seconds), 3)
        if name != streams[0]["recording"] and conversation["duration"] > seconds:
            streams.append({"recording": name, "path": conversation["path"], "start": start, "seconds": seconds,
                            "text": None, "speakers": []})
    noise_path, noise_seconds = rng.choice(noises)
    for stream, rir in zip(streams, rng.sample(rooms[room], count)):
        stream["rir"] = rir
    if count == 2:
        streams[1]["gain_db"] = round(rng.uniform(*SECOND_CONVERSATION_GAIN_DB), 2)
    return {"id": f"{DATASET_ID}:{language}:{index:06d}", "language": language, "seconds": seconds, "room": room,
            "streams": streams, "frame_p95_dbfs": round(rng.uniform(*FRAME_P95_DBFS), 2),
            "snr_db": round(rng.uniform(*SNR_DB), 2), "direct_cut_db": round(rng.uniform(*DIRECT_PATH_CUT_DB), 2), "dull": {"above_hz": round(rng.uniform(*DULL_ABOVE_HZ), 1),
                                                               "db": round(rng.uniform(*DULL_DB), 2)},
            "noise": {"path": noise_path, "start": round(rng.uniform(0.0, max(noise_seconds - seconds, 0.0)), 3)},
            "floor": {"kind": rng.choice(FLOOR_KINDS), "dbfs": round(rng.uniform(*FLOOR_DBFS), 2),
                      "seed": rng.getrandbits(32)}}


def read_window(path, start, seconds):
    with sf.SoundFile(path) as stream:
        stream.seek(int(start * stream.samplerate))
        wave = stream.read(int(seconds * stream.samplerate), dtype="float32", always_2d=True).mean(axis=1)
        if stream.samplerate != SR:
            raise ValueError(f"{path}: {stream.samplerate} Hz")
    return wave


def dull(wave, above_hz, db):
    """Lower everything above ``above_hz`` by ``db``, with a 500 Hz ramp, as a distant talker through the device sounds."""
    spectrum = np.fft.rfft(wave)
    hz = np.fft.rfftfreq(len(wave), 1.0 / SR)
    return np.fft.irfft(spectrum * 10.0 ** (-db * np.clip((hz - above_hz) / 500.0, 0.0, 1.0) / 20.0), len(wave))


def render(p):
    length = int(p["seconds"] * SR)
    mix = np.zeros(length, dtype=np.float64)
    for stream in p["streams"]:
        wave = read_window(stream["path"], stream["start"], p["seconds"])
        rir = bench.ts_build.read_audio(stream["rir"]).copy()
        rir[:int(np.abs(rir).argmax()) + DIRECT_PATH_SAMPLES] *= 10.0 ** (-p["direct_cut_db"] / 20.0)
        wave = bench.mixer.apply_rir(wave, rir)[:length]
        mix[:len(wave)] += wave / bench.mixer.rms(wave) * 10.0 ** (stream.get("gain_db", 0.0) / 20.0)
    w = dull(mix, p["dull"]["above_hz"], p["dull"]["db"]).astype(np.float32)
    speech_p95 = frame_p95_dbfs(w)
    noise = read_window(p["noise"]["path"], p["noise"]["start"], p["seconds"])
    if len(noise) < len(w):
        noise = np.resize(noise, len(w))
    w = w + noise / bench.mixer.rms(noise) * 10.0 ** ((speech_p95 - p["snr_db"]) / 20.0)
    w = w * 10.0 ** ((p["frame_p95_dbfs"] - frame_p95_dbfs(w)) / 20.0)
    w = (w + bench.mixer.floor_noise(len(w), p["floor"])).astype(np.float32)
    peak = float(np.abs(w).max())
    if peak > 0.99:
        w = w * (0.99 / peak)
    name = p["id"].split(":", 1)[1].replace(":", "-")
    relative = f"datasets/{DATASET_ID}/source/{G['version']}/audio/{p['language']}/{name}.flac"
    (DATA / relative).parent.mkdir(parents=True, exist_ok=True)
    sf.write(DATA / relative, w, SR, format="FLAC", subtype="PCM_16")
    return {**p, "path": relative, "frames": len(w), "peak_dbfs": round(20 * np.log10(peak + 1e-12), 2)}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", required=True)
    parser.add_argument("--zh", type=int, required=True, help="clips")
    parser.add_argument("--en", type=int, required=True, help="clips")
    parser.add_argument("--workers", type=int, default=24)
    args = parser.parse_args()
    catalog, roots = load_catalog(str(DATA / "registry/catalog")), load_roots(str(DATA / "registry/roots.json"))
    rooms = bench.babble_rooms({"babble_rir": RIR}, catalog, roots)
    G.update(version=args.version)
    noises = [(row["sources"][0]["source"], float(row["duration"]))
              for split in NOISE_SPLITS
              for path in resolve_split(catalog, NOISE["dataset"], NOISE["version"], split, "recordings", roots)
              for row in bench.ts_build._rows(path)]
    print("room noises", len(noises), flush=True)
    jobs = []
    for language, source in SOURCES.items():
        conversations = (load_icsi_conversations(source, catalog, roots) if language == "en"
                         else load_conversations(source, language, catalog, roots))
        names = sorted(conversations)
        print(language, "conversations", len(names), flush=True)
        jobs += [plan(language, i, conversations, names, rooms, noises) for i in range(getattr(args, language))]
    with ProcessPoolExecutor(args.workers, mp_context=bench.FORK) as pool:
        rendered = list(pool.map(render, jobs, chunksize=16))
    manifest = DATA / "datasets" / DATASET_ID / "source" / args.version / "manifest.jsonl"
    with manifest.open("w", encoding="utf-8") as stream:
        for row in rendered:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    print("rendered", len(rendered), "->", manifest, flush=True)


if __name__ == "__main__":
    main()

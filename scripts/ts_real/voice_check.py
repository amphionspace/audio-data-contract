"""Check that an enrollment sounds like its labelled speaker (``build.py`` recipes with ``voice_check``).

An enrollment passes when its embedding is closer to the profile of its own speaker in the recording (mean
embedding of their other utterances there) than to the profile of every other speaker of that recording, both
for the first ``crop`` seconds (what the client sends) and for the whole stored enrollment. Profiles use
utterances of at least ``PROFILE_MIN`` seconds that others overlap for at most ``PROFILE_OVERLAP`` of their length
and that the transcript does not exclude, at most ``PROFILE_MAX`` per speaker, never the enrollment's own pieces.
A speaker without such an utterance cannot be checked and fails.

The question is whether the label is right, so the audio is the cleanest view of the recording that ``cut``
offers (``build.check_cut``: the sum of the close-talk microphones where the corpus has them, else the channel
the set is cut from).

Embeddings come from ``embed_worker.py``, run in its own environment (it needs onnxruntime and torchaudio).
"""

from __future__ import annotations

import bisect
import random
import struct
import subprocess
from collections import Counter
from pathlib import Path

import numpy as np

PROFILE_MIN = 2.0  # seconds; shorter utterances give noisy embeddings
PROFILE_OVERLAP = 0.2  # share of a profile utterance others may talk in (the enrollment rule)
PROFILE_MAX = 12  # utterances per speaker profile
PROFILE_CAP = 10.0  # seconds embedded per profile utterance
SR = 16000


class Embedder:
    def __init__(self, python, model, threads=4):
        worker = Path(__file__).with_name("embed_worker.py")
        self.proc = subprocess.Popen([str(python), "-I", str(worker), "--model", str(model), "--threads", str(threads)],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        (self.dim,) = struct.unpack("<I", self._read(4))

    def _read(self, n):
        data = self.proc.stdout.read(n)
        if len(data) != n:
            raise RuntimeError(f"embedding worker exited ({self.proc.poll()})")
        return data

    def __call__(self, w):
        w = np.ascontiguousarray(w, dtype="<f4")
        self.proc.stdin.write(struct.pack("<Q", len(w)) + w.tobytes())
        self.proc.stdin.flush()
        return np.frombuffer(self._read(4 * self.dim), dtype="<f4").copy()

    def close(self):
        self.proc.stdin.close()
        self.proc.wait()


class VoiceCheck:
    def __init__(self, embed, cut, crop, store, view):
        """``cut(recordings, recording, start, end)`` gives the audio to check, ``view(entry)`` names it."""
        self.embed, self.cut, self.crop, self.store, self.view = embed, cut, crop, store, view
        self.stats = Counter()
        self.events = []

    # Caches live on the recording's entry: recording IDs repeat across corpora (CHiME-6 and DiPCo both have S01).
    def _utterance(self, recordings, recording, s, e):
        cache = recordings[recording].setdefault("voice_embeddings", {})
        if (s, e) not in cache:
            cache[(s, e)] = self.embed(self.cut(recordings, recording, s, min(e, s + PROFILE_CAP)))
        return cache[(s, e)]

    def _candidates(self, recordings, recording, speaker):
        cache = recordings[recording].setdefault("voice_candidates", {})
        if speaker not in cache:
            entry = recordings[recording]
            excluded = entry.get("excluded", {})
            out = []
            for s, e, spk, _ in entry["sups"]:
                if spk != speaker or e - s < PROFILE_MIN or (s, e, spk) in excluded:
                    continue
                first = bisect.bisect_left(entry["starts"], s - entry["longest"])
                last = bisect.bisect_left(entry["starts"], e)
                others = sum(max(0.0, min(e, o[1]) - max(s, o[0])) for o in entry["sups"][first:last] if o[2] != speaker)
                if others <= PROFILE_OVERLAP * (e - s):
                    out.append((s, e))
            random.Random(f"{recording}:{speaker}:profile").shuffle(out)
            cache[speaker] = out
        return cache[speaker]

    def profile(self, recordings, recording, speaker, exclude=()):
        candidates = self._candidates(recordings, recording, speaker)
        chosen = [(s, e) for s, e in candidates if not any(s < pe and e > ps for ps, pe in exclude)][:PROFILE_MAX]
        if not chosen:
            return None, 0
        mean = np.mean([self._utterance(recordings, recording, s, e) for s, e in chosen], axis=0)
        return mean / np.linalg.norm(mean), len(chosen)

    def check(self, recordings, recording, speaker, pieces):
        """{passed, audio, crop_own, crop_other, full_own, full_other, other_speaker, profile_utts}."""
        own, count = self.profile(recordings, recording, speaker, pieces)
        verdict = {"passed": False, "audio": self.view(recordings[recording]), "profile_utts": count}
        if own is None:
            verdict["reason"] = "no_profile"
            return verdict
        others = {}
        for other in sorted({u[2] for u in recordings[recording]["sups"]} - {speaker}):
            vector, _ = self.profile(recordings, recording, other)
            if vector is not None:
                others[other] = vector
        audio = np.concatenate([self.cut(recordings, recording, s, e) for s, e in pieces])[: int(self.store * SR)]
        passed = True
        for part, w in (("crop", audio[: int(self.crop * SR)]), ("full", audio)):
            e = self.embed(w)
            sims = {other: float(e @ v) for other, v in others.items()}
            best = max(sims, key=sims.get) if sims else None
            verdict[f"{part}_own"] = round(float(e @ own), 3)
            verdict[f"{part}_other"] = round(sims[best], 3) if best else None
            if part == "crop":
                verdict["other_speaker"] = best
            passed &= best is None or verdict[f"{part}_own"] > verdict[f"{part}_other"]
        verdict["passed"] = bool(passed)
        return verdict

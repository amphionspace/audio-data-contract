"""English real-conversation corpora for ``build.py --recipe en``: transcript cleaning and per-corpus loaders.

Each loader returns ``{recording: entry}`` in the shape ``build.load_corpus`` produces (``path``, ``sups`` as
``(start, end, speaker, text)``, ``duration``) plus:

* ``excluded``: ``{(start, end, speaker): reason}`` for speech whose words are not (all) in the transcript
  (unintelligible, foreign, censored, untranscribed) or that is not conversation (ICSI digit reading). Such an
  utterance still counts as speech in a window (window edges, who is present), but never as a target's reference
  or an enrollment.
* ``source``: the channel the audio is cut from.

Text keeps the annotation's casing and punctuation; annotation markup (noise and laughter tags, truncated-word
fragments, restart dashes, name tags) is removed, see ``clean``. Utterances left with no words and no excluded
speech (a bare ``[laughs]``) are dropped, as ``build.load_corpus`` drops empty supervisions.
"""

from __future__ import annotations

import bisect
import gzip
import io
import json
import re
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import soundfile as sf

from audio_data_contract import resolve_artifact, resolve_split

SR = 16000

# Bracket and angle tags per corpus: removed (non-speech, markup) or excluded (speech without a reference).
TAGS = {
    # CHiME-6 transcription conventions; [inaudible 0:12:34.56] carries the time of the inaudible stretch.
    "chime6": {"remove": {"[laughs]", "[noise]"}, "exclude": {"[inaudible": "unintelligible", "[redacted]": "redacted"}},
    # DiPCo README: [noise] speaker noise, [laugh], [unintelligible].
    "dipco": {"remove": {"[noise]", "[laugh]"}, "exclude": {"[unintelligible]": "unintelligible"}},
    # NOTSOFAR-1 GT: <ST/> segment-continuation mark, <FILL/> filled pause, <FILLlaugh/> laughter, <PName> name tags;
    # <UNKNOWN/> unintelligible word, <FL/> foreign language, <BA/> segment without words, <ISSUE/> annotator flag,
    # #ignore="SegmTooShort" segment flag.
    "notsofar": {"remove": {"<ST/>", "<FILL/>", "<FILLlaugh/>", "<PName>", "</PName>"},
                 "exclude": {"<UNKNOWN/>": "unintelligible", "<FL/>": "foreign", "<BA/>": "untranscribed",
                             "<ISSUE/>": "annotation_issue", "#ignore=": "ignored_segment"}},
    # AMI (lhotse text, already without markup).
    "ami": {"remove": set(), "exclude": {}},
}
TAG = re.compile(r"\[[^\]]*\]|<[^>]*>|#ignore=\"[^\"]*\"")
PUNCT = "\"'.,?!;:()"


def clean_words(text):
    """Words of ``text`` without truncated-word fragments (``th-``, ``-ing``) and bare dashes; a punctuation mark
    left alone by a removed tag joins the previous word."""
    words = []
    for token in text.split():
        core = token.strip(PUNCT)
        if not any(ch.isalnum() for ch in core):
            if words and token.strip("-") and not core.strip("-"):
                words[-1] += token.strip("-")
            continue
        if core.endswith("-") or core.startswith("-"):
            continue
        words.append(token)
    return " ".join(words)


def clean(raw, kind):
    """(text, excluded reason or None) of one transcript line."""
    rules, reason = TAGS[kind], None
    for tag in TAG.findall(raw):
        hit = next((r for prefix, r in rules["exclude"].items() if tag.startswith(prefix)), None)
        if hit:
            reason = reason or hit
        elif tag not in rules["remove"]:
            raise ValueError(f"{kind}: unknown tag {tag!r} in {raw!r}")
    return clean_words(TAG.sub(" ", raw)), reason


def _entry(path, sups, duration, excluded, source):
    return {"path": str(path), "sups": sups, "duration": float(duration), "channels": 1, "excluded": excluded,
            "source": source}


def _add(sups, excluded, start, end, speaker, raw, kind):
    text, reason = clean(raw, kind)
    if reason:
        excluded[(start, end, speaker)] = reason
    if text or reason:
        sups.append((start, end, speaker, text))


def _seconds(stamp):
    hours, minutes, seconds = stamp.split(":")
    return round(int(hours) * 3600 + int(minutes) * 60 + float(seconds), 3)


# --- NOTSOFAR-1 ------------------------------------------------------------------


def load_notsofar(spec, catalog, roots, rng):
    """One single-channel device per meeting (drawn with ``rng``), times and text from the meeting's GT.

    The icefall manifest lists one recording per (meeting, device) and drops GT segments whose words are all tags
    (``<UNKNOWN/>``, laughter), so unintelligible speech would be missing from the timeline; the GT next to the
    audio keeps them.
    """
    meetings = defaultdict(list)
    for path in resolve_split(catalog, spec["dataset"], spec["version"], spec["split"], "recordings", roots):
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            for row in map(json.loads, stream):
                meeting = "_".join(row["id"].split("_")[:2])
                meetings[meeting].append((row["id"], row["sources"][0]["source"], float(row["duration"])))
    out = {}
    for meeting in sorted(meetings):
        rid, audio, duration = rng.choice(sorted(meetings[meeting]))
        gt = json.loads((Path(audio).parents[1] / "gt_transcription.json").read_text(encoding="utf-8"))
        sups, excluded = [], {}
        for row in gt:
            _add(sups, excluded, round(float(row["start_time"]), 3), round(float(row["end_time"]), 3),
                 str(row["speaker_id"]), row["text"], "notsofar")
        if sups:
            out[rid] = _entry(audio, sups, duration, excluded, "/".join(Path(audio).parts[-2:]))
            # Headsets on the GT time base, for the voice check (devices are within 0.03 s of them).
            out[rid]["close_talk"] = sorted(str(p) for p in (Path(audio).parents[1] / "close_talk").glob("*.wav"))
    return out


# --- CHiME-6 -----------------------------------------------------------------------


def load_chime6(spec, catalog, roots):
    """Sessions of the official transcription (array-synchronised times), one entry per session.

    Speakers move between kitchen, dining and living room; each utterance carries its location and the
    reference array of that room (one per room and session). Audio is cut from channel 1 of the reference array
    of the room (``paths``/``locations``; ``build.cut`` picks it per span) and windows must stay in one room
    (``build.single_room``), so nobody in the window talks from another room.
    """
    (records,) = resolve_split(catalog, spec["dataset"], spec["version"], spec["split"], "records", roots)
    (index,) = resolve_split(catalog, spec["dataset"], spec["version"], spec["split"], "audio_index", roots)
    files = {}
    with gzip.open(index, "rt", encoding="utf-8") as stream:
        for row in map(json.loads, stream):
            files[Path(row["relative_path"]).stem] = (Path(roots[row["root_alias"]]) / row["relative_path"], row["duration"])
    rows = []
    with gzip.open(records, "rt", encoding="utf-8") as stream:
        rows += [json.loads(line)["metadata"]["source_annotation"] for line in stream]
    # The prepared records leave out annotations with start > end; keep them as speech of unknown words.
    invalid = json.loads(resolve_artifact(catalog, spec["dataset"], spec["version"], "excluded_annotations", roots).read_text())
    sessions = {row["session_id"] for row in rows}
    rows += [{**item["annotation"], "invalid": True} for item in invalid if item["annotation"]["session_id"] in sessions]
    by_session = defaultdict(list)
    for row in rows:
        by_session[row["session_id"]].append(row)
    out = {}
    for session, session_rows in sorted(by_session.items()):
        refs = defaultdict(Counter)
        for row in session_rows:
            if row.get("ref"):
                refs[row["location"]][row["ref"]] += 1
        arrays = {location: count.most_common(1)[0][0] for location, count in refs.items()}
        if len(set(arrays.values())) != len(arrays):
            raise ValueError(f"{session}: rooms share a reference array {arrays}")
        sups, excluded, locations = [], {}, {}
        for row in session_rows:
            start, end = sorted((_seconds(row["start_time"]), _seconds(row["end_time"])))
            text, reason = clean(row["words"], "chime6")
            reason = "invalid_timestamps" if row.get("invalid") else reason
            if reason:
                excluded[(start, end, row["speaker"])] = reason
            if text or reason:
                sups.append((start, end, row["speaker"], text))
                locations[(start, end, row["speaker"])] = row["location"]
        paths = {location: files[f"{session}_{array}.CH1"][0] for location, array in arrays.items()}
        duration = min(files[f"{session}_{array}.CH1"][1] for array in arrays.values())
        entry = _entry(next(iter(paths.values())), sups, duration, excluded,
                       ", ".join(f"{location}={array}.CH1" for location, array in sorted(arrays.items())))
        entry.update(paths={k: str(v) for k, v in paths.items()}, locations=locations,
                     arrays={k: f"{v}.CH1" for k, v in arrays.items()})
        out[session] = entry
    return out


# --- DiPCo ---------------------------------------------------------------------------


def load_dipco(spec, catalog, roots, rng):
    """One far-field device per session (drawn with ``rng``), channel 1, official transcription.

    The transcription gives every device the close-talk times, but the far-field files are offset from the
    close-talk ones by 0.1-0.25 s; ``close_talk`` lists the headset files for ``measure_offset``, ``shift`` and the
    voice check.
    """
    (transcripts,) = resolve_split(catalog, spec["dataset"], spec["version"], spec["split"], "transcriptions", roots)
    (audio_dir,) = resolve_split(catalog, spec["dataset"], spec["version"], spec["split"], "source_directory", roots)
    out = {}
    for path in sorted((transcripts / spec["split"]).glob("*.json")):
        session = path.stem
        device = rng.choice(["U01", "U02", "U03", "U04", "U05"])
        audio = audio_dir / spec["split"] / f"{session}_{device}.CH1.wav"
        sups, excluded = [], {}
        for row in json.loads(path.read_text(encoding="utf-8")):
            _add(sups, excluded, _seconds(row["start_time"][device]), _seconds(row["end_time"][device]),
                 row["speaker_id"], row["words"], "dipco")
        entry = _entry(audio, sups, sf.info(str(audio)).duration, excluded, f"{device}.CH1")
        entry["close_talk"] = sorted(str(p) for p in (audio_dir / spec["split"]).glob(f"{session}_P*.wav"))
        out[session] = entry
    return out


def shift(entry, seconds):
    """Move an entry's timeline by ``seconds`` (``offset_s``), before ``build.finish_entry``."""
    def moved(s, e, spk):
        return round(s + seconds, 3), round(e + seconds, 3), spk

    entry["sups"] = [(*moved(s, e, spk), text) for s, e, spk, text in entry["sups"]]
    entry["excluded"] = {moved(*key): reason for key, reason in entry["excluded"].items()}
    entry["offset_s"] = seconds


def frame_energy(w, hop=160):
    w = w[: len(w) // hop * hop].reshape(-1, hop)
    return np.log(np.mean(np.square(w, dtype=np.float64), axis=1) + 1e-10)


def measure_offset(reference, far, starts, span=120.0, max_lag=1.0):
    """Seconds by which ``far`` lags the summed ``reference`` files, from log-energy cross-correlation over
    ``span``-second stretches at ``starts``; returns (median lag, per-stretch lags, correlations)."""
    lags, peaks = [], []
    hop, limit = 160, int(max_lag * SR / 160)
    for start in starts:
        first, last = int(start * SR), int((start + span) * SR)
        ref = sum(sf.read(p, start=first, stop=last, dtype="float32")[0] ** 2 for p in reference)
        ref = frame_energy(np.sqrt(ref), hop)
        sig = frame_energy(sf.read(far, start=first, stop=last, dtype="float32")[0], hop)
        n = min(len(ref), len(sig))
        if n < 4 * limit:
            continue
        a = (ref[:n] - ref[:n].mean()) / (ref[:n].std() + 1e-9)
        b = (sig[:n] - sig[:n].mean()) / (sig[:n].std() + 1e-9)
        scores = [float(np.mean(a[: n - lag] * b[lag:])) if lag >= 0 else float(np.mean(a[-lag:] * b[: n + lag]))
                  for lag in range(-limit, limit + 1)]
        best = int(np.argmax(scores))
        lags.append((best - limit) * hop / SR)
        peaks.append(round(scores[best], 3))
    return (float(np.median(lags)) if lags else None), lags, peaks


# --- ICSI ------------------------------------------------------------------------------

# Elements whose text is speech (kept) and whose text is a description (dropped with the element).
ICSI_KEEP = {"Emphasis", "Uncertain", "Pronounce"}
ICSI_DROP = {"VocalSound", "NonVocalSound", "Comment", "Pause"}
SPELLED = re.compile(r"\b((?:[A-Za-z]_)+)([A-Za-z]\b)?")


def icsi_segment(segment):
    """(text, excluded reason or None) of one MRT segment."""
    reason = None
    if segment.get("DigitTask") == "true":
        reason = "digit_task"
    parts = [segment.text or ""]
    for child in segment:
        description = child.get("Description", "")
        if child.tag in ICSI_DROP:
            if description == "Censored":
                reason = reason or "censored"
            elif description == "pre-meeting utterance":
                reason = reason or "untranscribed"
        elif child.tag == "Foreign":
            reason = reason or "foreign"
        elif child.tag in ICSI_KEEP:
            parts.append("".join(child.itertext()))
        else:
            raise ValueError(f"ICSI: unknown element {child.tag}")
        parts.append(child.tail or "")
    raw = " ".join(parts)
    if "@@" in raw:
        reason = reason or "unintelligible"
        raw = raw.replace("@@", " ")
    # Letters read out are written "O_K", "I_B_M", "X_" (one letter), "C_zero" (letter, then a word).
    raw = SPELLED.sub(lambda m: m.group(1).replace("_", "") + (m.group(2) or " "), raw)
    return clean_words(raw.replace("_", " ")), reason


def load_icsi(spec, catalog, roots):
    """The recipe's ``meetings`` (the ICSI test partition), MRT transcripts, audio = the official headset mix."""
    transcripts = next(p for p in resolve_split(catalog, spec["dataset"], spec["version"], spec["split"], "transcriptions", roots)
                       if (p / "transcripts").is_dir())
    (parquet_dir,) = resolve_split(catalog, spec["dataset"], spec["version"], spec["split"], "records", roots)
    audio = icsi_audio(parquet_dir, set(spec["meetings"]))
    out = {}
    for meeting in spec["meetings"]:
        root = ET.parse(transcripts / "transcripts" / f"{meeting}.mrt").getroot()
        sups, excluded = [], {}
        for segment in root.iter("Segment"):
            speaker = segment.get("Participant")
            if not speaker:
                continue
            start, end = round(float(segment.get("StartTime")), 3), round(float(segment.get("EndTime")), 3)
            text, reason = icsi_segment(segment)
            if reason:
                excluded[(start, end, speaker)] = reason
            if text or reason:
                sups.append((start, end, speaker, text))
        samples = audio[meeting]
        entry = _entry(f"{parquet_dir}#{meeting}.interaction.wav", sups, len(samples) / SR, excluded,
                       "interaction.wav (headset mix)")
        entry["samples"] = samples
        out[meeting] = entry
    return out


def icsi_audio(parquet_dir, meetings):
    """{meeting: float32 samples} of the headset-mix files in the mirror's parquet shards."""
    import pyarrow.parquet as pq

    out = {}
    for path in sorted(Path(parquet_dir).glob("test-*.parquet")):
        shard = pq.ParquetFile(path)
        # Shards are sorted by file name; the min/max statistics of the path column skip the others unread.
        column = [shard.metadata.schema.column(j).path for j in range(shard.metadata.num_columns)].index("audio.path")
        stats = [shard.metadata.row_group(i).column(column).statistics for i in range(shard.metadata.num_row_groups)]
        if all(s is not None and s.has_min_max for s in stats) and not any(
                s.min <= f"{m}.interaction.wav" <= s.max for s in stats for m in meetings):
            continue
        names = [row["path"].removesuffix(".interaction.wav")  # a struct column holding only ``path``
                 for row in shard.read(columns=["audio.path"]).column(0).to_pylist()]
        wanted = [i for i, name in enumerate(names) if name in meetings]
        if not wanted:
            continue
        audio = shard.read(columns=["audio"]).column(0).to_pylist()
        for i in wanted:
            w, rate = sf.read(io.BytesIO(audio[i]["bytes"]), dtype="float32", always_2d=True)
            if rate != SR:
                raise ValueError(f"{names[i]}: expected {SR} Hz, got {rate}")
            out[names[i]] = w[:, 0].copy()
        if len(out) == len(meetings):
            break
    missing = sorted(meetings - set(out))
    if missing:
        raise FileNotFoundError(f"ICSI meetings not in {parquet_dir}: {missing}")
    return out


def location_at(entry, start, end):
    """Room of the utterance that covers most of [start, end] (CHiME-6)."""
    first = bisect.bisect_left(entry["starts"], start - entry["longest"])
    best, room = 0.0, None
    for s, e, spk, _ in entry["sups"][first:bisect.bisect_left(entry["starts"], end)]:
        shared = min(e, end) - max(s, start)
        if shared > best:
            best, room = shared, entry["locations"][(s, e, spk)]
    if room is None:
        raise ValueError(f"no utterance covers {start}-{end}")
    return room

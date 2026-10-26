#!/usr/bin/env python3
"""Add each mixture's speaker timeline (``metadata.window_utts``) to TS training records, as a derived version.

open-audio-llm's frame-level speaker-activity loss (``objective.ts_activity_weight``) labels a mixture frame by
who speaks in it. It reads ``metadata.window_utts`` (speaker, start and duration relative to the mixture start)
and ``metadata.target_speaker`` in the same speaker namespace, as ts_real_train v2 writes them. The sources
below were cut from annotated audio but did not keep the timeline; this script recovers it from that
annotation and writes ``<version>-utts``: the same records, with the timeline added and the audio refs pointing
at the derived version, whose audio index rows are the original's.

* ``span`` - windows over long annotated recordings: ts_real_train v1 (alimeeting, aishell4, ramc), the v3
  AliMeeting headset views (alimeeting_en_mn / _mf; near and far files are aligned, so the far-field
  annotation holds) and the turn-taking windows of alimeeting_sdm, aishell4, ami_sdm and magicdata_ramc.
  Annotation: the icefall-20260908 supervisions of each corpus's train split.
* ``moss`` - ts_real_train v3 emilia2_1spk, from the MOSS diarization window each record names.
* ``dialog`` - emilia2_dialog turn-taking windows, from the Emilia2 dialogue JSON (``short`` segments).
* ``mix`` - emilia2_mix, from its mixing protocol (``supervision/protocol-*.jsonl.gz``).
* ``keep`` - ts_real_train v2, whose builder wrote the timeline itself: only the check below is applied. Speakers
  recur across AliMeeting and RAMC sessions, so a few ``other_recording`` negatives enrolled the window's own speaker.

An utterance overlapping the mixture is kept, clipped to it (marked ``clipped``). A positive keeps its timeline
only when its target utterances spell the record's transcript (whitespace and punctuation ignored; an utterance
cut by the window edge may be transcribed in part) and a negative only when the target does not speak in it; any other record keeps no timeline, so it gets no frame
labels, and is counted in ``report.json``. A negative whose enrolled speaker does speak in the window per the
annotation is mislabelled (its transcript is empty), so its ID also goes to ``excluded-records-<split>.txt`` for
the training recipe's ``exclude_records``.

    python add_window_utts.py --source alimeeting_sdm@turn-taking-20261014 [--limit N]
"""

import argparse
import bisect
import copy
import gzip
import importlib.util
import json
import unicodedata
from collections import Counter, OrderedDict, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from audio_data_contract import load_catalog, resolve_split

DATA = Path("/workspace/data")
HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("ts_real_train_v3", HERE / "build_ts_real_train_v3.py")
v3 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(v3)
base = v3.base  # build_ts_real_train.py: load_corpus

ANNOTATION = "icefall-20260908"
CORPUS = {"alimeeting": "alimeeting_sdm", "aishell4": "aishell4", "ramc": "magicdata_ramc"}
TURN_TAKING = ("train_2spk", "train_3spk", "train_neg")
SOURCES = {
    "ts_real_train@v1-20261017": {"alimeeting": "span", "aishell4": "span", "ramc": "span"},
    "ts_real_train@v3-20261020": {"alimeeting_en_mn": "span", "alimeeting_en_mf": "span", "emilia2_1spk": "moss"},
    **{f"{d}@turn-taking-20261014": dict.fromkeys(TURN_TAKING, "span")
       for d in ("alimeeting_sdm", "aishell4", "ami_sdm")},
    "magicdata_ramc@turn-taking-20261014": dict.fromkeys(("train_2spk", "train_neg"), "span"),
    "emilia2_dialog@dialog-turn-taking-20261013-enroll": dict.fromkeys(TURN_TAKING, "dialog"),
    "emilia2_mix@mix-20261013": dict.fromkeys(("train_2spk", "train_3spk"), "mix"),
    "ts_real_train@v2-20261018": dict.fromkeys(("alimeeting", "aishell4", "ramc"), "keep"),
}
# Utterances touching the mixture edge by less than this are not in it.
EDGE_SECONDS = 0.01


def letters(text):
    """Transcript characters only: whitespace and punctuation / symbols dropped, NFKC, lower case."""
    text = unicodedata.normalize("NFKC", text or "").lower()
    return "".join(c for c in text if not c.isspace() and unicodedata.category(c)[0] not in "PS")


def mixture(record):
    return next(s for s in record["audio_slots"] if s["name"] == "mixture")["ref"]


def clip(utterances, lo, hi):
    """window_utts of ``(start, end, speaker, text)`` utterances in [lo, hi), times relative to lo."""
    out = []
    for start, end, speaker, text in sorted(utterances):
        if end - lo <= EDGE_SECONDS or hi - start <= EDGE_SECONDS:
            continue
        begin, finish = max(start, lo), min(end, hi)
        out.append({"speaker": speaker, "start": round(begin - lo, 3), "duration": round(finish - begin, 3),
                    "text": text, **({"clipped": True} if (begin, finish) != (start, end) else {})})
    return out


class Timeline:
    """Utterances of each recording, searchable by time."""

    def __init__(self, utterances):
        self.items = defaultdict(list)
        for key, start, end, speaker, text in utterances:
            self.items[key].append((start, end, speaker, text))
        self.starts, self.longest = {}, 0.0
        for key, rows in self.items.items():
            rows.sort()
            self.starts[key] = [r[0] for r in rows]
            self.longest = max(self.longest, max(r[1] - r[0] for r in rows))

    def window(self, key, lo, hi):
        rows = self.items.get(key)
        if rows is None:
            return None
        first = bisect.bisect_left(self.starts[key], lo - self.longest)
        last = bisect.bisect_left(self.starts[key], hi)
        return clip(rows[first:last], lo, hi)


def span_timeline(dataset, catalog, roots, prefix):
    """The train annotation of a corpus, speakers named ``<prefix>:<speaker>``."""
    recordings = base.load_corpus(dataset, ANNOTATION, catalog, roots)
    return Timeline((rid, s, e, f"{prefix}:{spk}", text)
                    for rid, entry in recordings.items() for s, e, spk, text in entry["sups"])


def span_rows(dataset, split, records, catalog, roots):
    """Timeline per record of a span source: (record, window_utts or None, target speaker)."""
    if dataset == "ts_real_train":
        corpora = {r["labels"]["corpus"] for r in records}
        timelines = {c: span_timeline(CORPUS[c], catalog, roots, records_prefix(records, c)) for c in corpora}
        for r in records:
            ref, target = mixture(r), r["metadata"]["target_speaker"]
            lo = ref["start"]
            yield r, timelines[r["labels"]["corpus"]].window(r["labels"]["recording"], lo, lo + ref["duration"]), target
    else:
        timeline = span_timeline(dataset, catalog, roots, dataset)
        for r in records:
            ref, meta = mixture(r), r["metadata"]
            lo = ref["start"]
            if abs(lo - meta["window_start"]) > 0.01:
                raise SystemExit(f"{r['id']}: mixture starts at {lo}, window at {meta['window_start']}")
            # A negative names the enrolled speaker, who is not in the window, as enroll_spk only.
            speaker = r["labels"].get("target_spk") or r["labels"]["enroll_spk"]
            yield r, timeline.window(meta["recording_id"], lo, lo + ref["duration"]), f"{dataset}:{speaker}"


def records_prefix(records, corpus):
    """The speaker namespace ts_real_train used for a corpus (the split name in v1, the corpus in v3)."""
    names = {r["metadata"]["target_speaker"].split(":", 1)[0] for r in records if r["labels"]["corpus"] == corpus}
    if len(names) != 1:
        raise SystemExit(f"{corpus}: speaker namespaces {sorted(names)}")
    return names.pop()


def moss_rows(records, catalog, roots):
    entries, _ = v3.load_emilia2(catalog, roots)
    for r in records:
        entry, ref = entries.get(r["metadata"]["source_record"]), mixture(r)
        if entry is None:
            yield r, None, r["metadata"]["target_speaker"]
            continue
        lo = ref["start"] - entry["offset"]
        utterances = [(s, e, f"emilia2:{spk}", text) for s, e, spk, text in entry["sups"]]
        yield r, clip(utterances, lo, lo + ref["duration"]), r["metadata"]["target_speaker"]


def dialog_utterances(path):
    """Emilia2 dialogue segments as (start, end, session#S<n>, text)."""
    data = json.loads(path.read_text())
    session, speakers = data["id"], data["dialogue"]["speaker_map"]
    out = []
    for segment in data["short"]:
        number = segment["speaker"].rsplit("_spk", 1)[1]
        if number in speakers and segment["text"].strip():
            out.append((segment["rel_start"], segment["rel_end"], f"emilia2_dialog:{session}#{speakers[number]}",
                        "".join(segment["text"].split())))
    return out


def dialog_rows(records):
    cache = OrderedDict()
    for r in records:
        meta, ref = r["metadata"], mixture(r)
        path = DATA / Path(meta["mixture_path"]).with_suffix(".json")
        if path not in cache:
            cache[path] = dialog_utterances(path) if path.exists() else None
            if len(cache) > 4096:
                cache.popitem(last=False)
        utterances = cache[path]
        window = None if utterances is None else clip(utterances, ref["start"], ref["start"] + ref["duration"])
        speaker = r["labels"].get("target_spk") or r["labels"]["enroll_spk"]
        yield r, window, f"emilia2_dialog:{speaker}"


def _protocol(path, wanted):
    out = {}
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for row in map(json.loads, stream):
            if row["mix_id"] in wanted:
                out[row["mix_id"]] = [(seg["mix_start"], seg["mix_start"] + seg["dur"],
                                       f"emilia2_mix:{spk['recording_id']}", "".join(seg["text"].split()))
                                      for spk in row["speakers"] for seg in spk["segments"]]
    return out


def mix_rows(records, catalog, roots):
    files = sorted((DATA / "datasets/emilia2-mix/versions/mix-20261013/supervision").glob("protocol-*.jsonl.gz"))
    wanted = frozenset(r["metadata"]["mix_id"] for r in records)
    protocol = {}
    with ProcessPoolExecutor(len(files)) as pool:
        for part in pool.map(_protocol, files, [wanted] * len(files)):
            protocol.update(part)
    for r in records:
        utterances, ref = protocol.get(r["metadata"]["mix_id"]), mixture(r)
        window = None if utterances is None else clip(utterances, ref["start"], ref["start"] + ref["duration"])
        speaker = r["labels"].get("target_spk") or r["labels"]["enroll_spk"]
        yield r, window, f"emilia2_mix:{speaker}"


def keep_rows(records):
    for r in records:
        yield r, r["metadata"]["window_utts"], r["metadata"]["target_speaker"]


def check(record, window, target):
    """Why a timeline cannot label this record, or None when it can."""
    if window is None:
        return "no_annotation"
    spoken = [u for u in window if u["speaker"] == target]
    if not record["target"].strip():
        return "absent_target_speaks" if spoken else None
    if not spoken:
        return "present_target_silent"
    # An utterance cut by the window edge may be transcribed only in part: every whole one must be in the
    # transcript, and the transcript within all of them.
    want, whole = letters(record["target"]), letters("".join(u["text"] for u in spoken))
    inner = [letters(u["text"]) for u in spoken if not u.get("clipped")]
    if want != whole and not (want in whole and all(text in want for text in inner)):
        return "transcript_mismatch"
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", choices=sorted(SOURCES), required=True)
    parser.add_argument("--output-root", type=Path, default=DATA / "datasets")
    parser.add_argument("--limit", type=int, help="check the first N records per split; write nothing")
    args = parser.parse_args()
    dataset, version = args.source.split("@")
    derived = f"{version}-utts"
    roots = {k: Path(v) for k, v in json.loads((DATA / "registry/roots.json").read_text()).items()}
    catalog = load_catalog(DATA / "registry/catalog")
    directory = args.output_root / dataset / "versions" / derived
    if args.limit is None:
        directory.mkdir(parents=True, exist_ok=False)
    report = {}
    for split, family in SOURCES[args.source].items():
        records = []
        for path in resolve_split(catalog, dataset, version, split, "records", roots):
            with gzip.open(path, "rt", encoding="utf-8") as stream:
                for line in stream:
                    records.append(json.loads(line))
                    if args.limit and len(records) >= args.limit:
                        break
        if family == "span":
            rows = span_rows(dataset, split, records, catalog, roots)
        elif family == "moss":
            rows = moss_rows(records, catalog, roots)
        elif family == "dialog":
            rows = dialog_rows(records)
        elif family == "mix":
            rows = mix_rows(records, catalog, roots)
        else:
            rows = keep_rows(records)
        counts, examples, out, cuts, excluded = Counter(), defaultdict(list), [], set(), []
        for record, window, target in rows:
            problem = check(record, window, target)
            counts[problem or "labelled"] += 1
            if problem == "absent_target_speaks":
                excluded.append(record["id"])
            if problem and len(examples[problem]) < 3:
                spoken = [u["text"] for u in window or [] if u["speaker"] == target]
                examples[problem].append({"id": record["id"], "target": record["target"][:80],
                                          "window_target_text": "".join(spoken)[:80]})
            record = copy.deepcopy(record)
            for slot in record["audio_slots"]:
                slot["ref"]["version"] = derived
                cuts.add(slot["ref"]["cut_id"])
            if problem is None:
                record["metadata"] = {**record["metadata"], "target_speaker": target, "window_utts": window}
            else:
                # target_speaker stays: without it the trainer would take the window for one clean target utterance.
                record["metadata"].pop("window_utts", None)
            out.append(record)
        report[split] = {"family": family, "records": len(out), **counts, "examples": examples}
        print(split, json.dumps({k: v for k, v in report[split].items() if k != "examples"}), flush=True)
        if args.limit is not None:
            for problem, items in examples.items():
                print("  ", problem, json.dumps(items, ensure_ascii=False))
            continue
        (directory / f"excluded-records-{split}.txt").write_text("".join(f"{i}\n" for i in excluded))
        with gzip.open(directory / f"records_{split}.jsonl.gz", "wt", encoding="utf-8") as stream:
            for record in out:
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        index = {}
        for path in resolve_split(catalog, dataset, version, split, "audio_index", roots):
            with gzip.open(path, "rt", encoding="utf-8") as stream:
                for row in map(json.loads, stream):
                    if row["cut_id"] in cuts:
                        index[row["cut_id"]] = row
        if missing := cuts - index.keys():
            raise SystemExit(f"{split}: {len(missing)} cuts missing from the audio index")
        with gzip.open(directory / f"audio_index_{split}.jsonl.gz", "wt", encoding="utf-8") as stream:
            for cut in sorted(index):
                stream.write(json.dumps(index[cut], ensure_ascii=False) + "\n")
    if args.limit is None:
        (directory / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()

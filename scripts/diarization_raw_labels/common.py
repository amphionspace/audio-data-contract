"""Shared helpers for registering diarization teacher labels as dataset versions.

Raw teacher output (one JSON object per source recording or per window, as written by the amphion-data `diarize`
pipeline) becomes `audio-record/1.0` rows: `audio_slots[0].ref` names the recording in the parent version, `target` is
the speaker-attributed transcript rendered from the segments (`[S1][start-end] text`), and everything else the teacher
returned stays in `metadata.<teacher>`. Lhotse supervisions keep their canonical fields and carry the extra
provenance in `custom.<name>`. Local file paths in the rows (audio, raw-response and run directories) are dropped.
"""

import copy
import gzip
import hashlib
import json
import os
import re
from pathlib import Path

from audio_data_contract.declarations import write_declarations

PERSONAL = re.compile(r"/workspace/workspace/[\w.-]+")  # per-user working directories
PATH_KEYS = {"audio", "crop", "dir", "raw", "run_dir"}
RECORD_SCHEMA = "audio-record/1.0"


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 22), b""):
            digest.update(block)
    return digest.hexdigest()


def scrub(value, dropped):
    """Remove local-path fields; `dropped` counts what was removed."""
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if key in PATH_KEYS and isinstance(item, str):
                dropped[key] += 1
                continue
            out[key] = scrub(item, dropped)
        return out
    if isinstance(value, list):
        return [scrub(item, dropped) for item in value]
    if isinstance(value, str) and PERSONAL.search(value):
        dropped["path in text"] += 1
        return PERSONAL.sub("", value)
    return value


def speaker_tag(name):
    """S01 -> S1; other speaker ids are kept as they are."""
    if len(name) > 1 and name[0] == "S" and name[1:].isdigit():
        return f"S{int(name[1:])}"
    return name


def render_target(segments, offset=0.0):
    """Speaker-attributed transcript with times relative to the audio slot (`offset` = slot start in the recording)."""
    lines = []
    for seg in sorted(segments or [], key=lambda s: (s.get("start") is None, s.get("start") or 0.0)):
        text = (seg.get("text") or "").strip()
        span = "-".join("?" if seg.get(k) is None else f"{seg[k] - offset:.2f}" for k in ("start", "end"))
        lines.append(f"[{speaker_tag(str(seg.get('speaker', 'S?')))}][{span}] {text}")
    return "\n".join(lines)


def audio_slot(ref, cut_id, start=None, duration=None):
    slot = {"dataset_id": ref[0], "version": ref[1], "split": ref[2], "cut_id": cut_id}
    if start is not None:
        slot["start"] = round(start, 3)
        slot["duration"] = round(duration, 3)
    return {"name": "mixture", "ref": slot}


def record(rid, ref, cut_id, metadata, segments=None, language=None, task="diarization", start=None, duration=None,
           absolute=False):
    """`absolute`: segment times are on the whole recording, so shift them by the slot start for the target."""
    row = {"schema_version": RECORD_SCHEMA, "id": rid, "task": task,
           "audio_slots": [audio_slot(ref, cut_id, start, duration)],
           "target": render_target(segments, start if absolute and start else 0.0)}
    if language:
        row["language"] = language
    if segments:
        row["labels"] = {"speaker_count": len({s.get("speaker") for s in segments})}
    row["metadata"] = metadata
    return row


def read_jsonl(path):
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


class Writer:
    """Write rows to `<name>.jsonl.gz` (deterministic gzip), then read the file back for count, bytes, sha256."""

    def __init__(self, out_dir, filename):
        self.final = Path(out_dir) / filename
        self.tmp = self.final.with_name(self.final.name + ".tmp")
        self.count = 0
        self.ids = set()
        self.raw = open(self.tmp, "wb")  # noqa: SIM115 - closed in close()
        self.gz = gzip.GzipFile(fileobj=self.raw, mode="wb", mtime=0, compresslevel=6)

    def write(self, row, unique_key="id"):
        key = row.get(unique_key)
        if key is not None:
            if key in self.ids:
                raise SystemExit(f"{self.final.name}: duplicate {unique_key} {key}")
            self.ids.add(key)
        self.gz.write((json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8"))
        self.count += 1

    def close(self):
        self.gz.close()
        self.raw.close()
        self.tmp.replace(self.final)
        with gzip.open(self.final, "rt", encoding="utf-8") as stream:  # the gzip CRC catches lost writes
            back = sum(1 for _ in stream)
        if back != self.count:
            raise SystemExit(f"{self.final}: read back {back} rows, wrote {self.count}")
        return self.count


def artifact(name, kind, dataset, version, filename, count, out_dir, metadata=None):
    path = Path(out_dir) / filename
    return {"name": name, "kind": kind, "root_alias": "aidc_data",
            "relative_path": f"datasets/{dataset}/versions/{version}/{filename}",
            "expected_bytes": path.stat().st_size, "sha256": sha256(path),
            "metadata": ({} if count is None else {"record_count": count}) | (metadata or {})}


def parent_artifacts(catalog, dataset, version, names):
    spec = catalog.get(dataset, version).to_dict()
    by_name = {a["name"]: a for a in spec["artifacts"]}
    return [copy.deepcopy(by_name[n]) for n in names]


def make_dir(root, dataset, version):
    out_dir = Path(root) / "datasets" / dataset / "versions" / version
    if out_dir.exists():
        raise SystemExit(f"{out_dir} exists; versions are immutable")
    old = os.umask(0o002)
    try:
        out_dir.mkdir(parents=True)
    finally:
        os.umask(old)
    return out_dir


def declaration(dataset, version, languages, tasks, artifacts, splits, provenance, recipe=None):
    entry = {"schema_version": "dataset-catalog/2.0", "dataset_id": dataset, "version": version,
             "languages": languages, "tasks": tasks, "aliases": [], "artifacts": artifacts, "splits": splits,
             "provenance": provenance}
    if recipe:
        entry["recipe_parameters"] = recipe
    return entry


def provenance(parent, description, status="prepared", ready=True, facts=None, **extra):
    out = {"preparation_status": status, "lineage_status": "exact", "materialization": "full",
           "source": parent, "description": description}
    if not ready:
        out["ready_for_training"] = False
    out.update(extra)
    if facts:
        out["facts"] = dict(facts)
    return out


def view(dataset, topic, version, parent_version, transforms, registered_at="2026-11-03"):
    return {"schema_version": "dataset-view/1.0", "view_id": f"{dataset}/{topic}", "version": version,
            "source": {"dataset_id": dataset, "version": parent_version},
            "result": {"dataset_id": dataset, "version": version},
            "materialization": "full", "lineage_status": "exact", "transforms": transforms,
            "provenance": {"registered_at": registered_at}}


def transform(name, version, kind, writes, overrides=None, **parameters):
    step = {"name": name, "version": version, "kind": kind, "writes": writes}
    if overrides:
        step["overrides"] = overrides
    step["parameters"] = parameters
    return step


def save(catalog_path, views_path, declarations, views, header):
    """Write both files with a one-line Chinese header; the JSON round trip keeps shared dicts from becoming anchors."""
    for path, rows, topic in ((catalog_path, declarations, "数据声明"), (views_path, views, "血缘声明")):
        write_declarations(path, json.loads(json.dumps(rows)))
        body = Path(path).read_text(encoding="utf-8")
        Path(path).write_text(f"# {header}（{topic}）\n{body}", encoding="utf-8")


def winning_rows(paths):
    """(file index, row index) of the row kept per recording id: the last one, unless a later retry failed."""
    best = {}
    for p, path in enumerate(paths):
        for n, row in enumerate(read_jsonl(path)):
            ok = row.get("status") == "ok"
            old = best.get(row["recording_id"])
            if old is None or ok or not old[2]:
                best[row["recording_id"]] = (p, n, ok)
    return {(p, n) for p, n, _ in best.values()}


def label_rows(paths, ref, name, dropped, counters, extra=None, id_of=None, lookup=None, keep=None):
    """Teacher label rows (one per recording, or per window crop when `lookup` maps crop id -> window) -> records."""
    paths = [paths] if isinstance(paths, (str, Path)) else paths
    for p, path in enumerate(paths):
        for n, row in enumerate(read_jsonl(path)):
            if keep is not None and (p, n) not in keep:
                counters["earlier rows replaced by a retry"] += 1
                continue
            rid = row["recording_id"]
            segments = row.get("segments") or []
            payload = scrub({k: v for k, v in row.items() if k != "recording_id"}, dropped)
            if extra and rid in extra:
                payload.update(extra[rid])
            counters["rows"] += 1
            counters[f"status {row.get('status')}"] += 1
            counters["segments"] += len(segments)
            if lookup is None:
                yield record(id_of(rid) if id_of else rid, ref, rid, {name: payload}, segments)
                continue
            window = lookup.get(rid)
            if window is None:
                counters["crops without a known window"] += 1
                yield record(rid, ref, rid.rsplit("-w", 1)[0], {name: payload}, segments)
                continue
            yield record(rid, ref, window[0], {name: payload}, segments, start=window[1], duration=window[2] - window[1])


def window_rows(paths, ref, name, dropped, counters):
    """Window verdicts (kept / rejected, checks, segments) -> records; the audio slot is the window."""
    for path in paths:
        for row in read_jsonl(path):
            payload = scrub({k: v for k, v in row.items() if k not in ("recording_id", "id")}, dropped)
            counters["rows"] += 1
            counters["kept" if row.get("kept") else "rejected"] += 1
            yield record(row["id"], ref, row["recording_id"], {name: payload}, row.get("segments") or [],
                         start=row["start"], duration=row["end"] - row["start"], absolute=True)


def window_lookup(paths):
    """window id -> (recording id, start, end)"""
    return {row["id"]: (row["recording_id"], row["start"], row["end"]) for path in paths for row in read_jsonl(path)}


def merged_rows(paths, ref, name, dropped, counters):
    """merge_local rows (usable / excluded segments with checks, per recording) -> records; target = usable segments."""
    for path in paths:
        for row in read_jsonl(path):
            payload = scrub({k: v for k, v in row.items() if k != "recording_id"}, dropped)
            counters["rows"] += 1
            counters["usable"] += len(row["usable"])
            counters["excluded"] += len(row["excluded"])
            yield record(row["recording_id"], ref, row["recording_id"], {name: payload}, row["usable"])



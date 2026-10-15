#!/usr/bin/env python3
"""Register the WenetSpeech COS mirror on aidc as a localized registry catalog.

The AIDC migration excluded the WenetSpeech family. Its legacy_asr files were
later mirrored to cos://amphion-audio-backup-1373259071/audio-data-contract/
datasets/wenetspeech/ and pulled with ab (per-file ETag checks) to
<root>/datasets/wenetspeech/source/cos-backup-20261011/. This script reads the
versions listed in that mirror's registry/registered-wenetspeech-versions.json
from catalog/, rewrites old absolute paths in recordings and cuts manifests
(deterministic gzip, path fields only), checks that every referenced file
exists, and writes registry declarations with root_alias aidc_data.

    python scripts/restore_wenetspeech.py --root /workspace/data \
        --output /workspace/data/registry/catalog/wenetspeech.yaml \
        --record /workspace/data/migration/wenetspeech-cos-20261011
"""

import argparse
import copy
import gzip
import hashlib
import io
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cos_relocate import relocate_item

from audio_data_contract.declarations import (
    declaration_files,
    read_declarations,
    write_declarations,
)

SOURCE = "datasets/wenetspeech/source/cos-backup-20261011"
MIRROR = "cos://amphion-audio-backup-1373259071/audio-data-contract/datasets/wenetspeech/"
REWRITE = {"lhotse-recordings", "lhotse-cuts"}
# Same TEST_NET/TEST_MEETING manifests as wenetspeech@eval-20261011 in the
# registry (catalog/zh_asr_eval.yaml), which already reads this mirror.
SKIP = {("wenetspeech", "eval-20260804"), ("wenetspeech_test_net", "eval-20260804"),
        ("wenetspeech_test_meeting", "eval-20260804")}
# Old cluster prefixes and their aidc locations. AudioSet road noise (used by
# the traffic eval cuts) was moved by the AIDC migration, see its path-map.jsonl.
PREFIXES = {
    "/ai_sds_wuzz/DATA_ASR/": SOURCE + "/legacy_asr/",
    "/ai_sds_wuzz/MULTILINGUAL_DATA/sound/": "datasets/audioset_road_traffic/source/sound-850ed0a8/",
}


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 22), b""):
            digest.update(block)
    return digest.hexdigest()


def rewrite(root, relative):
    """Rewrite one legacy_asr manifest; return its facts and referenced files."""
    root = Path(root)
    source = root / SOURCE / "legacy_asr" / relative
    target = root / SOURCE / "relocated" / relative
    referenced = set()

    def resolve(value):
        for old, new in PREFIXES.items():
            if value.startswith(old):
                local = str(root / new / value[len(old):])
                referenced.add(local)
                return local
        raise ValueError(f"unmapped path in {relative}: {value}")

    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    count = 0
    with gzip.open(source, "rt", encoding="utf-8") as lines, temporary.open("wb") as raw:
        compressed = gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0)
        out = io.TextIOWrapper(compressed, encoding="utf-8")
        for line in lines:
            if line.strip():
                item = relocate_item(json.loads(line), resolve)
                out.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n")
                count += 1
        out.flush()
        out.detach()
        compressed.close()
    temporary.replace(target)
    return relative, {
        "path": str(target.relative_to(root)),
        "bytes": target.stat().st_size,
        "sha256": sha256(target),
        "records": count,
        "original_bytes": source.stat().st_size,
        "original_sha256": sha256(source),
    }, sorted(referenced)


def original(root, relative):
    path = Path(root) / SOURCE / "legacy_asr" / relative
    return relative, {"path": str(path.relative_to(root)), "bytes": path.stat().st_size, "sha256": sha256(path)}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, default=Path(__file__).resolve().parent.parent / "catalog")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=32)
    args = parser.parse_args()
    root = args.root

    listed = json.loads((root / SOURCE / "registry/registered-wenetspeech-versions.json").read_text())
    wanted = {(row["dataset_id"], row["version"]) for row in listed} - SKIP
    specs = [row for path in declaration_files(args.catalog) for _, row in read_declarations(path)
             if (row["dataset_id"], row["version"]) in wanted]
    if len(specs) != len(wanted):
        raise SystemExit(f"catalog has {len(specs)} of {len(wanted)} mirrored versions")
    artifacts = [a for spec in specs for a in spec["artifacts"]]
    if any(a["root_alias"] != "legacy_asr" for a in artifacts):
        raise SystemExit("only legacy_asr artifacts are mirrored")

    # Published integrity facts must match the restored originals.
    for artifact in artifacts:
        path = root / SOURCE / "legacy_asr" / artifact["relative_path"]
        if artifact.get("expected_bytes") not in (None, path.stat().st_size):
            raise SystemExit(f"size mismatch: {path}")
        if artifact.get("sha256") and sha256(path) != artifact["sha256"]:
            raise SystemExit(f"sha256 mismatch: {path}")

    rewritten = sorted({a["relative_path"] for a in artifacts if a["kind"] in REWRITE})
    kept = sorted({a["relative_path"] for a in artifacts if a["kind"] not in REWRITE} - set(rewritten))
    facts, referenced = {}, set()
    with ProcessPoolExecutor(args.workers) as pool:
        for relative, fact, files in pool.map(rewrite, [root] * len(rewritten), rewritten):
            facts[relative] = fact
            referenced.update(files)
            print(json.dumps({"rewritten": relative, "records": fact["records"]}), flush=True)
        for relative, fact in pool.map(original, [root] * len(kept), kept):
            facts[relative] = fact

    with ThreadPoolExecutor(64) as pool:
        missing = [p for p, ok in zip(sorted(referenced), pool.map(os.path.isfile, sorted(referenced))) if not ok]
    args.record.mkdir(parents=True, exist_ok=True)
    (args.record / "relocated-manifests.json").write_text(json.dumps(facts, ensure_ascii=False, indent=1) + "\n")
    (args.record / "missing-references.json").write_text(json.dumps(missing, ensure_ascii=False, indent=1) + "\n")
    if missing:
        raise SystemExit(f"{len(missing)} of {len(referenced)} referenced files are missing; see {args.record}")

    output = []
    for spec in specs:
        spec = copy.deepcopy(spec)
        for artifact in spec["artifacts"]:
            fact = facts[artifact["relative_path"]]
            artifact["root_alias"] = "aidc_data"
            artifact["relative_path"] = fact["path"]
            artifact["expected_bytes"] = fact["bytes"]
            artifact["sha256"] = fact["sha256"]
            if "records" in fact and "record_count" in artifact.get("metadata", {}):
                artifact["metadata"]["record_count"] = fact["records"]
        spec.setdefault("provenance", {})["restored_from"] = MIRROR
        output.append(spec)
    write_declarations(args.output, output)
    summary = {"versions": len(output), "artifacts": len(artifacts), "rewritten_manifests": len(rewritten),
               "kept_manifests": len(kept), "referenced_files": len(referenced), "missing": 0}
    (args.record / "verification.json").write_text(json.dumps(summary, indent=1) + "\n")
    print(json.dumps(summary))


if __name__ == "__main__":
    main()

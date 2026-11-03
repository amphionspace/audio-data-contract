#!/usr/bin/env python3
"""Select the Americas-accent rows of Common Voice Spanish into new manifests.

A row is kept only when its accent field is made of the Common Voice preset
Americas labels below. Rows with Spain/Philippines labels, free-text accents or
no accent are dropped. Prints per-split and per-region counts and hours.
"""

import argparse
import collections
import gzip
import hashlib
import json
from pathlib import Path

AMERICAS = {
    "México": "mexico",
    "América central": "central_america",
    "Caribe: Cuba, Venezuela, Puerto Rico, República Dominicana, Panamá, "
    "Colombia caribeña, México caribeño, Costa del golfo de México": "caribbean",
    "Andino-Pacífico: Colombia, Perú, Ecuador, oeste de Bolivia y Venezuela andina": "andean",
    "Rioplatense: Argentina, Uruguay, este de Bolivia, Paraguay": "rioplatense",
    "Chileno: Chile, Cuyo": "chilean",
}


def regions(accents):
    """Return the preset Americas regions, or None if anything else remains."""
    rest, found = accents, []
    for label in sorted(AMERICAS, key=len, reverse=True):
        if label in rest:
            found.append(AMERICAS[label])
            rest = rest.replace(label, "")
    return sorted(found) if found and not rest.replace(",", "").strip() else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="legacy manifests directory")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    report = {}
    for split in ("train", "dev", "test"):
        kept, hours = set(), collections.Counter()
        src = args.source / f"cv-es_supervisions_{split}.jsonl.gz"
        dst = args.output / f"cv-es-americas_supervisions_{split}.jsonl.gz"
        with gzip.open(src, "rt") as fin, gzip.open(dst, "wt") as fout:
            for line in fin:
                row = json.loads(line)
                found = regions((row.get("custom") or {}).get("accents") or "")
                if found:
                    kept.add(row["recording_id"])
                    hours["+".join(found)] += row["duration"] / 3600
                    fout.write(line)
        src = args.source / f"cv-es_recordings_{split}.jsonl.gz"
        dst = args.output / f"cv-es-americas_recordings_{split}.jsonl.gz"
        with gzip.open(src, "rt") as fin, gzip.open(dst, "wt") as fout:
            fout.writelines(l for l in fin if json.loads(l)["id"] in kept)
        report[split] = {"rows": len(kept), "hours": round(sum(hours.values()), 4),
                         "hours_by_region": {k: round(v, 4) for k, v in sorted(hours.items())}}
    for path in sorted(args.output.iterdir()):
        report[path.name] = {"bytes": path.stat().st_size,
                             "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    print(json.dumps(report, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()

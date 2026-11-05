"""List ts_real_train target-absent records whose enrolled speaker actually talks inside the window.

The v2/v3 builders draw an "other_recording" enrollment from another meeting without excluding the window's speakers;
AliMeeting / AISHELL-4 / RAMC speaker ids are global, so the same person can attend both meetings. Speakers in a
window come from the corpus transcripts (load_corpus of build_ts_real_train.py), not from the record, so v3 (no
window_utts) is checked too. Writes one TSV per (version, split) with `record id<TAB>seconds the enrolled speaker
talks in the window` for the records where it is above 0, and report.json with the tallies.

    python scan_enrolled_in_window.py --catalog CATALOG --roots ROOTS.json --versions-dir DIR/ts_real_train/versions \
        --output OUT_DIR
"""

import argparse
import gzip
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "src"), str(REPO / "scripts/ts_real"), str(REPO / "scripts/ts_robust")]
from audio_data_contract import load_catalog

spec = importlib.util.spec_from_file_location("builder", REPO / "scripts/ts_robust/build_ts_real_train.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)

JOBS = [
    ("v1-20261017-utts", "alimeeting", "alimeeting"), ("v1-20261017-utts", "aishell4", "aishell4"),
    ("v1-20261017-utts", "ramc", "ramc"), ("v2-20261018", "alimeeting", "alimeeting"),
    ("v2-20261018", "aishell4", "aishell4"), ("v2-20261018", "ramc", "ramc"),
    ("v3-20261020", "alimeeting_en_mn", "alimeeting"), ("v3-20261020", "alimeeting_en_mf", "alimeeting"),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--roots", type=Path, required=True)
    parser.add_argument("--versions-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    roots = {k: Path(v) for k, v in json.loads(args.roots.read_text()).items()}
    catalog = load_catalog(args.catalog)
    corpora, report = {}, {}
    for version, split, corpus in JOBS:
        if corpus not in corpora:
            corpora[corpus] = builder.load_corpus(*builder.CORPORA[corpus], catalog, roots)
        recs = corpora[corpus]
        bad, tally = [], Counter()
        with gzip.open(args.versions_dir / version / f"records_{split}.jsonl.gz", "rt") as stream:
            for line in stream:
                r = json.loads(line)
                if r["labels"].get("target_present") is not False:
                    continue
                tally["neg"] += 1
                tally[r["labels"].get("absent_source")] += 1
                rid, lo = r["labels"]["recording"], r["metadata"]["window_start_s"]
                hi = lo + r["labels"]["duration_s"]
                enrolled = r["metadata"]["target_speaker"].split(":", 1)[1]
                talks = sum(max(0.0, min(e, hi) - max(s, lo)) for s, e, spk, _ in recs[rid]["sups"] if spk == enrolled)
                if talks > 0:
                    bad.append(f'{r["id"]}\t{talks:.2f}')
                    tally["enrolled_talks_in_window"] += 1
                    tally["talks>=0.3s"] += talks >= 0.3
        (args.output / f"{version}--{split}.tsv").write_text("".join(i + "\n" for i in bad))
        report[f"{version}/{split}"] = dict(tally)
        print(version, split, dict(tally), flush=True)
    (args.output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n")


if __name__ == "__main__":
    main()

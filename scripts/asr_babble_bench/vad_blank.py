#!/usr/bin/env python3
"""FSMN-VAD speech spans of the TD-Tech blank candidates cut by ``build_blank.py candidates``.

Runs in an environment with FunASR (here ``dolphin``); writes ``vad.jsonl`` next to ``candidates.jsonl``:
one row per cut with ``speech`` as [[start_ms, end_ms], ...]. ``build_blank.py render`` quarantines cuts whose
speech adds up to the recipe's ``vad_max_speech_seconds``.

    python vad_blank.py <tdtech-candidates dir> [--model /workspace/model/fsmn-vad]
"""

import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("cuts", type=Path)
    parser.add_argument("--model", default="/workspace/model/fsmn-vad")
    parser.add_argument("--device", default="cpu")
    args = parser.parse_args()
    from funasr import AutoModel

    model = AutoModel(model=args.model, device=args.device, disable_update=True)
    rows = [json.loads(line) for line in (args.cuts / "candidates.jsonl").open(encoding="utf-8")]
    out = args.cuts / "vad.jsonl"
    with out.open("w", encoding="utf-8") as stream:
        for row in rows:
            result = model.generate(input=str(args.cuts / f"{row['cut_id']}.wav"))
            spans = result[0]["value"] if result else []
            stream.write(json.dumps({"cut_id": row["cut_id"], "speech": spans}) + "\n")
    print(f"{len(rows)} cuts -> {out}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Run `amphion-data clean` (HTTP backend, Qwen3-ASR-1.7B + MOSS-Transcribe-Diarize) per dataset and record the status.

Produced the 2026-10-08/09 clean-dual-qwen-moss versions. The HTTP workers skip ids already present in
workdir/_infer_*.jsonl, so a stopped run resumes. inputs.json maps each dataset to its supervisions and recordings
manifests ({dataset: {"supervisions": {"path": ...}, "recordings": {"path": ...}, "pilot": {"path": ...}}}).

    python scripts/zh_source_clean/run_clean.py --run-dir RUN --amphiondata CHECKOUT --python PYTHON \
        --config CHECKOUT/configs/experiments/zh-source-clean-qwen-moss.toml full aishell2 kespeech
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--run-dir", type=Path, required=True, help="holds inputs.json; outputs go below it")
parser.add_argument("--amphiondata", type=Path, required=True, help="amphiondata checkout at the registered commit")
parser.add_argument("--python", required=True, help="interpreter of the environment that runs amphiondata")
parser.add_argument("--config", type=Path, required=True)
parser.add_argument("--workers", type=int, default=256)
parser.add_argument("--io-workers", type=int, default=16)
parser.add_argument("stage", choices=["pilot", "full"])
parser.add_argument("datasets", nargs="*")
args = parser.parse_args()

run = args.run_dir
inputs = json.loads((run / "inputs.json").read_text())
datasets = args.datasets or list(inputs)
status_path = run / f"{args.stage}-status.json"
status = json.loads(status_path.read_text()) if status_path.exists() else {}


def save():
    # Several drivers may run different datasets of one stage; merge on write.
    merged = json.loads(status_path.read_text()) if status_path.exists() else {}
    merged.update({d: status[d] for d in datasets if d in status})
    tmp = status_path.with_name(f"{status_path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n")
    tmp.replace(status_path)


env = dict(os.environ)
env["PYTHONPATH"] = str(args.amphiondata / "src")
commit = subprocess.check_output(["git", "-C", str(args.amphiondata), "rev-parse", "HEAD"], text=True).strip()
dirty = bool(subprocess.check_output(["git", "-C", str(args.amphiondata), "status", "--porcelain"], text=True).strip())
for dataset in datasets:
    entry = inputs[dataset]
    source = entry["pilot"]["path"] if args.stage == "pilot" else entry["supervisions"]["path"]
    out_dir = run / ("pilot" if args.stage == "pilot" else "") / dataset
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        args.python, "-c",
        "import sys; from amphiondata.cli import main; sys.argv[0]='amphion-data'; main()",
        "--config", str(args.config), "clean", source, "-o", str(out_dir),
        "--backend", "http", "-r", entry["recordings"]["path"],
        "-w", str(args.workers), "--io-workers", str(args.io_workers),
    ]
    record = {
        "dataset": dataset, "input": source, "output": str(out_dir), "command": cmd[3:],
        "code_commit": commit, "code_dirty": dirty, "started": time.time(),
        "state": "running", "pid": os.getpid(),
    }
    status[dataset] = record
    save()
    with open(out_dir / "clean.log", "a", encoding="utf-8") as log:
        rc = subprocess.call(cmd, env=env, stdout=log, stderr=subprocess.STDOUT)
    record.update(ended=time.time(), exit_code=rc, state="complete" if rc == 0 else "failed")
    save()
    if rc != 0:
        sys.exit(rc)

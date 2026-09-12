#!/usr/bin/env python3
"""Finish and register this batch after its extraction workers exit successfully."""

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from extract import DATASETS, VERSION, paths, save


def progress(root, base):
    report = {}
    for dataset in DATASETS:
        work, final = paths(root, dataset)
        directory = final if final.exists() else work
        state = json.loads((directory / "state.json").read_text()) if (directory / "state.json").exists() else {}
        prepared = final.exists() and (final / "registration.json").exists()
        count = 0
        size = 0
        for receipt in (directory / "inventories").glob("*.complete.json"):
            receipt = json.loads(receipt.read_text())
            count += receipt["audio_files"]
            size += receipt["extracted_bytes"]
        report[dataset] = {"phase": "prepared" if prepared else state.get("state", "pending"),
                           "completed_archive_audio_files": count, "completed_archive_bytes": size,
                           "records": state.get("metadata", {}).get("records", {})}
    save(base / "summary.json", report)
    labels = {"prepared": "已处理，等待或已完成登记", "extracted": "解压完成，等待生成清单",
              "partial": "解压及音频头统计中", "failed": "失败，见日志", "pending": "等待中"}
    content = ["# 说话人数据处理进度", "", "更新时间：" + datetime.now(timezone.utc).isoformat(), "",
               "| 数据集 | 状态 | 已完成归档的音频数 | 生成记录数 |", "|---|---|---:|---:|"]
    for dataset, row in report.items():
        content.append(f"| {dataset} | {labels[row['phase']]} | {row['completed_archive_audio_files']:,} | {sum(row['records'].values()):,} |")
    content.extend(["", "音频数只累计已完整解压的归档；处理中的归档进度见各数据集 `*-extract.log`。",
                    "全部登记和项目检查完成后生成 `complete.json`。"])
    (base / "progress.md").write_text("\n".join(content) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--roots", type=Path, required=True)
    args = parser.parse_args()
    root = Path(json.loads(args.roots.read_text())["legacy_asr"])
    base = root / "downloads/speaker-preparation-20260912"
    done = set()
    while len(done) < len(DATASETS):
        progress(root, base)
        for dataset in DATASETS:
            if dataset in done:
                continue
            # A pre-existing worker (started interactively) owns its conversion
            # until its exit marker appears. Other conversions run serially here.
            session = subprocess.run(["tmux", "has-session", "-t", "speaker-prepare-" + dataset],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            if session.returncode == 0:
                continue
            exit_path = base / (dataset + "-extract.exit")
            if not exit_path.exists():
                continue
            if exit_path.read_text().strip() != "0":
                raise RuntimeError(f"extraction failed: {dataset}; see {base / (dataset + '-extract.log')}")
            command = [sys.executable, "-u", str(args.repo / "scripts/speaker/prepare.py"),
                       dataset, "--repo", str(args.repo), "--roots", str(args.roots), "--register"]
            print("preparing", dataset, flush=True)
            with (base / (dataset + "-prepare.log")).open("a") as log:
                result = subprocess.run(command, cwd=args.repo, stdout=log, stderr=subprocess.STDOUT, check=False)
            (base / (dataset + "-prepare.exit")).write_text(str(result.returncode) + "\n")
            result.check_returncode()
            subprocess.run(["audio-data-contract", "generate-overview"], cwd=args.repo, check=True)
            done.add(dataset)
            print("registered", dataset, flush=True)
            progress(root, base)
        if len(done) < len(DATASETS):
            time.sleep(30)
    for command in [
        ["audio-data-contract", "validate-catalog", "catalog"],
        ["audio-data-contract", "validate-views", "views", "catalog"],
        ["audio-data-contract", "generate-overview", "--check"],
        [str(args.repo / ".venv/bin/ruff"), "check", "."],
        [sys.executable, "-m", "pytest", "-q"],
    ]:
        subprocess.run(command, cwd=args.repo, check=True)
    save(base / "complete.json", {"completed_at": datetime.now(timezone.utc).isoformat(),
                                  "datasets": list(DATASETS), "version": VERSION,
                                  "validation": "audio headers, all records, references, gzip CRC, catalog, views, overview, ruff and pytest passed"})
    progress(root, base)


if __name__ == "__main__":
    main()

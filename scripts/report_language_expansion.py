#!/usr/bin/env python3
"""Write a live summary of language-expansion downloads without changing catalog."""

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path


def report(work):
    plans = {}
    for name in ("hf-plan.json", "http-plan.json"):
        plans.update(json.loads((work / name).read_text()))
    summaries = []
    for path in sorted(work.glob("*/state.json")):
        state = json.loads(path.read_text())
        source = state.get("artifacts", {}).get("source", {})
        summaries.append({
            "dataset": state["dataset_id"],
            "state": state["state"],
            "pause_reason": state.get("metadata", {}).get("pause_reason"),
            "verified_files": source.get("verified_files", 0),
            "expected_files": source.get("expected_files", 0),
            "verified_bytes": source.get("verified_bytes", 0),
            "expected_bytes": source.get("expected_bytes", 0),
            "failed_files": len(state.get("metadata", {}).get("failures", {})),
            "destination": source.get("path"),
            "state_file": str(path),
            "updated_at": state["updated_at"],
        })
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    pause_file = work / "storage-quota-pause.json"
    pause = json.loads(pause_file.read_text()) if pause_file.exists() else {}
    usage_file = work / "storage-usage.json"
    usage = json.loads(usage_file.read_text()) if usage_file.exists() else {}
    result = {
        "updated_at": now, "datasets": summaries,
        "storage_pause": pause, "storage_usage_snapshot": usage,
    }
    temporary = work / "summary.json.tmp"
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(work / "summary.json")
    labels = {
        "downloading": "下载中", "verified": "下载和校验完成",
        "partial": "部分完成，有失败文件", "waiting_auth": "等待授权",
        "failed": "失败", "planned": "待启动",
    }
    lines = [
        "# 语种数据补充进度", "", f"更新时间：{now}", "",
    ]
    if pause_file.exists() and pause.get("active", True):
        lines += [
            "**下载已暂停：等待核实目录或账号的实际存储配额。**",
            "暂停标记会拦截新启动的下载；运行中的传输需单独停止。",
            "共享文件系统的剩余容量不能作为本次下载的可用额度。", "",
        ]
    if usage:
        lines += [
            (
                "相关目录和缓存实占快照："
                f"{usage['total_allocated_bytes'] / 1e9:.3f} GB。"
                "包含未完成文件、既有 AISHELL-5 文件及共享 HF 缓存，"
                "不能全部算作本次新增，也不代表整个配额的已用量。"
            ),
            "",
        ]
    lines += [
        "按完成校验的文件统计；正在传输的文件不计入已完成字节。",
        "源包包含的小时数不等于可商用、地区已筛选或去重后的训练小时数。", "",
        "| 数据 | 状态 | 校验文件/计划 | 已校验 GB/计划 GB | 失败文件 |",
        "|---|---|---:|---:|---:|",
    ]
    for item in summaries:
        label = labels.get(item["state"], item["state"])
        if item["pause_reason"] == "storage_quota_unverified":
            label = "已暂停，待核实存储配额"
        lines.append(
            f"| {item['dataset']} | {label} | "
            f"{item['verified_files']}/{item['expected_files']} | "
            f"{item['verified_bytes'] / 1e9:.3f}/"
            f"{item['expected_bytes'] / 1e9:.3f} | {item['failed_files']} |"
        )
    lines += ["", "## 数据目录", ""]
    for name, plan in plans.items():
        lines.append(f"- {name}: `{plan['destination']}`")
    lines += [
        "", "Common Voice 西语和葡语需要 Mozilla Data Collective 授权。",
        "CIEMPIESS 原版的独立下载日志：`ciempiess_original.log`。", "",
        "每套数据的 `verified.jsonl` 保存上游/本地哈希和已校验文件记录；",
        "`state.json` 保存机器可读状态。`verified` 只表示下载和文件校验完成。",
        "所有小时统计、地区筛选和训练准备状态需要分别确认。", "",
    ]
    temporary = work / "progress.md.tmp"
    temporary.write_text("\n".join(lines))
    temporary.replace(work / "progress.md")
    return summaries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    parser.add_argument("--watch", action="store_true")
    args = parser.parse_args()
    while True:
        summaries = report(args.work)
        if not args.watch or not any(
            item["state"] == "downloading" for item in summaries
        ):
            break
        time.sleep(30)


if __name__ == "__main__":
    main()

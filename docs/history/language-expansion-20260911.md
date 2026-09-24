# 英语、美洲西语、巴西葡语和中文数据补充

2026-09-11 已启动补充下载，随后按用户的存储限额要求停止了所有仍在传输的本次任务，保留文件和断点。当前环境只能读取共享 GPFS 的整体容量，无法读取账号或目录配额；实际可用额度确认前不恢复下载。Common Voice 西语和葡语仍等待 Mozilla Data Collective 授权。

结果见下载进度（`/ai_sds_wuzz/MULTILINGUAL_DATA/downloads/language-expansion-20260911/progress.md`）和机器可读汇总（`/ai_sds_wuzz/MULTILINGUAL_DATA/downloads/language-expansion-20260911/summary.json`）。报告按完成校验的文件统计；实际占用另见 storage-usage.json（`/ai_sds_wuzz/MULTILINGUAL_DATA/downloads/language-expansion-20260911/storage-usage.json`），包含断点和缓存。暂停时停止定时报告，恢复下载时可重新启动报告进程。

原计划源文件合计约 8.755 TB，尚未包含解压、训练准备及缓存空间，不能据此直接启动全量下载。后续须按确认的剩余额度分批安排，并预留临时文件和其他任务所需空间。

| 来源 | 范围 |
|---|---|
| MuPe / CORAA-MUPE-ASR-GZ | 完整 train、validation、test 音频及标注；标注统计 365.15 小时，是否下载完成以实时状态为准 |
| MLS 葡语 | 官方 FLAC ASR 归档，包含 train/dev/test |
| Google 拉美六口音 | SLR61、71–75 的全部音频及标注；源包里的西班牙天气样本不属于美洲数据 |
| CIEMPIESS | 官方原版另通过发布方 MEGA 链接下载；同时下载官方 LIGHT 和独立 TEST 版本 |
| People’s Speech | clean、clean_sa、dirty、dirty_sa 的全部训练分区，共用验证/测试只保留一套 |
| LoquaciousSet | large 完整训练集及 dev/test；small、medium、clean 音频是子集，不重复下载 |
| YODAS-Granary | 西语和葡语全部 asr_only、ast 分区，约 4.56 TB；不包含其他语种 |
| AISHELL-5 | 续传已有 train/dev/eval1/eval2/noise 归档，保留原断点 |
| Common Voice 26 | 西语、葡语来源已登记，等待授权 |

已完成 CIEMPIESS LIGHT：16,663 条，18.424 小时，6 个文件全部通过上游哈希校验，已登记为墨西哥西语训练数据。其他来源的即时状态由上述实时报告给出。

Hugging Face 文件固定 revision，并核对上游 Git/LFS 哈希。MLS 使用官方 MD5。OpenSLR 没有公布哈希的音频归档核对文件长度和归档 CRC，并记录本地 SHA-256。`verified` 表示下载及文件完整性通过，不代表转写质量、地区筛选、商用许可或训练准备完成。

AISHELL-5 的 ELDA 镜像训练归档与既有断点长度不一致，因此改用长度匹配的官方 trmal 镜像续传。OpenSLR 与发布方的许可声明仍有差异，下载不视为商用授权确认。Common Voice 当前发布页还限制重新托管/分享数据。

本次没有将 `emilia2` 源统计量并入新增量，也没有把未知地区的西语/葡语当成美洲/巴西子集。不同数据集之间的来源重叠尚未完成去重。

## 运行与恢复

任务目录：`/ai_sds_wuzz/MULTILINGUAL_DATA/downloads/language-expansion-20260911`。

- `hf-plan.json` / `http-plan.json`：确切下载文件、版本、目标路径和校验依据。
- `<dataset>/state.json`：可按 `dataset-state/1.0` 读取的进度。
- `<dataset>/verified.jsonl`：逐文件校验记录；恢复时跳过未变化且已校验的文件。
- `<dataset>.log`：独立下载日志。
- `tools/aria2c`：本任务的 aria2 启动器，未安装或修改系统软件。
- `storage-quota-pause.json`：当前暂停标记，`active: true` 时下载脚本会在写入前退出。只有核实实际配额并确定本批容量后才能解除。
- `storage-usage.json`：停止传输后的实占空间快照；不是账号总用量或配额查询结果。

Hugging Face 下载需先安装 `huggingface_hub`（`python -m pip install huggingface_hub`）；HTTP 下载仅需 aria2。暂停检查不依赖 Hugging Face SDK。

后台下载会话以 `audio-expand-` 开头，可用 `tmux list-sessions` 查看。以下为恢复命令模板，当前会被配额暂停标记拦截；同一数据集有文件锁，不能重复启动写入。暂停标记只拦截新启动的下载，运行中的传输需单独停止。

```bash
python scripts/download_language_expansion.py \
  /ai_sds_wuzz/MULTILINGUAL_DATA/downloads/language-expansion-20260911/hf-plan.json \
  coraa_mupe --workers 3

python scripts/download_language_expansion.py \
  /ai_sds_wuzz/MULTILINGUAL_DATA/downloads/language-expansion-20260911/http-plan.json \
  google_latam --workers 1 \
  --aria2 /ai_sds_wuzz/MULTILINGUAL_DATA/downloads/language-expansion-20260911/tools/aria2c
```

报告进程只更新数据目录内的状态汇总，不在后台修改仓库 catalog。下载完成后，按实际文件统计时长和地区，再更新对应声明。

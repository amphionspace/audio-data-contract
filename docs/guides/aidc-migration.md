# 迁移已注册数据到 aidc-dev

迁移以当前 `catalog/`、`views/` YAML 和本机 `roots.json` 为输入，保留本机源文件。排除全部 WenetSpeech 系列和 `download_planned` 版本；含 WenetSpeech 依赖的版本单列为暂缓。不会下载数据，也不使用或修改 COS 上传状态库。

## 目录与状态

目标目录：

```text
/workspace/data/
  datasets/<dataset_id>/source/
  datasets/<dataset_id>/versions/<version>/
  registry/
  migration/<run_id>/
  .incoming/<run_id>/
```

同一物理文件只传一次。目标清单改写实际文件引用，保留数据集、版本和样本 ID。原始声明、清单和源路径映射保存在迁移记录中。

本机 `--work` 目录保存独立 SQLite 清单、配置、检查点和日志。`progress.json` 的文件总量在扫描结束前仍会增加；此时不能据此计算完成百分比。已发送的数据流字节也不等于已校验发布的文件字节。

## 启动

先确保目标子目录可以写入，并暂停 COS 上传及其守护进程。脚本检查到 COS 进程时会停止启动传输。

```bash
.venv/bin/python scripts/aidc_migrate.py init \
  --work state/aidc-20260923 --run aidc-20260923 \
  --host aidc-dev --destination /workspace/data
.venv/bin/python scripts/aidc_migrate.py install-receiver --work state/aidc-20260923
.venv/bin/python -u scripts/aidc_migrate.py run --work state/aidc-20260923 --tune
```

`run` 并行扫描与传输，然后执行最终校验和注册表发布。`--tune` 从 4 路开始，依次观察 8、16 路各约 60 秒的实际吞吐，记录源端 CPU 和磁盘等待，选择吞吐最高的一档。普通批次上限为 8 GiB 或 50,000 个文件，超大文件默认分为 1 GiB 的块。SSH 不压缩、不限速；源端不生成完整传输归档。

也可分别运行 `scan` 和 `transfer`。同一状态目录不应同时运行多个 scanner 或多个 uploader。2026-09-23 的任务采用独立后台进程，PID 分别记录在 `scan.pid`、`transfer.pid`、`controller.pid`；`watch` 控制进程等待它们退出，再执行最终发布。

## 进度与续传

```bash
.venv/bin/python scripts/aidc_migrate.py status --work state/aidc-20260923
tail -f state/aidc-20260923/transfer.log
```

查看 `throughput-tuning.json` 获取并发测量结果，查看 `controller.json` 获取后台任务状态。扫描中断后重跑 `scan`；传输中断后重跑 `transfer`，保留原来的 `--work`。已完成批次通过目标端回执复用，不重传源文件。被明确标为 `failed` 的批次保留错误，修复具体原因后才能重新入队。

源文件在传输前后检查大小、修改时间和物理身份；发送方与接收方计算 SHA-256。未完成批次写入 `.incoming`，校验后发布。目标端已有不同内容时拒绝覆盖。

## 验收和读取

扫描及传输全部结束后，执行：

```bash
.venv/bin/python scripts/aidc_migrate.py finalize --work state/aidc-20260923
```

最终记录位于目标端 `migration/<run_id>/`：

| 文件或目录 | 内容 |
|---|---|
| `original-registry/` | 本轮原始 YAML 声明和 roots 配置 |
| `original-manifests/` | 改写前的原始清单 |
| `path-map.jsonl` | 源路径、目标路径、大小和 SHA-256 |
| `relocated-manifests.json` | 改写前后清单校验值 |
| `excluded-versions.json` | 排除版本及依赖异常导致的暂缓版本 |
| `exceptions.json` | 扫描发现的异常 |
| `verification.json` | 最终注册表、文件覆盖和格式读取检查结果 |

最终校验包括目标清单路径、AudioRecord 索引 ID、归档成员及字节范围，目录原始登记校验值，以及每种音频格式的实际抽样读取。出现传输未完成或校验失败时不生成成功验收结果。COS 保持暂停。

验收成功后，目标端可用随迁移保存的 Python 代码读取注册表，无需源机器路径：

```bash
export PYTHONPATH=/workspace/data/migration/aidc-20260923/runtime/src:/workspace/data/migration/aidc-20260923/runtime/vendor
python3 -m audio_data_contract.cli validate-catalog /workspace/data/registry/catalog
python3 -m audio_data_contract.cli resolve /workspace/data/registry/catalog \
  police_v6_acceptance_205 v6-acceptance-20260921 test_recordings \
  --roots /workspace/data/registry/roots.json
```

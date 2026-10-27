# 评测集数据镜像（ab）

评测集（amphion-eval 的 `eval-set.yaml`）只引用数据，音频在数据盘上。**登记或更新评测集后，必须把它用到的数据集镜像到 COS**，别处的协作者才能拉到完整评测集。镜像用 `ab`，整目录原样上传到：

```text
amphion-audio-backup-1373259071:audio-data-contract/datasets/<数据集名>/
```

数据集目录里 `versions/` 是清单，`source/` 是音频，清单里的路径都相对这个目录，所以整目录镜像就是完整副本。只处理根目录就是数据集自己目录的数据集（`ts_asr_*`、`business_feedback` 等）；放在共享根（如 `aidc_data`、`legacy_asr`）下的数据集不镜像，`pending` 会把它们列为 skipped。

## 评测集的维护者：登记后同步

在放着音频的机器上（需要 `roots.json` 和 `ab` 可写该桶）：

```bash
python scripts/cos_sync_eval_sets.py pending --eval-sets /path/to/amphion-eval/src/amphion_eval/defaults/eval-sets
python scripts/cos_sync_eval_sets.py run     --eval-sets /path/to/amphion-eval/src/amphion_eval/defaults/eval-sets
```

- `run` 对每个未记录的数据集执行 `ab push`，随后做一次 `--dry-run`，要求没有待传、冲突或失败，才写入 `catalog/backups/ab-datasets.json`。
- `ab-datasets.json` 必须和数据集声明一起提交；新评测集引用的数据集不在里面，`pending` 就会列出它。
- `pending --check` 在有未镜像数据集时返回 1，可用于合并前检查。
- 中断后重跑同一命令即可续传，内容相同的文件会跳过。冲突（同名但内容不同）不会被覆盖，先确认原因。

## 协作者：在别处拉取

只需要 `ab` 和本仓库（含 `catalog/backups/ab-datasets.json`），不需要 `roots.json`：

```bash
python scripts/cos_sync_eval_sets.py pull --dest /data/eval-data                  # 全部已镜像的数据集
python scripts/cos_sync_eval_sets.py pull --dest /data/eval-data --alias ts_asr_benchmark --alias ts_asr_real
export AUDIO_DATA_ROOTS_FILE=/data/eval-data/roots.pulled.json                      # pull 结束时会打印这一行
```

`pull` 把每个数据集放到 `--dest/<数据集名>/`，并生成 `roots.pulled.json`（别名到本地目录）。已有的相同文件会跳过。

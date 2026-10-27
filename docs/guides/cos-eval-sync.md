# 评测集数据同步到 COS

amphion-eval 登记的评测集只保存数据引用，音频在本机数据盘上。`scripts/cos_sync_eval_sets.py` 找出评测集用到、但还没有 COS 绑定的数据集，补传到备份桶 `amphion-audio-backup-1373259071`。

查看待备份的数据集（读 amphion-eval 的 `src/amphion_eval/defaults/eval-sets`，对照 `catalog/backups/*.json` 里已有的 `dataset_bindings`）：

```bash
python scripts/cos_sync_eval_sets.py pending \
  --eval-sets /path/to/amphion-eval/src/amphion_eval/defaults/eval-sets
```

上传并生成绑定（需要 `COS_SecretID`、`COS_SecretKey`，能读 `roots.json` 指向的数据盘）：

```bash
python scripts/cos_sync_eval_sets.py run \
  --eval-sets /path/to/amphion-eval/src/amphion_eval/defaults/eval-sets
```

- 没有待备份的数据集时，`run` 直接退出并返回 0，可以放进数据盘所在机器的 cron，例如每天一次。
- 每次运行是一个独立快照：前缀 `audio-data-contract/v1/eval-sets-<日期>/`，绑定文件写到 `catalog/backups/cos-<日期>-eval-sets.json`。绑定文件需要提交到仓库，下次 `pending` 才会把这些数据集算作已备份。
- 中断后用同样的 `--work` 目录重跑即可续传，已上传的分块会跳过。默认的 `--work` 按日期命名，跨天续传时显式指定。
- 恢复方法同 [COS 恢复](cos-restore.md)，用对应的绑定文件作 `--binding`。
- 只处理评测集的 `validation` 和 `evaluation` 引用的数据集；训练数据不在范围内。

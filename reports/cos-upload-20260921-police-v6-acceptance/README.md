# V6 新增指令验收集：COS 补充备份

`police_v6_acceptance_205` 已完成检查、上传和完整回读核验。
本批是 **test-only 验收集**，覆盖 V6.0 的 `20260915新增` 全部 205 条指令，
不是历史术语与新增指令合并后的整套 V6.0。

| 项目 | 结果 |
|---|---|
| 音频 | 3,773 条，3.01947 小时，103 个说话人标签 |
| 指令覆盖 | 205/205，每条至少 10 个不同说话人 |
| 参数与格式 | 保留原始指令参数；全部 PCM16、16 kHz、单声道，数据载荷完整 |
| 质量口径 | 已有自动质检全部通过；本次未人工听审 |
| 备份内容 | 3,773 个音频文件、10 个清单/来源/报告文件 |
| 原始大小 | 356,974,366 bytes |
| 云端分片 | 2 个 tar.zst，共 279,014,566 bytes |
| 云端校验 | 大小、CRC64、计划标识通过；整包及全部 3,783 个文件 SHA-256 回读通过 |

两个登记版本 `v6-acceptance-20260921` 和 `icefall-20260908` 共用这份备份。

## 对象存储位置

私有桶：`amphion-audio-backup-1373259071`，地域：`ap-guangzhou`。

恢复绑定：

```text
cos://amphion-audio-backup-1373259071/audio-data-contract/v1/batches/police-v6-acceptance-205-20260921/catalog-binding.json
```

验收回执及分片位于：

```text
cos://amphion-audio-backup-1373259071/audio-data-contract/v1/batches/police-v6-acceptance-205-20260921/820ad088c2f6bfdd92d8fee7787e6c36c99fc92d10d8fd473edfc29eeb98608a/
```

此目录包含 `complete.json`、元数据 `shard-00000.tar.zst`、音频 `shard-00001.tar.zst`。
包内采用内容哈希寻址，原路径和文件对应关系保存在回执及包内索引中。

## 查询和恢复

本机及其他机器均可使用已发布的
[专用绑定](../../catalog/backups/cos-20260921-police-v6-acceptance.json)：

```bash
python scripts/cos_restore.py locate \
  --binding catalog/backups/cos-20260921-police-v6-acceptance.json \
  --work state/cos-restore-police-v6-acceptance \
  --dataset police_v6_acceptance_205@v6-acceptance-20260921 \
  --artifact test_supervisions
```

恢复过程见 [COS 恢复说明](../../docs/guides/cos-restore.md)，使用本批专用绑定。
本批通过已验收批次回执提供索引，不提供全库 final index；使用现有恢复命令时
需加 `--allow-incomplete`，恢复范围仍仅为本绑定列出的已验收文件。

本地检查点：`state/cos-backup-20260921/police-v6-acceptance-205/`。
未删除本地源文件，未修改训练或测试划分。

## 检查记录

- [本地完整性及覆盖核验](local-verification.json)
- [云端完整回读核验](remote-verification.json)

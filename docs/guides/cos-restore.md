# 从 COS 恢复数据

项目通过 [cos-20260914.json](../../catalog/backups/cos-20260914.json) 绑定本次全库同步的 **353 个数据版本**。`dataset_bindings` 按 `dataset_id@version` 登记 COS 快照前缀，以及每个 artifact 的 `root_alias:relative_path`；文件级对象路径、包内成员名和 SHA-256 来自云端已验收回执及最终恢复索引。

桶为 `amphion-audio-backup-1373259071`，地域为 `ap-guangzhou`。绑定文件也已发布到：

```text
cos://amphion-audio-backup-1373259071/audio-data-contract/v1/full-catalog-20260914/catalog-binding.json
```

**绑定表示纳入本次同步，不表示已经上传完毕。** 工具从 COS 列举 `batches/*/complete.json`，同时读取已完成的 police v5 回执；不会读取尚未验收的分块。全库 `index/*/complete.json` 发布后，自动改用其中的 `recovery-index.jsonl.gz`，补齐跨批次去重、源包成员复用、路径解析和缺口记录。恢复不依赖上传机器的 `state/`、SQLite 数据库或源文件，也不需要停止上传来更新绑定文件。

## 另一台服务器上的操作

取得本项目及上述绑定文件，安装备份依赖：

```bash
python -m pip install -e '.[backup]'
```

通过环境变量提供 `COS_SecretID`、`COS_SecretKey`，临时凭据另提供 `COS_Token`。恢复仅需要对本次备份及其复用的 police v5 对象有列举、HEAD 和读取权限；凭据不写进项目。

先建立本机恢复索引，并查询一个版本的具体产物位置：

```bash
python scripts/cos_restore.py prepare --work state/cos-restore

python scripts/cos_restore.py locate \
  --work state/cos-restore \
  --dataset police_terms_v5@icefall-20260908 \
  --artifact train_rec_0
```

`--artifact` 使用该版本 catalog 中的 artifact 名称；也可以在绑定文件的 `dataset_bindings` 中查看。文件查询返回 `cos_uri`、`member`、`container_format`、大小和 SHA-256；目录查询返回当前已验收路径数量。未验收的产物会明确返回 `not_yet_verified`，未配置的源根目录返回 `unconfigured_root`。

全库同步完成且没有缺口时，恢复到自己选择的数据盘：

```bash
python scripts/cos_restore.py restore \
  --work state/cos-restore \
  --destination /data/audio-recovery
```

上传尚未完成，或最终索引中有缺口时，默认拒绝作为完整备份恢复。明确只恢复当前可用部分时增加 `--allow-incomplete`：

```bash
python scripts/cos_restore.py restore \
  --work state/cos-restore \
  --destination /data/audio-recovery \
  --allow-incomplete
```

按原路径选择文件或目录可增加一个或多个 `--path-prefix /原机器/数据路径`。这是文件范围选择，不会自动补齐某个数据集的所有依赖；完整迁移使用全库恢复。执行前确认目标数据盘能容纳所选数据及文件索引。

## 恢复后的布局与路径迁移

例如原文件 `/ai_sds_wuzz/DATA_ASR/example/audio.wav` 会恢复为：

```text
/data/audio-recovery/files/ai_sds_wuzz/DATA_ASR/example/audio.wav
```

`/data/audio-recovery/roots.restored.json` 自动将项目根目录别名指向新位置。目录层次保持原样，音频和原始清单先按备份 SHA-256 恢复。相同内容的多个路径使用硬链接，避免重复占用数据空间；需要独立修改某份副本时应先复制或以新文件替换。

对于清单中旧机器的绝对音频路径，在所需文件恢复齐全后执行：

```bash
python scripts/cos_relocate.py \
  --work state/cos-restore \
  --destination /data/audio-recovery

export AUDIO_DATA_ROOTS_FILE=/data/audio-recovery/roots.restored.json
```

该命令迁移已识别的 Lhotse recordings/cuts（含嵌套录音、RIR、特征路径）、ShareGPT `audios`、target-ASR 的混合与注册音频路径；audio-index / AudioRef 继续通过新的 roots 配置读取。tar/dd 音频命令只按已有白名单模板改写文件参数，不执行命令，也不改动转写文本或包内成员名。相对引用使用恢复索引中的解析记录，或唯一存在的已恢复路径。找不到依赖时记录失败，保留该清单原字节。

迁移前的清单保存在 `original-manifests/`；`relocated-manifests.json` 在替换清单前记录新旧哈希，中断后可重跑迁移命令，`relocate-result.json` 记录失败及未恢复的清单数量。应先完成所需恢复，再迁移路径；迁移后的清单字节已改变，重新执行字节恢复会拒绝覆盖它们。自定义消费程序若在其他配置或脚本中硬编码了旧路径，仍需使用新的 roots 或自行更新配置。

## 校验和空间占用

- 下载前根据上传回执核对 COS 对象大小、CRC64 和计划标识；每个输出文件核对大小及 SHA-256，成功后才以正式路径发布。抽取部分成员时不宣称整包 SHA-256 回读完成。
- 已有同路径、同内容文件可复用；同一对象的全部目标文件通过本地校验后，跳过该对象的数据下载。内容不同则停止，保留原文件。恢复不会删除上传机源文件，也不会覆盖目标机已有的不同内容。
- tar.zst 和 tar/gzip/xz/bzip2 直接从下载流提取；ZIP 通过 Range 请求随机读取。原包本身需要恢复时直接写成最终数据文件，随后可复用本地原包提取成员，不另存一份下载归档。
- 本机保留恢复 SQLite 索引、当前输出文件的临时文件和必要元数据；全库恢复直接复用索引，不额外复制一份全量选择表。导入最终索引时会暂存一份新数据库，校验成功后替换旧索引。全库索引仍会随文件数量增长，不能将“不暂存整包”理解成“不需要目标数据空间”。
- `restore-result.json` 中的 `verified_available_files` / `verified_selected_files` 只表示本次输出文件通过校验。`full_index_available` 和 `known_issues` 单独说明全库索引及缺口状态。

本次绑定的生成及发布命令为：

```bash
python scripts/cos_restore.py bind \
  --work state/cos-backup-20260914/full-catalog \
  --reuse state/cos-backup-20260914/police-v5/upload/complete.json
```

此命令只上传绑定元数据，并回读验证；不会重传音频或重新启动扫描。更换备份快照时用不同的 `--binding` 文件保存新的映射。

2026-09-15 已在本机隔离目录完成云端恢复抽检：police v5 的一份训练清单（7,878 条记录）及 6 个音频，共 3,218,879 bytes，全部通过 SHA-256 校验，音频头可读取。该抽检未读取上传机的源文件或上传 SQLite 索引；还不是另一台物理服务器上的全量演练。记录见 [restore-drill-20260915.json](../../reports/cos-upload-20260914/restore-drill-20260915.json)。

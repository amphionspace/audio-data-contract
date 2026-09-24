# COS 备份执行记录（2026-09-14～15）

本文保留该批次的计划、执行命令和验收结果。下载与恢复操作见 [COS 恢复说明](../guides/cos-restore.md)。

目标为私有桶 `amphion-audio-backup-1373259071`，地域 `ap-guangzhou`，前缀 `audio-data-contract/v1/`。2026-09-14 已创建并检查桶权限，小样本已完成上传、整包 SHA-256 回读及逐文件恢复校验。

警务 v5 首批已完成备份：4.767 GB 原始内容上传为 3.949 GB，节省约 17.15% 传输字节，上传阶段耗时约 5 分 49 秒，进程峰值内存约 362.5 MiB。全库同步尚未完成；当前任务不删除训练源文件。打包流直接进入 COS，不产生需要上传后删除的本地归档。

## 打包与上传方式

| 数据形态 | 处理方式 | 空间与恢复 |
|---|---|---|
| 已有完整归档 | 原文件直接分块上传，不重新打包、压缩或复制 | 不额外占用整包空间；恢复后保持原字节 |
| 小音频、清单和元数据 | 按约 4 GiB 原始内容划分独立 tar.zst，边打包边上传 | 每片可独立恢复；失败最多重新生成当前片 |
| 多版本共享文件 | 先按文件系统身份合并引用，再以完整 SHA-256 合并内容 | 同一内容保存一次，所有原路径和版本声明保留 |
| 未完成下载、未定位路径 | 登记缺口，暂不发布为完整备份 | `.aria2` 断点文件、大小不符和不支持的依赖均阻止相应批次发布 |

首批抽取 371 个 WAV、67,162,378 bytes 测试：zstd 1 的体积为原始的 84.52%，zstd 3 为 82.22%；压缩分别耗时约 0.038 秒、0.114 秒，首次读盘耗时约 6.15 秒。因此本批选择 zstd 3；这是局部样本测量，不是全库压缩率预测。

首批使用 4 个并发的 32 MiB 分块；全库任务使用 8 个并发以增加传输吞吐，另保留当前缓冲和压缩器内存。文件内容在生成归档时再次核对 SHA-256；COS 分块与最终对象核对 CRC64，最终对象还核对长度及计划标识。分块 ETag 仅用于识别已有分块，不当作整文件 MD5。

重跑相同命令会读取本地检查点和 COS 分块列表，重新生成当前流，并跳过与已记录内容相同的分块。已验收对象通过 HEAD 复核后跳过。上传完成但响应丢失时，可从写入完成前保存的对象校验信息恢复。传输过程中不要修改源文件。

## 已冻结的首批范围

警务 v5 批次保留以下 5 个入口：

- `police_synthetic_zh_accent@v5-20260830-qc`
- `police_synthetic_zh_accent@v5-20260830-qwen75-cosy25`
- `police_terms_v5@icefall-20260908`
- `police_terms_v5_dev@icefall-20260908`
- `police_terms_v5_test@icefall-20260908`

源音频共 14,423 个、4,752,616,834 bytes，各版本共用音频只存一份。额外包含 166 个清单、元数据及仓库快照文件，共 13,962,157 bytes；总计 14,589 份内容、4,766,578,991 bytes，分为 1 个元数据片和 2 个音频片。29,012 条路径映射包含原始引用路径和解析后的路径，不能当成独立文件数或本地可释放空间。

正在使用的 `v5-20260830-qwen75-cosy25-split80-10-10` 的 train/dev/test、划分摘要和源音频均包含在首批范围。QC 源独有音频也保留。v1/v2/v3 与其他数据将在后续批次处理。

小样本验收见 [control-verification.json](../../reports/cos-upload-20260914/control-verification.json)，正式批次结果见 [police-v5-upload.json](../../reports/cos-upload-20260914/police-v5-upload.json)。3 片均通过云端大小与 CRC64 校验；元数据片已整片回读并逐文件验证 166 个成员，两个音频片各回读验证 3 个音频成员。没有再次下载整套音频。全部分片通过后已发布 `complete.json`。本机记录位于 `state/cos-backup-20260914/police-v5/`。

## 全库盘点与后续顺序

最新盘点覆盖 353 条版本声明、3,043 次直接产物引用、2,691 个逻辑路径。其中 2,601 个为文件，75 个为目录，2 个尚不存在，5 个归档带未完成下载标记，8 个路径未配置根目录。去除同文件引用后，直接文件现存约 824.14 GB，**包含未完成文件，不含目录内部和全部音频、特征依赖，不能当作最终上传量**。

详见 [inventory-summary.json](../../reports/cos-upload-20260914/inventory-summary.json)、[版本盘点](../../reports/cos-upload-20260914/versions.csv)和[缺口清单](../../reports/cos-upload-20260914/issues.csv)。

后续按以下顺序推进：

1. **已完成旧重复映射复核。** 因设备标识与旧快照不同，本轮重新读取两侧 960 个文件、213,109,505,486 bytes；480 对完整 SHA-256 全部相同，可避免重复上传 106,554,752,743 bytes（106.55 GB）。后续复用新映射时仍核对文件状态。
2. 展开 AliMeeting、target-ASR 和说话人数据的目录、音频索引及源包关系。能从已保留归档逐文件恢复的解包副本，需要先有字节一致证据，再避免重复备份。
3. 逐批展开其余 RecordingSet、CutSet、特征存储及原始归档；共享依赖只处理一次。没有替代证据的独有标注、View、划分和配方继续保留。
4. 定位 `managed_fast` / `managed_bulk` 的 8 处路径；AISHELL-5 的 5 个断点归档及待授权的 Common Voice 西/葡语保持暂缓。

重复文件复核使用 2 个工作线程，现已完成且无失败。结果见[新重复映射](../../reports/cos-upload-20260914/duplicates-reverified.csv)和[复核汇总](../../reports/cos-upload-20260914/duplicate-recheck-summary.json)，可续跑日志保存在 `state/cos-backup-20260914/duplicate-recheck/`。这项任务只读取源文件，没有上传或删除源数据。

`scripts/cos_sync_catalog.py` 为全库入口，覆盖全部版本及目录，展开 RecordingSet、嵌套 CutSet、RIR、特征存储、audio-index、ShareGPT、target-ASR 和 extraction-inventory 的文件引用。AudioRecord 通过已注册版本的 audio-index 恢复。相对路径只在候选位置唯一存在时纳入，并记录解析结果；无法解析的引用进入缺口清单。命令型音频只解析受支持的 tar/dd 模板，不执行命令。

全库扫描和上传可同时运行，通过 SQLite 保存文件状态及跨批次内容位置。相同 inode 复用已核实哈希，相同 SHA-256 和大小复用云端内容；导入 v5 回执前重新检查对象大小、CRC64 及计划标识。大于等于 128 MiB 的已有归档直接上传；其他文件按最多 5,000 个成员、约 4 GiB 原始数据流式分片。

`scripts/cos_index_archives.py` 同时读取大源包的 tar/gzip/xz/bzip2/zip 成员，流式计算成员哈希和源包哈希，不解压到磁盘。只有源包已在 COS 验收且哈希一致，才将成员位置加入去重表；随后发现的相同解包文件可复用源包。恢复索引中的 `container_format`、`object_key` 和 `member` 指明从哪个包读取哪个成员。小于 128 MiB 的包暂不做包内成员合并；不能按名称唯一恢复或无法解析的源包会记录问题，不冒认成员已备份。

目录仅展开注册的数据范围，排除凭据、缓存和未完成下载，不跟随目录符号链接。下载状态为 partial 的数据集仍同步已存在的完整文件，同时保留来源不完整标记；不会启动下载。扫描完成且所有可上传文件验收后，生成并上传 `recovery-index.jsonl.gz`，记录目录版本、全部恢复路径、对象位置及缺口。存在缺口时结果标记为 `completed_available_files_with_gaps`，不声明全库完整。

## 执行与恢复入口

跨服务器下载恢复、版本与 COS 对象查询、旧清单路径迁移见 [COS 恢复说明](../guides/cos-restore.md)。下方 `upload` 重跑命令用于继续上传，不是下载恢复。

安装：`python -m pip install -e '.[backup]'`。凭据从已有 `COS_SecretID`、`COS_SecretKey` 读取，不写入仓库或归档；可选临时令牌变量为 `COS_Token`。

```bash
python scripts/cos_backup.py plan \
  --dataset police_synthetic_zh_accent@v5-20260830-qc \
  --dataset police_synthetic_zh_accent@v5-20260830-qwen75-cosy25 \
  --dataset police_terms_v5@icefall-20260908 \
  --dataset police_terms_v5_dev@icefall-20260908 \
  --dataset police_terms_v5_test@icefall-20260908 \
  --include-file /ai_sds_wuzz/DATA_ASR/LHOTSE/synthetic/police_synthetic_zh_accent/v5-20260830-qwen75-cosy25-split80-10-10/metadata/split_summary.json \
  --include-repository \
  --output state/cos-backup-20260914/police-v5/plan.json

python scripts/cos_backup.py upload \
  state/cos-backup-20260914/police-v5/plan.json \
  --bucket amphion-audio-backup-1373259071 \
  --prefix audio-data-contract/v1/batches/police-v5-20260914
```

已有计划不能覆盖；恢复时直接运行第二条命令，保留 `upload/` 下的检查点。当前机器可通过 `PYTHONPATH=/tmp/icefall-cos-sdk-v5:src` 使用已安装的 SDK，常规环境使用上述 backup 依赖即可。

全库任务状态目录为 `state/cos-backup-20260914/full-catalog/`，目标前缀为 `audio-data-contract/v1/full-catalog-20260914/`。初始化会冻结目录声明和范围配置；目录扫描、源包索引和上传分别加锁，允许并行、禁止重复启动同一阶段。中断后使用原状态目录重跑对应命令。

```bash
python scripts/cos_sync_catalog.py init \
  --work state/cos-backup-20260914/full-catalog \
  --bucket amphion-audio-backup-1373259071 \
  --allow-root /222042021/mingdong/workspace/AmphionData/results \
  --hash-journal state/cos-backup-20260914/duplicate-recheck/verified.jsonl \
  --reuse state/cos-backup-20260914/police-v5/upload/complete.json

python scripts/cos_sync_catalog.py scan --work state/cos-backup-20260914/full-catalog
python scripts/cos_index_archives.py --work state/cos-backup-20260914/full-catalog
python scripts/cos_sync_catalog.py upload --work state/cos-backup-20260914/full-catalog --workers 8
python scripts/cos_sync_catalog.py status --work state/cos-backup-20260914/full-catalog
```

`progress.json` 保存批次间进度；`status` 默认查询已发现路径数量、批次、任务和问题，不在每批重复遍历数千万条文件记录。需要逐状态的路径数量和大小时使用 `status --count-files`。路径包含别名，不能当作唯一内容量。`batches/*/upload/complete.json` 是逐批验收回执，`result.json` 只在目录扫描、源包索引、可用文件上传和恢复索引上传结束后生成。单独某个批次的 `complete.json` 不代表全库同步完成。

2026-09-15 已修复数据库写锁竞争：三个进程通过同一个本地文件锁排队写入，并缩短扫描及回执回写事务；选批和查找源包均使用已有索引。已成功上传但尚未写回本地状态的批次，先核验云端回执再补记，不重传数据。

本机运行由状态目录内的 `supervise.py` 管理，`processes.json` 每 10 秒更新进程状态和退出码。异常退出后等待 60 秒重试，每个阶段最多启动 3 次；超过次数明确标记失败。停止整组任务时，终止 `processes.json` 中的 `supervisor_pid`，它会停止子进程，避免只停止工作进程后被自动重启。

所有分片验收后才在 COS 发布 `<批次前缀>/<计划SHA-256>/complete.json`。它包含分片 SHA-256、CRC64、文件内容哈希、全部恢复路径及数据声明；tar.zst 内部另含 `.backup/index.json`，内容成员为 `files/<文件SHA-256>`。恢复工具先核对对象大小、CRC64 和计划标识，逐文件核对 SHA-256，再按索引将内容还原到所选根目录；不能仅解压内容成员就认为旧 manifest 已能读取。只恢复部分成员时，不声称完成整片 SHA-256 回读。

本地保留计划、检查点、日志和文件索引；索引随路径数量增长，2026-09-15 主数据库约 19.4 GB，不能算作零本地占用。没有本地整包可清理；源文件释放空间仍须结合在用依赖与恢复验收另行执行。

实现依据：[COS Python 上传 API](https://www-sg.tencentcloud.com/document/product/436/46468)、[COS CRC64 校验](https://intl.cloud.tencent.com/zh/document/product/436/34078)、[官方 Python SDK](https://github.com/tencentyun/cos-python-sdk-v5)。

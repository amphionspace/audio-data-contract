# Lance 物化后端

**定位：正式的查询 / 清洗后端，JSONL 与规范 Layer 仍是权威来源。** Lance 表随时可从源 JSONL + Layer 重建；它不改变 Dataset / Layer / View 的业务身份，也不存放音频。转正还差最后一步：用真实全量数据跑验收（见文末），通过后再在 catalog 正式登记。早期试验见 [CHiME-6 试验报告](../reports/lance-pilot-20260929/README.md)。

## 快速开始

```bash
pip install -e '.[lance]'
export AUDIO_DATA_ROOTS_FILE=/path/to/roots.json   # 含 managed_fast 等根目录别名
CLI="python -m audio_data_contract.lance_cli --roots $AUDIO_DATA_ROOTS_FILE"

$CLI import records.jsonl.gz /data/managed/lance/ws-clean --source-view 'wenetspeech/clean@v1' --workers 8
$CLI verify /data/managed/lance/ws-clean/artifact.json records.jsonl.gz
$CLI export /data/managed/lance/ws-clean/artifact.json passed.jsonl.gz --clean-pass true --language zh
$CLI catalog-ref /data/managed/lance/ws-clean/artifact.json --name lance   # 输出 catalog 条目
```

也可使用安装后的 `audio-data-contract-lance` 命令。

```python
from audio_data_contract import read_artifact
from audio_data_contract.lance import LanceArtifact, RecordQuery

artifact = LanceArtifact.read("/data/managed/lance/ws-clean/artifact.json")
records = read_artifact(artifact, RecordQuery(ids=("sample-1", "sample-2")))
```

## 侧车、路径与 catalog 登记

每个已发布快照对应一个 JSON 侧车 `artifact.json`（`LanceArtifact`），记录表位置、`snapshot_version`、`record_count`、`schema_hash`、`source_view` 和重建信息（源 JSONL、规范记录流哈希、Layer 链、已声明写入字段）。

| 项 | 说明 |
| --- | --- |
| 可移植路径 | 导入时传 `--roots`（或 `roots=`），表、源 JSONL、Layer 均记为 `{root_alias, relative_path}`；换机器只需改 roots 文件。未传时沿用旧的绝对路径，旧侧车继续可读 |
| catalog | `catalog-ref` 生成 `kind: lance-table` 的 ArtifactRef，必须固定 `snapshot_version`、`record_count`、`schema_hash`；`open_catalog_artifact()` 打开时逐项核对侧车，不一致即报错 |
| 读取 | 只读固定版本，从不读 latest；格式、schema 或版本不匹配报 `ContractError` |

## 映射与索引

| 列 | 语义 | 标量索引 |
| --- | --- | --- |
| `record_json` | `AudioRecord.to_dict()` 的规范 JSON，保留全部字段 | — |
| `id` | 记录 ID | BTREE |
| `task`, `language` | 字符串投影 | BITMAP |
| `splits` | 所有音频槽位 split 的去重集合，匹配任一槽位 | LABEL_LIST |
| `clean_pass` | `metadata.clean.pass` 为布尔值时的投影，否则 null | BITMAP |
| `retained` | View 成员状态；删除只置 false，默认读取不可见 | BITMAP |

投影不是新的事实来源，回写时与完整 JSON 一起更新。映射版本 `audio-record-lance/1.0`，存储格式固定 `2.0`，依赖锁定 `pylance==12.0.0`。索引在导入发布前建好，每次 Layer 合并后增量更新。每个 fragment 最多 256Ki 行（约 9,278 万行对应约 350 个 fragment），作为训练分片单位。

导入用 `--workers N` 在子进程中并行校验和编码，输出顺序和结果与单进程完全一致；ID 去重用磁盘 SQLite，内存不随数据量增长。子进程异常退出会直接报错，不会挂起。

## 清洗 Layer 与增量回写

patch JSONL 每行：

```json
{"id":"sample-1","changes":{"target":"修正文本","metadata.clean.pass":true},"status":"keep"}
```

`status` 为 `keep` 或 `delete`；`changes` 支持 metadata/labels 的点分路径。只允许改 target、language、hotwords、metadata、labels 和 `$membership`，不允许改 ID/AudioRef。覆盖已有不同值或先前 Layer 写过的字段须声明 `overrides`；删除须声明 `$membership`。未知 ID、重复 patch、重叠路径和未声明字段都会拒绝写入。TransformStep 示例：

```json
{
  "name":"clean","version":"v1","kind":"filter-and-correct",
  "writes":["target","metadata.clean","$membership"],
  "overrides":["target","metadata.clean"],
  "parameters":{"threshold":0.8}
}
```

```bash
$CLI patch ws-clean/artifact.json patches.jsonl transform.json /data/managed/lance/clean-layer \
  --source-view 'wenetspeech/clean@v2' --tool cleaner-v1 --model actual-model-version
```

流程：先按 ID 排序、去重并发布 `patch.jsonl` + `manifest.json`（规范处理事实），再一次合并提交 Lance 版本，打 tag，最后发布该 Layer 的 `artifact.json`。patch 在磁盘上排序，按 64k 条分块校验和暂存，内存不随批次大小增长。

**内存提示**：Lance 合并时的哈希连接不能落盘，默认 150 MiB 内存池在约 20 万条 patch 时就会失败。适配器会按暂存数据大小自动设置 `LANCE_MEM_POOL_SIZE`（约为暂存大小的 4 倍）；若已手动设置该环境变量，则以手动值为准。实测在 100 万行表上，50 万条 patch 的进程峰值约 2.2 GB。更大的清洗批次建议拆成多个 Layer。

## 版本治理

| 机制 | 说明 |
| --- | --- |
| tag = 已发布 | 导入（`import`）、Layer（`layer-<清单哈希>`）、压缩（`compact-<版本>`）发布前先打 tag，再写侧车 |
| 中断恢复 | 重跑同一 Layer 的 `patch` / `materialize_layer` 即可：已提交并打 tag 的只补发侧车；父快照之后只有未打 tag 的提交时，先回滚到父快照内容再合并。父快照之后若已有其他已发布版本，则报 stale |
| `doctor` | 列出已发布与未发布版本 |
| `compact <侧车> <新侧车>` | 合并小文件、物化删除并更新索引；校验可见记录内容摘要不变后，发布等价的新侧车。只能对最新已发布快照执行 |
| `cleanup <侧车> --older-than-days N` | 删除早于 N 天且未打 tag 的版本；所有已发布版本保留 |
| `protect <侧车>` | 为打 tag 之前发布的旧侧车补 tag；未打 tag 的表拒绝 `cleanup` |

所有写操作（import 之后的 patch、compact、cleanup、protect、mirror）在本机通过表旁的 `.writer.lock` 串行化。**所有写入必须经过本适配器**，不要用 Lance SDK 直接改同一张表。未打 tag 的旧表保持严格 stale 检查，不会自动回滚。

## 对象存储（COS / OBS）

写入只在本地或共享 POSIX 盘（如 managed_fast）进行；COS/OBS 作为只读镜像：

```bash
export AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=... AWS_REGION=...
export AWS_ENDPOINT=https://cos.<region>.myqcloud.com      # Lance 读取
export AWS_ENDPOINT_URL=$AWS_ENDPOINT                       # pyarrow 镜像上传
$CLI mirror ws-clean/artifact.json s3://bucket/lance-root
```

镜像保持侧车里的相对路径：先传不可变数据文件，再传 `_versions`，最后传 tag；已存在的不可变文件会跳过，完成后按固定版本打开镜像核对行数。读取方在自己的 roots 文件中把同一别名指向 `s3://bucket/lance-root`，用同一份侧车读取；只有 Lance 读取路径接受 URL 根目录。对象存储上的表只读，写操作会被拒绝。本地 `cleanup` 不会同步删除镜像中的旧文件。

原因：Lance 在 S3 上安全并发提交依赖条件写或外部锁服务，COS/OBS 对条件写的支持尚未确认。凭据只走环境变量，不进 catalog 或侧车。真实 COS/OBS 读取需在有凭据的环境中手动验证一次。

## 训练直读

```python
from audio_data_contract.lance_stream import iter_records, worker_shard

class Records(torch.utils.data.IterableDataset):
    def __iter__(self):
        shard, shards = worker_shard(rank, world_size)   # 已考虑 DataLoader worker
        yield from iter_records(artifact, RecordQuery(split="train", language="zh"),
                                shard=shard, num_shards=shards, seed=0, epoch=self.epoch)
```

按 fragment 分片，每个 epoch 按 `(seed, epoch)` 重排 fragment 顺序，各分片的并集恰好等于查询结果。各分片记录数不等，选择性查询下差异更大，分布式训练不要假设每个 rank 的 batch 数相同。fragment 内部不打乱，记录级打乱由训练侧的 buffer 负责。

## JSONL / Lhotse 导出与重建

```python
from audio_data_contract.lance_export import export_artifact
from audio_data_contract.lance import rebuild_artifact, rebuild_layer

export_artifact(artifact, "records.jsonl.gz")
export_artifact(artifact, "cuts.jsonl.gz", slot="mixture", resolve_audio=existing_audio_index_resolver)
rebuilt = rebuild_artifact(artifact, "/data/managed/lance/rebuilt")   # 原表可完全不可读
```

Lhotse 导出每条记录中**一个明确指定的槽位**，`custom.audio_record` 保留完整记录；resolver 返回结构与 `scripts/target_asr/read.py:resolve_audio` 一致，不复制音频。重建会核对源哈希、Layer 哈希、父 Layer 链和结果数量。`replay_layer` 可在不安装 Lance 的情况下重放 Layer，但会把该 Layer 的 patch 全部载入内存。

## 规模验收

```bash
python scripts/lance_scale_acceptance.py records.jsonl.gz /new/acceptance-dir \
  --source-view 'actual/view@version' --source-root /dir/containing/records \
  --workers 8 --shards 8 --layer-sizes 1 64 100000 1000000
```

每项操作在独立子进程中运行，并记录各自的峰值 RSS；冷读前用 `posix_fadvise(DONTNEED)` 释放表文件的页缓存。覆盖导入、ID / 语言 / split / clean_pass 查询（冷 / 热）、全量 `verify`、各规模 Layer 回写、compact、cleanup、镜像和多分片流式读取。合成数据上的结果见 [生产化报告](../reports/lance-prod-20261004/README.md)；真实 9,278 万条数据的验收待数据就绪后执行。

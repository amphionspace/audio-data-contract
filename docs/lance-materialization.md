# 可选 Lance 物化试验

当前定位为**试验性查询副本**。不改 Dataset / Layer / View 的业务身份，不替换 catalog、训练入口或音频存储。实测结果与未完成项见 [试验报告](../reports/lance-pilot-20260929/README.md)。

## 安装与接口

```bash
pip install -e '.[lance]'
python -m audio_data_contract.lance_cli import records.jsonl.gz experiment/raw \
  --source-view 'wenetspeech/clean@v1'
python -m audio_data_contract.lance_cli verify experiment/raw/artifact.json records.jsonl.gz
python -m audio_data_contract.lance_cli export experiment/raw/artifact.json passed.jsonl.gz \
  --clean-pass true --language zh --task asr --split train
```

也可使用安装后的 `audio-data-contract-lance` 命令。这里的 View 名称是示例，调用者必须传入实际、固定版本的 View 身份；试验侧车不会自动创建或修改正式 View 声明。

```python
from audio_data_contract import read_artifact
from audio_data_contract.lance import LanceArtifact, RecordQuery

artifact = LanceArtifact.read("experiment/raw/artifact.json")
records = read_artifact(artifact, RecordQuery(ids=("sample-1", "sample-2")))
# JSONL 路径使用相同查询接口，原 load_records(path) 保持兼容。
```

`import_jsonl` 支持 JSONL / JSONL.gz，分批写入；临时 SQLite 主键检查全部批次的 ID 唯一性。只有输入验证、Lance 写入和计数检查全部成功才发布新目录。空数据集合法。导入、导出和 Layer 目录不能覆盖已有输出。

## 映射与版本边界

| 列 | 语义 |
| --- | --- |
| `record_json` | `AudioRecord.to_dict()` 的规范 JSON，保留全部字段和任意 JSON metadata/labels |
| `id`, `task`, `language` | 字符串查询投影 |
| `splits` | 所有音频槽位的 split 去重集合；split 筛选匹配任意槽位 |
| `clean_pass` | `metadata.clean.pass` 是布尔值时的投影，否则 null |
| `retained` | View 成员状态；删除保留物理行，但默认读取不可见 |

音频槽位顺序、整数/数组 channel、start/duration、空 target、整数精度和字段缺省语义均以 AudioRecord 序列化为准。投影不是新的事实来源；回写同时更新完整 JSON 和投影。没有强制将任意 metadata 推断成 Arrow struct。

`LanceArtifact` 是独立的 JSON 侧车，登记 `table_path`、`snapshot_version`、`storage_version`、`audio_record_schema`、`record_count`（保留样本数）、`schema_hash`、`source_view` 和 `rebuild_metadata`。后者包含源 JSONL 路径、规范记录流哈希、映射版本、Layer 路径列表及已声明写入字段。

映射版本为 `audio-record-lance/1.0`，存储格式显式固定为 `2.0`，依赖锁定 `pylance==12.0.0`；本次验证使用 PyArrow 25.0.1。schema hash 覆盖 AudioRecord JSON Schema 和 Arrow 映射。读取不使用 latest；不存在的 snapshot、格式或 schema 不匹配会报 `ContractError`。完整计数和 ID/字段一致性通过 `verify_equivalence` 检查，普通选择性读取不额外执行全表计数。

Lance 的固定格式版本、流式写入和 merge 行为参考 [官方读写文档](https://lance.org/guide/read_and_write/)；历史版本机制参考 [官方版本文档](https://lance.org/quickstart/versioning/)。这里未启用 namespace/catalog 服务、Blob、向量/全文/标量索引或训练直读。SDK 自带的 namespace 依赖不代表接入 namespace 服务。

## 清洗 Layer 与增量回写

输入 patch JSONL 的每行格式：

```json
{"id":"sample-1","changes":{"target":"修正文本","metadata.clean.pass":true},"status":"keep"}
```

`status` 为 `keep` 或 `delete`；`changes` 是声明字段的赋值，支持 metadata/labels 的点分路径。只允许改 target、language、hotwords、metadata、labels 和 `$membership`，不允许更改 ID/AudioRef。覆盖已有不同值或先前 Layer 写过的父/子字段，必须声明 `overrides`；删除必须声明 `$membership`。不知道的 ID、重复 patch ID、重叠路径和未声明字段会拒绝写入。

TransformStep 示例：

```json
{
  "name":"clean","version":"v1","kind":"filter-and-correct",
  "writes":["target","metadata.clean","$membership"],
  "overrides":["target","metadata.clean"],
  "parameters":{"threshold":0.8}
}
```

```bash
python -m audio_data_contract.lance_cli patch experiment/raw/artifact.json \
  patches.jsonl transform.json experiment/clean-layer \
  --source-view 'wenetspeech/clean@v2' --tool cleaner-v1 --model actual-model-version
```

先按 ID 排序并发布 `patch.jsonl` + `manifest.json`，再一次 merge 提交 Lance 版本，最后发布该 Layer 的 `artifact.json`。每个 patch 带父 snapshot 和自身哈希；批次 manifest 记录完整父 artifact、字段声明、工具、模型（不用模型时为 null）、参数、输入/保留/结果数量及批次哈希。共享处理事实由 manifest 提供，不在每一行重复。

当前支持本地 POSIX 文件系统，通过 `flock` 串行化适配器写入，并拒绝过期父 snapshot。**所有写入必须经过此适配器**；不支持其他进程直接用 Lance SDK 修改同一表。patch 批次加载到内存，调用者应分批提交；这不是无限流式清洗服务。一个已发布 artifact 固定绑定一个 snapshot，后续更新生成新 artifact，旧 View 不受影响。不要清理仍被引用的 Lance 版本。

规范 patch 保留的是处理事实，不是仅存于 Lance 的审计备注。失败恢复：

```python
from audio_data_contract.lance import rebuild_artifact, rebuild_layer

# 原表可以完全不可读；使用源 JSONL 和规范 Layer 重建到新目录。
rebuilt = rebuild_artifact(artifact, "experiment/rebuilt")
# merge 或 artifact 发布失败，Layer 已落盘但没有新的 artifact：
recovered = rebuild_layer("experiment/clean-layer", "experiment/recovered",
                          source_view="wenetspeech/clean@v2")
```

重建核对源哈希、Layer 哈希、父 Layer 链和结果数量。若 merge 已提交但侧车发布失败，可能留下未发布的完整 snapshot；不能把 latest 当作已发布 View，应使用上述重建恢复。原始 JSONL、Layer、侧车和表目录须一起保留；当前路径是本地绝对路径，迁移时需显式更新绑定。`replay_layer` 可不安装 Lance 在声明的父 JSONL 上重放，但须完整消费迭代器才能完成尾部 ID/数量检查。

## JSONL / Lhotse 导出

```python
from audio_data_contract.lance_export import export_artifact

export_artifact(artifact, "records.jsonl.gz")
export_artifact(artifact, "cuts.jsonl.gz", slot="mixture",
                resolve_audio=existing_audio_index_resolver)
```

Lhotse 导出每条记录的一个**明确指定的槽位**，支持 MonoCut / MultiCut、channel 和时间片段。resolver 接收 AudioRecord，返回按槽位名索引的 `path`、`sample_rate`、`channels`（通道数）、`duration`（完整音频时长）；与现有 `scripts/target_asr/read.py:resolve_audio` 返回结构一致。路径仍由 audio-index + roots 解析，不复制音频。

`custom.audio_record` 保留完整 AudioRecord，包括其他槽位和空转写；`custom.audio_slot` 标识本次导出的主槽位；同时按现有约定投影 `custom.hotwords`、`custom.labels` 和 `custom.clean`。Lhotse 通用消费方读取所选主音频；需要 enrollment/mixture 配对的消费方继续使用现有 JSONL 适配，不能假设通用 CutSet 自动处理其他槽位。两种导出均在成功后才发布文件。

## 重跑基线

```bash
python scripts/benchmark_lance.py records.jsonl.gz /new/experiment \
  --source-view 'actual/view@version' --repeats 7
```

脚本先写 `baseline.json`，再创建 Lance 表，记录全量/清洗/语言任务 split/单条和批量 ID 查询的 p50/p95、JSONL 物化、单条/批量字段回写、产物大小与进程 RSS 峰值，并核对初始/最终 ID 和字段。回写字段是明确标注的试验质量字段，不代表模型清洗结果。脚本只操作新实验目录，不修改源文件、catalog 或训练入口。

这不是 9,278 万条规模的验收：重复查询未清空系统缓存，7 次观测的 p95 是最大值，RSS 是整个进程的高水位。正式采用仍需真实清洗 View、实际生产 Layer、全规模查询选择率及独立进程内存测量。

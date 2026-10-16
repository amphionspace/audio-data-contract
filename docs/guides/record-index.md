# Lance 记录索引

**用途：训练启动时一次读到全部记录的元数据和音频位置，不再逐行解析 JSONL，也不再在运行时把 audio-index 转成 sqlite。** 音频文件不动，索引只存位置。原有的 JSONL 产物仍是权威来源，索引由它们生成，随时可以重建。

## 生成和登记

```bash
audio-data-contract build-record-index <catalog> <dataset_id> <version> <输出目录> --roots roots.json
```

- 按 split 的用途自动选择输入：有 `records` + `audio_index` 的读 AudioRecord；有 `recordings` + `supervisions` 的读 Lhotse 清单。
- 先按 catalog 的 sha256 核对每个输入文件，再生成；任何一行出错都不发布，输出目录不会留下半成品。
- 输出目录包含 `table.lance` 和 `index.json`，命令打印出一条 catalog 产物声明（`kind: lance-record-index`），把它加进该版本的 `artifacts`，再在每个 split 下加用途 `records_lance`：

```yaml
  - name: record_index
    kind: lance-record-index
    root_alias: aidc_data
    relative_path: datasets/<id>/versions/<version>/record_index/index.json
    sha256: ...            # index.json 的 sha256
    metadata:
      snapshot_version: 6
      rows: 3994914
      schema_hash: ...
  splits:
    train_zh:
      artifacts:
        records: [train_zh]
        audio_index: [audio_index]
        records_lance: [record_index]
```

旧的 `records` / `audio_index` 原样保留，训练侧按需选择用途。

加 `--register` 时，命令建完直接把上面的产物声明和各 split 的 `records_lance` 写回声明该版本的 YAML 文件，不用手工改。同一位置重建的索引会就地更新原产物的 sha256 和固定版本。写回只追加这两处，文件其余内容逐字不变；如果某个文件的排版（例如手工折行）无法原样写回，命令会报错并保持文件不动，这时按打印的声明手工添加。写回后整个 catalog 必须仍能加载，否则恢复原文件。

**登记流程要求**：带 `records` + `audio_index` 或 `recordings` + `supervisions` 的版本，登记时应同时建好索引。`check-registration` 对缺索引的 split 输出 `warnings`；加 `--require-record-index` 则当作错误。

`check-registration` 会检查 `lance-record-index`：每个 split 的行数等于源 JSONL 条数；抽样源记录，逐项比对时长、`cut_id`、音频位置、起始帧和帧数，并确认音频文件可读。

## 读取

```python
from audio_data_contract.record_index import iter_batches, open_index, to_table

index = open_index(catalog, "emilia2_short", "short-20261014", "record_index", roots)
table = to_table(index, split="train_zh", filter="duration <= 30 AND language = 'zh'")
for batch in iter_batches(index, split="train_zh", shard=shard, num_shards=shards, epoch=epoch):
    ...
```

`open_index` 核对 `index.json` 的 sha256、snapshot 版本、行数和 schema，只读登记时固定的版本。`split=` 转成 `array_has(splits, ...)`；`filter` 是 Lance SQL 条件，在读取时下推执行。`iter_batches` 按 fragment 分片，每个 epoch 重排，用法同 `lance_stream.iter_records`。

## 列

| 列 | 含义 |
|---|---|
| `id` | 记录 ID（Lhotse 输入为 supervision ID），有 BTREE 索引 |
| `splits` | 列出该记录所属的全部 split，有 LABEL_LIST 索引。同一份源文件被多个 split 引用时（如 `train` = `train_zh` + `train_en`），记录只存一次 |
| `task`、`language` | 有 BITMAP 索引；Lhotse 的 `language` 保留原值（如 `Chinese`） |
| `duration` | 秒，有 BTREE 索引 |
| `text`、`speaker` | 目标文本；说话人取 `metadata.speaker` 或 supervision 的 `speaker`，有 BTREE 索引。值只在本数据集内唯一，跨数据集请拼成 `dataset_id:speaker`；派生数据集请直接写带前缀的值。gigaspeech 全部是 `N/A`，emilia2_short 是单条录音内的说话人编号 |
| `source_group` | 没有可靠说话人时的来源分组，取 `metadata.source_group`，有 BTREE 索引 |
| `loudness_dbfs`、`clip_ratio`、`voiced_ratio` | 质量列，取 `metadata` 同名字段，缺失为空：整段 RMS 响度（dBFS，16 kHz 单声道下混后计算）；\|x\| ≥ 0.999 的采样点占比；25 ms 帧中能量高于 −50 dBFS 的帧占比（能量门限，不是语音检测）。可直接在 `filter` 里使用 |
| `cut_id` | 主音频槽位的 `AudioRef.cut_id`；Lhotse 输入同 `id`。主槽位：只有一个槽位时取它，否则取 `primary`，再否则取 TS 的 `mixture` |
| `root_alias`、`relative_path` | 音频文件位置，用 roots 文件解析 |
| `start_frame`、`num_frames`、`sample_rate` | 从文件第几帧开始读多少帧；整文件记录 `start_frame` 为 0 |
| `channels`、`channel` | 文件声道数；选定的声道（未指定为空） |
| `slots` | 记录的全部音频槽位（如 TS 的 `enrollment` 和 `mixture`），每个都带 `name`、`purpose`、`cut_id`、时长和上面这些位置字段 |
| `record_json` | 完整 AudioRecord（含 `labels`、`hotwords`、`metadata`），默认不读；Lhotse 输入为空 |

每个 fragment 最多 65,536 行。映射版本 `record-index-lance/1.1`（1.0 加上质量列、`source_group` 和说话人索引；1.0 的表需重建）。Lhotse 输入不读取 `custom` 字段，质量列和 `source_group` 为空。

## 限制

- 只处理单文件音频源；Lhotse 多文件或多声道选择会直接报错。
- 每个槽位引用的 cut 都必须在本版本的 audio_index 里，指向其他数据集的槽位会报错。
- 记录 ID 在每个 split 内唯一。两个源文件可以用同一批 ID（如 `hw_sft` 的 `train_hotwords` 是 `train` 的子集），各存一行，按 split 读取不会重复；不带 `split` 读全表时会看到重复 ID。
- 生成时在内存中保存全部 ID 和音频位置。实测 emilia2_mix 921 万条峰值约 5 GB 内存，24 分钟。
- Lhotse 输入每条录音都要解析一次路径；一条录音一个文件的数据集（如 vitw 56 万条，18 分钟）比长录音切段的数据集慢得多。
- 音频位置的 `root_alias` 优先用源产物自己的别名；多个别名指向同一目录时不会随别名名字变化。

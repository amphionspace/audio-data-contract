# DATA-TTS-UNIFIED 用于 ASR 的评估

17 个已发布的 v0.1 数据集（共约 37.4 万小时）中，**8 个排除原始 dev/test 后即可用于 ASR（约 13.9 万小时）**，
**3 个需要先做质量过滤（约 22.3 万小时）**，**6 个游戏/表演类数据不建议现在使用（约 1.3 万小时）**。
emilia2 尚未发布，未纳入。

通用清洗已在本仓库以读取规则 `tts-asr-rules/v1` 实现（见下），只在读取时生效，不改 DATA-TTS-UNIFIED。
套用规则后剩余：A 类 133,862 小时，B 类 222,574 小时，C 类 11,754 小时。
B 类的转写质量过滤由 amphiondata 负责。`text_kind` 无法用来区分人工转写和机器转写：除 libriheavy 是 `source_book_text` 外，
其余全部是 `source_transcript`，Emilia 的机器转写也是这个值。

## 结论

| 等级 | 数据集 | 小时 | 语言 | 用前必须做 |
|---|---|---:|---|---|
| A 可直接用 | libriheavy | 51,044.7 | en | 书本原文带大小写和标点，需按训练配方归一化；超过 30 秒的 43.9 万条需切分或过滤 |
| A | mls_sidon | 50,834.3 | en 为主，另有 de/nl/fr/es/it/pt/pl | **排除 valid/test（35,483 条，即 MLS 评测集）**；音频经 Sidon 修复；与已登记的 mls_* 是同一批语音 |
| A | hifitts2 | 35,932.7 | en | 排除 dev_*/test_*（4,026 条） |
| A | libritts_r | 583.1 | en | **排除 dev/test（20,306 条，来自 LibriSpeech dev/test，会污染 LibriSpeech 评测）** |
| A | hifitts | 291.7 | en | 排除 dev/test（1,500 条） |
| A | aishell3 | 85.6 | zh | **排除 test（24,773 条）**；与已登记的 aishell3 是同一批音频 |
| A | vctk | 82.7 | en | 172 条无文本 |
| A | ljspeech | 23.9 | en | 单一说话人；11% 含未展开的数字 |
| B 需过滤 | emilia_yodas | 113,820.6 | en 为主，另有 ko/fr/de/ja/zh | 机器转写；文本开头带空格；建议做双模型一致性或置信度过滤 |
| B | emilia | 101,655.6 | zh/en 为主 | 同上；抽样中有明显的识别错误 |
| B | wenetspeech4tts | 7,232.2 | zh | 来自 WenetSpeech 的弱标注，建议用和 `clean-dual-qwen-moss` 一样的方式过滤 |
| C 暂不用 | galgame | 10,173.7 | ja | 游戏配音，表演腔和拟声词多，4.5% 不足 1 秒 |
| C | genshin_voice | 1,039.7 | zh/en/ja/ko | 52,693 条无文本；2.8% 带 `{NICKNAME}`、`<color>` 等标记 |
| C | starrail_voice | 692.6 | zh/en/ja/ko | **en/ja/ko 配音约 94% 配的是中文文本**（见下）；61,375 条无文本；9% 带标记 |
| C | wutheringwaves | 134.8 | zh/en/ja/ko | en 配音中 2.5% 配的是中文文本 |
| C | zenless_voice | 554.4 | zh/en/ja/ko | 123,429 条无文本（30%）；3.3% 带 `{…}` 等标记；12% 不足 1 秒（2026-10-09 发布后补登记） |
| C | csemotions | 10.2 | zh | 表演型情感语音，数据量太小 |

## ASR 读取规则 tts-asr-rules/v1

`iter_asr_samples()` 在 `iter_samples()` 的基础上逐条套用 `apply_asr_rules()`：

1. 排除原始划分不是 train 的行（`eval_split`）。
2. 排除时长超过 30 秒的行（`too_long`）。阈值可调，设为 `None` 则不限。
3. 去掉 `<i>`、`<color=…>` 等格式标签和空的 `[]`，去掉开头的 `#`，合并空白字符，并去掉首尾空格。
4. 去掉格式标签后仍含 `{}`、`<>`、`[]` 的行一律排除（`markup`）。这类文本有三种：性别分支 `{M#他}{F#她}`、
   昵称占位 `{NICKNAME}`、注音 `{RUBY_B#…}`，以及有声书的 `[Illustration: …]`、`[Footnote: …]`。
   它们都无法确定音频里实际念的是哪些字。
5. 排除没有任何文字或数字的行（`no_lexical`），例如 `……`。
6. 排除语言和文本所用文字对不上的行（`script_mismatch`）：
   - zh 文本含假名或谚文；
   - ko 文本没有谚文却有汉字或假名；
   - 拉丁字母语言的文本含中日韩文字；
   - ja 文本含谚文，或不含假名但汉字有 6 个及以上。
7. 语言标签只保留主标签（`zh-CN` → `zh`，`en-US` → `en`），原值记在 `metadata.source_language`。
   每条记录写入 `metadata.asr_rules`。

全量统计（单位：条；无文本的行在读取时已跳过）：

| 数据集 | 原时长（小时） | 保留时长（小时） | 原始 dev/test | 无文本 | 标记 | 无文字 | 语言和文字不一致 | 超过 30 秒 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| libriheavy | 51,044.7 | 46,360.0 | — | — | 200,283 | 8 | 53 | 438,673 |
| mls_sidon | 50,834.3 | 50,686.8 | 35,483 | — | — | — | — | — |
| hifitts2 | 35,932.7 | 35,804.8 | 4,026 | — | 32,891 | — | — | — |
| libritts_r | 583.1 | 551.1 | 20,306 | — | 217 | — | — | 115 |
| hifitts | 291.7 | 289.9 | 1,500 | — | 1 | — | — | — |
| aishell3 | 85.6 | 63.2 | 24,773 | — | — | — | — | — |
| vctk | 82.7 | 82.5 | — | 172 | — | — | — | — |
| ljspeech | 23.9 | 23.9 | — | — | 7 | — | — | — |
| emilia_yodas | 113,820.6 | 113,714.0 | — | — | 4,296 | 1 | 28,142 | 228 |
| emilia | 101,655.6 | 101,627.8 | — | — | 793 | 33 | 8,238 | 430 |
| wenetspeech4tts | 7,232.2 | 7,232.2 | — | — | — | — | — | — |
| galgame | 10,173.7 | 10,095.9 | — | — | 11,401 | 147,386 | 1,218 | 311 |
| genshin_voice | 1,039.7 | 927.5 | — | 52,693 | 16,205 | 8,044 | 51 | 1,938 |
| starrail_voice | 692.6 | 157.7 | — | 61,375 | 28,906 | 6,555 | 210,181 | 288 |
| wutheringwaves | 134.8 | 128.1 | — | — | 632 | 316 | 508 | 494 |
| zenless_voice | 554.4 | 434.7 | — | 123,429 | 10,966 | 5,470 | 8 | 56 |
| csemotions | 10.2 | 10.1 | — | — | — | — | — | 15 |

补充说明：
- libriheavy 超过 30 秒的 43.9 万条（3,726 小时）如果要用，需要另做切分。
- emilia 的"语言和文字不一致"多是德语、英语文本里混入了"呃"之类的中文，属于机器转写的幻觉，排除是对的。

## B 类质量过滤（由 amphiondata 负责）

emilia、emilia_yodas、wenetspeech4tts 的转写质量过滤由 amphiondata 负责，本仓库只登记清洗结果。
需要注意三点，已列入[待办](../../docs/datasets/tts-unified.md#待办)：

- 规模：上次中文双模型清洗实测每小时能处理 210–430 小时音频（2–4 张卡）。按这个速度，22.3 万小时大约要 1 个月。
- 输入：音频在 Lance 表内，清洗工具需要通过 `tts_lance` 读取。
- 阈值：非中文部分没有现成的阈值。

## 已知问题（已标记，留给 tts-data-pipeline 处理）

1. **starrail_voice 的语言和文本对不上。** 按文本字符统计：`en` 有 78,864 条是中文文本，只有 4,786 条是英文；
   `ja`、`ko` 也一样。看起来是每种语言的配音都配上了中文台词。这个问题同样影响 TTS 训练。
   已写入该条目的 `provenance.known_issues`。本仓库不改数据，ASR 规则会把这 21 万条排除。
2. 语言标签不统一（`zh-CN`/`zh`、`en-US`/`en`），emilia 文本开头带空格。ASR 规则读取时已处理，上游数据未改。

## 读取方法

已在本仓库登记为 `<dataset_id>@tts-unified-v0.1`（`catalog/tts_unified.yaml`），产物类型为 `tts-lance-release`，
固定发布 manifest 的 sha256 和 Lance snapshot 版本。ASR 训练用 `iter_asr_samples`：

```python
from audio_data_contract import load_catalog
from audio_data_contract.lance_stream import worker_shard
from audio_data_contract.tts_lance import iter_asr_samples, open_release

release = open_release(load_catalog(catalog_dir), "hifitts2", "tts-unified-v0.1", "samples", roots)
shard, shards = worker_shard(rank, world_size)
for record, audio_bytes in iter_asr_samples(release, shard=shard, num_shards=shards, epoch=epoch):
    ...  # record.target 为清洗后的文本，audio_bytes 为原始编码（wav/mp3/ogg 等），用 soundfile 解码
```

`iter_samples()` 读出的是不套用规则的原始记录（只跳过无文本的行），给 TTS 或其他用途使用。

## 数据来源

[summary.json](summary.json) 对每个数据集做了全量扫描，统计 text、text_kind、language、duration_seconds、text_variants；
字符速率每 97 行抽 1 行。各数据集按 manifest 固定的 Lance 版本读取。原始划分来自 `metadata_json.original_split`。
语言和文本不一致的问题，是按文本中的假名、谚文、汉字、拉丁字母判断的。
`asr_rules` 一节是规则 v1 在全部 17 个数据集上逐条运行的结果。

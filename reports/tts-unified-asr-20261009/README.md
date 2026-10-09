# DATA-TTS-UNIFIED 用于 ASR 的评估

16 个已发布的 v0.1 数据集（共约 37.4 万小时）中，**8 个排除原始 dev/test 后即可用于 ASR（约 13.9 万小时）**，
**3 个需要先做质量过滤（约 22.3 万小时）**，**5 个游戏/表演类数据不建议现在使用（约 1.2 万小时）**。
emilia2 尚未发布，未纳入。

所有数据都需要做通用清洗：去掉原始 dev/test、去掉无文本行、去掉首尾空格、统一语言标签，
以及处理超过 30 秒的片段。`text_kind` 无法用来区分人工转写和机器转写：除 libriheavy 是 `source_book_text` 外，
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
| C | csemotions | 10.2 | zh | 表演型情感语音，数据量太小 |

## 需要反馈给 tts-data-pipeline 的问题

1. **starrail_voice 的语言和文本对不上。** 按文本字符统计：`en` 有 78,864 条是中文文本，只有 4,786 条是英文；
   `ja`、`ko` 也一样。看起来是每种语言的配音都配上了中文台词。这个问题同样影响 TTS 训练。
2. **语言标签不统一**：starrail 用 `zh-CN`，其他数据集用 `zh`；genshin 用 `en-US`，其他用 `en`。
   genshin 有 1,088 条语言为空。
3. emilia 和 emilia_yodas 的文本开头带空格。

## 读取方法

已在本仓库登记为 `<dataset_id>@tts-unified-v0.1`（`catalog/tts_unified.yaml`），产物类型为 `tts-lance-release`，
固定发布 manifest 的 sha256 和 Lance snapshot 版本。用 `audio_data_contract.tts_lance` 读取：

```python
from audio_data_contract import load_catalog
from audio_data_contract.lance_stream import worker_shard
from audio_data_contract.tts_lance import iter_samples, open_release

release = open_release(load_catalog(catalog_dir), "hifitts2", "tts-unified-v0.1", "samples", roots)
shard, shards = worker_shard(rank, world_size)
for record, audio_bytes in iter_samples(
    release, filter="language = 'en'", shard=shard, num_shards=shards, epoch=epoch
):
    ...  # record.target 为文本，audio_bytes 为原始编码（wav/mp3/ogg 等），用 soundfile 解码
```

无文本的行会自动跳过。读取不会排除原始 dev/test，需要调用方自己处理，或者另外做清洗 Layer。

## 数据来源

[summary.json](summary.json) 对每个数据集做了全量扫描，统计 text、text_kind、language、duration_seconds、text_variants；
字符速率每 97 行抽 1 行。各数据集按 manifest 固定的 Lance 版本读取。原始划分来自 `metadata_json.original_split`。
语言和文本不一致的问题，是按文本中的假名、谚文、汉字、拉丁字母判断的。

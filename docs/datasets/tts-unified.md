# DATA-TTS-UNIFIED 数据

`/workspace/data/DATA-TTS-UNIFIED` 下已发布的 16 个 v0.1 数据集已登记为 `<dataset_id>@tts-unified-v0.1`，共约 37.4 万小时。
数据仍归 tts-data-pipeline 管理，本仓库只登记，不改数据。数据清洗由 amphiondata 负责。

声明文件：[tts_unified.yaml](../../catalog/tts_unified.yaml)，由 [register_tts_unified.py](../../scripts/register_tts_unified.py) 从各数据集的发布 manifest 生成。
各数据集能否用于 ASR，以及需要排除哪些数据，见 [评估报告](../../reports/tts-unified-asr-20261009/README.md)。

## 登记方式

- 产物类型 `tts-lance-release`：固定发布 manifest 的 sha256 和 Lance snapshot 版本。读取时逐项核对，不一致直接报错，不会读到更新的版本。
- 音频以原始编码字节存放在 Lance 表内，没有单独的音频文件。
- 原始划分记在 `metadata_json.original_split`，统一输出全部标为 train。

## 读取

```python
from audio_data_contract import load_catalog
from audio_data_contract.tts_lance import iter_asr_samples, iter_samples, open_release

release = open_release(load_catalog(catalog_dir), "hifitts2", "tts-unified-v0.1", "samples", roots)
for record, audio_bytes in iter_asr_samples(release, shard=shard, num_shards=shards, epoch=epoch):
    ...
```

| 入口 | 用途 |
|---|---|
| `iter_samples()` | 原始记录，只跳过无文本的行 |
| `iter_asr_samples()` | 套用读取规则 `tts-asr-rules/v1`：排除原始 dev/test、无法确定读音的标记、无文字行、语言和文字不一致的行、超过 30 秒的行；统一语言标签 |
| `read_audio()` | 按样本 ID 取音频字节 |

读取规则只做确定性的文本和划分处理，不判断转写质量。

## Emilia 精修元数据

`emilia@refined-metadata-20261010`（[emilia_refined.yaml](../../catalog/emilia_refined.yaml)）是 TTS 团队对 Emilia 的文本精修结果，从 `amphion-tts-data:Emilia-Refined-Metadata/` 下载到 `/workspace/data/datasets/emilia/source/refined-metadata-20261010/`。只有 JSON 元数据，不含音频；记录的 `id` 就是 `emilia@tts-unified-v0.1` 的 `source_key`，四个目录全部能对上，音频按 `id` 从统一版读取。

| 产物 | 目录 | 条数 | 小时 | 内容 |
|---|---|---:|---:|---|
| `final` | `emili_1.0_final` | 31,275,879 | 78,091.0 | 筛选后的最终集，精修文本 + 词级时间戳 |
| `refined_full` | `emilia_1.0` | 40,264,231 | 101,655.6 | 全量精修文本 + 词级时间戳，未筛选 |
| `qc_monolang` | `emilia_monolang` | 34,947,009 | 88,746.5 | 单语样本的质量分数（`wer`、`ttps`、`raw_text`） |
| `qc_multilang` | `emilia_multilang` | 2,390,658 | 6,266.9 | 语种混杂样本的质量分数，未进入 `final` |

`final` 是 `qc_monolang` 的子集，`wer` 都不超过 0.25；完整筛选规则没有随数据提供。

## 待办

| # | 事项 | 负责 | 本仓库要做的 |
|---|---|---|---|
| 1 | emilia、emilia_yodas、wenetspeech4tts 是机器转写或弱标注，需要做质量过滤（22.3 万小时）。emilia 已有 TTS 团队的精修版 `refined-metadata-20261010`（见上节） | amphiondata | 清洗结果出来后登记为新版本或 Layer |
| 2 | amphiondata 清洗工具要能读 Lance 表内的音频，可以直接用 `tts_lance.iter_samples` / `read_audio` | amphiondata | 接口有变化时配合调整 |
| 3 | emilia 的 en/de/fr/ja/ko 部分没有现成的清洗阈值，现有规则只在中文上验证过；可参考精修版的 `wer` 分数 | amphiondata | — |
| 4 | libriheavy 有 43.9 万条超过 30 秒（3,726 小时），读取规则直接排除了；要用的话需要切分 | amphiondata | 切分结果登记为新版本 |
| 5 | starrail_voice 的 en/ja/ko 配音约 94% 配的是中文文本，已写入 `provenance.known_issues` | tts-data-pipeline | 修复后重新运行 `register_tts_unified.py` 登记新版本 |
| 6 | emilia2 还在 `v0.1.incomplete`，未发布 | tts-data-pipeline | 发布后重新运行 `register_tts_unified.py`，同步到 registry |
| 7 | DATA-TTS 下的 WenetSpeech-Chuan、WenetSpeech-Wu、WenetSpeech-Yue、zenless-voice 还没有转入统一版，目前没有登记 | tts-data-pipeline | 转入后登记 |
| 8 | aishell3、mls_sidon 和已登记的 aishell3、mls_* 是同一批语音，混合训练时不要重复计入 | 训练配置方 | — |
| 9 | 游戏和表演类数据（galgame、genshin_voice、starrail_voice、wutheringwaves、csemotions）是否用于 ASR，还没有定 | 待定 | — |
| 10 | emilia 精修版 `final` 的完整筛选规则不明（已知 `wer` ≤ 0.25，但 `wer` 为 0 的样本也有被排除的），`emilia_monolang/ZH` 比其他目录少 2 个文件 | tts-data-pipeline | 拿到规则后补进声明 |

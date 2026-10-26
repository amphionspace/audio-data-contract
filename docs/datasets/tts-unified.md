# DATA-TTS-UNIFIED 数据

`/workspace/data/DATA-TTS-UNIFIED` 下已发布的 18 个 v0.1 数据集已登记为 `<dataset_id>@tts-unified-v0.1`，共约 52.1 万小时。
数据仍归 tts-data-pipeline 管理，本仓库只登记，不改数据。数据清洗由 amphiondata 负责。

声明文件：[tts_unified.yaml](../../catalog/tts_unified.yaml)，由 `audio-data-contract sync-tts-unified` 按发布方的登记表生成，registry 中的副本每小时自动同步（见下文“自动同步”）。
各数据集能否用于 ASR，以及需要排除哪些数据，见 [评估报告](../../reports/tts-unified-asr-20261009/README.md)。

## 登记方式

- 产物类型 `tts-lance-release`：固定发布 manifest 的 sha256 和 Lance snapshot 版本。读取时逐项核对，不一致直接报错，不会读到更新的版本。
- 音频以原始编码字节存放在 Lance 表内，没有单独的音频文件。
- 原始划分记在 `metadata_json.original_split`，统一输出全部标为 train。
- 标注（ASR 转写、DNSMOS 质量分、说话人日志等）登记为同一版本下的 `tts-lance-annotation` 产物，产物名是标注的 run_id，
  在 train 划分里按任务名归组（例如 `transcription`、`upstream_quality`）。产物固定标注 manifest 的 sha256；
  `metadata.table_path` 是该数据集结果表的位置（相对 `aidc_data`），`metadata.coverage` 是成功和失败的条数。
  读取方式见下文“读取标注”。

## 自动同步

发布方在 `DATA-TTS-UNIFIED/PUBLICATIONS.md` 的“当前发布总览”表里登记正式发布。同步只认这张表：

- 表里的基础数据集登记为 `<dataset_id>@tts-unified-<release_id>`，表里的 Annotation 挂到它覆盖的数据集上；
  manifest 已经 complete、但表里还没有的 run 不登记。
- 表里删掉的 run 下次同步时一起删掉；manifest 被修正后，登记的 sha256 跟着更新。
- 表不完整、表里的 run 找不到 complete manifest、或新文件让 registry 校验失败时报错退出，registry 保持原样。

registry 由 [deploy/tts-unified-sync.sh](../../deploy/tts-unified-sync.sh) 每小时同步一次，日志在
`/workspace/data/tts-unified-sync/sync.log`。容器里没有 systemd/cron，容器重启后需要手动重新启动（命令见脚本开头）。
同步失败时发飞书卡片到 storage-audit 的群，同一个错误只发一次，下次同步成功时再发一条“已恢复”。
手动预览差异：

```bash
audio-data-contract sync-tts-unified /workspace/data --catalog-dir /workspace/data/registry/catalog \
  --views /workspace/data/registry/views --roots /workspace/data/registry/roots.json --dry-run
```

仓库里的 `catalog/tts_unified.yaml` 是快照，修改生成代码时用 `--catalog-dir catalog --views views` 重新生成。

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

### 读取标注

标注按 run_id 打开，同样核对 manifest sha256 和 Lance 快照版本。转写类标注可以直接替换训练文本：

```python
from audio_data_contract.tts_lance import open_annotation, read_annotations

asr = open_annotation(catalog, "emilia", "tts-unified-v0.1", "tts-ann-transcription-20261012T092945bjt-01", roots)
for record, audio_bytes in iter_asr_samples(release, text_from=asr, shard=shard, num_shards=shards):
    ...  # record.target / record.language 来自标注，metadata.text_source 是 run_id

dnsmos = open_annotation(catalog, "emilia", "tts-unified-v0.1", "tts-ann-upstream_quality-20261013T143341bjt-01", roots)
scores = read_annotations(dnsmos, sample_ids, columns=("status", "result.upstream_dnsmos"))
```

| 入口 | 用途 |
|---|---|
| `iter_samples(..., text_from=asr)` / `iter_asr_samples(..., text_from=asr)` | 文本和语言取自转写标注里 status=ok 的行；没有成功转写的样本跳过，基础文本为空也能读 |
| `read_annotations()` | 按样本 ID 取标注行（`status`、`error_code`、`result`，嵌套字段写成 `result.<字段>`）；不在标注范围内的样本没有行 |

标注结果的含义（例如 DNSMOS 用什么阈值）由使用方决定，读取接口不做筛选。

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
| 5 | starrail_voice 的 en/ja/ko 配音约 94% 配的是中文文本，已写入 `provenance.known_issues` | tts-data-pipeline | 修复后自动同步；确认修好后删掉 `tts_unified_sync.KNOWN_ISSUES` 里的说明 |
| 6 | emilia2 已于 2026-10-11 发布并登记（9,984 万条，14.6 万小时，41 种语言），只登记为 TTS；是否可用于 ASR 还没有评估 | amphiondata | 评估后补 ASR 说明和读取规则 |
| 7 | DATA-TTS 下的 WenetSpeech-Chuan、WenetSpeech-Wu、WenetSpeech-Yue 还没有转入统一版，目前没有登记 | tts-data-pipeline | 转入后登记 |
| 8 | aishell3、mls_sidon 和已登记的 aishell3、mls_* 是同一批语音，混合训练时不要重复计入 | 训练配置方 | — |
| 9 | 游戏和表演类数据（galgame、genshin_voice、starrail_voice、wutheringwaves、zenless_voice、csemotions）是否用于 ASR，还没有定 | 待定 | — |
| 10 | emilia 精修版 `final` 的完整筛选规则不明（已知 `wer` ≤ 0.25，但 `wer` 为 0 的样本也有被排除的），`emilia_monolang/ZH` 比其他目录少 2 个文件 | tts-data-pipeline | 拿到规则后补进声明 |

# Common Voice EN 清洗说明

**train 和 test 都运行过 Qwen3-ASR-1.7B + whisper-large-v3 双引擎筛选，但当前登记的两个清单都不能直接视为已剔除失败样本的最终数据。**

2026-09-09 检查了 `clean-v1-20260805` 对应的实际文件：完整扫描两个发布清单的 `custom.clean`，抽看两个 `results.jsonl` 的识别结果，并读取各自的 `filter_report.json`。没有进行音频人工听审。

| 划分 | 筛选报告处理量 | 通过 | 拒绝 | 当前登记清单 |
|---|---:|---:|---:|---|
| train | 1,143,276 | 1,142,149 | 1,127 | 全部条目都有 `custom.clean`，其中 1,127 条 `pass=false` 仍保留，读取时应过滤 |
| test | 16,402 | 16,294 | 108 | 全部条目都没有 `custom.clean`；不能在这个文件上按该字段完成筛选 |

train 的拒绝原因是 `bad_annotation` 858 条、`ambiguous` 269 条；test 报告分别为 47 条、61 条。test 的通过/拒绝数仅登记为运行报告证据，不写成当前 test 清单的通过/拒绝标记统计。

两个报告的参数均为 `threshold=50.0`、`agree_threshold=30.0`、`min_tokens=2`。报告未说明阈值的单位，本次也未核查规则实现，不进一步解释为某个具体错误率指标。

## 样本证据

训练样本原文为：

> Different species have different ways of dealing with tides.

Qwen 输出与原文一致；Whisper 把最后的 `tides` 识别成 `types`。两份结果分别存于 `inference.Qwen3-ASR-1.7B` 和 `inference.whisper-large-v3`。对应发布清单记录：

```json
{"engine":["Qwen3-ASR-1.7B","whisper-large-v3"],"pass":true,"reason":"","rules":"v1"}
```

这证明存在双引擎推理和筛选记录，不表示通过样本都经过人工确认，也不证明所有转写均已纠正。

## 产物与追溯

根目录别名均为 `legacy_asr`，以下路径相对于该根目录：

| 内容 | 相对路径 |
|---|---|
| 当前 train 清单 | `common_voice_en/lhotse/clean/v1/cv-en_supervisions_train_orig_punc.jsonl.gz` |
| 当前 test 清单 | `common_voice_en/lhotse/clean/v1/cv-en_supervisions_test_orig_punc.jsonl.gz` |
| train 筛选报告 | `common_voice_en/lhotse/clean/v1/workdir/cv-en_supervisions_train_orig_punc/filtered/filter_report.json` |
| test 筛选报告 | `common_voice_en/lhotse/clean/v1/workdir/cv-en_supervisions_test_orig_punc/filtered/filter_report.json` |

各工作目录下的 `results.jsonl` 保存双引擎识别输出。工作目录用于追溯，不能直接当作已发布的数据入口。

[机器可读登记](../catalog/local_lhotse_derived.jsonl)补充了引擎、train 统计、test 报告及清单落地差异。[逻辑视图](../views/local_lhotse_views.jsonl)仍保留 `inferred` 血缘状态：本次检查没有补齐整个历史流程的工具版本、父版本哈希和全部变换证据。热词派生版未在本次重新扫描，不能把清洗清单的统计直接套用到热词文件。

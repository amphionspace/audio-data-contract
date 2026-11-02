# 鼎桥客户真实录音评测集（tdtech_customer_bench）

`tdtech_customer_bench@v1-20261102` 是鼎桥（td-tech）客户自己提供的真实录音（邮件/Wiki 基线 2026-09-30），用来评测语音识别。录音由 EvalHub 整理发布，本数据集只评测，不进训练。与 `police_scene_bench` 的 TTS 模拟数据不同，这里的音频都来自客户的邮件和 Wiki，基本是设备实录；其中远场信噪比那几条是客户在同一段录音上人工加噪的测试文件。

参考文本**没有全部经过人工听审**，使用时注意下面写明的来源。

## 内容

| split | 条数 | 时长 | 音频来源（EvalHub） | 参考文本 |
|---|---:|---:|---|---|
| `general` | 18 | 0.033 h | `asr/dingqiao-asr-quality@20261016-machine01`（32 条中保留 18 条） | 三份机器转写中有两份一致（见下文） |
| `police-cmd` | 137 | 0.054 h | `asr/dingqiao-asr-police-cmd@20261020-jyjy-v6-human04`（全部） | 录音分组对应的指令词，按《警言警语 V6.0》对齐；39 条经人工听原音确认 |

`general` 的场景写在 `labels.scenario`，保留情况：

| 场景 | 保留 / 原有 | 说明 |
|---|---:|---|
| `ptt` | 7 / 10 | PTT 按键说话 |
| `far_field_snr` | 6 / 7 | 客户 Wiki「BUG-08 远场、噪声与音频采集链路」附件：同一句“你好一二三四”加不同信噪比（30 到 −5 dB）的粉红噪声，噪声是人工加的 |
| `police_badcase` | 3 / 4 | 警务术语与通用识别 badcase |
| `long_speech` | 1 / 5 | 长语句与会议纪要录音 |
| `unconfirmed` | 1 / 4 | 客户验收问题邮件的附件，场景待确认 |
| `far_field_distance` | 0 / 2 | 55 秒远场录音（MIC / VOICE_COMMUNICATION 采集对照） |

`police-cmd` 是 PTT 警务指令短句，`labels.term` 是指令词。

## 参考文本怎么来的

**general**：EvalHub 的机器参考大多来自 Qwen-audio-3.1，2 条来自 MOSS。另用两套不属于 Qwen 系的 ASR 转写同一批音频：FireRedASR2-AED 和 MiMo-V2.5-ASR。三份转写中，有两份按 amphion-eval 原生打分口径（打分版本 3）逐字一致，才保留这条录音：

- 一致的两份里有 EvalHub 参考时，用 EvalHub 的文本；
- 否则用 FireRedASR2-AED 的文本；
- 三份两两都不一致的录音不收，清单在数据目录 `versions/v1-20261102/general-dropped.json`。

一致的录音偏简单（18 条中有 6 条是同一句话的加噪版本）。被筛掉的多是长语音、远场和含警务术语的录音（如“情指行”三份转写都不对），所以这个 split 的数字偏乐观，不代表客户场景的整体水平。EvalHub 把其中一条（`dq-48c903431ae27586`）标成了已核验，但它的文本其实是 Qwen 预标注；本数据集按机器参考处理，这条三份转写也不一致，所以没有收录。

**police-cmd**：参考不是 ASR 的输出，而是说话人照着念的指令词（来自录音分组），并按《警言警语 V6.0》校对了写法。EvalHub 对识别出错的条目做过四轮人工听音：39 条确认后标为 `reference_kind: human`，听不清的已经删掉。FireRedASR2-AED 的转写只作参考，记在 `metadata.transcripts`，不影响是否收录。

每条记录的 `labels.reference_kind`、`labels.reference_source`、`labels.agreed_by` 写明参考来源；`metadata.transcripts` 是各系统的原始转写，`metadata.evalhub` 是 EvalHub 的版本和样例 ID。

## 没有收录的

- 角色分离（20 段，3.88 小时）、机主识别（28 段）、热词（2 段）：没有可靠的参考。热词那两段的机器参考把热词本身写错了（如“文赋成”写成“文富成”），交叉核对也纠正不了，需要人工补热词表和参考文本。
- 超过 200 秒的两段长录音：FireRedASR2-AED 无法解码，MiMo-V2.5-ASR 与 EvalHub 参考也不一致。

## 文件

- 音频按 EvalHub 发布时的原样保存在 `source/evalhub/<类别>_<id>@<版本>/`，构建时按其中的 `files.json` 逐个校验 sha256。
- 两套 ASR 的请求、转写和日志在 `source/firered-aed/`、`source/mimo-asr/`，三选二的结果在 `source/agreement.json`。
- 脚本：`scripts/tdtech_customer_bench/agree.py`（在 amphion-eval 环境中运行，用它的原生打分口径）和 `build.py`。

对应的测试集登记是 amphion-eval 的 `tdtech/customer-asr@v1-20261102`。

## 读取

```bash
audio-data-contract resolve catalog tdtech_customer_bench v1-20261102 records --roots roots.json
```

roots 中的 `tdtech_customer_bench` 指向 `/workspace/data/datasets/tdtech_customer_bench`。

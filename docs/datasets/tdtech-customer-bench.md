# 鼎桥客户真实录音评测集（tdtech_customer_bench）

`tdtech_customer_bench` 是鼎桥（td-tech）客户自己提供的真实录音（邮件/Wiki 基线 2026-09-30），用来评测语音识别、机主识别和热词。录音由 EvalHub 整理发布，本数据集只评测，不进训练。与 `police_scene_bench` 的 TTS 模拟数据不同，这里的音频都来自客户的邮件和 Wiki，基本是设备实录；其中远场信噪比那几条是客户在同一段录音上人工加噪的测试文件。

参考文本**没有全部经过人工听审**，使用时注意下面写明的来源。

| 版本 | 内容 |
|---|---|
| `v1-20261102` | `general`、`police-cmd` |
| `v2-20261102` | 同 v1，另加 `police-cmd-hw300`（警务指令带 300 词热词表）；`general`、`police-cmd` 两个 split 的记录与 v1 逐条相同 |
| `v3-20261103` | 同 v1，另加 `police-cmd-builtin`（警务指令带 audiollm-go 出厂内置热词表整表，1296 条），代替 v2 的 300 词表；`general`、`police-cmd` 与 v1 逐条相同 |
| `v4-20261104` | 同 v3，另加 `owner`（机主识别 6 段）和 `hotword`（人名热词 2 段），两者都经人工听审；“黄静飞/黄敬飞”写法未定，不在人名表里 |
| `v5-20261105` | 同 v4，按客户确认把人名写成“黄晋飞”，并加进人名表（5 个名字）；其余 split 与 v4 逐条相同 |

## 内容

| split | 条数 | 时长 | 音频来源（EvalHub） | 参考文本 |
|---|---:|---:|---|---|
| `general` | 18 | 0.033 h | `asr/dingqiao-asr-quality@20261016-machine01`（32 条中保留 18 条） | 三份机器转写中有两份一致（见下文） |
| `police-cmd` | 137 | 0.054 h | `asr/dingqiao-asr-police-cmd@20261020-jyjy-v6-human04`（全部） | 录音分组对应的指令词，按《警言警语 V6.0》对齐；39 条经人工听原音确认 |
| `police-cmd-builtin`（v3） | 137 | 同上 | 与 `police-cmd` 相同 | 与 `police-cmd` 相同，每条另带出厂内置热词表（1296 条） |
| `police-cmd-hw300`（仅 v2） | 137 | 同上 | 与 `police-cmd` 相同 | 与 `police-cmd` 相同，每条另带 300 词热词表 |
| `owner`（v4 起） | 6 | 0.016 h（测试音） | `target-speaker/dingqiao-ts@20261014`（28 段中有注册音的 6 段） | 机主由人工听审确定，文字取多模型一致转写（见下文） |
| `hotword`（v4 起） | 2 | 0.010 h | `hotword/dingqiao-hotword-quality@20261016-machine01`（全部） | 人工听审确认 |

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

## 热词版

“e警保”“京警智联”这类客户自有的词，不带热词很难认对（FireRedASR2-AED 把 5 条“e警保”全部认错），所以 v2 起把 `police-cmd` 再出一份带热词表的副本。两版共同点：

- 音频、参考与 `police-cmd` 相同，任务是 `asr_hotwords`；`hotwords` 是这条录音念的指令词（`labels.term`）。
- 137 条用同一份热词表（`metadata.bias_lists`），`metadata.distractor_kinds` 标出不是本条指令词的列表词，用于统计误触发。amphion-eval 的热词评测器对每条录音分别跑不带热词表（`none`）和带热词表两种条件。

**v3 `police-cmd-builtin`（固定热词池）**：热词表是 audiollm-go `main-td` 分支的出厂内置热词表 `providers/common/rag/vocabulary/builtin-hotwords-20261102.txt`（1296 条，由《警言警语 V6.0》和鼎桥补充词表生成，客户不传热词时线上也用它），按文件顺序整表发给模型，列表名 `builtin`。副本和来源 commit 在数据目录 `source/audiollm-go/`（`SOURCE.json`），构建时按 sha256 校验。

- 35 个指令词中 32 个在表里；“低压”“咿呀”“签收警单”不在（共 8 条，`labels.term_in_pool: false`），这几条测的是表里没有这个词时会不会被带偏。
- 线上不是整表下发：每段语音先按音频从池里召回最多 50 条、300 字送给模型。这里整表下发（约 4600 token），测的是“给全表时能否认对”，和线上效果不完全相同。

**v2 `police-cmd-hw300`**：300 词热词表，全部 35 个指令词加 265 个干扰词；干扰词从 `police_scene_bench@v1-20261028` 九个 `-hw300` 热词表的并集（1311 个警务术语）里按固定种子随机抽取，再整体打乱（列表名 `list300`）。v3 起改用出厂内置热词表；v2 的生成代码见 git 历史。

## 机主识别和人名热词（v4 起）

**owner**：任务是 `ts_asr`，每条两段音频：`enrollment` 是机主的注册音（同组近场录音，`enroll/<组>/near.wav`），`mixture` 是测试音频，参考是机主在测试音频里说的话。EvalHub 的 28 段机主录音里只有 6 段带同一压缩包里的注册音，其余 22 段没有注册音，不能用来评测。

- 机主是谁：把三段注册音和测试音拼在一起，用本机 MOSS、MOSS-pro、百炼三个说话人日志模型打标，再由人听音，从本机 MOSS 的说话人里选出机主（或判定机主没说话）。
- 机主说的话：每句取本机 MOSS、MOSS-pro、百炼、Qwen3-ASR 中至少两份一致的转写（不计标点）；文字没有经人逐字校对，`labels.reference_kind` 为 `human_speaker_machine_text`。有分歧的句子（如“清单/警单”“我看看/帮我看看”）各模型的写法记在 `metadata.listening.disagreements`。
- 6 段中 5 段机主说话、1 段（“非机主说”）机主没说话，参考为空，`labels.target_present` 区分两类。

**hotword**：两段人名短信指令，任务是 `asr_hotwords`。参考文本按文件名和录音内容定人名写法（文赋成、余祈根、王光辉、潘聪），经人工听审确认。每条带客户 Demo 的人名表（`metadata.bias_lists.demo`）。“黄晋飞”听审时与“黄静飞/黄敬飞”同音分不出，v4 暂写“黄静飞”且不进人名表；v5 按客户确认写成“黄晋飞”并加进人名表（余祈根、黄晋飞、文赋成、王光辉、潘聪），客户确认的写法记在数据目录 `source/customer-names-20261105.json`。

听审结论和每条的选择记在数据目录 `source/listening-review-20261105.json`，打标过程和模型原始输出在 `/workspace/data/runs/tdtech-customer-v4`。

## 参考文本怎么来的

**general**：EvalHub 的机器参考大多来自 Qwen-audio-3.1，2 条来自 MOSS。另用两套不属于 Qwen 系的 ASR 转写同一批音频：FireRedASR2-AED 和 MiMo-V2.5-ASR。三份转写中，有两份按 amphion-eval 原生打分口径（打分版本 3）逐字一致，才保留这条录音：

- 一致的两份里有 EvalHub 参考时，用 EvalHub 的文本；
- 否则用 FireRedASR2-AED 的文本；
- 三份两两都不一致的录音不收，清单在数据目录 `versions/v1-20261102/general-dropped.json`。

一致的录音偏简单（18 条中有 6 条是同一句话的加噪版本）。被筛掉的多是长语音、远场和含警务术语的录音（如“情指行”三份转写都不对），所以这个 split 的数字偏乐观，不代表客户场景的整体水平。EvalHub 把其中一条（`dq-48c903431ae27586`）标成了已核验，但它的文本其实是 Qwen 预标注；本数据集按机器参考处理，这条三份转写也不一致，所以没有收录。

**police-cmd**：参考不是 ASR 的输出，而是说话人照着念的指令词（来自录音分组），并按《警言警语 V6.0》校对了写法。EvalHub 对识别出错的条目做过四轮人工听音：39 条确认后标为 `reference_kind: human`，听不清的已经删掉。FireRedASR2-AED 的转写只作参考，记在 `metadata.transcripts`，不影响是否收录。

每条记录的 `labels.reference_kind`、`labels.reference_source`、`labels.agreed_by` 写明参考来源；`metadata.transcripts` 是各系统的原始转写，`metadata.evalhub` 是 EvalHub 的版本和样例 ID。

## 没有收录的

- 角色分离（20 段会议录音加 5 段在线问题复现）：v4 用三个说话人日志模型加 Qwen3-ASR 打标，多模型严格一致的语音只占约 12%，且偏简单，不足以做参考；暂不收录，也不安排人工标注。
- 机主识别中没有注册音的 22 段。
- 超过 200 秒的两段长录音：FireRedASR2-AED 无法解码，MiMo-V2.5-ASR 与 EvalHub 参考也不一致。

## 文件

- 音频按 EvalHub 发布时的原样保存在 `source/evalhub/<类别>_<id>@<版本>/`，构建时按其中的 `files.json` 逐个校验 sha256。
- 两套 ASR 的请求、转写和日志在 `source/firered-aed/`、`source/mimo-asr/`，三选二的结果在 `source/agreement.json`。
- v4 的听审结论在 `source/listening-review-20261105.json`。
- 出厂内置热词表的副本在 `source/audiollm-go/builtin-hotwords-20261102.txt`，来源见同目录 `SOURCE.json`。
- 脚本：`scripts/tdtech_customer_bench/agree.py`（在 amphion-eval 环境中运行，用它的原生打分口径）和 `build.py`（当前生成 v5）。

对应的测试集登记是 amphion-eval 的 `tdtech/customer-asr@v1-20261102`、`@v2-20261102`（300 词热词表）和 `@v3-20261103`（出厂内置热词表）；v4 是 `tdtech/customer-asr@v4-20261104`（加人名热词列）和 `tdtech/customer-ts@v4-20261104`（机主识别）；`tdtech/customer-asr@v5-20261105` 用 v5 的人名热词。

## 读取

```bash
audio-data-contract resolve catalog tdtech_customer_bench v5-20261105 records --roots roots.json
```

roots 中的 `tdtech_customer_bench` 指向 `/workspace/data/datasets/tdtech_customer_bench`。

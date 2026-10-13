# 目标说话人 ASR 评测集（ts_asr_benchmark）

`ts_asr_benchmark@v1-20261013`：7,740 条 `ts_asr` 记录，60 个场景（split），约 25 小时、3.8 GB。只用于评测，不进训练。评测集登记在 AmphionEval：`open-audio-llm/ts-asr-benchmark@20261013`。

目的是让评测能反映业务里观察到的三类问题：转写了别人、目标缺席时误输出、漏转写。场景设计来自对已发布 checkpoint-34479 的分析（见 open-audio-llm `docs/experiments/2026-10-12-ts-badcase/`），每个场景对应一个具体的怀疑点，而不是随机凑数。

## 一条记录

- `task = "ts_asr"`，`audio_slots` 依次是 `enrollment` 和 `mixture`。
- `target`：目标说话人在混合音频里所有语句按时间顺序拼接的文本；目标缺席或没有说话声时为空字符串，同时 `labels.target_present = false`。
- 干净注册（`enroll_condition = clean`）保存整条语句，由客户端取前 3 秒，和部署行为一致；其余劣化条件保存的就是模型实际收到的 3 秒。
- 混合音频不超过 27 秒（TS 服务的单段上限）。
- `labels`（用于切片）：`scenario`、`group`、`kind`（pos / neg / nonspeech）、`schedule`、`n_interferers`、`enroll_condition`、`noise`、`snr_db`、`reverb`、`target_overlap_ratio`（目标语句时间内有干扰人说话的比例）、`interferer_gain_db`、`interferer_gap_s`、`target_gap_s`、`hard_cosine`、`duration_s`。
- `metadata`：种子、目标说话人、注册语句、目标语句和每个干扰人的语句（文本、起止时间、增益）。用它可以判断输出是不是转写了干扰人。

## 数据来源

说话人只来自各语料的**官方 test 划分**，训练没有见过这些说话人：

| 池 | 来源 | 说话人（合格） |
| --- | --- | --- |
| studio | AISHELL-3 test，棚内朗读，有性别 | 108 |
| phone | KeSpeech test（手机，含方言口音，取 250 位）、MagicData test、AISHELL-2 test | 151 |
| read | AISHELL-1 test | 20 |
| mixed | 上面三个池的并集 | 279 |

合格条件：长度 1.5–9 秒的语句不少于 6 条，且至少一条不短于 3.5 秒（作注册）。噪声用 MUSAN 噪声与音乐、AudioSet 道路交通；房间响应是 DNS5 脉冲响应包里按文件名哈希抽取的 300 个（保存在 `source/<版本>/rir/`）。

## 合成规则

- 每条语句先归一到 −25 dBFS，再按信干比（SIR，目标减干扰，负值表示干扰更响）加增益，所以电平只由增益决定；干扰人每人再随机 ±2 dB。最终峰值归一到 0.5。
- 目标说话人只说**完整语句**；干扰人的最后一句可能被片段末尾截断，加 30 ms 淡出，近似 VAD 切段。
- 干扰人的发言间隔按样本在「稠密 / 中等 / 稀疏」三档里随机，目标和干扰人的重叠程度因此在同一场景内有变化，实际值记在 `target_overlap_ratio`。`burst`、`enter`、`leave`、`short` 场景里别人持续说话（间隔 0–0.5 秒）。
- 目标发言时机（`schedule`）：`full` 连续说话；`burst` 别人一直说，目标只在中间插 1–2 句；`enter` 前半段没有目标，后半段加入；`leave` 目标先说，前半段结束后离场；`alternate` 多人轮流，几乎不重叠；`overlap` 与某个干扰人语句同时开始；`short` 目标只说约 1 秒的短语。
- 目标缺席（`neg`）：注册人是另一个人，不在混合音频中。`abs-hard` 用 ECAPA 余弦相似度挑与某个干扰人最相近的 5 位之一（平均余弦 0.53；同一说话人均值 0.62，不同说话人 p95 0.42），向量保存在 `source/<版本>/speaker-embeddings.npz`。
- 没有说话声（`nonspeech`）：只有噪声、音乐、交通或近乎静音。
- **配对设计**：`enroll-*` 的 9 个条件共用同一批基础场景（相同的说话人、语句、时间和增益，只改注册音频），`dom-clean`、`dom-reverb-noise`、`dom-music`、`dom-traffic` 共用同一批场景（只改背景），`abs-hard` 与 `abs-k2` 共用同一批干扰人（只改注册人）。场景、注册和背景使用三个独立的随机流，所以条件间的差值是配对差值，区间比独立抽样窄得多；`labels.pair` 标明配对组，`analyze.py` 输出配对差值。
- 同一份配方、种子和语料版本生成相同的场景和增益；音频文件通过 `speaker_embeddings.py`、`build.py` 重新生成。

## 场景

「目标在场」报转写字错率（CER）和漏识率，「目标缺席」和「没有说话声」报误输出率。每个场景 150 条（`enroll-*`）或 120 条（其余）。

### A 注册音频劣化（18 个，同一批基础场景：目标 + 1–2 个干扰人）

条件：`clean`、`short1`（仅 1 秒语音）、`lead_silence`（开头 1.5 秒静音）、`lp4k`（4 kHz 低通）、`noise10`（MUSAN 噪声 10 dB）、`reverb`（房间响应）、`contam10` / `contam0`（叠加另一说话人，SIR 10 / 0 dB，后者标签含糊只作压力测试）、`quiet`（降 25 dB，此前实测不敏感，作对照）。每个条件分 `-pos`、`-neg` 两个 split。

### B 进场、离场与缺席（22 个）

`dyn-solo`（对照）、`dyn-full-k1/k4`、`dyn-burst-k1/k2/k4`、`dyn-enter-k2`、`dyn-leave-k2`、`dyn-alternate-k2/k4`、`dyn-overlap-k1/k3`、`dyn-short-k1/k3`、`dyn-target-quiet`（目标轻 6–12 dB）、`dyn-target-loud`（对照）；缺席：`abs-k1/k2/k4`、`abs-hard`、`abs-long`（22–26.5 秒）、`abs-short`（0.4–1.2 秒）。

### C 没有说话声（6 个）

`nonspeech-noise`、`-music`、`-traffic`、`-quiet`、`-short`（0.3–1 秒）、`-long`（22–26.5 秒）。

### D 环境与设备（14 个）

无背景（配对对照）、混响加噪声、背景音乐、道路交通各分在场与缺席；`dom-solo-music`、`dom-solo-traffic`（目标单独说话加背景）；手机录音与棚内录音各分在场与缺席。

## 评测

```bash
ae open-audio-llm ts-asr --model <权重> --data_config <eval-set.yaml> --split_group evaluation \
  --samples_per_source 0 --tsasr-server-url <SEP 服务> --tsasr-served-model <名称> --output_dir <目录>
```

需要 TS 服务（`serve/tsasr.yaml`，插入 `[SEP]`）。`data_config` 用 AmphionEval 的评测集 `open-audio-llm/ts-asr-benchmark@20261013`，设置 `AUDIO_DATA_CATALOG` 和 `AUDIO_DATA_ROOTS_FILE`（别名 `ts_asr_benchmark`）。AmphionEval 报告每个场景的 CER、漏识率和误输出率。更细的诊断（转写了干扰人的比例、复读、按重叠程度和干扰人数切片）用 `scripts/ts_benchmark/analyze.py`。

## 它能和不能说明什么

- 能：模型在可控的场景因素上怎么变化，每个因素独立可比；同一模型换训练后能否修复。
- 不能：真实手机麦克风、户外、真实对话的绝对表现。语音来自朗读语料，没有真实对话的韵律、情绪和抢话；噪声与混响是合成的；说话人数有限。真实数据靠 `business_feedback` 的业务批次和真实会议窗口评测补充。
- 每个场景只有 120–150 条，单个场景的差异需要看置信区间，不要读到小数点后。
- 合成语料里「目标说话人」只是语句的随机组合，没有同一说话人的情绪、语速一致性。

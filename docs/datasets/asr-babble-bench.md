# 普通 ASR 背景人声评测集（asr_babble_bench）

`asr_babble_bench@v2-20261023`：3,200 条、16 列，约 8.8 小时、1.4 GB，`asr` 记录。只用于评测，不进训练。评测集登记在 AmphionEval：`open-audio-llm/asr-babble-bench@v3-20261023`。上一版数据 `v1-20261023` 的背景人声太容易听清（见文末「v1 的问题」），用它的评测集 `@v1-20261023`、`@v2-20261023` 不再用于新的评测。配方 `scripts/asr_babble_bench/recipe.yaml`，生成 `scripts/asr_babble_bench/build.py`，AmphionEval 数据配置 `scripts/asr_babble_bench/eval_set.py`。

来源：AmphionASR 10.21 版本（`amphionasr-1.7b-v4-enroll10-ckpt48000`）的普通 ASR 抗噪差，一段背景人声（babble）会输出一段无关的文字。此前的普通 ASR 评测（ASR-full 16 个测试集）都是干净语音；`open_audio_eval` 的 `cv_*_noise_*` 是整段语音加噪，没有「只有背景人声」的片段；`ts_asr_noise` 有纯背景人声，但走的是目标说话人任务（带注册音频），量不到普通 ASR。

## 两类场景

**只有背景人声**（`kind = noise`，参考为空，期望输出为空，指标为误输出率）：

| 列 | 内容 |
|---|---|
| `zh-babble-far` / `-mid` | 合成中文背景人声，电平 −45～−38 / −38～−31 dBFS（正常说话约 −25 dBFS），2–20 秒。两列是同一批片段，只改电平 |
| `en-babble-far` / `-mid` | 同上，英文 |
| `crowd-wham` | WHAM! 测试划分 `tt` 的真实录音（咖啡馆、餐厅、酒吧等，以英文人声为主），−45～−31 dBFS |
| `crowd-fsd` | FSD50K 评测划分里标为 Crowd 或 Chatter 的真实录音（不含音乐、掌声、欢呼），−45～−31 dBFS |

**一句话前后有背景人声**（`kind = speech`，指标为字错率 / 词错率，插入算在内）：

| 列 | 内容 |
|---|---|
| `zh-clean` | AISHELL-1、MagicData 测试集的一句话（2–12 秒），前后各留 1–5 秒，只有很低的噪声底 |
| `zh-babble20` / `10` / `5` | 同一句话、同样的前后时长，整段叠加中文背景人声，信噪比 20 / 10 / 5 dB；前后那几秒只有背景人声 |
| `zh-babble10-tight` | 与 `zh-babble10` 同一句话、同一段背景人声，没有前后空白（逐样本相同，只差噪声底）。`zh-babble10` 减去它，就是只有背景人声的那几秒带来的错误 |
| `en-*` | 同上，LibriSpeech test-clean |

`zh-*` 与 `en-*` 各自的 5 列是同一批句子、前后时长和背景片段（配方里的 `pair`），只改名字里的那一个因素，可以逐条配对比较。

## 背景人声怎么合成

- 每段 30 秒，16–24 人同时连续说话，每人增益 ±3 dB，句间停 0.1–0.8 秒，整体归一到 −25 dBFS。
- 每段放在一个模拟房间里：SLR28 的中、大房间（`sim_rir_slr28`，长宽 10–50 米），每个房间只有一个接收点，每个说话人站在不同位置（离接收点不超过 5 米），各自卷积自己的房间脉冲响应。听起来是远处的一群人，听不出某一个人说的内容。
- 中英文各 300 段，存在 `source/v2-20261023/babble/`。`manifest.jsonl` 记录每段的房间，以及每个说话人的脉冲响应、语句、文本和在片段里的起止时间，可以检查模型输出是不是转写了某个背景说话人。
- 中文说话人取自 KeSpeech test（1,735 位，有方言口音的手机录音），英文取自 LibriSpeech dev 与 test-other（106 位）。它们不进训练，也不与被转写的目标语音（AISHELL-1、MagicData、LibriSpeech test-clean）重叠，`build.py` 会检查。
- 已登记的 `babble_noise_synth` 没有用：它取自 AISHELL-1 train 和 LibriSpeech train-clean-100，这些句子模型训练时见过。

## 电平约定

- 每句话按 RMS 归一到 −25 dBFS。信噪比按**说话期间**的背景人声 RMS 计算，所以 `-tight` 与有前后空白的同名列信噪比完全一致。
- 所有音频都叠加一层白噪声或粉红噪声底，−65～−55 dBFS（真实录音没有数字静音），记录在 `labels.noise_floor_dbfs`、`noise_floor_kind`。
- 峰值超过 0.99 时整体降电平（相对电平不变），降了多少记在 `labels.peak_scale_db`。

## 一条记录

- `task = "asr"`，一个音频槽 `primary`；`target` 是那句话的文本，只有背景人声时为空字符串；`language` 是 `zh` 或 `en`（`crowd-*` 记为 `en`，参考为空时语言不影响计分）。
- `labels`：`scenario`、`kind`（noise / speech）、`pair`、`noise`（babble_zh、babble_en、wham、fsd_crowd）、`snr_db` 或 `level_dbfs`、`num_talkers`（合成背景人声的人数）、`speech_start_s` / `speech_end_s` / `lead_s` / `trail_s`、`duration_s`。
- `metadata`：种子、目标语句（id、说话人、文本）、背景片段（合成片段的 id 或 `open_noise` 下的相对路径，以及起点）。

## 评测

AmphionEval 的 native 评测器（`amphion_eval.legacy.open_audio_llm.ts_asr`）直接支持：普通 ASR 请求（system 为空、不指定语言），参考为空的列报 `false_alarm_rate`（输出非空的比例），其余列报 CER / WER。

## 评测结果（2026-10-23，v2 数据）

普通 ASR 服务（各自交付包的 `serve.sh asr`；底座用 vLLM 原生加载），native 评测器，全部 3,200 条，`max_new_tokens 512`。百分比，越低越好。

只有背景人声，误输出率（输出非空的比例）：

| 列 | 10.21（v4 ckpt-48000） | 9.26（v3 ckpt-34479） | 底座 Qwen3-ASR-1.7B |
|---|---:|---:|---:|
| zh-babble-far | 25.5 | 100.0 | 4.0 |
| zh-babble-mid | 35.0 | 100.0 | 9.5 |
| en-babble-far | 22.0 | 100.0 | 0.5 |
| en-babble-mid | 28.5 | 100.0 | 2.0 |
| crowd-wham | 7.5 | 100.0 | 13.0 |
| crowd-fsd | 21.0 | 100.0 | 12.0 |

一句话前后有背景人声，CER（中文）/ WER（英文）：

| 列 | 10.21 | 9.26 | 底座 |
|---|---:|---:|---:|
| zh-clean | 2.83 | 1.75 | 2.03 |
| zh-babble20 | 2.55 | 6.19 | 1.98 |
| zh-babble10 | 4.06 | 4.44 | 2.50 |
| zh-babble5 | 6.33 | 22.38 | 5.10 |
| zh-babble10-tight | 2.83 | 1.89 | 2.93 |
| en-clean | 4.78 | 21.64 | 1.48 |
| en-babble20 | 8.86 | 52.22 | 1.45 |
| en-babble10 | 58.45 | 72.35 | 1.99 |
| en-babble5 | 75.11 | 79.83 | 3.28 |
| en-babble10-tight | 2.54 | 2.34 | 1.80 |

观察：

- 只有合成背景人声时，底座几乎不出字（0.5–9.5%），10.21 仍有 22–35%，9.26 版本全部出字。10.21 的输出是编出来的：英文输出的两词组合能在本段背景原文里找到的比例（19.5%）与换成另一段背景时一样；中文三字组合是 5.0% 对 0.4%。英文背景人声上 10.21 的 101 条误输出里有 31 条是中文。
- 真实人群录音上，10.21 与底座接近（WHAM! 7.5 对 13.0，FSD50K 21.0 对 12.0）。
- 英文「续写」仍然明显：10.21 `en-babble10` 58.5%，同一批音频去掉前后空白（`-tight`）只有 2.5%；底座 2.0%。中文同类代价小得多（4.06 对 2.83）。
- 10.21 在 `en-clean` 里有 5%（10/200）输出为空，都是 `language None`，多为 2–3 秒的短句。
- 9.26 版本不稳定：`en-clean` 与 v1 逐样本相同，两次评测有 9 条输出不同，词错率从 9.7% 变成 21.6%，差在它有时输出一段与句子无关的长文本。

## v1 的问题

`v1-20261023` 的背景人声是 8–20 人、没有混响，还有一档 −31～−24 dBFS（与正常说话一样响）的近档。底座在只有背景人声的 6 列上误输出 14–80%，输出的多是背景里某个人的半句话：英文输出的两词组合有 39.5% 能在本段背景原文里找到，换成另一段背景只有 8.9%（中文三字组合 20.4% 对 0.2%）；人越少越多（英文 8–11 人 52.5%，16–20 人 8.5%）。误输出率因此把「转写听得清的背景说话人」和「编出无关的句子」算成了同一种错。

v2 改成 16–24 人、加房间混响、去掉近档，真实人群录音的电平上限也降到 −31 dBFS。目标语句、前后时长、信噪比和配对方式不变，`zh-clean`、`en-clean` 两列与 v1 逐样本相同。

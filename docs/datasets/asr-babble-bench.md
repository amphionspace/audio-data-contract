# 普通 ASR 背景人声评测集（asr_babble_bench）

`asr_babble_bench@v1-20261023`：3,600 条、18 列，约 10.1 小时、1.5 GB，`asr` 记录。只用于评测，不进训练。配方 `scripts/asr_babble_bench/recipe.yaml`，生成 `scripts/asr_babble_bench/build.py`，AmphionEval 数据配置 `scripts/asr_babble_bench/eval_set.py`。

来源：AmphionASR 10.21 版本（`amphionasr-1.7b-v4-enroll10-ckpt48000`）的普通 ASR 抗噪差，一段背景人声（babble）会输出一段无关的文字。此前的普通 ASR 评测（ASR-full 16 个测试集）都是干净语音；`open_audio_eval` 的 `cv_*_noise_*` 是整段语音加噪，没有「只有背景人声」的片段；`ts_asr_noise` 有纯背景人声，但走的是目标说话人任务（带注册音频），量不到普通 ASR。

## 两类场景

**只有背景人声**（`kind = noise`，参考为空，期望输出为空，指标为误输出率）：

| 列 | 内容 |
|---|---|
| `zh-babble-far` / `-mid` / `-near` | 合成中文背景人声，电平 −45～−38 / −38～−31 / −31～−24 dBFS（正常说话约 −25 dBFS），2–20 秒。三列是同一批片段，只改电平 |
| `en-babble-far` / `-mid` / `-near` | 同上，英文 |
| `crowd-wham` | WHAM! 测试划分 `tt` 的真实录音（咖啡馆、餐厅、酒吧等，以英文人声为主），−45～−24 dBFS |
| `crowd-fsd` | FSD50K 评测划分里标为 Crowd 或 Chatter 的真实录音（不含音乐、掌声、欢呼），−45～−24 dBFS |

**一句话前后有背景人声**（`kind = speech`，指标为字错率 / 词错率，插入算在内）：

| 列 | 内容 |
|---|---|
| `zh-clean` | AISHELL-1、MagicData 测试集的一句话（2–12 秒），前后各留 1–5 秒，只有很低的噪声底 |
| `zh-babble20` / `10` / `5` | 同一句话、同样的前后时长，整段叠加中文背景人声，信噪比 20 / 10 / 5 dB；前后那几秒只有背景人声 |
| `zh-babble10-tight` | 与 `zh-babble10` 同一句话、同一段背景人声，没有前后空白（逐样本相同，只差噪声底）。`zh-babble10` 减去它，就是只有背景人声的那几秒带来的错误 |
| `en-*` | 同上，LibriSpeech test-clean |

`zh-*` 与 `en-*` 各自的 5 列是同一批句子、前后时长和背景片段（配方里的 `pair`），只改名字里的那一个因素，可以逐条配对比较。

## 背景人声怎么合成

- 每段 30 秒，8–20 人同时连续说话，每人增益 ±3 dB，句间停 0.1–0.8 秒，整体归一到 −25 dBFS；人多、电平接近，听不清某一个人说的内容。中英文各 300 段，存在 `source/v1-20261023/babble/`，`manifest.jsonl` 记录每段每个说话人的语句、文本和在片段里的起止时间，可以检查模型输出是不是转写了某个背景说话人。
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

## 首次评测（2026-10-23）

普通 ASR 服务（各自交付包的 `serve.sh asr`；底座用 vLLM 原生加载），native 评测器，全部 3,600 条，`max_new_tokens 512`。百分比，越低越好。

只有背景人声，误输出率（输出非空的比例）：

| 列 | 10.21（v4 ckpt-48000） | 9.26（v3 ckpt-34479） | 底座 Qwen3-ASR-1.7B |
|---|---:|---:|---:|
| zh-babble-far | 53.5 | 100.0 | 33.5 |
| zh-babble-mid | 67.5 | 100.0 | 61.5 |
| zh-babble-near | 74.0 | 100.0 | 80.0 |
| en-babble-far | 59.0 | 100.0 | 14.0 |
| en-babble-mid | 71.5 | 100.0 | 32.5 |
| en-babble-near | 81.5 | 100.0 | 44.0 |
| crowd-wham | 8.5 | 100.0 | 11.5 |
| crowd-fsd | 21.5 | 100.0 | 13.5 |

一句话前后有背景人声，CER（中文）/ WER（英文）：

| 列 | 10.21 | 9.26 | 底座 |
|---|---:|---:|---:|
| zh-clean | 2.79 | 1.65 | 2.03 |
| zh-babble20 | 3.02 | 6.94 | 2.22 |
| zh-babble10 | 4.25 | 23.14 | 3.59 |
| zh-babble5 | 11.43 | 55.38 | 9.30 |
| zh-babble10-tight | 2.74 | 2.64 | 2.41 |
| en-clean | 4.78 | 9.67 | 1.45 |
| en-babble20 | 27.94 | 40.82 | 1.64 |
| en-babble10 | 73.92 | 61.01 | 2.06 |
| en-babble5 | 89.92 | 92.87 | 5.23 |
| en-babble10-tight | 2.38 | 2.57 | 2.18 |

观察：

- 只有背景人声时，三个模型都会出字。9.26 版本在全部 1,600 条上都输出了文字（多为整段英文小说式文本，或重复到 512 个 token 的上限），10.21 降到 53–82%，但英文仍远高于底座（远场 59.0% 对 14.0%）；中文远场（−45～−38 dBFS）10.21 是 53.5%，底座 33.5%。10.21 的误输出大多是与背景内容无关的通顺句子：用 `manifest.jsonl` 比对，能对上某个背景说话人语句的（rapidfuzz partial_ratio ≥ 80）中文只占 10–13%、英文约 5%；底座是 20–25%，更像是在转写某个背景说话人。
- 英文退化最明显：`en-babble10` 的 WER 是 73.9%，同一批音频去掉前后空白（`en-babble10-tight`）只有 2.4%，多出来的几乎全是插入（62 个百分点）。10.21 在句子说完后的背景人声里接着往下「续写」，续写的内容像原书的下文（例如把 “…the fine old furniture gave” 续成 “…a hint of its real elegance and polish”）。底座同一列 2.1%，9.26 版本 61.0%。
- 中文同类代价在 10.21 上小得多：`zh-babble10` 比 `-tight` 高 1.5 个百分点，插入多在句首、句尾的几个字；9.26 版本是 23.1% 对 2.6%。
- 另一个现象：10.21 在 `en-clean`（前后只有很低的噪声底）里有 5%（10/200）输出为空，都是 `language None`，多为 2–3 秒的短句；`en-babble10-tight` 没有这个问题。

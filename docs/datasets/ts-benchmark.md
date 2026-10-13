# 目标说话人 ASR 评测集（ts_asr_benchmark）

三个版本：**v1-20261013**（60 个场景、7,740 条，发言间隙是数字静音）、**v2-20261013**（64 个场景，所有场景加合成噪声底，并新增真实注册录音场景）和 **v3-20261013**（110 个场景、13,900 条，噪声底和房间响应换成真实录音，并新增脆弱性面板）。新的评测和训练验收用 v3，v1、v2 保留作连续性对照。三个版本的前 60 个场景的说话人、语句、时间和增益逐条相同，同名场景可以做配对比较。真实对话见 [ts_asr_real](ts-real.md)。

`ts_asr_benchmark`：`ts_asr` 记录，约 25 小时、3.8 GB（每个版本）。只用于评测，不进训练。评测集登记在 AmphionEval：`open-audio-llm/ts-asr-benchmark@20261013`（v1）和 `@v2-20261013`。

目的是让评测能反映业务里观察到的三类问题：转写了别人、目标缺席时误输出、漏转写。场景设计来自对已发布 checkpoint-34479 的分析（见 open-audio-llm `docs/experiments/2026-10-12-ts-badcase/`），每个场景对应一个具体的怀疑点，而不是随机凑数。


## v2 与 v1 的区别

- **噪声底**：v1 的发言间隙是精确的 0，而真实录音总有噪声底。对比实验表明模型对噪声底非常敏感（−60 dBFS 的几乎听不见的白噪声就让缺席误输出率翻倍），v1 因此低估了失败。v2 给每个场景的混合音频和注册音频各加一层白噪声或粉红噪声，电平在 −65 到 −35 dBFS 均匀抽取（说话约 −25 dBFS），记录在 `labels.noise_floor_dbfs` 和 `noise_floor_kind`。噪声底在场景之后抽取，所以场景本身与 v1 逐条相同。
- **真实注册录音**（`realreg` 组，4 个场景）：业务反馈里测试人员的两段真实注册录音（`enrollment_files`，来自 `business_feedback`），配上没有他的说话人（`realreg1-neg`、`realreg2-neg`，各 200 条）和纯音乐（`realreg1-music`、`realreg2-music`，各 120 条），给出对这两段注册录音有统计意义的误输出率。记录的 `labels.enroll_file` 标明用的是哪一段。
- 注意：v2 里 `enroll-quiet` 不再只是电平对照。注册音频降 25 dB 后，加上噪声底，注册的信噪比可能为负，结果显示它与「注册仅 1 秒语音」同样严重。

## v3：真实噪声、真实房间响应和脆弱性面板

- **噪声底改用真实录音**：底噪池是 WHAM!（咖啡馆、餐厅、酒吧、公园和街道的真实环境噪声）、DNS5 的 AudioSet 与 Freesound 噪声（只取电平稳定的片段，即 0.5 秒帧电平的标准差小于 3 dB 且没有突出的事件）、白噪声和粉红噪声，默认权重 70% 真实、30% 合成，电平 −65 到 −35 dBFS（说话约 −25 dBFS）。`labels.noise_floor_kind` 记录用的是哪个池，`noise_floor_clip` 是片段名。素材由 `prepare_noise.py` 流式取出，保存在 `source/<版本>/noise/`，不解压整个 DNS5 压缩包。没有找到真实手机的纯环境录音（业务反馈的片段里没有稳定的静态噪声），所以没有手机设备底噪。
- **房间响应**：`prepare_noise.py` 另外准备 SLR28 的实测响应（178 个）和模拟的小、中、大房间（各 100 个），加上 DNS5 的模拟响应，`rir` 参数可以指定池。
- **脆弱性面板**（`panel` 组，42 个场景，每个 120 条）：`panel-base-pos/neg` 是共同基线（目标 + 1–2 个干扰人，默认底噪、干燥房间、正常电平），其他场景与它共用同一批基础场景，一次只改一个因素。底噪场景的底噪不随房间或背景改变，因此条件间是严格配对：
  - `floor-*`：无底噪、白、粉红、WHAM −60/−50/−40/−30 dBFS、DNS5 AudioSet、DNS5 Freesound；
  - `room-*`：实测、模拟小、中、大、DNS5 模拟；
  - `level-*`：整体电平降 20、10 dB，升 10 dB（业务第一批包电平 −41 到 −46 dBFS、第二批 −16 到 −31 dBFS，评测集默认 −25 dBFS），以及削波、3.4 kHz 窄带、μ 律编码三个诊断条件。
- **组合压力**（`stress-outdoor`、`stress-office`）：几种不利因素同时出现，只作诊断。
- **现实性原则**：评测条件基于业务现实，不做极端测试。削波、电话编码、窄带、`enroll-contam0`（0 dB 注册污染）和组合压力是诊断条件，在 AmphionEval 的评测集里不进分组，因此不计入平均，也不进 `analyze.py` 的脆弱点排序。
- `analyze.py` 增加：`--run` 可给多个目录（评测被拆成几份时），脆弱点排序（区间不含 0 的变差，按变化量），`--dataset` 选择数据集。

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

### E 真实注册录音（4 个，仅 v2）

`realreg1-neg`、`realreg2-neg`、`realreg1-music`、`realreg2-music`，见上文「v2 与 v1 的区别」。

## 评测

```bash
ae open-audio-llm ts-asr --model <权重> --data_config <eval-set.yaml> --split_group evaluation \
  --samples_per_source 0 --tsasr-server-url <SEP 服务> --tsasr-served-model <名称> --output_dir <目录>
```

需要 TS 服务（`serve/tsasr.yaml`，插入 `[SEP]`）。`data_config` 用 AmphionEval 的评测集 `open-audio-llm/ts-asr-benchmark@20261013`，设置 `AUDIO_DATA_CATALOG` 和 `AUDIO_DATA_ROOTS_FILE`（别名 `ts_asr_benchmark`）。AmphionEval 报告每个场景的 CER、漏识率和误输出率。更细的诊断（转写了干扰人的比例、复读、按重叠程度和干扰人数切片、配对差值）用 `scripts/ts_benchmark/analyze.py`；`--compare <另一次运行>` 在同一批样本上给出两次运行（两个模型或两个 checkpoint）的配对差值，是训练前后对比的标准方式。`scripts/ts_benchmark/gate_scores.py` 输出每条记录的说话人验证分数（WeSpeaker ECAPA 余弦），用于评估外部验证门。

## 它能和不能说明什么

- 能：模型在可控的场景因素上怎么变化，每个因素独立可比；同一模型换训练后能否修复。
- 不能：真实手机麦克风、户外、真实对话的绝对表现。语音来自朗读语料，没有真实对话的韵律、情绪和抢话；噪声与混响是合成的；说话人数有限。真实数据靠 `business_feedback` 的业务批次和真实会议窗口评测补充。
- 每个场景只有 120–200 条，单个场景的差异需要看置信区间，不要读到小数点后。同一模型两次独立运行的差异：误输出率平均 0.4、最大 1.7 个百分点，CER 平均 0.5、最大 1.9 个百分点，所以小于 2 个百分点的差异按噪声处理。
- v1 的场景没有噪声底，会低估误输出；v2 的噪声底是合成的白噪声或粉红噪声，不是真实房间噪声。
- 音乐来自 MUSAN，几乎没有带人声的歌曲；评测里没有带人声的歌。
- 合成语料里「目标说话人」只是语句的随机组合，没有同一说话人的情绪、语速一致性。

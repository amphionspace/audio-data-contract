# 目标说话人训练的素材池

训练目标说话人 ASR（TS-ASR）时，在线混合需要「别人的声音」「没有人声的声音」「多句场景」和「真实噪声、房间响应」。这些素材登记为下面五份数据。它们只用于训练；评测用 [ts_asr_benchmark](ts-benchmark.md)，两边的说话人和噪声互不重叠（见最后一节）。

| 数据 | 版本 | 内容 | 规模 |
| --- | --- | --- | --- |
| `ts_interference_pool` | `v2-20261016`（`v1-20261015` 为首版） | 干扰人：单人语音片段，按偏移取自源文件 | zh 32 万条 389 h、en 20 万条 268 h |
| `ts_nonspeech_pool` | `v1-20261016` | 没有人声的噪声和音乐，转写为空 | 4.8 万条 65.7 h |
| `ts_scene_pool` | `v2-20261016`；`hard-20261016`；`multi-20261017` | 多句场景：alternate / burst / short；相近声音版；目标说多句的并行版（full，含缺席孪生） | v2：zh 15 万条、en 10 万条；hard：zh 4 万条、en 2.5 万条；multi：zh 12 万条、en 4 万条 |
| `ts_real_train` | `v1-20261017`；`v2-20261018` | 真实会议窗口（训练划分），在场与缺席成对。v1 按 1 / 2 / 3+ 人分档；v2 以目标为锚开窗、按重叠比例分档，带窗口内每句的时间戳 | v1：9.1 万条（alimeeting 2.5 万、aishell4 3.0 万、ramc 3.7 万）；v2：8.4 万条（alimeeting 4.2 万、aishell4 3.0 万、ramc 1.2 万） |
| `babble_noise_train` | `v1-20261017` | 合成背景人声（babble）训练划分，可作噪声或空目标 | zh、en 各 2,600 条，30 秒 |
| `dns5_noise_train` | `v1-20261016` | DNS5 的 AudioSet 和 Freesound 噪声，以及模拟房间响应 | 见下 |
| `audioset_road_traffic` | `legacy-20260804` | 道路交通噪声（早已登记，这里只说明用法） | 10.9 万条 299 h |

训练配置里的用法见 open-audio-llm 的 `train-data-v3-scene.yaml`（`interference_sources`、`nonspeech_sources`、`noise_sources`、`rir_sources` 和 `ts_scene_pool` 的 `online_mix`）。

## 格式

前三份是 `records` + `audio_index`：记录里的片段指向源文件的一段（`cut_id`、`start`、`duration`），不复制音频；`audio_index` 给出源文件位置。三份都建了 Lance 记录索引（`record_index`，映射 1.2），`check-registration --require-record-index` 通过。`dns5_noise_train` 是 Lhotse 录音清单，音频是登记目录下的 FLAC / WAV。

## ts_interference_pool

在线混合里叠加的「别人」。片段 1–15 s，按来源限量：

| 来源 | 限量 | 条数 |
| --- | --- | --- |
| Emilia2 short（zh / en） | 每个源视频 ≤15 条，不测质量 | 15 万 / 10 万 |
| KeSpeech | 每人 ≤40 条 | 9 万 |
| WenetSpeech youtube / podcast | 每个来源 ≤10 条 | 各 4 万 |
| Common Voice en | 每人 ≤20 条 | 5 万 |
| GigaSpeech | 每个来源 ≤10 条 | 5 万 |

- 排除 AISHELL-2 和 LibriSpeech：AISHELLMix、LibriMix 的目标说话人来自这两个语料，干扰人再取它们会让目标和干扰人出现在同一说话人里。
- 质量门槛只留 `voiced_ratio ≥ 0.5` 和响度 ≥ −50 dBFS（Emilia2 不测）；`loudness_dbfs`、`clip_ratio`、`voiced_ratio` 写在记录 `metadata`，进了 Lance 索引的质量列。
- `speaker` 只有 KeSpeech 和 Common Voice 有真实标签；其余来源用 `source_group`（源视频或来源分组）近似同一人。

## ts_nonspeech_pool

转写为空（`task = asr`，`target = ""`）的噪声和音乐片段，用于让普通 ASR 在没有人声时输出空。来源 MUSAN 噪声和音乐各 2.4 万条，时长在 0.3–26 s 之间对数均匀。电平在训练时抽取（配置里 `nonspeech: {level_dbfs: [...]}`）。

不含 WHAM：它录自咖啡馆和酒吧，里面有听得出内容的人声，不能当作「没有人声」。

## ts_scene_pool

每条记录给出一个场景里的全部语句，加载时只负责放到时间线上，混响、电平、噪声底仍在训练时随机。三种模式对应评测集的同名时机：

| 模式 | 做法 |
| --- | --- |
| `alternate` | 目标说 1–2 句，与 2–6 个其他说话人轮流，句间 0.2–1 s，互不重叠 |
| `burst` | 1–6 个其他说话人各连续说 2–4 句（间隔 0–0.5 s），目标夹在中间 |
| `short` | 0.8–2.5 s 的短目标（英文 ≤3.5 s），夹在 1–5 个其他说话人的话里 |

- 说话人来自带真实说话人标签的语料，经 Lance 记录索引按说话人取多句：zh 目标为 AISHELL-2，其他说话人为 AISHELL-2 和 KeSpeech；en 目标为 LibriSpeech，其他说话人为 LibriSpeech 和 Common Voice。均取 train 划分。
- 其他说话人彼此不同，也不同于目标；注册音频是目标说话人的另一句。
- 场景总长有上限（alternate 30 s、burst 22 s、short 14 s，含间隔），超出的重抽。`metadata.scene` 里是 `mode`、`targets`（含文本）、`enrollment`、`interferers`；`target` 是目标语句按时间顺序拼接的文本，中文直接拼，英文用空格。
- 实测（训练加载器抽样）：burst、short 的目标重叠率中位 1.0，alternate 中位 0。

### 相近声音版（hard-20261016）

对应评测集的 `abs-hard`（目标缺席但有相近的声音）和目标在场时有相近声音干扰。每条记录里其他说话人的第一位是目标的相近说话人，取自说话人向量余弦最近邻的前 10 名之一（按排名挑，不设阈值：不同语料的最佳阈值差到 0.33–0.60，固定阈值会在各语料里选出不同的东西）。

- `absent`（约 55%）：注册音频是 A，场景里只有相近的 B 和其他人，转写为空，`labels.target_present = false`；几何是 alternate 或 burst。
- `present`（约 45%）：目标 A 说话，相近的 B 同时在场，几何是 alternate、burst 或 short。
- 说话人向量用 ERes2NetV2：每个说话人取 4 句 2–8 s 的语句的归一化向量均值。候选包含目标语料外的 KeSpeech（随机 6000 位）和 Common Voice en（随机 6000 位）。最近邻表和向量在 `datasets/ts_scene_pool/source/speaker-neighbors-20261016/`（`neighbors.json`、`embeddings.npz`、`report.json`），生成脚本 `scripts/ts_robust/speaker_neighbors.py`。
- 最相近一位的余弦中位数：zh 0.69（p10–p90：0.62–0.77），en 0.74（0.67–0.79）。这是 ERes2NetV2 的尺度，评测集的 `hard_cosine`（0.53）用的是 ECAPA，两个数不能直接比。
- `labels.hard_cosine` 记录该相近说话人与目标的余弦。

### 多句目标版（multi-20261017）

对应评测集 ts_asr_benchmark 的基础场景：目标说 2–5 句，其他说话人（1–4 个）各自按自己的节奏说话，目标的几句被别人的话打断或盖住。checkpoint-7000 在这类评测样本上删除率从约 10% 涨到 26%–34%，而训练的场景池里目标说两句的样本只占约 1.3%（见 open-audio-llm 的 `docs/experiments/2026-10-17-ts-v7-data/plan.md`）。

| 项 | 做法 |
| --- | --- |
| 模式 | `full`：并行轨道，目标和每个其他说话人各一条，起点在加载时随机错开；记录里写 `target_gap` 和 `interferers[].gap`（说话人自己两句之间的停顿范围，秒） |
| 目标句数 | 2 / 3 / 4 / 5 句，概率 0.4 / 0.3 / 0.2 / 0.1；每句 1.5–9 秒；参考文本是各句按时间顺序拼接 |
| 其他说话人 | 1 / 2 / 3 / 4 个，概率 0.3 / 0.3 / 0.25 / 0.15；每人的轨道长度约为目标轨道的 0.7–1.3 倍，最多 6 句 |
| 停顿 | 四档：0.2–1 s（两档权重）、1–3 s、2.5–6 s，和评测集的发言间隙一致；每个说话人各抽一档 |
| 场景长度 | 以最大停顿计不超过 32 s；实际窗口 p50 约 15 s，p90 约 24 s |
| 缺席孪生 | 约 26% 的记录是孪生：同一批语句和停顿，目标的语句变成另一个干扰人的，注册人换成场景外的另一位（一半取目标的近邻声音，一半随机），转写为空；孪生对共用 `labels.pair`，`labels.twin_enrollment` 为 `near` 或 `random` |
| 说话人与语料 | 同 v2：zh 目标取 AISHELL-2，其他说话人取 AISHELL-2 与 KeSpeech；en 目标取 LibriSpeech，其他取 LibriSpeech 与 Common Voice；均为 train 划分 |
| 规模 | zh 12 万条（含孪生 3.1 万）、en 4 万条（含孪生 1.0 万） |

加载需要训练端支持 `full` 模式（open-audio-llm PR #60）：`build_scene` 按记录里的停顿范围拼接，`scene_seconds` 用同样的上界给采样器估长度。生成命令：

    python build_ts_scene_pool.py --output-dir DIR --version multi-20261017 --multi --neighbors FILE --zh 120000 --en 40000

## dns5_noise_train

DNS5 噪声包里的 AudioSet 和 Freesound 噪声（16 kHz 单声道 FLAC，≤30 s，RMS 归一到 −30 dBFS，与评测集的噪声同样处理），以及模拟房间响应。split：

| split | 内容 |
| --- | --- |
| `audioset`、`freesound` | 全部噪声片段 |
| `stationary` | 电平稳定（0.5 s 帧电平标准差 <3 dB 且无突出事件）的片段，适合做噪声底 |
| `rir` | `impulse_responses_000` 里的模拟房间响应，保留原电平 |

录音的 `custom` 记录 `stationary`、`level_std_db`、`peak_over_median_db`。提取脚本 `scripts/ts_robust/prepare_training_noise.py`，按流式读取，不解压整个压缩包。

## ts_real_train

评测集 ts_asr_real 的真实对话窗口用官方测试划分；这里用同样的方法在 **train 划分**上切窗口：AliMeeting 远场（`alimeeting_sdm@icefall-20260908`）、AISHELL-4（`aishell4@icefall-20260908`）、MagicData-RAMC 手机通话（`magicdata_ramc@icefall-20260908`）。8–22 秒、由完整语句组成，窗口之间不重叠，说话人数分 `1spk`、`2spk`、`3plus` 三档，每个语料每档最多 1 万个窗口（`labels.bucket`）。

- 每个窗口一对样本，音频相同：目标在场（窗口里说话不少于 1 秒的一位，注册取窗口外同一录音的另一句，3–6 秒）和目标缺席（同一录音里没在窗口说话的另一人；没有则取其他录音，`labels.absent_source` 记录是哪一种）。同一对共用 `labels.pair`。
- 为什么另做：现有的会议 `train_neg`（`turn-taking-20261014`）窗口里总有 2–3 个说话人，没有「窗口里只有另一个人在说话」的样本，而评测的真实缺席误输出最高的正是 1 人窗口（AISHELL-4：checkpoint-7000 为 26%）；它们还把 8 路麦克风取平均，评测读第 0 声道。
- 声道：每个槽位的引用写 `channel: 0`，加载器只读第 0 声道，与评测一致；音频索引里的 `channels` 是文件真实声道数。
- 记录是长录音上的片段，不复制音频；规模：alimeeting 2.5 万条（含 1 人窗口 1,395 个）、aishell4 3.0 万条（2,618 个）、ramc 3.7 万条（8,324 个）。ramc 是两人通话，2 人窗口里没有缺席的人，缺席样本取其他通话的说话人。
- 与评测互不重叠：评测用官方测试划分的录音，这里用 train 划分。生成脚本 `scripts/ts_robust/build_ts_real_train.py`。

**`v2-20261018`（`--recipe v2`）：重叠窗口。** v1 的窗口要求所有人的语句完整，重叠多的段落几乎都切不进来；v2 改用 ts_asr_real `overlap-v1-20261017` 的开窗方法，用于训练个人 VAD 这类需要逐帧标签、要见到重叠的模型。

- 以目标为锚：窗口从目标某句前 0–4 秒开到其后 8–22 秒（不超过 26 秒），目标的语句完整，别人的语句截到窗口边界（`window_utts` 里标 `clipped`）。
- 按目标语音被别人盖住的比例分档（`labels.overlap_bucket`）：`o0` ≤5%、`o20` 5–20%、`o50` 20–50%、`o100` >50%。每档配额：alimeeting 3,000 / 4,000 / 6,000 / 8,000，aishell4 各 4,000（`o100` 只凑到 2,959，与已选窗口重叠过半的窗口被跳过），ramc 只有 `o0` 6,000（标注没有重叠）。
- `metadata.window_utts`：窗口内每句的说话人、相对窗口起点的起止和文本，格式同 ts_asr_real，可直接生成逐帧的目标 / 他人活动标签。
- 去掉含 dev / test 说话人的录音（ramc 14 段，alimeeting、aishell4 没有），评测和选模的说话人不进训练。
- 其余同 v1：成对样本、注册取同一录音窗口外的另一句、`channel: 0`、不复制音频。

## babble_noise_train

`babble_noise_synth` 的 zh、en 训练划分（每种语言 2,600 条，每条 30 秒，5–20 位说话人同时说话）。原数据集只登记了源目录和 manifest，训练加载器读不了，这里写成 Lhotse 录音清单，可以放进 `noise_sources`（叠加在目标说话人场景上）或 `nonspeech_sources`（空目标）。评测的 babble 来自 dev / test 说话人，与训练说话人互不重叠。脚本 `scripts/ts_robust/register_babble_noise.py`。

## 与评测集互不重叠

- **说话人**：评测集的说话人只来自各语料的官方 test 划分（AISHELL-1/3 test、KeSpeech test、MagicData test、AISHELL-2 test）；这里的目标说话人和其他说话人取 train 划分。
- **DNS5 噪声**：评测集取每个压缩包里最先出现的 80 个可用片段；训练跳过它们（按评测集 `noise/manifest.json` 的片段 ID 排除）。
- **DNS5 房间响应**：评测集取文件名哈希最小的 300 个；训练取哈希排序之后的，按同一个键排序，因此划分是精确的。
- **道路交通噪声**：评测集从整个 `audioset_road_traffic` 随机抽片段，没有单独划出训练部分，所以训练和评测可能用到同一条交通录音。这是噪声类型的重叠，不是说话人或语句的重叠；评测每条样本只抽一段，用到的录音只占整个池的一小部分。

## 生成脚本

`scripts/ts_robust/`：`build_interference_pool.py`、`build_nonspeech_pool.py`、`build_ts_scene_pool.py`、`speaker_neighbors.py`、`prepare_training_noise.py`、`register_training_noise.py`、`register_records_pool.py`（把 `records` + `audio_index` 版本写成声明）、`build_ts_real_train.py`、`register_babble_noise.py`。登记后用 `build-record-index --register` 建索引。

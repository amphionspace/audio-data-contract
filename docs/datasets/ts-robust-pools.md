# 目标说话人训练的素材池

训练目标说话人 ASR（TS-ASR）时，在线混合需要「别人的声音」「没有人声的声音」「多句场景」和「真实噪声、房间响应」。这些素材登记为下面五份数据。它们只用于训练；评测用 [ts_asr_benchmark](ts-benchmark.md)，两边的说话人和噪声互不重叠（见最后一节）。

| 数据 | 版本 | 内容 | 规模 |
| --- | --- | --- | --- |
| `ts_interference_pool` | `v2-20261016`（`v1-20261015` 为首版） | 干扰人：单人语音片段，按偏移取自源文件 | zh 32 万条 389 h、en 20 万条 268 h |
| `ts_nonspeech_pool` | `v1-20261016` | 没有人声的噪声和音乐，转写为空 | 4.8 万条 65.7 h |
| `ts_scene_pool` | `v2-20261016` | 多句场景：alternate / burst / short | zh 15 万条、en 10 万条 |
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

## dns5_noise_train

DNS5 噪声包里的 AudioSet 和 Freesound 噪声（16 kHz 单声道 FLAC，≤30 s，RMS 归一到 −30 dBFS，与评测集的噪声同样处理），以及模拟房间响应。split：

| split | 内容 |
| --- | --- |
| `audioset`、`freesound` | 全部噪声片段 |
| `stationary` | 电平稳定（0.5 s 帧电平标准差 <3 dB 且无突出事件）的片段，适合做噪声底 |
| `rir` | `impulse_responses_000` 里的模拟房间响应，保留原电平 |

录音的 `custom` 记录 `stationary`、`level_std_db`、`peak_over_median_db`。提取脚本 `scripts/ts_robust/prepare_training_noise.py`，按流式读取，不解压整个压缩包。

## 与评测集互不重叠

- **说话人**：评测集的说话人只来自各语料的官方 test 划分（AISHELL-1/3 test、KeSpeech test、MagicData test、AISHELL-2 test）；这里的目标说话人和其他说话人取 train 划分。
- **DNS5 噪声**：评测集取每个压缩包里最先出现的 80 个可用片段；训练跳过它们（按评测集 `noise/manifest.json` 的片段 ID 排除）。
- **DNS5 房间响应**：评测集取文件名哈希最小的 300 个；训练取哈希排序之后的，按同一个键排序，因此划分是精确的。
- **道路交通噪声**：评测集从整个 `audioset_road_traffic` 随机抽片段，没有单独划出训练部分，所以训练和评测可能用到同一条交通录音。这是噪声类型的重叠，不是说话人或语句的重叠；评测每条样本只抽一段，用到的录音只占整个池的一小部分。

## 生成脚本

`scripts/ts_robust/`：`build_interference_pool.py`、`build_nonspeech_pool.py`、`build_ts_scene_pool.py`、`prepare_training_noise.py`、`register_records_pool.py`（把 `records` + `audio_index` 版本写成声明）。登记后用 `build-record-index --register` 建索引。

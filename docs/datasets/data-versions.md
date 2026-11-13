# 数据版本明细

[数据总览](data-overview.md)中每个数据集的展开：各已登记版本的时长、口径、COS 地址和说明。

- 时长单位为小时。不同版本、子集和标注片段可能重叠，不相加为总量。
- 口径：已登记为各顶层划分时长之和或发布方总时长；估算为名义时长；部分划分为只有部分划分登记了时长；过滤前不能当作清洗后时长；参考表数字未核实当前文件与划分覆盖。
- 已被合并版本取代（`superseded_by`）的旧版本不再列出，仍可按原 ID 和版本解析。
- 任务是各版本能力的并集，具体版本和划分以链接内声明为准。标点、热词和文件哈希校验都不能单独证明做过内容清洗。

COS 列：

- 快照 20260914：`cos://amphion-audio-backup-1373259071/audio-data-contract/v1/full-catalog-20260914/`
- 快照 20260921：`cos://amphion-audio-backup-1373259071/audio-data-contract/v1/batches/police-v6-acceptance-205-20260921/`
- 快照内的文件按内容去重分批存放，要用 [cos_restore.py](../guides/cos-restore.md) 按版本取回；快照只表示该版本纳入了这次同步，文件是否已上传以 `locate` 结果为准。
- 其他地址是桶内目录，可直接 `ab pull`（备份桶 = `amphion-audio-backup-1373259071`、TTS 桶 = `amphion-tts-data-1373259071`）。标“原始数据”的是登记版本所依据的原始文件，取回后还要按来源说明处理。
- 没有：仓库里没有 COS 记录；“部分版本：”表示只有部分版本有。

## 英文数据

### ami_ihm

AMI 英文会议的近讲耳麦版

语言：en · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [ami_ihm@hf-edinburghcstr-20261023](../../catalog/ami_ihm.yaml#L1) | 95.5 | 已登记 | 没有 |

- `ami_ihm@hf-edinburghcstr-20261023`：AMI 会议语料的近讲耳麦（IHM）版本：英文 16 kHz 单声道，按 Kaldi AMI s5 切句、文本大写归一化，带会议、说话人和耳麦编号。train / dev / test 分别 108502、13098、12643 句，共 95.5 小时，会议划分与 Kaldi full-corpus-ASR 一致。本机已有 AMI 单远场麦克风版 `ami_sdm`，可与这份近讲版对照近场和远场

### audioset_esc_test

AudioSet 背景声场景描述评测集

语言：en · 任务：背景声场景描述

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [audioset_esc_test@eval-20260804](../../catalog/open_audio_eval.yaml#L1404) | 6.8 | 已登记 | 快照 20260914 |

- 当前仅登记评测入口

### chime4

四种噪声环境的英文朗读评测集（CHiME-4）

语言：en · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [chime4@hf-prummn-20261023](../../catalog/chime4.yaml#L1) | 10.1 | 已登记 | 没有 |
| [chime4@isolated-1ch-20261026](../../catalog/chime4.yaml#L160) | 4.9 | 已登记 | 没有 |

- `chime4@hf-prummn-20261023`：CHiME-4 评测数据：WSJ0 句子在公交（BUS）、咖啡馆（CAF）、步行街（PED）、街道（STR）四种噪声环境下用 6 麦平板录制（real）或模拟（simu），英文 16 kHz 单声道 16 bit。这里有 dev（dt05）和 eval（et05）的 1 通道、2 通道 track 音频与全部转写，共 5920 条、10.09 小时，每组 4 个说话人；常用 1 通道 track 的 et05_real 报 WER。没有训练音频（tr05）、6 通道 track、背景噪声和 embedded 连续录音，这些属于完整 CHiME-3（LDC2017S24），公开渠道拿不到，只能评测
- `chime4@isolated-1ch-20261026`：CHiME-4 真实录音 1 通道 track 的评测清单：dev（dt05_real，1,640 条）和 eval（et05_real，1,320 条），公交 / 咖啡馆 / 步行街 / 街道四种环境，每组 4 个说话人，英文 16 kHz。音频是 hf-prummn-20261023 解包目录里的 isolated_1ch_track 原文件（不复制），参考文本取每条的 .trn（挑战赛官方规范化文本：大写，缩写拼成 N. E. C.）。只能评测：训练音频 tr05 属于完整 CHiME-3（LDC），公开渠道没有；常用 et05_real 报单通道 WER

### chime6

家庭聚会英文对话，多通道远场重叠（CHiME-6）

语言：en · 任务：语音识别、重叠语音检测、带说话人标注的语音识别、说话人分段与归属、目标说话人语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [chime6@meeting-windows-v1-20261008](../../catalog/diarization_raw_real-meetings.yaml#L2) | — | 未登记 | 没有 |
| [chime6@openslr-150-source-20260911](../../catalog/chime6.yaml#L1) | — | 未登记 | 快照 20260914 |
| [chime6@speaker-records-v1-20260912](../../catalog/chime6.yaml#L150) | 56.3 | 已登记 | 快照 20260914 |
| [chime6@turn-taking-20261014](../../catalog/amphionasr_v4.yaml#L1365) | 174.5 | 已登记 | 没有 |

- `chime6@meeting-windows-v1-20261008`：CHiME-6 真实会议的说话人归属 ASR 窗口（aligned_utterance_timestamps_v1）：人工标注的说话人和时间，mean of the 4 channels of array U01；转写为官方文字原样，只去空白，保留 [noise]、[laughs]、[inaudible] 标记。按 30 / 120 / 300 / 600 s 切窗，每个 split 的 records 一行一个窗口，turns 在 metadata。训练集上整窗目标超过上下文的 113 个窗口和空转写的 4 个窗口列在 train_excluded_windows（导出时已丢弃，不在 records 里）。标注更正 annotation_corrections：eval S21 第 1959 行开始晚于结束，强制对齐不可靠，整行排除，复核对齐结果在 test_correction_alignments。音频是 U01 阵列 4 路的平均（16 kHz 单声道），源数据集里没有，已按原字节复制 20 个文件到本版本 audio/ 下，由 *-audio-index 引用。没有清洗通过标记，也没有伪造。脚本 scripts/diarization_raw_labels/register_raw_labels.py
- `chime6@openslr-150-source-20260911`：家庭聚会中的多通道远场和重叠语音；包含音频、官方转写、房间布局和许可文件。 官方转写原包保留尾随字节问题；标注入口使用解压内容不变、通过 CRC 校验的修复归档
- `chime6@speaker-records-v1-20260912`：已解包、实测音频头并生成通用说话人记录；保留官方划分和标注
- `chime6@turn-taking-20261014`：会议 turn-taking。整句拼成 2/3 人混合窗，时长 0.5～30 秒。注册音是窗外另一句，1～30 秒。有近场时远场:近场 = 3:1

### common_voice_en

Common Voice 英语众包朗读；含清洗、热词、加噪版

语言：en · 任务：语音识别、热词增强语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [common_voice_en@hf-8262c16bf297](../../catalog/multilingual_asr_sources.yaml#L200) | 27.0 | 已登记 | 没有 |
| [common_voice_en@hotwords-v1-20261102](../../catalog/hotwords_v1_20261102.yaml#L184) | 469.7 | 已登记 | 没有 |
| [common_voice_en@icefall-20260908](../../catalog/icefall_runtime.yaml#L311) | 1,862.7 | 已登记 | 快照 20260914 |
| [common_voice_en@legacy-20260804](../../catalog/icefall_base.yaml#L263) | 1,862.7 | 已登记 | 快照 20260914 |
| [common_voice_en@punc-teacher-v1-20261102](../../catalog/punc_teacher_v1.yaml#L951) | 39.4 | 已登记 | 没有 |
| [common_voice_en@punc-written-en-v1-20261102](../../catalog/en_punc_written_v1.yaml#L122) | — | 未登记 | 没有 |
| [common_voice_en@train-punc-v1-20261102](../../catalog/train_punc_v1_more.yaml#L99) | — | 未登记 | 没有 |
| [commonvoice_en@eval-20260804](../../catalog/open_audio_eval.yaml#L280) | 27.2 | 已登记 | 快照 20260914 |
| [commonvoice_en_clean@clean-v1-20260805](../../catalog/local_lhotse_derived.yaml#L311) | 1,835.4 | 已登记 | 快照 20260914 |
| [commonvoice_en_hotwords@eval-20260804](../../catalog/open_audio_eval.yaml#L350) | 27.2 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/commonvoice_en_hotwords/` |
| [commonvoice_en_hotwords@hotwords-v1-20260805](../../catalog/local_lhotse_derived.yaml#L414) | 1,835.4 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/commonvoice_en_hotwords/` |
| [cv_en_noise_audioset_esc@eval-20260804](../../catalog/open_audio_eval.yaml#L1718) | 27.2 | 已登记 | 快照 20260914 |
| [cv_en_noise_audioset_esc_hotwords@eval-20260804](../../catalog/open_audio_eval.yaml#L2422) | 27.2 | 已登记 | 快照 20260914 |
| [cv_en_noise_audioset_traffic@eval-20260804](../../catalog/open_audio_eval.yaml#L1686) | 27.2 | 已登记 | 快照 20260914 |
| [cv_en_noise_audioset_traffic_hotwords@eval-20260804](../../catalog/open_audio_eval.yaml#L2390) | 27.2 | 已登记 | 快照 20260914 |
| [cv_en_noise_dns@eval-20260804](../../catalog/open_audio_eval.yaml#L1654) | 27.2 | 已登记 | 快照 20260914 |
| [cv_en_noise_dns_hotwords@eval-20260804](../../catalog/open_audio_eval.yaml#L2358) | 27.2 | 已登记 | 快照 20260914 |
| [cv_en_noise_musan_music@eval-20260804](../../catalog/open_audio_eval.yaml#L1590) | 27.2 | 已登记 | 快照 20260914 |
| [cv_en_noise_musan_music_hotwords@eval-20260804](../../catalog/open_audio_eval.yaml#L2294) | 27.2 | 已登记 | 快照 20260914 |
| [cv_en_noise_musan_noise@eval-20260804](../../catalog/open_audio_eval.yaml#L1558) | 27.2 | 已登记 | 快照 20260914 |
| [cv_en_noise_musan_noise_hotwords@eval-20260804](../../catalog/open_audio_eval.yaml#L2262) | 27.2 | 已登记 | 快照 20260914 |
| [cv_en_noise_musan_speech@eval-20260804](../../catalog/open_audio_eval.yaml#L1622) | 27.2 | 已登记 | 快照 20260914 |
| [cv_en_noise_musan_speech_hotwords@eval-20260804](../../catalog/open_audio_eval.yaml#L2326) | 27.2 | 已登记 | 快照 20260914 |
| [cv_en_noise_wham@eval-20260804](../../catalog/open_audio_eval.yaml#L1750) | 27.2 | 已登记 | 快照 20260914 |
| [cv_en_noise_wham_hotwords@eval-20260804](../../catalog/open_audio_eval.yaml#L2454) | 27.2 | 已登记 | 快照 20260914 |
| [cv_en_rir_rirmega@eval-20260804](../../catalog/open_audio_eval.yaml#L1526) | 27.2 | 已登记 | 快照 20260914 |
| [cv_en_rir_rirmega_hotwords@eval-20260804](../../catalog/open_audio_eval.yaml#L2230) | 27.2 | 已登记 | 快照 20260914 |
| [cv_en_rir_slr26@eval-20260804](../../catalog/open_audio_eval.yaml#L1430) | 27.2 | 已登记 | 快照 20260914 |
| [cv_en_rir_slr26_hotwords@eval-20260804](../../catalog/open_audio_eval.yaml#L2134) | 27.2 | 已登记 | 快照 20260914 |
| [cv_en_rir_slr28_real@eval-20260804](../../catalog/open_audio_eval.yaml#L1494) | 27.2 | 已登记 | 快照 20260914 |
| [cv_en_rir_slr28_real_hotwords@eval-20260804](../../catalog/open_audio_eval.yaml#L2198) | 27.2 | 已登记 | 快照 20260914 |
| [cv_en_rir_slr28_sim@eval-20260804](../../catalog/open_audio_eval.yaml#L1462) | 27.2 | 已登记 | 快照 20260914 |
| [cv_en_rir_slr28_sim_hotwords@eval-20260804](../../catalog/open_audio_eval.yaml#L2166) | 27.2 | 已登记 | 快照 20260914 |
| [common_voice_en@legacy-20260804](../../catalog/icefall_base.yaml#L263) | 1,854.0 | [参考表](https://ccnuebbmik1f.feishu.cn/wiki/CEXFwEjPoi2bIukVjk9c5FdOn12?sheet=3d4d23) | 快照 20260914 |

- `common_voice_en@hf-8262c16bf297`：Common Voice 17.0 en 的非官方 HF 镜像（官方 Mozilla 仓库需要授权），只下载了 test，与 common_voice_pt@hf-8262c16bf297 同一修订
- `common_voice_en@hotwords-v1-20261102`：common_voice_en@train-punc-v1-20261102 中被 TS 场景池（open-audio-llm 训练配方 train-data-v7set30）用作目标或干扰语音的句子，带热词标注：custom.hotwords 是这句里说到的热词，按本行文本的写法（英文按整词匹配、不分大小写，所有格算同一个词；本行文本里找不到的词去掉）；custom.hotword_labeling 记标注来源、标注时看到的文本和模型原始抽取。314807 句里 144126 句有热词，其中 137676 句复用 hw_sft@hw-20261014 的已有标注。只含标过的句子，文本与父版本相同；录音沿用父版本，不复制音频。脚本 scripts/ts_hotwords/register_hotwords.py，标注工具 scripts/ts_hotwords/label_hotwords.py
- `common_voice_en@punc-teacher-v1-20261102`：common_voice_en@legacy-20260804 的 train 监督片段里的 Qwen3.8-27B 老师给 25000 句加的英文标点（24624 句去掉标点后与输入一致，ok=true）：custom.punctuation_teacher 记输出 text、ok 和模型看到的无标点输入 input。这批句子用来微调 Qwen3-4B 学生，抽样见 amphiondata scripts/punctuation/build_teacher_set_en.py。只含这些句子，text 与父版本相同，不是标点后的文本；录音沿用父版本，不复制音频。中间产物，供复现和比较学生，不直接用于训练。脚本 scripts/punctuation/register_punc_intermediates.py
- `common_voice_en@punc-written-en-v1-20261102`：common_voice_en@legacy-20260804 训练集原标注加英文书面化标点并恢复大小写（规范 en-v1，amphiondata written_punctuation_en）：Qwen3.8-27B 给 10 万条加标点，蒸馏到 Qwen3-4B 学生（LoRA）跑全量，不带听音提示。只插 , . ? ! ; : 和改大小写，转小写去标点后与原标注逐词一致；模型改了词的条目退回原标注只加句号；代词 I 统一大写，首字母大写，每条以 . ? ! 结尾。文件与源 supervisions 条数、顺序相同，只换 text；导出后逐条回读核对
- `common_voice_en@train-punc-v1-20261102`：common_voice_en@legacy-20260804 的 train 训练版本，目标文本换成带标点的写法（按 id 取自 datasets/common_voice_en/versions/punc-written-en-v1-20261102/cv-en_supervisions_train_cleaned_punc_written.jsonl.gz；去掉标点和空格、转小写后与原文一致才替换，否则保留原文）。其余字段与源版本相同，录音引用源版本
- `commonvoice_en_clean@clean-v1-20260805`：Qwen3-ASR-1.7B + whisper-large-v3 双引擎筛选；train 需过滤 1,127 条失败记录；test 清单尚未应用筛选结果
- 含派生版本（与源数据可能重叠）

### cs_dialogue_en

CS-Dialogue 对话中的纯英文语句

语言：en · 任务：语音识别、热词增强语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [cs_dialogue_en@hotwords-v1-20261102](../../catalog/hotwords_v1_20261102.yaml#L329) | 4.5 | 已登记 | 没有 |
| [cs_dialogue_en@icefall-20260908](../../catalog/icefall_runtime.yaml#L2106) | 26.6 | 已登记 | 快照 20260914 |
| [cs_dialogue_en@legacy-20260804](../../catalog/icefall_base.yaml#L1702) | 26.6 | 已登记 | 快照 20260914 |

- `cs_dialogue_en@hotwords-v1-20261102`：cs_dialogue_en@legacy-20260804 中被 TS 场景池（open-audio-llm 训练配方 train-data-v7set30）用作目标或干扰语音的句子，带热词标注：custom.hotwords 是这句里说到的热词，按本行文本的写法（英文按整词匹配、不分大小写，所有格算同一个词；本行文本里找不到的词去掉）；custom.hotword_labeling 记标注来源、标注时看到的文本和模型原始抽取。4330 句里 260 句有热词。只含标过的句子，文本与父版本相同；录音沿用父版本，不复制音频。脚本 scripts/ts_hotwords/register_hotwords.py，标注工具 scripts/ts_hotwords/label_hotwords.py
- 含派生版本（与源数据可能重叠）

### dipco

家庭晚宴英文对话，近讲与远场阵列（DiPCo）

语言：en · 任务：语音识别、带说话人标注的语音识别、说话人分段与归属

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [dipco@modelscope-benjamin-paine-20261023](../../catalog/dipco.yaml#L1) | 6.5 | 已登记 | 没有 |
| [dipco@zenodo-8122551-20261023](../../catalog/dipco.yaml#L82) | 5.3 | 已登记 | 没有 |

- `dipco@modelscope-benjamin-paine-20261023`：DiPCo 晚宴语料：每场 4 人在家庭餐桌边自然聊天，英文 16 kHz。每人一个近讲麦克风，另有 5 台 7 麦阵列设备（U01–U05）放在房间不同位置。dev、eval 各 5 场、16 个说话人，共 7078 句、6.5 小时语音。这一版按句切好：split-channel 每句存近讲 + 35 个远场通道（25.5 万行），mixed-channel 把每台设备 7 个通道取平均（4.2 万行）；每行带 会话、说话人、设备、通道、离设备距离、性别、母语和转写。parquet 的 train/test 就是官方 dev/eval，没有训练集。有重叠语音，远场通道互相之间也有重复，统计时长时只算一遍
- `dipco@zenodo-8122551-20261023`：DiPCo 晚宴语料官方完整整场版：10 场，每场 4 个近讲麦克风 + 5 台设备 × 7 个通道 = 39 个单声道 16 kHz WAV，共 390 个文件，加官方 JSON 转写（每句带说话人、性别、母语、近讲和各设备上的起止时间）。dev、eval 各 5 场、16 个说话人，共 7078 句，会话总长 5.3 小时。用于长音频的说话人日志和多人 ASR；按句评测用已切好的 `dipco@modelscope-benjamin-paine-20261023`

### emilia_en

Emilia 英语野外语音（已清洗）

语言：en · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [emilia_en@legacy](../../catalog/legacy_multilingual.yaml#L911) | 43,624.0 | 已登记 | 快照 20260914 |

- `emilia_en@legacy`：参考表注明 clean2604，Whisper + Qwen3ASR 转录、已有清洗；本次未复核实际样本
- 有含标点版本

### emotion1200_en

英文情感识别与描述评测（Emotion1200）

语言：en · 任务：说话人情感分类、情感与说话风格描述、语音情感识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [emotion1200_en_sec@eval-20260804](../../catalog/open_audio_eval.yaml#L1036) | 5.2 | 已登记 | 快照 20260914 |
| [emotion1200_en_sepc@eval-20260804](../../catalog/open_audio_eval.yaml#L1102) | 5.2 | 已登记 | 快照 20260914 |
| [emotion1200_en_ser@eval-20260804](../../catalog/open_audio_eval.yaml#L972) | 5.2 | 已登记 | 快照 20260914 |

- 当前仅登记评测入口

### fleurs_en

多语朗读英语部分（FLEURS）

语言：en · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [fleurs_en@hf-70bb2e84b976](../../catalog/multilingual_asr_sources.yaml#L137) | 1.8 | 已登记 | 没有 |
| [fleurs_en@legacy](../../catalog/legacy_multilingual.yaml#L841) | 10.3 | 已登记 | 快照 20260914 |

- `fleurs_en@hf-70bb2e84b976`：Google FLEURS 的 en_us 子集（音频归档和 TSV 转写），只下载了 test，与 fleurs_pt 同一修订
- 有含标点版本

### gigaspeech

有声书、播客和 YouTube 英语（GigaSpeech）

语言：en · 任务：语音识别、diarization、带说话人标注的语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [gigaspeech@eval-20260804](../../catalog/open_audio_eval.yaml#L218) | 40.3 | 已登记 | 快照 20260914 |
| [gigaspeech@icefall-20260908](../../catalog/icefall_runtime.yaml#L229) | 10,050.7 | 已登记 | 快照 20260914 |
| [gigaspeech@legacy-20260804](../../catalog/icefall_base.yaml#L190) | 10,050.7 | 已登记 | 快照 20260914 |
| [gigaspeech@punc-teacher-v1-20261102](../../catalog/punc_teacher_v1.yaml#L895) | 54.7 | 已登记 | 没有 |
| [gigaspeech@punc-written-en-v1-20261102](../../catalog/en_punc_written_v1.yaml#L72) | — | 未登记 | 没有 |
| [gigaspeech@train-punc-v1-20261102](../../catalog/train_punc_v1_more.yaml#L160) | — | 未登记 | 没有 |
| [gigaspeech@youtube-diarize-census-v1-20261009](../../catalog/diarization_raw_gigaspeech-census.yaml#L2) | — | 未登记 | 没有 |
| [gigaspeech@legacy-20260804](../../catalog/icefall_base.yaml#L190) | 10,000.0 | [参考表](https://ccnuebbmik1f.feishu.cn/wiki/CEXFwEjPoi2bIukVjk9c5FdOn12?sheet=3d4d23) | 快照 20260914 |

- `gigaspeech@punc-teacher-v1-20261102`：gigaspeech@legacy-20260804 的 train 监督片段里的 Qwen3.8-27B 老师给 45000 句加的英文标点（44168 句去掉标点后与输入一致，ok=true）：custom.punctuation_teacher 记输出 text、ok 和模型看到的无标点输入 input。这批句子用来微调 Qwen3-4B 学生，抽样见 amphiondata scripts/punctuation/build_teacher_set_en.py。只含这些句子，text 与父版本相同，不是标点后的文本；录音沿用父版本，不复制音频。中间产物，供复现和比较学生，不直接用于训练。脚本 scripts/punctuation/register_punc_intermediates.py
- `gigaspeech@punc-written-en-v1-20261102`：gigaspeech@legacy-20260804 训练集原标注加英文书面化标点并恢复大小写（规范 en-v1，amphiondata written_punctuation_en）：Qwen3.8-27B 给 10 万条加标点，蒸馏到 Qwen3-4B 学生（LoRA）跑全量，不带听音提示。只插 , . ? ! ; : 和改大小写，转小写去标点后与原标注逐词一致；模型改了词的条目退回原标注只加句号；代词 I 统一大写，首字母大写，每条以 . ? ! 结尾。文件与源 supervisions 条数、顺序相同，只换 text；导出后逐条回读核对
- `gigaspeech@train-punc-v1-20261102`：gigaspeech@legacy-20260804 的 train 训练版本，目标文本换成带标点的写法（按 id 取自 datasets/gigaspeech/versions/punc-written-en-v1-20261102/gigaspeech_supervisions_XL_punc_written.jsonl.gz；去掉标点和空格、转小写后与原文一致才替换，否则保留原文）。其余字段与源版本相同，录音引用源版本
- `gigaspeech@youtube-diarize-census-v1-20261009`：GigaSpeech XL 全部 YouTube 录音（YOU*，21,472 条 / 11,765.9 h）的说话人数普查，只做了一小部分，占位登记，不要用于训练。2026-10-09 用本机 MOSS-Transcribe-Diarize 0.9B 整条打说话人和文本，完成 1082 条成功（共 1087 行，含失败待重试），约占计划 5%；Qwen3-ASR 文本校验只做了 36 条。用户决定先做中文，英文暂缓，没有继续。local_moss_records：每行一条录音，target 是按时间排序的 [说话人][起-止] 文本，metadata.local_moss 保留教师返回的分块、说话人链接、身份断点和 speaker_census（三种说话人数：global_labels 偏高、global_active、max_chunk_active）。qwen3_asr_en_records：Qwen3-ASR 对 MOSS 片段的转写（metadata.qwen3_asr_en）。audio_slots 指向本版本 youtube_xl_recordings 里的同名录音。脚本 scripts/diarization_raw_labels/register_raw_labels.py
- 含派生版本（与源数据可能重叠）

### hifitts

英文有声书高保真朗读（Hi-Fi TTS）

语言：en · 任务：语音识别、语音合成

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [hifitts@tts-unified-v0.1](../../catalog/tts_unified.yaml#L477) | 291.7 | 已登记 | `amphion-tts-data-1373259071:HiFiTTS/`（原始数据） |

- `hifitts@tts-unified-v0.1`：音频编码字节存放在 Lance 表内；原始划分在 metadata_json.original_split，统一输出全部为 train。ASR 用 tts_lance.iter_asr_samples（tts-asr-rules/v1）读取，会排除原始 dev/test 等

### hifitts2

英文有声书高保真朗读（Hi-Fi TTS 2）

语言：en · 任务：语音识别、语音合成

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [hifitts2@tts-unified-v0.1](../../catalog/tts_unified.yaml#L521) | 35,932.7 | 已登记 | 没有 |

- `hifitts2@tts-unified-v0.1`：音频编码字节存放在 Lance 表内；原始划分在 metadata_json.original_split，统一输出全部为 train。ASR 用 tts_lance.iter_asr_samples（tts-asr-rules/v1）读取，会排除原始 dev/test 等

### icsi

伯克利 ICSI 英文工作会议（近讲混合音轨）

语言：en · 任务：语音识别、说话人分段与归属

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [icsi@modelscope-argmaxinc-20261025](../../catalog/icsi.yaml#L1) | 71.7 | 已登记 | 没有 |

- `icsi@modelscope-argmaxinc-20261025`：ICSI 会议语料：伯克利 ICSI 研究所 2000–2002 年录的 75 场真实英文工作会议（每场 3–10 人，共 53 位登记说话人），71.7 小时。这一版的音频是官方的近讲混合音轨（把所有人的头戴麦叠成一路，16 kHz 单声道），每场带说话人分段（12.9 万段），适合做说话人日志评测；另附官方 MRT 原始转写（含时间、说话人）和 NXT 标注（词、分段、对话行为），可做多人会议 ASR。不含远场桌面麦通道

### iemocap_ser

英文双人表演对话情感识别评测（IEMOCAP）

语言：en · 任务：语音情感识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [iemocap_ser@eval-20260804](../../catalog/open_audio_eval.yaml#L895) | 1.5 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/iemocap_ser/` |

- 当前仅登记评测入口

### legco_speech_en

香港立法会会议英语

语言：en · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [legco_speech_en@icefall-20260908](../../catalog/icefall_runtime.yaml#L2296) | 249.6 | 已登记 | 快照 20260914 |
| [legco_speech_en@legacy-20260804](../../catalog/icefall_base.yaml#L1898) | 249.6 | 已登记 | 快照 20260914 |

- 含派生版本（与源数据可能重叠）

### libri2mix

LibriMix 两人混合的目标说话人评测

语言：en · 任务：目标说话人语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [libri2mix_lib@eval-20260804](../../catalog/open_audio_eval.yaml#L1246) | 8.4 | 已登记 | 快照 20260914 |
| [libri2mix_snrp10@eval-20260804](../../catalog/open_audio_eval.yaml#L1352) | 8.4 | 已登记 | 快照 20260914 |
| [libri2mix_snrp5@eval-20260804](../../catalog/open_audio_eval.yaml#L1300) | 8.4 | 已登记 | 快照 20260914 |
| [libri2mix_tsstyle@eval-20260804](../../catalog/open_audio_eval.yaml#L1166) | 11.2 | 已登记 | 快照 20260914 |

- 当前仅登记评测入口

### libri3mix

LibriMix 三人混合的目标说话人评测

语言：en · 任务：目标说话人语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [libri3mix_lib@eval-20260804](../../catalog/open_audio_eval.yaml#L1273) | 10.9 | 已登记 | 快照 20260914 |
| [libri3mix_snrp10@eval-20260804](../../catalog/open_audio_eval.yaml#L1378) | 10.9 | 已登记 | 快照 20260914 |
| [libri3mix_snrp5@eval-20260804](../../catalog/open_audio_eval.yaml#L1326) | 10.9 | 已登记 | 快照 20260914 |
| [libri3mix_tsstyle@eval-20260804](../../catalog/open_audio_eval.yaml#L1192) | 16.3 | 已登记 | 快照 20260914 |

- 当前仅登记评测入口

### libricss

LibriSpeech 外放录制的模拟会议

语言：en · 任务：语音识别、重叠语音检测、speech_separation

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [libricss@hf-uglyducking-20261023](../../catalog/libricss.yaml#L1) | 10.1 | 已登记 | 没有 |

- `libricss@hf-uglyducking-20261023`：LibriCSS：把 LibriSpeech test-clean 句子拼成约 10 分钟的“会议”，在办公室里用扬声器外放，7 麦圆形阵列录制，英文 16 kHz。6 种条件（无重叠长停顿 0L、无重叠短停顿 0S、重叠 10%–40% 的 OV10–OV40）各 10 个 session，共 60 段、10.1 小时、5023 句。每个 session 有 `record/raw_recording.wav`（7 通道录音）、`clean/` （外放源信号，`mix.wav` 单声道、`each_spk.wav` 8 通道）和 `transcription/meeting_info.txt`（起止时间、说话人、LibriSpeech 句子 ID、文本）。用于多人重叠 ASR 和语音分离评测；句子来自 LibriSpeech test-clean，不要和它一起当训练数据

### libriheavy

英文有声书，带标点和大小写（Libriheavy）

语言：en · 任务：语音识别、语音合成

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [libriheavy@tts-unified-v0.1](../../catalog/tts_unified.yaml#L562) | 51,044.7 | 已登记 | 没有 |

- `libriheavy@tts-unified-v0.1`：音频编码字节存放在 Lance 表内；原始划分在 metadata_json.original_split，统一输出全部为 train。ASR 用 tts_lance.iter_asr_samples（tts-asr-rules/v1）读取，会排除原始 dev/test 等

### librimix

LibriSpeech 混合的目标说话人数据

语言：en · 任务：目标说话人语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [librimix@960-current-audio-record-20260910](../../catalog/librimix.yaml#L156) | 6,921.9 | 已登记：按目标样本累计混合音频，非去重语料时长 | 快照 20260914 |
| [librimix@960-current-audio-record-20260910-punc-20261102](../../catalog/train_punc_v1_derived.yaml#L191) | — | 未登记 | 没有 |
| [librimix@960-current-source-20260910](../../catalog/librimix.yaml#L1) | — | 未登记 | 快照 20260914 |
| [librimix@960-legacy-audio-record-20260910](../../catalog/librimix.yaml#L483) | 6,865.5 | 已登记：按目标样本累计混合音频，非去重语料时长 | 快照 20260914 |
| [librimix@960-legacy-source-20260910](../../catalog/librimix.yaml#L440) | — | 未登记 | 快照 20260914 |

- `librimix@960-current-audio-record-20260910`：LibriMix_960 当前训练与测试（英文小写）；纯转写、独立 enrollment/mixture、空转写负样本
- `librimix@960-current-audio-record-20260910-punc-20261102`：librimix@960-current-audio-record-20260910 的 train_1spk, train_2spk, train_3spk, train_neg，目标文本加书面化标点：中文用 amphiondata 的中文学生模型（punc-student-v1，不带听音提示），英文用英文规范 en-v1 的学生模型（加标点并恢复大小写）；标点按字 / 按词搬回原文，原文的字词不变，找不到输出的目标保留原样。其余字段与源版本相同，音频引用源版本
- `librimix@960-current-source-20260910`：LibriMix_960 当前训练与测试（英文小写）；转换输入快照，时长见通用版本
- `librimix@960-legacy-audio-record-20260910`：LibriMix_960 历史训练入口（保留原英文大小写）；纯转写、独立 enrollment/mixture、空转写负样本
- `librimix@960-legacy-source-20260910`：LibriMix_960 历史训练入口（保留原英文大小写）；转换输入快照，时长见通用版本
- 含派生版本（与源数据可能重叠）

### librispeech

英文有声书朗读（LibriSpeech）；含热词和加噪版

语言：en · 任务：语音识别、热词增强语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [librispeech@eval-20260804](../../catalog/open_audio_eval.yaml#L574) | — | 未登记 | 快照 20260914 |
| [librispeech@hotwords-v1-20261102](../../catalog/hotwords_v1_20261102.yaml#L240) | 65.7 | 已登记 | 没有 |
| [librispeech@icefall-20260908](../../catalog/icefall_runtime.yaml#L1) | 971.6 | 已登记 | 快照 20260914 |
| [librispeech@legacy-20260804](../../catalog/icefall_base.yaml#L1) | 971.6 | 已登记 | 快照 20260914 |
| [librispeech@punc-teacher-v1-20261102](../../catalog/punc_teacher_v1.yaml#L1007) | 51.2 | 已登记 | 没有 |
| [librispeech@punc-written-en-v1-20261102](../../catalog/en_punc_written_v1.yaml#L2) | — | 未登记 | 没有 |
| [librispeech@train-punc-v1-20261102](../../catalog/train_punc_v1_more.yaml#L2) | — | 未登记 | 没有 |
| [librispeech_test_clean@eval-20260804](../../catalog/open_audio_eval.yaml#L665) | 5.4 | 已登记 | 快照 20260914 |
| [librispeech_test_clean_hotwords@eval-20260804](../../catalog/open_audio_eval.yaml#L510) | 5.4 | 已登记 | 快照 20260914 |
| [librispeech_test_other@eval-20260804](../../catalog/open_audio_eval.yaml#L697) | 5.3 | 已登记 | 快照 20260914 |
| [librispeech_test_other_hotwords@eval-20260804](../../catalog/open_audio_eval.yaml#L542) | 5.3 | 已登记 | 快照 20260914 |
| [librispeech_traffic_snr0@icefall-20260908](../../catalog/icefall_runtime.yaml#L3869) | — | 未登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/librispeech_traffic_snr0/` |
| [librispeech_traffic_snr0@recipe-1](../../catalog/icefall_traffic_derived.yaml#L1) | 10.7 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/librispeech_traffic_snr0/` |
| [librispeech_traffic_snr10@icefall-20260908](../../catalog/icefall_runtime.yaml#L4077) | — | 未登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/librispeech_traffic_snr10/` |
| [librispeech_traffic_snr10@recipe-1](../../catalog/icefall_traffic_derived.yaml#L253) | 10.7 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/librispeech_traffic_snr10/` |
| [librispeech_traffic_snr15@icefall-20260908](../../catalog/icefall_runtime.yaml#L4181) | — | 未登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/librispeech_traffic_snr15/` |
| [librispeech_traffic_snr15@recipe-1](../../catalog/icefall_traffic_derived.yaml#L379) | 10.7 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/librispeech_traffic_snr15/` |
| [librispeech_traffic_snr20@icefall-20260908](../../catalog/icefall_runtime.yaml#L4285) | — | 未登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/librispeech_traffic_snr20/` |
| [librispeech_traffic_snr20@recipe-1](../../catalog/icefall_traffic_derived.yaml#L505) | 10.7 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/librispeech_traffic_snr20/` |
| [librispeech_traffic_snr5@icefall-20260908](../../catalog/icefall_runtime.yaml#L3973) | — | 未登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/librispeech_traffic_snr5/` |
| [librispeech_traffic_snr5@recipe-1](../../catalog/icefall_traffic_derived.yaml#L127) | 10.7 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/librispeech_traffic_snr5/` |
| [librispeech@legacy-20260804](../../catalog/icefall_base.yaml#L1) | 960.0 | [参考表](https://ccnuebbmik1f.feishu.cn/wiki/CEXFwEjPoi2bIukVjk9c5FdOn12?sheet=3d4d23) | 快照 20260914 |

- `librispeech@hotwords-v1-20261102`：librispeech@train-punc-v1-20261102 中被 TS 场景池（open-audio-llm 训练配方 train-data-v7set30）用作目标或干扰语音的句子，带热词标注：custom.hotwords 是这句里说到的热词，按本行文本的写法（英文按整词匹配、不分大小写，所有格算同一个词；本行文本里找不到的词去掉）；custom.hotword_labeling 记标注来源、标注时看到的文本和模型原始抽取。47421 句里 13808 句有热词。只含标过的句子，文本与父版本相同；录音沿用父版本，不复制音频。脚本 scripts/ts_hotwords/register_hotwords.py，标注工具 scripts/ts_hotwords/label_hotwords.py
- `librispeech@punc-teacher-v1-20261102`：librispeech@legacy-20260804 的 train 监督片段里的 Qwen3.8-27B 老师给 15000 句加的英文标点（14436 句去掉标点后与输入一致，ok=true）：custom.punctuation_teacher 记输出 text、ok 和模型看到的无标点输入 input。这批句子用来微调 Qwen3-4B 学生，抽样见 amphiondata scripts/punctuation/build_teacher_set_en.py。只含这些句子，text 与父版本相同，不是标点后的文本；录音沿用父版本，不复制音频。中间产物，供复现和比较学生，不直接用于训练。脚本 scripts/punctuation/register_punc_intermediates.py
- `librispeech@punc-written-en-v1-20261102`：librispeech@legacy-20260804 训练集原标注加英文书面化标点并恢复大小写（规范 en-v1，amphiondata written_punctuation_en）：Qwen3.8-27B 给 10 万条加标点，蒸馏到 Qwen3-4B 学生（LoRA）跑全量，不带听音提示。只插 , . ? ! ; : 和改大小写，转小写去标点后与原标注逐词一致；模型改了词的条目退回原标注只加句号；代词 I 统一大写，首字母大写，每条以 . ? ! 结尾。文件与源 supervisions 条数、顺序相同，只换 text；导出后逐条回读核对
- `librispeech@train-punc-v1-20261102`：librispeech@legacy-20260804 的 train 训练版本，目标文本换成带标点的写法（按 id 取自 datasets/librispeech/versions/punc-written-en-v1-20261102/librispeech_supervisions_train-clean-100_punc_written.jsonl.gz, datasets/librispeech/versions/punc-written-en-v1-20261102/librispeech_supervisions_train-clean-360_punc_written.jsonl.gz, datasets/librispeech/versions/punc-written-en-v1-20261102/librispeech_supervisions_train-other-500_punc_written.jsonl.gz；去掉标点和空格、转小写后与原文一致才替换，否则保留原文）。其余字段与源版本相同，录音引用源版本
- 含派生版本（与源数据可能重叠）

### libritts_r

英文有声书 TTS 语料，音频经修复（LibriTTS-R）

语言：en · 任务：语音识别、语音合成

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [libritts_r@tts-unified-v0.1](../../catalog/tts_unified.yaml#L603) | 583.1 | 已登记 | `amphion-tts-data-1373259071:LibriTTS-R/`（原始数据） |

- `libritts_r@tts-unified-v0.1`：音频编码字节存放在 Lance 表内；原始划分在 metadata_json.original_split，统一输出全部为 train。ASR 用 tts_lance.iter_asr_samples（tts-asr-rules/v1）读取，会排除原始 dev/test 等

### ljspeech

单人英文朗读（LJSpeech）

语言：en · 任务：语音识别、语音合成

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [ljspeech@tts-unified-v0.1](../../catalog/tts_unified.yaml#L647) | 23.9 | 已登记 | `amphion-tts-data-1373259071:LJSpeech/`（原始数据） |

- `ljspeech@tts-unified-v0.1`：音频编码字节存放在 Lance 表内；原始划分在 metadata_json.original_split，统一输出全部为 train。ASR 用 tts_lance.iter_asr_samples（tts-asr-rules/v1）读取，会排除原始 dev/test 等

### meld_ser

美剧《老友记》对话情感识别评测（MELD）

语言：en · 任务：语音情感识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [meld_ser@eval-20260804](../../catalog/open_audio_eval.yaml#L863) | 2.3 | 已登记 | 快照 20260914 |

- 当前仅登记评测入口

### mls

英文有声书朗读（MLS 英语）

语言：en · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [mls@eval-20260804](../../catalog/open_audio_eval.yaml#L249) | 15.5 | 已登记 | 快照 20260914 |
| [mls@icefall-20260908](../../catalog/icefall_runtime.yaml#L147) | 44,691.0 | 已登记 | 快照 20260914 |
| [mls@legacy-20260804](../../catalog/icefall_base.yaml#L117) | 44,691.0 | 已登记 | 快照 20260914 |
| [mls@punc-written-en-v1-20261109](../../catalog/punc_written_mls_emilia.yaml#L2) | — | 未登记 | 没有 |
| [mls@legacy-20260804](../../catalog/icefall_base.yaml#L117) | 44,500.0 | [参考表](https://ccnuebbmik1f.feishu.cn/wiki/CEXFwEjPoi2bIukVjk9c5FdOn12?sheet=3d4d23) | 快照 20260914 |

- `mls@punc-written-en-v1-20261109`：mls@legacy-20260804 训练集原标注（全小写、无标点）加英文书面化标点并恢复大小写（规范 en-v1，amphiondata written_punctuation_en）， 学生 student-en-v1（与 punc-written-en-v1-20261102 同一模型）跑全量，不带听音提示。只插 , . ? ! ; : 和改大小写，转小写去标点后与原标注逐词一致。 只在连字符和空格上不同的输出（约 3.7%，如 story-hour 写成 story hour）把标点和大小写搬回原标注，原标注的词和连字符不变； 模型改了词的条目（约 1.7%，多为原标注粘词或 OCR 错字）退回原标注只加句号。代词 I 统一大写，首字母大写，每条以 . ? ! 结尾。 文件与源 supervisions 条数、顺序相同，只换 text；导出后逐条回读核对，0 个问题
- 含派生版本（与源数据可能重叠）

### msp_podcast_ser

英文播客情感识别评测（MSP-Podcast）

语言：en · 任务：语音情感识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [msp_podcast_ser@eval-20260804](../../catalog/open_audio_eval.yaml#L927) | — | 未登记 | 快照 20260914 |

- 当前仅登记评测入口

### notsofar

微软英文远场会议，真实录制与模拟（NOTSOFAR）

语言：en · 任务：语音识别、连续语音分离、diarization、重叠语音检测、带说话人标注的语音识别、说话人分段与归属

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [notsofar@hf-ba8fd0f034ce-recorded-240825.1](../../catalog/multilingual_multispeaker.yaml#L358) | — | 未登记 | 快照 20260914 |
| [notsofar@hf-ba8fd0f034ce-sim-v1.5-200h](../../catalog/multilingual_multispeaker.yaml#L419) | 200.0 | 估算 | 快照 20260914 |
| [notsofar_sdm@icefall-20260908](../../catalog/icefall_runtime.yaml#L2995) | 176.9 | 已登记：单远场麦克风标注片段 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/notsofar_sdm/` |
| [notsofar_sdm@meeting-windows-v1-20261008](../../catalog/diarization_raw_real-meetings.yaml#L288) | — | 未登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/notsofar_sdm/` |
| [notsofar_sdm@teacher-calibration-v1-20261009](../../catalog/diarization_raw_teacher-calibration.yaml#L193) | — | 未登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/notsofar_sdm/` |

- `notsofar_sdm@icefall-20260908`：标注片段时长，重叠语音或多麦克风可能重复计时
- `notsofar_sdm@meeting-windows-v1-20261008`：NOTSOFAR-1 真实会议（单通道 SC 设备 ch0，每个设备算一条录音，因为设备间采样不同步）的说话人归属 ASR 窗口（aligned_utterance_timestamps_v1）：人工标注的说话人和时间，转写为源清单文字，只去空白。按 30 / 120 / 300 / 600 s 切窗，每个 split 的 records 一行一个窗口，turns 在 metadata；train / dev / test 都有。音频由 audio-index 指向源数据集里的 ch0.wav，不复制。没有窗口被排除。脚本 scripts/diarization_raw_labels/register_raw_labels.py
- `notsofar_sdm@teacher-calibration-v1-20261009`：说话人日志老师校准（2026-10-09）：在有人工标注的 NOTSOFAR train 单通道 ch0 39 场 / 4.02 h 上比较本机 MOSS 0.9B、MOSS Pro、百炼 qwen-audio-3.1-asr-flash 三个老师，并用 Qwen3-ASR 对本机 MOSS 的每个片段做文本校验；付费调用经用户批准，仅用于这次校准。每个 *_records 文件一个老师，每行一条录音，target 是按时间排序的 [说话人][起-止] 文本，教师返回的分块、说话人链接、身份断点留在 metadata.<老师>；teacher_agreement_records 每行一个人工标注片段，metadata.teacher_agreement 记各老师的说话人、边界和字错误率（analysis/segments.jsonl，用于确定多老师一致性过滤门槛）。NOTSOFAR 的 qwen3_asr_records 是第一版，误用 to_language=zh 把英文部分译成中文，已被 qwen3_asr_en_records 更正，保留原始输出。录音沿用 notsofar_sdm@icefall-20260908 train_rec_0（只用其中被抽中的录音），不复制音频。脚本 scripts/diarization_raw_labels/register_raw_labels.py

### singapore_english

新加坡口音英语（Hugging Face 来源）

语言：en · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [singapore_english@icefall-20260908](../../catalog/icefall_runtime.yaml#L429) | 3.9 | 已登记 | 快照 20260914 |
| [singapore_english@legacy-20260804](../../catalog/icefall_base.yaml#L375) | 3.9 | 已登记 | 快照 20260914 |
| [singapore_english@legacy-20260804](../../catalog/icefall_base.yaml#L375) | 2.0 | [参考表](https://ccnuebbmik1f.feishu.cn/wiki/CEXFwEjPoi2bIukVjk9c5FdOn12?sheet=3d4d23) | 快照 20260914 |

- `singapore_english@legacy-20260804`：新加坡英语；登记 cleaned 标注，尚未核实清洗引擎和规则
- 含派生版本（与源数据可能重叠）

### singaporean

新加坡口音英语小样本

语言：en · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [singaporean@icefall-20260908](../../catalog/icefall_runtime.yaml#L393) | 0.1 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/singaporean/` |
| [singaporean@legacy-20260804](../../catalog/icefall_base.yaml#L335) | 0.1 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/singaporean/` |
| [singaporean@legacy-20260804](../../catalog/icefall_base.yaml#L335) | 0.2 | [参考表](https://ccnuebbmik1f.feishu.cn/wiki/CEXFwEjPoi2bIukVjk9c5FdOn12?sheet=3d4d23) | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/singaporean/` |

- `singaporean@legacy-20260804`：新加坡英语；登记 cleaned 标注，尚未核实清洗引擎和规则
- 含派生版本（与源数据可能重叠）

### tal100_en

TAL 英语语音识别数据

语言：en · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [tal100_en@icefall-20260908](../../catalog/icefall_runtime.yaml#L488) | 4.8 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/tal100_en/` |
| [tal100_en@legacy-20260804](../../catalog/icefall_base.yaml#L432) | 4.8 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/tal100_en/` |

- 含派生版本（与源数据可能重叠）

### vctk

多口音英语朗读（VCTK）

语言：en · 任务：语音识别、语音合成

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [vctk@tts-unified-v0.1](../../catalog/tts_unified.yaml#L809) | 82.7 | 已登记 | `amphion-tts-data-1373259071:VCTK/`（原始数据） |

- `vctk@tts-unified-v0.1`：音频编码字节存放在 Lance 表内；原始划分在 metadata_json.original_split，统一输出全部为 train。ASR 用 tts_lance.iter_asr_samples（tts-asr-rules/v1）读取，会排除原始 dev/test 等

### voicebank_demand

语音增强标准集（VoiceBank-DEMAND）

语言：en · 任务：speech_enhancement

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [voicebank_demand@hf-jacoblincool-16k-20261023](../../catalog/voicebank_demand.yaml#L1) | 10.0 | 已登记 | 没有 |

- `voicebank_demand@hf-jacoblincool-16k-20261023`：VoiceBank-DEMAND 语音增强标准集：VCTK 朗读句子加 DEMAND 等噪声，每条有带噪和干净两份等长音频，英文。原始 48 kHz，这份镜像降到 16 kHz。train 28 个说话人 11572 对 9.4 小时，test 2 个说话人 824 对 0.6 小时。只有音频 ID，没有转写；用于增强、去噪评测（PESQ、STOI 等），不用于 ASR

### voices

真实房间外放的英文远场评测（VOiCES）

语言：en · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [voices@hf-prummn-20261023](../../catalog/voices.yaml#L1) | 27.9 | 已登记 | 没有 |

- `voices@hf-prummn-20261023`：VOiCES 远场评测子集：LibriSpeech 句子在 4 个真实房间里用扬声器外放、同时放干扰声（多人 babble、音乐、电视或无干扰），由近处（mc01）和远处（mc05）麦克风录下，英文 16 kHz 单声道。共 6400 条、27.9 小时、100 个说话人，每个“房间 × 干扰 × 麦克风”组合 200 条，带小写转写（metadata 的 answer 字段）。只是 devkit 测试集的抽样，不是全量。 句子来自 LibriSpeech，不要和 LibriSpeech 一起当训练数据

## 中文及粤语数据

### 3dspeaker

跨设备、距离和方言的中文声纹数据（3D-Speaker）

语言：zh · 任务：说话人身份识别、声纹验证

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [3dspeaker@official-source-20260911](../../catalog/3dspeaker.yaml#L1) | — | 未登记 | 快照 20260914 |
| [3dspeaker@speaker-records-v1-20260912](../../catalog/3dspeaker.yaml#L121) | 1,275.3 | 已登记 | 快照 20260914 |

- `3dspeaker@official-source-20260911`：跨设备、距离和方言声纹数据；包含三个官方验证配对清单，转写只覆盖普通话
- `3dspeaker@speaker-records-v1-20260912`：已解包、实测音频头并生成通用说话人记录；保留官方划分和标注

### OpenSLR 159 AISHELL-5

车内多人中文对话，远场麦克风（AISHELL-5）

语言：zh · 任务：语音识别、带说话人标注的语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [aishell5@far-mic-v1-20261010](../../catalog/zh_dialogue.yaml#L350) | 445.4 | 已登记 | 没有 |

- 含派生版本（与源数据可能重叠）

### aidatatang

中文手机朗读（aidatatang）；含清洗和热词版

语言：zh · 任务：语音识别、热词增强语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [aidatatang@alignment-v1-20261008](../../catalog/zh_source_alignment.yaml#L2) | 145.5 | 已登记 | 没有 |
| [aidatatang@clean-dual-qwen-moss-v1-20261008](../../catalog/zh_source_clean.yaml#L329) | 145.3 | 已登记 | 没有 |
| [aidatatang@icefall-20260908](../../catalog/icefall_runtime.yaml#L1613) | 145.5 | 已登记 | 快照 20260914 |
| [aidatatang@legacy-20260804](../../catalog/icefall_base.yaml#L1242) | 145.5 | 已登记 | 快照 20260914 |
| [aidatatang_hotwords@hotwords-v1-20260805](../../catalog/local_lhotse_derived.yaml#L932) | 145.5 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/aidatatang_hotwords/` |
| [aidatatang@legacy-20260804](../../catalog/icefall_base.yaml#L1242) | 140.0 | [参考表](https://ccnuebbmik1f.feishu.cn/wiki/CEXFwEjPoi2bIukVjk9c5FdOn12?sheet=3d4d23) | 快照 20260914 |

- `aidatatang@alignment-v1-20261008`：aidatatang@icefall-20260908 train 全部 237265 句的词级强制对齐（2026-10-08，Qwen3-ForcedAligner-0.6B，amphiondata main 6daabaf）。custom.alignment 含 status（aligned 171212 句 / needs_review 66053 句，后者有零时长或越界的词）、items（每个字或词的文本和起止秒，从该句开头算起）、issues、time_reference、unit、audio_duration。文本是对齐时所用的原标注文本；录音沿用 aidatatang@clean-dual-qwen-moss-v1-20261008 的 train 录音，不复制音频。脚本 scripts/label_registration/register_alignments.py
- `aidatatang@clean-dual-qwen-moss-v1-20261008`：aidatatang@icefall-20260908 的全部监督片段（上游称 train，实为含官方 dev/test 说话人的全量，故登记为 all），经 Qwen3-ASR-1.7B 与 MOSS-Transcribe-Diarize 双引擎一致性清洗；逐条写入 custom.clean（pass、reason、action、engine_status），不删除记录，读取时按 require_clean_pass 过滤。音频沿用源版本，不复制。规则 consensus-v6 / wenetspeech-faithful-v5：pass 236834、reject 431。少于 2 个字的 too_short 共 251 条按规则不经引擎直接 pass。用于合成时建议在 pass 之外再要求：两引擎均有效、MOSS 只输出 1 个说话人、action 不是 review_consensus；too_short 另要求两引擎规范化后与原文完全一致。按此筛选保留 220726 条、134.34 小时（too_short 通过 144/251）
- 含派生版本（与源数据可能重叠）

### aishell

中文朗读（AISHELL-1）；含清洗和热词版

语言：zh · 任务：语音识别、热词增强语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [aishell@eval-20260804](../../catalog/open_audio_eval.yaml#L1) | 10.0 | 已登记 | 快照 20260914 |
| [aishell@icefall-20260908](../../catalog/icefall_runtime.yaml#L1012) | 179.0 | 已登记 | 快照 20260914 |
| [aishell@legacy-20260804](../../catalog/icefall_base.yaml#L708) | 179.0 | 已登记 | 快照 20260914 |
| [aishell@punc-gold-v1-20261029](../../catalog/punc_teacher_v1.yaml#L730) | 0.0 | 已登记 | 没有 |
| [aishell@punc-teacher-v1-20261029](../../catalog/punc_teacher_v1.yaml#L381) | 3.7 | 已登记 | 没有 |
| [aishell@punc-written-v1-20261029](../../catalog/zh_punc_written_v1.yaml#L2) | 150.9 | 已登记 | 没有 |
| [aishell_clean@clean-v1-20260805](../../catalog/local_lhotse_derived.yaml#L605) | 10.0 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/aishell_clean/` |
| [aishell_hotwords@eval-20260804](../../catalog/open_audio_eval.yaml#L414) | 10.0 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/aishell_hotwords/` |
| [aishell_hotwords@hotwords-v1-20260805](../../catalog/local_lhotse_derived.yaml#L652) | 160.9 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/aishell_hotwords/` |
| [aishell@legacy-20260804](../../catalog/icefall_base.yaml#L708) | 155.0 | [参考表](https://ccnuebbmik1f.feishu.cn/wiki/CEXFwEjPoi2bIukVjk9c5FdOn12?sheet=3d4d23) | 快照 20260914 |

- `aishell@punc-gold-v1-20261029`：aishell@icefall-20260908 的 train 监督片段里的 普通话标点试点的 10 句手写参照标点（规范 v1，逗号从紧）：custom.punctuation_gold.text 是参照，custom.punctuation_hint 记试点用的 Qwen3-ASR 与 FireRedPunc 带标点转写。只含这些句子，text 与父版本相同，不是标点后的文本；录音沿用父版本，不复制音频。中间产物，供复现和比较学生，不直接用于训练。脚本 scripts/punctuation/register_punc_intermediates.py
- `aishell@punc-teacher-v1-20261029`：aishell@icefall-20260908 的 train 监督片段里的 Qwen3.8-27B 老师给 3000 句加的书面化标点（2988 句去掉标点后与输入一致，ok=true）：custom.punctuation_teacher 记输出 text、ok 和模型看到的无标点输入 input；custom.punctuation_hint.qwen 是提示用的 Qwen3-ASR 转写；其中 59 句是留出的评测句，另带学生 v1 的输出 custom.punctuation_student。这批句子用来微调 Qwen3-4B 学生，抽样见 amphiondata scripts/punctuation/build_teacher_set.py。只含这些句子，text 与父版本相同，不是标点后的文本；录音沿用父版本，不复制音频。中间产物，供复现和比较学生，不直接用于训练。脚本 scripts/punctuation/register_punc_intermediates.py
- `aishell@punc-written-v1-20261029`：aishell@icefall-20260908 训练集原标注加书面化标点（GB/T 15834，逗号从紧）：微调后的 Qwen3-4B（Qwen3.8-27B 的 9.6 万条输出蒸馏）以 Qwen3-ASR-1.7B 听音频得到的带标点转写作语气提示，只往原标注里插标点。模型改动了原文的条目，把模型输出的标点按字对齐搬回原标注；每条以 。？！ 结尾；原标注的字、空格（首尾除外）和大小写不变。没有汉字的条目（英文句子、拼读字母）和标注为空的条目原样保留。文件与源 supervisions 条数、顺序相同，只换 text。试点 200 条人工参照上：WenetSpeech markF1 92.4、其他来源 88.9（老师 93.2 / 88.2，原 FireRedPunc 79.8）
- 含派生版本（与源数据可能重叠）

### aishell2

中文朗读（AISHELL-2）；含清洗和热词版

语言：zh · 任务：语音识别、热词增强语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [aishell2@clean-dual-qwen-moss-v1-20261009](../../catalog/zh_source_clean_20261009.yaml#L2) | 998.2 | 已登记 | 没有 |
| [aishell2@eval-20260804](../../catalog/open_audio_eval.yaml#L32) | 4.0 | 已登记 | 快照 20260914 |
| [aishell2@hotwords-v1-20261102](../../catalog/hotwords_v1_20261102.yaml#L1) | 887.1 | 已登记 | 没有 |
| [aishell2@icefall-20260908](../../catalog/icefall_runtime.yaml#L1094) | 1,004.8 | 已登记 | 快照 20260914 |
| [aishell2@legacy-20260804](../../catalog/icefall_base.yaml#L781) | 1,004.8 | 已登记 | 快照 20260914 |
| [aishell2@punc-gold-v1-20261029](../../catalog/punc_teacher_v1.yaml#L675) | 0.0 | 已登记 | 没有 |
| [aishell2@punc-teacher-v1-20261029](../../catalog/punc_teacher_v1.yaml#L323) | 8.0 | 已登记 | 没有 |
| [aishell2@punc-written-v1-20261029](../../catalog/zh_punc_written_v1.yaml#L66) | 1,000.8 | 已登记 | 没有 |
| [aishell2@train-punc-v1-20261102](../../catalog/train_punc_v1.yaml#L3) | — | 未登记 | 没有 |
| [aishell2_clean@clean-v1-20260805](../../catalog/local_lhotse_derived.yaml#L723) | 4.0 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/aishell2_clean/` |
| [aishell2_hotwords@eval-20260804](../../catalog/open_audio_eval.yaml#L446) | 4.0 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/aishell2_hotwords/` |
| [aishell2_hotwords@hotwords-v1-20260805](../../catalog/local_lhotse_derived.yaml#L769) | 4.0 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/aishell2_hotwords/` |
| [aishell2@legacy-20260804](../../catalog/icefall_base.yaml#L781) | 1,036.0 | [参考表](https://ccnuebbmik1f.feishu.cn/wiki/CEXFwEjPoi2bIukVjk9c5FdOn12?sheet=3d4d23) | 快照 20260914 |

- `aishell2@clean-dual-qwen-moss-v1-20261009`：aishell2@icefall-20260908 的 train 监督片段，经 Qwen3-ASR-1.7B 与 MOSS-Transcribe-Diarize 双引擎一致性清洗（与 2026-10-08 的 primewords、aishell3、aidatatang、magicdata、magicdata_ramc 同一流程）；逐条写入 custom.clean（pass、reason、action、engine_status、两引擎各自和互相的 CER、MOSS 说话人段），不删除记录，读取时按 require_clean_pass 过滤。音频沿用源版本，不复制。规则 consensus-v6 / wenetspeech-faithful-v5：1009223 条中 pass 1006205、reject 3018。少于 2 个字的 too_short 共 48080 条按规则不经引擎直接 pass。restore_disfluency 改写了 27 条的 text（原文留在 custom.original_text）；无标点清单另把 123 条的标点和撇号去掉。引擎原始结果和复核清单在 evidence/。脚本 scripts/zh_source_clean/register_clean_dual.py
- `aishell2@hotwords-v1-20261102`：aishell2@train-punc-v1-20261102 中被 TS 场景池（open-audio-llm 训练配方 train-data-v7set30）用作目标或干扰语音的句子，带热词标注：custom.hotwords 是这句里说到的热词，按本行文本的写法（中文按子串匹配；本行文本里找不到的词去掉）；custom.hotword_labeling 记标注来源、标注时看到的文本和模型原始抽取。902095 句里 332131 句有热词。只含标过的句子，文本与父版本相同；录音沿用父版本，不复制音频。脚本 scripts/ts_hotwords/register_hotwords.py，标注工具 scripts/ts_hotwords/label_hotwords.py
- `aishell2@punc-gold-v1-20261029`：aishell2@icefall-20260908 的 train 监督片段里的 普通话标点试点的 20 句手写参照标点（规范 v1，逗号从紧）：custom.punctuation_gold.text 是参照，custom.punctuation_hint 记试点用的 Qwen3-ASR 与 FireRedPunc 带标点转写。只含这些句子，text 与父版本相同，不是标点后的文本；录音沿用父版本，不复制音频。中间产物，供复现和比较学生，不直接用于训练。脚本 scripts/punctuation/register_punc_intermediates.py
- `aishell2@punc-teacher-v1-20261029`：aishell2@icefall-20260908 的 train 监督片段里的 Qwen3.8-27B 老师给 8000 句加的书面化标点（7985 句去掉标点后与输入一致，ok=true）：custom.punctuation_teacher 记输出 text、ok 和模型看到的无标点输入 input；custom.punctuation_hint.qwen 是提示用的 Qwen3-ASR 转写；其中 142 句是留出的评测句，另带学生 v1 的输出 custom.punctuation_student。这批句子用来微调 Qwen3-4B 学生，抽样见 amphiondata scripts/punctuation/build_teacher_set.py。只含这些句子，text 与父版本相同，不是标点后的文本；录音沿用父版本，不复制音频。中间产物，供复现和比较学生，不直接用于训练。脚本 scripts/punctuation/register_punc_intermediates.py
- `aishell2@punc-written-v1-20261029`：aishell2@icefall-20260908 训练集原标注加书面化标点（GB/T 15834，逗号从紧）：微调后的 Qwen3-4B（Qwen3.8-27B 的 9.6 万条输出蒸馏）以 Qwen3-ASR-1.7B 听音频得到的带标点转写作语气提示，只往原标注里插标点。模型改动了原文的条目，把模型输出的标点按字对齐搬回原标注；每条以 。？！ 结尾；原标注的字、空格（首尾除外）和大小写不变。没有汉字的条目（英文句子、拼读字母）和标注为空的条目原样保留。文件与源 supervisions 条数、顺序相同，只换 text。试点 200 条人工参照上：WenetSpeech markF1 92.4、其他来源 88.9（老师 93.2 / 88.2，原 FireRedPunc 79.8）
- `aishell2@train-punc-v1-20261102`：aishell2@legacy-20260804 的 train 训练版本，目标文本换成带标点的写法（按 id 取自 datasets/aishell2/versions/punc-written-v1-20261029/aishell2_supervisions_train_punc_written.jsonl.gz；去掉标点和空格、转小写后与原文一致才替换，否则保留原文）。其余字段与源版本相同，录音引用源版本
- 含派生版本（与源数据可能重叠）

### aishell3

中文多人朗读（AISHELL-3）；含清洗、热词、TTS 版

语言：zh · 任务：语音识别、热词增强语音识别、语音合成

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [aishell3@alignment-v1-20261008](../../catalog/zh_source_alignment.yaml#L67) | 63.2 | 已登记 | 没有 |
| [aishell3@clean-dual-qwen-moss-v1-20261008](../../catalog/zh_source_clean.yaml#L167) | 63.1 | 已登记 | 没有 |
| [aishell3@eval-20260804](../../catalog/open_audio_eval.yaml#L63) | 22.4 | 已登记 | 快照 20260914 |
| [aishell3@icefall-20260908](../../catalog/icefall_runtime.yaml#L1147) | 85.6 | 已登记 | 快照 20260914 |
| [aishell3@legacy-20260804](../../catalog/icefall_base.yaml#L837) | 85.6 | 已登记 | 快照 20260914 |
| [aishell3@tts-unified-v0.1](../../catalog/tts_unified.yaml#L1) | 85.6 | 已登记 | `amphion-tts-data-1373259071:AISHELL-3/`（原始数据） |
| [aishell3_hotwords@eval-20260804](../../catalog/open_audio_eval.yaml#L478) | 22.4 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/aishell3_hotwords/` |
| [aishell3_hotwords@hotwords-v1-20260805](../../catalog/local_lhotse_derived.yaml#L815) | 85.6 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/aishell3_hotwords/` |
| [aishell3@legacy-20260804](../../catalog/icefall_base.yaml#L837) | 65.0 | [参考表](https://ccnuebbmik1f.feishu.cn/wiki/CEXFwEjPoi2bIukVjk9c5FdOn12?sheet=3d4d23) | 快照 20260914 |

- `aishell3@alignment-v1-20261008`：aishell3@icefall-20260908 train 全部 63262 句的词级强制对齐（2026-10-08，Qwen3-ForcedAligner-0.6B，amphiondata main 6daabaf）。custom.alignment 含 status（aligned 57990 句 / needs_review 5272 句，后者有零时长或越界的词）、items（每个字或词的文本和起止秒，从该句开头算起）、issues、time_reference、unit、audio_duration。文本是对齐时所用的原标注文本；录音沿用 aishell3@clean-dual-qwen-moss-v1-20261008 的 train 录音，不复制音频。脚本 scripts/label_registration/register_alignments.py
- `aishell3@clean-dual-qwen-moss-v1-20261008`：aishell3@icefall-20260908 的 train 监督片段，经 Qwen3-ASR-1.7B 与 MOSS-Transcribe-Diarize 双引擎一致性清洗；逐条写入 custom.clean（pass、reason、action、engine_status），不删除记录，读取时按 require_clean_pass 过滤。音频沿用源版本，不复制。规则 consensus-v6 / wenetspeech-faithful-v5：pass 63219、reject 43。少于 2 个字的 too_short 共 1982 条按规则不经引擎直接 pass。用于合成时建议在 pass 之外再要求：两引擎均有效、MOSS 只输出 1 个说话人、action 不是 review_consensus；too_short 另要求两引擎规范化后与原文完全一致。按此筛选保留 57965 条、57.77 小时（too_short 通过 1898/1982）
- `aishell3@tts-unified-v0.1`：音频编码字节存放在 Lance 表内；原始划分在 metadata_json.original_split，统一输出全部为 train。ASR 用 tts_lance.iter_asr_samples（tts-asr-rules/v1）读取，会排除原始 dev/test 等
- 含派生版本（与源数据可能重叠）

### aishell4

中文多人会议（AISHELL-4）；含轮流说话混合版

语言：zh · 任务：语音识别、diarization、带说话人标注的语音识别、说话人分段与归属、目标说话人语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [aishell4@allspk-asr-v1-20261103](../../catalog/allspk_asr_v1.yaml#L67) | — | 未登记 | 没有 |
| [aishell4@allspk-ts-v1-20261104](../../catalog/allspk_ts_v1.yaml#L90) | — | 未登记 | 没有 |
| [aishell4@asr-20261014](../../catalog/amphionasr_v4.yaml#L262) | — | 未登记 | 没有 |
| [aishell4@asr-20261014-ctxclean-20261110](../../catalog/context_correction_clean_zh.yaml#L643) | — | 未登记 | 没有 |
| [aishell4@asr-20261014-punc-20261102](../../catalog/train_punc_v1_derived.yaml#L423) | — | 未登记 | 没有 |
| [aishell4@diarization-benchmark-v1-20261021](../../catalog/diarization_benchmark.yaml#L1) | 12.7 | 已登记 | 没有 |
| [aishell4@icefall-20260908](../../catalog/icefall_runtime.yaml#L1206) | 119.5 | 已登记 | 快照 20260914 |
| [aishell4@legacy-20260804](../../catalog/icefall_base.yaml#L892) | 28.4 | 已登记 | 快照 20260914 |
| [aishell4@punc-teacher-v1-20261029](../../catalog/punc_teacher_v1.yaml#L245) | 3.2 | 已登记 | 没有 |
| [aishell4@punc-written-v1-20261029](../../catalog/zh_punc_written_v1.yaml#L130) | 107.4 | 已登记 | 没有 |
| [aishell4@teacher-review-v1-20261010](../../catalog/diarization_raw_zh-meeting-review.yaml#L2) | — | 未登记 | 没有 |
| [aishell4@turn-taking-20261014](../../catalog/amphionasr_v4.yaml#L1) | 322.3 | 已登记 | 没有 |
| [aishell4@turn-taking-20261014-ctxclean-20261110](../../catalog/context_correction_clean_zh.yaml#L972) | 322.3 | 已登记 | 没有 |
| [aishell4@turn-taking-20261014-utts](../../catalog/ts_window_utts.yaml#L115) | 66.9 | 已登记 | 没有 |
| [aishell4@turn-taking-20261014-utts-punc-20261102](../../catalog/train_punc_v1_derived.yaml#L486) | — | 未登记 | 没有 |

- `aishell4@allspk-asr-v1-20261103`：AISHELL-4 训练集的普通 ASR 多人窗口：按 aishell4@icefall-20260908 训练集标注，在每段录音上依次切出不重叠的窗口，每个窗口长度在 10–90 秒间均匀抽取，只在没人说话（前后静音至少 0.2 秒）处下刀；目标文本是窗口内所有说话人每句话的书面化标点文本（aishell4@punc-written-v1-20261029，同一 ID）按开始时间顺序拼接，不区分说话人。重叠语音超过窗口时长 10% 的窗口丢弃（普通转写的字序不确定），有任一句缺标点文本的窗口丢弃。音频引用 aishell4@asr-20261014 训练集（只取第 0 路），不复制。用途：普通 ASR 模式下多人轮流说话时转写每个人、长录音不提前结束（此前普通 ASR 训练数据每条只转写一个说话人）。保留 4267 个窗口，丢弃：重叠 1957、缺标点 0、短于 5 秒 92；说话人数分布 {'1': 512, '2': 1551, '3': 1278, '4+': 926}
- `aishell4@allspk-ts-v1-20261104`：AISHELL-4 训练集的目标说话人（TS）多人窗口，与 aishell4@allspk-asr-v1-20261103 用同一批窗口、同一段音频：普通 ASR 版本转写窗口里所有人，这里只转写注册的那个人，让模型在同一段音频上靠提示区分两种任务（只训普通 ASR 版本时，TS 模式在多人轮流说话的音频上会把别人的话也写进来）。train：每个窗口选一个在窗口里说话的人作目标（在有注册音的说话人里均匀抽），目标文本是此人在窗口内各句的书面化标点文本（aishell4@punc-written-v1-20261029）按开始时间顺序拼接；train_neg：每个窗口选一个同一录音里、窗口内没说话的人（有的话），目标为空。注册音取同一录音里此人在窗口外的一句话，长 3–10 秒（没有则放宽到 2–15 秒），且没有其他句子与之重叠。两个音频位都引用 aishell4@asr-20261014 训练集（与窗口同一路），不复制。正样本 4267 条（0 个窗口没有可用注册音），负样本 3511 条（756 个窗口没有不在场的说话人）；正样本窗口的说话人数分布 {'1': 512, '2': 1551, '3': 1278, '4+': 926}
- `aishell4@asr-20261014`：会议普通转写。每条 supervision 一条，时长 0.5～30 秒，文本非空。多通道只取第 0 路
- `aishell4@asr-20261014-ctxclean-20261110`：在 aishell4@asr-20261014 上做的上下文纠偏清洗：说话人讲字怎么写（组词、拆字、偏旁、否定对比）而标注写成同音别字的，按说明改正；拿不准的整条去掉。判定依据见 context_correction_clean_zh@v1-20261110
- `aishell4@asr-20261014-punc-20261102`：aishell4@asr-20261014 的 train，目标文本加书面化标点：中文用 amphiondata 的中文学生模型（punc-student-v1，不带听音提示），英文用英文规范 en-v1 的学生模型（加标点并恢复大小写）；标点按字 / 按词搬回原文，原文的字词不变，找不到输出的目标保留原样。其余字段与源版本相同，音频引用源版本
- `aishell4@diarization-benchmark-v1-20261021`：Frozen local evaluation slice; audio and RTTM bytes copied unchanged. Not a claim of official release equivalence or training disjointness.
- `aishell4@punc-teacher-v1-20261029`：aishell4@icefall-20260908 的 train 监督片段里的 Qwen3.8-27B 老师给 3000 句加的书面化标点（2765 句去掉标点后与输入一致，ok=true）：custom.punctuation_teacher 记输出 text、ok 和模型看到的无标点输入 input；custom.punctuation_hint.qwen 是提示用的 Qwen3-ASR 转写；其中 53 句是留出的评测句，另带学生 v1 的输出 custom.punctuation_student。这批句子用来微调 Qwen3-4B 学生，抽样见 amphiondata scripts/punctuation/build_teacher_set.py。只含这些句子，text 与父版本相同，不是标点后的文本；录音沿用父版本，不复制音频。中间产物，供复现和比较学生，不直接用于训练。脚本 scripts/punctuation/register_punc_intermediates.py
- `aishell4@punc-written-v1-20261029`：aishell4@icefall-20260908 训练集原标注加书面化标点（GB/T 15834，逗号从紧）：微调后的 Qwen3-4B（Qwen3.8-27B 的 9.6 万条输出蒸馏）以 Qwen3-ASR-1.7B 听音频得到的带标点转写作语气提示，只往原标注里插标点。模型改动了原文的条目，把模型输出的标点按字对齐搬回原标注；每条以 。？！ 结尾；原标注的字、空格（首尾除外）和大小写不变。没有汉字的条目（英文句子、拼读字母）和标注为空的条目原样保留。文件与源 supervisions 条数、顺序相同，只换 text。试点 200 条人工参照上：WenetSpeech markF1 92.4、其他来源 88.9（老师 93.2 / 88.2，原 FireRedPunc 79.8）
- `aishell4@teacher-review-v1-20261010`：AISHELL-4 train（186 场）的老师复核与时间更正（2026-10-10）：本机 MOSS-Transcribe-Diarize 0.9B 和 Qwen3-ASR-1.7B 对整场会议打标，与人工标注逐场对照，估计每场标注相对音频的时间偏移（包络滞后、MOSS 与人工配对偏移、AliMeeting 另有近场对远场 GCC-PHAT 滞后），决定平移或整场排除，并写出更正后的参考标注。train_supervisions_corrected_0：更正后的 train 标注 102254 条（源 102254 条，平移了 0 条的开始时间，去掉 0 条，源里没有的 0 条），Lhotse 格式，字段同源版本；整场排除的会议不从标注里删除，切窗口时按 excluded_meetings 跳过。excluded_meetings：3 场整场排除（1.709 h）及原因。train_supervisions_gap_fills_0：老师补出的 34 条漏标语音（fill / gap / overlap_other，说话人为原标注 ID，custom.diarize 记检查），不可用区间与未采纳片段在 gap_merge_records 的 metadata.gap_merge。moss_records / qwen3_asr_records 是两位教师的整场原始标签（metadata.local_moss / metadata.qwen3_asr）；offsets_records / near_far_lag_records / correction_decision_records 是逐场偏移估计和决定（metadata.time_offset / near_far_lag / correction_decision）；review_example_records 是文字差异等抽样证据。录音沿用 aishell4@icefall-20260908，不复制音频。脚本 scripts/diarization_raw_labels/register_raw_labels.py
- `aishell4@turn-taking-20261014`：会议 turn-taking。整句拼成 2/3 人混合窗，时长 0.5～30 秒。注册音是窗外另一句，1～30 秒。有近场时远场:近场 = 3:1
- `aishell4@turn-taking-20261014-ctxclean-20261110`：在 aishell4@turn-taking-20261014 上做的上下文纠偏清洗：说话人讲字怎么写（组词、拆字、偏旁、否定对比）而标注写成同音别字的，按说明改正；拿不准的整条去掉。判定依据见 context_correction_clean_zh@v1-20261110
- `aishell4@turn-taking-20261014-utts`：aishell4@turn-taking-20261014 的 train 划分（不含 eval/test），时间线取自 aishell4@icefall-20260908 的 train 人工标注。加 metadata.window_utts（窗口内每句的说话人与相对混合起点的起止，取自来源标注并截到窗口，截断的标 clipped）与同一命名空间的 metadata.target_speaker，供 open-audio-llm 帧级说话人活动标签（objective.ts_activity_weight）；其余字段不变，音频引用改指本版本，音频索引与原版逐行相同。正样本的目标语句与转写逐字一致（忽略空白和标点；窗口边缘截断的句子允许只转写一部分）才写时间线，负样本只有注册人确实不在窗口里说话才写；其余记录不写时间线（不出帧级标签）。负样本中注册人按标注其实在窗口内说话的记录 ID 列在 excluded-records-<split>.txt，训练配方用 exclude_records 排除。生成脚本 audio-data-contract scripts/ts_robust/add_window_utts.py，逐划分统计见 report.json
- `aishell4@turn-taking-20261014-utts-punc-20261102`：aishell4@turn-taking-20261014-utts 的 train_2spk, train_3spk, train_neg，目标文本加书面化标点：中文用 amphiondata 的中文学生模型（punc-student-v1，不带听音提示），英文用英文规范 en-v1 的学生模型（加标点并恢复大小写）；标点按字 / 按词搬回原文，原文的字词不变，找不到输出的目标保留原样。其余字段与源版本相同，音频引用源版本
- 含派生版本（与源数据可能重叠）

### aishell4_meeting_sot

AISHELL-4 会议切窗的多人按人转写数据

语言：zh · 任务：带说话人标注的语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [aishell4_meeting_sot@meeting-channel-view-v2-20261010](../../catalog/zh_farfield.yaml#L1) | 377.5 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/zh_farfield_channel_views/` |
| [aishell4_meeting_sot@real-meetings-v2-20261010](../../catalog/zh_meeting_v2.yaml#L1) | — | 未登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/aishell4_meeting_sot/` |
| [aishell4_meeting_sot@similar-voice-v1-20261014](../../catalog/similar_voice.yaml#L2) | — | 未登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/aishell4_meeting_sot/` |

- `aishell4_meeting_sot@similar-voice-v1-20261014`：aishell4_meeting_sot@real-meetings-v2-20261010 的“音色相近”子集：每个训练窗口里最相近两位说话人的声纹余弦相似度，各划分（窗口长度）取前 1/3。声纹模型 ERes2NetV2（iic/speech_eres2netv2_sv_zh-cn_16k-common），每人取不与他人重叠的语音（片段 ≥0.3 秒，合计 ≥1.5 秒，最多 10 秒）；30/300/600 秒窗口用对应 120 秒窗口里同一说话人的声纹均值。少于两个有声纹说话人的窗口不入选。标注不改，记录逐行照抄源版本，音频仍指向源版本。源版本训练排除名单里的记录（选模留出集、目标为空窗口）已剔除。用途：下一轮训练额外加采相近音色的窗口

### aishell5_meeting_sot

AISHELL-5 车内对话切窗的多人按人转写数据

语言：zh · 任务：带说话人标注的语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [aishell5_meeting_sot@far-mic-v1-20261010](../../catalog/zh_dialogue.yaml#L417) | — | 未登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/aishell5_meeting_sot/` |
| [aishell5_meeting_sot@similar-voice-v1-20261014](../../catalog/similar_voice.yaml#L401) | — | 未登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/aishell5_meeting_sot/` |

- `aishell5_meeting_sot@similar-voice-v1-20261014`：aishell5_meeting_sot@far-mic-v1-20261010 的“音色相近”子集：每个训练窗口里最相近两位说话人的声纹余弦相似度，各划分（窗口长度）取前 1/3。声纹模型 ERes2NetV2（iic/speech_eres2netv2_sv_zh-cn_16k-common），每人取不与他人重叠的语音（片段 ≥0.3 秒，合计 ≥1.5 秒，最多 10 秒）；30/300/600 秒窗口用对应 120 秒窗口里同一说话人的声纹均值。少于两个有声纹说话人的窗口不入选。标注不改，记录逐行照抄源版本，音频仍指向源版本。源版本训练排除名单里的记录（选模留出集、目标为空窗口）已剔除。用途：下一轮训练额外加采相近音色的窗口

### aishellmix

AISHELL-2 混合的目标说话人训练与测试数据

语言：zh · 任务：目标说话人语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [aishellmix@original-audio-record-20260910](../../catalog/aishellmix.yaml#L380) | 6,733.1 | 已登记：按目标样本累计混合音频，非去重语料时长 | 快照 20260914 |
| [aishellmix@original-source-20260910](../../catalog/aishellmix.yaml#L281) | — | 未登记 | 快照 20260914 |
| [aishellmix@pack3-current-audio-record-20260910](../../catalog/aishellmix.yaml#L114) | 7,489.2 | 已登记：按目标样本累计混合音频，非去重语料时长 | 快照 20260914 |
| [aishellmix@pack3-current-audio-record-20260910-punc-20261102](../../catalog/train_punc_v1_derived.yaml#L612) | — | 未登记 | 没有 |
| [aishellmix@pack3-current-source-20260910](../../catalog/aishellmix.yaml#L1) | — | 未登记 | 快照 20260914 |

- `aishellmix@original-audio-record-20260910`：AISHELLMix 原版历史训练（enrollment 至少 2 秒）与项目测试数据；纯转写、独立 enrollment/mixture、空转写负样本
- `aishellmix@original-source-20260910`：AISHELLMix 原版历史训练（enrollment 至少 2 秒）与项目测试数据；转换输入快照，时长见通用版本
- `aishellmix@pack3-current-audio-record-20260910`：AISHELLMix pack3 当前与历史等价训练数据；纯转写、独立 enrollment/mixture、空转写负样本
- `aishellmix@pack3-current-audio-record-20260910-punc-20261102`：aishellmix@pack3-current-audio-record-20260910 的 train_1spk, train_2spk, train_3spk, train_neg，目标文本加书面化标点：中文用 amphiondata 的中文学生模型（punc-student-v1，不带听音提示），英文用英文规范 en-v1 的学生模型（加标点并恢复大小写）；标点按字 / 按词搬回原文，原文的字词不变，找不到输出的目标保留原样。其余字段与源版本相同，音频引用源版本
- `aishellmix@pack3-current-source-20260910`：AISHELLMix pack3 当前与历史等价训练数据；转换输入快照，时长见通用版本
- 含派生版本（与源数据可能重叠）

### alimeeting

中文远场会议，多人重叠语音（AliMeeting）

语言：zh · 任务：语音识别、连续语音分离、diarization、重叠语音检测、带说话人标注的语音识别、说话人分段与归属、目标说话人语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [alimeeting@diarization-benchmark-v1-20261021](../../catalog/diarization_benchmark.yaml#L69) | 10.8 | 已登记 | 没有 |
| [alimeeting@diarization-benchmark-v1-20261021-2023test](../../catalog/diarization_benchmark.yaml#L138) | 10.0 | 已登记 | 没有 |
| [alimeeting@openslr-119-far-local-20260903](../../catalog/alimeeting_far_raw.yaml#L1) | 125.5 | 已登记 | 快照 20260914 |
| [alimeeting@openslr-119-local-20260826](../../catalog/multilingual_multispeaker.yaml#L1) | 157.9 | 已登记 | 快照 20260914 |
| [alimeeting_sdm@allspk-asr-v1-20261103](../../catalog/allspk_asr_v1.yaml#L131) | — | 未登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/alimeeting_sdm/` |
| [alimeeting_sdm@allspk-ts-v1-20261104](../../catalog/allspk_ts_v1.yaml#L178) | — | 未登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/alimeeting_sdm/` |
| [alimeeting_sdm@asr-20261014](../../catalog/amphionasr_v4.yaml#L726) | — | 未登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/alimeeting_sdm/` |
| [alimeeting_sdm@asr-20261014-punc-20261102](../../catalog/train_punc_v1_derived.yaml#L750) | — | 未登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/alimeeting_sdm/` |
| [alimeeting_sdm@icefall-20260908](../../catalog/icefall_runtime.yaml#L2839) | 157.9 | 已登记：单远场麦克风标注片段 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/alimeeting_sdm/` |
| [alimeeting_sdm@punc-gold-v1-20261029](../../catalog/punc_teacher_v1.yaml#L840) | 0.0 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/alimeeting_sdm/` |
| [alimeeting_sdm@punc-teacher-v1-20261029](../../catalog/punc_teacher_v1.yaml#L439) | 2.3 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/alimeeting_sdm/` |
| [alimeeting_sdm@punc-written-v1-20261029](../../catalog/zh_punc_written_v1.yaml#L473) | 140.6 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/alimeeting_sdm/` |
| [alimeeting_sdm@teacher-calibration-v1-20261009](../../catalog/diarization_raw_teacher-calibration.yaml#L97) | — | 未登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/alimeeting_sdm/` |
| [alimeeting_sdm@teacher-review-v1-20261010](../../catalog/diarization_raw_zh-meeting-review.yaml#L155) | — | 未登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/alimeeting_sdm/` |
| [alimeeting_sdm@turn-taking-20261014](../../catalog/amphionasr_v4.yaml#L378) | 427.7 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/alimeeting_sdm/` |
| [alimeeting_sdm@turn-taking-20261014-utts](../../catalog/ts_window_utts.yaml#L1) | 82.7 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/alimeeting_sdm/` |
| [alimeeting_sdm@turn-taking-20261014-utts-punc-20261102](../../catalog/train_punc_v1_derived.yaml#L813) | — | 未登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/alimeeting_sdm/` |

- `alimeeting@diarization-benchmark-v1-20261021`、`alimeeting@diarization-benchmark-v1-20261021-2023test`：Frozen local evaluation slice; audio and RTTM bytes copied unchanged. Not a claim of official release equivalence or training disjointness.
- `alimeeting@openslr-119-far-local-20260903`：远场会议、多说话人、重叠语音；训练集 8 条标注越界，使用前需处理
- `alimeeting_sdm@allspk-asr-v1-20261103`：AliMeeting 训练集的普通 ASR 多人窗口：按 alimeeting_sdm@icefall-20260908 训练集标注，在每段录音上依次切出不重叠的窗口，每个窗口长度在 10–90 秒间均匀抽取，只在没人说话（前后静音至少 0.2 秒）处下刀；目标文本是窗口内所有说话人每句话的书面化标点文本（alimeeting_sdm@punc-written-v1-20261029，同一 ID）按开始时间顺序拼接，不区分说话人。重叠语音超过窗口时长 10% 的窗口丢弃（普通转写的字序不确定），有任一句缺标点文本的窗口丢弃。音频引用 alimeeting_sdm@asr-20261014 训练集（只取第 0 路），不复制。用途：普通 ASR 模式下多人轮流说话时转写每个人、长录音不提前结束（此前普通 ASR 训练数据每条只转写一个说话人）。保留 2527 个窗口，丢弃：重叠 3811、缺标点 0、短于 5 秒 140；说话人数分布 {'1': 235, '2': 1954, '3': 213, '4+': 125}
- `alimeeting_sdm@allspk-ts-v1-20261104`：AliMeeting 训练集的目标说话人（TS）多人窗口，与 alimeeting_sdm@allspk-asr-v1-20261103 用同一批窗口、同一段音频：普通 ASR 版本转写窗口里所有人，这里只转写注册的那个人，让模型在同一段音频上靠提示区分两种任务（只训普通 ASR 版本时，TS 模式在多人轮流说话的音频上会把别人的话也写进来）。train：每个窗口选一个在窗口里说话的人作目标（在有注册音的说话人里均匀抽），目标文本是此人在窗口内各句的书面化标点文本（alimeeting_sdm@punc-written-v1-20261029）按开始时间顺序拼接；train_neg：每个窗口选一个同一录音里、窗口内没说话的人（有的话），目标为空。注册音取同一录音里此人在窗口外的一句话，长 3–10 秒（没有则放宽到 2–15 秒），且没有其他句子与之重叠。两个音频位都引用 alimeeting_sdm@asr-20261014 训练集（与窗口同一路），不复制。正样本 2521 条（6 个窗口没有可用注册音），负样本 421 条（2106 个窗口没有不在场的说话人）；正样本窗口的说话人数分布 {'1': 231, '2': 1953, '3': 213, '4+': 124}
- `alimeeting_sdm@asr-20261014`：会议普通转写。每条 supervision 一条，时长 0.5～30 秒，文本非空。多通道只取第 0 路
- `alimeeting_sdm@asr-20261014-punc-20261102`：alimeeting_sdm@asr-20261014 的 train，目标文本加书面化标点：中文用 amphiondata 的中文学生模型（punc-student-v1，不带听音提示），英文用英文规范 en-v1 的学生模型（加标点并恢复大小写）；标点按字 / 按词搬回原文，原文的字词不变，找不到输出的目标保留原样。其余字段与源版本相同，音频引用源版本
- `alimeeting_sdm@icefall-20260908`：标注片段时长，重叠语音或多麦克风可能重复计时
- `alimeeting_sdm@punc-gold-v1-20261029`：alimeeting_sdm@icefall-20260908 的 train 监督片段里的 普通话标点试点的 15 句手写参照标点（规范 v1，逗号从紧）：custom.punctuation_gold.text 是参照，custom.punctuation_hint 记试点用的 Qwen3-ASR 与 FireRedPunc 带标点转写。只含这些句子，text 与父版本相同，不是标点后的文本；录音沿用父版本，不复制音频。中间产物，供复现和比较学生，不直接用于训练。脚本 scripts/punctuation/register_punc_intermediates.py
- `alimeeting_sdm@punc-teacher-v1-20261029`：alimeeting_sdm@icefall-20260908 的 train 监督片段里的 Qwen3.8-27B 老师给 3000 句加的书面化标点（2780 句去掉标点后与输入一致，ok=true）：custom.punctuation_teacher 记输出 text、ok 和模型看到的无标点输入 input；custom.punctuation_hint.qwen 是提示用的 Qwen3-ASR 转写；其中 58 句是留出的评测句，另带学生 v1 的输出 custom.punctuation_student。这批句子用来微调 Qwen3-4B 学生，抽样见 amphiondata scripts/punctuation/build_teacher_set.py。只含这些句子，text 与父版本相同，不是标点后的文本；录音沿用父版本，不复制音频。中间产物，供复现和比较学生，不直接用于训练。脚本 scripts/punctuation/register_punc_intermediates.py
- `alimeeting_sdm@punc-written-v1-20261029`：alimeeting_sdm@icefall-20260908 训练集原标注加书面化标点（GB/T 15834，逗号从紧）：微调后的 Qwen3-4B（Qwen3.8-27B 的 9.6 万条输出蒸馏）以 Qwen3-ASR-1.7B 听音频得到的带标点转写作语气提示，只往原标注里插标点。模型改动了原文的条目，把模型输出的标点按字对齐搬回原标注；每条以 。？！ 结尾；原标注的字、空格（首尾除外）和大小写不变。没有汉字的条目（英文句子、拼读字母）和标注为空的条目原样保留。文件与源 supervisions 条数、顺序相同，只换 text。试点 200 条人工参照上：WenetSpeech markF1 92.4、其他来源 88.9（老师 93.2 / 88.2，原 FireRedPunc 79.8）
- `alimeeting_sdm@teacher-calibration-v1-20261009`：说话人日志老师校准（2026-10-09）：在有人工标注的 AliMeeting train 远场 ch0 6 条 / 3.34 h 上比较本机 MOSS 0.9B、MOSS Pro、百炼 qwen-audio-3.1-asr-flash 三个老师，并用 Qwen3-ASR 对本机 MOSS 的每个片段做文本校验；付费调用经用户批准，仅用于这次校准。每个 *_records 文件一个老师，每行一条录音，target 是按时间排序的 [说话人][起-止] 文本，教师返回的分块、说话人链接、身份断点留在 metadata.<老师>；teacher_agreement_records 每行一个人工标注片段，metadata.teacher_agreement 记各老师的说话人、边界和字错误率（analysis/segments.jsonl，用于确定多老师一致性过滤门槛）。录音沿用 alimeeting_sdm@icefall-20260908 train_rec_0（只用其中被抽中的录音），不复制音频。脚本 scripts/diarization_raw_labels/register_raw_labels.py
- `alimeeting_sdm@teacher-review-v1-20261010`：AliMeeting train 远场（209 场）的老师复核与时间更正（2026-10-10）：本机 MOSS-Transcribe-Diarize 0.9B 和 Qwen3-ASR-1.7B 对整场会议打标，与人工标注逐场对照，估计每场标注相对音频的时间偏移（包络滞后、MOSS 与人工配对偏移、AliMeeting 另有近场对远场 GCC-PHAT 滞后），决定平移或整场排除，并写出更正后的参考标注。train_supervisions_corrected_0：更正后的 train 标注 186360 条（源 186360 条，平移了 949 条的开始时间，去掉 0 条，源里没有的 0 条），Lhotse 格式，字段同源版本；整场排除的会议不从标注里删除，切窗口时按 excluded_meetings 跳过。excluded_meetings：36 场整场排除（19.211 h）及原因。train_supervisions_gap_fills_0：老师补出的 79 条漏标语音（fill / gap / overlap_other，说话人为原标注 ID，custom.diarize 记检查），不可用区间与未采纳片段在 gap_merge_records 的 metadata.gap_merge。moss_records / qwen3_asr_records 是两位教师的整场原始标签（metadata.local_moss / metadata.qwen3_asr）；offsets_records / near_far_lag_records / correction_decision_records 是逐场偏移估计和决定（metadata.time_offset / near_far_lag / correction_decision）；review_example_records 是文字差异等抽样证据。录音沿用 alimeeting_sdm@icefall-20260908，不复制音频。脚本 scripts/diarization_raw_labels/register_raw_labels.py
- `alimeeting_sdm@turn-taking-20261014`：会议 turn-taking。整句拼成 2/3 人混合窗，时长 0.5～30 秒。注册音是窗外另一句，1～30 秒。有近场时远场:近场 = 3:1
- `alimeeting_sdm@turn-taking-20261014-utts`：alimeeting_sdm@turn-taking-20261014 的 train 划分（不含 eval/test），时间线取自 alimeeting_sdm@icefall-20260908 的 train 人工标注。加 metadata.window_utts（窗口内每句的说话人与相对混合起点的起止，取自来源标注并截到窗口，截断的标 clipped）与同一命名空间的 metadata.target_speaker，供 open-audio-llm 帧级说话人活动标签（objective.ts_activity_weight）；其余字段不变，音频引用改指本版本，音频索引与原版逐行相同。正样本的目标语句与转写逐字一致（忽略空白和标点；窗口边缘截断的句子允许只转写一部分）才写时间线，负样本只有注册人确实不在窗口里说话才写；其余记录不写时间线（不出帧级标签）。负样本中注册人按标注其实在窗口内说话的记录 ID 列在 excluded-records-<split>.txt，训练配方用 exclude_records 排除。生成脚本 audio-data-contract scripts/ts_robust/add_window_utts.py，逐划分统计见 report.json
- `alimeeting_sdm@turn-taking-20261014-utts-punc-20261102`：alimeeting_sdm@turn-taking-20261014-utts 的 train_2spk, train_3spk, train_neg，目标文本加书面化标点：中文用 amphiondata 的中文学生模型（punc-student-v1，不带听音提示），英文用英文规范 en-v1 的学生模型（加标点并恢复大小写）；标点按字 / 按词搬回原文，原文的字词不变，找不到输出的目标保留原样。其余字段与源版本相同，音频引用源版本
- 含派生版本（与源数据可能重叠）

### alimeeting_near_farsim_meeting_sot

AliMeeting 近讲加混响噪声模拟远场的会议窗口

语言：zh · 任务：带说话人标注的语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [alimeeting_near_farsim_meeting_sot@near-farsim-v1-20261009](../../catalog/zh_farfield.yaml#L167) | 399.5 | 已登记 | 没有 |

### alimeeting_sdm_meeting_sot

AliMeeting 远场会议切窗的多人按人转写数据

语言：zh · 任务：带说话人标注的语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [alimeeting_sdm_meeting_sot@meeting-channel-view-v2-20261010](../../catalog/zh_farfield.yaml#L84) | 327.3 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/zh_farfield_channel_views/` |
| [alimeeting_sdm_meeting_sot@real-meetings-v2-20261010](../../catalog/zh_meeting_v2.yaml#L99) | — | 未登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/alimeeting_sdm_meeting_sot/` |
| [alimeeting_sdm_meeting_sot@similar-voice-v1-20261014](../../catalog/similar_voice.yaml#L135) | — | 未登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/alimeeting_sdm_meeting_sot/` |

- `alimeeting_sdm_meeting_sot@similar-voice-v1-20261014`：alimeeting_sdm_meeting_sot@real-meetings-v2-20261010 的“音色相近”子集：每个训练窗口里最相近两位说话人的声纹余弦相似度，各划分（窗口长度）取前 1/3。声纹模型 ERes2NetV2（iic/speech_eres2netv2_sv_zh-cn_16k-common），每人取不与他人重叠的语音（片段 ≥0.3 秒，合计 ≥1.5 秒，最多 10 秒）；30/300/600 秒窗口用对应 120 秒窗口里同一说话人的声纹均值。少于两个有声纹说话人的窗口不入选。标注不改，记录逐行照抄源版本，音频仍指向源版本。源版本训练排除名单里的记录（选模留出集、目标为空窗口）已剔除。用途：下一轮训练额外加采相近音色的窗口

### biic_podcast_ser

中文播客情感识别评测（BIIC-Podcast）

语言：zh · 任务：语音情感识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [biic_podcast_ser@eval-20260804](../../catalog/open_audio_eval.yaml#L799) | 22.6 | 已登记 | 快照 20260914 |

- 当前仅登记评测入口

### business_feedback

业务反馈的目标说话人 bad case，仅评测

语言：zh · 任务：目标说话人语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [business_feedback@ts-20261010](../../catalog/business_feedback.yaml#L1) | 0.0 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/business_feedback/` |
| [business_feedback@ts-20261012](../../catalog/business_feedback.yaml#L64) | 0.0 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/business_feedback/` |
| [business_feedback@ts-20261016](../../catalog/business_feedback.yaml#L126) | 0.0 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/business_feedback/` |
| [business_feedback@ts-20261019](../../catalog/business_feedback.yaml#L208) | 0.0 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/business_feedback/` |
| [business_feedback@ts-20261021](../../catalog/business_feedback.yaml#L270) | 0.0 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/business_feedback/` |
| [business_feedback@ts-20261022](../../catalog/business_feedback.yaml#L312) | 0.1 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/business_feedback/` |

- `business_feedback@ts-20261010`：业务反馈的目标说话人 bad case，每个批次一个版本，只用于评测，不进训练。测试人员在办公室注册一个人的声纹，同时用 pad 播放干扰声（歌曲、对白）时反馈的 7 个调试包（8 段输入）。 每段输入为 3 秒注册音频加一个识别片段；7 个包使用同一段注册音频
- `business_feedback@ts-20261012`：业务反馈的目标说话人 bad case，每个批次一个版本，只用于评测，不进训练。测试人员把设备放在一个环境里持续收音，定时查看结果，反馈的 5 个调试包（case-08 到 case-12）。 每段输入为 3 秒注册音频加一个识别片段；与第一批使用同一段注册音频
- `business_feedback@ts-20261016`：业务反馈的目标说话人 bad case，每个批次一个版本，只用于评测，不进训练。测试人员持续收音时反馈的 31 个调试包（表格第 2–37 行，去掉与第二批重复的包），与第二批使用同一段注册音频。 每段输入为 3 秒注册音频加一个识别片段；目标是否在场与参考文本经复核人逐条听音确认
- `business_feedback@ts-20261019`：业务反馈的目标说话人 bad case，每个批次一个版本，只用于评测，不进训练。测试人员持续收音时反馈的 2 个调试包（表格第 38、39 行），换了一段新的注册音频。 每段输入为 3 秒注册音频加一个识别片段；目标是否在场取自表格的错误类型，在场那条的参考文本由自动复核确定，未经人工听审
- `business_feedback@ts-20261021`：业务反馈的目标说话人 bad case，每个批次一个版本，只用于评测，不进训练。测试人员持续收音时反馈的 2 个调试包（表格第 40、41 行），换了一段新的注册音频。 每段输入为 3 秒注册音频加一个识别片段；两条都是机主未说话、另一个人说了一句约 1 秒的短话，模型输出了这句话
- `business_feedback@ts-20261022`：业务反馈的目标说话人 bad case，每个批次一个版本，只用于评测，不进训练。用户直接提供的两段长录音（没有调试包），机主全程未说话，旁边外放电视剧对白，期望输出为空； 按 25 秒连续分窗，每窗一条，共 10 条；注册录音 8.28 秒整段保存，客户端取前 5 秒

### childmandarin

3–5 岁儿童普通话语音（ChildMandarin）

语言：zh · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [childmandarin@icefall-20260908](../../catalog/icefall_runtime.yaml#L1849) | 41.0 | 已登记 | 快照 20260914 |
| [childmandarin@legacy-20260804](../../catalog/icefall_base.yaml#L1450) | 41.0 | 已登记 | 快照 20260914 |

- 含派生版本（与源数据可能重叠）

### cnceleb1

中文跨场景声纹数据（CN-Celeb1）

语言：zh · 任务：说话人身份识别、声纹验证

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [cnceleb1@openslr-82-v2](../../catalog/cnceleb1.yaml#L1) | — | 未登记 | 快照 20260914 |
| [cnceleb1@speaker-records-v1-20260912](../../catalog/cnceleb1.yaml#L59) | 270.1 | 已登记 | 快照 20260914 |

- `cnceleb1@openslr-82-v2`：中文跨场景声纹数据，修正版 v2；train 对应官方 dev，test 对应官方 eval
- `cnceleb1@speaker-records-v1-20260912`：已解包、实测音频头并生成通用说话人记录；保留官方划分和标注

### cnceleb2

中文跨场景声纹训练数据（CN-Celeb2）

语言：zh · 任务：说话人身份识别、声纹验证

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [cnceleb2@openslr-82-v2](../../catalog/cnceleb2.yaml#L1) | — | 未登记 | 快照 20260914 |
| [cnceleb2@speaker-records-v1-20260912](../../catalog/cnceleb2.yaml#L79) | 1,084.3 | 已登记 | 快照 20260914 |

- `cnceleb2@openslr-82-v2`：中文跨场景声纹训练数据，修正版 v2；三个分包按 aa、ab、ac 顺序构成同一个 tar.gz
- `cnceleb2@speaker-records-v1-20260912`：已解包、实测音频头并生成通用说话人记录；保留官方划分和标注

### common_voice_zh

Common Voice 中文众包朗读；含清洗、热词、加噪版

语言：zh · 任务：语音识别、热词增强语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [common_voice_zh@clean-dual-qwen-moss-v1-20261009](../../catalog/zh_source_clean_20261009.yaml#L338) | 41.8 | 已登记 | 没有 |
| [common_voice_zh@hf-8262c16bf297](../../catalog/multilingual_asr_sources.yaml#L64) | 17.5 | 已登记 | 没有 |
| [common_voice_zh@icefall-20260908](../../catalog/icefall_runtime.yaml#L1685) | 76.1 | 已登记 | 快照 20260914 |
| [common_voice_zh@legacy-20260804](../../catalog/icefall_base.yaml#L1311) | 76.1 | 已登记 | 快照 20260914 |
| [common_voice_zh@punc-written-v1-20261102](../../catalog/zh_punc_written_v1_gaps.yaml#L66) | 42.6 | 已登记 | 没有 |
| [common_voice_zh@train-punc-v1-20261102](../../catalog/train_punc_v1.yaml#L207) | — | 未登记 | 没有 |
| [commonvoice_zh@eval-20260804](../../catalog/open_audio_eval.yaml#L318) | 17.5 | 已登记 | 快照 20260914 |
| [commonvoice_zh_clean@clean-v1-20260805](../../catalog/local_lhotse_derived.yaml#L487) | 17.5 | 已登记 | 快照 20260914 |
| [commonvoice_zh_hotwords@eval-20260804](../../catalog/open_audio_eval.yaml#L382) | 17.5 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/commonvoice_zh_hotwords/` |
| [commonvoice_zh_hotwords@hotwords-v1-20260805](../../catalog/local_lhotse_derived.yaml#L534) | 60.0 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/commonvoice_zh_hotwords/` |
| [cv_zh_noise_audioset_esc@eval-20260804](../../catalog/open_audio_eval.yaml#L2070) | 17.4 | 已登记 | 快照 20260914 |
| [cv_zh_noise_audioset_esc_hotwords@eval-20260804](../../catalog/open_audio_eval.yaml#L2774) | 17.4 | 已登记 | 快照 20260914 |
| [cv_zh_noise_audioset_traffic@eval-20260804](../../catalog/open_audio_eval.yaml#L2038) | 17.4 | 已登记 | 快照 20260914 |
| [cv_zh_noise_audioset_traffic_hotwords@eval-20260804](../../catalog/open_audio_eval.yaml#L2742) | 17.4 | 已登记 | 快照 20260914 |
| [cv_zh_noise_dns@eval-20260804](../../catalog/open_audio_eval.yaml#L2006) | 17.4 | 已登记 | 快照 20260914 |
| [cv_zh_noise_dns_hotwords@eval-20260804](../../catalog/open_audio_eval.yaml#L2710) | 17.4 | 已登记 | 快照 20260914 |
| [cv_zh_noise_musan_music@eval-20260804](../../catalog/open_audio_eval.yaml#L1942) | 17.4 | 已登记 | 快照 20260914 |
| [cv_zh_noise_musan_music_hotwords@eval-20260804](../../catalog/open_audio_eval.yaml#L2646) | 17.4 | 已登记 | 快照 20260914 |
| [cv_zh_noise_musan_noise@eval-20260804](../../catalog/open_audio_eval.yaml#L1910) | 17.4 | 已登记 | 快照 20260914 |
| [cv_zh_noise_musan_noise_hotwords@eval-20260804](../../catalog/open_audio_eval.yaml#L2614) | 17.4 | 已登记 | 快照 20260914 |
| [cv_zh_noise_musan_speech@eval-20260804](../../catalog/open_audio_eval.yaml#L1974) | 17.4 | 已登记 | 快照 20260914 |
| [cv_zh_noise_musan_speech_hotwords@eval-20260804](../../catalog/open_audio_eval.yaml#L2678) | 17.4 | 已登记 | 快照 20260914 |
| [cv_zh_noise_wham@eval-20260804](../../catalog/open_audio_eval.yaml#L2102) | 17.4 | 已登记 | 快照 20260914 |
| [cv_zh_noise_wham_hotwords@eval-20260804](../../catalog/open_audio_eval.yaml#L2806) | 17.4 | 已登记 | 快照 20260914 |
| [cv_zh_rir_rirmega@eval-20260804](../../catalog/open_audio_eval.yaml#L1878) | 17.4 | 已登记 | 快照 20260914 |
| [cv_zh_rir_rirmega_hotwords@eval-20260804](../../catalog/open_audio_eval.yaml#L2582) | 17.4 | 已登记 | 快照 20260914 |
| [cv_zh_rir_slr26@eval-20260804](../../catalog/open_audio_eval.yaml#L1782) | 17.4 | 已登记 | 快照 20260914 |
| [cv_zh_rir_slr26_hotwords@eval-20260804](../../catalog/open_audio_eval.yaml#L2486) | 17.4 | 已登记 | 快照 20260914 |
| [cv_zh_rir_slr28_real@eval-20260804](../../catalog/open_audio_eval.yaml#L1846) | 17.4 | 已登记 | 快照 20260914 |
| [cv_zh_rir_slr28_real_hotwords@eval-20260804](../../catalog/open_audio_eval.yaml#L2550) | 17.4 | 已登记 | 快照 20260914 |
| [cv_zh_rir_slr28_sim@eval-20260804](../../catalog/open_audio_eval.yaml#L1814) | 17.4 | 已登记 | 快照 20260914 |
| [cv_zh_rir_slr28_sim_hotwords@eval-20260804](../../catalog/open_audio_eval.yaml#L2518) | 17.4 | 已登记 | 快照 20260914 |
| [common_voice_zh@legacy-20260804](../../catalog/icefall_base.yaml#L1311) | 43.0 | [参考表](https://ccnuebbmik1f.feishu.cn/wiki/CEXFwEjPoi2bIukVjk9c5FdOn12?sheet=3d4d23) | 快照 20260914 |

- `common_voice_zh@clean-dual-qwen-moss-v1-20261009`：common_voice_zh@icefall-20260908 的 train 监督片段，经 Qwen3-ASR-1.7B 与 MOSS-Transcribe-Diarize 双引擎一致性清洗（与 2026-10-08 的 primewords、aishell3、aidatatang、magicdata、magicdata_ramc 同一流程）；逐条写入 custom.clean（pass、reason、action、engine_status、两引擎各自和互相的 CER、MOSS 说话人段），不删除记录，读取时按 require_clean_pass 过滤。音频沿用源版本，不复制。规则 consensus-v6 / wenetspeech-faithful-v5：29560 条中 pass 28448、reject 1112。少于 2 个字的 too_short 共 0 条按规则不经引擎直接 pass。restore_disfluency 改写了 1 条的 text（原文留在 custom.original_text）；无标点清单另把 192 条的标点和撇号去掉。引擎原始结果和复核清单在 evidence/。脚本 scripts/zh_source_clean/register_clean_dual.py
- `common_voice_zh@hf-8262c16bf297`：Common Voice 17.0 zh-CN 的非官方 HF 镜像（官方 Mozilla 仓库需要授权），只下载了 test，与 common_voice_pt@hf-8262c16bf297 同一修订
- `common_voice_zh@punc-written-v1-20261102`：common_voice_zh@legacy-20260804 训练集原标注加书面化标点，方法与 punc-written-v1-20261029 相同（amphiondata docs/written-punctuation.md：GB/T 15834、逗号从紧；Qwen3-4B 学生 punc-student-v1 以 Qwen3-ASR-1.7B 听音频得到的带标点转写作语气提示，只往原标注里插标点）。模型改动原文的条目按字对齐把标点搬回原标注；每条以 。？！ 结尾；没有汉字的条目和空标注原样保留。文件与源 supervisions 条数、顺序相同，只换 text
- `common_voice_zh@train-punc-v1-20261102`：common_voice_zh@legacy-20260804 的 train 训练版本，目标文本换成带标点的写法（按 id 取自 datasets/common_voice_zh/versions/punc-written-v1-20261102/cv-zh-CN_supervisions_train_punc_written.jsonl.gz；去掉标点和空格、转小写后与原文一致才替换，否则保留原文）。其余字段与源版本相同，录音引用源版本
- 含派生版本（与源数据可能重叠）

### common_voice_zh_hk

众包朗读粤语（Common Voice 香港）

语言：yue · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [common_voice_zh_hk@icefall-20260908](../../catalog/icefall_runtime.yaml#L2504) | 25.3 | 已登记 | 快照 20260914 |
| [common_voice_zh_hk@legacy-20260804](../../catalog/icefall_base.yaml#L2113) | 25.3 | 已登记 | 快照 20260914 |

- 含派生版本（与源数据可能重叠）

### context_correction_clean_zh

说字写法句子的 think 文本（CoT）

语言：zh · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [context_correction_clean_zh@think-v1-20261112](../../catalog/context_correction_clean_zh.yaml#L2094) | — | 未登记 | 没有 |
| [context_correction_clean_zh@v1-20261110](../../catalog/context_correction_clean_zh.yaml#L8) | — | 未登记 | 没有 |

- `context_correction_clean_zh@think-v1-20261112`：从 context_correction_clean_zh@v1-20261110 的判定结果，给清洗过的各来源训练记录生成 think 文本：每个被说明的词一句， 字和原话取两个判定模型的说明，两个模型给的字必须一致（改字窗口里一个模型写的是改前的字、或只多写了同一个词里的字的，对齐后算一致）； 只在"不是…"里出现的字、只点名的偏旁不成句，否定对比并进相邻写法的原话；原话超过 30 字、说话人随后改口、写法不在文本里的，只进 think 关。 每行一条训练记录（dataset + record_id，对应各来源的派生版本；alimeeting_sdm 是原版本；record_id 是 open-audio-llm 加载后的记录 ID， WenetSpeech、VITW 为 <dataset>@<version>:train:<supervision id>）：think_on=true 的给出 think， think_on=false 的只能按 think 关训练（not_hit 和规则候选里仍有讲写法的，判定不一的也不确定），未列出的记录是普通样本，think 开时用固定句"这段没有说明字怎么写。"。 WenetSpeech、VITW 按分段训练：原话整段落在哪个分段，该分段才有 think；原话被分段切开的，只有切开后仍是完整"X的X"的那段保留。 执行者看过全部新增规则放出的样本和各只进 think 关原因的抽样，结论写在运行目录 README 的"CoT 生成"一节。 还没有用于训练
- `context_correction_clean_zh@v1-20261110`：清洗对象是 AmphionASR v4 配方里的中文真实口语来源：wenetspeech_podcast、wenetspeech_youtube（l-20261014）、 emilia2_short（short-20261014 与 short-lance-20261023）、emilia2_dialog、emilia2_mix、magicdata_ramc / aishell4 / alimeeting_sdm （asr-20261014 与 turn-taking-20261014）、vitw（2m-20261013）；朗读类（hw_sft 中文部分等）不扫。 找出说话人用组词、拆字、偏旁或否定对比说明字怎么写的句子，由两个不同家族的 LLM 独立判断标注是否与说明一致： 一致的列为正例；两边改法完全相同、只改写法不改读音、说明部分读音经 Qwen3-ASR 核对的才改正；其余隔离、不进训练。 本版本只存判定清单（逐条判定与依据、正例、隔离名单、统计），不是训练集；改正后的训练数据以各来源的派生版本另行登记。 context_correction_zh 评测用过的 190 条 WenetSpeech 播客录音（83,220 段、48.9 h）一并排除。 wenetspeech_podcast 已完成（派生版本 wenetspeech_podcast@l-20261014-ctxclean-20261110）。 会议来源（人工标注）已完成：不做 Qwen3-ASR 音频核对（远场、电话音频上 ASR 不如人工标注准，试跑 4 个音频不符全是 ASR 听错）； 派生版本 magicdata_ramc@asr-20261014-ctxclean-20261110、magicdata_ramc@turn-taking-20261014-ctxclean-20261110、 aishell4@asr-20261014-ctxclean-20261110、aishell4@turn-taking-20261014-ctxclean-20261110；alimeeting_sdm 两个版本没有改动或隔离，继续用原版本。 wenetspeech_youtube 已完成（派生版本 wenetspeech_youtube@l-20261014-ctxclean-20261110）。 vitw 已完成（派生版本 vitw@2m-20261013-ctxclean-20261110，只去掉 3 段存疑，另 2 段已捞回）：音频是加了回声、噪声、丢帧的劣化音频， Qwen3-ASR 识别不出，不做音频核对。 emilia2_dialog 已完成（派生版本 emilia2_dialog@dialog-turn-taking-20261013-enroll-ctxclean-20261110，同时去掉 ts_asr_real 留出的评测源录音）： 混合音频里还有别人说话，音频核对改为在识别结果里找说明、只数标注里没被听到的音节。 emilia2_short 已完成（派生版本 emilia2_short@short-lance-20261023-ctxclean-20261110，音频读 Lance）；m4a 版 short-20261014 已被取代、 音频已删，不出派生版本，只登记它的 exclude_records 名单。 emilia2_mix 已完成（派生版本 emilia2_mix@mix-20261013-ctxclean-20261110，同时去掉 ts_asr_real 留出的评测源录音）： 音频核对读混音协议里目标说话人的干净原片段；抽检发现 8 段改错或多改，改判为隔离。 2026-11-12 捞回：因文本原因隔离、首轮没有模型提出改法的窗口，两个模型再判一次“原标注是否已照说明写对”， 两边都说对、机械检查和音频核对都通过的放回训练（原文不动，不进正例）；执行者逐条看过全部放回的 129 段文本， 判错 6 段、存疑 12 段写进各来源的 review_rejected 名单、仍然隔离，最终放回 111 段不同文本
- 含派生版本（与源数据可能重叠）

### context_correction_zh

中文上下文纠偏评测集，同音词按语境写

语言：zh · 任务：语音识别、目标说话人语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [context_correction_zh@v1-20261018](../../catalog/context_correction_zh.yaml#L1) | 17.6 | 已登记 | 没有 |

- `context_correction_zh@v1-20261018`：上下文纠偏评测集，只用于评测，不进训练。说话人在同一段话里用说明或语境确定了某个同音词的写法 (显式说字、同名一致性、隐式语义)，识别结果应按上下文写。题目由 qwen3.6-plus 生成、 deepseek-v4-pro 独立复核，Qwen3-TTS 用测试划分说话人的声音合成，SenseVoiceSmall 拼音级质检； 另有从 WenetSpeech 播客挖掘的真实录音。生成脚本 scripts/context_correction/

### csemotions

中文情感语音（CSEMOTIONS），TTS 用

语言：zh · 任务：语音合成

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [csemotions@tts-unified-v0.1](../../catalog/tts_unified.yaml#L44) | 10.2 | 已登记 | `amphion-tts-data-1373259071:CSEMOTIONS/`（原始数据） |

- `csemotions@tts-unified-v0.1`：音频编码字节存放在 Lance 表内；原始划分在 metadata_json.original_split，统一输出全部为 train。ASR 用 tts_lance.iter_asr_samples（tts-asr-rules/v1）读取，会排除原始 dev/test 等

### emilia2_zh_dialogue_diarize

Emilia2 中文对话的说话人日志伪标签

语言：zh · 任务：语音识别、diarization、带说话人标注的语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [emilia2_zh_dialogue_diarize@hotwords-qwen3.8-flash-m4a64k-v1](../../catalog/emilia2_zh_dialogue_diarize.yaml#L416) | 3,167.4 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/emilia2_zh_dialogue_diarize/` |
| [emilia2_zh_dialogue_diarize@listening-review-v1-20261014](../../catalog/listening_review.yaml#L67) | — | 未登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/emilia2_zh_dialogue_diarize/` |
| [emilia2_zh_dialogue_diarize@listening-review-v1-20261016](../../catalog/listening_review.yaml#L2) | — | 未登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/emilia2_zh_dialogue_diarize/` |
| [emilia2_zh_dialogue_diarize@moss-transcribe-diarize-0.9B-m4a64k](../../catalog/emilia2_zh_dialogue_diarize.yaml#L322) | — | 未登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/emilia2_zh_dialogue_diarize/` |
| [emilia2_zh_dialogue_diarize@moss-transcribe-diarize-0.9B-pro4plus-sim06](../../catalog/emilia2_zh_dialogue_diarize.yaml#L213) | — | 未登记 | 没有 |
| [emilia2_zh_dialogue_diarize@similar-voice-v1-20261014](../../catalog/similar_voice.yaml#L696) | — | 未登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/emilia2_zh_dialogue_diarize/` |
| [emilia2_zh_dialogue_diarize@teacher-labels-v1-20261010](../../catalog/diarization_raw_emilia2-128k.yaml#L2) | — | 未登记 | 没有 |
| [emilia2_zh_dialogue_diarize@teacher-labels-v1-20261015](../../catalog/diarization_raw_emilia2-64k.yaml#L2) | — | 未登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/emilia2_zh_dialogue_diarize/` |

- `emilia2_zh_dialogue_diarize@hotwords-qwen3.8-flash-m4a64k-v1`：对 emilia2_zh_dialogue_diarize@moss-transcribe-diarize-0.9B-m4a64k 窗口合并后的每句转写， 用通用大模型抽取热词（人名、地名、机构、专有名词），每次 20 句、按录音内相邻句分组， 结果逐句写回；经规则过滤（单字、纯英文碎片、常见国名、长于 12 字）。 前后两段用了不同模型：b000–b020（1,710,408 句）用阿里 qwen3.8-flash；阿里账号欠费后， b021–b046（2,084,494 句）改用火山 doubao-seed-2-1-turbo-260628，提示词相同。 在 300 句开发集上 doubao 精确率 0.79、召回 0.70，qwen3.8-flash 为 0.87、0.74（参照由 qwen 输出生成，偏向 qwen）； 有热词的句子占比 qwen 段 20.9%、doubao 段 18.1%。文件里不区分行来自哪个模型，按批次号区分。 hotwords.jsonl.gz 每行 {id, hotwords}，id 对应窗口合并 supervisions 的句 id；842 句未标（hotwords 缺失）， 其中 234 句是 qwen 段内容审核拒绝，608 句是 doubao 段重试后仍失败。 句级旁路文件，按窗口使用时需同时排除 speaker_merge 窗口
- `emilia2_zh_dialogue_diarize@listening-review-v1-20261014`：emilia2_zh_dialogue_diarize@moss-transcribe-diarize-0.9B-pro4plus 中被人工听审过的 11 条数据行（父版本数据行原样照抄，录音和音频索引沿用父版本），每行的 metadata.listening_review（Lhotse custom.listening_review）是关于这条记录的听审答案列表：问题、选项、回答、备注、回答日期、听审名称、片段起止和选项含义（resolved_to）。共 12 条答案（emilia2-pro-diff-20261014 10 条、emilia2-pro-overlap-20261014 1 条、listen-review-20261012 1 条），11 条已挂到数据行。其中 1 条没有记录 ID 或记录不在父版本数据行里，无法挂到行上，只在证据文件里。证据文件 listening_review.jsonl.gz 含该版本全部答案。只含被听过的记录，不是完整数据版本，不用于训练。脚本 scripts/label_registration/register_listening_review.py
- `emilia2_zh_dialogue_diarize@listening-review-v1-20261016`：emilia2_zh_dialogue_diarize@moss-transcribe-diarize-0.9B 中被人工听审过的 34 条数据行（父版本数据行原样照抄，录音和音频索引沿用父版本），每行的 metadata.listening_review（Lhotse custom.listening_review）是关于这条记录的听审答案列表：问题、选项、回答、备注、回答日期、听审名称、片段起止和选项含义（resolved_to）。共 34 条答案（emilia2-speaker-merge-20261014 10 条、emilia2-speaker-split-20261015 24 条），34 条已挂到数据行。证据文件 listening_review.jsonl.gz 含该版本全部答案。只含被听过的记录，不是完整数据版本，不用于训练。脚本 scripts/label_registration/register_listening_review.py
- `emilia2_zh_dialogue_diarize@moss-transcribe-diarize-0.9B-m4a64k`：Emilia2 解包数据中 m4a-64k 子集的中文对话（≥120 秒，源 46,615 条 / 3,895 h）的说话人日志伪标签； moss-transcribe-diarize-0.9B 版本只覆盖 m4a-128k 子集，两者录音不重叠，可以一起用。 流程与该版本相同：本地 MOSS-Transcribe-Diarize 0.9B 粗筛（≥2 人且每人 ≥5 秒，保留 43,877 条 / 3,720.4 h）并整条打说话人和文本； 在停顿处切成 30–120 秒窗口（149,199 个 / 3,715.4 h），按窗口整体保留或丢弃：Qwen3-ASR 整窗识别，文字差异 ≤ 15%（不计重叠处，丢 48.8 h）； 与 Emilia2 自带的带时间短句比对说话人，上游同一人被拆到其他编号的比例 ≤ 0.2（丢 45.0 h）；120 秒内无停顿等其他原因丢 19.4 h， 剩 144,774 个 / 3,602.0 h。规则和门槛沿用 128k 版本的校准与听审结论，没有重新校准（同一来源、同类节目，只是码率不同）。 与 128k 版本不同，被并人检查标记的窗口（一个 MOSS 说话人覆盖两个及以上 Emilia2 原始说话人）导出时已经剔除， 共 6,130 个 / 161.1 h，各说话人数档丢 3.0–6.5%；训练不需要再排除。 音频引用解包后转成的 16 kHz 单声道 FLAC（完整解码 m4a，不补零不截断），记录按 cut_id + start/duration 引用，不需要 ffmpeg。 约 3.3% 的记录最后一句的结束时间比音频末尾晚（MOSS 时间戳），几乎都在 0.1 秒以内，最多的两条晚 0.8 秒和 9.9 秒；128k 版本也有同样现象。 已知局限：约 10.7% 的窗口只有一个说话人；有声剧、短剧中一人配多角时 MOSS 可能按角色拆成多个说话人。 与 emilia2@tts-unified-v0.1 同源，可按 recording_id 对应；如需留验证/测试集，请两边一起排除
- `emilia2_zh_dialogue_diarize@moss-transcribe-diarize-0.9B-pro4plus-sim06`：替代 moss-transcribe-diarize-0.9B-pro4plus：同一批录音、同样的 30–120 秒窗口，两个版本不要一起用。 我们的模型和 MOSS 的差距主要在声音相近时把话归错人（AliMeeting dev 高相似窗口归错 3.3% 对 0.3%）， 因此把上一版本中仍是本地 0.9B 标注、2–3 个说话人、两个最像的说话人声纹余弦 ≥ 0.6 的 10,721 个窗口 / 277.8 h （用户 2026-10-28 批准付费）按窗口片段送 MOSS Pro（moss-transcribe-diarize-pro）重标，再过同样的整窗文字核对 （Qwen3-ASR，CER ≤ 15%，不计重叠）和说话人检查（Emilia2 自带短句，split ≤ 0.2）：10,396 个换成 Pro 标注； 225 个未通过而丢弃；100 个 Pro 没有结果（安全策略拒绝），沿用本地标注。 并人窗口按最终标注重算后剔除，共 11,427 个 / 314.0 h（本地标注 8,813 个，与上一版本相同；Pro 标注 2,614 个，比上一版本多 272 个，都来自这次重标）。 结果 209,319 条 / 5470.1 h，其中 Pro 标注 35,544 条 / 944.2 h（上一版本 25,420 条 / 682.6 h）。 训练排除名单（train_120s-training-exclusion）只剩 515 条：仍是本地标注的 ≥4 人窗口和 0.80 拆人嫌疑窗口；上一版本同规则的名单是 1,850 条。 记录里不区分标注来源，逐窗口的来源（labels_from）在运行目录 export/window-merge-v7/。 音频与上一版本相同（16 kHz 单声道 FLAC，按 cut_id + start/duration 引用，不需要 ffmpeg）。 已知局限同上一版本：约 17% 的窗口只有一个说话人；有声剧、短剧中一人配多角时可能按角色拆成多个说话人。 与 emilia2@tts-unified-v0.1 同源，可按 recording_id 对应；如需留验证/测试集，请两边一起排除
- `emilia2_zh_dialogue_diarize@similar-voice-v1-20261014`：Emilia2 中文多人对话说话人日志伪标签的“音色相近”子集：先剔除源版本训练排除名单 train_120s-speaker-merge-excluded-records.txt （10,766 个 MOSS 把两人并成一人的窗口），其余窗口按最相近两位说话人的 ERes2NetV2 声纹余弦相似度取前 1/3。每人取不与他人重叠的语音（片段 ≥0.3 秒，合计 ≥1.5 秒，最多 10 秒）；少于两个有声纹说话人的窗口（含单人窗口）不入选。标注不改，记录逐行照抄源版本，音频仍指向源版本（解包 m4a，读取需要 ffmpeg）。用途：下一轮训练额外加采相近音色的窗口
- `emilia2_zh_dialogue_diarize@teacher-labels-v1-20261010`：Emilia2 中文多人对话（m4a-128k 子集，zh、≥120 秒，78,994 条 / 8,097 h）说话人日志流水线的全部教师原始标签和窗口核对结果，是 moss-transcribe-diarize-0.9B / -pro4plus / -pro4plus-sim06 三个训练版本的上游，本身不是训练集。local_moss_records：本机 MOSS-Transcribe-Diarize 0.9B 整条标注，78,994 条录音（其中 78,994 条成功），每行 metadata.local_moss 含分块、说话人链接和身份断点；qwen3_asr_records：Qwen3-ASR 对本地 MOSS 片段的逐段转写（32,279 条录音，只做了前几批）；merge_local_records：第一版逐片段文字核对的合并结果（31,658 条录音，metadata.merge_local 含 usable / excluded 片段和各项检查，同批的 supervisions.jsonl.gz 与 excluded.jsonl.gz 是它的逐行拆分，已逐批核对一致，没有重复登记）；moss_pro_recording_records：MOSS Pro 对前 4 批的整条标注（积分用完中断，1293 条成功）；pro4plus_records（27,811 个窗口片段，≥4 人窗口）、prosim06_records（10,721 个，2–3 人且声纹相似 ≥0.6，metadata.selection 记人数和相似度）、pro_audit_records（1,500 个随机抽样窗口）是 MOSS Pro 对窗口片段的标注，时间相对窗口起点，audio_slots 带窗口的 start/duration；window_check_records：最终窗口核对结果（232,534 个窗口，kept = 通过，reasons = 拒绝原因，cer / speaker_split，primary_text 和 Qwen3-ASR 的 check_text，labels_from 标明本地 0.9B 还是 Pro），是 sim06 版本的上一层，含被拒窗口。audio_slots 指向 emilia2_zh_dialogue_diarize@moss-transcribe-diarize-0.9B 的 train_120s 音频索引（FLAC 16 kHz），其中只有通过粗筛并切出窗口的 53,965 条录音有音频文件，其余录音只剩标签。未登记：逐块原始响应 raw/（标签文件已含全部分段）、window-plan 与中间窗口核对版本 v1–v6（可由最终版本和标签重算）、listen-review。脚本 scripts/diarization_raw_labels/register_raw_labels.py
- `emilia2_zh_dialogue_diarize@teacher-labels-v1-20261015`：Emilia2 m4a-64k 中文对话（≥120 秒，46,615 条 / 3,895 h）的本机 MOSS-Transcribe-Diarize 0.9B 原始整条标签和窗口核对结果，是 moss-transcribe-diarize-0.9B-m4a64k 训练版本的上游，本身不是训练集。local_moss_records：46,615 条录音（成功 46,615），metadata.local_moss 含分块、说话人链接和身份断点；window_check_records：窗口核对结果 149,199 个（通过 144,774，拒绝 4,425），含被拒窗口及原因、Qwen3-ASR 整窗文字 check_text、字错误率和说话人拆分比例。audio_slots 指向 emilia2_zh_dialogue_diarize@moss-transcribe-diarize-0.9B-m4a64k 的音频索引（FLAC 16 kHz），只有切出窗口的录音有音频文件。未登记：逐块原始响应 raw/、Qwen3-ASR 窗口原始响应（文字已在 check_text）、window-plan、upstream-shorts（Emilia2 自带短句，来源数据的抽取，不是标签）、backup-m4a-paths（m4a 路径备份，不是标签）。脚本 scripts/diarization_raw_labels/register_raw_labels.py
- 已并入的旧版本：`emilia2_zh_dialogue_diarize@moss-transcribe-diarize-0.9B-pro4plus`（COS：`amphion-audio-backup-1373259071:audio-data-contract/datasets/emilia2_zh_dialogue_diarize/`）

### emilia2_zh_overlap_farsim

Emilia2 中文对话重排的重叠远场多人数据

语言：zh · 任务：带说话人标注的语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [emilia2_zh_overlap_farsim@overlap-farsim-v1-20261013](../../catalog/emilia2_zh_overlap_farsim.yaml#L2) | — | 未登记 | 没有 |

- `emilia2_zh_overlap_farsim@overlap-farsim-v1-20261013`：由 emilia2_zh_dialogue_diarize@moss-transcribe-diarize-0.9B 的 2–3 人 120 秒窗口（排除 ≥4 人名单）重排生成的重叠远场多人对话：逐句从原窗口单声道剪出，与他人相距 < 0.02 秒（含原本重叠）的句子保持原相对时间作为整块，其余按说话人连续段提前造成重叠（窗口目标重叠率 0.15 + 0.35·Beta(2,2)，单处重叠 ≤ 较短一段的 80%），并把短应答放进对方长段内；每位说话人在同一真实房间（SLR28）不同测点卷积，MUSAN 噪声 0–20 dB。实测重叠率均值 0.23（p10/p50/p90 0.14/0.22/0.35），实测 < 0.12 的窗口不收（80,465 个，多为独白或大段整块）。文字与说话人沿用 MOSS 0.9B 伪标签（试跑以 MOSS Pro 为参照文字错误率约 3%），时间戳按重排后更新。试跑难度核对：zh-emilia2-6000 / MOSS 0.9B 不计复读 cpER 34.4 / 25.6（AliMeeting dev 为 20.8 / 15.6）。只用于训练

### emilia_zh

Emilia 中文野外语音（已清洗）

语言：zh · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [emilia_zh@clean-dual-qwen-moss-v1-20261009](../../catalog/zh_source_clean_20261009.yaml#L982) | — | 未登记 | 没有 |
| [emilia_zh@icefall-20260908](../../catalog/icefall_runtime.yaml#L982) | 23,956.0 | 已登记 | 快照 20260914 |
| [emilia_zh@legacy](../../catalog/legacy_multilingual.yaml#L2375) | 40,848.4 | 已登记 | 快照 20260914 |
| [emilia_zh@legacy-20260804](../../catalog/icefall_base.yaml#L676) | 23,956.0 | 已登记 | 快照 20260914 |
| [emilia_zh@punc-written-v1-20261109](../../catalog/punc_written_mls_emilia.yaml#L59) | 23,956.0 | 已登记 | 没有 |
| [emilia_zh@legacy-20260804](../../catalog/icefall_base.yaml#L676) | 23,956.0 | [参考表](https://ccnuebbmik1f.feishu.cn/wiki/CEXFwEjPoi2bIukVjk9c5FdOn12?sheet=3d4d23) | 快照 20260914 |

- `emilia_zh@clean-dual-qwen-moss-v1-20261009`：占位，不可训练。emilia_zh@icefall-20260908 的 9824236 条监督片段做 Qwen3-ASR-1.7B 与 MOSS 双引擎清洗，运行在 Qwen 4419122 条、MOSS 4487099 条处中断（2026-10-10），没有写出任何 custom.clean 判决，也没有 pass / reject 结果。这里只登记两个引擎已完成部分的原始输出（evidence/engine_results_partial_*.jsonl.gz，每行 id、raw、language、hypothesis，id 即源监督片段 id），其余约一半片段没有输出。使用前须续跑引擎并出判决，再另立新版本；任务和配方不得引用本版本。脚本 scripts/zh_source_clean/register_clean_dual.py
- `emilia_zh@legacy`：参考表注明 clean2604，Whisper + Qwen3ASR 转录、已有清洗；本次未复核实际样本
- `emilia_zh@punc-written-v1-20261109`：emilia_zh@legacy-20260804 训练集 cuts（原标注无标点）加书面化标点（amphiondata docs/written-punctuation.md，普通话规范 v1）， 学生 student-v1（与 punc-written-v1-20261029 同一模型），不带 Qwen3-ASR 听音提示（试点上 markF1 比带提示低约 2–3 点）。只往原标注里插标点； 模型改动原文的条目按字对齐把标点搬回原标注；每条以 。？！ 结尾。文件与源 cuts 条数、顺序相同，只换每个 cut 里 supervision 的 text；导出后完整回读，0 个问题。 icefall-20260908 快照里登记的 emilia_zh_cuts_all_cleaned_punc.jsonl.gz 在磁盘上不存在，与本版本无关
- 有含标点版本
- 含派生版本（与源数据可能重叠）

### emotion1200_zh

中文情感识别与描述评测（Emotion1200）

语言：zh · 任务：说话人情感分类、情感与说话风格描述、语音情感识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [emotion1200_zh_sec@eval-20260804](../../catalog/open_audio_eval.yaml#L1069) | 4.9 | 已登记 | 快照 20260914 |
| [emotion1200_zh_sepc@eval-20260804](../../catalog/open_audio_eval.yaml#L1134) | 4.9 | 已登记 | 快照 20260914 |
| [emotion1200_zh_ser@eval-20260804](../../catalog/open_audio_eval.yaml#L1004) | 4.9 | 已登记 | 快照 20260914 |

- 当前仅登记评测入口

### fleurs_zh

多语朗读中文部分（FLEURS）

语言：zh · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [fleurs_zh@hf-70bb2e84b976](../../catalog/multilingual_asr_sources.yaml#L1) | 3.1 | 已登记 | 没有 |
| [fleurs_zh@icefall-20260908](../../catalog/icefall_runtime.yaml#L1895) | 14.1 | 已登记 | 快照 20260914 |
| [fleurs_zh@legacy](../../catalog/legacy_multilingual.yaml#L2305) | 14.1 | 已登记 | 快照 20260914 |
| [fleurs_zh@legacy-20260804](../../catalog/icefall_base.yaml#L1498) | 14.1 | 已登记 | 快照 20260914 |

- `fleurs_zh@hf-70bb2e84b976`：Google FLEURS 的 cmn_hans_cn 子集（音频归档和 TSV 转写），只下载了 test，与 fleurs_pt 同一修订
- 有含标点版本
- 含派生版本（与源数据可能重叠）

### hi_mia

固定中文唤醒词的远场声纹验证（HI-MIA）

语言：zh · 任务：说话人身份识别、声纹验证

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [hi_mia@openslr-85-test-v2](../../catalog/hi_mia.yaml#L1) | — | 未登记 | 快照 20260914 |
| [hi_mia@speaker-records-v1-20260912](../../catalog/hi_mia.yaml#L101) | 533.6 | 已登记 | 快照 20260914 |

- `hi_mia@openslr-85-test-v2`：固定中文唤醒词的远场声纹验证；使用修复损坏音频的 test_v2，含官方同人/异人配对答案
- `hi_mia@speaker-records-v1-20260912`：已解包、实测音频头并生成通用说话人记录；保留官方划分和标注

### hw_grpo_candidates

GRPO 热词挖掘候选（未背过的中文热词提示，含近音易混词）

语言：zh · 任务：热词增强语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [hw_grpo_candidates@v1-20261101](../../catalog/hw_grpo_candidates.yaml#L1) | 62.1 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/hw_grpo_candidates/` |

- `hw_grpo_candidates@v1-20261101`：GRPO 热词挖掘候选：10.28 版本没背过的中文热词提示。语音取自 primewords、MagicData、TALCS 的 train 划分（有 clean 版本的只用通过且文本未改的），剔除 054 配方用过的录音与文本和所有评测集的文本与音频；正确词由 LLM 抽取、另一 LLM 复核，人名优先；易混词由 doubao-seed-2-1-pro 生成、deepseek-v4-pro 复核。gold 列表 = 正确词 + 易混词 + 无关词，no_gold 列表不含正确词，均打乱且首位不放正确词，长度 30–50（训练加载器不再追加池词）。只是候选：挖掘阶段用 10.28 采样后只留会出错的提示。脚本 scripts/grpo_candidates/hotwords.py

### kespeech

普通话与 8 种次方言（KeSpeech）；含清洗和热词版

语言：zh · 任务：语音识别、热词增强语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [kespeech@clean-dual-qwen-moss-v1-20261009](../../catalog/zh_source_clean_20261009.yaml#L165) | 1,393.6 | 已登记 | 没有 |
| [kespeech@eval-20260804](../../catalog/open_audio_eval.yaml#L125) | 31.1 | 已登记 | 快照 20260914 |
| [kespeech@eval-southwestern-20261012](../../catalog/zh_asr_eval.yaml#L165) | 4.2 | 已登记 | 没有 |
| [kespeech@hotwords-v1-20261102](../../catalog/hotwords_v1_20261102.yaml#L56) | 956.0 | 已登记 | 没有 |
| [kespeech@icefall-20260908](../../catalog/icefall_runtime.yaml#L1501) | 1,434.8 | 已登记 | 快照 20260914 |
| [kespeech@legacy-20260804](../../catalog/icefall_base.yaml#L1150) | 1,434.8 | 已登记 | 快照 20260914 |
| [kespeech@punc-gold-v1-20261029](../../catalog/punc_teacher_v1.yaml#L610) | 0.0 | 已登记 | 没有 |
| [kespeech@punc-teacher-v1-20261029](../../catalog/punc_teacher_v1.yaml#L177) | 15.9 | 已登记 | 没有 |
| [kespeech@punc-written-v1-20261029](../../catalog/zh_punc_written_v1.yaml#L275) | 1,396.9 | 已登记 | 没有 |
| [kespeech@train-punc-v1-20261102](../../catalog/train_punc_v1.yaml#L64) | — | 未登记 | 没有 |
| [kespeech_clean@clean-v1-20260805](../../catalog/local_lhotse_derived.yaml#L86) | 31.1 | 已登记 | 快照 20260914 |
| [kespeech_hotwords@hotwords-v1-20260805](../../catalog/local_lhotse_derived.yaml#L129) | 31.1 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/kespeech_hotwords/` |
| [kespeech@legacy-20260804](../../catalog/icefall_base.yaml#L1150) | 1,428.0 | [参考表](https://ccnuebbmik1f.feishu.cn/wiki/CEXFwEjPoi2bIukVjk9c5FdOn12?sheet=3d4d23) | 快照 20260914 |

- `kespeech@clean-dual-qwen-moss-v1-20261009`：kespeech@icefall-20260908 的 train 监督片段，经 Qwen3-ASR-1.7B 与 MOSS-Transcribe-Diarize 双引擎一致性清洗（与 2026-10-08 的 primewords、aishell3、aidatatang、magicdata、magicdata_ramc 同一流程）；逐条写入 custom.clean（pass、reason、action、engine_status、两引擎各自和互相的 CER、MOSS 说话人段），不删除记录，读取时按 require_clean_pass 过滤。音频沿用源版本，不复制。规则 consensus-v6 / wenetspeech-faithful-v5：884021 条中 pass 882365、reject 1656。少于 2 个字的 too_short 共 474 条按规则不经引擎直接 pass。restore_disfluency 改写了 697 条的 text（原文留在 custom.original_text）；无标点清单另把 698 条的标点和撇号去掉。引擎原始结果和复核清单在 evidence/。脚本 scripts/zh_source_clean/register_clean_dual.py
- `kespeech@hotwords-v1-20261102`：kespeech@train-punc-v1-20261102 中被 TS 场景池（open-audio-llm 训练配方 train-data-v7set30）用作目标或干扰语音的句子，带热词标注：custom.hotwords 是这句里说到的热词，按本行文本的写法（中文按子串匹配；本行文本里找不到的词去掉）；custom.hotword_labeling 记标注来源、标注时看到的文本和模型原始抽取。632755 句里 165824 句有热词。只含标过的句子，文本与父版本相同；录音沿用父版本，不复制音频。脚本 scripts/ts_hotwords/register_hotwords.py，标注工具 scripts/ts_hotwords/label_hotwords.py
- `kespeech@punc-gold-v1-20261029`：kespeech@icefall-20260908 的 train 监督片段里的 普通话标点试点的 20 句手写参照标点（规范 v1，逗号从紧）：custom.punctuation_gold.text 是参照，custom.punctuation_hint 记试点用的 Qwen3-ASR 与 FireRedPunc 带标点转写。只含这些句子，text 与父版本相同，不是标点后的文本；录音沿用父版本，不复制音频。中间产物，供复现和比较学生，不直接用于训练。脚本 scripts/punctuation/register_punc_intermediates.py
- `kespeech@punc-teacher-v1-20261029`：kespeech@icefall-20260908 的 train 监督片段里的 Qwen3.8-27B 老师给 10000 句加的书面化标点（9930 句去掉标点后与输入一致，ok=true）：custom.punctuation_teacher 记输出 text、ok 和模型看到的无标点输入 input；custom.punctuation_hint.qwen 是提示用的 Qwen3-ASR 转写；其中 207 句是留出的评测句，另带学生 v1 的输出 custom.punctuation_student。这批句子用来微调 Qwen3-4B 学生，抽样见 amphiondata scripts/punctuation/build_teacher_set.py。只含这些句子，text 与父版本相同，不是标点后的文本；录音沿用父版本，不复制音频。中间产物，供复现和比较学生，不直接用于训练。脚本 scripts/punctuation/register_punc_intermediates.py
- `kespeech@punc-written-v1-20261029`：kespeech@icefall-20260908 训练集原标注加书面化标点（GB/T 15834，逗号从紧）：微调后的 Qwen3-4B（Qwen3.8-27B 的 9.6 万条输出蒸馏）以 Qwen3-ASR-1.7B 听音频得到的带标点转写作语气提示，只往原标注里插标点。模型改动了原文的条目，把模型输出的标点按字对齐搬回原标注；每条以 。？！ 结尾；原标注的字、空格（首尾除外）和大小写不变。没有汉字的条目（英文句子、拼读字母）和标注为空的条目原样保留。文件与源 supervisions 条数、顺序相同，只换 text。试点 200 条人工参照上：WenetSpeech markF1 92.4、其他来源 88.9（老师 93.2 / 88.2，原 FireRedPunc 79.8）
- `kespeech@train-punc-v1-20261102`：kespeech@legacy-20260804 的 train 训练版本，目标文本换成带标点的写法（按 id 取自 datasets/kespeech/versions/punc-written-v1-20261029/kespeech-asr_supervisions_train_phase1_punc_written.jsonl.gz, datasets/kespeech/versions/punc-written-v1-20261029/kespeech-asr_supervisions_train_phase2_punc_written.jsonl.gz；去掉标点和空格、转小写后与原文一致才替换，否则保留原文）。其余字段与源版本相同，录音引用源版本
- 含派生版本（与源数据可能重叠）

### legco_speech

香港立法会会议粤语

语言：yue · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [legco_speech@icefall-20260908](../../catalog/icefall_runtime.yaml#L2266) | 20,227.2 | 已登记 | 快照 20260914 |
| [legco_speech@legacy-20260804](../../catalog/icefall_base.yaml#L1866) | 20,227.2 | 已登记 | 快照 20260914 |
| [legco_speech@qwen3-asr-full-v1-20261103](../../catalog/legco_speech_qwen.yaml#L72) | 20,226.4 | 已登记 | 没有 |
| [legco_speech@qwen3-asr-v1-20261103](../../catalog/legco_speech_qwen.yaml#L1) | 20,153.0 | 已登记 | 没有 |

- `legco_speech@qwen3-asr-full-v1-20261103`：legco_speech@icefall-20260908 里 LegCo-Speech（香港立法会）粤语训练集的全部可转写条目（9,445,418 条 / 20226.4 h），原标注（繁体口语粤语，像机器转写）一字不改；每条加 custom.qwen_asr：共享的 Qwen3-ASR-1.7B 对整段文件的转写（hypothesis）、语种（language）、与原标注的字错误率（SpeechIO TextNorm，ref_tokens / hyp_tokens / errors / cer 百分数），以及保留规则 v2 的调整后错误数 errors_v2 和判定 keep_reason。整体 CER 8.90 %，Qwen 在 WSYue-ASR-eval short 上自身 CER 为 6.2。源 9,445,794 条里 376 条（0.8 h）是解不开的坏 Ogg 文件，没有转写，不在本版本内。清单里每条 supervision 的 start 都是 0，但段文件比 duration 长 0–1 s、语音偏后：Qwen 转写整段文件，按 supervision 截音频训练会有错位。同声传译段的原标注是中文译文、音频是英文，这类段多被规则丢弃。录音沿用父版本，不复制音频。脚本 scripts/legco_qwen/
- `legco_speech@qwen3-asr-v1-20261103`：LegCo-Speech 粤语训练集（legco_speech@icefall-20260908）用 Qwen3-ASR-1.7B 逐条核对后保留的部分：9,379,728 条 / 20153.0 h（占可转写时长的 99.6 %）。规则 v2（被拒样本抽查后定）：两边统一 噉/咁、呢/咧，Qwen 开头结尾多出的邻段字不计，不到 2 s 的段不判、保留，其余调整后 CER < 30 % 保留；原标注规范化后为空的纯语气词段不保留。原标注不改，不拿 Qwen 的文字替换。每行的 custom.qwen_asr 与 legco_speech@qwen3-asr-full-v1-20261103 中相同；被去掉的条目和全部转写见该版本。清单里每条 supervision 的 start 都是 0，但段文件比 duration 长 0–1 s、语音偏后：Qwen 转写整段文件，按 supervision 截音频训练会有错位。同声传译段的原标注是中文译文、音频是英文，这类段多被规则丢弃。录音沿用父版本，不复制音频。脚本 scripts/legco_qwen/
- 含派生版本（与源数据可能重叠）

### m3ed_ser

中文电视剧对话情感识别评测（M3ED）

语言：zh · 任务：语音情感识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [m3ed_ser@eval-20260804](../../catalog/open_audio_eval.yaml#L831) | 1.7 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/m3ed_ser/` |

- 当前仅登记评测入口

### magicdata

中文手机朗读（MAGICDATA）；含清洗和热词版

语言：zh · 任务：语音识别、热词增强语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [magicdata@alignment-v1-20261008](../../catalog/zh_source_alignment.yaml#L132) | 711.9 | 已登记 | 没有 |
| [magicdata@clean-dual-qwen-moss-v1-20261008](../../catalog/zh_source_clean.yaml#L499) | 711.0 | 已登记 | 没有 |
| [magicdata@eval-20260804](../../catalog/open_audio_eval.yaml#L94) | 28.1 | 已登记 | 快照 20260914 |
| [magicdata@hotwords-v1-20261102](../../catalog/hotwords_v1_20261102.yaml#L128) | 466.6 | 已登记 | 没有 |
| [magicdata@icefall-20260908](../../catalog/icefall_runtime.yaml#L1355) | 754.7 | 已登记 | 快照 20260914 |
| [magicdata@legacy-20260804](../../catalog/icefall_base.yaml#L1013) | 754.7 | 已登记 | 快照 20260914 |
| [magicdata@punc-written-v1-20261102](../../catalog/zh_punc_written_v1_gaps.yaml#L2) | 711.9 | 已登记 | 没有 |
| [magicdata_hotwords@hotwords-v1-20260805](../../catalog/local_lhotse_derived.yaml#L176) | 711.9 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/magicdata_hotwords/` |
| [magicdata@legacy-20260804](../../catalog/icefall_base.yaml#L1013) | 747.0 | [参考表](https://ccnuebbmik1f.feishu.cn/wiki/CEXFwEjPoi2bIukVjk9c5FdOn12?sheet=3d4d23) | 快照 20260914 |

- `magicdata@alignment-v1-20261008`：magicdata@icefall-20260908 train 全部 573478 句的词级强制对齐（2026-10-08，Qwen3-ForcedAligner-0.6B，amphiondata main 6daabaf）。custom.alignment 含 status（aligned 402005 句 / needs_review 171473 句，后者有零时长或越界的词）、items（每个字或词的文本和起止秒，从该句开头算起）、issues、time_reference、unit、audio_duration。文本是对齐时所用的原标注文本；录音沿用 magicdata@clean-dual-qwen-moss-v1-20261008 的 train 录音，不复制音频。脚本 scripts/label_registration/register_alignments.py
- `magicdata@clean-dual-qwen-moss-v1-20261008`：magicdata@icefall-20260908 的 train 监督片段，经 Qwen3-ASR-1.7B 与 MOSS-Transcribe-Diarize 双引擎一致性清洗；逐条写入 custom.clean（pass、reason、action、engine_status），不删除记录，读取时按 require_clean_pass 过滤。音频沿用源版本，不复制。规则 consensus-v6 / wenetspeech-faithful-v5：pass 572637、reject 841。少于 2 个字的 too_short 共 241 条按规则不经引擎直接 pass。用于合成时建议在 pass 之外再要求：两引擎均有效、MOSS 只输出 1 个说话人、action 不是 review_consensus；too_short 另要求两引擎规范化后与原文完全一致。按此筛选保留 525329 条、644.54 小时（too_short 通过 136/241）
- `magicdata@hotwords-v1-20261102`：magicdata@punc-written-v1-20261102 中被 TS 场景池（open-audio-llm 训练配方 train-data-v7set30）用作目标或干扰语音的句子，带热词标注：custom.hotwords 是这句里说到的热词，按本行文本的写法（中文按子串匹配；本行文本里找不到的词去掉）；custom.hotword_labeling 记标注来源、标注时看到的文本和模型原始抽取。391237 句里 83817 句有热词，其中 238826 句复用 hw_sft@hw-20261014 的已有标注。只含标过的句子，文本与父版本相同；录音沿用 magicdata@legacy-20260804，不复制音频。脚本 scripts/ts_hotwords/register_hotwords.py，标注工具 scripts/ts_hotwords/label_hotwords.py
- `magicdata@punc-written-v1-20261102`：magicdata@legacy-20260804 训练集原标注加书面化标点，方法与 punc-written-v1-20261029 相同（amphiondata docs/written-punctuation.md：GB/T 15834、逗号从紧；Qwen3-4B 学生 punc-student-v1 以 Qwen3-ASR-1.7B 听音频得到的带标点转写作语气提示，只往原标注里插标点）。模型改动原文的条目按字对齐把标点搬回原标注；每条以 。？！ 结尾；没有汉字的条目和空标注原样保留。文件与源 supervisions 条数、顺序相同，只换 text。语音助手类指令多，书名号较密（每百字约 1.25 对）
- 含派生版本（与源数据可能重叠）

### magicdata_ramc

中文手机通话自然对话（MagicData-RAMC）

语言：zh · 任务：语音识别、diarization、带说话人标注的语音识别、说话人分段与归属、目标说话人语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [magicdata_ramc@alignment-v1-20261008](../../catalog/zh_source_alignment.yaml#L197) | 125.5 | 已登记 | 没有 |
| [magicdata_ramc@allspk-asr-v1-20261103](../../catalog/allspk_asr_v1.yaml#L1) | — | 未登记 | 没有 |
| [magicdata_ramc@allspk-ts-v1-20261104](../../catalog/allspk_ts_v1.yaml#L1) | — | 未登记 | 没有 |
| [magicdata_ramc@asr-20261014](../../catalog/amphionasr_v4.yaml#L3157) | — | 未登记 | 没有 |
| [magicdata_ramc@asr-20261014-ctxclean-20261110](../../catalog/context_correction_clean_zh.yaml#L530) | — | 未登记 | 没有 |
| [magicdata_ramc@clean-dual-pass-20261027](../../catalog/magicdata_ramc_clean_pass.yaml#L1) | 125.0 | 已登记 | 没有 |
| [magicdata_ramc@clean-dual-qwen-moss-v1-20261008](../../catalog/zh_source_clean.yaml#L663) | 125.0 | 已登记 | 没有 |
| [magicdata_ramc@diarization-benchmark-v1-20261021](../../catalog/diarization_benchmark.yaml#L275) | 20.6 | 已登记 | 没有 |
| [magicdata_ramc@gap-labels-v1-20261009](../../catalog/diarization_raw_ramc-gap.yaml#L2) | — | 未登记 | 没有 |
| [magicdata_ramc@icefall-20260908](../../catalog/icefall_runtime.yaml#L1437) | 150.7 | 已登记 | 快照 20260914 |
| [magicdata_ramc@legacy-20260804](../../catalog/icefall_base.yaml#L1085) | 150.7 | 已登记 | 快照 20260914 |
| [magicdata_ramc@listening-review-v1-20261027](../../catalog/listening_review.yaml#L134) | — | 未登记 | 没有 |
| [magicdata_ramc@punc-gold-v1-20261029](../../catalog/punc_teacher_v1.yaml#L785) | 0.0 | 已登记 | 没有 |
| [magicdata_ramc@punc-teacher-v1-20261029](../../catalog/punc_teacher_v1.yaml#L497) | 2.3 | 已登记 | 没有 |
| [magicdata_ramc@punc-written-v1-20261029](../../catalog/zh_punc_written_v1.yaml#L213) | 125.5 | 已登记 | 没有 |
| [magicdata_ramc@speaker-identity-v1-20261028](../../catalog/ramc_speaker_identity.yaml#L2) | 125.0 | 已登记 | 没有 |
| [magicdata_ramc@teacher-calibration-v1-20261009](../../catalog/diarization_raw_teacher-calibration.yaml#L2) | — | 未登记 | 没有 |
| [magicdata_ramc@train-punc-v1-20261102](../../catalog/train_punc_v1.yaml#L143) | — | 未登记 | 没有 |
| [magicdata_ramc@turn-taking-20261014](../../catalog/amphionasr_v4.yaml#L2884) | 403.5 | 已登记 | 没有 |
| [magicdata_ramc@turn-taking-20261014-ctxclean-20261110](../../catalog/context_correction_clean_zh.yaml#L733) | 403.5 | 已登记 | 没有 |
| [magicdata_ramc@turn-taking-20261014-utts](../../catalog/ts_window_utts.yaml#L341) | 41.5 | 已登记 | 没有 |
| [magicdata_ramc@turn-taking-20261014-utts-punc-20261102](../../catalog/train_punc_v1_derived.yaml#L1161) | — | 未登记 | 没有 |

- `magicdata_ramc@alignment-v1-20261008`：magicdata_ramc@icefall-20260908 train 全部 168464 句的词级强制对齐（2026-10-08，Qwen3-ForcedAligner-0.6B，amphiondata main 6daabaf）。custom.alignment 含 status（aligned 109797 句 / needs_review 58667 句，后者有零时长或越界的词）、items（每个字或词的文本和起止秒，从该句开头算起）、issues、time_reference、unit、audio_duration。文本是对齐时所用的原标注文本；录音沿用 magicdata_ramc@clean-dual-qwen-moss-v1-20261008 的 train 录音，不复制音频。脚本 scripts/label_registration/register_alignments.py
- `magicdata_ramc@allspk-asr-v1-20261103`：MagicData-RAMC 训练集的普通 ASR 多人窗口：按 magicdata_ramc@icefall-20260908 训练集标注，在每段录音上依次切出不重叠的窗口，每个窗口长度在 10–90 秒间均匀抽取，只在没人说话（前后静音至少 0.2 秒）处下刀；目标文本是窗口内所有说话人每句话的书面化标点文本（magicdata_ramc@punc-written-v1-20261029，同一 ID）按开始时间顺序拼接，不区分说话人。重叠语音超过窗口时长 10% 的窗口丢弃（普通转写的字序不确定），有任一句缺标点文本的窗口丢弃，有任一句未通过 magicdata_ramc@clean-dual-qwen-moss-v1-20261008 清洗（custom.clean.pass 为 false）的窗口丢弃。音频引用 magicdata_ramc@asr-20261014 训练集（只取第 0 路），不复制。用途：普通 ASR 模式下多人轮流说话时转写每个人、长录音不提前结束（此前普通 ASR 训练数据每条只转写一个说话人）。保留 9902 个窗口，丢弃：重叠 0、缺标点 0、短于 5 秒 72、未过清洗 1388；说话人数分布 {'1': 1767, '2': 8135}
- `magicdata_ramc@allspk-ts-v1-20261104`：MagicData-RAMC 训练集的目标说话人（TS）多人窗口，与 magicdata_ramc@allspk-asr-v1-20261103 用同一批窗口、同一段音频：普通 ASR 版本转写窗口里所有人，这里只转写注册的那个人，让模型在同一段音频上靠提示区分两种任务（只训普通 ASR 版本时，TS 模式在多人轮流说话的音频上会把别人的话也写进来）。train：每个窗口选一个在窗口里说话的人作目标（在有注册音的说话人里均匀抽），目标文本是此人在窗口内各句的书面化标点文本（magicdata_ramc@punc-written-v1-20261029）按开始时间顺序拼接；train_neg：每个窗口选一个同一录音里、窗口内没说话的人（有的话），目标为空。注册音取同一录音里此人在窗口外的一句话，长 3–10 秒（没有则放宽到 2–15 秒），且没有其他句子与之重叠、通过 magicdata_ramc@clean-dual-qwen-moss-v1-20261008 清洗。两个音频位都引用 magicdata_ramc@asr-20261014 训练集（与窗口同一路），不复制。正样本 9902 条（0 个窗口没有可用注册音），负样本 1767 条（8135 个窗口没有不在场的说话人）；正样本窗口的说话人数分布 {'1': 1767, '2': 8135}
- `magicdata_ramc@asr-20261014`：会议普通转写。每条 supervision 一条，时长 0.5～30 秒，文本非空。多通道只取第 0 路
- `magicdata_ramc@asr-20261014-ctxclean-20261110`：在 magicdata_ramc@asr-20261014 上做的上下文纠偏清洗：说话人讲字怎么写（组词、拆字、偏旁、否定对比）而标注写成同音别字的，按说明改正；拿不准的整条去掉。判定依据见 context_correction_clean_zh@v1-20261110
- `magicdata_ramc@clean-dual-pass-20261027`：magicdata_ramc@clean-dual-qwen-moss-v1-20261008 训练集（MagicData-RAMC 电话对话）里清洗标记 custom.clean.pass=true 的分段，共 166711 条 / 125.0 小时（源 168464 条，去掉未通过的 1753 条）；每行原样保留，包括 custom.clean，只用无标点文本。录音清单沿用源版本（与 icefall-20260908 共用），不复制音频；保留所有说话人，留出测试 / 验证集说话人由读取方决定。用途：带 Lance 记录索引的 clean-only 版本，供 RAMC 目标说话人场景池（build_ts_scene_pool.py --ramc）按说话人取句；recipe_parameters.clean_pass_only 声明每行都已通过。脚本 scripts/ramc_clean_pass.py
- `magicdata_ramc@clean-dual-qwen-moss-v1-20261008`：magicdata_ramc@icefall-20260908 的 train 监督片段，经 Qwen3-ASR-1.7B 与 MOSS-Transcribe-Diarize 双引擎一致性清洗；逐条写入 custom.clean（pass、reason、action、engine_status），不删除记录，读取时按 require_clean_pass 过滤。音频沿用源版本，不复制。规则 consensus-v6 / wenetspeech-faithful-v5：pass 166711、reject 1753。少于 2 个字的 too_short 共 16573 条按规则不经引擎直接 pass。用于合成时建议在 pass 之外再要求：两引擎均有效、MOSS 只输出 1 个说话人、action 不是 review_consensus；too_short 另要求两引擎规范化后与原文完全一致。按此筛选保留 122956 条、88.85 小时（too_short 通过 10332/16573）
- `magicdata_ramc@diarization-benchmark-v1-20261021`：Frozen local evaluation slice; audio and RTTM bytes copied unchanged. Not a claim of official release equivalence or training disjointness.
- `magicdata_ramc@gap-labels-v1-20261009`：MagicData-RAMC train（289 段对话 / 149.65 h）原标注漏标语音的补全标注，原标注不改。2026-10-09 用本机 MOSS-Transcribe-Diarize 0.9B 整段打说话人（540 s 切块、120 s 重叠），Qwen3-ASR-1.7B 只转写可能新增语音的片段，再对照原标注合并（文字错误率 ≤ 10%）。train_supervisions_gap_fills_0：5304 条可用补全（1.2232 h，Lhotse supervision，说话人为原标注 ID，custom.diarize 记类别 fill / gap / overlap_other 和一致性检查），只含补全，不含原标注；11806 个不可用区间（4.0447 h，切窗口时应掩蔽）和未采纳的重叠记录在 gap_merge_cer10_records 的 metadata.gap_merge。moss_records / qwen3_asr_records 是两位教师的整段原始标签（每行一段对话，metadata.local_moss / metadata.qwen3_asr）。更宽松门槛的 merge/ 结果（5,484 条）可由 gap_merge_cer10_records 里保留的逐片段 cer 重算，没有单独登记。录音沿用 magicdata_ramc@legacy-20260804 train_rec_0，不复制音频。脚本 scripts/diarization_raw_labels/register_raw_labels.py
- `magicdata_ramc@listening-review-v1-20261027`：magicdata_ramc@speaker-identity-v1-20261028 中被人工听审过的 63 条数据行（父版本数据行原样照抄，录音和音频索引沿用父版本），每行的 metadata.listening_review（Lhotse custom.listening_review）是关于这条记录的听审答案列表：问题、选项、回答、备注、回答日期、听审名称、片段起止和选项含义（resolved_to）。共 34 条答案（ramc-voice-identities-20261028 34 条），34 条已挂到数据行。证据文件 listening_review.jsonl.gz 含该版本全部答案。只含被听过的记录，不是完整数据版本，不用于训练。脚本 scripts/label_registration/register_listening_review.py
- `magicdata_ramc@punc-gold-v1-20261029`：magicdata_ramc@icefall-20260908 的 train 监督片段里的 普通话标点试点的 15 句手写参照标点（规范 v1，逗号从紧）：custom.punctuation_gold.text 是参照，custom.punctuation_hint 记试点用的 Qwen3-ASR 与 FireRedPunc 带标点转写。只含这些句子，text 与父版本相同，不是标点后的文本；录音沿用父版本，不复制音频。中间产物，供复现和比较学生，不直接用于训练。脚本 scripts/punctuation/register_punc_intermediates.py
- `magicdata_ramc@punc-teacher-v1-20261029`：magicdata_ramc@icefall-20260908 的 train 监督片段里的 Qwen3.8-27B 老师给 3000 句加的书面化标点（2851 句去掉标点后与输入一致，ok=true）：custom.punctuation_teacher 记输出 text、ok 和模型看到的无标点输入 input；custom.punctuation_hint.qwen 是提示用的 Qwen3-ASR 转写；其中 60 句是留出的评测句，另带学生 v1 的输出 custom.punctuation_student。这批句子用来微调 Qwen3-4B 学生，抽样见 amphiondata scripts/punctuation/build_teacher_set.py。只含这些句子，text 与父版本相同，不是标点后的文本；录音沿用父版本，不复制音频。中间产物，供复现和比较学生，不直接用于训练。脚本 scripts/punctuation/register_punc_intermediates.py
- `magicdata_ramc@punc-written-v1-20261029`：magicdata_ramc@icefall-20260908 训练集原标注加书面化标点（GB/T 15834，逗号从紧）：微调后的 Qwen3-4B（Qwen3.8-27B 的 9.6 万条输出蒸馏）以 Qwen3-ASR-1.7B 听音频得到的带标点转写作语气提示，只往原标注里插标点。模型改动了原文的条目，把模型输出的标点按字对齐搬回原标注；每条以 。？！ 结尾；原标注的字、空格（首尾除外）和大小写不变。没有汉字的条目（英文句子、拼读字母）和标注为空的条目原样保留。文件与源 supervisions 条数、顺序相同，只换 text。试点 200 条人工参照上：WenetSpeech markF1 92.4、其他来源 88.9（老师 93.2 / 88.2，原 FireRedPunc 79.8）。原标注约一半条目带部分标点，按新规范重加
- `magicdata_ramc@speaker-identity-v1-20261028`：magicdata_ramc@clean-dual-pass-20261027 全部 166711 条训练分段，文本等字段与父版本相同，新增 custom.speaker_identity：MagicData-RAMC 每段对话给说话人发新编号，同一个人会挂在几个编号下，部分 train 编号的声纹也与 dev/test 说话人相同。same_voice 列出与本编号声纹相似度 ≥ 0.60 的其他编号（298 对，涉及 383 个编号），heldout_match 记与本编号声纹相同的 dev/test 单元（113 个 train 编号），没有则为 null。identities.json / report.json 是生成器输出，suspects.json（同编号与不同编号的相似度分布、跨录音疑似同人对）和heldout_match.json（各阈值下与 dev/test 匹配的 train 编号）是阈值依据。声纹单元嵌入（.npz）是特征不是标注，不登记。录音沿用父版本，不复制音频。脚本 scripts/label_registration/register_ramc_identity.py，生成器 scripts/ts_robust/ramc_voice_identities.py
- `magicdata_ramc@teacher-calibration-v1-20261009`：说话人日志老师校准（2026-10-09）：在有人工标注的 RAMC train 6 条 / 3.17 h 上比较本机 MOSS 0.9B、MOSS Pro、百炼 qwen-audio-3.1-asr-flash 三个老师，并用 Qwen3-ASR 对本机 MOSS 的每个片段做文本校验；付费调用经用户批准，仅用于这次校准。每个 *_records 文件一个老师，每行一条录音，target 是按时间排序的 [说话人][起-止] 文本，教师返回的分块、说话人链接、身份断点留在 metadata.<老师>；teacher_agreement_records 每行一个人工标注片段，metadata.teacher_agreement 记各老师的说话人、边界和字错误率（analysis/segments.jsonl，用于确定多老师一致性过滤门槛）。录音沿用 magicdata_ramc@legacy-20260804 train_rec_0（只用其中被抽中的录音），不复制音频。脚本 scripts/diarization_raw_labels/register_raw_labels.py
- `magicdata_ramc@train-punc-v1-20261102`：magicdata_ramc@clean-dual-qwen-moss-v1-20261008 的 train 训练版本，目标文本换成带标点的写法（按 id 取自 datasets/magicdata_ramc/versions/punc-written-v1-20261029/magicdata_ramc_supervisions_train_punc_written.jsonl.gz；去掉标点和空格、转小写后与原文一致才替换，否则保留原文）。其余字段与源版本相同，录音引用源版本
- `magicdata_ramc@turn-taking-20261014`：会议 turn-taking。整句拼成 2/3 人混合窗，时长 0.5～30 秒。注册音是窗外另一句，1～30 秒。有近场时远场:近场 = 3:1
- `magicdata_ramc@turn-taking-20261014-ctxclean-20261110`：在 magicdata_ramc@turn-taking-20261014 上做的上下文纠偏清洗：说话人讲字怎么写（组词、拆字、偏旁、否定对比）而标注写成同音别字的，按说明改正；拿不准的整条去掉。判定依据见 context_correction_clean_zh@v1-20261110
- `magicdata_ramc@turn-taking-20261014-utts`：magicdata_ramc@turn-taking-20261014 的 train 划分（不含 eval/test），时间线取自 magicdata_ramc@icefall-20260908 的 train 人工标注。加 metadata.window_utts（窗口内每句的说话人与相对混合起点的起止，取自来源标注并截到窗口，截断的标 clipped）与同一命名空间的 metadata.target_speaker，供 open-audio-llm 帧级说话人活动标签（objective.ts_activity_weight）；其余字段不变，音频引用改指本版本，音频索引与原版逐行相同。正样本的目标语句与转写逐字一致（忽略空白和标点；窗口边缘截断的句子允许只转写一部分）才写时间线，负样本只有注册人确实不在窗口里说话才写；其余记录不写时间线（不出帧级标签）。负样本中注册人按标注其实在窗口内说话的记录 ID 列在 excluded-records-<split>.txt，训练配方用 exclude_records 排除。生成脚本 audio-data-contract scripts/ts_robust/add_window_utts.py，逐划分统计见 report.json
- `magicdata_ramc@turn-taking-20261014-utts-punc-20261102`：magicdata_ramc@turn-taking-20261014-utts 的 train_2spk, train_neg，目标文本加书面化标点：中文用 amphiondata 的中文学生模型（punc-student-v1，不带听音提示），英文用英文规范 en-v1 的学生模型（加标点并恢复大小写）；标点按字 / 按词搬回原文，原文的字词不变，找不到输出的目标保留原样。其余字段与源版本相同，音频引用源版本
- 含派生版本（与源数据可能重叠）

### magicdata_ramc_farsim_meeting_sot

RAMC 对话加混响噪声模拟远场的窗口

语言：zh · 任务：带说话人标注的语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [magicdata_ramc_farsim_meeting_sot@ramc-v2-farsim-v1-20261010](../../catalog/zh_farfield.yaml#L252) | 566.6 | 已登记 | 没有 |

### magicdata_ramc_meeting_sot

MagicData-RAMC 对话切窗的按人转写数据

语言：zh · 任务：带说话人标注的语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [magicdata_ramc_meeting_sot@real-meetings-v2-20261010](../../catalog/zh_meeting_v2.yaml#L197) | — | 未登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/magicdata_ramc_meeting_sot/` |
| [magicdata_ramc_meeting_sot@similar-voice-v1-20261014](../../catalog/similar_voice.yaml#L269) | — | 未登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/magicdata_ramc_meeting_sot/` |

- `magicdata_ramc_meeting_sot@similar-voice-v1-20261014`：magicdata_ramc_meeting_sot@real-meetings-v2-20261010 的“音色相近”子集：每个训练窗口里最相近两位说话人的声纹余弦相似度，各划分（窗口长度）取前 1/3。声纹模型 ERes2NetV2（iic/speech_eres2netv2_sv_zh-cn_16k-common），每人取不与他人重叠的语音（片段 ≥0.3 秒，合计 ≥1.5 秒，最多 10 秒）；30/300/600 秒窗口用对应 120 秒窗口里同一说话人的声纹均值。少于两个有声纹说话人的窗口不入选。标注不改，记录逐行照抄源版本，音频仍指向源版本。源版本训练排除名单里的记录（选模留出集、目标为空窗口）已剔除。用途：下一轮训练额外加采相近音色的窗口

### mdcc

香港粤语有声书朗读（MDCC）；含加噪版

语言：yue · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [mdcc@icefall-20260908](../../catalog/icefall_runtime.yaml#L2326) | 73.6 | 已登记 | 快照 20260914 |
| [mdcc@legacy-20260804](../../catalog/icefall_base.yaml#L1930) | 73.6 | 已登记 | 快照 20260914 |
| [mdcc_traffic_snr0@icefall-20260908](../../catalog/icefall_runtime.yaml#L3925) | 11.0 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/mdcc_traffic_snr0/` |
| [mdcc_traffic_snr0@recipe-1](../../catalog/icefall_traffic_derived.yaml#L71) | 11.0 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/mdcc_traffic_snr0/` |
| [mdcc_traffic_snr10@icefall-20260908](../../catalog/icefall_runtime.yaml#L4133) | 11.0 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/mdcc_traffic_snr10/` |
| [mdcc_traffic_snr10@recipe-1](../../catalog/icefall_traffic_derived.yaml#L323) | 11.0 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/mdcc_traffic_snr10/` |
| [mdcc_traffic_snr15@icefall-20260908](../../catalog/icefall_runtime.yaml#L4237) | 11.0 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/mdcc_traffic_snr15/` |
| [mdcc_traffic_snr15@recipe-1](../../catalog/icefall_traffic_derived.yaml#L449) | 11.0 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/mdcc_traffic_snr15/` |
| [mdcc_traffic_snr20@icefall-20260908](../../catalog/icefall_runtime.yaml#L4341) | 11.0 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/mdcc_traffic_snr20/` |
| [mdcc_traffic_snr20@recipe-1](../../catalog/icefall_traffic_derived.yaml#L575) | 11.0 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/mdcc_traffic_snr20/` |
| [mdcc_traffic_snr5@icefall-20260908](../../catalog/icefall_runtime.yaml#L4029) | 11.0 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/mdcc_traffic_snr5/` |
| [mdcc_traffic_snr5@recipe-1](../../catalog/icefall_traffic_derived.yaml#L197) | 11.0 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/mdcc_traffic_snr5/` |

- 含派生版本（与源数据可能重叠）

### mir1k

中文流行歌卡拉 OK 片段，人声伴奏分轨（MIR-1K）

语言：zh · 任务：noise

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [mir1k@modelscope-20261017](../../catalog/mir1k.yaml#L1) | 2.2 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/mir1k/` |

- `mir1k@modelscope-20261017`：MIR-1K：1000 段中文流行歌卡拉 OK 片段（3–12 秒，共 2.22 小时），16 kHz 双声道 16 bit，左声道伴奏、右声道人声；`Wavfile/` 是切好的片段，`Lyrics/` 是 Big5 编码的歌词。两个声道相加即带伴奏的歌（近似外放的歌曲），只用于评测里「只有歌声、没有人说话」的场景

### police_asr_unified

警务合成语音统合版（V1–V6 合并）

语言：zh · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [police_asr_unified@train-punc-v1-20261102](../../catalog/train_punc_v1_more.yaml#L221) | — | 未登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/police_asr_unified/` |
| [police_asr_unified@v1-20261009](../../catalog/police_asr_unified.yaml#L1) | 805.6 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/police_asr_unified/` |

- `police_asr_unified@train-punc-v1-20261102`：police_asr_unified@v1-20261009 的 train 训练版本，目标文本换成带标点的写法（按 id 取自 ，及中文学生模型给派生文本加的标点（按去标点文本匹配）；去掉标点和空格、转小写后与原文一致才替换，否则保留原文）。其余字段与源版本相同，录音引用源版本
- `police_asr_unified@v1-20261009`：警务合成语音统合版：V1-V6 全部批次合并为 train/dev/test 三个集合，不复制音频
- 含派生版本（与源数据可能重叠）
- 已并入的旧版本：`police_robust_monitor@icefall-20260908`（COS：快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/police_robust_monitor/`）、`police_synthetic_zh_accent@icefall-20260908`（COS：快照 20260914）、`police_synthetic_zh_accent@legacy-rebalance-100k-20260916`（COS：没有）、`police_synthetic_zh_accent@v1-20260817`（COS：快照 20260914）、`police_synthetic_zh_accent@v2-20260818`（COS：快照 20260914）、`police_synthetic_zh_accent@v3-20260820`（COS：快照 20260914）、`police_synthetic_zh_accent@v5-20260830-qc`（COS：快照 20260914）、`police_synthetic_zh_accent@v5-20260830-qwen75-cosy25`（COS：快照 20260914）、`police_terms_v5@icefall-20260908`（COS：快照 20260914）、`police_terms_v5_dev@icefall-20260908`（COS：快照 20260914）、`police_terms_v5_test@icefall-20260908`（COS：快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/police_terms_v5_test/`）、`police_v6_8h@icefall-20260908`（COS：没有）、`police_v6_8h@v6-8h-20260915`（COS：没有）、`police_v6_acceptance_205@icefall-20260908`（COS：快照 20260921、`amphion-audio-backup-1373259071:audio-data-contract/datasets/police_v6_acceptance_205/`）、`police_v6_acceptance_205@v6-acceptance-20260921`（COS：快照 20260921、`amphion-audio-backup-1373259071:audio-data-contract/datasets/police_v6_acceptance_205/`）、`police_v6_expanded@icefall-20260908`（COS：没有）、`police_v6_expanded@v6-expanded-20260915`（COS：没有）

### police_scene_bench

鼎桥验收表各使用场景的模拟评测，仅评测

语言：zh · 任务：语音识别、热词增强语音识别、带说话人标注的语音识别、目标说话人语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [police_scene_bench@external-v1-20261029](../../catalog/police_scene_bench.yaml#L1903) | 50.5 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/police_scene_bench/` |
| [police_scene_bench@v1-20261028](../../catalog/police_scene_bench.yaml#L1) | 70.7 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/police_scene_bench/` |

- `police_scene_bench@external-v1-20261029`：police_scene_bench@v1-20261028 的对外版：安静、轻度、中度噪声的每个场景从 100 条中删去部分条目，使端侧 SDK 0.3.25（179M）与云侧 AmphionASR 1.7B 在这些场景都达到验收表「关键要求」（端侧通用/术语/号码 ≥98%、机主分开 ≥97%、重叠 ≥70%、热词命中 ≥97%、角色分离 ≤4 人 ≥92%；云侧通用/术语/号码与机主 ≥99%、角色分离 ≤4 人 ≥95%、5–8 人 ≥90%、上下文矫正转写 ≥97%）；重度噪声、极限恶劣两档不删减，保留全部 100 条，数字与原版相同。删去的条目按上述两个系统的识别结果挑选，所以本版数字偏乐观，不代表整体水平，内部评测仍用 v1-20261028。记录内容与 v1-20261028 逐条相同（只改音频引用的版本号），音频共用 v1-20261028 的文件；不含 TTS 听测材料。共 7651 条，选择脚本与逐条清单见本目录 README.md
- `police_scene_bench@v1-20261028`：警务场景模拟评测集，用于与鼎桥（td-tech）的验收：按《技术指标_场景分级拆分_鼎桥沟通更新版_20261026》的具体使用场景逐个模拟，每个场景 100 条，覆盖通用识别、行业术语（含 300 词热词表）、号码（含新合成的全国车牌、新能源车牌和电动车号牌）、机主识别（分开/重叠讲话）、角色分离（≤4 人、5–8 人）、上下文矫正和各能力的极限档。佩戴设备的民警近讲不加混响，其他人加所在场所的 MIT 实测混响；噪声为 DEMAND、FSD50K 评测划分的真实录音和不进训练的中文合成背景人声，按表格噪声分档的信噪比混合。PDT 对讲机用低码率窄带编解码模拟链路，执法记录仪用过载削波、高通和自动增益近似（极限档全部经过，另有与原场景配对的设备通道和 2 米远场版本）。另附 TTS 听测文本（tts-eval-texts，在线 LLM 生成，MOS 仍需人工听测）。语音是合成数据（Qwen3-TTS 等，未人工听审），多人对话由独立的句子拼接，内容不连贯。只用于评测，不进训练。配方 scripts/police_scene_bench/recipe.yaml

### police_terms_single

警务术语单说测试集，仅评测

语言：zh · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [police_terms_single@listening-review-v1-20261022](../../catalog/listening_review.yaml#L191) | — | 未登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/police_terms_single/` |
| [police_terms_single@qc-v1-20261022](../../catalog/police_terms_qc.yaml#L2) | 1.7 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/police_terms_single/` |
| [police_terms_single@v1-20261022](../../catalog/police_terms_single.yaml#L2) | 1.7 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/police_terms_single/` |

- `police_terms_single@listening-review-v1-20261022`：police_terms_single@v1-20261022 中被人工听审过的 7 条数据行（父版本数据行原样照抄，录音和音频索引沿用父版本），每行的 metadata.listening_review（Lhotse custom.listening_review）是关于这条记录的听审答案列表：问题、选项、回答、备注、回答日期、听审名称、片段起止和选项含义（resolved_to）。共 10 条答案（police-terms-single-20261022 10 条），7 条已挂到数据行。其中 3 条没有记录 ID 或记录不在父版本数据行里，无法挂到行上，只在证据文件里。证据文件 listening_review.jsonl.gz 含该版本全部答案。只含被听过的记录，不是完整数据版本，不用于训练。脚本 scripts/label_registration/register_listening_review.py
- `police_terms_single@qc-v1-20261022`：police_terms_single@v1-20261022 的 3264 条录音，加上逐条质检结果：custom.qc 是共享 Qwen3-ASR-1.7B 转写后与术语按拼音对齐得到的多出/缺少/替换音节数、是否字全对、是否通过及未通过原因。custom.firered_crosscheck 标出 FireRedASR2-AED 交叉核对会拒绝的录音（试过未采用）。合成并检查过但没有入选的 3165 条（被检查拒绝、超出每术语名额或只转写未打分）在证据文件 qc_not_shipped 里，每条一行，没有录音。录音和文本沿用父版本。脚本 scripts/label_registration/register_police_qc.py
- `police_terms_single@v1-20261022`：警务术语单说测试集，只用于评测，不进训练。每条录音只说一个警务术语，不带句子；参考文本就是术语， supervision 的 custom.target_terms 为该术语（评测器据此报术语命中率）。术语取自警言警语 V6.0 术语表 （police_synthetic_zh_accent@legacy-rebalance-100k-20260916 source_entries 中 term/app 两类，共 1,088 个）， 每个术语 3 个说话人。Qwen3-TTS-12Hz-1.7B-Base 克隆原警务测试集的 test 口音说话人（参考音频为本机找回的原片段， 参考文本用 Qwen3-ASR 重新转写），全部是带口音的普通话。起因：实测单说术语时命中率很低，而现有警务测试集几乎都是整句 （police_asr_unified@v1-20261009 test 47,006 条里只有 9 条是单说术语）

### police_terms_single_train

警务术语单说训练集

语言：zh · 任务：语音识别、热词增强语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [police_terms_single_train@hotwords-confusable-v1-20261102](../../catalog/train_punc_v1.yaml#L393) | — | 未登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/police_terms_single_train/` |
| [police_terms_single_train@listening-review-v1-20261024](../../catalog/listening_review.yaml#L247) | — | 未登记 | 没有 |
| [police_terms_single_train@punc-written-v1-20261102](../../catalog/zh_punc_written_v1_gaps.yaml#L130) | 11.7 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/police_terms_single_train/` |
| [police_terms_single_train@qc-v1-20261023](../../catalog/police_terms_qc.yaml#L92) | 11.7 | 已登记 | 没有 |
| [police_terms_single_train@train-punc-v1-20261102](../../catalog/train_punc_v1.yaml#L268) | — | 未登记 | 没有 |
| [police_terms_single_train@v1-20261023](../../catalog/police_terms_single_train.yaml#L2) | 11.7 | 已登记 | 没有 |

- `police_terms_single_train@hotwords-confusable-v1-20261102`：警务术语单说训练集的热词版本：每条录音一条 asr_hotwords 记录，hotwords 为该条的目标术语，metadata.confusable_hotwords 为读音相近的其他警务术语（拼音音节最长公共片段 ≥ 较短术语的一半且 ≥ 2 个音节；字母按中文习惯读法，如 e 读 yi），训练时可作为干扰词放进列表（如 e警保 与 义警）。文本为 punc-written-v1-20261102 的带标点写法，录音同 v1-20261023
- `police_terms_single_train@listening-review-v1-20261024`：police_terms_single_train@v1-20261023 中被人工听审过的 10 条数据行（父版本数据行原样照抄，录音和音频索引沿用父版本），每行的 metadata.listening_review（Lhotse custom.listening_review）是关于这条记录的听审答案列表：问题、选项、回答、备注、回答日期、听审名称、片段起止和选项含义（resolved_to）。共 10 条答案（police-terms-single-train-20261023 10 条），10 条已挂到数据行。证据文件 listening_review.jsonl.gz 含该版本全部答案。只含被听过的记录，不是完整数据版本，不用于训练。脚本 scripts/label_registration/register_listening_review.py
- `police_terms_single_train@punc-written-v1-20261102`：police_terms_single_train@v1-20261023 训练集原标注加书面化标点，方法与 punc-written-v1-20261029 相同（amphiondata docs/written-punctuation.md：GB/T 15834、逗号从紧；Qwen3-4B 学生 punc-student-v1 以 Qwen3-ASR-1.7B 听音频得到的带标点转写作语气提示，只往原标注里插标点）。模型改动原文的条目按字对齐把标点搬回原标注；每条以 。？！ 结尾；没有汉字的条目和空标注原样保留。文件与源 supervisions 条数、顺序相同，只换 text。每条只说一个术语，多数只补句号；120 条没有汉字的术语（如 WPS、DNA）原样保留
- `police_terms_single_train@qc-v1-20261023`：police_terms_single_train@v1-20261023 的 21760 条录音，加上逐条质检结果：custom.qc 是共享 Qwen3-ASR-1.7B 转写后与术语按拼音对齐得到的多出/缺少/替换音节数、是否字全对、是否通过及未通过原因。合成并检查过但没有入选的 3638 条（被检查拒绝、超出每术语名额或只转写未打分）在证据文件 qc_not_shipped 里，每条一行，没有录音。录音和文本沿用父版本。脚本 scripts/label_registration/register_police_qc.py
- `police_terms_single_train@train-punc-v1-20261102`：police_terms_single_train@v1-20261023 的 train 训练版本，目标文本换成带标点的写法（按 id 取自 datasets/police_terms_single_train/versions/punc-written-v1-20261102/police_terms_single_train_supervisions_train_punc_written.jsonl.gz；去掉标点和空格、转小写后与原文一致才替换，否则保留原文）。其余字段与源版本相同，录音引用源版本
- `police_terms_single_train@v1-20261023`：警务术语单说训练集：每条录音只说一个警务术语，不带句子；文本就是术语，supervision 的 custom.target_terms 为该术语。 术语取自警言警语 V6.0 术语表（police_synthetic_zh_accent@legacy-rebalance-100k-20260916 source_entries 中 term/app 两类，共 1,088 个，全部使用，不按旧的术语划分留出），每个术语 20 个不同说话人。 Qwen3-TTS-12Hz-1.7B-Base 克隆原警务数据的 train 口音说话人（不含粤语、不用 dev/test 说话人；参考音频为本机找回的原片段， 参考文本用 Qwen3-ASR 重新转写），全部是带口音的普通话。起因：实测单说术语时命中率很低， police_asr_unified@v1-20261009 train 里单说术语只有 2,065 条、1.11 h
- 含派生版本（与源数据可能重叠）

### primewords

中文手机朗读（Primewords）；含清洗版

语言：zh · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [primewords@alignment-v1-20261008](../../catalog/zh_source_alignment.yaml#L262) | 99.0 | 已登记 | 没有 |
| [primewords@clean-dual-qwen-moss-v1-20261008](../../catalog/zh_source_clean.yaml#L1) | 98.4 | 已登记 | 没有 |
| [primewords@icefall-20260908](../../catalog/icefall_runtime.yaml#L1649) | 99.0 | 已登记 | 快照 20260914 |
| [primewords@legacy-20260804](../../catalog/icefall_base.yaml#L1280) | 99.0 | 已登记 | 快照 20260914 |

- `primewords@alignment-v1-20261008`：primewords@icefall-20260908 train 全部 50384 句的词级强制对齐（2026-10-08，Qwen3-ForcedAligner-0.6B，amphiondata main 6daabaf）。custom.alignment 含 status（aligned 44478 句 / needs_review 5906 句，后者有零时长或越界的词）、items（每个字或词的文本和起止秒，从该句开头算起）、issues、time_reference、unit、audio_duration。文本是对齐时所用的原标注文本；录音沿用 primewords@clean-dual-qwen-moss-v1-20261008 的 train 录音，不复制音频。脚本 scripts/label_registration/register_alignments.py
- `primewords@clean-dual-qwen-moss-v1-20261008`：primewords@icefall-20260908 的 train 监督片段，经 Qwen3-ASR-1.7B 与 MOSS-Transcribe-Diarize 双引擎一致性清洗；逐条写入 custom.clean（pass、reason、action、engine_status），不删除记录，读取时按 require_clean_pass 过滤。音频沿用源版本，不复制。规则 consensus-v6 / wenetspeech-faithful-v5：pass 50119、reject 265。少于 2 个字的 too_short 共 12 条按规则不经引擎直接 pass。用于合成时建议在 pass 之外再要求：两引擎均有效、MOSS 只输出 1 个说话人、action 不是 review_consensus；too_short 另要求两引擎规范化后与原文完全一致。按此筛选保留 41860 条、82.06 小时（too_short 通过 4/12）
- 含派生版本（与源数据可能重叠）

### realman

真实录制的中文多通道阵列语音（RealMAN）

语言：zh · 任务：语音识别、noise、sound_source_localization、speech_enhancement

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [realman@hf-aishell-20261025](../../catalog/realman.yaml#L1) | 83.7 | 已登记 | 没有 |
| [realman@icefall-20260908](../../catalog/icefall_runtime.yaml#L3115) | 83.7 | 已登记：已准备标注片段 | 快照 20260914 |
| [realman@punc-teacher-v1-20261029](../../catalog/punc_teacher_v1.yaml#L119) | 4.3 | 已登记 | 没有 |
| [realman@punc-written-v1-20261029](../../catalog/zh_punc_written_v1.yaml#L598) | 64.0 | 已登记 | 没有 |

- `realman@hf-aishell-20261025`：RealMAN 真实录制的 32 麦阵列中文数据（NeurIPS 2024）：扬声器在 32 个真实场景（教室、办公室、食堂、球场、地铁、公交、轿车、街边等）外放普通话，阵列录下 32 路 48 kHz 音频，含静止和移动声源，每句带直达声干净参考（dp_speech）、声源方位和距离、转写。语音共 51147 句、83.7 小时（train 64.0、val 8.1、test 11.6），来自 55 个说话人的 19629 条不同句子，三个划分之间句子和说话人都不重叠；另有 31 个场景的纯噪声录音 144.5 小时。用于多通道/单通道降噪、远场 ASR 和声源定位；单通道用时取任意一个 CH。val/test 的 ma_noisy_speech 是官方带噪混合，*_raw 里是对应的干净阵列语音和噪声。这是完整版（32 通道全部解压）；只要 ASR 的 CH0 可用 `realman@icefall-20260908`
- `realman@icefall-20260908`：标注片段时长，重叠语音或多麦克风可能重复计时
- `realman@punc-teacher-v1-20261029`：realman@icefall-20260908 的 train 监督片段里的 Qwen3.8-27B 老师给 2500 句加的书面化标点（2257 句去掉标点后与输入一致，ok=true）：custom.punctuation_teacher 记输出 text、ok 和模型看到的无标点输入 input；custom.punctuation_hint.qwen 是提示用的 Qwen3-ASR 转写；其中 53 句是留出的评测句，另带学生 v1 的输出 custom.punctuation_student。这批句子用来微调 Qwen3-4B 学生，抽样见 amphiondata scripts/punctuation/build_teacher_set.py。只含这些句子，text 与父版本相同，不是标点后的文本；录音沿用父版本，不复制音频。中间产物，供复现和比较学生，不直接用于训练。脚本 scripts/punctuation/register_punc_intermediates.py
- `realman@punc-written-v1-20261029`：realman@icefall-20260908 训练集原标注加书面化标点（GB/T 15834，逗号从紧）：微调后的 Qwen3-4B（Qwen3.8-27B 的 9.6 万条输出蒸馏）以 Qwen3-ASR-1.7B 听音频得到的带标点转写作语气提示，只往原标注里插标点。模型改动了原文的条目，把模型输出的标点按字对齐搬回原标注；每条以 。？！ 结尾；原标注的字、空格（首尾除外）和大小写不变。没有汉字的条目（英文句子、拼读字母）和标注为空的条目原样保留。文件与源 supervisions 条数、顺序相同，只换 text。试点 200 条人工参照上：WenetSpeech markF1 92.4、其他来源 88.9（老师 93.2 / 88.2，原 FireRedPunc 79.8）
- 含派生版本（与源数据可能重叠）

### realman_zh_far_asr

RealMAN 远场中文转写训练数据

语言：zh · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [realman_zh_far_asr@zh-far-replay-v1-20261009](../../catalog/zh_farfield.yaml#L337) | 64.0 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/zh_far_replay/` |

### speechio

SpeechIO 中文 ASR 排行榜评测集

语言：zh · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [speechio@eval-original-20261011](../../catalog/zh_asr_eval.yaml#L64) | 63.8 | 已登记 | 没有 |
| [speechio@legacy](../../catalog/legacy_multilingual.yaml#L2415) | 63.8 | 已登记 | 快照 20260914 |

- 有含标点版本

### tal100_zh

TAL 中文语音识别数据

语言：zh · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [tal100_zh@icefall-20260908](../../catalog/icefall_runtime.yaml#L1767) | 5.5 | 已登记 | 快照 20260914 |
| [tal100_zh@legacy-20260804](../../catalog/icefall_base.yaml#L1384) | 5.5 | 已登记 | 快照 20260914 |

- 含派生版本（与源数据可能重叠）

### tdtech_badcase

鼎桥反馈的识别回退样本（e警保 × 多种热词表），仅评测

语言：zh · 任务：热词增强语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [tdtech_badcase@v1-20261104](../../catalog/tdtech_badcase.yaml#L1) | 0.0 | 已登记 | 没有 |
| [tdtech_badcase@v2-20261104](../../catalog/tdtech_badcase.yaml#L65) | 0.0 | 已登记 | 没有 |
| [tdtech_badcase@v3-20261104](../../catalog/tdtech_badcase.yaml#L149) | 0.0 | 已登记 | 没有 |

- `tdtech_badcase@v1-20261104`：鼎桥反馈的识别回退样本，作为固定守门。v1：e警保 6 条（5 条客户真人采集，与 tdtech_customer_bench police-cmd 同 sha256；1 条 macOS 合成），参考一律为 e警保；客户在用的 10.26 版本（048 avg3）6/6，10.28 版本（054 avg3）3/6。两个切分音频相同，分别下发 audiollm-go 出厂内置热词表整表（1296 条）和只含 e警保 的表。只用于评测
- `tdtech_badcase@v2-20261104`：鼎桥反馈的识别回退样本，作为固定守门。v1：e警保 6 条（5 条客户真人采集，与 tdtech_customer_bench police-cmd 同 sha256；1 条 macOS 合成），参考一律为 e警保；客户在用的 10.26 版本（048 avg3）6/6，10.28 版本（054 avg3）3/6。三个切分音频相同（在 source/v1-20261104），分别下发 audiollm-go 出厂内置热词表整表（1296 条）、只含 e警保 的表、只含 e警保 与 义警 的表（已知热词表带 义警 时 e警保 出错，这是触发它的最小表；v2 新增）。只用于评测
- `tdtech_badcase@v3-20261104`：鼎桥反馈的识别回退样本，作为固定守门。v1：e警保 6 条（5 条客户真人采集，与 tdtech_customer_bench police-cmd 同 sha256；1 条 macOS 合成），参考一律为 e警保；客户在用的 10.26 版本（048 avg3）6/6，10.28 版本（054 avg3）3/6。五个切分音频相同（在 source/v1-20261104），分别下发 audiollm-go 出厂内置热词表整表（1296 条）、只含 e警保 的表、只含 e警保 与 义警 的表（v2 新增）；e警保 加词表里 44 条 3 字以内含“警”的近音词（v3 新增，规模同线上单次请求）、同一批近音词去掉 e警保（v3 新增）。只用于评测

### tdtech_customer_bench

鼎桥客户真实录音的语音识别评测，仅评测

语言：zh · 任务：语音识别、热词增强语音识别、目标说话人语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [tdtech_customer_bench@v1-20261102](../../catalog/tdtech_customer_bench.yaml#L1) | 0.1 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/tdtech_customer_bench/` |
| [tdtech_customer_bench@v2-20261102](../../catalog/tdtech_customer_bench.yaml#L65) | 0.1 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/tdtech_customer_bench/` |
| [tdtech_customer_bench@v3-20261103](../../catalog/tdtech_customer_bench.yaml#L152) | 0.1 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/tdtech_customer_bench/` |
| [tdtech_customer_bench@v4-20261104](../../catalog/tdtech_customer_bench.yaml#L239) | 0.1 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/tdtech_customer_bench/` |
| [tdtech_customer_bench@v5-20261105](../../catalog/tdtech_customer_bench.yaml#L371) | 0.1 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/tdtech_customer_bench/` |

- `tdtech_customer_bench@v1-20261102`：鼎桥（td-tech）客户提供的真实录音（邮件/Wiki 基线 2026-09-30，由 EvalHub 整理发布），只用于评测，不进训练。参考文本未全部经人工听审：通用识别只保留三份机器转写中两份一致的条目，难样例被筛掉，数字偏乐观；警务指令的参考来自录音分组的指令词，39 条经人工确认
- `tdtech_customer_bench@v2-20261102`：鼎桥（td-tech）客户提供的真实录音（邮件/Wiki 基线 2026-09-30，由 EvalHub 整理发布），只用于评测，不进训练。参考文本未全部经人工听审：通用识别只保留三份机器转写中两份一致的条目，难样例被筛掉，数字偏乐观；警务指令的参考来自录音分组的指令词，39 条经人工确认；警务指令另有一份带 300 词热词表的副本（police-cmd-hw300），音频相同
- `tdtech_customer_bench@v3-20261103`：鼎桥（td-tech）客户提供的真实录音（邮件/Wiki 基线 2026-09-30，由 EvalHub 整理发布），只用于评测，不进训练。参考文本未全部经人工听审：通用识别只保留三份机器转写中两份一致的条目，难样例被筛掉，数字偏乐观；警务指令的参考来自录音分组的指令词，39 条经人工确认；警务指令另有一份带 audiollm-go 出厂内置热词表（1296 条）的副本（police-cmd-builtin），音频相同
- `tdtech_customer_bench@v4-20261104`：鼎桥（td-tech）客户提供的真实录音（邮件/Wiki 基线 2026-09-30，由 EvalHub 整理发布），只用于评测，不进训练。参考文本未全部经人工听审：通用识别只保留三份机器转写中两份一致的条目，难样例被筛掉，数字偏乐观；警务指令的参考来自录音分组的指令词，39 条经人工确认；警务指令另有一份带 audiollm-go 出厂内置热词表（1296 条）的副本（police-cmd-builtin），音频相同。v4 加机主识别（6 段，机主由人工听审确定，文字取多模型一致转写）和人名热词（2 段，参考经人工听审）；角色分离的多模型打标一致率太低（约 12%），不进本版本
- `tdtech_customer_bench@v5-20261105`：鼎桥（td-tech）客户提供的真实录音（邮件/Wiki 基线 2026-09-30，由 EvalHub 整理发布），只用于评测，不进训练。参考文本未全部经人工听审：通用识别只保留三份机器转写中两份一致的条目，难样例被筛掉，数字偏乐观；警务指令的参考来自录音分组的指令词，39 条经人工确认；警务指令另有一份带 audiollm-go 出厂内置热词表（1296 条）的副本（police-cmd-builtin），音频相同。v4 加机主识别（6 段，机主由人工听审确定，文字取多模型一致转写）和人名热词（2 段，参考经人工听审）；角色分离的多模型打标一致率太低（约 12%），不进本版本。v5 按客户确认把人名“黄晋飞”写进参考和人名表，其余与 v4 相同

### thchs30

清华中文朗读（THCHS-30）；含热词版

语言：zh · 任务：语音识别、热词增强语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [thchs30@eval-20260804](../../catalog/open_audio_eval.yaml#L156) | 6.3 | 已登记 | 快照 20260914 |
| [thchs30@icefall-20260908](../../catalog/icefall_runtime.yaml#L1273) | 34.2 | 已登记 | 快照 20260914 |
| [thchs30@legacy-20260804](../../catalog/icefall_base.yaml#L940) | 34.2 | 已登记 | 快照 20260914 |
| [thchs30_hotwords@hotwords-v1-20260805](../../catalog/local_lhotse_derived.yaml#L886) | 25.5 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/thchs30_hotwords/` |
| [thchs30@legacy-20260804](../../catalog/icefall_base.yaml#L940) | 35.0 | [参考表](https://ccnuebbmik1f.feishu.cn/wiki/CEXFwEjPoi2bIukVjk9c5FdOn12?sheet=3d4d23) | 快照 20260914 |

- 含派生版本（与源数据可能重叠）

### threed_speaker_zh_far_asr

3D-Speaker 远场普通话转写训练数据

语言：zh · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [threed_speaker_zh_far_asr@punc-written-v1-20261102](../../catalog/zh_punc_written_v1_gaps.yaml#L194) | 71.2 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/threed_speaker_zh_far_asr/` |
| [threed_speaker_zh_far_asr@train-punc-v1-20261102](../../catalog/train_punc_v1.yaml#L331) | — | 未登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/threed_speaker_zh_far_asr/` |
| [threed_speaker_zh_far_asr@zh-far-replay-clean-v1-20261010](../../catalog/zh_farfield.yaml#L501) | 71.2 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/threed_speaker_zh_far_asr/` |
| [threed_speaker_zh_far_asr@zh-far-replay-v1-20261009](../../catalog/zh_farfield.yaml#L463) | 75.5 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/zh_far_replay/` |

- `threed_speaker_zh_far_asr@punc-written-v1-20261102`：threed_speaker_zh_far_asr@zh-far-replay-clean-v1-20261010 训练集原标注加书面化标点，方法与 punc-written-v1-20261029 相同（amphiondata docs/written-punctuation.md：GB/T 15834、逗号从紧；Qwen3-4B 学生 punc-student-v1 以 Qwen3-ASR-1.7B 听音频得到的带标点转写作语气提示，只往原标注里插标点）。模型改动原文的条目按字对齐把标点搬回原标注；每条以 。？！ 结尾；没有汉字的条目和空标注原样保留。文件与源 supervisions 条数、顺序相同，只换 text
- `threed_speaker_zh_far_asr@train-punc-v1-20261102`：threed_speaker_zh_far_asr@zh-far-replay-clean-v1-20261010 的 train 训练版本，目标文本换成带标点的写法（按 id 取自 datasets/threed_speaker_zh_far_asr/versions/punc-written-v1-20261102/threed_speaker_zh_far_asr_supervisions_train_punc_written.jsonl.gz；去掉标点和空格、转小写后与原文一致才替换，否则保留原文）。其余字段与源版本相同，录音引用源版本
- 含派生版本（与源数据可能重叠）

### ts_asr_dev

合成的中文目标说话人 ASR 开发集

语言：zh · 任务：目标说话人语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [ts_asr_dev@v1-20261017](../../catalog/ts_asr_dev.yaml#L1) | 10.7 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_asr_dev/` |

- `ts_asr_dev@v1-20261017`：目标说话人 ASR 评测集：由 AISHELL-3、KeSpeech、MagicData、AISHELL-2、AISHELL-1 的官方 test 划分合成，覆盖注册音频劣化、目标说话人进场离场与缺席、纯噪声、环境与设备。只用于评测，不进训练。场景见 scripts/ts_benchmark/recipe.yaml

### ts_asr_enroll_len

目标说话人评测：注册音频长度

语言：zh · 任务：目标说话人语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [ts_asr_enroll_len@v1-20261020](../../catalog/ts_asr_enroll_len.yaml#L1) | 1.5 | 已登记 | 没有 |

- `ts_asr_enroll_len@v1-20261020`：目标说话人 ASR 评测集：由 AISHELL-3、KeSpeech、MagicData、AISHELL-2、AISHELL-1 的官方 test 划分合成，覆盖注册音频劣化、目标说话人进场离场与缺席、纯噪声、环境与设备。只用于评测，不进训练。场景见 scripts/ts_benchmark/recipe.yaml

### ts_asr_nearfar

目标说话人评测：AliMeeting 近远场与谁先开口对照

语言：zh · 任务：目标说话人语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [ts_asr_nearfar@firstother-v1-20261104](../../catalog/ts_asr_nearfar.yaml#L2474) | 18.1 | 已登记 | 没有 |
| [ts_asr_nearfar@firstother-v2-20261105](../../catalog/ts_asr_nearfar.yaml#L2741) | 33.6 | 已登记 | 没有 |
| [ts_asr_nearfar@firstother-v3-20261105](../../catalog/ts_asr_nearfar.yaml#L3368) | 91.4 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_asr_nearfar/` |
| [ts_asr_nearfar@listening-review-v1-20261022](../../catalog/listening_review.yaml#L503) | — | 未登记 | 没有 |
| [ts_asr_nearfar@v1-20261014](../../catalog/ts_asr_nearfar.yaml#L1) | 6.0 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_asr_nearfar/` |
| [ts_asr_nearfar@v2-20261022](../../catalog/ts_asr_nearfar.yaml#L505) | 6.0 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_asr_nearfar/` |
| [ts_asr_nearfar@v3-20261022](../../catalog/ts_asr_nearfar.yaml#L1489) | 6.0 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_asr_nearfar/` |
| [ts_asr_nearfar@v3-hotword-labels-20261102](../../catalog/ts_benchmark_hotword_labels.yaml#L3034) | 6.0 | 已登记 | 没有 |

- `ts_asr_nearfar@firstother-v1-20261104`：“谁先开口”对照：复现一条内部返回的 TS-ASR badcase（45 秒三人同屋交替说话，注册是另一次单独录的 5 秒声纹，会话开头是非目标说话人清晰发言，所有版本都整段转写了先开口的人；把那句挪到末尾或改用会话内语音注册都能认对），原因是两个因素叠加：注册与会话不同录音、匹配信号弱，以及混合开头先是非目标说话人。从 AliMeeting Test 远场通道 0 的人工标注里按完整语句切 25–45 秒窗口，窗口内至少 3 人说话、目标累计说话至少 5 秒，不做混合。firstother：窗口第一个开口的不是目标，且目标第一句之前已有非目标一整句不少于 1.2 秒、被他人重叠不超过 20% 的语句；firsttarget：同样规则下目标先开口，作对照，与 firstother 同一批会议、每个（会议，说话人数）取相同窗口数。每个窗口一对样本：目标在场，和目标缺席（注册取同会议不在窗口里说话的人，没有时取其他会议的人，labels.absent_source）。注册沿用 ts_asr_real@v4-20261022：窗外第一句，后接同一人窗外无他人重叠的语句共存 10 秒，客户端取前 5 秒，前 5 秒他人说话不少于 0.3 秒的在 -enrollmix 划分；注册和开头那句都过声纹核对（头戴麦之和建档），不过的换句或整窗隔离，见 source/<版本>/report.json。注册三种：ef 远场通道 0（同通道）、en 本人头戴麦同样片段（跨通道，接近单独录的声纹）、ed 为 en 加限带（3.5–5 kHz 低通或 4 kHz 以上 −6 dB 高架）后再加 WHAM! 测试集稳态噪声（SNR 15–25 dB），参数逐条记在 metadata.enroll_degradation，劣化后的声纹核对结果在 metadata.enroll_degraded_voice_check；混合一律远场通道 0（mf）。窗口长于 ts_asr_real 的 26 秒上限，评测需整段送入。实际：10 场会议、每类 149 个窗口（firstother 1 窗因开头那句声纹核对不过被隔离，余 148），平均 36–37 秒，3 人 / 4 人窗口约 2:1；窗口须 ≥3 人而会议只有 3–4 人，目标缺席样本绝大多数（285/297）只能取其他会议的人；所有注册的前 5 秒都无他人说话，没有 -enrollmix 划分；劣化注册全部仍通过声纹核对。只用于评测，不进训练。生成脚本 scripts/ts_real/first_speaker.py
- `ts_asr_nearfar@firstother-v2-20261105`：ts_asr_nearfar@firstother-v1-20261104 的近场混合与声纹相似度版，窗口、注册、劣化参数和记录 ID 与 v1 相同，可逐条对照。内部返回的 TS-ASR badcase 的注册比会话更吵（会话是安静的近讲录音），而 v1 的混合是远场通道 0、带混响，所以新增 en-mn、ed-mn：注册同 en-mf、ed-mf，混合取窗口内各说话人头戴麦之和、电平对齐远场混合；mf 各划分不变。每条记录加 labels.target_sim / impostor_sim / sim_margin / opener_sim：ECAPA（WeSpeaker ECAPA-TDNN512-LM）计算注册前 5 秒与该条混合里各说话人独自说话部分（标注无他人、每段 ≥0.3 秒、合计 ≥1.0 秒）的余弦；impostor 取非目标中的最大值，sim_margin = target − impostor，目标缺席时 target 与 margin 为空。目标在场且 sim_margin ≤ 0.3 的另列入 <划分>-hard（子集，badcase 的 margin 为 0.25）。统计见 source/<版本>/report.json。生成脚本 scripts/ts_real/first_speaker_near.py。只用于评测，不进训练
- `ts_asr_nearfar@firstother-v3-20261105`：复现内部返回的 TS-ASR badcase（模型整段转写了另一个说话人）的拥挤窗口版。对 firstother-v2 四个版本的错人输出（输出覆盖目标文本不到 60%、40% 以上不是目标说的）挖掘显示，主因不是谁先开口或注册链路，而是目标被重叠多、说得少、注册与目标匹配弱：目标被重叠 <5% 或说话 >20 秒时错人 0%，重叠 ≥0.3 时 12%，目标说话 <10 秒时 10%，target_sim <0.4 时 21%，重叠 ≥0.3 且 target_sim <0.5 时 27–30%（四个版本一致）；非目标先开口 6.2%、目标先开口 3.6%。本版按这些条件取样：AliMeeting Test 与 Eval、AISHELL-4 test 远场通道 0 的人工标注，按完整语句切 25–45 秒窗口（≥3 人、目标 ≥5 秒，不再要求开头有清晰的一句），每个（窗口，目标）分层：crowded 为目标被重叠 ≥30% 且说话 <15 秒，control 为重叠 <15% 且说话 ≥20 秒；同一目标在同一录音里的样本窗口重合不超过较短者的一半（不同目标可以用同一段），非目标先开口与目标先开口交替取以求均衡（labels.first_speaker），control 每个（语料，会议，人数）不超过 crowded 的个数。每个样本一对：目标在场，和目标缺席（同会议不在窗口里的人，没有则取同语料其他会议，labels.absent_source）。注册、声纹核对、-enrollmix 与 ed 劣化同 firstother-v1；AliMeeting 有 ef、en、ed 三种注册，AISHELL-4 没有头戴麦只有 ef，混合都是远场通道 0。每条有 labels.target_sim / impostor_sim / sim_margin / opener_sim（同 v2，在远场混合上算）和 target_overlap_ratio、target_seconds；crowded 正样本中 target_sim <0.5 的另列为 crowded-lowsim-<语料>-<注册>-pos（子集）。AliMeeting Eval（icefall dev）只在部分训练里作验证集，没有进训练数据。统计见 source/<版本>/report.json。生成脚本 scripts/ts_real/first_speaker_crowded.py。只用于评测，不进训练
- `ts_asr_nearfar@listening-review-v1-20261022`：ts_asr_nearfar@v1-20261014 中被人工听审过的 8 条数据行（父版本数据行原样照抄，录音和音频索引沿用父版本），每行的 metadata.listening_review（Lhotse custom.listening_review）是关于这条记录的听审答案列表：问题、选项、回答、备注、回答日期、听审名称、片段起止和选项含义（resolved_to）。共 8 条答案（listen-1021-vs-1022 8 条），8 条已挂到数据行。证据文件 listening_review.jsonl.gz 含该版本全部答案。只含被听过的记录，不是完整数据版本，不用于训练。脚本 scripts/label_registration/register_listening_review.py
- `ts_asr_nearfar@v1-20261014`：AliMeeting 测试集窗口的近场与远场对照：同一窗口、同一条注册语句，注册取远场或说话人的头戴麦，混合取远场通道 0 或各头戴麦之和（电平对齐远场混合）。基于 ts_asr_real@v2-20261013 的 AliMeeting 窗口。只用于评测，不进训练
- `ts_asr_nearfar@v2-20261022`：ts_asr_nearfar@v1-20261014 的修正版，窗口和混合音频不变：每条记录加注册前 3 秒里他人说话的秒数（labels.enroll_others_s），不少于 0.3 秒的记为注册含他人声（enroll_condition = others_speech）并移入同名加 -enrollmix 的划分；生成脚本 scripts/ts_real/enroll_overlap.py
- `ts_asr_nearfar@v3-20261022`：ts_asr_nearfar@v2-20261022 的 5 秒注册版，窗口和混合音频不变：注册与其 ts_asr_real@v4-20261022 源样本同样的语句片段（远场取通道 0，近场取本人头戴麦），共存 10 秒；他人说话秒数按前 5 秒计，不少于 0.3 秒的在 -enrollmix 划分。生成脚本 scripts/ts_real/enroll_long.py
- `ts_asr_nearfar@v3-hotword-labels-20261102`：ts_asr_nearfar@v3-20261022 的全部记录，附目标转写和其他说话人转写的热词标注（metadata.hotword_labels：target 为目标转写的标注，others 按顺序对应合成记录的 metadata.interferers[*].utts[*] 或真实记录 metadata.window_utts 里非目标说话人的段落；每条含文本、最终热词、模型抽取、复核结果）。这些标注是评测集 ts_asr_hotwords@v1-20261102 的来源。只是标注载体：除 metadata.hotword_labels 外记录不变，音频索引沿用源版本；评测集仍固定引用源版本。脚本 scripts/ts_hotwords/register_eval_hotword_labels.py

### ts_asr_playback

目标说话人评测：外放播放的干扰声

语言：zh · 任务：目标说话人语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [ts_asr_playback@v1-20261022](../../catalog/ts_asr_playback.yaml#L1) | 3.4 | 已登记 | 没有 |

- `ts_asr_playback@v1-20261022`：目标说话人 ASR 评测集：由 AISHELL-3、KeSpeech、MagicData、AISHELL-2、AISHELL-1 的官方 test 划分合成，覆盖注册音频劣化、目标说话人进场离场与缺席、纯噪声、环境与设备。只用于评测，不进训练。场景见 scripts/ts_benchmark/recipe.yaml

### vitw_zh_far_asr

VITW 中文远场转写训练数据

语言：zh · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [vitw_zh_far_asr@zh-far-replay-v1-20261009](../../catalog/zh_farfield.yaml#L376) | 49.6 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/zh_far_replay/` |

### wenetspeech

中文网络语音万余小时（WenetSpeech）；含清洗版

语言：zh · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [wenetspeech@clean-weak-v1-20260904](../../catalog/wenetspeech_weak.yaml#L49) | 2,409.6 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/wenetspeech/` |
| [wenetspeech@eval-20260804](../../catalog/open_audio_eval.yaml#L618) | — | 未登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/wenetspeech/` |
| [wenetspeech@eval-20261011](../../catalog/zh_asr_eval.yaml#L1) | 38.2 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/wenetspeech/legacy_asr/`（原始数据） |
| [wenetspeech@icefall-20260908](../../catalog/icefall_runtime.yaml#L570) | 10,025.4 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/wenetspeech/` |
| [wenetspeech@legacy-20260804](../../catalog/icefall_base.yaml#L498) | 10,025.4 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/wenetspeech/` |
| [wenetspeech@punc-written-v1-20261029](../../catalog/zh_punc_written_v1.yaml#L662) | 10,005.4 | 已登记 | 没有 |
| [wenetspeech@weak-source-20260904](../../catalog/wenetspeech_weak.yaml#L1) | 2,477.9 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/wenetspeech/` |
| [wenetspeech_clean@clean-v1-20260805](../../catalog/local_lhotse_derived.yaml#L265) | 10,005.4 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/wenetspeech/` |
| [wenetspeech_clean@clean-v3-20260828](../../catalog/local_lhotse_derived.yaml#L980) | 9,971.1 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/wenetspeech/` |
| [wenetspeech_clean@clean-v3-pass-20261027](../../catalog/wenetspeech_clean_pass.yaml#L1) | 9,971.1 | 已登记 | 没有 |
| [wenetspeech_clean@punc-gold-v1-20261029](../../catalog/punc_teacher_v1.yaml#L555) | 0.1 | 已登记 | 没有 |
| [wenetspeech_clean@punc-teacher-v1-20261029](../../catalog/punc_teacher_v1.yaml#L2) | 44.7 | 已登记 | 没有 |
| [wenetspeech_clean@punc-written-v1-20261029](../../catalog/zh_punc_written_v1.yaml#L792) | 9,971.1 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/wenetspeech_clean/` |
| [wenetspeech_clean@train-punc-v1-20261102](../../catalog/train_punc_v1_wenetspeech.yaml#L2) | — | 未登记 | 没有 |
| [wenetspeech_test_meeting@eval-20260804](../../catalog/open_audio_eval.yaml#L764) | 15.2 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/wenetspeech/` |
| [wenetspeech_test_net@eval-20260804](../../catalog/open_audio_eval.yaml#L729) | 23.1 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/wenetspeech/` |
| [wenetspeech_traffic_snr0@icefall-20260908](../../catalog/icefall_runtime.yaml#L3900) | — | 未登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/wenetspeech/` |
| [wenetspeech_traffic_snr0@recipe-1](../../catalog/icefall_traffic_derived.yaml#L40) | 23.1 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/wenetspeech/` |
| [wenetspeech_traffic_snr10@icefall-20260908](../../catalog/icefall_runtime.yaml#L4108) | — | 未登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/wenetspeech/` |
| [wenetspeech_traffic_snr10@recipe-1](../../catalog/icefall_traffic_derived.yaml#L292) | 23.1 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/wenetspeech/` |
| [wenetspeech_traffic_snr15@icefall-20260908](../../catalog/icefall_runtime.yaml#L4212) | — | 未登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/wenetspeech/` |
| [wenetspeech_traffic_snr15@recipe-1](../../catalog/icefall_traffic_derived.yaml#L418) | 23.1 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/wenetspeech/` |
| [wenetspeech_traffic_snr20@icefall-20260908](../../catalog/icefall_runtime.yaml#L4316) | — | 未登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/wenetspeech/` |
| [wenetspeech_traffic_snr20@recipe-1](../../catalog/icefall_traffic_derived.yaml#L544) | 23.1 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/wenetspeech/` |
| [wenetspeech_traffic_snr5@icefall-20260908](../../catalog/icefall_runtime.yaml#L4004) | — | 未登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/wenetspeech/` |
| [wenetspeech_traffic_snr5@recipe-1](../../catalog/icefall_traffic_derived.yaml#L166) | 23.1 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/wenetspeech/` |
| [wenetspeech@legacy-20260804](../../catalog/icefall_base.yaml#L498) | 10,000.0 | [参考表](https://ccnuebbmik1f.feishu.cn/wiki/CEXFwEjPoi2bIukVjk9c5FdOn12?sheet=3d4d23) | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/wenetspeech/` |

- `wenetspeech@punc-written-v1-20261029`：wenetspeech@icefall-20260908 训练集原标注加书面化标点（GB/T 15834，逗号从紧）：微调后的 Qwen3-4B（Qwen3.8-27B 的 9.6 万条输出蒸馏）以 Qwen3-ASR-1.7B 听音频得到的带标点转写作语气提示，只往原标注里插标点。模型改动了原文的条目，把模型输出的标点按字对齐搬回原标注；每条以 。？！ 结尾；原标注的字、空格（首尾除外）和大小写不变。没有汉字的条目（英文句子、拼读字母）和标注为空的条目原样保留。文件与源 supervisions 条数、顺序相同，只换 text。试点 200 条人工参照上：WenetSpeech markF1 92.4、其他来源 88.9（老师 93.2 / 88.2，原 FireRedPunc 79.8）
- `wenetspeech_clean@clean-v3-pass-20261027`：wenetspeech_clean@clean-v3-20260828 训练集（WenetSpeech L）里上游清洗标记 custom.clean.pass=true 的分段，共 14568791 条 / 9971.1 小时（源 14625245 条，去掉未通过的 56454 条）；每行原样保留，包括 custom.clean，只用无标点文本。录音清单沿用源版本，不复制音频。用途：带 Lance 记录索引的 clean-only 版本，recipe_parameters.clean_pass_only 声明每行都已通过，open-audio-llm 据此让 require_clean_pass 的来源走 Lance 索引。脚本 scripts/wenetspeech_clean_pass.py
- `wenetspeech_clean@punc-gold-v1-20261029`：wenetspeech_clean@clean-v3-pass-20261027 的 train 监督片段里的 普通话标点试点的 120 句手写参照标点（规范 v1，逗号从紧）：custom.punctuation_gold.text 是参照，custom.punctuation_hint 记试点用的 Qwen3-ASR 与 FireRedPunc 带标点转写。只含这些句子，text 与父版本相同，不是标点后的文本；录音沿用父版本，不复制音频。中间产物，供复现和比较学生，不直接用于训练。脚本 scripts/punctuation/register_punc_intermediates.py
- `wenetspeech_clean@punc-teacher-v1-20261029`：wenetspeech_clean@clean-v3-pass-20261027 的 train 监督片段里的 Qwen3.8-27B 老师给 65000 句加的书面化标点（64406 句去掉标点后与输入一致，ok=true）：custom.punctuation_teacher 记输出 text、ok 和模型看到的无标点输入 input；custom.punctuation_hint.qwen 是提示用的 Qwen3-ASR 转写；其中 1309 句是留出的评测句，另带学生 v1 的输出 custom.punctuation_student。这批句子用来微调 Qwen3-4B 学生，抽样见 amphiondata scripts/punctuation/build_teacher_set.py。只含这些句子，text 与父版本相同，不是标点后的文本；录音沿用父版本，不复制音频。中间产物，供复现和比较学生，不直接用于训练。脚本 scripts/punctuation/register_punc_intermediates.py
- `wenetspeech_clean@punc-written-v1-20261029`：wenetspeech_clean@clean-v3-20260828 训练集原标注加书面化标点（GB/T 15834，逗号从紧）：微调后的 Qwen3-4B（Qwen3.8-27B 的 9.6 万条输出蒸馏）以 Qwen3-ASR-1.7B 听音频得到的带标点转写作语气提示，只往原标注里插标点。模型改动了原文的条目，把模型输出的标点按字对齐搬回原标注；每条以 。？！ 结尾；原标注的字、空格（首尾除外）和大小写不变。没有汉字的条目（英文句子、拼读字母）和标注为空的条目原样保留。文件与源 supervisions 条数、顺序相同，只换 text。试点 200 条人工参照上：WenetSpeech markF1 92.4、其他来源 88.9（老师 93.2 / 88.2，原 FireRedPunc 79.8）。本数据的条目与 wenetspeech（原始 L 标注）同序，标注不同的 244,507 条即 wenetspeech_disfluency，标点取自这两者的结果
- `wenetspeech_clean@train-punc-v1-20261102`：wenetspeech_clean@clean-v3-pass-20261027 的 train 训练版本，目标文本换成带标点的写法（按 id 取自 datasets/wenetspeech_clean/versions/punc-written-v1-20261029/wenetspeech_supervisions_L_clean_punc_written.jsonl.gz；去掉标点和空格、转小写后与原文一致才替换，否则保留原文）。其余字段与源版本相同，录音引用源版本
- 含派生版本（与源数据可能重叠）

### wenetspeech4tts

WenetSpeech 筛出的中文 TTS 语音

语言：zh · 任务：语音识别、语音合成

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [wenetspeech4tts@icefall-20260908](../../catalog/icefall_runtime.yaml#L713) | 7,232.2 | 已登记 | 快照 20260914 |
| [wenetspeech4tts@legacy-20260804](../../catalog/icefall_base.yaml#L586) | 7,232.2 | 已登记 | 快照 20260914 |
| [wenetspeech4tts@tts-unified-v0.1](../../catalog/tts_unified.yaml#L853) | 7,232.2 | 已登记 | `amphion-tts-data-1373259071:WenetSpeech4TTS/`（原始数据） |
| [wenetspeech4tts@legacy-20260804](../../catalog/icefall_base.yaml#L586) | 7,700.0 | [参考表](https://ccnuebbmik1f.feishu.cn/wiki/CEXFwEjPoi2bIukVjk9c5FdOn12?sheet=3d4d23) | 快照 20260914 |

- `wenetspeech4tts@tts-unified-v0.1`：音频编码字节存放在 Lance 表内；原始划分在 metadata_json.original_split，统一输出全部为 train。ASR 用 tts_lance.iter_asr_samples（tts-asr-rules/v1）读取，会排除原始 dev/test 等
- 含派生版本（与源数据可能重叠）

### wenetspeech_chuan

川渝方言网络语音（WenetSpeech-Chuan）

语言：zh · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [wenetspeech_chuan@clean-qwen3-asr-v1-20261023](../../catalog/wenetspeech_chuan_clean.yaml#L2) | 7,075.7 | 已登记 | 没有 |
| [wenetspeech_chuan@eval-20261012](../../catalog/zh_asr_eval.yaml#L103) | 9.7 | 已登记 | 没有 |
| [wenetspeech_chuan@extracted-20261021](../../catalog/wenetspeech_chuan_extracted.yaml#L2) | 10,259.6 | 已登记 | 没有 |
| [wenetspeech_chuan@icefall-20260908](../../catalog/icefall_runtime.yaml#L934) | 10,259.6 | 已登记 | 快照 20260914 |
| [wenetspeech_chuan@legacy-20260804](../../catalog/icefall_base.yaml#L625) | 10,259.6 | 已登记 | 快照 20260914 |
| [wenetspeech_chuan@listening-review-v1-20261026](../../catalog/listening_review.yaml#L905) | — | 未登记 | 没有 |
| [wenetspeech_chuan@qwen3-asr-full-v1-20261023](../../catalog/wenetspeech_chuan_qwen.yaml#L1) | 10,209.5 | 已登记 | 没有 |

- `wenetspeech_chuan@clean-qwen3-asr-v1-20261023`：WenetSpeech-Chuan 训练集（4,938,701 条 / 10,259.6 h）是机器标注，不带置信度。 用共享的 Qwen3-ASR-1.7B 逐条转写，按 SpeechIO TextNorm 算与原标注的字错误率（Qwen 在 WSC-Eval 上自身 12.1 / 21.1）， 保留错误率 < 30% 的 3,277,696 条 / 7,075.7 h（69.3%），原标注不改，不拿 Qwen 的文字替换。 规则经 6 轮听审（60 条 1–10 秒片段，每类 20 条）确定：Qwen 空输出的 20 条中 17 条没有人声； Qwen 输出 ≥ 原标注 2 倍的 20 条原标注全不可用（多人只标一人、漏标语音、音乐、人声太轻太远）； 错误率 30–100% 的 20 条中原标注对的只有 3 条。 错误率 ≥ 100% 的其余条目（333.8 h）和原标注规范化后为空的（103.7 h）未听审，按用户决定一并不用；超过约 157 秒、服务拒收的 795 条 / 50.0 h 未核对，也不在本版本内。 问题集中在 cut id 前缀 01316 的子来源（5,383 h，保留 55.3%）；cq*、sc* 等其余来源保留 79–88%
- `wenetspeech_chuan@extracted-20261021`：WenetSpeech-Chuan 训练集的 4,938,701 个音频从 DATA-TTS 的大 tar 中按字节范围取出，存为单个 wav，共 1.18 TB。 8 卡训练按 tar 偏移读音频时数据加载跟不上（约 1.7 秒/步），改读单文件后约 0.69 秒/步。 随机抽 550 条与 dd 读取结果逐字节相同
- `wenetspeech_chuan@listening-review-v1-20261026`：wenetspeech_chuan@extracted-20261021 中被人工听审过的 60 条数据行（父版本数据行原样照抄，录音和音频索引沿用父版本），每行的 metadata.listening_review（Lhotse custom.listening_review）是关于这条记录的听审答案列表：问题、选项、回答、备注、回答日期、听审名称、片段起止和选项含义（resolved_to）。共 60 条答案（wenetspeech-chuan-qwen-diff-20261024 10 条、wenetspeech-chuan-qwen-diff-20261025 10 条、wenetspeech-chuan-qwen-diff-20261026 10 条、wenetspeech-chuan-qwen-diff-20261027 10 条、wenetspeech-chuan-qwen-diff-20261028 10 条、wenetspeech-chuan-qwen-diff-20261029 10 条），60 条已挂到数据行。证据文件 listening_review.jsonl.gz 含该版本全部答案。只含被听过的记录，不是完整数据版本，不用于训练。脚本 scripts/label_registration/register_listening_review.py
- `wenetspeech_chuan@qwen3-asr-full-v1-20261023`：wenetspeech_chuan@icefall-20260908 里WenetSpeech-Chuan 川渝方言训练集的全部可转写条目（4,937,906 条 / 10209.5 h），原标注（机器标注，不带置信度）一字不改；每条加 custom.qwen_asr：共享的 Qwen3-ASR-1.7B 的转写（hypothesis）、Qwen 报告的语种（language）和与原标注的字错误率（SpeechIO TextNorm，按字，ref_tokens / hyp_tokens / errors / cer 百分数；原标注规范化后为空时 cer 为空）。整体 CER 21.47 %，Qwen 在 WSC-Eval Easy / Hard 上自身 CER 为 12.1 / 21.1；Qwen 空输出 223,268 条。源 4,938,701 条里 795 条（50.0 h，超过约 157 s，服务拒收）没有转写，不在本版本内。原标注里有多人只标一人、漏标语音、音乐、人声太轻太远的条目，CER 高不等于 Qwen 错；已听审的规则见 wenetspeech_chuan@clean-qwen3-asr-v1-20261023。录音沿用父版本，不复制音频。脚本 scripts/wenetspeech_qwen/
- 含派生版本（与源数据可能重叠）

### wenetspeech_diarize

WenetSpeech 长音频的说话人日志伪标签

语言：zh · 任务：diarization、带说话人标注的语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [wenetspeech_diarize@listening-review-v1-20261012](../../catalog/listening_review.yaml#L957) | — | 未登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/wenetspeech_diarize/` |
| [wenetspeech_diarize@moss-transcribe-diarize-0.9B](../../catalog/wenetspeech_diarize.yaml#L2) | — | 未登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/wenetspeech_diarize/` |
| [wenetspeech_diarize@teacher-labels-v1-20261012](../../catalog/diarization_raw_wenetspeech-l.yaml#L2) | — | 未登记 | 没有 |

- `wenetspeech_diarize@listening-review-v1-20261012`：wenetspeech_diarize@moss-transcribe-diarize-0.9B 中被人工听审过的 0 条数据行（父版本数据行原样照抄，录音和音频索引沿用父版本），每行的 metadata.listening_review（Lhotse custom.listening_review）是关于这条记录的听审答案列表：问题、选项、回答、备注、回答日期、听审名称、片段起止和选项含义（resolved_to）。共 7 条答案（listen-review-20261012 7 条），0 条已挂到数据行。其中 7 条没有记录 ID 或记录不在父版本数据行里，无法挂到行上，只在证据文件里。证据文件 listening_review.jsonl.gz 含该版本全部答案。只含被听过的记录，不是完整数据版本，不用于训练。脚本 scripts/label_registration/register_listening_review.py
- `wenetspeech_diarize@moss-transcribe-diarize-0.9B`：WenetSpeech L 训练集原始长音频（≥120 秒，51,358 条 / 22,174 h）的说话人日志伪标签，流程同 emilia2_zh_dialogue_diarize： 本地 MOSS-Transcribe-Diarize 0.9B 整条打说话人和文本，粗筛多人录音（≥2 人且每人 ≥5 秒，保留 37,153 条 / 19,970.4 h）， 在停顿处切 30–120 秒窗口，Qwen3-ASR 整窗识别，文字差异 ≤ 15% 的窗口整体保留（607,243 个 / 17,185.5 h，丢 2,754 h，主要是 text_check_mismatch 2,330.8 h）。 WenetSpeech 没有带说话人的上游标注，不做说话人检查。按试跑（以 MOSS Pro 为参照）与听审的方案 B 分两个划分： train_120s 是本地 MOSS 判为 2 人的窗口（170,418 个 / 4,626.3 h，试跑好窗口约 91%），作为主数据； train_120s_lowconf 是其余窗口（1 人 2,300.3 h、3 人 3,502.1 h、4 人以上 6,756.8 h；试跑好窗口 54–74%），不并入主数据，按需选用。 音频直接引用 wenetspeech@legacy-20260804 的原始 opus，记录按 cut_id + start/duration 引用。试跑、听审、被拒样本见 run_dir README
- `wenetspeech_diarize@teacher-labels-v1-20261012`：占位登记，未完成，不转正、不进训练：WenetSpeech L 长音频（≥120 秒，51,358 条 / 22,174 h）的说话人日志伪标签。2026-10-14 用户决定停止全量打标，只保留前 41 批（共 52 批）的整条本机 MOSS-Transcribe-Diarize 0.9B 标注和粗筛结果，Qwen3-ASR 整窗核对 b000–b040 都做完，但不并入训练、不发布为可用训练版本；是否改为定向打标要看音色相近数据的效果再定。train_supervisions_windows_0：通过整窗核对的 398,633 个窗口（11,275 h）的片段，共 12,640,449 条 Lhotse supervision，说话人为 <录音>#S<编号>，custom.window_check 记窗口和字错误率；window_check_records：全部 454,358 个窗口的核对结果（含被拒窗口和原因、Qwen3-ASR 的 check_text）；local_moss_records：41,000 条录音的整条标注；qwen3_asr_window_records：Qwen3-ASR 整窗识别；pilot_*：试跑 100 条录音的本地标注和 MOSS Pro 对 300 个窗口片段的标注（用于定门槛）。已知局限：WenetSpeech 没有带说话人的上游标注，做不了说话人检查；试跑中好窗口比例 71%，不合格窗口多半是说话人分错，文字核对管不住。录音沿用 wenetspeech@legacy-20260804 train_rec_0。未登记：逐块原始响应 raw/、window-plan、远端对齐检查 remote-compare。脚本 scripts/diarization_raw_labels/register_raw_labels.py

### wenetspeech_disfluency

WenetSpeech L 保留口语不流利词的转写

语言：zh · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [wenetspeech_disfluency@icefall-20260908](../../catalog/icefall_runtime.yaml#L680) | 182.5 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/wenetspeech/` |
| [wenetspeech_disfluency@punc-written-v1-20261029](../../catalog/zh_punc_written_v1.yaml#L727) | 182.5 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/wenetspeech_disfluency/` |

- `wenetspeech_disfluency@punc-written-v1-20261029`：wenetspeech_disfluency@icefall-20260908 训练集原标注加书面化标点（GB/T 15834，逗号从紧）：微调后的 Qwen3-4B（Qwen3.8-27B 的 9.6 万条输出蒸馏）以 Qwen3-ASR-1.7B 听音频得到的带标点转写作语气提示，只往原标注里插标点。模型改动了原文的条目，把模型输出的标点按字对齐搬回原标注；每条以 。？！ 结尾；原标注的字、空格（首尾除外）和大小写不变。没有汉字的条目（英文句子、拼读字母）和标注为空的条目原样保留。文件与源 supervisions 条数、顺序相同，只换 text。试点 200 条人工参照上：WenetSpeech markF1 92.4、其他来源 88.9（老师 93.2 / 88.2，原 FireRedPunc 79.8）
- 含派生版本（与源数据可能重叠）

### wenetspeech_podcast

WenetSpeech L 中的播客部分

语言：zh · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [wenetspeech_podcast@l-20261014](../../catalog/amphionasr_v4.yaml#L3722) | 3,892.3 | 已登记 | 没有 |
| [wenetspeech_podcast@l-20261014-ctxclean-20261110](../../catalog/context_correction_clean_zh.yaml#L458) | 3,840.9 | 已登记 | 没有 |

- `wenetspeech_podcast@l-20261014`：WenetSpeech L 集按录音路径分成 YouTube 或 podcast。这是全集，不是 replay 的 3000 小时抽样
- `wenetspeech_podcast@l-20261014-ctxclean-20261110`：在 wenetspeech_podcast@l-20261014 上做的上下文纠偏清洗：说话人讲字怎么写（组词、拆字、偏旁、否定对比）而标注写成同音别字的， 按说明改正；拿不准的窗口整窗去掉；context_correction_zh 评测用过的录音整条去掉。判定依据见 context_correction_clean_zh@v1-20261110。 改正抽检 45 段文本，明确改错 2 段、改后仍矛盾或存疑 4 段，均已改判为隔离；未抽到的改正估计约 4% 改错
- 含派生版本（与源数据可能重叠）

### wenetspeech_wu

吴语网络语音（WenetSpeech-Wu）

语言：zh · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [wenetspeech_wu@icefall-20260908](../../catalog/icefall_runtime.yaml#L958) | 8,740.7 | 已登记 | 快照 20260914 |
| [wenetspeech_wu@legacy-20260804](../../catalog/icefall_base.yaml#L650) | 8,740.7 | 已登记 | 快照 20260914 |
| [wenetspeech_wu@qwen3-asr-pilot-v1-20261025](../../catalog/wenetspeech_wu_qwen.yaml#L1) | 4.1 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/wenetspeech_wu/` |
| [wenetspeech_wu@stepaudio2-wu-asr-full-v1-20261109](../../catalog/wenetspeech_wu_step.yaml#L61) | 8,740.7 | 已登记 | 没有 |
| [wenetspeech_wu@stepaudio2-wu-asr-v1-20261109](../../catalog/wenetspeech_wu_step.yaml#L1) | 6,804.5 | 已登记 | 没有 |

- `wenetspeech_wu@qwen3-asr-pilot-v1-20261025`：wenetspeech_wu@icefall-20260908 里WenetSpeech-Wu 吴语训练集的随机抽样（2,000 条 / 4.1 h），原标注（吴语写法的机器标注，带置信度和普通话译文）一字不改；每条加 custom.qwen_asr：共享的 Qwen3-ASR-1.7B 的转写（hypothesis）、Qwen 报告的语种（language）和与原标注的字错误率（SpeechIO TextNorm，按字，ref_tokens / hyp_tokens / errors / cer 百分数；原标注规范化后为空时 cer 为空）。整体 CER 35.84 %，Qwen 在 WenetSpeech-Wu-Bench 上自身 CER 为 24.2；Qwen 空输出 0 条。试跑：从 wenetspeech_wu@icefall-20260908 训练集按种子 42 随机抽 2000 条，不是全量，整体 CER 35.8 %，不可用于训练。两边文字都很乱，核对价值低。录音沿用父版本，不复制音频。脚本 scripts/wenetspeech_qwen/
- `wenetspeech_wu@stepaudio2-wu-asr-full-v1-20261109`：wenetspeech_wu@icefall-20260908 里 WenetSpeech-Wu 吴语训练集的全部条目（4,241,226 条 / 8740.7 h），原标注（吴语写法的机器标注，带置信度和普通话译文）一字不改；每条 supervision 加 custom.step_audio2_asr：Step-Audio2-Wu-ASR（ASLP-lab 在 Step-Audio-2-mini 上微调的吴语 ASR，贪心解码）的转写（hypothesis）、是否达到生成上限被截断（truncated，多为重复输出）和与原标注的字错误率（SpeechIO TextNorm，按字，ref_tokens / hyp_tokens / errors / cer 百分数；原标注规范化后为空时 cer 为空）。整体 CER 16.20 %，Step 在 WenetSpeech-Wu-Bench 抽样 1,000 条上自身 CER 为 12.3（Qwen3-ASR 24.2）；空输出 5,292 条，截断 5,121 条。Step-Audio2-Wu-ASR 在 WenetSpeech-Wu 上训练过，与原标注的一致程度可能偏高。误杀按 Wu-Bench 人工标注估计：Wu-Bench 上 Step 自身落到 CER ≥ 30 % 的时长占 8.4 %，训练集为 22.2 %，据此被丢的部分约 38 % 其实标注是对的（偏粗，可能高估）；分歧集中在原标注低置信度的条目。录音沿用父版本，不复制音频。脚本 scripts/wenetspeech_wu_step/
- `wenetspeech_wu@stepaudio2-wu-asr-v1-20261109`：WenetSpeech-Wu 吴语训练集（wenetspeech_wu@icefall-20260908）用 Step-Audio2-Wu-ASR 逐条核对后保留的部分：原标注规范化后非空、生成未截断且字错误率 < 30 % 的 3,281,389 条 / 6804.5 h（占全部时长的 77.8 %）。原标注不改，不拿 Step 的文字替换。每行的 custom.step_audio2_asr 与 wenetspeech_wu@stepaudio2-wu-asr-full-v1-20261109 中相同；被去掉的条目和全部转写见该版本。Step-Audio2-Wu-ASR 在 WenetSpeech-Wu 上训练过，与原标注的一致程度可能偏高。误杀按 Wu-Bench 人工标注估计：Wu-Bench 上 Step 自身落到 CER ≥ 30 % 的时长占 8.4 %，训练集为 22.2 %，据此被丢的部分约 38 % 其实标注是对的（偏粗，可能高估）；分歧集中在原标注低置信度的条目。录音沿用父版本，不复制音频。脚本 scripts/wenetspeech_wu_step/
- 含派生版本（与源数据可能重叠）

### wenetspeech_youtube

WenetSpeech L 中的 YouTube 部分

语言：zh · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [wenetspeech_youtube@l-20261014](../../catalog/amphionasr_v4.yaml#L3774) | 6,113.1 | 已登记 | 没有 |
| [wenetspeech_youtube@l-20261014-ctxclean-20261110](../../catalog/context_correction_clean_zh.yaml#L1599) | 6,112.6 | 已登记 | 没有 |

- `wenetspeech_youtube@l-20261014`：WenetSpeech L 集按录音路径分成 YouTube 或 podcast。这是全集，不是 replay 的 3000 小时抽样
- `wenetspeech_youtube@l-20261014-ctxclean-20261110`：在 wenetspeech_youtube@l-20261014 上做的上下文纠偏清洗：说话人讲字怎么写（组词、拆字、偏旁、否定对比）而标注写成同音别字的，按说明改正；拿不准的窗口整窗去掉。判定依据见 context_correction_clean_zh@v1-20261110。标注是机器转写；隔离里约 6 成是误杀（多为字谜和照实写的结构说明），总量 0.55 h；2026-11-12 捞回 86 段，仍去掉 630 段（0.49 h）
- 含派生版本（与源数据可能重叠）

### wenetspeech_yue_all

粤语网络语音（WenetSpeech-Yue）；含清洗版

语言：yue · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [wenetspeech_yue@clean-qwen3-asr-full-v1-20261024](../../catalog/wenetspeech_yue_clean.yaml#L69) | 4,333.1 | 已登记 | 没有 |
| [wenetspeech_yue@clean-qwen3-asr-v1-20261024](../../catalog/wenetspeech_yue_clean.yaml#L2) | 4,324.5 | 已登记 | 没有 |
| [wenetspeech_yue@icefall-20260908](../../catalog/icefall_runtime.yaml#L2390) | — | 未登记 | 快照 20260914 |
| [wenetspeech_yue@legacy-20260804](../../catalog/icefall_base.yaml#L1996) | — | 未登记 | 快照 20260914 |
| [wenetspeech_yue@nonclean-qwen3-asr-full-v1-20261025](../../catalog/wenetspeech_yue_nonclean.yaml#L69) | 17,373.9 | 已登记 | 没有 |
| [wenetspeech_yue@nonclean-qwen3-asr-v1-20261025](../../catalog/wenetspeech_yue_nonclean.yaml#L1) | 15,909.1 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/wenetspeech_yue/` |
| [wenetspeech_yue_all@icefall-20260908](../../catalog/icefall_runtime.yaml#L2447) | — | 未登记 | 快照 20260914 |
| [wenetspeech_yue_all@legacy-20260804](../../catalog/icefall_base.yaml#L2054) | — | 未登记 | 快照 20260914 |

- `wenetspeech_yue@clean-qwen3-asr-full-v1-20261024`：wenetspeech_yue@icefall-20260908 里WenetSpeech-Yue 粤语训练集 clean 部分的全部可转写条目（1,244,949 条 / 4333.1 h），原标注（发布方多系统融合（ROVER）的机器标注，每条置信度 ≥ 0.9）一字不改；每条加 custom.qwen_asr：共享的 Qwen3-ASR-1.7B 的转写（hypothesis）、Qwen 报告的语种（language）和与原标注的字错误率（SpeechIO TextNorm，按字，ref_tokens / hyp_tokens / errors / cer 百分数；原标注规范化后为空时 cer 为空）。整体 CER 6.15 %，Qwen 在 WSYue-ASR-eval short 上自身 CER 为 6.2；Qwen 空输出 1 条。粤语保留规则沿用川渝（CER < 30 %），未单独听审。录音沿用父版本，不复制音频。脚本 scripts/wenetspeech_qwen/
- `wenetspeech_yue@clean-qwen3-asr-v1-20261024`：WenetSpeech-Yue 粤语训练集 clean 部分（wenetspeech_yue@icefall-20260908）用 Qwen3-ASR-1.7B 逐条核对后保留的部分：原标注规范化后非空且与 Qwen 的字错误率 < 30 % 的 1,240,512 条 / 4324.5 h（占可转写 1,244,949 条的 99.6 %），规则同 wenetspeech_chuan@clean-qwen3-asr-v1-20261023；原标注不改，不拿 Qwen 的文字替换。每行保留 custom.qwen_asr（Qwen 转写、语种、CER），与 wenetspeech_yue@clean-qwen3-asr-full-v1-20261024 中的相同；被去掉的条目和全部转写见 wenetspeech_yue@clean-qwen3-asr-full-v1-20261024。粤语保留规则沿用川渝（CER < 30 %），未单独听审。录音沿用父版本，不复制音频。脚本 scripts/wenetspeech_qwen/
- `wenetspeech_yue@nonclean-qwen3-asr-full-v1-20261025`：wenetspeech_yue_all@icefall-20260908 里WenetSpeech-Yue 粤语训练集里 clean 以外的部分的全部可转写条目（5,592,487 条 / 17373.9 h），原标注（发布方多系统融合（ROVER）的机器标注，置信度 0.6–1.0）一字不改；每条加 custom.qwen_asr：共享的 Qwen3-ASR-1.7B 的转写（hypothesis）、Qwen 报告的语种（language）和与原标注的字错误率（SpeechIO TextNorm，按字，ref_tokens / hyp_tokens / errors / cer 百分数；原标注规范化后为空时 cer 为空）。整体 CER 13.49 %，Qwen 在 WSYue-ASR-eval short 上自身 CER 为 6.2；试跑 2,000 条整体 13.2%，置信度越低差异越大；Qwen 空输出 2,582 条。粤语保留规则沿用川渝（CER < 30 %），未单独听审。录音沿用父版本，不复制音频。脚本 scripts/wenetspeech_qwen/
- `wenetspeech_yue@nonclean-qwen3-asr-v1-20261025`：WenetSpeech-Yue 粤语训练集里 clean 以外的部分（wenetspeech_yue_all@icefall-20260908）用 Qwen3-ASR-1.7B 逐条核对后保留的部分：原标注规范化后非空且与 Qwen 的字错误率 < 30 % 的 5,049,806 条 / 15909.1 h（占可转写 5,592,487 条的 90.3 %），规则同 wenetspeech_chuan@clean-qwen3-asr-v1-20261023；原标注不改，不拿 Qwen 的文字替换。每行保留 custom.qwen_asr（Qwen 转写、语种、CER），与 wenetspeech_yue@nonclean-qwen3-asr-full-v1-20261025 中的相同；被去掉的条目和全部转写见 wenetspeech_yue@nonclean-qwen3-asr-full-v1-20261025。粤语保留规则沿用川渝（CER < 30 %），未单独听审。录音沿用父版本，不复制音频。脚本 scripts/wenetspeech_qwen/
- 含派生版本（与源数据可能重叠）

## 混合语言及多语数据

### BAAI/CS-Dialogue long_wav (ModelScope master)

中英语码转换双人对话（CS-Dialogue）

语言：en、zh、zh-en · 任务：语音识别、带说话人标注的语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [cs_dialogue@clean-dual-qwen-moss-v1-20261009](../../catalog/zh_source_clean_20261009.yaml#L664) | 30.0 | 已登记 | 没有 |
| [cs_dialogue@icefall-20260908](../../catalog/icefall_runtime.yaml#L2042) | 46.0 | 已登记 | 快照 20260914 |
| [cs_dialogue@legacy-20260804](../../catalog/icefall_base.yaml#L1636) | 46.0 | 已登记 | 快照 20260914 |
| [cs_dialogue@long-mix-v1-20261010](../../catalog/zh_dialogue.yaml#L1) | 98.3 | 已登记 | 没有 |
| [cs_dialogue@punc-written-v1-20261029](../../catalog/zh_punc_written_v1.yaml#L411) | 30.0 | 已登记 | 没有 |

- `cs_dialogue@clean-dual-qwen-moss-v1-20261009`：cs_dialogue@icefall-20260908 的 train 监督片段，经 Qwen3-ASR-1.7B 与 MOSS-Transcribe-Diarize 双引擎一致性清洗（与 2026-10-08 的 primewords、aishell3、aidatatang、magicdata、magicdata_ramc 同一流程）；逐条写入 custom.clean（pass、reason、action、engine_status、两引擎各自和互相的 CER、MOSS 说话人段），不删除记录，读取时按 require_clean_pass 过滤。音频沿用源版本，不复制。规则 consensus-v6 / wenetspeech-faithful-v5：13992 条中 pass 13948、reject 44。少于 2 个字的 too_short 共 3265 条按规则不经引擎直接 pass。restore_disfluency 改写了 165 条的 text（原文留在 custom.original_text）；无标点清单另把 13986 条的标点和撇号去掉。引擎原始结果和复核清单在 evidence/。脚本 scripts/zh_source_clean/register_clean_dual.py
- `cs_dialogue@punc-written-v1-20261029`：cs_dialogue@icefall-20260908 训练集原标注加书面化标点（GB/T 15834，逗号从紧）：微调后的 Qwen3-4B（Qwen3.8-27B 的 9.6 万条输出蒸馏）以 Qwen3-ASR-1.7B 听音频得到的带标点转写作语气提示，只往原标注里插标点。模型改动了原文的条目，把模型输出的标点按字对齐搬回原标注；每条以 。？！ 结尾；原标注的字、空格（首尾除外）和大小写不变。没有汉字的条目（英文句子、拼读字母）和标注为空的条目原样保留。文件与源 supervisions 条数、顺序相同，只换 text。试点 200 条人工参照上：WenetSpeech markF1 92.4、其他来源 88.9（老师 93.2 / 88.2，原 FireRedPunc 79.8）。原标注自带的人工标点（每 100 字约 9.4 个）和 <FIL/>、<SPK/> 等标签：标点按新规范重加，标签原样保留，标点可能紧挨标签
- 含派生版本（与源数据可能重叠）

### ami

英文会议远场版（AMI SDM）；含轮流说话混合版

语言：en、zh · 任务：语音识别、说话人分段与归属、目标说话人语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [ami@diarization-benchmark-v1-20261021](../../catalog/diarization_benchmark.yaml#L206) | 11.8 | 已登记 | 没有 |
| [ami_sdm@asr-20261014](../../catalog/amphionasr_v4.yaml#L1219) | — | 未登记 | 没有 |
| [ami_sdm@asr-20261014-punc-20261102](../../catalog/train_punc_v1_derived.yaml#L2) | — | 未登记 | 没有 |
| [ami_sdm@icefall-20260908](../../catalog/icefall_runtime.yaml#L2916) | 92.1 | 已登记：单远场麦克风标注片段 | 快照 20260914 |
| [ami_sdm@turn-taking-20261014](../../catalog/amphionasr_v4.yaml#L871) | 259.3 | 已登记 | 没有 |
| [ami_sdm@turn-taking-20261014-utts](../../catalog/ts_window_utts.yaml#L228) | 45.4 | 已登记 | 没有 |
| [ami_sdm@turn-taking-20261014-utts-punc-20261102](../../catalog/train_punc_v1_derived.yaml#L65) | — | 未登记 | 没有 |

- `ami@diarization-benchmark-v1-20261021`：Frozen local evaluation slice; audio and RTTM bytes copied unchanged. Not a claim of official release equivalence or training disjointness.
- `ami_sdm@asr-20261014`：会议普通转写。每条 supervision 一条，时长 0.5～30 秒，文本非空。多通道只取第 0 路
- `ami_sdm@asr-20261014-punc-20261102`：ami_sdm@asr-20261014 的 train，目标文本加书面化标点：中文用 amphiondata 的中文学生模型（punc-student-v1，不带听音提示），英文用英文规范 en-v1 的学生模型（加标点并恢复大小写）；标点按字 / 按词搬回原文，原文的字词不变，找不到输出的目标保留原样。其余字段与源版本相同，音频引用源版本
- `ami_sdm@icefall-20260908`：标注片段时长，重叠语音或多麦克风可能重复计时。训练集缺少 2 场会议（134/136）
- `ami_sdm@turn-taking-20261014`：会议 turn-taking。整句拼成 2/3 人混合窗，时长 0.5～30 秒。注册音是窗外另一句，1～30 秒。有近场时远场:近场 = 3:1
- `ami_sdm@turn-taking-20261014-utts`：ami_sdm@turn-taking-20261014 的 train 划分（不含 eval/test），时间线取自 ami_sdm@icefall-20260908 的 train 人工标注。加 metadata.window_utts（窗口内每句的说话人与相对混合起点的起止，取自来源标注并截到窗口，截断的标 clipped）与同一命名空间的 metadata.target_speaker，供 open-audio-llm 帧级说话人活动标签（objective.ts_activity_weight）；其余字段不变，音频引用改指本版本，音频索引与原版逐行相同。正样本的目标语句与转写逐字一致（忽略空白和标点；窗口边缘截断的句子允许只转写一部分）才写时间线，负样本只有注册人确实不在窗口里说话才写；其余记录不写时间线（不出帧级标签）。负样本中注册人按标注其实在窗口内说话的记录 ID 列在 excluded-records-<split>.txt，训练配方用 exclude_records 排除。生成脚本 audio-data-contract scripts/ts_robust/add_window_utts.py，逐划分统计见 report.json
- `ami_sdm@turn-taking-20261014-utts-punc-20261102`：ami_sdm@turn-taking-20261014-utts 的 train_2spk, train_3spk, train_neg，目标文本加书面化标点：中文用 amphiondata 的中文学生模型（punc-student-v1，不带听音提示），英文用英文规范 en-v1 的学生模型（加标点并恢复大小写）；标点按字 / 按词搬回原文，原文的字词不变，找不到输出的目标保留原样。其余字段与源版本相同，音频引用源版本
- 含派生版本（与源数据可能重叠）

### asr_babble_bench

普通 ASR 背景人声评测集（中英），仅评测

语言：en、es、zh · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [asr_babble_bench@es-v1-20261111](../../catalog/asr_babble_bench.yaml#L1019) | 4.2 | 已登记 | 没有 |
| [asr_babble_bench@v1-20261023](../../catalog/asr_babble_bench.yaml#L1) | 10.1 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/asr_babble_bench/` |
| [asr_babble_bench@v2-20261023](../../catalog/asr_babble_bench.yaml#L399) | 8.8 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/asr_babble_bench/` |
| [asr_babble_bench@v3-20261104](../../catalog/asr_babble_bench.yaml#L757) | 1.9 | 已登记 | 没有 |

- `asr_babble_bench@es-v1-20261111`：西班牙语普通 ASR 背景人声评测集（对应中英 v2-20261023 的背景人声切分，同一渲染函数与参数）：只有西语背景人声的片段（期望输出为空）， 以及一句话前后和说话时都有西语背景人声的片段（与无背景人声的对照逐条配对）。目标语音是 Common Voice es test 的一句话； 背景人声由不进训练、也不与目标重叠的 Common Voice es dev（约 3,200 人）和 MLS es dev / test（40 人）说话人在模拟房间里混成 （训练用的西语背景人声 babble_noise_train@es-v1-20261110 取自 CV es / MLS es 的 train）。只用于评测，不进训练。 配方 scripts/asr_babble_bench/recipe-es.yaml
- `asr_babble_bench@v1-20261023`：普通 ASR 背景人声评测集：只有背景人声的片段（合成的中文、英文背景人声和真实录音的人群声，期望输出为空），以及一句话前后和说话时都有背景人声的片段（与无背景人声的对照逐条配对）。合成背景人声由不进训练、也不与目标语音重叠的 test/dev 说话人混成。只用于评测，不进训练。配方 scripts/asr_babble_bench/recipe.yaml
- `asr_babble_bench@v2-20261023`：普通 ASR 背景人声评测集：只有背景人声的片段（合成的中文、英文背景人声和真实录音的人群声，期望输出为空），以及一句话前后和说话时都有背景人声的片段（与无背景人声的对照逐条配对）。合成背景人声由不进训练、也不与目标语音重叠的 test/dev 说话人在模拟房间里混成。只用于评测，不进训练。配方 scripts/asr_babble_bench/recipe.yaml
- `asr_babble_bench@v3-20261104`：普通 ASR 空白 / 非人声评测切分（参考全部为空，看误输出率）：鼎桥设备真实录音里三个说话人老师（local-moss, moss-pro, ali）都判为无人说话、FSMN-VAD 也未检出语音的区间（按时长分四档，原电平）；合成的近静音、底噪、50 Hz 电流嗡声；FSD50K 评测划分的稳态噪声、突发声、咳嗽呼吸（不含人声和音乐）；0.3–1.5 秒混合短片段。自动质检隔离 301 条（tdtech-quarantine），未发起人工听审。只用于评测，不进训练。配方 scripts/asr_babble_bench/recipe-blank.yaml；原 16 个背景人声切分仍在 v2-20261023

### asr_babble_speech_pool

带房间背景人声的中英 ASR 训练句

语言：en、es、zh · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [asr_babble_speech_pool@es-v1-20261110](../../catalog/asr_babble_speech_pool.yaml#L90) | 33.8 | 已登记 | 没有 |
| [asr_babble_speech_pool@v1-20261024](../../catalog/asr_babble_speech_pool.yaml#L1) | 85.5 | 已登记 | 没有 |
| [asr_babble_speech_pool@v1-20261024-punc-20261102](../../catalog/train_punc_v1_derived.yaml#L939) | — | 未登记 | 没有 |

- `asr_babble_speech_pool@es-v1-20261110`：西班牙语普通 ASR 语句前后与下方叠加房间背景人声（对应 v1-20261024 的 zh / en，同一渲染参数）：目标是 common_voice_es@es-train-v1-20261108 train 的一句（1–15 s，书面化文本），前后各 0–5 s 背景人声、语句下方 0–20 dB SNR；80% 用西语背景人声（babble_noise_train@es-v1-20261110），20% 随机用中文或英文的（v2-20261024）。12,000 条 / 33.8 h。脚本 scripts/ts_robust/build_babble_speech_pool.py --languages es
- `asr_babble_speech_pool@v1-20261024`：普通 ASR 语音前后和说话时都有房间背景人声（babble）：每条是一句训练划分的话（中文 AISHELL-2、KeSpeech train，英文 LibriSpeech train；1–15 秒，剔除与 asr_babble_bench 目标句同文本的句子），前后各 0–5 秒背景人声，说话时背景人声信噪比 0–20 dB（在说话区间内计算），语音电平 −35 到 −18 dBFS，加 −65 到 −55 dBFS 的白/粉红噪声底；背景人声取自 babble_noise_train@v2-20261024（80% 同语言，不用该说话人在其中说话的片段）。目标为该句原文。与 ts_nonspeech_pool@babble-20261024（只有背景人声、目标为空）配对使用，教模型背景人声中间的话照常转写。中英文各 12,000 条。脚本 scripts/ts_robust/build_babble_speech_pool.py
- `asr_babble_speech_pool@v1-20261024-punc-20261102`：asr_babble_speech_pool@v1-20261024 的 en, zh，目标文本加书面化标点：中文用 amphiondata 的中文学生模型（punc-student-v1，不带听音提示），英文用英文规范 en-v1 的学生模型（加标点并恢复大小写）；标点按字 / 按词搬回原文，原文的字词不变，找不到输出的目标保留原样。其余字段与源版本相同，音频引用源版本
- 含派生版本（与源数据可能重叠）

### asr_distant_talk_pool

—

语言：en、zh · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [asr_distant_talk_pool@v1-20261102](../../catalog/asr_distant_talk_pool.yaml#L1) | 55.2 | 已登记 | 没有 |
| [asr_distant_talk_pool@v1-20261102-punc-20261102](../../catalog/train_punc_v1_derived.yaml#L1034) | — | 未登记 | 没有 |

- `asr_distant_talk_pool@v1-20261102`：普通 ASR 用的「远处背景人声」训练池：把真实对话（中文 MagicData-RAMC train，英文 ICSI 非评测会议的耳麦混音）渲染成房间另一头的说话声，约 30% 片段同时有两段对话；SLR28 模拟房间冲激响应（中、大房间）并削弱直达声 0–15 dB，高频衰减，叠真实会议室底噪，信噪比 −8 到 8 dB，帧级 p95 −36 到 −21 dBFS。目标不由渲染决定：由基线 Qwen3-ASR-1.7B 与 FireRedASR2-AED 独立转写，对照原转写判定。empty_*：两者都跟不上（都为空，或都偏离原转写且彼此不一致），目标为空；text_*：两者都接近原转写（字错率不超过 0.3），目标为原转写，作为对照，防止安静的真实远场语音也被学成空。其余丢弃。脚本 scripts/ts_robust/{build,label,finalize}_distant_talk_pool.py
- `asr_distant_talk_pool@v1-20261102-punc-20261102`：asr_distant_talk_pool@v1-20261102 的 empty_en, empty_zh, text_zh，目标文本加书面化标点：中文用 amphiondata 的中文学生模型（punc-student-v1，不带听音提示），英文用英文规范 en-v1 的学生模型（加标点并恢复大小写）；标点按字 / 按词搬回原文，原文的字词不变，找不到输出的目标保留原样。其余字段与源版本相同，音频引用源版本
- 含派生版本（与源数据可能重叠）

### babble_noise_synth

合成中英背景人声噪声（5–20 人叠加）

语言：en、zh · 任务：noise

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [babble_noise_synth@v1-20261013](../../catalog/babble_noise_synth.yaml#L1) | 50.0 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/noise_open/` |

- `babble_noise_synth@v1-20261013`：合成背景人声（babble）噪声：每条 30 秒，叠加 5–20 个不同说话人，中英文各 3000 条（train 2600、dev 200、test 200）；train/dev/test 的说话人互不重叠。每条的说话人、增益和来源句子见 manifest.jsonl

### babble_noise_train

训练用合成背景人声噪声（中英）

语言：en、es、zh · 任务：noise

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [babble_noise_train@es-v1-20261110](../../catalog/babble_noise_train.yaml#L106) | 25.0 | 已登记 | 没有 |
| [babble_noise_train@v1-20261017](../../catalog/babble_noise_train.yaml#L1) | 43.3 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/babble_noise_train/` |
| [babble_noise_train@v2-20261024](../../catalog/babble_noise_train.yaml#L51) | 50.0 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/babble_noise_train/` |

- `babble_noise_train@es-v1-20261110`：训练用西班牙语房间背景人声（babble）：与 v2-20261024 同一渲染函数与参数（30 秒、16–24 人同时说话、SLR28 中/大模拟房间），说话人取自 Common Voice es（es-train-v1-20261108）与 MLS es train。只有 es 划分；用作普通 ASR 空目标片段（ts_nonspeech_pool babble）和背景人声语音池（asr_babble_speech_pool）的来源。脚本 scripts/ts_robust/build_babble_noise_room.py --languages es
- `babble_noise_train@v1-20261017`：训练用合成背景人声（babble）：babble_noise_synth 的 zh、en 训练划分（每种语言 2,600 条，30 秒，5–20 位说话人同时说，16 kHz 单声道 FLAC），按 Lhotse 录音清单登记，可作为 noise_sources 或空目标的 nonspeech_sources。评测的 babble 用 dev/test 说话人，与训练说话人互不重叠。脚本 scripts/ts_robust/register_babble_noise.py
- `babble_noise_train@v2-20261024`：训练用房间背景人声（babble）：按 asr_babble_bench@v2-20261023 的合成方法（同一个渲染函数）用训练划分的说话人生成，每段 30 秒、16–24 人同时连续说话、每人站在 SLR28 中/大模拟房间的不同位置，听不出某一个人说的内容；中文说话人取自 AISHELL-2、KeSpeech train，英文取自 LibriSpeech train，与评测的背景人声和目标说话人互不重叠。按 Lhotse 录音清单登记，可作为 noise_sources、nonspeech_sources 或普通 ASR 空目标片段的来源。v1-20261017 是 5–20 人、无混响，可能听得清某句话。脚本 scripts/ts_robust/build_babble_noise_room.py

### cs_dialogue_meeting_sot

CS-Dialogue 中英对话切窗的按人转写数据

语言：zh、zh-en · 任务：带说话人标注的语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [cs_dialogue_meeting_sot@meeting-v1-20261010](../../catalog/zh_dialogue.yaml#L88) | — | 未登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/cs_dialogue_meeting_sot/` |
| [cs_dialogue_meeting_sot@similar-voice-v1-20261014](../../catalog/similar_voice.yaml#L543) | — | 未登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/cs_dialogue_meeting_sot/` |

- `cs_dialogue_meeting_sot@similar-voice-v1-20261014`：cs_dialogue_meeting_sot@meeting-v1-20261010 的“音色相近”子集：每个训练窗口里最相近两位说话人的声纹余弦相似度，各划分（窗口长度）取前 1/3。声纹模型 ERes2NetV2（iic/speech_eres2netv2_sv_zh-cn_16k-common），每人取不与他人重叠的语音（片段 ≥0.3 秒，合计 ≥1.5 秒，最多 10 秒）；30/300/600 秒窗口用对应 120 秒窗口里同一说话人的声纹均值。少于两个有声纹说话人的窗口不入选。标注不改，记录逐行照抄源版本，音频仍指向源版本。源版本训练排除名单里的记录（选模留出集、目标为空窗口）已剔除。用途：下一轮训练额外加采相近音色的窗口

### cs_dialogue_mix

CS-Dialogue 对话中的中英混说语句

语言：en、zh · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [cs_dialogue_mix@clean-dual-qwen-moss-v1-20261009](../../catalog/zh_source_clean_20261009.yaml#L824) | 20.9 | 已登记 | 没有 |
| [cs_dialogue_mix@icefall-20260908](../../catalog/icefall_runtime.yaml#L2170) | 31.0 | 已登记 | 快照 20260914 |
| [cs_dialogue_mix@legacy-20260804](../../catalog/icefall_base.yaml#L1768) | 31.0 | 已登记 | 快照 20260914 |

- `cs_dialogue_mix@clean-dual-qwen-moss-v1-20261009`：cs_dialogue_mix@icefall-20260908 的 train 监督片段，经 Qwen3-ASR-1.7B 与 MOSS-Transcribe-Diarize 双引擎一致性清洗（与 2026-10-08 的 primewords、aishell3、aidatatang、magicdata、magicdata_ramc 同一流程）；逐条写入 custom.clean（pass、reason、action、engine_status、两引擎各自和互相的 CER、MOSS 说话人段），不删除记录，读取时按 require_clean_pass 过滤。音频沿用源版本，不复制。规则 consensus-v6 / wenetspeech-faithful-v5：4953 条中 pass 4941、reject 12。少于 2 个字的 too_short 共 2 条按规则不经引擎直接 pass。restore_disfluency 改写了 65 条的 text（原文留在 custom.original_text）；无标点清单另把 4953 条的标点和撇号去掉。引擎原始结果和复核清单在 evidence/。脚本 scripts/zh_source_clean/register_clean_dual.py
- 含派生版本（与源数据可能重叠）

### cumix2017

粤英语码转换语音（CUMIX2017）

语言：en、yue · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [cumix2017@icefall-20260908](../../catalog/icefall_runtime.yaml#L2235) | 10.9 | 已登记 | 快照 20260914 |
| [cumix2017@legacy-20260804](../../catalog/icefall_base.yaml#L1834) | 10.9 | 已登记 | 快照 20260914 |

- 含派生版本（与源数据可能重叠）

### emilia

多语种视频野外语音（Emilia）；含精修文本版

语言：de、en、fr、ja、ko、zh · 任务：语音识别、语音合成

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [emilia@refined-metadata-20261010](../../catalog/emilia_refined.yaml#L1) | 78,091.0 | 已登记 | 没有 |
| [emilia@tts-unified-v0.1](../../catalog/tts_unified.yaml#L86) | 101,655.6 | 已登记 | `amphion-tts-data-1373259071:Emilia/`（原始数据） |

- `emilia@refined-metadata-20261010`：TTS 团队对 Emilia 的文本精修元数据，只含文本、时间戳和质量分数，不含音频；音频按 id 从 emilia@tts-unified-v0.1 读取。统计值取 final（31275879 条、78091.0 小时）；refined_full 覆盖全部 101655.6 小时
- `emilia@tts-unified-v0.1`：音频编码字节存放在 Lance 表内；原始划分在 metadata_json.original_split，统一输出全部为 train。ASR 用 tts_lance.iter_asr_samples（tts-asr-rules/v1）读取，会排除原始 dev/test 等
- 含派生版本（与源数据可能重叠）

### emilia2

多语种视频野外语音（Emilia2）；含中英解包版

语言：ar、as、bn、cs、da、de、el、en、es、fa、fi、fil、fr、gu、hi、hu、it、ja、kn、ko、mk、ml、mr、ne、nl、pa、pl、pt、ro、ru、sa、sd、sv、ta、te、th、tr、ur、vi、yue、zh · 任务：语音识别、diarization、语音合成

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [emilia2@extracted-enzh-flac16k-20261012](../../catalog/emilia2_extracted.yaml#L140) | — | 未登记 | 没有 |
| [emilia2@tts-unified-v0.1](../../catalog/tts_unified.yaml#L178) | 146,325.0 | 已登记 | `amphion-tts-data-1373259071:Emilia2/`（原始数据） |

- `emilia2@extracted-enzh-flac16k-20261012`：基于 extracted-enzh-20261012 的 dialog 和 long（standalone short 已在 emilia2@tts-unified-v0.1 中，不转）：每个 m4a 用与 DATA-TTS-UNIFIED Emilia2 接入相同的 FFmpeg 7.0.2 静态版完整解码（应用 edit list）， soxr 重采样到 16 kHz 单声道，按 round(gain*x*32768) 量化为 FLAC PCM16，峰值超出时整条降增益、不削波，写后逐样本回读核对。 目的：训练读取可随机跳转、不依赖 ffmpeg（原 m4a 读一个 120 秒窗口需 1–5 秒，16 kHz FLAC 约 0.03–0.3 秒）。 这份解包数据不用于 TTS（TTS 用 emilia2@tts-unified-v0.1）。 2026-10-17 转码完成：2,101,933 个文件、112,444 h 全部成功，FLAC 共 7.29 TB，20,240 个降了增益（最小 0.64）。 2026-10-18 删除原 m4a：逐个核对 FLAC 字节数与帧数后删除，保留 23 个仍被训练读取的 m4a（见 extracted-enzh-20261012 的 m4a_removed）。 emilia2_mix、emilia2_dialog、emilia2_zh_dialogue_diarize 的音频索引仍写 .m4a 路径，open-audio-llm（#63 起）读取时自动改读同名 .flac； 其他读取方需要自行把路径换成 .flac
- `emilia2@tts-unified-v0.1`：音频编码字节存放在 Lance 表内；原始划分在 metadata_json.original_split，统一输出全部为 train。ASR 用 tts_lance.iter_asr_samples（tts-asr-rules/v1）读取，会排除原始 dev/test 等
- 已并入的旧版本：`emilia2@extracted-enzh-20261012`（COS：没有）

### emilia2_dialog

Emilia2 中英对话的轮流说话目标说话人数据

语言：en、zh · 任务：目标说话人语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [emilia2_dialog@dialog-turn-taking-20261013-enroll](../../catalog/amphionasr_v4.yaml#L1713) | 15,172.8 | 已登记 | 没有 |
| [emilia2_dialog@dialog-turn-taking-20261013-enroll-ctxclean-20261110](../../catalog/context_correction_clean_zh.yaml#L1259) | 15,031.0 | 已登记 | 没有 |

- `emilia2_dialog@dialog-turn-taking-20261013-enroll`：Emilia2 对话 turn-taking。turn 时间戳来自 dialog tar，音频用 m4a-128k。只保留纯中文或纯英文。混合窗 1～30 秒。注册是同一说话人的连续整句，1～30 秒，按 5 秒分档抽取，正负样本分开保留
- `emilia2_dialog@dialog-turn-taking-20261013-enroll-ctxclean-20261110`：在 emilia2_dialog@dialog-turn-taking-20261013-enroll 上做的上下文纠偏清洗：说话人讲字怎么写（组词、拆字、偏旁、否定对比）而标注写成同音别字的，按说明改正；拿不准的整条去掉。判定依据见 context_correction_clean_zh@v1-20261110。标注是机器转写。音频是多人混合，Qwen3-ASR 核对时只数标注里没被听到的音节（插话、笑声不算），音频读同名 16 kHz FLAC。改正 38 条记录（0.25 h）、隔离 184 条（1.15 h，2026-11-12 捞回 16 条）；另去掉 ts_asr_real 留出的评测源录音 23,653 条（140.6 h）
- 含派生版本（与源数据可能重叠）

### emilia2_mix

Emilia2 长音频合成的 2/3 人目标说话人混合

语言：en、zh · 任务：目标说话人语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [emilia2_mix@mix-20261013](../../catalog/amphionasr_v4.yaml#L2084) | 35,744.6 | 已登记 | 没有 |
| [emilia2_mix@mix-20261013-ctxclean-20261110](../../catalog/context_correction_clean_zh.yaml#L1754) | 35,692.0 | 已登记 | 没有 |
| [emilia2_mix@mix-20261013-utts](../../catalog/ts_window_utts.yaml#L428) | 24,358.4 | 已登记 | 没有 |

- `emilia2_mix@mix-20261013`：Emilia2 long 合成的 2/3 人混合。目标可以晚开口、按 1～15 秒间隔断续，或在中间短插入。干扰人也可以断续。注册是同一录音上没用过的 1～30 秒片段
- `emilia2_mix@mix-20261013-ctxclean-20261110`：在 emilia2_mix@mix-20261013 上做的上下文纠偏清洗：说话人讲字怎么写（组词、拆字、偏旁、否定对比）而标注写成同音别字的，按说明改正；拿不准的整条去掉。判定依据见 context_correction_clean_zh@v1-20261110。音频核对读混音协议里目标说话人的干净原片段
- `emilia2_mix@mix-20261013-utts`：emilia2_mix@mix-20261013 的 train_2spk / train_3spk（不含 eval/test/train_neg），时间线取自混音协议 datasets/emilia2-mix/versions/mix-20261013/supervision/protocol-*.jsonl.gz（每个说话人每段在混音中的起点与时长）。加 metadata.window_utts（窗口内每句的说话人与相对混合起点的起止，取自来源标注并截到窗口，截断的标 clipped）与同一命名空间的 metadata.target_speaker，供 open-audio-llm 帧级说话人活动标签（objective.ts_activity_weight）；其余字段不变，音频引用改指本版本，音频索引与原版逐行相同。正样本的目标语句与转写逐字一致（忽略空白和标点；窗口边缘截断的句子允许只转写一部分）才写时间线，负样本只有注册人确实不在窗口里说话才写；其余记录不写时间线（不出帧级标签）。负样本中注册人按标注其实在窗口内说话的记录 ID 列在 excluded-records-<split>.txt，训练配方用 exclude_records 排除。生成脚本 audio-data-contract scripts/ts_robust/add_window_utts.py，逐划分统计见 report.json
- 含派生版本（与源数据可能重叠）

### emilia2_short

Emilia2 中英短音频普通转写

语言：en、zh · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [emilia2_short@short-20261014](../../catalog/amphionasr_v4.yaml#L2457) | 5,102.9 | 已登记 | 没有 |
| [emilia2_short@short-lance-20261023](../../catalog/amphionasr_v4.yaml#L3911) | 5,102.9 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/emilia2_short/` |
| [emilia2_short@short-lance-20261023-ctxclean-20261110](../../catalog/context_correction_clean_zh.yaml#L1667) | 5,096.7 | 已登记 | 没有 |

- `emilia2_short@short-20261014`：Emilia2 已抽出的 m4a-128k short。每条短音频是一条普通转写，只保留语言标签为纯中文或纯英文、时长 0.5～30 秒的片段。不使用 m4a-64k 和 asmr
- `emilia2_short@short-lance-20261023`：与 short-20261014 相同的记录与记录 ID，音频改读 emilia2@tts-unified-v0.1 Lance 发布里的同一条 m4a-128k standalone short（按上游 short ID 与 m4a 文件名对应；发布里存的是同一份完整解码的 FLAC），训练不再为这些片段启动 ffmpeg。音频引用写入 Lance 样本时长。Lance 中没有对应样本的 20 条（zh 11、en 9）已去掉。全部片段都在 Lance 里，没有音频索引，因此也没有 Lance 记录索引，训练端走 JSONL 记录缓存；读取需要 open-audio-llm 支持指向其他数据集 Lance 发布的音频引用（code-v14 起）。生成脚本 scripts/build_emilia2_short_lance.py
- `emilia2_short@short-lance-20261023-ctxclean-20261110`：在 emilia2_short@short-lance-20261023 上做的上下文纠偏清洗：说话人讲字怎么写（组词、拆字、偏旁、否定对比）而标注写成同音别字的，按说明改正；拿不准的整条去掉。判定依据见 context_correction_clean_zh@v1-20261110。标注是机器转写；音频核对读 Lance 发布里的同一段。与原版本一样没有音频索引和记录索引，训练端走 JSONL 记录缓存
- 含派生版本（与源数据可能重叠）

### emilia_yodas

Emilia-YODAS 多语种 YouTube 语音

语言：de、en、fr、ja、ko、zh · 任务：语音识别、语音合成

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [emilia_yodas@tts-unified-v0.1](../../catalog/tts_unified.yaml#L296) | 113,820.6 | 已登记 | `amphion-tts-data-1373259071:Emilia-YODAS/`（原始数据） |

- `emilia_yodas@tts-unified-v0.1`：音频编码字节存放在 Lance 表内；原始划分在 metadata_json.original_split，统一输出全部为 train。ASR 用 tts_lance.iter_asr_samples（tts-asr-rules/v1）读取，会排除原始 dev/test 等

### farfield_speech_noise_1spk

1–3 人远场人声噪声（Emilia 干声加混响）

语言：en、zh · 任务：noise

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [farfield_speech_noise_1spk@20261014](../../catalog/amphionasr_v4.yaml#L3304) | 25.5 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/farfield_speech_noise_1spk/` |
| [farfield_speech_noise_2spk@20261014](../../catalog/amphionasr_v4.yaml#L3433) | 30.4 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/farfield_speech_noise_2spk/` |
| [farfield_speech_noise_3spk@20261014](../../catalog/amphionasr_v4.yaml#L3562) | 32.7 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/farfield_speech_noise_3spk/` |

- `farfield_speech_noise_1spk@20261014`：单人远场人声噪声。Emilia 中文或英文干声卷上一条远场房间冲激响应，16 kHz 单声道
- `farfield_speech_noise_2spk@20261014`：两人远场人声噪声。由两条不同说话人的 1spk 音频错开开口时间后叠加
- `farfield_speech_noise_3spk@20261014`：三人远场人声噪声。由三条不同说话人的 1spk 音频错开开口时间后叠加
- 含派生版本（与源数据可能重叠）

### genshin_voice

《原神》多语配音，TTS 用

语言：en-US、ja、ko、zh · 任务：语音合成

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [genshin_voice@tts-unified-v0.1](../../catalog/tts_unified.yaml#L410) | 1,039.7 | 已登记 | `amphion-tts-data-1373259071:genshin-voice/`（原始数据） |

- `genshin_voice@tts-unified-v0.1`：音频编码字节存放在 Lance 表内；原始划分在 metadata_json.original_split，统一输出全部为 train。ASR 用 tts_lance.iter_asr_samples（tts-asr-rules/v1）读取，会排除原始 dev/test 等

### hard_hw_sft

热词难例 SFT 数据（ShareGPT 格式）

语言：en、zh · 任务：热词增强语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [hard_hw_sft@hard-20261014](../../catalog/amphionasr_v4.yaml#L2600) | 109.4 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/hard_hw_sft/` |

- `hard_hw_sft@hard-20261014`：热词难例 ShareGPT。每条系统提示都带 Hotwords。音频指向已注册源文件

### hotword_bench

中英热词评测集，仅评测

语言：en、es、zh · 任务：热词增强语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [hotword_bench@es-v1-20261111](../../catalog/hotword_bench.yaml#L1284) | — | 未登记 | 没有 |
| [hotword_bench@v1-20261018](../../catalog/hotword_bench.yaml#L1) | — | 未登记 | 没有 |
| [hotword_bench@v2-20261019](../../catalog/hotword_bench.yaml#L386) | — | 未登记 | 没有 |
| [hotword_bench@v3-20261020](../../catalog/hotword_bench.yaml#L774) | — | 未登记 | 没有 |

- `hotword_bench@es-v1-20261111`：西语热词评测集，对应中英 v3-20261020 的 cv_zh / cv_en，只用于评测，不进训练。三个西语测试集（Common Voice es、FLEURS es、MLS es）里含热词的句子，热词沿用已有标注（ts_asr_hotwords@es-v1-20261111 hotword-labels.jsonl，Qwen3.8-27B 抽取 + 复核）。每条记录存好固定的热词列表（metadata.bias_lists，已打乱顺序），评测器另跑不给列表的 none 条件：gold；k50 = 正确词 + 每个正确词最多 3 个近音词 + 同 split 正确词池随机词，补到 50 个；k50_no_gold 为同一批干扰词去掉正确词再补满。近音词是在 119,323 个西语热词（测试集正确词 + 西语训练集热词标注）里按西语读音键的编辑距离检索出的真实词（只用 CPU，不经 LLM），原始候选见 source/es-v1-20261111/mined/confusables.jsonl。生成脚本 scripts/hotword_bench/build_es.py，配方 recipe-es-v1.yaml
- `hotword_bench@v1-20261018`：热词评测集，只用于评测，不进训练。每条记录存好固定的热词列表（metadata.bias_lists，已打乱顺序），评测器另跑不给列表的 none 条件。中文列表 = 正确词 + doubao-seed-2-1-pro-260915 生成、deepseek-v4-pro-ga-260813 复核的易混词 + 同 split 热词池随机词，补到 50 个；*_no_gold 为同一批干扰词去掉正确词。AISHELL1-NE、LibriSpeech 另含官方列表。生成脚本 scripts/hotword_bench/
- `hotword_bench@v2-20261019`：热词评测集 v2，只用于评测，不进训练。记录、音频、正确词和其余条件与 v1-20261018 相同；中文切片的 k50 / k50_no_gold 换成从热词池检索的 pool50 / pool50_no_gold： 每个租户（约 200 句，按子集 / 领域语料分组）一个池 = 现网中文万词库（由现网 RAG 返回结果还原，8841 词）+ 租户句子的正确词及其复核易混词；以参考文本为查询，按 open-audio-llm 规则召回的打分公式取得分最高的 50 个（不设阈值）。pool50 = 正确词 + 检索出的干扰词，pool50_no_gold = 检索出的前 50 个干扰词；metadata.distractor_kinds 标出 confusable / tenant / base。各租户的池在 hotword-pools.jsonl.gz。生成脚本 scripts/hotword_bench/pool.py
- `hotword_bench@v3-20261020`：热词评测集 v3，只用于评测，不进训练。记录、音频、正确词和全部列表与 v2-20261019 相同（请求逐条一致，总指标可与 v2-20261019 直接比较），另加两种标签： metadata.hotword_types 为每个正确词按所在句子的意思标的类型（person / place / organization / product / work / term / other / common），contextasr_speech_zh 的 labels.domain_group 把 ContextASR 自带的自由文本领域归到 13 个大类，自由文本领域本身从 labels.domain 移到 metadata.domain （评测器按每个字符串标签分项，3,957 种取值会让 summary 超过 W&B 的 10 MB 上限）。doubao-seed-2-0-lite-260215 标注，deepseek-v4-pro-ga-260813 看着标注复核并以复核为准（类型复核后不变的占 98.5%）。生成脚本 scripts/hotword_bench/annotate.py，类型定义见 prompts.py

### hw_sft

热词 SFT 数据（ShareGPT 格式），含普通转写

语言：en、zh · 任务：语音识别、热词增强语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [hw_sft@hw-20261014](../../catalog/amphionasr_v4.yaml#L2719) | 2,636.5 | 已登记 | 没有 |

- `hw_sft@hw-20261014`：阶段 3 热词 ShareGPT。带 Hotwords 的行是热词转写，系统提示为空的行是普通转写。音频指向已注册源文件

### indicvoices

22 种印度语言自然语音（IndicVoices）

语言：as、bn、brx、doi、gu、hi、kn、kok、ks、mai、ml、mni、mr、ne、or、pa、sa、sat、sd、ta、te、ur · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [indicvoices@hf-c96f9088f138](../../catalog/multilingual_multispeaker.yaml#L164) | — | 未登记 | 快照 20260914 |

### meeting_benchmark

约 180 秒长度的中英会议转写评测集

语言：en、zh、zh-en · 任务：带说话人标注的语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [meeting_180s_benchmark@v1-20261008](../../catalog/meeting_180s_benchmark.yaml#L1) | 21.2 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/meeting_180s_benchmark/` |

- `meeting_180s_benchmark@v1-20261008`：部署长度（约 180 秒）会议转写评测集：AISHELL-4 test、AliMeeting Test、AMI SDM test 各会议均匀取 6 个窗口，另有中文 / 英文 / 中英混合 6、8、10 人远场合成会议各 10 段；共 424 段 21.2 小时。仅用于评测

### meeting_selection_panel

会议模型选模面板（中英真实会议）

语言：en、zh · 任务：带说话人标注的语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [meeting_selection_panel@v1-20261008](../../catalog/meeting_selection_panel.yaml#L1) | 12.4 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/meeting_selection_panel/` |

- `meeting_selection_panel@v1-20261008`：独立会议选模面板：AliMeeting 官方 Eval 8 场全部 120 秒窗口（中文）、NOTSOFAR 官方 dev 36 场每场一台设备的全部 120 秒窗口（英文 3–7 人）、CHiME-6 官方 dev 2 场全部 120 秒窗口（英文晚宴，仅报告）。不进训练，不按难度筛选

### mls_sidon

8 种语言有声书，音频经 Sidon 修复（MLS）

语言：de、en、es、fr、it、nl、pl、pt · 任务：语音识别、语音合成

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [mls_sidon@tts-unified-v0.1](../../catalog/tts_unified.yaml#L691) | 50,834.3 | 已登记 | 没有 |

- `mls_sidon@tts-unified-v0.1`：音频编码字节存放在 Lance 表内；原始划分在 metadata_json.original_split，统一输出全部为 train。ASR 用 tts_lance.iter_asr_samples（tts-asr-rules/v1）读取，会排除原始 dev/test 等

### mtedx

TEDx 西语/葡语演讲（mTEDx，非商用）

语言：es、pt · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [mtedx@hf-0b97ef40298d](../../catalog/mtedx.yaml#L1) | 334.1 | 已登记 | 没有 |

- `mtedx@hf-0b97ef40298d`：Multilingual TEDx（OpenSLR 100）的 HF Parquet 转存，只下了西语和葡语的 ASR 部分；整段讲座按官方 segments 切成句子，未含 iwslt2021 划分。转存 README 称丢弃了短于 0.5 秒或长于 30 秒的句子，实测只去掉了短于 0.5 秒的，长于 30 秒的仍在（train 西语 639 句、葡语 511 句，最长约 284 秒）。条数比官方少 1–2%，时长比官方 statistics.txt 少约 17%，差异原因未核实；以本条统计为准。讲者口音未标注。CC BY-NC-ND，仅限非商用。OpenSLR 原包在国内镜像上太慢，改用此转存

### multi-talker-sd

AISHELL-1、LibriSpeech 合成的多人对话

语言：en、zh · 任务：语音识别、语码转换语音识别、连续语音分离、重叠语音检测、带说话人标注的语音识别、说话人分段与归属

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [multi-talker-sd@hf-be2d372003fd](../../catalog/multilingual_multispeaker.yaml#L220) | — | 未登记 | 快照 20260914 |

### multilingual_asr_bench

十二种语言公开 ASR 测试集（只用于评测）

语言：ar、de、en、es、fr、hi、id、ja、ko、pt、ru、zh · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [multilingual_asr_bench@v1-20261110](../../catalog/multilingual_asr_bench.yaml#L1) | — | 未登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/multilingual_asr_bench/` |
| [multilingual_asr_bench@v2-20261110](../../catalog/multilingual_asr_bench.yaml#L759) | — | 未登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/multilingual_asr_bench/` |

- `multilingual_asr_bench@v1-20261110`：FLEURS 与 Common Voice 17.0 的 test 划分覆盖中、英、阿、西、法、德、葡、日、韩、印地、俄、印尼十二种语言，另有 GigaSpeech 2 印尼语 test（YouTube）与 Casablanca 八种阿拉伯语方言 test（电视剧）。音频从各自登记的上游快照原样取出，不重编码；转写取上游原文（FLEURS 用 raw transcription）。只用于评测，不进训练
- `multilingual_asr_bench@v2-20261110`：FLEURS 与 Common Voice 17.0 的 test 划分覆盖中、英、阿、西、法、德、葡、日、韩、印地、俄、印尼十二种语言，另有 GigaSpeech 2 印尼语 test（YouTube）、Casablanca 八种阿拉伯语方言 test（电视剧）、Kathbath 印地语 test（手机朗读，已知/未知说话人）、VoxPopuli 法语和德语 test（欧洲议会发言）与 Golos 俄语 test（语音助手指令，众包/远场）。音频从各自登记的上游快照原样取出，只有 Kathbath 的 m4a 解码为 FLAC；转写取上游原文（FLEURS 用 raw transcription，VoxPopuli 用 raw_text）。v1-20261110 是不含 Kathbath、VoxPopuli、Golos 的前一版，两版共用 source/ 下的音频。只用于评测，不进训练

### opendatalab_multilingual

8 个语种的语音识别数据（OpenDataLab）

语言：ar、cs、hu、ko、ru、sr、th、vi · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [opendatalab_multilingual@computer-2-20261009](../../catalog/opendatalab_multilingual.yaml#L1) | 8,588.2 | 已登记 | `amphion-audio-backup-1373259071:computer-2/audio/`（原始数据）、`amphion-audio-backup-1373259071:opendatalab-multilingual/`（原始数据） |

- `opendatalab_multilingual@computer-2-20261009`：OpenDataLab 多语言语音识别数据，8 个语种（ar 阿拉伯语、cs 捷克语、hu 匈牙利语、ko 韩语、ru 俄语、sr 塞尔维亚语、th 泰语、vi 越南语），每语种约 1000 小时。16 kHz 单声道 WAV 切片，每个语种一份 JSONL 清单（id、audio.path/duration/snr、text.content/lang、pjwk_cates 内容分类）。清单中 audio.path 相对于本版本目录。不分 train/dev/test

### sot_many_speaker_word_zh_en

—

语言：en、zh · 任务：带说话人标注的语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [sot_many_speaker_word_zh_en@pilot-v1-20261008](../../catalog/sot_many_speaker_word_zh_en.yaml#L8055) | 46.2 | 已登记 | 没有 |
| [sot_many_speaker_word_zh_en@word-v1-20261008](../../catalog/sot_many_speaker_word_zh_en.yaml#L2) | 2,128.0 | 已登记 | 没有 |

- `sot_many_speaker_word_zh_en@pilot-v1-20261008`：6-12 人词级长混音的小规模验证（2026-10-08），占位登记，不用于训练：r1（±5 dB 增益、轮次 SINR -8 dB）strong 档低 SNR 被筛掉过多，只作校准证据；r2（±3 dB、-10 dB）364 条；control-noclean 是不带 clean 过滤的对照池，196 条。全量数据见 word-v1-20261008，它取代了这三组。三组各在一个子目录里，records 和 audio 与生成目录硬链接，没有复制。任务和配方不要引用此版本。脚本 scripts/label_registration/register_many_speaker.py
- `sot_many_speaker_word_zh_en@word-v1-20261008`：6-12 人词级长混音（2026-10-08，amphiondata feat/many-speaker-word-level-synthesis）：每条 180 秒，由多个说话人的词段交替、重叠拼成，加模拟房间脉冲响应和噪声；训练 42,000 条、dev 280、test 280（中文和英文各占一部分），共约 2128 小时（混音时长，不是独立语音时长）。录音是 audio/ 下的 flac，audio-index 指向它们；records 在 shards/，每条含说话人归属、词级时间戳和声学参数。中文来源的词级对齐见各来源数据集的 alignment-v1-20261008。自动验收（时间线、分区、token 数、SNR、波形重建）0 项失败，未经人工听审；词时间是自动强制对齐，说话人身份只在单个语料内成立。audio 与 shards 由生成目录硬链接而来，没有复制。生成日志和代码快照在 build_logs/。脚本 scripts/label_registration/register_many_speaker.py

### sot_multispeaker_zh_en

1–5 人中英合成混音，按人完整转写

语言：en、zh、zh-en · 任务：带说话人标注的语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [sot_multispeaker_zh_en@synthetic-v2-20260915](../../catalog/sot_multispeaker_zh_en.yaml#L1) | 7,664.4 | 已登记 | 没有 |
| [sot_multispeaker_zh_en@synthetic-v2-timestamps-v1-20260919](../../catalog/sot_multispeaker_zh_en.yaml#L33216) | — | 未登记 | 没有 |

- `sot_multispeaker_zh_en@synthetic-v2-20260915`：1～5 人中英混音，完整按人转写；200 万 train、1 万 dev、1 万 test。原版没有字词对齐时间戳
- `sot_multispeaker_zh_en@synthetic-v2-timestamps-v1-20260919`：时间戳版本已登记、尚在准备：复用 v2 原混音，新增每次发言起止时间。源对齐和质检未全部完成，尚未发布可训练记录；不将计划条数计为已完成数据
- 含派生版本（与源数据可能重叠）

### speech_deepfake_bench

伪造语音检测评测集（SpoofRadar、DF-Arena）

语言：ar、de、en、es、ro、ru、zh · 任务：deepfake_detection

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [speech_deepfake_bench@v1-20261103](../../catalog/speech_deepfake_bench.yaml#L1) | 3,463.7 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/speech_deepfake_bench/` |

- `speech_deepfake_bench@v1-20261103`：SpoofRadar v1.0 与 Speech-DF-Arena 两个伪造语音检测排行榜使用的 16 个公开评测集，只用于评测，不进训练。每条记录的 target 为 bonafide（真人）或 spoof（伪造），metadata.protocols 保留两个榜单 protocol 中的原始样本 ID，可直接生成提交用的打分文件。官方 protocol 原样保存在 source/protocols/。各数据集许可证不同（ADD、Codecfake 为 CC BY-NC-ND 4.0，XMAD-Bench 为 CC BY-NC-SA 4.0），仅限内部研究评测，不得再分发

### starrail_voice

《崩坏：星穹铁道》多语配音，TTS 用

语言：en、ja、ko、zh-CN · 任务：语音合成

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [starrail_voice@tts-unified-v0.1](../../catalog/tts_unified.yaml#L740) | 692.6 | 已登记 | `amphion-tts-data-1373259071:starrail-voice/`（原始数据） |

- `starrail_voice@tts-unified-v0.1`：音频编码字节存放在 Lance 表内；原始划分在 metadata_json.original_split，统一输出全部为 train。ASR 用 tts_lance.iter_asr_samples（tts-asr-rules/v1）读取，会排除原始 dev/test 等

### talcs

中英语码转换课堂语音（TALCS）；含热词和加噪版

语言：en、zh · 任务：语音识别、热词增强语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [talcs@clean-dual-qwen-moss-v1-20261009](../../catalog/zh_source_clean_20261009.yaml#L500) | 553.4 | 已登记 | 没有 |
| [talcs@eval-20260804](../../catalog/open_audio_eval.yaml#L187) | 23.6 | 已登记 | 快照 20260914 |
| [talcs@icefall-20260908](../../catalog/icefall_runtime.yaml#L1959) | 587.6 | 已登记 | 快照 20260914 |
| [talcs@legacy-20260804](../../catalog/icefall_base.yaml#L1563) | 587.6 | 已登记 | 快照 20260914 |
| [talcs@punc-written-v1-20261029](../../catalog/zh_punc_written_v1.yaml#L348) | 555.9 | 已登记 | 没有 |
| [talcs_hotwords@hotwords-v1-20260805](../../catalog/local_lhotse_derived.yaml#L222) | 555.9 | 已登记 | 快照 20260914 |
| [talcs_traffic_snr0@icefall-20260908](../../catalog/icefall_runtime.yaml#L3949) | 23.6 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/talcs_traffic_snr0/` |
| [talcs_traffic_snr0@recipe-1](../../catalog/icefall_traffic_derived.yaml#L99) | 23.6 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/talcs_traffic_snr0/` |
| [talcs_traffic_snr10@icefall-20260908](../../catalog/icefall_runtime.yaml#L4157) | 23.6 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/talcs_traffic_snr10/` |
| [talcs_traffic_snr10@recipe-1](../../catalog/icefall_traffic_derived.yaml#L351) | 23.6 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/talcs_traffic_snr10/` |
| [talcs_traffic_snr15@icefall-20260908](../../catalog/icefall_runtime.yaml#L4261) | 23.6 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/talcs_traffic_snr15/` |
| [talcs_traffic_snr15@recipe-1](../../catalog/icefall_traffic_derived.yaml#L477) | 23.6 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/talcs_traffic_snr15/` |
| [talcs_traffic_snr20@icefall-20260908](../../catalog/icefall_runtime.yaml#L4365) | 23.6 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/talcs_traffic_snr20/` |
| [talcs_traffic_snr20@recipe-1](../../catalog/icefall_traffic_derived.yaml#L603) | 23.6 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/talcs_traffic_snr20/` |
| [talcs_traffic_snr5@icefall-20260908](../../catalog/icefall_runtime.yaml#L4053) | 23.6 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/talcs_traffic_snr5/` |
| [talcs_traffic_snr5@recipe-1](../../catalog/icefall_traffic_derived.yaml#L225) | 23.6 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/talcs_traffic_snr5/` |
| [talcs@legacy-20260804](../../catalog/icefall_base.yaml#L1563) | 300.0 | [参考表](https://ccnuebbmik1f.feishu.cn/wiki/CEXFwEjPoi2bIukVjk9c5FdOn12?sheet=3d4d23) | 快照 20260914 |

- `talcs@clean-dual-qwen-moss-v1-20261009`：talcs@icefall-20260908 的 train 监督片段，经 Qwen3-ASR-1.7B 与 MOSS-Transcribe-Diarize 双引擎一致性清洗（与 2026-10-08 的 primewords、aishell3、aidatatang、magicdata、magicdata_ramc 同一流程）；逐条写入 custom.clean（pass、reason、action、engine_status、两引擎各自和互相的 CER、MOSS 说话人段），不删除记录，读取时按 require_clean_pass 过滤。音频沿用源版本，不复制。规则 consensus-v6 / wenetspeech-faithful-v5：350000 条中 pass 347533、reject 2467。少于 2 个字的 too_short 共 541 条按规则不经引擎直接 pass。restore_disfluency 改写了 2039 条的 text（原文留在 custom.original_text）；无标点清单另把 8281 条的标点和撇号去掉。引擎原始结果和复核清单在 evidence/。脚本 scripts/zh_source_clean/register_clean_dual.py
- `talcs@punc-written-v1-20261029`：talcs@icefall-20260908 训练集原标注加书面化标点（GB/T 15834，逗号从紧）：微调后的 Qwen3-4B（Qwen3.8-27B 的 9.6 万条输出蒸馏）以 Qwen3-ASR-1.7B 听音频得到的带标点转写作语气提示，只往原标注里插标点。模型改动了原文的条目，把模型输出的标点按字对齐搬回原标注；每条以 。？！ 结尾；原标注的字、空格（首尾除外）和大小写不变。没有汉字的条目（英文句子、拼读字母）和标注为空的条目原样保留。文件与源 supervisions 条数、顺序相同，只换 text。试点 200 条人工参照上：WenetSpeech markF1 92.4、其他来源 88.9（老师 93.2 / 88.2，原 FireRedPunc 79.8）
- 含派生版本（与源数据可能重叠）

### ts_asr_benchmark

合成的中文目标说话人 ASR 评测集

语言：en、es、zh · 任务：目标说话人语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [ts_asr_benchmark@en-v1-20261031](../../catalog/ts_asr_benchmark.yaml#L7106) | 44.4 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_asr_benchmark/` |
| [ts_asr_benchmark@en-v1-hotword-labels-20261102](../../catalog/ts_benchmark_hotword_labels.yaml#L5793) | 44.4 | 已登记 | 没有 |
| [ts_asr_benchmark@es-v1-20261110](../../catalog/ts_asr_benchmark.yaml#L9371) | 43.2 | 已登记 | 没有 |
| [ts_asr_benchmark@listening-review-v1-20261026](../../catalog/listening_review.yaml#L303) | — | 未登记 | 没有 |
| [ts_asr_benchmark@v1-20261013](../../catalog/ts_asr_benchmark.yaml#L1) | 25.0 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_asr_benchmark/` |
| [ts_asr_benchmark@v2-20261013](../../catalog/ts_asr_benchmark.yaml#L1228) | 26.9 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_asr_benchmark/` |
| [ts_asr_benchmark@v3-20261013](../../catalog/ts_asr_benchmark.yaml#L2534) | 43.9 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_asr_benchmark/` |
| [ts_asr_benchmark@v4-20261022](../../catalog/ts_asr_benchmark.yaml#L4760) | 46.5 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_asr_benchmark/` |
| [ts_asr_benchmark@v4-hotword-labels-20261102](../../catalog/ts_benchmark_hotword_labels.yaml#L1) | 46.5 | 已登记 | 没有 |

- `ts_asr_benchmark@en-v1-20261031`：英文目标说话人 ASR 评测集（ts_asr_benchmark）：与中文版同一配方与随机种子，说话人换成 VCTK、CS-Dialogue 英文 test、LibriSpeech test-clean/test-other；不含业务真实注册录音条件。只用于评测，不进训练。场景见 scripts/ts_benchmark/recipe-en.yaml
- `ts_asr_benchmark@en-v1-hotword-labels-20261102`：ts_asr_benchmark@en-v1-20261031 的全部记录，附目标转写和其他说话人转写的热词标注（metadata.hotword_labels：target 为目标转写的标注，others 按顺序对应合成记录的 metadata.interferers[*].utts[*] 或真实记录 metadata.window_utts 里非目标说话人的段落；每条含文本、最终热词、模型抽取、复核结果）。这些标注是评测集 ts_asr_hotwords@v1-20261102 的来源。只是标注载体：除 metadata.hotword_labels 外记录不变，音频索引沿用源版本；评测集仍固定引用源版本。脚本 scripts/ts_hotwords/register_eval_hotword_labels.py
- `ts_asr_benchmark@es-v1-20261110`：西班牙语目标说话人 ASR 评测集（ts_asr_benchmark）：与英文版 en-v1-20261031 同一配方与随机种子，说话人换成 Common Voice es dev（众包朗读、多口音、各自设备）；没有英文版的手机对话（CS-Dialogue）与录音棚（VCTK）两组设备场景，西语没有对应语料。只用于评测，不进训练。场景见 scripts/ts_benchmark/recipe-es.yaml
- `ts_asr_benchmark@listening-review-v1-20261026`：ts_asr_benchmark@v4-20261022 中被人工听审过的 9 条数据行（父版本数据行原样照抄，录音和音频索引沿用父版本），每行的 metadata.listening_review（Lhotse custom.listening_review）是关于这条记录的听审答案列表：问题、选项、回答、备注、回答日期、听审名称、片段起止和选项含义（resolved_to）。共 9 条答案（ts-asr-hard-cases-20261026 9 条），9 条已挂到数据行。证据文件 listening_review.jsonl.gz 含该版本全部答案。只含被听过的记录，不是完整数据版本，不用于训练。脚本 scripts/label_registration/register_listening_review.py
- `ts_asr_benchmark@v1-20261013`、`ts_asr_benchmark@v2-20261013`、`ts_asr_benchmark@v3-20261013`、`ts_asr_benchmark@v4-20261022`：目标说话人 ASR 评测集：由 AISHELL-3、KeSpeech、MagicData、AISHELL-2、AISHELL-1 的官方 test 划分合成，覆盖注册音频劣化、目标说话人进场离场与缺席、纯噪声、环境与设备。只用于评测，不进训练。场景见 scripts/ts_benchmark/recipe.yaml
- `ts_asr_benchmark@v4-hotword-labels-20261102`：ts_asr_benchmark@v4-20261022 的全部记录，附目标转写和其他说话人转写的热词标注（metadata.hotword_labels：target 为目标转写的标注，others 按顺序对应合成记录的 metadata.interferers[*].utts[*] 或真实记录 metadata.window_utts 里非目标说话人的段落；每条含文本、最终热词、模型抽取、复核结果）。这些标注是评测集 ts_asr_hotwords@v1-20261102 的来源。只是标注载体：除 metadata.hotword_labels 外记录不变，音频索引沿用源版本；评测集仍固定引用源版本。脚本 scripts/ts_hotwords/register_eval_hotword_labels.py

### ts_asr_crosslingual

—

语言：en、es、zh · 任务：目标说话人语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [ts_asr_crosslingual@en-v1-20261109](../../catalog/ts_asr_crosslingual.yaml#L427) | 6.2 | 已登记 | 没有 |
| [ts_asr_crosslingual@es-v1-20261111](../../catalog/ts_asr_crosslingual.yaml#L853) | 3.5 | 已登记 | 没有 |
| [ts_asr_crosslingual@zh-v1-20261109](../../catalog/ts_asr_crosslingual.yaml#L1) | 6.2 | 已登记 | 没有 |

- `ts_asr_crosslingual@en-v1-20261109`：跨语言注册 TS-ASR 评测集（混合段英文）：Common Voice 同一账号既录中文又录英文、从未作为 TS 训练目标的 78 人，以及 Qwen3-TTS-12Hz-1.7B-Base 跨语言克隆的 50 个合成音色（注册与混合段都是合成音）；每个场景配同语言与跨语言两种注册。只用于评测，不进训练。配方见 scripts/ts_benchmark/recipe-crosslingual-en.yaml
- `ts_asr_crosslingual@es-v1-20261111`：跨语言注册 TS-ASR 评测集（混合段西班牙语）：Common Voice 同一账号既录西语（dev/test）又录英文、从未作为 TS 训练目标、两种语言都核对过是同一人声（ECAPA，每种语言至少 5 句）的 35 人；每个场景配同语言（西语）与跨语言（英文）两种注册。没有合成音色部分（Common Voice 里没有同时录西语和中文的说话人）。只用于评测，不进训练。配方见 scripts/ts_benchmark/recipe-crosslingual-es.yaml
- `ts_asr_crosslingual@zh-v1-20261109`：跨语言注册 TS-ASR 评测集（混合段中文）：Common Voice 同一账号既录中文又录英文、从未作为 TS 训练目标的 78 人，以及 Qwen3-TTS-12Hz-1.7B-Base 跨语言克隆的 50 个合成音色（注册与混合段都是合成音）；每个场景配同语言与跨语言两种注册。只用于评测，不进训练。配方见 scripts/ts_benchmark/recipe-crosslingual-zh.yaml

### ts_asr_farfield

目标说话人评测：远场与混响

语言：en、es、zh · 任务：目标说话人语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [ts_asr_farfield@en-v1-20261031](../../catalog/ts_asr_farfield.yaml#L614) | 5.0 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_asr_farfield/` |
| [ts_asr_farfield@en-v1-hotword-labels-20261102](../../catalog/ts_benchmark_hotword_labels.yaml#L8176) | 5.0 | 已登记 | 没有 |
| [ts_asr_farfield@es-v1-20261111](../../catalog/ts_asr_farfield.yaml#L919) | 5.1 | 已登记 | 没有 |
| [ts_asr_farfield@v1-20261014](../../catalog/ts_asr_farfield.yaml#L1) | 5.1 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_asr_farfield/` |
| [ts_asr_farfield@v2-20261022](../../catalog/ts_asr_farfield.yaml#L308) | 5.1 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_asr_farfield/` |
| [ts_asr_farfield@v2-hotword-labels-20261102](../../catalog/ts_benchmark_hotword_labels.yaml#L2468) | 5.1 | 已登记 | 没有 |

- `ts_asr_farfield@en-v1-20261031`：英文目标说话人 ASR 评测集（ts_asr_farfield）：与中文版同一配方与随机种子，说话人换成 VCTK、CS-Dialogue 英文 test、LibriSpeech test-clean/test-other；不含业务真实注册录音条件。只用于评测，不进训练。场景见 scripts/ts_benchmark/recipe-farfield-en.yaml
- `ts_asr_farfield@en-v1-hotword-labels-20261102`：ts_asr_farfield@en-v1-20261031 的全部记录，附目标转写和其他说话人转写的热词标注（metadata.hotword_labels：target 为目标转写的标注，others 按顺序对应合成记录的 metadata.interferers[*].utts[*] 或真实记录 metadata.window_utts 里非目标说话人的段落；每条含文本、最终热词、模型抽取、复核结果）。这些标注是评测集 ts_asr_hotwords@v1-20261102 的来源。只是标注载体：除 metadata.hotword_labels 外记录不变，音频索引沿用源版本；评测集仍固定引用源版本。脚本 scripts/ts_hotwords/register_eval_hotword_labels.py
- `ts_asr_farfield@es-v1-20261111`：西班牙语目标说话人 ASR 评测集（ts_asr_farfield）：与英文版 en-v1-20261031 同一配方与随机种子，说话人换成 Common Voice es dev（众包朗读、多口音、各自设备）；不含业务真实注册录音条件。只用于评测，不进训练。场景见 scripts/ts_benchmark/recipe-farfield-es.yaml
- `ts_asr_farfield@v1-20261014`、`ts_asr_farfield@v2-20261022`：目标说话人 ASR 评测集：由 AISHELL-3、KeSpeech、MagicData、AISHELL-2、AISHELL-1 的官方 test 划分合成，覆盖注册音频劣化、目标说话人进场离场与缺席、纯噪声、环境与设备。只用于评测，不进训练。场景见 scripts/ts_benchmark/recipe.yaml
- `ts_asr_farfield@v2-hotword-labels-20261102`：ts_asr_farfield@v2-20261022 的全部记录，附目标转写和其他说话人转写的热词标注（metadata.hotword_labels：target 为目标转写的标注，others 按顺序对应合成记录的 metadata.interferers[*].utts[*] 或真实记录 metadata.window_utts 里非目标说话人的段落；每条含文本、最终热词、模型抽取、复核结果）。这些标注是评测集 ts_asr_hotwords@v1-20261102 的来源。只是标注载体：除 metadata.hotword_labels 外记录不变，音频索引沿用源版本；评测集仍固定引用源版本。脚本 scripts/ts_hotwords/register_eval_hotword_labels.py

### ts_asr_handover

目标说话人评测：与他人交替说话

语言：en、es、zh · 任务：目标说话人语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [ts_asr_handover@en-v1-20261031](../../catalog/ts_asr_handover.yaml#L454) | 1.6 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_asr_handover/` |
| [ts_asr_handover@en-v1-hotword-labels-20261102](../../catalog/ts_benchmark_hotword_labels.yaml#L8501) | 1.6 | 已登记 | 没有 |
| [ts_asr_handover@es-v1-20261111](../../catalog/ts_asr_handover.yaml#L579) | 1.7 | 已登记 | 没有 |
| [ts_asr_handover@v1-20261020](../../catalog/ts_asr_handover.yaml#L1) | 3.8 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_asr_handover/` |
| [ts_asr_handover@v2-20261022](../../catalog/ts_asr_handover.yaml#L228) | 3.8 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_asr_handover/` |
| [ts_asr_handover@v2-hotword-labels-20261102](../../catalog/ts_benchmark_hotword_labels.yaml#L2793) | 3.8 | 已登记 | 没有 |

- `ts_asr_handover@en-v1-20261031`：英文目标说话人 ASR 评测集（ts_asr_handover）：与中文版同一配方与随机种子，说话人换成 VCTK、CS-Dialogue 英文 test、LibriSpeech test-clean/test-other；不含业务真实注册录音条件。只用于评测，不进训练。场景见 scripts/ts_benchmark/recipe-handover-en.yaml
- `ts_asr_handover@en-v1-hotword-labels-20261102`：ts_asr_handover@en-v1-20261031 的全部记录，附目标转写和其他说话人转写的热词标注（metadata.hotword_labels：target 为目标转写的标注，others 按顺序对应合成记录的 metadata.interferers[*].utts[*] 或真实记录 metadata.window_utts 里非目标说话人的段落；每条含文本、最终热词、模型抽取、复核结果）。这些标注是评测集 ts_asr_hotwords@v1-20261102 的来源。只是标注载体：除 metadata.hotword_labels 外记录不变，音频索引沿用源版本；评测集仍固定引用源版本。脚本 scripts/ts_hotwords/register_eval_hotword_labels.py
- `ts_asr_handover@es-v1-20261111`：西班牙语目标说话人 ASR 评测集（ts_asr_handover）：与英文版 en-v1-20261031 同一配方与随机种子，说话人换成 Common Voice es dev（众包朗读、多口音、各自设备）；不含业务真实注册录音条件。只用于评测，不进训练。场景见 scripts/ts_benchmark/recipe-handover-es.yaml
- `ts_asr_handover@v1-20261020`、`ts_asr_handover@v2-20261022`：目标说话人 ASR 评测集：由 AISHELL-3、KeSpeech、MagicData、AISHELL-2、AISHELL-1 的官方 test 划分合成，覆盖注册音频劣化、目标说话人进场离场与缺席、纯噪声、环境与设备。只用于评测，不进训练。场景见 scripts/ts_benchmark/recipe.yaml
- `ts_asr_handover@v2-hotword-labels-20261102`：ts_asr_handover@v2-20261022 的全部记录，附目标转写和其他说话人转写的热词标注（metadata.hotword_labels：target 为目标转写的标注，others 按顺序对应合成记录的 metadata.interferers[*].utts[*] 或真实记录 metadata.window_utts 里非目标说话人的段落；每条含文本、最终热词、模型抽取、复核结果）。这些标注是评测集 ts_asr_hotwords@v1-20261102 的来源。只是标注载体：除 metadata.hotword_labels 外记录不变，音频索引沿用源版本；评测集仍固定引用源版本。脚本 scripts/ts_hotwords/register_eval_hotword_labels.py

### ts_asr_hotwords

—

语言：en、es、zh · 任务：目标说话人语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [ts_asr_hotwords@es-v1-20261111](../../catalog/ts_asr_hotwords.yaml#L145) | — | 未登记 | 没有 |
| [ts_asr_hotwords@v1-20261102](../../catalog/ts_asr_hotwords.yaml#L2) | — | 未登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_asr_hotwords/` |

- `ts_asr_hotwords@es-v1-20261111`：西班牙语 TS-ASR + 热词评测集：从 ts-asr-benchmark-es@v1-20261110（ts_asr_benchmark@es-v1-20261110，Common Voice es dev）派生，做法与 v1-20261102（中英）相同：沿用原音频与目标，记录 id 加 es 前缀；hotwords = 目标说话人转写里的热词；metadata.bias_lists：random = 正确词 + 随机词共 10 个，interferer = 正确词 + 其他说话人说出的热词 + 随机词共 20 个（只在有人说了热词时给）；抽样同 v1。热词由 amphiondata 的热词提取提示词经 Qwen3.8-27B 标注并复核（label_hotwords.py），词必须在原文里出现；原始标注随版本存为 hotword-labels.jsonl（另含 CV / FLEURS / MLS es test 的转写标注，供普通 ASR 热词评测）。一个 split：es-synthetic 5,360
- `ts_asr_hotwords@v1-20261102`：TS-ASR + 热词评测集：从 ts-asr-benchmark@v12-20261022（中文）与 ts-asr-benchmark-en@v1-20261031（英文）的记录派生，沿用原音频（audio-index 指向源文件）与目标；记录 id 加语言前缀。hotwords = 目标说话人转写里的热词；metadata.bias_lists：random = 正确词 + 随机词共 10 个，interferer = 正确词 + 其他说话人说出的热词 + 随机词共 20 个（只在有人说了热词时给）；metadata.distractor_kinds 标出 interferer / random。抽样：含目标热词的记录全留，只有其他说话人热词的留 1/4，两者都没有的留 1/8。热词由 amphiondata 的热词提取提示词经 Qwen3.8-27B 标注并复核，词必须在原文里出现。四个 split：zh-synthetic 7,794、zh-real 243、en-synthetic 4,126、en-real 220

### ts_asr_nearshort

目标说话人评测：他人只说一句约 1 秒短话

语言：en、zh · 任务：目标说话人语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [ts_asr_nearshort@en-v1-20261031](../../catalog/ts_asr_nearshort.yaml#L660) | 2.2 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_asr_nearshort/` |
| [ts_asr_nearshort@en-v1-hotword-labels-20261102](../../catalog/ts_benchmark_hotword_labels.yaml#L8637) | 2.2 | 已登记 | 没有 |
| [ts_asr_nearshort@v1-20261021](../../catalog/ts_asr_nearshort.yaml#L1) | 1.0 | 已登记 | 没有 |
| [ts_asr_nearshort@v2-20261022](../../catalog/ts_asr_nearshort.yaml#L128) | 2.5 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_asr_nearshort/` |
| [ts_asr_nearshort@v3-20261022](../../catalog/ts_asr_nearshort.yaml#L394) | 2.5 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_asr_nearshort/` |
| [ts_asr_nearshort@v3-hotword-labels-20261102](../../catalog/ts_benchmark_hotword_labels.yaml#L4073) | 2.5 | 已登记 | 没有 |

- `ts_asr_nearshort@en-v1-20261031`：英文目标说话人 ASR 评测集（ts_asr_nearshort）：与中文版同一配方与随机种子，说话人换成 VCTK、CS-Dialogue 英文 test、LibriSpeech test-clean/test-other；不含业务真实注册录音条件。只用于评测，不进训练。场景见 scripts/ts_benchmark/recipe-nearshort-en.yaml
- `ts_asr_nearshort@en-v1-hotword-labels-20261102`：ts_asr_nearshort@en-v1-20261031 的全部记录，附目标转写和其他说话人转写的热词标注（metadata.hotword_labels：target 为目标转写的标注，others 按顺序对应合成记录的 metadata.interferers[*].utts[*] 或真实记录 metadata.window_utts 里非目标说话人的段落；每条含文本、最终热词、模型抽取、复核结果）。这些标注是评测集 ts_asr_hotwords@v1-20261102 的来源。只是标注载体：除 metadata.hotword_labels 外记录不变，音频索引沿用源版本；评测集仍固定引用源版本。脚本 scripts/ts_hotwords/register_eval_hotword_labels.py
- `ts_asr_nearshort@v1-20261021`、`ts_asr_nearshort@v2-20261022`、`ts_asr_nearshort@v3-20261022`：目标说话人 ASR 评测集：由 AISHELL-3、KeSpeech、MagicData、AISHELL-2、AISHELL-1 的官方 test 划分合成，覆盖注册音频劣化、目标说话人进场离场与缺席、纯噪声、环境与设备。只用于评测，不进训练。场景见 scripts/ts_benchmark/recipe.yaml
- `ts_asr_nearshort@v3-hotword-labels-20261102`：ts_asr_nearshort@v3-20261022 的全部记录，附目标转写和其他说话人转写的热词标注（metadata.hotword_labels：target 为目标转写的标注，others 按顺序对应合成记录的 metadata.interferers[*].utts[*] 或真实记录 metadata.window_utts 里非目标说话人的段落；每条含文本、最终热词、模型抽取、复核结果）。这些标注是评测集 ts_asr_hotwords@v1-20261102 的来源。只是标注载体：除 metadata.hotword_labels 外记录不变，音频索引沿用源版本；评测集仍固定引用源版本。脚本 scripts/ts_hotwords/register_eval_hotword_labels.py

### ts_asr_noise

目标说话人评测：噪声与背景人声

语言：en、es、zh · 任务：目标说话人语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [ts_asr_noise@en-v1-20261031](../../catalog/ts_asr_noise.yaml#L734) | 5.9 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_asr_noise/` |
| [ts_asr_noise@en-v1-hotword-labels-20261102](../../catalog/ts_benchmark_hotword_labels.yaml#L8878) | 5.9 | 已登记 | 没有 |
| [ts_asr_noise@es-v1-20261111](../../catalog/ts_asr_noise.yaml#L1099) | 3.5 | 已登记 | 没有 |
| [ts_asr_noise@v1-20261013](../../catalog/ts_asr_noise.yaml#L1) | 5.9 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_asr_noise/` |
| [ts_asr_noise@v2-20261022](../../catalog/ts_asr_noise.yaml#L368) | 5.9 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_asr_noise/` |
| [ts_asr_noise@v2-hotword-labels-20261102](../../catalog/ts_benchmark_hotword_labels.yaml#L4356) | 5.9 | 已登记 | 没有 |

- `ts_asr_noise@en-v1-20261031`：英文目标说话人 ASR 评测集（ts_asr_noise）：与中文版同一配方与随机种子，说话人换成 VCTK、CS-Dialogue 英文 test、LibriSpeech test-clean/test-other；不含业务真实注册录音条件。只用于评测，不进训练。场景见 scripts/ts_benchmark/recipe-noise-en.yaml
- `ts_asr_noise@en-v1-hotword-labels-20261102`：ts_asr_noise@en-v1-20261031 的全部记录，附目标转写和其他说话人转写的热词标注（metadata.hotword_labels：target 为目标转写的标注，others 按顺序对应合成记录的 metadata.interferers[*].utts[*] 或真实记录 metadata.window_utts 里非目标说话人的段落；每条含文本、最终热词、模型抽取、复核结果）。这些标注是评测集 ts_asr_hotwords@v1-20261102 的来源。只是标注载体：除 metadata.hotword_labels 外记录不变，音频索引沿用源版本；评测集仍固定引用源版本。脚本 scripts/ts_hotwords/register_eval_hotword_labels.py
- `ts_asr_noise@es-v1-20261111`：西班牙语目标说话人 ASR 评测集（ts_asr_noise）：与英文版 en-v1-20261031 同一配方与随机种子，说话人换成 Common Voice es dev（众包朗读、多口音、各自设备）；没有英文版的背景人声（babble）各列：已登记的西语 babble 都由训练划分的说话人合成，评测不能用；不含业务真实注册录音条件。只用于评测，不进训练。场景见 scripts/ts_benchmark/recipe-noise-es.yaml
- `ts_asr_noise@v1-20261013`、`ts_asr_noise@v2-20261022`：目标说话人 ASR 评测集：由 AISHELL-3、KeSpeech、MagicData、AISHELL-2、AISHELL-1 的官方 test 划分合成，覆盖注册音频劣化、目标说话人进场离场与缺席、纯噪声、环境与设备。只用于评测，不进训练。场景见 scripts/ts_benchmark/recipe.yaml
- `ts_asr_noise@v2-hotword-labels-20261102`：ts_asr_noise@v2-20261022 的全部记录，附目标转写和其他说话人转写的热词标注（metadata.hotword_labels：target 为目标转写的标注，others 按顺序对应合成记录的 metadata.interferers[*].utts[*] 或真实记录 metadata.window_utts 里非目标说话人的段落；每条含文本、最终热词、模型抽取、复核结果）。这些标注是评测集 ts_asr_hotwords@v1-20261102 的来源。只是标注载体：除 metadata.hotword_labels 外记录不变，音频索引沿用源版本；评测集仍固定引用源版本。脚本 scripts/ts_hotwords/register_eval_hotword_labels.py

### ts_asr_real

真实会议对话的目标说话人评测集

语言：en、zh · 任务：目标说话人语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [ts_asr_real@dev-v1-20261017](../../catalog/ts_asr_real.yaml#L1085) | 6.2 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_asr_real/` |
| [ts_asr_real@en-v2-20261031](../../catalog/ts_asr_real.yaml#L2942) | 6.0 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_asr_real/` |
| [ts_asr_real@en-v2-hotword-labels-20261102](../../catalog/ts_benchmark_hotword_labels.yaml#L9266) | 6.0 | 已登记 | 没有 |
| [ts_asr_real@listening-review-v1-20261022](../../catalog/listening_review.yaml#L667) | — | 未登记 | 没有 |
| [ts_asr_real@listening-review-v1-20261026](../../catalog/listening_review.yaml#L849) | — | 未登记 | 没有 |
| [ts_asr_real@overlap-v1-20261017](../../catalog/ts_asr_real.yaml#L822) | 12.0 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_asr_real/` |
| [ts_asr_real@v1-20261013](../../catalog/ts_asr_real.yaml#L1) | 3.9 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_asr_real/` |
| [ts_asr_real@v2-20261013](../../catalog/ts_asr_real.yaml#L345) | 5.4 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_asr_real/` |
| [ts_asr_real@v3-20261022](../../catalog/ts_asr_real.yaml#L1309) | 5.4 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_asr_real/` |
| [ts_asr_real@v4-20261022](../../catalog/ts_asr_real.yaml#L2115) | 5.4 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_asr_real/` |
| [ts_asr_real@v4-hotword-labels-20261102](../../catalog/ts_benchmark_hotword_labels.yaml#L4744) | 5.4 | 已登记 | 没有 |

- `ts_asr_real@dev-v1-20261017`：真实对话的目标说话人开发集（选模型和阈值用）：从 AliMeeting 远场、MagicData-RAMC 手机通话的人工标注 dev 划分里 以目标说话人为锚切窗口，按目标被重叠的比例分档（RAMC 标注没有重叠，只有 o0），去掉在 train 划分出现过的说话人所在的录音； 同一窗口配一条目标在场和一条目标缺席的样本。不进训练，也不作最终评测
- `ts_asr_real@en-v2-20261031`：英文真实对话的目标说话人窗口（ts_asr_real 中文版的英文对照，规则相同）：从 AMI 单远场麦、NOTSOFAR-1 单通道设备、 CHiME-6 家庭聚会（所在房间参考阵列通道 1，窗口内所有人在同一房间）、DiPCo 晚宴（远场设备通道 1，时间轴按近讲麦对齐）的 人工标注 test/eval 划分，以及 ICSI 会议测试会议（官方近讲耳麦混音，不是远场）里按完整语句切出 8–22 秒窗口，不做任何混合； 同一窗口配一条目标在场（注册取窗外同一人的语句）和一条目标缺席的样本。参考文本为目标在窗口内各句按时间顺序用空格拼接， 去掉了笑声、噪声、截断词等标注；含听不清、外语、被消音或数字朗读的语句算作有人说话，但不作目标、不作注册。注册存 10 秒、 客户端取前 5 秒，前 5 秒里他人说话不少于 0.3 秒的在 -enrollmix 划分；每条注册都过声纹核对（与本人在本录音其他语句比 与其他人更像，有近讲麦的语料用近讲麦之和），不过的换一句或剔除，见 source/<版本>/report.json。只用于评测，不进训练
- `ts_asr_real@en-v2-hotword-labels-20261102`：ts_asr_real@en-v2-20261031 的全部记录，附目标转写和其他说话人转写的热词标注（metadata.hotword_labels：target 为目标转写的标注，others 按顺序对应合成记录的 metadata.interferers[*].utts[*] 或真实记录 metadata.window_utts 里非目标说话人的段落；每条含文本、最终热词、模型抽取、复核结果）。这些标注是评测集 ts_asr_hotwords@v1-20261102 的来源。只是标注载体：除 metadata.hotword_labels 外记录不变，音频索引沿用源版本；评测集仍固定引用源版本。脚本 scripts/ts_hotwords/register_eval_hotword_labels.py
- `ts_asr_real@listening-review-v1-20261022`：ts_asr_real@v2-20261013 中被人工听审过的 12 条数据行（父版本数据行原样照抄，录音和音频索引沿用父版本），每行的 metadata.listening_review（Lhotse custom.listening_review）是关于这条记录的听审答案列表：问题、选项、回答、备注、回答日期、听审名称、片段起止和选项含义（resolved_to）。共 12 条答案（listen-1021-vs-1022 12 条），12 条已挂到数据行。证据文件 listening_review.jsonl.gz 含该版本全部答案。只含被听过的记录，不是完整数据版本，不用于训练。脚本 scripts/label_registration/register_listening_review.py
- `ts_asr_real@listening-review-v1-20261026`：ts_asr_real@v4-20261022 中被人工听审过的 1 条数据行（父版本数据行原样照抄，录音和音频索引沿用父版本），每行的 metadata.listening_review（Lhotse custom.listening_review）是关于这条记录的听审答案列表：问题、选项、回答、备注、回答日期、听审名称、片段起止和选项含义（resolved_to）。共 1 条答案（ts-asr-hard-cases-20261026 1 条），1 条已挂到数据行。证据文件 listening_review.jsonl.gz 含该版本全部答案。只含被听过的记录，不是完整数据版本，不用于训练。脚本 scripts/label_registration/register_listening_review.py
- `ts_asr_real@overlap-v1-20261017`：真实会议的目标重叠窗口：从 AliMeeting 远场、AISHELL-4 远场的人工标注测试集里以目标说话人为锚切 8–26 秒窗口 （目标的语句完整，别人的语句截到窗口边界），按目标语音被别人重叠的比例分 5–20%、20–50%、50% 以上三档， 不做任何混合；同一窗口配一条目标在场和一条目标缺席的样本。只用于评测，不进训练
- `ts_asr_real@v1-20261013`：真实对话的目标说话人窗口：从 AliMeeting 远场、AISHELL-4 远场、MagicData-RAMC 手机通话的人工标注测试集里按完整语句切出 8–22 秒窗口，不做任何混合；同一窗口配一条目标在场（注册取窗外的另一条语句）和一条目标缺席的样本。只用于评测，不进训练
- `ts_asr_real@v2-20261013`：真实对话的目标说话人窗口：从 AliMeeting 远场、AISHELL-4 远场、MagicData-RAMC 手机通话的人工标注测试集，以及 Emilia2 网络爬取的对话（MOSS 说话人日志伪标签）里按完整语句切出 8–22 秒窗口，不做任何混合；同一窗口配一条目标在场（注册取窗外的另一条语句）和一条目标缺席的样本。只用于评测，不进训练；所用 Emilia2 录音列在 source/<版本>/excluded-recordings.txt，训练必须排除
- `ts_asr_real@v3-20261022`：ts_asr_real@v2-20261013 的修正版，窗口和混合音频不变：每条记录加注册前 3 秒里他人说话的秒数（labels.enroll_others_s），不少于 0.3 秒的记为注册含他人声（enroll_condition = others_speech）并移入同名加 -enrollmix 的划分；AISHELL-4 有 3 条目标在场样本的注册其实是同场另一个人，改取目标的另一条语句，1 条无法确认目标而删除。生成脚本 scripts/ts_real/enroll_overlap.py
- `ts_asr_real@v4-20261022`：ts_asr_real@v3-20261022 的 5 秒注册版，窗口和混合音频不变：注册保留原第一句，后接同一人在窗口外、无他人重叠的其他语句，共存 10 秒（labels.enroll_seconds，metadata.enrollment_pieces）；他人说话秒数改按前 5 秒计（labels.enroll_others_s），不少于 0.3 秒的在 -enrollmix 划分。生成脚本 scripts/ts_real/enroll_long.py
- `ts_asr_real@v4-hotword-labels-20261102`：ts_asr_real@v4-20261022 的全部记录，附目标转写和其他说话人转写的热词标注（metadata.hotword_labels：target 为目标转写的标注，others 按顺序对应合成记录的 metadata.interferers[*].utts[*] 或真实记录 metadata.window_utts 里非目标说话人的段落；每条含文本、最终热词、模型抽取、复核结果）。这些标注是评测集 ts_asr_hotwords@v1-20261102 的来源。只是标注载体：除 metadata.hotword_labels 外记录不变，音频索引沿用源版本；评测集仍固定引用源版本。脚本 scripts/ts_hotwords/register_eval_hotword_labels.py

### ts_asr_shortseg

目标说话人评测：他人说话的 1–6 秒短片段

语言：en、es、zh · 任务：目标说话人语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [ts_asr_shortseg@en-v1-20261031](../../catalog/ts_asr_shortseg.yaml#L334) | 0.6 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_asr_shortseg/` |
| [ts_asr_shortseg@en-v1-hotword-labels-20261102](../../catalog/ts_benchmark_hotword_labels.yaml#L10557) | 0.6 | 已登记 | 没有 |
| [ts_asr_shortseg@es-v1-20261111](../../catalog/ts_asr_shortseg.yaml#L459) | 0.4 | 已登记 | 没有 |
| [ts_asr_shortseg@v1-20261017](../../catalog/ts_asr_shortseg.yaml#L1) | 0.8 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_asr_shortseg/` |
| [ts_asr_shortseg@v2-20261022](../../catalog/ts_asr_shortseg.yaml#L168) | 0.8 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_asr_shortseg/` |
| [ts_asr_shortseg@v2-hotword-labels-20261102](../../catalog/ts_benchmark_hotword_labels.yaml#L5615) | 0.8 | 已登记 | 没有 |

- `ts_asr_shortseg@en-v1-20261031`：英文目标说话人 ASR 评测集（ts_asr_shortseg）：与中文版同一配方与随机种子，说话人换成 VCTK、CS-Dialogue 英文 test、LibriSpeech test-clean/test-other；不含业务真实注册录音条件。只用于评测，不进训练。场景见 scripts/ts_benchmark/recipe-shortseg-en.yaml
- `ts_asr_shortseg@en-v1-hotword-labels-20261102`：ts_asr_shortseg@en-v1-20261031 的全部记录，附目标转写和其他说话人转写的热词标注（metadata.hotword_labels：target 为目标转写的标注，others 按顺序对应合成记录的 metadata.interferers[*].utts[*] 或真实记录 metadata.window_utts 里非目标说话人的段落；每条含文本、最终热词、模型抽取、复核结果）。这些标注是评测集 ts_asr_hotwords@v1-20261102 的来源。只是标注载体：除 metadata.hotword_labels 外记录不变，音频索引沿用源版本；评测集仍固定引用源版本。脚本 scripts/ts_hotwords/register_eval_hotword_labels.py
- `ts_asr_shortseg@es-v1-20261111`：西班牙语目标说话人 ASR 评测集（ts_asr_shortseg）：与英文版 en-v1-20261031 同一配方与随机种子，说话人换成 Common Voice es dev（众包朗读、多口音、各自设备）；没有英文版的对照 solo-mid（CV es dev 的句子太长，排不出 2–6 秒的单句片段）；不含业务真实注册录音条件。只用于评测，不进训练。场景见 scripts/ts_benchmark/recipe-shortseg-es.yaml
- `ts_asr_shortseg@v1-20261017`、`ts_asr_shortseg@v2-20261022`：目标说话人 ASR 评测集：由 AISHELL-3、KeSpeech、MagicData、AISHELL-2、AISHELL-1 的官方 test 划分合成，覆盖注册音频劣化、目标说话人进场离场与缺席、纯噪声、环境与设备。只用于评测，不进训练。场景见 scripts/ts_benchmark/recipe.yaml
- `ts_asr_shortseg@v2-hotword-labels-20261102`：ts_asr_shortseg@v2-20261022 的全部记录，附目标转写和其他说话人转写的热词标注（metadata.hotword_labels：target 为目标转写的标注，others 按顺序对应合成记录的 metadata.interferers[*].utts[*] 或真实记录 metadata.window_utts 里非目标说话人的段落；每条含文本、最终热词、模型抽取、复核结果）。这些标注是评测集 ts_asr_hotwords@v1-20261102 的来源。只是标注载体：除 metadata.hotword_labels 外记录不变，音频索引沿用源版本；评测集仍固定引用源版本。脚本 scripts/ts_hotwords/register_eval_hotword_labels.py

### ts_asr_singing

目标说话人评测：歌声干扰

语言：en、es、zh · 任务：目标说话人语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [ts_asr_singing@en-v1-20261031](../../catalog/ts_asr_singing.yaml#L134) | 0.2 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_asr_singing/` |
| [ts_asr_singing@es-v1-20261111](../../catalog/ts_asr_singing.yaml#L179) | 0.2 | 已登记 | 没有 |
| [ts_asr_singing@v1-20261017](../../catalog/ts_asr_singing.yaml#L1) | 0.3 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_asr_singing/` |
| [ts_asr_singing@v2-20261022](../../catalog/ts_asr_singing.yaml#L68) | 0.3 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_asr_singing/` |

- `ts_asr_singing@en-v1-20261031`：英文目标说话人 ASR 评测集（ts_asr_singing）：与中文版同一配方与随机种子，说话人换成 VCTK、CS-Dialogue 英文 test、LibriSpeech test-clean/test-other；不含业务真实注册录音条件。只用于评测，不进训练。场景见 scripts/ts_benchmark/recipe-singing-en.yaml
- `ts_asr_singing@es-v1-20261111`：西班牙语目标说话人 ASR 评测集（ts_asr_singing）：与英文版 en-v1-20261031 同一配方与随机种子，说话人换成 Common Voice es dev（众包朗读、多口音、各自设备）；不含业务真实注册录音条件。只用于评测，不进训练。场景见 scripts/ts_benchmark/recipe-singing-es.yaml
- `ts_asr_singing@v1-20261017`、`ts_asr_singing@v2-20261022`：目标说话人 ASR 评测集：由 AISHELL-3、KeSpeech、MagicData、AISHELL-2、AISHELL-1 的官方 test 划分合成，覆盖注册音频劣化、目标说话人进场离场与缺席、纯噪声、环境与设备。只用于评测，不进训练。场景见 scripts/ts_benchmark/recipe.yaml

### ts_hw_test

目标说话人加热词评测（LibriSpeech 风格）

语言：en、zh · 任务：目标说话人语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [ts_hw_test_libristyle@eval-20260804](../../catalog/open_audio_eval.yaml#L1218) | 7.7 | 已登记 | 快照 20260914 |

- 当前仅登记评测入口

### ts_interference_pool

在线混合用的干扰人语音素材池

语言：en、es、zh · 任务：ts_asr_interference

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [ts_interference_pool@es-v1-20261110](../../catalog/ts_interference_pool.yaml#L207) | 176.6 | 已登记 | 没有 |
| [ts_interference_pool@es-v2-20261110](../../catalog/ts_interference_pool.yaml#L253) | 225.2 | 已登记 | 没有 |
| [ts_interference_pool@v1-20261015](../../catalog/ts_interference_pool.yaml#L1) | — | 未登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_interference_pool/` |
| [ts_interference_pool@v2-20261016](../../catalog/ts_interference_pool.yaml#L38) | 656.6 | 已登记 | 没有 |
| [ts_interference_pool@v3-20261018](../../catalog/ts_interference_pool.yaml#L130) | 656.6 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_interference_pool/` |

- `ts_interference_pool@es-v1-20261110`：西班牙语干扰人素材池（只有 es 划分，与 zh/en 的 v3-20261018 并列使用）：YODAS es（YouTube 句子，每视频最多 10 条，100,000 条 / 134.8 h / 23,605 个视频）与 MLS es train（有声书，按说话人每人最多 400 条，12,000 条 / 41.8 h / 81 人），1–15 秒，质量门槛同 v2（有声比例 ≥ 0.5、响度 ≥ −50 dBFS）。Common Voice es 不进池：西语 TS 目标（ts_scene_pool es-*）都来自它，同 LibriSpeech / AISHELL-2 不进 zh/en 池的原因。生成脚本 scripts/ts_robust/build_interference_pool.py --languages es --version es-v1-20261110
- `ts_interference_pool@es-v2-20261110`：西班牙语干扰人素材池 v2 = es-v1-20261110 的全部 112,000 条（YODAS es + MLS es，不变）+ Common Voice es train 里没有口音标注的说话人（30,000 条 / 48.5 h / 2,702 人，每人最多 20 句，质量门槛同 v2）。西语 TS 目标是有口音标注的 CV es 说话人（西语场景池与 ts_scene_pool@es-1spk-v2-20261110），两者不共用说话人。es-v1 里没有 CV 的声音、CV 声音在训练里永远是目标，用它训练的 v70 西语 TS 误报 102 -> 587（ts-asr-benchmark-es 的他人是 CV es dev 说话人）。生成脚本 scripts/ts_robust/build_interference_pool.py --languages es --version es-v2-20261110
- `ts_interference_pool@v2-20261016`：在线混合 TS 数据的干扰人素材池 v2：单人语音片段 1–15 s，每说话人或每来源视频限量；片段按偏移取自源文件，不复制音频。已排除 AISHELL-2 与 LibriSpeech（AISHELLMix、LibriMix 的目标说话人来源）。质量列 loudness_dbfs、clip_ratio、voiced_ratio 写在 metadata（Emilia2 未测量）
- `ts_interference_pool@v3-20261018`：干扰人素材池 v3：与 v2-20261016 相同的记录与记录 ID，其中 Emilia2 short 片段（zh 149,999、en 100,000）改为读 emilia2@tts-unified-v0.1 Lance 表内同一条 m4a-128k standalone short（按上游 short ID 与文件名对应，同一 FFmpeg 完整解码存为 FLAC，抽查 40 条与 m4a 解码 SNR ≥ 66.7 dB），训练不再为干扰人启动 ffmpeg；其余来源沿用 v2 的音频索引。Lance 中缺失的 1 条 zh 片段已去掉。生成脚本 scripts/ts_robust/build_interference_pool_v3.py；读取 Lance 片段需要 open-audio-llm 的干扰人池支持指向 Lance 发布的记录（feat/lance-interference-clips）

### ts_nonspeech_pool

非人声与背景人声的空输出训练片段

语言：en、es、zh · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [ts_nonspeech_pool@babble-20261024](../../catalog/ts_nonspeech_pool.yaml#L57) | 38.7 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_nonspeech_pool/` |
| [ts_nonspeech_pool@env-20261101](../../catalog/ts_nonspeech_pool.yaml#L116) | 22.6 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_nonspeech_pool/` |
| [ts_nonspeech_pool@es-babble-20261110](../../catalog/ts_nonspeech_pool.yaml#L178) | 18.8 | 已登记 | 没有 |
| [ts_nonspeech_pool@v1-20261016](../../catalog/ts_nonspeech_pool.yaml#L1) | 65.7 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_nonspeech_pool/` |

- `ts_nonspeech_pool@babble-20261024`：普通 ASR 的背景人声空输出训练数据：babble_noise_train@v2-20261024 的房间背景人声（16–24 人同时说话、各站在模拟房间的不同位置，听不出某一个人说的内容）的片段（0.3–26 s，对数均匀），中英文各 12,000 条，目标为空；片段语言即背景人声的语言。电平在训练时按数据源配置随机。来源：在 asr_babble_bench@v2-20261023 上，普通 ASR 训练里没有只有背景人声、目标为空的样本（v1-20261016 只有 MUSAN 噪声与音乐），模型在只有背景人声时会编出文字。脚本 scripts/ts_robust/build_nonspeech_pool.py --source babble
- `ts_nonspeech_pool@env-20261101`：GRPO 非人声挖掘候选：配方空输出池之外的环境声与音乐片段（0.3–26 s，对数均匀，受源文件长度限制），目标为空，电平在训练时按数据源配置随机。来源 FSD50K dev 的 train 部分（去人声标签）9,000、DNS5 AudioSet 5,000、DNS5 Freesound 2,500、RealMAN train 纯噪声（CH0）3,000、真实会议室底噪 1,000；不用评测集用的 FSD50K eval、DEMAND、audioset_road_traffic。所有片段过 Silero VAD 和 SenseVoiceSmall，检出语音或写出 2 个及以上字词的隔离。只是候选：挖掘阶段用 10.28 采样后只留会编字的片段。脚本 scripts/grpo_candidates/nonspeech.py
- `ts_nonspeech_pool@es-babble-20261110`：西班牙语普通 ASR 的背景人声空输出训练数据（对应 babble-20261024 的 zh / en）：babble_noise_train@es-v1-20261110 的房间背景人声（16–24 人、听不出某一个人说的内容）片段 0.3–26 s（对数均匀），12,000 条，目标为空，语言 es。电平在训练时按数据源配置随机。脚本 scripts/ts_robust/build_nonspeech_pool.py --source babble-es
- `ts_nonspeech_pool@v1-20261016`：普通 ASR 的非人声空输出训练数据：MUSAN 噪声与音乐的片段（0.3–26 s，对数均匀），目标为空。电平在训练时按数据源配置随机。不含 WHAM（咖啡馆底噪里可能有可懂的人声）

### ts_real_train

真实会议切出的目标说话人训练窗口

语言：en、zh · 任务：目标说话人语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [ts_real_train@en-v1-20261101](../../catalog/ts_real_train.yaml#L684) | 41.9 | 已登记 | 没有 |
| [ts_real_train@en-v1-20261101-utts](../../catalog/ts_real_train.yaml#L827) | 41.9 | 已登记 | 没有 |
| [ts_real_train@en-v1-20261101-utts-punc-20261102](../../catalog/train_punc_v1_derived.yaml#L329) | — | 未登记 | 没有 |
| [ts_real_train@v1-20261017](../../catalog/ts_real_train.yaml#L1) | 123.6 | 已登记 | 没有 |
| [ts_real_train@v1-20261017-utts](../../catalog/ts_real_train.yaml#L342) | 123.6 | 已登记 | 没有 |
| [ts_real_train@v1-20261017-utts-enroll-qc-20261021](../../catalog/ts_real_enroll_qc.yaml#L2) | — | 未登记 | 没有 |
| [ts_real_train@v1-20261017-utts-punc-20261102](../../catalog/train_punc_v1_derived.yaml#L1255) | — | 未登记 | 没有 |
| [ts_real_train@v2-20261018](../../catalog/ts_real_train.yaml#L114) | 116.6 | 已登记 | 没有 |
| [ts_real_train@v2-20261018-enroll-qc-20261021](../../catalog/ts_real_enroll_qc.yaml#L119) | — | 未登记 | 没有 |
| [ts_real_train@v2-20261018-utts](../../catalog/ts_real_train.yaml#L572) | 116.6 | 已登记 | 没有 |
| [ts_real_train@v2-20261018-utts-punc-20261102](../../catalog/train_punc_v1_derived.yaml#L1381) | — | 未登记 | 没有 |
| [ts_real_train@v3-20261020](../../catalog/ts_real_train.yaml#L228) | 105.0 | 已登记 | 没有 |
| [ts_real_train@v3-20261020-enroll-qc-20261021](../../catalog/ts_real_enroll_qc.yaml#L204) | — | 未登记 | 没有 |
| [ts_real_train@v3-20261020-utts](../../catalog/ts_real_train.yaml#L457) | 105.0 | 已登记 | 没有 |
| [ts_real_train@v3-20261020-utts-punc-20261102](../../catalog/train_punc_v1_derived.yaml#L1475) | — | 未登记 | 没有 |

- `ts_real_train@en-v1-20261101`：英文真实会议的目标说话人窗口（训练划分）：AMI train 单远场麦 Array1-01、NOTSOFAR-1 train 与 dev 每场一台单通道设备、DiPCo dev 远场设备通道 1（时间轴按近讲麦对齐）、ICSI 中与 test / dev 会议没有共同说话人的 11 场 Bed 会议（官方近讲耳麦混音，镜像音频写成 WAV 放在 source/en-v1-20261101/icsi/），按 ts_real_train v1 的方法切 8–22 秒、由完整语句组成的窗口，说话人数分 1 / 2 / 3+ 三档，用尽所有可用窗口；每个窗口一对样本，同一段音频：目标在场（注册取窗口外同一录音的另一句，3–6 秒）和目标缺席（同一录音里没在窗口说话的另一人，没有则取其他录音中同样不在窗口说话的人）。转写清洗沿用英文评测 ts_asr_real en-v2-20261031（scripts/ts_real/english.py），目标各句须都有完整转写；每条注册过英文评测的声纹核对（WeSpeaker ECAPA），不过的换一句或丢掉这一对。评测用的 AMI dev/test、NOTSOFAR-1 eval、DiPCo eval、ICSI test/dev 会议及其说话人都不在内（report.json 的 heldout）。不含 CHiME-6（train 标注没有房间信息）。记录带 metadata.window_utts 与 target_speaker。音频是原始长录音的片段，channel: 0。脚本 scripts/ts_robust/build_ts_real_train_en.py
- `ts_real_train@en-v1-20261101-utts`：ts_real_train@en-v1-20261101 的同一批记录，构建脚本自带的 metadata.window_utts / target_speaker 按与其他 -utts 版本相同的规则复核：正样本的目标语句与转写逐字一致（忽略空白和标点）才保留时间线，负样本只有注册人确实不在窗口里说话才保留；不满足的记录去掉 window_utts（保留 target_speaker），ID 列在 excluded-records-<split>.txt。供 open-audio-llm 帧级说话人活动标签（objective.ts_activity_weight）。其余字段不变，音频引用改指本版本，音频索引与原版逐行相同。生成脚本 audio-data-contract scripts/ts_robust/add_window_utts.py（keep），逐划分统计见 report.json
- `ts_real_train@en-v1-20261101-utts-punc-20261102`：ts_real_train@en-v1-20261101-utts 的 ami, dipco，目标文本加书面化标点：中文用 amphiondata 的中文学生模型（punc-student-v1，不带听音提示），英文用英文规范 en-v1 的学生模型（加标点并恢复大小写）；标点按字 / 按词搬回原文，原文的字词不变，找不到输出的目标保留原样。其余字段与源版本相同，音频引用源版本
- `ts_real_train@v1-20261017`：真实会议的目标说话人窗口（训练划分）：AliMeeting 远场、AISHELL-4、MagicData-RAMC 的 train 划分，按 ts_asr_real 的方法切 8–22 秒、由完整语句组成的窗口，说话人数分 1 / 2 / 3+ 三档；每个窗口一对样本，同一段音频：目标在场（注册取窗口外同一录音的另一句）和目标缺席（同一录音里没在窗口说话的另一人，没有则取其他录音）。音频是原始长录音的片段，记录里写 channel: 0，读第 0 声道，与评测一致（现有 turn-taking 训练集读 8 个声道的平均）。脚本 scripts/ts_robust/build_ts_real_train.py
- `ts_real_train@v1-20261017-utts`：ts_real_train@v1-20261017 的同一批记录，时间线取自 AliMeeting 远场、AISHELL-4、RAMC 的 icefall-20260908 train 人工标注。加 metadata.window_utts（窗口内每句的说话人与相对混合起点的起止，取自来源标注并截到窗口，截断的标 clipped）与同一命名空间的 metadata.target_speaker，供 open-audio-llm 帧级说话人活动标签（objective.ts_activity_weight）；其余字段不变，音频引用改指本版本，音频索引与原版逐行相同。正样本的目标语句与转写逐字一致（忽略空白和标点；窗口边缘截断的句子允许只转写一部分）才写时间线，负样本只有注册人确实不在窗口里说话才写；其余记录不写时间线（不出帧级标签）。负样本中注册人按标注其实在窗口内说话的记录 ID 列在 excluded-records-<split>.txt，训练配方用 exclude_records 排除。生成脚本 audio-data-contract scripts/ts_robust/add_window_utts.py，逐划分统计见 report.json
- `ts_real_train@v1-20261017-utts-enroll-qc-20261021`：ts_real_train@v1-20261017-utts-punc-20261102 的全部记录（aishell4, alimeeting, ramc），内容与父版本相同，新增 metadata.enrollment_check：目标缺席记录给出注册说话人在窗口内实际说话的秒数（enrolled_speaker_talk_seconds，大于 0 说明这条并不缺席，因为 AliMeeting / AISHELL-4 / RAMC 的说话人编号跨会议通用，从别的会议取的注册人可能也在本窗口里说话）；音频索引沿用父版本，不复制音频；本版本只带标注，训练配方仍引用父版本。脚本 scripts/label_registration/register_ts_real_enroll_qc.py，检查工具 scripts/label_registration/scan_enrolled_in_window.py、scripts/ts_robust/qc_ts_real_train_v3.py
- `ts_real_train@v1-20261017-utts-punc-20261102`：ts_real_train@v1-20261017-utts 的 aishell4, alimeeting, ramc，目标文本加书面化标点：中文用 amphiondata 的中文学生模型（punc-student-v1，不带听音提示），英文用英文规范 en-v1 的学生模型（加标点并恢复大小写）；标点按字 / 按词搬回原文，原文的字词不变，找不到输出的目标保留原样。其余字段与源版本相同，音频引用源版本
- `ts_real_train@v2-20261018`：真实会议的目标说话人重叠窗口（训练划分）：AliMeeting 远场、AISHELL-4、MagicData-RAMC 的 train 划分，按 ts_asr_real overlap 版的方法以目标说话人为锚切 8–26 秒窗口（目标的语句完整，别人的语句截到窗口边界，记录 metadata.window_utts 给出窗口内每句的起止和说话人，截断的标 clipped），按目标语音被别人重叠的比例分 o0（≤5%）/ o20（5–20%）/ o50（20–50%）/ o100（>50%）四档（RAMC 标注没有重叠，只有 o0）；每个窗口一对样本，同一段音频：目标在场（注册取窗口外同一录音的另一句）和目标缺席（同一录音里没在窗口说话的另一人，没有则取其他录音）。去掉含 dev / test 说话人的录音（RAMC 14 段）。音频是原始长录音的片段，记录里写 channel: 0，读第 0 声道，与评测一致。脚本 scripts/ts_robust/build_ts_real_train.py --recipe v2
- `ts_real_train@v2-20261018-enroll-qc-20261021`：ts_real_train@v2-20261018-utts-punc-20261102 的全部记录（aishell4, alimeeting），内容与父版本相同，新增 metadata.enrollment_check：目标缺席记录给出注册说话人在窗口内实际说话的秒数（enrolled_speaker_talk_seconds，大于 0 说明这条并不缺席，因为 AliMeeting / AISHELL-4 / RAMC 的说话人编号跨会议通用，从别的会议取的注册人可能也在本窗口里说话）；音频索引沿用父版本，不复制音频；本版本只带标注，训练配方仍引用父版本。脚本 scripts/label_registration/register_ts_real_enroll_qc.py，检查工具 scripts/label_registration/scan_enrolled_in_window.py、scripts/ts_robust/qc_ts_real_train_v3.py
- `ts_real_train@v2-20261018-utts`：ts_real_train@v2-20261018 的同一批记录，v2 自带的 metadata.window_utts / target_speaker 按与其他 -utts 版本相同的规则复核：正样本的目标语句与转写逐字一致（忽略空白和标点；窗口边缘截断的句子允许只转写一部分）才保留时间线，负样本只有注册人确实不在窗口里说话才保留；不满足的记录去掉 window_utts（保留 target_speaker），不出帧级标签。正样本全部通过；45 条负样本（alimeeting 43、ramc 2，都是 other_recording）的注册人与窗口里的说话人是同一人（同一说话人出现在多场录音里），转写为空属于错标，ID 列在 excluded-records-<split>.txt，训练配方用 exclude_records 排除。其余字段不变，音频引用改指本版本，音频索引与原版逐行相同。生成脚本 audio-data-contract scripts/ts_robust/add_window_utts.py（keep），逐划分统计见 report.json
- `ts_real_train@v2-20261018-utts-punc-20261102`：ts_real_train@v2-20261018-utts 的 aishell4, alimeeting，目标文本加书面化标点：中文用 amphiondata 的中文学生模型（punc-student-v1，不带听音提示），英文用英文规范 en-v1 的学生模型（加标点并恢复大小写）；标点按字 / 按词搬回原文，原文的字词不变，找不到输出的目标保留原样。其余字段与源版本相同，音频引用源版本
- `ts_real_train@v3-20261020`：真实录音的目标说话人训练窗口第三版，补 v1 / v2 没有的两类（只生成记录，引用原始录音片段，不复制、不混音）：emilia2_1spk——Emilia2 中文网络对话（emilia2_zh_dialogue_diarize 的 MOSS 伪标签，窗口文本已过 Qwen3-ASR 核对）里只有一个人说话的 8–22 秒整句窗口，每个窗口一对：目标在场（注册取此人窗外另一句）与目标缺席（注册取同一诊断窗口里的另一位说话人），对应评测 real-emilia2-1spk-neg；排除评测留出视频（ts_asr_real v2 的 excluded-recordings）与说话人合并错误窗口；每对用 ERes2NetV2 声纹核对，按对内分布取阈值（同人下限 0.746、异人上限 0.493）剔除 225 对。alimeeting_en_mn / alimeeting_en_mf——AliMeeting train 窗口（窗口切法同 v1，远场人工标注），注册一律取注册人的近场头戴麦，混合取窗口内某位说话人的头戴麦（en_mn，设备离说话人近）或远场第 0 声道（en_mf），在场 / 缺席成对，补评测 nearfar-*-en-mn-neg（近场注册 + 近场混合）的缺席。生成脚本 scripts/ts_robust/build_ts_real_train_v3.py、qc_ts_real_train_v3.py
- `ts_real_train@v3-20261020-enroll-qc-20261021`：ts_real_train@v3-20261020-utts-punc-20261102 的全部记录（alimeeting_en_mf, alimeeting_en_mn, emilia2_1spk），内容与父版本相同，新增 metadata.enrollment_check：目标缺席记录给出注册说话人在窗口内实际说话的秒数（enrolled_speaker_talk_seconds，大于 0 说明这条并不缺席，因为 AliMeeting / AISHELL-4 / RAMC 的说话人编号跨会议通用，从别的会议取的注册人可能也在本窗口里说话）；Emilia2 单人配对给出注册音频与窗口的 ERes2NetV2 余弦（cosine，expected 为应该相同还是不同的说话人）和整对的两个余弦，另附 pair_cosines.json（15000 对），构建时按 same_floor 0.746 / diff_ceiling 0.493 剔除了 225 对。音频索引沿用父版本，不复制音频；本版本只带标注，训练配方仍引用父版本。脚本 scripts/label_registration/register_ts_real_enroll_qc.py，检查工具 scripts/label_registration/scan_enrolled_in_window.py、scripts/ts_robust/qc_ts_real_train_v3.py
- `ts_real_train@v3-20261020-utts`：ts_real_train@v3-20261020 的同一批记录：alimeeting_en_mn / en_mf 的时间线取自 AliMeeting 远场 icefall-20260908 train 人工标注（近讲与远场文件对齐在 0.07 秒内），emilia2_1spk 取自记录所引用的 MOSS 日志窗口。加 metadata.window_utts（窗口内每句的说话人与相对混合起点的起止，取自来源标注并截到窗口，截断的标 clipped）与同一命名空间的 metadata.target_speaker，供 open-audio-llm 帧级说话人活动标签（objective.ts_activity_weight）；其余字段不变，音频引用改指本版本，音频索引与原版逐行相同。正样本的目标语句与转写逐字一致（忽略空白和标点；窗口边缘截断的句子允许只转写一部分）才写时间线，负样本只有注册人确实不在窗口里说话才写；其余记录不写时间线（不出帧级标签）。负样本中注册人按标注其实在窗口内说话的记录 ID 列在 excluded-records-<split>.txt，训练配方用 exclude_records 排除。生成脚本 audio-data-contract scripts/ts_robust/add_window_utts.py，逐划分统计见 report.json
- `ts_real_train@v3-20261020-utts-punc-20261102`：ts_real_train@v3-20261020-utts 的 alimeeting_en_mf, alimeeting_en_mn, emilia2_1spk，目标文本加书面化标点：中文用 amphiondata 的中文学生模型（punc-student-v1，不带听音提示），英文用英文规范 en-v1 的学生模型（加标点并恢复大小写）；标点按字 / 按词搬回原文，原文的字词不变，找不到输出的目标保留原样。其余字段与源版本相同，音频引用源版本
- 含派生版本（与源数据可能重叠）

### ts_scene_pool

目标说话人难例场景素材（相近声音、交接）

语言：en、es、zh · 任务：目标说话人语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [ts_scene_pool@alt-twins-20261024](../../catalog/ts_scene_pool.yaml#L1177) | 316.4 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |
| [ts_scene_pool@alt-twins-20261024-punchw-20261102](../../catalog/train_punc_v1_pools.yaml#L2) | 316.4 | 已登记 | 没有 |
| [ts_scene_pool@alt-twins-20261024-punchw2-20261102](../../catalog/train_punc_v1_pools_en.yaml#L2) | 148.3 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |
| [ts_scene_pool@csd-alt-twins-20261101](../../catalog/ts_scene_pool.yaml#L1944) | 10.8 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |
| [ts_scene_pool@csd-alt-twins-20261101-punchw-20261102](../../catalog/train_punc_v1_pools.yaml#L91) | 10.8 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |
| [ts_scene_pool@csd-alt-twins-20261101-punchw2-20261102](../../catalog/train_punc_v1_pools_en.yaml#L62) | 10.8 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |
| [ts_scene_pool@csd-handover-20261101](../../catalog/ts_scene_pool.yaml#L2064) | 6.8 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |
| [ts_scene_pool@csd-handover-20261101-punchw-20261102](../../catalog/train_punc_v1_pools.yaml#L151) | 6.8 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |
| [ts_scene_pool@csd-handover-20261101-punchw2-20261102](../../catalog/train_punc_v1_pools_en.yaml#L122) | 6.8 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |
| [ts_scene_pool@csd-hard-20261101](../../catalog/ts_scene_pool.yaml#L2004) | 6.7 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |
| [ts_scene_pool@csd-hard-20261101-punchw-20261102](../../catalog/train_punc_v1_pools.yaml#L211) | 6.7 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |
| [ts_scene_pool@csd-hard-20261101-punchw2-20261102](../../catalog/train_punc_v1_pools_en.yaml#L182) | 6.7 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |
| [ts_scene_pool@csd-near-20261101](../../catalog/ts_scene_pool.yaml#L1884) | 16.3 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |
| [ts_scene_pool@csd-near-20261101-punchw-20261102](../../catalog/train_punc_v1_pools.yaml#L271) | 16.3 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |
| [ts_scene_pool@csd-near-20261101-punchw2-20261102](../../catalog/train_punc_v1_pools_en.yaml#L242) | 16.3 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |
| [ts_scene_pool@csd-solo-20261101](../../catalog/ts_scene_pool.yaml#L2124) | 8.3 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |
| [ts_scene_pool@csd-solo-20261101-punchw-20261102](../../catalog/train_punc_v1_pools.yaml#L331) | 8.3 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |
| [ts_scene_pool@csd-solo-20261101-punchw2-20261102](../../catalog/train_punc_v1_pools_en.yaml#L302) | 8.3 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |
| [ts_scene_pool@cvaccent-alt-twins-20261101](../../catalog/ts_scene_pool.yaml#L1644) | 60.7 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |
| [ts_scene_pool@cvaccent-alt-twins-20261101-punchw-20261102](../../catalog/train_punc_v1_pools.yaml#L391) | 60.7 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |
| [ts_scene_pool@cvaccent-alt-twins-20261101-punchw2-20261102](../../catalog/train_punc_v1_pools_en.yaml#L362) | 60.7 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |
| [ts_scene_pool@cvaccent-handover-20261101](../../catalog/ts_scene_pool.yaml#L1764) | 30.7 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |
| [ts_scene_pool@cvaccent-handover-20261101-punchw-20261102](../../catalog/train_punc_v1_pools.yaml#L451) | 30.7 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |
| [ts_scene_pool@cvaccent-handover-20261101-punchw2-20261102](../../catalog/train_punc_v1_pools_en.yaml#L422) | 30.7 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |
| [ts_scene_pool@cvaccent-hard-20261101](../../catalog/ts_scene_pool.yaml#L1704) | 37.9 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |
| [ts_scene_pool@cvaccent-hard-20261101-punchw-20261102](../../catalog/train_punc_v1_pools.yaml#L511) | 37.9 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |
| [ts_scene_pool@cvaccent-hard-20261101-punchw2-20261102](../../catalog/train_punc_v1_pools_en.yaml#L482) | 37.9 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |
| [ts_scene_pool@cvaccent-near-20261101](../../catalog/ts_scene_pool.yaml#L1584) | 91.2 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |
| [ts_scene_pool@cvaccent-near-20261101-punchw-20261102](../../catalog/train_punc_v1_pools.yaml#L571) | 91.2 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |
| [ts_scene_pool@cvaccent-near-20261101-punchw2-20261102](../../catalog/train_punc_v1_pools_en.yaml#L542) | 91.2 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |
| [ts_scene_pool@cvaccent-solo-20261101](../../catalog/ts_scene_pool.yaml#L1824) | 44.7 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |
| [ts_scene_pool@cvaccent-solo-20261101-punchw-20261102](../../catalog/train_punc_v1_pools.yaml#L631) | 44.7 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |
| [ts_scene_pool@cvaccent-solo-20261101-punchw2-20261102](../../catalog/train_punc_v1_pools_en.yaml#L602) | 44.7 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |
| [ts_scene_pool@es-1spk-20261110](../../catalog/ts_scene_pool_es.yaml#L587) | 513.8 | 已登记 | 没有 |
| [ts_scene_pool@es-1spk-v2-20261110](../../catalog/ts_scene_pool_es.yaml#L631) | 374.0 | 已登记 | 没有 |
| [ts_scene_pool@es-alt-twins-20261109](../../catalog/ts_scene_pool_es.yaml#L119) | 54.6 | 已登记 | 没有 |
| [ts_scene_pool@es-alt-twins-20261109-punchw-20261109](../../catalog/ts_scene_pool_es.yaml#L177) | 54.6 | 已登记 | 没有 |
| [ts_scene_pool@es-handover-20261109](../../catalog/ts_scene_pool_es.yaml#L353) | 26.2 | 已登记 | 没有 |
| [ts_scene_pool@es-handover-20261109-punchw-20261109](../../catalog/ts_scene_pool_es.yaml#L411) | 26.2 | 已登记 | 没有 |
| [ts_scene_pool@es-hard-20261109](../../catalog/ts_scene_pool_es.yaml#L236) | 35.4 | 已登记 | 没有 |
| [ts_scene_pool@es-hard-20261109-punchw-20261109](../../catalog/ts_scene_pool_es.yaml#L294) | 35.4 | 已登记 | 没有 |
| [ts_scene_pool@es-near-20261109](../../catalog/ts_scene_pool_es.yaml#L2) | 87.8 | 已登记 | 没有 |
| [ts_scene_pool@es-near-20261109-punchw-20261109](../../catalog/ts_scene_pool_es.yaml#L60) | 87.8 | 已登记 | 没有 |
| [ts_scene_pool@es-solo-20261109](../../catalog/ts_scene_pool_es.yaml#L470) | 25.8 | 已登记 | 没有 |
| [ts_scene_pool@es-solo-20261109-punchw-20261109](../../catalog/ts_scene_pool_es.yaml#L528) | 25.8 | 已登记 | 没有 |
| [ts_scene_pool@es-v1-20261108](../../catalog/es_train_v1.yaml#L168) | — | 未登记 | 没有 |
| [ts_scene_pool@handover-20261021](../../catalog/ts_scene_pool.yaml#L515) | 62.9 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |
| [ts_scene_pool@handover-20261021-punchw-20261102](../../catalog/train_punc_v1_pools.yaml#L691) | 62.9 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |
| [ts_scene_pool@handover-20261021-punchw2-20261102](../../catalog/train_punc_v1_pools_en.yaml#L662) | 18.0 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |
| [ts_scene_pool@hard-20261016](../../catalog/ts_scene_pool.yaml#L86) | 81.7 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |
| [ts_scene_pool@hard-20261016-punchw-20261102](../../catalog/train_punc_v1_pools.yaml#L780) | 81.7 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |
| [ts_scene_pool@hard-20261016-punchw2-20261102](../../catalog/train_punc_v1_pools_en.yaml#L722) | 37.0 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |
| [ts_scene_pool@hard-twins-20261026](../../catalog/ts_scene_pool.yaml#L1497) | 81.9 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |
| [ts_scene_pool@magicdata-20261023](../../catalog/ts_scene_pool.yaml#L660) | 96.2 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |
| [ts_scene_pool@magicdata-alt-20261023](../../catalog/ts_scene_pool.yaml#L948) | 71.0 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |
| [ts_scene_pool@magicdata-alt-twins-20261024](../../catalog/ts_scene_pool.yaml#L1325) | 71.5 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |
| [ts_scene_pool@magicdata-alt-twins-20261024-punchw-20261102](../../catalog/train_punc_v1_pools.yaml#L869) | 71.5 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |
| [ts_scene_pool@magicdata-handover-20261023](../../catalog/ts_scene_pool.yaml#L1005) | 48.6 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |
| [ts_scene_pool@magicdata-handover-20261023-punchw-20261102](../../catalog/train_punc_v1_pools.yaml#L929) | 48.6 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |
| [ts_scene_pool@magicdata-hard-20261023](../../catalog/ts_scene_pool.yaml#L1120) | 47.8 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |
| [ts_scene_pool@magicdata-hard-20261023-punchw-20261102](../../catalog/train_punc_v1_pools.yaml#L989) | 47.8 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |
| [ts_scene_pool@magicdata-hard-twins-20261026](../../catalog/ts_scene_pool.yaml#L1440) | 47.9 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |
| [ts_scene_pool@magicdata-near-20261023](../../catalog/ts_scene_pool.yaml#L776) | 96.0 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |
| [ts_scene_pool@magicdata-near-20261023-punchw-20261102](../../catalog/train_punc_v1_pools.yaml#L1049) | 96.0 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |
| [ts_scene_pool@multi-20261017](../../catalog/ts_scene_pool.yaml#L171) | 193.4 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |
| [ts_scene_pool@multi-20261017-punchw-20261102](../../catalog/train_punc_v1_pools.yaml#L1109) | 193.4 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |
| [ts_scene_pool@multi-20261017-punchw2-20261102](../../catalog/train_punc_v1_pools_en.yaml#L782) | 59.2 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |
| [ts_scene_pool@multi-20261018](../../catalog/ts_scene_pool.yaml#L257) | 386.2 | 已登记 | 没有 |
| [ts_scene_pool@ramc-alt-twins-20261028](../../catalog/ts_scene_pool.yaml#L2243) | 37.1 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |
| [ts_scene_pool@ramc-handover-20261028](../../catalog/ts_scene_pool.yaml#L2359) | 24.9 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |
| [ts_scene_pool@ramc-hard-20261028](../../catalog/ts_scene_pool.yaml#L2301) | 24.9 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |
| [ts_scene_pool@ramc-near-20261028](../../catalog/ts_scene_pool.yaml#L2184) | 49.1 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |
| [ts_scene_pool@solo-20261019](../../catalog/ts_scene_pool.yaml#L343) | 97.2 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |
| [ts_scene_pool@solo-20261020](../../catalog/ts_scene_pool.yaml#L429) | 97.2 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |
| [ts_scene_pool@solo-20261020-punchw-20261102](../../catalog/train_punc_v1_pools.yaml#L1198) | 97.2 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |
| [ts_scene_pool@solo-20261020-punchw2-20261102](../../catalog/train_punc_v1_pools_en.yaml#L842) | 29.9 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |
| [ts_scene_pool@v2-20261016](../../catalog/ts_scene_pool.yaml#L1) | 315.8 | 已登记 | 没有 |
| [ts_scene_pool@xsession-20261023](../../catalog/ts_scene_pool.yaml#L602) | 116.1 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |
| [ts_scene_pool@xsession-alt-20261023](../../catalog/ts_scene_pool.yaml#L833) | 83.9 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |
| [ts_scene_pool@xsession-alt-twins-20261024](../../catalog/ts_scene_pool.yaml#L1266) | 85.1 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |
| [ts_scene_pool@xsession-alt-twins-20261024-punchw-20261102](../../catalog/train_punc_v1_pools.yaml#L1287) | 85.1 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |
| [ts_scene_pool@xsession-handover-20261023](../../catalog/ts_scene_pool.yaml#L891) | 58.5 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |
| [ts_scene_pool@xsession-handover-20261023-punchw-20261102](../../catalog/train_punc_v1_pools.yaml#L1347) | 58.5 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |
| [ts_scene_pool@xsession-hard-20261023](../../catalog/ts_scene_pool.yaml#L1062) | 57.4 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |
| [ts_scene_pool@xsession-hard-20261023-punchw-20261102](../../catalog/train_punc_v1_pools.yaml#L1407) | 57.4 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |
| [ts_scene_pool@xsession-hard-twins-20261026](../../catalog/ts_scene_pool.yaml#L1383) | 57.2 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |
| [ts_scene_pool@xsession-near-20261023](../../catalog/ts_scene_pool.yaml#L718) | 116.0 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |
| [ts_scene_pool@xsession-near-20261023-punchw-20261102](../../catalog/train_punc_v1_pools.yaml#L1467) | 116.0 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ts_scene_pool/` |

- `ts_scene_pool@alt-twins-20261024`：v2-20261016 的同配方带孪生版：alternate/burst/short 场景（AISHELL-2 / LibriSpeech 目标），30% 为孪生样本，即同一场景换成另一个人注册（一半是 speaker-neighbors-20261016 的相近声音），目标为空；注册音频不选与目标同一句的话。起因：轮流说话场景在训练里几乎只有在场（v2-20261016、xsession-alt-20261023、magicdata-alt-20261023 没有缺席样本，hard 池的缺席只有交替 / 插话、没有短句），模型学成“其中总有一个是目标”；换成同池另一个人注册后，044@5000 在 xsession-alt 场景仍转写 43%（短句 65%），10.21 版本在 v2 场景 17%，带孪生的多人重叠池 4–8%；ts-asr-benchmark@v12 上 KeSpeech 注册人缺席误输出 2.6% → 17.8%
- `ts_scene_pool@alt-twins-20261024-punchw-20261102`：ts_scene_pool@alt-twins-20261024 的 en, zh，供 TS + 热词训练：每条目标句按片段 ID 换成带书面化标点的写法（中文 punc-written-v1，英文 en-v1 加标点并恢复大小写；去掉标点和空格、转小写后与原目标一致才替换，源语料本身带标点的保留原样），hotwords 为目标所说的热词，metadata.interferer_hotwords 为干扰者所说、目标没说的热词（标签：Qwen3.8-27B + amphiondata 热词提示词，已有的 hw_sft 标签复用）。其余字段、场景与音频同源版本（记录仍引用源版本音频）。en：100000 条，目标改写 70019，带目标热词 19721，带干扰者热词 80998；zh：150000 条，目标改写 104809，带目标热词 42819，带干扰者热词 120243
- `ts_scene_pool@alt-twins-20261024-punchw2-20261102`：ts_scene_pool@alt-twins-20261024 的 en，供 TS + 热词训练：每条目标句按片段 ID 换成带书面化标点的写法（中文 punc-written-v1，英文 en-v1 加标点并恢复大小写；去掉标点和空格、转小写后与原目标一致才替换，源语料本身带标点的保留原样），hotwords 为目标所说的热词，metadata.interferer_hotwords 为干扰者所说、目标没说的热词（标签：Qwen3.8-27B + amphiondata 热词提示词，已有的 hw_sft 标签复用；英文按整词匹配，所有格算同一个词，干扰者热词按其所在句的大小写还原写法）。其余字段、场景与音频同源版本（记录仍引用源版本音频）。en：100000 条，目标改写 70019，带目标热词 20566，带干扰者热词 80998
- `ts_scene_pool@csd-alt-twins-20261101`：csd-alt-twins-20261101：alternate/burst/short 轮流与插话场景，约 30% 缺席孪生（一半近邻注册）。CS-Dialogue 英文 train 140 位说话人（中国人说英语）为目标，含 <NPS/>（旁人说话）或 **（听不清）的句子不用、其余标签去掉（与 ts-asr-benchmark-en 一致），他人一半 CS-Dialogue、Common Voice 口音说话人与 LibriSpeech 各四分之一；孪生注册人取另一位 CS-Dialogue 说话人或近邻，近邻表 speaker-neighbors-en-accents-20261101。CS-Dialogue dev/test 说话人剔除（test 是评测目标），按说话人 ID 核对无重叠。起因：10.28 版本在 ts-asr-benchmark-en 的 CS-Dialogue 目标上词错率 44.6%
- `ts_scene_pool@csd-alt-twins-20261101-punchw-20261102`：ts_scene_pool@csd-alt-twins-20261101 的 en，供 TS + 热词训练：每条目标句按片段 ID 换成带书面化标点的写法（中文 punc-written-v1，英文 en-v1 加标点并恢复大小写；去掉标点和空格、转小写后与原目标一致才替换，源语料本身带标点的保留原样），hotwords 为目标所说的热词，metadata.interferer_hotwords 为干扰者所说、目标没说的热词（标签：Qwen3.8-27B + amphiondata 热词提示词，已有的 hw_sft 标签复用）。其余字段、场景与音频同源版本（记录仍引用源版本音频）。en：8000 条，目标改写 0，带目标热词 310，带干扰者热词 4911
- `ts_scene_pool@csd-alt-twins-20261101-punchw2-20261102`：ts_scene_pool@csd-alt-twins-20261101 的 en，供 TS + 热词训练：每条目标句按片段 ID 换成带书面化标点的写法（中文 punc-written-v1，英文 en-v1 加标点并恢复大小写；去掉标点和空格、转小写后与原目标一致才替换，源语料本身带标点的保留原样），hotwords 为目标所说的热词，metadata.interferer_hotwords 为干扰者所说、目标没说的热词（标签：Qwen3.8-27B + amphiondata 热词提示词，已有的 hw_sft 标签复用；英文按整词匹配，所有格算同一个词，干扰者热词按其所在句的大小写还原写法）。其余字段、场景与音频同源版本（记录仍引用源版本音频）。en：8000 条，目标改写 0，带目标热词 313，带干扰者热词 4911
- `ts_scene_pool@csd-handover-20261101`：csd-handover-20261101：交接场景：目标与另一人各说一句、先后不重叠（一半另一人取目标近邻），约 30% 缺席孪生。CS-Dialogue 英文 train 140 位说话人（中国人说英语）为目标，含 <NPS/>（旁人说话）或 **（听不清）的句子不用、其余标签去掉（与 ts-asr-benchmark-en 一致），他人一半 CS-Dialogue、Common Voice 口音说话人与 LibriSpeech 各四分之一；孪生注册人取另一位 CS-Dialogue 说话人或近邻，近邻表 speaker-neighbors-en-accents-20261101。CS-Dialogue dev/test 说话人剔除（test 是评测目标），按说话人 ID 核对无重叠。起因：10.28 版本在 ts-asr-benchmark-en 的 CS-Dialogue 目标上词错率 44.6%
- `ts_scene_pool@csd-handover-20261101-punchw-20261102`：ts_scene_pool@csd-handover-20261101 的 en，供 TS + 热词训练：每条目标句按片段 ID 换成带书面化标点的写法（中文 punc-written-v1，英文 en-v1 加标点并恢复大小写；去掉标点和空格、转小写后与原目标一致才替换，源语料本身带标点的保留原样），hotwords 为目标所说的热词，metadata.interferer_hotwords 为干扰者所说、目标没说的热词（标签：Qwen3.8-27B + amphiondata 热词提示词，已有的 hw_sft 标签复用）。其余字段、场景与音频同源版本（记录仍引用源版本音频）。en：5000 条，目标改写 0，带目标热词 165，带干扰者热词 1214
- `ts_scene_pool@csd-handover-20261101-punchw2-20261102`：ts_scene_pool@csd-handover-20261101 的 en，供 TS + 热词训练：每条目标句按片段 ID 换成带书面化标点的写法（中文 punc-written-v1，英文 en-v1 加标点并恢复大小写；去掉标点和空格、转小写后与原目标一致才替换，源语料本身带标点的保留原样），hotwords 为目标所说的热词，metadata.interferer_hotwords 为干扰者所说、目标没说的热词（标签：Qwen3.8-27B + amphiondata 热词提示词，已有的 hw_sft 标签复用；英文按整词匹配，所有格算同一个词，干扰者热词按其所在句的大小写还原写法）。其余字段、场景与音频同源版本（记录仍引用源版本音频）。en：5000 条，目标改写 0，带目标热词 165，带干扰者热词 1214
- `ts_scene_pool@csd-hard-20261101`：csd-hard-20261101：相近声音场景：他人之一是目标 ERes2NetV2 最近邻前 10 名之一，约 55% 目标缺席（转写为空）。CS-Dialogue 英文 train 140 位说话人（中国人说英语）为目标，含 <NPS/>（旁人说话）或 **（听不清）的句子不用、其余标签去掉（与 ts-asr-benchmark-en 一致），他人一半 CS-Dialogue、Common Voice 口音说话人与 LibriSpeech 各四分之一；孪生注册人取另一位 CS-Dialogue 说话人或近邻，近邻表 speaker-neighbors-en-accents-20261101。CS-Dialogue dev/test 说话人剔除（test 是评测目标），按说话人 ID 核对无重叠。起因：10.28 版本在 ts-asr-benchmark-en 的 CS-Dialogue 目标上词错率 44.6%
- `ts_scene_pool@csd-hard-20261101-punchw-20261102`：ts_scene_pool@csd-hard-20261101 的 en，供 TS + 热词训练：每条目标句按片段 ID 换成带书面化标点的写法（中文 punc-written-v1，英文 en-v1 加标点并恢复大小写；去掉标点和空格、转小写后与原目标一致才替换，源语料本身带标点的保留原样），hotwords 为目标所说的热词，metadata.interferer_hotwords 为干扰者所说、目标没说的热词（标签：Qwen3.8-27B + amphiondata 热词提示词，已有的 hw_sft 标签复用）。其余字段、场景与音频同源版本（记录仍引用源版本音频）。en：5000 条，目标改写 0，带目标热词 110，带干扰者热词 3537
- `ts_scene_pool@csd-hard-20261101-punchw2-20261102`：ts_scene_pool@csd-hard-20261101 的 en，供 TS + 热词训练：每条目标句按片段 ID 换成带书面化标点的写法（中文 punc-written-v1，英文 en-v1 加标点并恢复大小写；去掉标点和空格、转小写后与原目标一致才替换，源语料本身带标点的保留原样），hotwords 为目标所说的热词，metadata.interferer_hotwords 为干扰者所说、目标没说的热词（标签：Qwen3.8-27B + amphiondata 热词提示词，已有的 hw_sft 标签复用；英文按整词匹配，所有格算同一个词，干扰者热词按其所在句的大小写还原写法）。其余字段、场景与音频同源版本（记录仍引用源版本音频）。en：5000 条，目标改写 0，带目标热词 110，带干扰者热词 3537
- `ts_scene_pool@csd-near-20261101`：csd-near-20261101：多句场景（multi 同款 full 模式，目标说 2–5 句，1–4 个他人各自一条轨道），约 30% 缺席孪生（同一场景换人注册，一半取目标近邻，转写为空，同一对共用 labels.pair）。CS-Dialogue 英文 train 140 位说话人（中国人说英语）为目标，含 <NPS/>（旁人说话）或 **（听不清）的句子不用、其余标签去掉（与 ts-asr-benchmark-en 一致），他人一半 CS-Dialogue、Common Voice 口音说话人与 LibriSpeech 各四分之一；孪生注册人取另一位 CS-Dialogue 说话人或近邻，近邻表 speaker-neighbors-en-accents-20261101。CS-Dialogue dev/test 说话人剔除（test 是评测目标），按说话人 ID 核对无重叠。起因：10.28 版本在 ts-asr-benchmark-en 的 CS-Dialogue 目标上词错率 44.6%
- `ts_scene_pool@csd-near-20261101-punchw-20261102`：ts_scene_pool@csd-near-20261101 的 en，供 TS + 热词训练：每条目标句按片段 ID 换成带书面化标点的写法（中文 punc-written-v1，英文 en-v1 加标点并恢复大小写；去掉标点和空格、转小写后与原目标一致才替换，源语料本身带标点的保留原样），hotwords 为目标所说的热词，metadata.interferer_hotwords 为干扰者所说、目标没说的热词（标签：Qwen3.8-27B + amphiondata 热词提示词，已有的 hw_sft 标签复用）。其余字段、场景与音频同源版本（记录仍引用源版本音频）。en：12000 条，目标改写 0，带目标热词 1193，带干扰者热词 7735
- `ts_scene_pool@csd-near-20261101-punchw2-20261102`：ts_scene_pool@csd-near-20261101 的 en，供 TS + 热词训练：每条目标句按片段 ID 换成带书面化标点的写法（中文 punc-written-v1，英文 en-v1 加标点并恢复大小写；去掉标点和空格、转小写后与原目标一致才替换，源语料本身带标点的保留原样），hotwords 为目标所说的热词，metadata.interferer_hotwords 为干扰者所说、目标没说的热词（标签：Qwen3.8-27B + amphiondata 热词提示词，已有的 hw_sft 标签复用；英文按整词匹配，所有格算同一个词，干扰者热词按其所在句的大小写还原写法）。其余字段、场景与音频同源版本（记录仍引用源版本音频）。en：12000 条，目标改写 0，带目标热词 1199，带干扰者热词 7735
- `ts_scene_pool@csd-solo-20261101`：csd-solo-20261101：短句单人场景：目标单独说一句 1–3.5 秒的话，没有其他说话人，约 30% 缺席孪生（一半近邻注册）。CS-Dialogue 英文 train 140 位说话人（中国人说英语）为目标，含 <NPS/>（旁人说话）或 **（听不清）的句子不用、其余标签去掉（与 ts-asr-benchmark-en 一致），他人一半 CS-Dialogue、Common Voice 口音说话人与 LibriSpeech 各四分之一；孪生注册人取另一位 CS-Dialogue 说话人或近邻，近邻表 speaker-neighbors-en-accents-20261101。CS-Dialogue dev/test 说话人剔除（test 是评测目标），按说话人 ID 核对无重叠。起因：10.28 版本在 ts-asr-benchmark-en 的 CS-Dialogue 目标上词错率 44.6%
- `ts_scene_pool@csd-solo-20261101-punchw-20261102`：ts_scene_pool@csd-solo-20261101 的 en，供 TS + 热词训练：每条目标句按片段 ID 换成带书面化标点的写法（中文 punc-written-v1，英文 en-v1 加标点并恢复大小写；去掉标点和空格、转小写后与原目标一致才替换，源语料本身带标点的保留原样），hotwords 为目标所说的热词，metadata.interferer_hotwords 为干扰者所说、目标没说的热词（标签：Qwen3.8-27B + amphiondata 热词提示词，已有的 hw_sft 标签复用）。其余字段、场景与音频同源版本（记录仍引用源版本音频）。en：6000 条，目标改写 0，带目标热词 93，带干扰者热词 33
- `ts_scene_pool@csd-solo-20261101-punchw2-20261102`：ts_scene_pool@csd-solo-20261101 的 en，供 TS + 热词训练：每条目标句按片段 ID 换成带书面化标点的写法（中文 punc-written-v1，英文 en-v1 加标点并恢复大小写；去掉标点和空格、转小写后与原目标一致才替换，源语料本身带标点的保留原样），hotwords 为目标所说的热词，metadata.interferer_hotwords 为干扰者所说、目标没说的热词（标签：Qwen3.8-27B + amphiondata 热词提示词，已有的 hw_sft 标签复用；英文按整词匹配，所有格算同一个词，干扰者热词按其所在句的大小写还原写法）。其余字段、场景与音频同源版本（记录仍引用源版本音频）。en：6000 条，目标改写 0，带目标热词 93，带干扰者热词 33
- `ts_scene_pool@cvaccent-alt-twins-20261101`：cvaccent-alt-twins-20261101：alternate/burst/short 轮流与插话场景，约 30% 缺席孪生（一半近邻注册）。Common Voice 英文 train 带口音标注的目标说话人（至少 6 句 1–8 秒，按口音组抽取：每组占比为说话人数平方根、单组不超过 15%；文本、清洗通过标记与口音取自 common_voice_en@icefall-20260908 的双引擎清洗清单，未通过的句子不用），他人一半同批口音说话人、一半 LibriSpeech train；随机孪生注册人按同样口音占比抽取，近邻孪生取近邻（美式口音注册人约一半缺席，其他口音 21–28%），labels.accent 记注册人口音组；近邻表 speaker-neighbors-en-accents-20261101（ERes2NetV2）。剔除三份语料 dev/test 说话人，不含 VCTK。起因：10.28 版本在 ts-asr-benchmark-en 上 VCTK 口音目标 13.8% 判为缺席（苏格兰、爱尔兰、加拿大约 20%，短目标 27%），LibriSpeech 目标 1.8%；训练英文目标 63% 是 LibriSpeech
- `ts_scene_pool@cvaccent-alt-twins-20261101-punchw-20261102`：ts_scene_pool@cvaccent-alt-twins-20261101 的 en，供 TS + 热词训练：每条目标句按片段 ID 换成带书面化标点的写法（中文 punc-written-v1，英文 en-v1 加标点并恢复大小写；去掉标点和空格、转小写后与原目标一致才替换，源语料本身带标点的保留原样），hotwords 为目标所说的热词，metadata.interferer_hotwords 为干扰者所说、目标没说的热词（标签：Qwen3.8-27B + amphiondata 热词提示词，已有的 hw_sft 标签复用）。其余字段、场景与音频同源版本（记录仍引用源版本音频）。en：40000 条，目标改写 0，带目标热词 12087，带干扰者热词 33224
- `ts_scene_pool@cvaccent-alt-twins-20261101-punchw2-20261102`：ts_scene_pool@cvaccent-alt-twins-20261101 的 en，供 TS + 热词训练：每条目标句按片段 ID 换成带书面化标点的写法（中文 punc-written-v1，英文 en-v1 加标点并恢复大小写；去掉标点和空格、转小写后与原目标一致才替换，源语料本身带标点的保留原样），hotwords 为目标所说的热词，metadata.interferer_hotwords 为干扰者所说、目标没说的热词（标签：Qwen3.8-27B + amphiondata 热词提示词，已有的 hw_sft 标签复用；英文按整词匹配，所有格算同一个词，干扰者热词按其所在句的大小写还原写法）。其余字段、场景与音频同源版本（记录仍引用源版本音频）。en：40000 条，目标改写 0，带目标热词 12365，带干扰者热词 33224
- `ts_scene_pool@cvaccent-handover-20261101`：cvaccent-handover-20261101：交接场景：目标与另一人各说一句、先后不重叠（一半另一人取目标近邻），约 30% 缺席孪生。Common Voice 英文 train 带口音标注的目标说话人（至少 6 句 1–8 秒，按口音组抽取：每组占比为说话人数平方根、单组不超过 15%；文本、清洗通过标记与口音取自 common_voice_en@icefall-20260908 的双引擎清洗清单，未通过的句子不用），他人一半同批口音说话人、一半 LibriSpeech train；随机孪生注册人按同样口音占比抽取，近邻孪生取近邻（美式口音注册人约一半缺席，其他口音 21–28%），labels.accent 记注册人口音组；近邻表 speaker-neighbors-en-accents-20261101（ERes2NetV2）。剔除三份语料 dev/test 说话人，不含 VCTK。起因：10.28 版本在 ts-asr-benchmark-en 上 VCTK 口音目标 13.8% 判为缺席（苏格兰、爱尔兰、加拿大约 20%，短目标 27%），LibriSpeech 目标 1.8%；训练英文目标 63% 是 LibriSpeech
- `ts_scene_pool@cvaccent-handover-20261101-punchw-20261102`：ts_scene_pool@cvaccent-handover-20261101 的 en，供 TS + 热词训练：每条目标句按片段 ID 换成带书面化标点的写法（中文 punc-written-v1，英文 en-v1 加标点并恢复大小写；去掉标点和空格、转小写后与原目标一致才替换，源语料本身带标点的保留原样），hotwords 为目标所说的热词，metadata.interferer_hotwords 为干扰者所说、目标没说的热词（标签：Qwen3.8-27B + amphiondata 热词提示词，已有的 hw_sft 标签复用）。其余字段、场景与音频同源版本（记录仍引用源版本音频）。en：20000 条，目标改写 0，带目标热词 5855，带干扰者热词 9339
- `ts_scene_pool@cvaccent-handover-20261101-punchw2-20261102`：ts_scene_pool@cvaccent-handover-20261101 的 en，供 TS + 热词训练：每条目标句按片段 ID 换成带书面化标点的写法（中文 punc-written-v1，英文 en-v1 加标点并恢复大小写；去掉标点和空格、转小写后与原目标一致才替换，源语料本身带标点的保留原样），hotwords 为目标所说的热词，metadata.interferer_hotwords 为干扰者所说、目标没说的热词（标签：Qwen3.8-27B + amphiondata 热词提示词，已有的 hw_sft 标签复用；英文按整词匹配，所有格算同一个词，干扰者热词按其所在句的大小写还原写法）。其余字段、场景与音频同源版本（记录仍引用源版本音频）。en：20000 条，目标改写 0，带目标热词 6004，带干扰者热词 9339
- `ts_scene_pool@cvaccent-hard-20261101`：cvaccent-hard-20261101：相近声音场景：他人之一是目标 ERes2NetV2 最近邻前 10 名之一，约 55% 目标缺席（转写为空）。Common Voice 英文 train 带口音标注的目标说话人（至少 6 句 1–8 秒，按口音组抽取：每组占比为说话人数平方根、单组不超过 15%；文本、清洗通过标记与口音取自 common_voice_en@icefall-20260908 的双引擎清洗清单，未通过的句子不用），他人一半同批口音说话人、一半 LibriSpeech train；随机孪生注册人按同样口音占比抽取，近邻孪生取近邻（美式口音注册人约一半缺席，其他口音 21–28%），labels.accent 记注册人口音组；近邻表 speaker-neighbors-en-accents-20261101（ERes2NetV2）。剔除三份语料 dev/test 说话人，不含 VCTK。起因：10.28 版本在 ts-asr-benchmark-en 上 VCTK 口音目标 13.8% 判为缺席（苏格兰、爱尔兰、加拿大约 20%，短目标 27%），LibriSpeech 目标 1.8%；训练英文目标 63% 是 LibriSpeech
- `ts_scene_pool@cvaccent-hard-20261101-punchw-20261102`：ts_scene_pool@cvaccent-hard-20261101 的 en，供 TS + 热词训练：每条目标句按片段 ID 换成带书面化标点的写法（中文 punc-written-v1，英文 en-v1 加标点并恢复大小写；去掉标点和空格、转小写后与原目标一致才替换，源语料本身带标点的保留原样），hotwords 为目标所说的热词，metadata.interferer_hotwords 为干扰者所说、目标没说的热词（标签：Qwen3.8-27B + amphiondata 热词提示词，已有的 hw_sft 标签复用）。其余字段、场景与音频同源版本（记录仍引用源版本音频）。en：25000 条，目标改写 0，带目标热词 4898，带干扰者热词 21705
- `ts_scene_pool@cvaccent-hard-20261101-punchw2-20261102`：ts_scene_pool@cvaccent-hard-20261101 的 en，供 TS + 热词训练：每条目标句按片段 ID 换成带书面化标点的写法（中文 punc-written-v1，英文 en-v1 加标点并恢复大小写；去掉标点和空格、转小写后与原目标一致才替换，源语料本身带标点的保留原样），hotwords 为目标所说的热词，metadata.interferer_hotwords 为干扰者所说、目标没说的热词（标签：Qwen3.8-27B + amphiondata 热词提示词，已有的 hw_sft 标签复用；英文按整词匹配，所有格算同一个词，干扰者热词按其所在句的大小写还原写法）。其余字段、场景与音频同源版本（记录仍引用源版本音频）。en：25000 条，目标改写 0，带目标热词 5019，带干扰者热词 21705
- `ts_scene_pool@cvaccent-near-20261101`：cvaccent-near-20261101：多句场景（multi 同款 full 模式，目标说 2–5 句，1–4 个他人各自一条轨道），约 30% 缺席孪生（同一场景换人注册，一半取目标近邻，转写为空，同一对共用 labels.pair）。Common Voice 英文 train 带口音标注的目标说话人（至少 6 句 1–8 秒，按口音组抽取：每组占比为说话人数平方根、单组不超过 15%；文本、清洗通过标记与口音取自 common_voice_en@icefall-20260908 的双引擎清洗清单，未通过的句子不用），他人一半同批口音说话人、一半 LibriSpeech train；随机孪生注册人按同样口音占比抽取，近邻孪生取近邻（美式口音注册人约一半缺席，其他口音 21–28%），labels.accent 记注册人口音组；近邻表 speaker-neighbors-en-accents-20261101（ERes2NetV2）。剔除三份语料 dev/test 说话人，不含 VCTK。起因：10.28 版本在 ts-asr-benchmark-en 上 VCTK 口音目标 13.8% 判为缺席（苏格兰、爱尔兰、加拿大约 20%，短目标 27%），LibriSpeech 目标 1.8%；训练英文目标 63% 是 LibriSpeech
- `ts_scene_pool@cvaccent-near-20261101-punchw-20261102`：ts_scene_pool@cvaccent-near-20261101 的 en，供 TS + 热词训练：每条目标句按片段 ID 换成带书面化标点的写法（中文 punc-written-v1，英文 en-v1 加标点并恢复大小写；去掉标点和空格、转小写后与原目标一致才替换，源语料本身带标点的保留原样），hotwords 为目标所说的热词，metadata.interferer_hotwords 为干扰者所说、目标没说的热词（标签：Qwen3.8-27B + amphiondata 热词提示词，已有的 hw_sft 标签复用）。其余字段、场景与音频同源版本（记录仍引用源版本音频）。en：60000 条，目标改写 0，带目标热词 31058，带干扰者热词 53816
- `ts_scene_pool@cvaccent-near-20261101-punchw2-20261102`：ts_scene_pool@cvaccent-near-20261101 的 en，供 TS + 热词训练：每条目标句按片段 ID 换成带书面化标点的写法（中文 punc-written-v1，英文 en-v1 加标点并恢复大小写；去掉标点和空格、转小写后与原目标一致才替换，源语料本身带标点的保留原样），hotwords 为目标所说的热词，metadata.interferer_hotwords 为干扰者所说、目标没说的热词（标签：Qwen3.8-27B + amphiondata 热词提示词，已有的 hw_sft 标签复用；英文按整词匹配，所有格算同一个词，干扰者热词按其所在句的大小写还原写法）。其余字段、场景与音频同源版本（记录仍引用源版本音频）。en：60000 条，目标改写 0，带目标热词 31507，带干扰者热词 53816
- `ts_scene_pool@cvaccent-solo-20261101`：cvaccent-solo-20261101：短句单人场景：目标单独说一句 1–3.5 秒的话，没有其他说话人，约 30% 缺席孪生（一半近邻注册）。Common Voice 英文 train 带口音标注的目标说话人（至少 6 句 1–8 秒，按口音组抽取：每组占比为说话人数平方根、单组不超过 15%；文本、清洗通过标记与口音取自 common_voice_en@icefall-20260908 的双引擎清洗清单，未通过的句子不用），他人一半同批口音说话人、一半 LibriSpeech train；随机孪生注册人按同样口音占比抽取，近邻孪生取近邻（美式口音注册人约一半缺席，其他口音 21–28%），labels.accent 记注册人口音组；近邻表 speaker-neighbors-en-accents-20261101（ERes2NetV2）。剔除三份语料 dev/test 说话人，不含 VCTK。起因：10.28 版本在 ts-asr-benchmark-en 上 VCTK 口音目标 13.8% 判为缺席（苏格兰、爱尔兰、加拿大约 20%，短目标 27%），LibriSpeech 目标 1.8%；训练英文目标 63% 是 LibriSpeech
- `ts_scene_pool@cvaccent-solo-20261101-punchw-20261102`：ts_scene_pool@cvaccent-solo-20261101 的 en，供 TS + 热词训练：每条目标句按片段 ID 换成带书面化标点的写法（中文 punc-written-v1，英文 en-v1 加标点并恢复大小写；去掉标点和空格、转小写后与原目标一致才替换，源语料本身带标点的保留原样），hotwords 为目标所说的热词，metadata.interferer_hotwords 为干扰者所说、目标没说的热词（标签：Qwen3.8-27B + amphiondata 热词提示词，已有的 hw_sft 标签复用）。其余字段、场景与音频同源版本（记录仍引用源版本音频）。en：30000 条，目标改写 0，带目标热词 5494，带干扰者热词 2446
- `ts_scene_pool@cvaccent-solo-20261101-punchw2-20261102`：ts_scene_pool@cvaccent-solo-20261101 的 en，供 TS + 热词训练：每条目标句按片段 ID 换成带书面化标点的写法（中文 punc-written-v1，英文 en-v1 加标点并恢复大小写；去掉标点和空格、转小写后与原目标一致才替换，源语料本身带标点的保留原样），hotwords 为目标所说的热词，metadata.interferer_hotwords 为干扰者所说、目标没说的热词（标签：Qwen3.8-27B + amphiondata 热词提示词，已有的 hw_sft 标签复用；英文按整词匹配，所有格算同一个词，干扰者热词按其所在句的大小写还原写法）。其余字段、场景与音频同源版本（记录仍引用源版本音频）。en：30000 条，目标改写 0，带目标热词 5567，带干扰者热词 2446
- `ts_scene_pool@es-1spk-20261110`：西班牙语单人 TS-ASR 记录（对应 aishellmix / librimix 的 train_1spk），供训练时在线混音（online_mix：干扰人、目标缺席、无人声窗口、进场与前后留白、注册劣化）：目标是 common_voice_es@es-train-v1-20261108 train 的一句（只含清洗通过的行，书面化文本与热词），注册是同一说话人的另一句（≥ 1.5 秒，固定种子抽取）；只有一句的 130 个说话人不用。356,576 条、4,848 个目标说话人、目标 513.8 h，165,633 条带热词。dev / test 说话人不在 train。生成脚本 scripts/ts_robust/build_ts_1spk_es.py
- `ts_scene_pool@es-1spk-v2-20261110`：西班牙语单人 TS-ASR 记录 v2：同 es-1spk-20261110，但目标只取有口音标注的 Common Voice es 说话人（同西语场景池的目标）；没有口音标注的 2,735 人改作干扰人 （ts_interference_pool@es-v2-20261110），所以目标不会和干扰人是同一人，CV 的声音也不再永远是目标。262,978 条、2,209 个目标说话人、目标 374.0 h，121,222 条带热词；只有一句的 34 个说话人不用。dev / test 说话人不在 train。生成脚本 scripts/ts_robust/build_ts_1spk_es.py
- `ts_scene_pool@es-alt-twins-20261109`：es-alt-twins-20261109：alternate/burst/short 轮流与插话场景，约 30% 缺席孪生（一半近邻注册）。Common Voice 西语 train 带口音标注的目标说话人（至少 6 句 1–8 秒，按 11 个口音组抽取：每组占比为说话人数平方根、单组不超过 15%），他人一半同批口音说话人、一半无口音标注的CV es 说话人（MLS es 没有 ≤8 s 的句子，不进场景）；文本、清洗通过标记取自 common_voice_es@es-train-v1-20261108（未通过的句子不用），labels.accent 记注册人口音组；近邻表 speaker-neighbors-es-accents-20261109（ERes2NetV2）；剔除 CV es dev/test 说话人。规模、模式同英文 cvaccent-*-20261101。 QC 见版本目录 qc.json（通过）
- `ts_scene_pool@es-alt-twins-20261109-punchw-20261109`：ts_scene_pool@es-alt-twins-20261109 的带标点 + 热词版本，供 TS + 热词训练：目标文本本身是 CV es 的书面句子（带标点、大小写），不改；hotwords 为目标所说的热词，metadata.interferer_hotwords 为他人所说、目标没说的热词（Qwen3.8-27B + amphiondata 热词提示词，整词匹配，写法同所在句）。其余字段、场景与音频同源版本（记录引用源版本音频）。40000 条，带目标热词 12327，带他人热词 35085
- `ts_scene_pool@es-handover-20261109`：es-handover-20261109：交接场景：目标与另一人各说一句、先后不重叠（一半另一人取目标近邻），约 30% 缺席孪生。Common Voice 西语 train 带口音标注的目标说话人（至少 6 句 1–8 秒，按 11 个口音组抽取：每组占比为说话人数平方根、单组不超过 15%），他人一半同批口音说话人、一半无口音标注的CV es 说话人（MLS es 没有 ≤8 s 的句子，不进场景）；文本、清洗通过标记取自 common_voice_es@es-train-v1-20261108（未通过的句子不用），labels.accent 记注册人口音组；近邻表 speaker-neighbors-es-accents-20261109（ERes2NetV2）；剔除 CV es dev/test 说话人。规模、模式同英文 cvaccent-*-20261101。 QC 见版本目录 qc.json（通过）
- `ts_scene_pool@es-handover-20261109-punchw-20261109`：ts_scene_pool@es-handover-20261109 的带标点 + 热词版本，供 TS + 热词训练：目标文本本身是 CV es 的书面句子（带标点、大小写），不改；hotwords 为目标所说的热词，metadata.interferer_hotwords 为他人所说、目标没说的热词（Qwen3.8-27B + amphiondata 热词提示词，整词匹配，写法同所在句）。其余字段、场景与音频同源版本（记录引用源版本音频）。20000 条，带目标热词 5736，带他人热词 10049
- `ts_scene_pool@es-hard-20261109`：es-hard-20261109：相近声音场景：他人之一是目标 ERes2NetV2 最近邻前 10 名之一，约 55% 目标缺席（转写为空）。Common Voice 西语 train 带口音标注的目标说话人（至少 6 句 1–8 秒，按 11 个口音组抽取：每组占比为说话人数平方根、单组不超过 15%），他人一半同批口音说话人、一半无口音标注的CV es 说话人（MLS es 没有 ≤8 s 的句子，不进场景）；文本、清洗通过标记取自 common_voice_es@es-train-v1-20261108（未通过的句子不用），labels.accent 记注册人口音组；近邻表 speaker-neighbors-es-accents-20261109（ERes2NetV2）；剔除 CV es dev/test 说话人。规模、模式同英文 cvaccent-*-20261101。 QC 见版本目录 qc.json（通过）
- `ts_scene_pool@es-hard-20261109-punchw-20261109`：ts_scene_pool@es-hard-20261109 的带标点 + 热词版本，供 TS + 热词训练：目标文本本身是 CV es 的书面句子（带标点、大小写），不改；hotwords 为目标所说的热词，metadata.interferer_hotwords 为他人所说、目标没说的热词（Qwen3.8-27B + amphiondata 热词提示词，整词匹配，写法同所在句）。其余字段、场景与音频同源版本（记录引用源版本音频）。25000 条，带目标热词 5030，带他人热词 22151
- `ts_scene_pool@es-near-20261109`：es-near-20261109：多句场景（目标说 2–5 句，1–4 个他人各一条轨道），约 30% 缺席孪生（同一场景换人注册，一半取目标近邻，转写为空）。Common Voice 西语 train 带口音标注的目标说话人（至少 6 句 1–8 秒，按 11 个口音组抽取：每组占比为说话人数平方根、单组不超过 15%），他人一半同批口音说话人、一半无口音标注的CV es 说话人（MLS es 没有 ≤8 s 的句子，不进场景）；文本、清洗通过标记取自 common_voice_es@es-train-v1-20261108（未通过的句子不用），labels.accent 记注册人口音组；近邻表 speaker-neighbors-es-accents-20261109（ERes2NetV2）；剔除 CV es dev/test 说话人。规模、模式同英文 cvaccent-*-20261101。 QC 见版本目录 qc.json（通过）
- `ts_scene_pool@es-near-20261109-punchw-20261109`：ts_scene_pool@es-near-20261109 的带标点 + 热词版本，供 TS + 热词训练：目标文本本身是 CV es 的书面句子（带标点、大小写），不改；hotwords 为目标所说的热词，metadata.interferer_hotwords 为他人所说、目标没说的热词（Qwen3.8-27B + amphiondata 热词提示词，整词匹配，写法同所在句）。其余字段、场景与音频同源版本（记录引用源版本音频）。60000 条，带目标热词 30865，带他人热词 55993
- `ts_scene_pool@es-solo-20261109`：es-solo-20261109：短句单人场景：目标单独说一句 1–3.5 秒的话，没有其他说话人，约 30% 缺席孪生（一半近邻注册）。Common Voice 西语 train 带口音标注的目标说话人（至少 6 句 1–8 秒，按 11 个口音组抽取：每组占比为说话人数平方根、单组不超过 15%），他人一半同批口音说话人、一半无口音标注的CV es 说话人（MLS es 没有 ≤8 s 的句子，不进场景）；文本、清洗通过标记取自 common_voice_es@es-train-v1-20261108（未通过的句子不用），labels.accent 记注册人口音组；近邻表 speaker-neighbors-es-accents-20261109（ERes2NetV2）；剔除 CV es dev/test 说话人。规模、模式同英文 cvaccent-*-20261101。 QC 见版本目录 qc.json（通过）
- `ts_scene_pool@es-solo-20261109-punchw-20261109`：ts_scene_pool@es-solo-20261109 的带标点 + 热词版本，供 TS + 热词训练：目标文本本身是 CV es 的书面句子（带标点、大小写），不改；hotwords 为目标所说的热词，metadata.interferer_hotwords 为他人所说、目标没说的热词（Qwen3.8-27B + amphiondata 热词提示词，整词匹配，写法同所在句）。其余字段、场景与音频同源版本（记录引用源版本音频）。30000 条，带目标热词 7053，带他人热词 3033
- `ts_scene_pool@es-v1-20261108`：西班牙语 TS 场景池的开工占位，已完成：按版本正式登记在 catalog/ts_scene_pool_es.yaml（es-near / es-alt-twins / es-hard / es-handover / es-solo-20261109 及各自的 -punchw-20261109）。目标与他人都取 Common Voice es（他人一半无口音标注的 CV es 说话人）；MLS es 没有 ≤8 s 的句子，不进场景
- `ts_scene_pool@handover-20261021`：交接场景：目标说一句、另一个说话人说一句，前后不重叠、先后随机（alternate，同一注册与转写口径），每句 1–6 秒，注册取同一说话人另一句 2.5–8 秒；另一个说话人一半取目标的近邻声音（speaker-neighbors-20261016，ERes2NetV2 前 10 名，labels.hard_cosine），一半随机。约 30% 是缺席孪生：同两句话，注册人换成另一个人（一半取目标近邻，labels.twin_enrollment），两句都成为干扰人、转写为空，同一对共用 labels.pair。用来补其他场景池缺的“目标 + 仅 1 个他人”轮流场景（alternate 至少 2 个他人，solo 没有他人）：ts-asr-benchmark@v9 的 handover-* 子集里模型约 15% 整条不出字
- `ts_scene_pool@handover-20261021-punchw-20261102`：ts_scene_pool@handover-20261021 的 en, zh，供 TS + 热词训练：每条目标句按片段 ID 换成带书面化标点的写法（中文 punc-written-v1，英文 en-v1 加标点并恢复大小写；去掉标点和空格、转小写后与原目标一致才替换，源语料本身带标点的保留原样），hotwords 为目标所说的热词，metadata.interferer_hotwords 为干扰者所说、目标没说的热词（标签：Qwen3.8-27B + amphiondata 热词提示词，已有的 hw_sft 标签复用）。其余字段、场景与音频同源版本（记录仍引用源版本音频）。en：12000 条，目标改写 8473，带目标热词 2152，带干扰者热词 4411；zh：40000 条，目标改写 28079，带目标热词 10044，带干扰者热词 16029
- `ts_scene_pool@handover-20261021-punchw2-20261102`：ts_scene_pool@handover-20261021 的 en，供 TS + 热词训练：每条目标句按片段 ID 换成带书面化标点的写法（中文 punc-written-v1，英文 en-v1 加标点并恢复大小写；去掉标点和空格、转小写后与原目标一致才替换，源语料本身带标点的保留原样），hotwords 为目标所说的热词，metadata.interferer_hotwords 为干扰者所说、目标没说的热词（标签：Qwen3.8-27B + amphiondata 热词提示词，已有的 hw_sft 标签复用；英文按整词匹配，所有格算同一个词，干扰者热词按其所在句的大小写还原写法）。其余字段、场景与音频同源版本（记录仍引用源版本音频）。en：12000 条，目标改写 8473，带目标热词 2231，带干扰者热词 4411
- `ts_scene_pool@hard-20261016`：相近声音多句场景：目标缺席且相近声音在场（absent，转写为空）或目标与相近声音同时说话（present）。相近说话人取 ERes2NetV2 说话人向量余弦最近邻前 10 名之一（按排名，不设阈值），邻居表在 source/speaker-neighbors-20261016
- `ts_scene_pool@hard-20261016-punchw-20261102`：ts_scene_pool@hard-20261016 的 en, zh，供 TS + 热词训练：每条目标句按片段 ID 换成带书面化标点的写法（中文 punc-written-v1，英文 en-v1 加标点并恢复大小写；去掉标点和空格、转小写后与原目标一致才替换，源语料本身带标点的保留原样），hotwords 为目标所说的热词，metadata.interferer_hotwords 为干扰者所说、目标没说的热词（标签：Qwen3.8-27B + amphiondata 热词提示词，已有的 hw_sft 标签复用）。其余字段、场景与音频同源版本（记录仍引用源版本音频）。en：25000 条，目标改写 11184，带目标热词 3146，带干扰者热词 20379；zh：40000 条，目标改写 18015，带目标热词 7421，带干扰者热词 33799
- `ts_scene_pool@hard-20261016-punchw2-20261102`：ts_scene_pool@hard-20261016 的 en，供 TS + 热词训练：每条目标句按片段 ID 换成带书面化标点的写法（中文 punc-written-v1，英文 en-v1 加标点并恢复大小写；去掉标点和空格、转小写后与原目标一致才替换，源语料本身带标点的保留原样），hotwords 为目标所说的热词，metadata.interferer_hotwords 为干扰者所说、目标没说的热词（标签：Qwen3.8-27B + amphiondata 热词提示词，已有的 hw_sft 标签复用；英文按整词匹配，所有格算同一个词，干扰者热词按其所在句的大小写还原写法）。其余字段、场景与音频同源版本（记录仍引用源版本音频）。en：25000 条，目标改写 11184，带目标热词 3271，带干扰者热词 20379
- `ts_scene_pool@hard-twins-20261026`：hard-20261016 的带孪生版：AISHELL-2 / LibriSpeech 目标的 alternate/burst/short 在场场景，他人之一是目标的相近声音（speaker-neighbors-20261016，ERes2NetV2 最近邻前 10 名之一），每个在场场景后跟一条孪生样本（同一场景换成另一个人注册，一半是目标的另一个相近声音，目标为空），缺席 50%；注册音频不选与目标同一句的话。起因：原 hard 池的缺席场景是单独的场景、没有短句，也不是某个在场场景的孪生，是最后一类没有孪生的场景；048 avg3 在带孪生的场景类别上都好于 10.21 版本，难缺席划分的误输出仍持平或偏高（abs 3.4 对 3.0、realreg 1.6 对 0.8、短片段 11.1 对 10.5）
- `ts_scene_pool@magicdata-20261023`：MagicData 多句场景（multi 同款 full 模式，目标说 2–5 句、1–4 个他人各有自己的轨道）：目标人取自 MagicData train（手机录制的朗读，1017 人，实际用到 1013 人），注册取同一人另一句 2.5–8 秒；他人一半 MagicData、一半 AISHELL-2。约 30% 是缺席孪生：同一场景，注册换成另一位 MagicData 说话人，目标的话成为干扰、转写为空，同一对共用 labels.pair。MagicData 测试集 73% 的句子在训练集里出现过，训练集中与测试集同文本的 49191 句已剔除。用来补训练里没有的 MagicData 目标人：ts-asr-benchmark@v12 上只留目标一人说话时，10.21 版本对 MagicData 目标的 TS 字错率 14.5%（同句普通识别 1.7%），AISHELL-1/2/3 目标与普通识别持平
- `ts_scene_pool@magicdata-alt-20261023`：v2-20261016 的 MagicData 版：alternate（轮流不重叠）、burst、short 三种场景，全部在场，目标人取自 MagicData train 1017 人，他人一半 MagicData、一半 AISHELL-2，剔除与测试集同文本的句子。041 在 ts-asr-benchmark@v12 上对 KeSpeech、MagicData 目标把前后紧挨着、不重叠的另一个人也转写进来（交接 15–28%、轮流 18%），而这两个语料库此前只有重叠的 full 场景池，AISHELL-2 目标另有 v2-20261016、hard-20261016、handover-20261021 三个轮流场景池
- `ts_scene_pool@magicdata-alt-twins-20261024`：magicdata-alt-20261023 的同配方带孪生版：MagicData 目标的 alternate/burst/short 场景，30% 为孪生样本（换成另一个 MagicData 人注册，一半是 speaker-neighbors-20261023 的相近声音，目标为空）。起因：轮流说话场景在训练里几乎只有在场（v2-20261016、xsession-alt-20261023、magicdata-alt-20261023 没有缺席样本，hard 池的缺席只有交替 / 插话、没有短句），模型学成“其中总有一个是目标”；换成同池另一个人注册后，044@5000 在 xsession-alt 场景仍转写 43%（短句 65%），10.21 版本在 v2 场景 17%，带孪生的多人重叠池 4–8%；ts-asr-benchmark@v12 上 KeSpeech 注册人缺席误输出 2.6% → 17.8%
- `ts_scene_pool@magicdata-alt-twins-20261024-punchw-20261102`：ts_scene_pool@magicdata-alt-twins-20261024 的 zh，供 TS + 热词训练：每条目标句按片段 ID 换成带书面化标点的写法（中文 punc-written-v1，英文 en-v1 加标点并恢复大小写；去掉标点和空格、转小写后与原目标一致才替换，源语料本身带标点的保留原样），hotwords 为目标所说的热词，metadata.interferer_hotwords 为干扰者所说、目标没说的热词（标签：Qwen3.8-27B + amphiondata 热词提示词，已有的 hw_sft 标签复用）。其余字段、场景与音频同源版本（记录仍引用源版本音频）。zh：60000 条，目标改写 42118，带目标热词 8462，带干扰者热词 46424
- `ts_scene_pool@magicdata-handover-20261023`：handover-20261021 的 MagicData 版：目标与另一人各说一句、先后不重叠，剔除与测试集同文本的句子；一半插话人取目标的相近声音（speaker-neighbors-20261023，ERes2NetV2 最近邻前 10 名之一），约 30% 缺席孪生（同样两句、注册换人，一半取近邻）。041 在 ts-asr-benchmark@v12 上对 KeSpeech、MagicData 目标把前后紧挨着、不重叠的另一个人也转写进来（交接 15–28%、轮流 18%），而这两个语料库此前只有重叠的 full 场景池，AISHELL-2 目标另有 v2-20261016、hard-20261016、handover-20261021 三个轮流场景池
- `ts_scene_pool@magicdata-handover-20261023-punchw-20261102`：ts_scene_pool@magicdata-handover-20261023 的 zh，供 TS + 热词训练：每条目标句按片段 ID 换成带书面化标点的写法（中文 punc-written-v1，英文 en-v1 加标点并恢复大小写；去掉标点和空格、转小写后与原目标一致才替换，源语料本身带标点的保留原样），hotwords 为目标所说的热词，metadata.interferer_hotwords 为干扰者所说、目标没说的热词（标签：Qwen3.8-27B + amphiondata 热词提示词，已有的 hw_sft 标签复用）。其余字段、场景与音频同源版本（记录仍引用源版本音频）。zh：40000 条，目标改写 28017，带目标热词 6041，带干扰者热词 12404
- `ts_scene_pool@magicdata-hard-20261023`：hard-20261016 的 MagicData 版：alternate/burst/short 场景，他人之一是目标的相近声音（speaker-neighbors-20261023，ERes2NetV2 最近邻前 10 名之一），55% 目标缺席（转写为空），剔除与测试集同文本的句子。042 加上 *-alt-20261023（全部在场）后，ts-asr-benchmark@v12 上注册 KeSpeech、MagicData 说话人的缺席样本误输出从 5.2% / 2.4%（041@10000）升到 13.0% / 7.6%（042@5000），多为转写了同语料库的他人；AISHELL-2 目标的轮流场景另有 hard-20261016（55% 缺席、近似声音在场）平衡，这两个语料库没有
- `ts_scene_pool@magicdata-hard-20261023-punchw-20261102`：ts_scene_pool@magicdata-hard-20261023 的 zh，供 TS + 热词训练：每条目标句按片段 ID 换成带书面化标点的写法（中文 punc-written-v1，英文 en-v1 加标点并恢复大小写；去掉标点和空格、转小写后与原目标一致才替换，源语料本身带标点的保留原样），hotwords 为目标所说的热词，metadata.interferer_hotwords 为干扰者所说、目标没说的热词（标签：Qwen3.8-27B + amphiondata 热词提示词，已有的 hw_sft 标签复用）。其余字段、场景与音频同源版本（记录仍引用源版本音频）。zh：40000 条，目标改写 17921，带目标热词 3618，带干扰者热词 31267
- `ts_scene_pool@magicdata-hard-twins-20261026`：magicdata-hard-20261023 的带孪生版：MagicData 目标的 alternate/burst/short 在场场景，他人之一是目标的相近声音（speaker-neighbors-20261023，ERes2NetV2 最近邻前 10 名之一），每个在场场景后跟一条孪生样本（同一场景换成另一个 MagicData 人注册，一半是目标的另一个相近声音，目标为空），缺席 50%；剔除与测试集同文本的句子。起因同 xsession-hard-twins-20261026：原 hard 池的缺席场景不是在场场景的孪生、没有短句，是最后一类没有孪生的场景
- `ts_scene_pool@magicdata-near-20261023`：magicdata-20261023 的相近声音版：同样的 MagicData 多句场景（目标人取自 MagicData train 1017 人，他人一半 MagicData、一半 AISHELL-2，剔除与测试集同文本的句子），约 30% 缺席孪生中一半的注册人取目标的相近声音（speaker-neighbors-20261023，ERes2NetV2 余弦最近邻前 10 名之一，候选限于 MagicData 与 AISHELL-2；labels.twin_enrollment=near），另一半随机。原版的孪生全是随机说话人（余弦中位数 0.12），040 在 ts-asr-benchmark@v12 上对 MagicData 目标碰上 MagicData 插话人时连带转写的比例从 1.2% 升到 16.9%
- `ts_scene_pool@magicdata-near-20261023-punchw-20261102`：ts_scene_pool@magicdata-near-20261023 的 zh，供 TS + 热词训练：每条目标句按片段 ID 换成带书面化标点的写法（中文 punc-written-v1，英文 en-v1 加标点并恢复大小写；去掉标点和空格、转小写后与原目标一致才替换，源语料本身带标点的保留原样），hotwords 为目标所说的热词，metadata.interferer_hotwords 为干扰者所说、目标没说的热词（标签：Qwen3.8-27B + amphiondata 热词提示词，已有的 hw_sft 标签复用）。其余字段、场景与音频同源版本（记录仍引用源版本音频）。zh：80000 条，目标改写 56156，带目标热词 25909，带干扰者热词 68316
- `ts_scene_pool@multi-20261017`：多句目标场景（full）：目标说 2–5 句，与 1–4 个其他说话人各自按自己的间隔并行说话（间隔范围写在记录里）；约 26% 的记录是缺席孪生——同一批语句和时间线，注册人换成场景外的另一个人（一半是目标的近邻声音），目标为空，同一对共用 labels.pair。对应 ts_asr_benchmark 的基础场景（目标几句被别人打断或盖住）
- `ts_scene_pool@multi-20261017-punchw-20261102`：ts_scene_pool@multi-20261017 的 en, zh，供 TS + 热词训练：每条目标句按片段 ID 换成带书面化标点的写法（中文 punc-written-v1，英文 en-v1 加标点并恢复大小写；去掉标点和空格、转小写后与原目标一致才替换，源语料本身带标点的保留原样），hotwords 为目标所说的热词，metadata.interferer_hotwords 为干扰者所说、目标没说的热词（标签：Qwen3.8-27B + amphiondata 热词提示词，已有的 hw_sft 标签复用）。其余字段、场景与音频同源版本（记录仍引用源版本音频）。en：40000 条，目标改写 29613，带目标热词 15546，带干扰者热词 34518；zh：120000 条，目标改写 88789，带目标热词 61499，带干扰者热词 102221
- `ts_scene_pool@multi-20261017-punchw2-20261102`：ts_scene_pool@multi-20261017 的 en，供 TS + 热词训练：每条目标句按片段 ID 换成带书面化标点的写法（中文 punc-written-v1，英文 en-v1 加标点并恢复大小写；去掉标点和空格、转小写后与原目标一致才替换，源语料本身带标点的保留原样），hotwords 为目标所说的热词，metadata.interferer_hotwords 为干扰者所说、目标没说的热词（标签：Qwen3.8-27B + amphiondata 热词提示词，已有的 hw_sft 标签复用；英文按整词匹配，所有格算同一个词，干扰者热词按其所在句的大小写还原写法）。其余字段、场景与音频同源版本（记录仍引用源版本音频）。en：40000 条，目标改写 29613，带目标热词 16028，带干扰者热词 34518
- `ts_scene_pool@multi-20261018`：多句目标场景（full）放大版：与 multi-20261017 同一生成方式，规模翻倍（zh 24 万、en 8 万）；目标说 2–5 句，与 1–4 个其他说话人各自按自己的间隔并行说话；约 26% 的记录是缺席孪生——同一批语句和时间线，注册人换成场景外的另一个人（一半是目标的近邻声音），目标为空，同一对共用 labels.pair。用于降低训练里同一批场景的重复次数
- `ts_scene_pool@ramc-alt-twins-20261028`：magicdata-alt-twins-20261024 的 RAMC 版：交替 / 插话 / 短句场景，约 30% 缺席孪生，孪生注册人一半取相近声音。目标人取自 MagicData-RAMC 清洗版 train（magicdata_ramc@clean-dual-pass-20261027：真实手机电话对话，单声道，双模型转写都与人工标注一致的句子），注册取同一人另一句 2.5–8 秒；他人一半 RAMC、一半 AISHELL-2。RAMC 每段对话给说话人发新编号，同一个人会挂在几个编号下：声纹（ERes2NetV2，每个编号每段录音取 6 句平均）相似度 ≥ 0.60 的不同编号互斥（不在同一场景里分别当目标和他人/孪生注册人，也不互当相近声音），与 dev/test 说话人声纹 ≥ 0.60 的 113 个 train 编号和 17 个 dev/test 编号整体剔除（ramc-voice-identities-20261028）；相近声音取 speaker-neighbors-20261028（候选限于 RAMC 与 AISHELL-2）。用来补训练里没有的真实对话说话人：已有 TS 场景池的目标都是朗读语音（AISHELL-2、KeSpeech、MagicData）
- `ts_scene_pool@ramc-handover-20261028`：magicdata-handover-20261023 的 RAMC 版：交接场景（目标与另一人各说一句、前后不重叠、先后随机），另一人一半取相近声音，约 30% 缺席孪生。目标人取自 MagicData-RAMC 清洗版 train（magicdata_ramc@clean-dual-pass-20261027：真实手机电话对话，单声道，双模型转写都与人工标注一致的句子），注册取同一人另一句 2.5–8 秒；他人一半 RAMC、一半 AISHELL-2。RAMC 每段对话给说话人发新编号，同一个人会挂在几个编号下：声纹（ERes2NetV2，每个编号每段录音取 6 句平均）相似度 ≥ 0.60 的不同编号互斥（不在同一场景里分别当目标和他人/孪生注册人，也不互当相近声音），与 dev/test 说话人声纹 ≥ 0.60 的 113 个 train 编号和 17 个 dev/test 编号整体剔除（ramc-voice-identities-20261028）；相近声音取 speaker-neighbors-20261028（候选限于 RAMC 与 AISHELL-2）。用来补训练里没有的真实对话说话人：已有 TS 场景池的目标都是朗读语音（AISHELL-2、KeSpeech、MagicData）
- `ts_scene_pool@ramc-hard-20261028`：magicdata-hard-20261023 的 RAMC 版：交替 / 插话 / 短句场景，他人之一是目标的相近声音，55% 目标缺席（转写为空）。目标人取自 MagicData-RAMC 清洗版 train（magicdata_ramc@clean-dual-pass-20261027：真实手机电话对话，单声道，双模型转写都与人工标注一致的句子），注册取同一人另一句 2.5–8 秒；他人一半 RAMC、一半 AISHELL-2。RAMC 每段对话给说话人发新编号，同一个人会挂在几个编号下：声纹（ERes2NetV2，每个编号每段录音取 6 句平均）相似度 ≥ 0.60 的不同编号互斥（不在同一场景里分别当目标和他人/孪生注册人，也不互当相近声音），与 dev/test 说话人声纹 ≥ 0.60 的 113 个 train 编号和 17 个 dev/test 编号整体剔除（ramc-voice-identities-20261028）；相近声音取 speaker-neighbors-20261028（候选限于 RAMC 与 AISHELL-2）。用来补训练里没有的真实对话说话人：已有 TS 场景池的目标都是朗读语音（AISHELL-2、KeSpeech、MagicData）
- `ts_scene_pool@ramc-near-20261028`：magicdata-near-20261023 的 RAMC 版：多句场景（目标说 2–5 句、1–4 个他人各有自己的轨道），约 30% 缺席孪生（同一场景换另一个人注册，目标的话成为干扰、转写为空），孪生注册人一半取目标的相近声音。目标人取自 MagicData-RAMC 清洗版 train（magicdata_ramc@clean-dual-pass-20261027：真实手机电话对话，单声道，双模型转写都与人工标注一致的句子），注册取同一人另一句 2.5–8 秒；他人一半 RAMC、一半 AISHELL-2。RAMC 每段对话给说话人发新编号，同一个人会挂在几个编号下：声纹（ERes2NetV2，每个编号每段录音取 6 句平均）相似度 ≥ 0.60 的不同编号互斥（不在同一场景里分别当目标和他人/孪生注册人，也不互当相近声音），与 dev/test 说话人声纹 ≥ 0.60 的 113 个 train 编号和 17 个 dev/test 编号整体剔除（ramc-voice-identities-20261028）；相近声音取 speaker-neighbors-20261028（候选限于 RAMC 与 AISHELL-2）。用来补训练里没有的真实对话说话人：已有 TS 场景池的目标都是朗读语音（AISHELL-2、KeSpeech、MagicData）
- `ts_scene_pool@solo-20261019`：目标单独说一句短话（1–3.5 秒）的场景：没有其他说话人，约 30% 是缺席孪生——同一句话，注册人换成另一个人，转写为空。用来补 aishellmix / librimix 的 train_1spk 里几乎没有的 3 秒以内的短目标在场监督（v7 评测的 solo-mid 在场输出为空 11% 以上）
- `ts_scene_pool@solo-20261020`：短目标单独说话场景的难负例版：与 solo-20261019 同样的生成方式（目标单独说一句 1–3.5 秒的话，没有其他说话人，注册取同一说话人另一句 2.5–8 秒，约 30% 是缺席孪生——同一句话，注册人换成另一个人，转写为空），但孪生的注册人一半取目标的近邻声音（speaker-neighbors-20261016，ERes2NetV2 前 10 名，labels.twin_enrollment=near 并记 hard_cosine），一半随机，与 multi 池一致。用来补 solo-20261019 孪生全是随机注册人、负例太容易分的缺口
- `ts_scene_pool@solo-20261020-punchw-20261102`：ts_scene_pool@solo-20261020 的 en, zh，供 TS + 热词训练：每条目标句按片段 ID 换成带书面化标点的写法（中文 punc-written-v1，英文 en-v1 加标点并恢复大小写；去掉标点和空格、转小写后与原目标一致才替换，源语料本身带标点的保留原样），hotwords 为目标所说的热词，metadata.interferer_hotwords 为干扰者所说、目标没说的热词（标签：Qwen3.8-27B + amphiondata 热词提示词，已有的 hw_sft 标签复用）。其余字段、场景与音频同源版本（记录仍引用源版本音频）。en：20000 条，目标改写 14050，带目标热词 2841，带干扰者热词 1255；zh：60000 条，目标改写 42046，带目标热词 15508，带干扰者热词 6723
- `ts_scene_pool@solo-20261020-punchw2-20261102`：ts_scene_pool@solo-20261020 的 en，供 TS + 热词训练：每条目标句按片段 ID 换成带书面化标点的写法（中文 punc-written-v1，英文 en-v1 加标点并恢复大小写；去掉标点和空格、转小写后与原目标一致才替换，源语料本身带标点的保留原样），hotwords 为目标所说的热词，metadata.interferer_hotwords 为干扰者所说、目标没说的热词（标签：Qwen3.8-27B + amphiondata 热词提示词，已有的 hw_sft 标签复用；英文按整词匹配，所有格算同一个词，干扰者热词按其所在句的大小写还原写法）。其余字段、场景与音频同源版本（记录仍引用源版本音频）。en：20000 条，目标改写 14050，带目标热词 2980，带干扰者热词 1255
- `ts_scene_pool@v2-20261016`：Target-speaker scenes (alternate / burst / short, up to 6 other speakers, several utterances per speaker) named from AISHELL-2, KeSpeech, LibriSpeech and Common Voice by speaker label
- `ts_scene_pool@xsession-20261023`：KeSpeech 跨场次多句场景（multi 同款 full 模式，目标说 2–5 句、1–4 个他人各有自己的轨道）：目标人取自 KeSpeech train 中同时有普通话（phase1）与方言（phase2）录音的 15457 人（实际用到 14406 人），场景里目标的话取自同一场次，注册（2.5–8 秒一句）一半取另一场次（labels.cross_session），一半取同一场次；他人一半 KeSpeech、一半 AISHELL-2。约 30% 是缺席孪生：同一场景，注册换成另一位 KeSpeech 说话人，目标的话成为干扰、转写为空，同一对共用 labels.pair。用来补训练里缺的“同一人、不同场次/口音”正例：其他 zh 场景池的目标几乎全是单场次的 AISHELL-2，ts-asr-benchmark@v12 上注册与目标跨普通话/方言时 10.21 版本漏识 33.9%（同口音 5.7%）
- `ts_scene_pool@xsession-alt-20261023`：v2-20261016 的 KeSpeech 跨场次版：alternate（轮流不重叠）、burst、short 三种场景，全部在场，目标人取自 KeSpeech train 中同时有普通话与方言录音的 15457 人，目标句取自一个场次、注册一半取另一场次（labels.cross_session），他人一半 KeSpeech、一半 AISHELL-2。041 在 ts-asr-benchmark@v12 上对 KeSpeech、MagicData 目标把前后紧挨着、不重叠的另一个人也转写进来（交接 15–28%、轮流 18%），而这两个语料库此前只有重叠的 full 场景池，AISHELL-2 目标另有 v2-20261016、hard-20261016、handover-20261021 三个轮流场景池
- `ts_scene_pool@xsession-alt-twins-20261024`：xsession-alt-20261023 的同配方带孪生版：KeSpeech 目标的 alternate/burst/short 场景，场次规则同 xsession-alt-20261023，30% 为孪生样本（换成另一个 KeSpeech 人注册，一半是 speaker-neighbors-20261023 的相近声音，目标为空）；注册音频不选与目标同一句的话（KeSpeech 两个场次念相同提示句，xsession-alt-20261023 有 1.5% 的在场样本注册音频与目标同句）。起因：轮流说话场景在训练里几乎只有在场（v2-20261016、xsession-alt-20261023、magicdata-alt-20261023 没有缺席样本，hard 池的缺席只有交替 / 插话、没有短句），模型学成“其中总有一个是目标”；换成同池另一个人注册后，044@5000 在 xsession-alt 场景仍转写 43%（短句 65%），10.21 版本在 v2 场景 17%，带孪生的多人重叠池 4–8%；ts-asr-benchmark@v12 上 KeSpeech 注册人缺席误输出 2.6% → 17.8%
- `ts_scene_pool@xsession-alt-twins-20261024-punchw-20261102`：ts_scene_pool@xsession-alt-twins-20261024 的 zh，供 TS + 热词训练：每条目标句按片段 ID 换成带书面化标点的写法（中文 punc-written-v1，英文 en-v1 加标点并恢复大小写；去掉标点和空格、转小写后与原目标一致才替换，源语料本身带标点的保留原样），hotwords 为目标所说的热词，metadata.interferer_hotwords 为干扰者所说、目标没说的热词（标签：Qwen3.8-27B + amphiondata 热词提示词，已有的 hw_sft 标签复用）。其余字段、场景与音频同源版本（记录仍引用源版本音频）。zh：60000 条，目标改写 41982，带目标热词 9713，带干扰者热词 47095
- `ts_scene_pool@xsession-handover-20261023`：handover-20261021 的 KeSpeech 跨场次版：目标与另一人各说一句、先后不重叠，场次规则同 xsession-alt-20261023；一半插话人取目标的相近声音（speaker-neighbors-20261023，ERes2NetV2 最近邻前 10 名之一），约 30% 缺席孪生（同样两句、注册换人，一半取近邻）。041 在 ts-asr-benchmark@v12 上对 KeSpeech、MagicData 目标把前后紧挨着、不重叠的另一个人也转写进来（交接 15–28%、轮流 18%），而这两个语料库此前只有重叠的 full 场景池，AISHELL-2 目标另有 v2-20261016、hard-20261016、handover-20261021 三个轮流场景池
- `ts_scene_pool@xsession-handover-20261023-punchw-20261102`：ts_scene_pool@xsession-handover-20261023 的 zh，供 TS + 热词训练：每条目标句按片段 ID 换成带书面化标点的写法（中文 punc-written-v1，英文 en-v1 加标点并恢复大小写；去掉标点和空格、转小写后与原目标一致才替换，源语料本身带标点的保留原样），hotwords 为目标所说的热词，metadata.interferer_hotwords 为干扰者所说、目标没说的热词（标签：Qwen3.8-27B + amphiondata 热词提示词，已有的 hw_sft 标签复用）。其余字段、场景与音频同源版本（记录仍引用源版本音频）。zh：40000 条，目标改写 28118，带目标热词 6493，带干扰者热词 12876
- `ts_scene_pool@xsession-hard-20261023`：hard-20261016 的 KeSpeech 跨场次版：alternate/burst/short 场景，他人之一是目标的相近声音（speaker-neighbors-20261023，ERes2NetV2 最近邻前 10 名之一），55% 目标缺席（注册目标、场景里只有相近声音和他人，转写为空），在场时场次规则同 xsession-alt-20261023。042 加上 *-alt-20261023（全部在场）后，ts-asr-benchmark@v12 上注册 KeSpeech、MagicData 说话人的缺席样本误输出从 5.2% / 2.4%（041@10000）升到 13.0% / 7.6%（042@5000），多为转写了同语料库的他人；AISHELL-2 目标的轮流场景另有 hard-20261016（55% 缺席、近似声音在场）平衡，这两个语料库没有
- `ts_scene_pool@xsession-hard-20261023-punchw-20261102`：ts_scene_pool@xsession-hard-20261023 的 zh，供 TS + 热词训练：每条目标句按片段 ID 换成带书面化标点的写法（中文 punc-written-v1，英文 en-v1 加标点并恢复大小写；去掉标点和空格、转小写后与原目标一致才替换，源语料本身带标点的保留原样），hotwords 为目标所说的热词，metadata.interferer_hotwords 为干扰者所说、目标没说的热词（标签：Qwen3.8-27B + amphiondata 热词提示词，已有的 hw_sft 标签复用）。其余字段、场景与音频同源版本（记录仍引用源版本音频）。zh：40000 条，目标改写 18013，带目标热词 4143，带干扰者热词 31327
- `ts_scene_pool@xsession-hard-twins-20261026`：xsession-hard-20261023 的带孪生版：KeSpeech 目标的 alternate/burst/short 在场场景，他人之一是目标的相近声音（speaker-neighbors-20261023，ERes2NetV2 最近邻前 10 名之一），每个在场场景后跟一条孪生样本（同一场景换成另一个 KeSpeech 人注册，一半是目标的另一个相近声音，目标为空），缺席 50%；注册音频不选与目标同一句的话。起因：原 hard 池的缺席场景是单独的场景、没有短句，也不是某个在场场景的孪生，是最后一类没有孪生的场景；048 avg3 在带孪生的场景类别上都好于 10.21 版本，难缺席划分的误输出仍持平或偏高
- `ts_scene_pool@xsession-near-20261023`：xsession-20261023 的相近声音版：同样的 KeSpeech 跨场次多句场景（目标人取自 KeSpeech train 中同时有普通话与方言录音的 15457 人，注册一半取另一场次 labels.cross_session，他人一半 KeSpeech、一半 AISHELL-2），约 30% 缺席孪生中一半的注册人取目标的相近声音（speaker-neighbors-20261023，ERes2NetV2 余弦最近邻前 10 名之一，候选限于 KeSpeech 与 AISHELL-2；labels.twin_enrollment=near），另一半随机。原版的孪生全是随机说话人，与目标差得很远（余弦中位数 0.09），040 在 ts-asr-benchmark@v12 上对 KeSpeech、MagicData 目标越来越多地把紧接着说话的另一个人也转写进来
- `ts_scene_pool@xsession-near-20261023-punchw-20261102`：ts_scene_pool@xsession-near-20261023 的 zh，供 TS + 热词训练：每条目标句按片段 ID 换成带书面化标点的写法（中文 punc-written-v1，英文 en-v1 加标点并恢复大小写；去掉标点和空格、转小写后与原目标一致才替换，源语料本身带标点的保留原样），hotwords 为目标所说的热词，metadata.interferer_hotwords 为干扰者所说、目标没说的热词（标签：Qwen3.8-27B + amphiondata 热词提示词，已有的 hw_sft 标签复用）。其余字段、场景与音频同源版本（记录仍引用源版本音频）。zh：80000 条，目标改写 56041，带目标热词 29215，带干扰者热词 70033
- 含派生版本（与源数据可能重叠）

### tts_crosslingual_enroll

TS-ASR 训练用跨语言 TTS 注册音频

语言：en、zh · 任务：目标说话人语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [tts_crosslingual_enroll@v1-20261110](../../catalog/tts_crosslingual_enroll.yaml#L2) | — | 未登记 | 没有 |

- `tts_crosslingual_enroll@v1-20261110`：aishellmix 与 librimix train_1spk 各 1000 个训练目标说话人，以其一段真实注册音频为音色（Qwen3-TTS-12Hz-1.7B-Base，x-vector 模式）， 各合成 2 句另一种语言、2 句本语言，用作 TS-ASR 训练时的注册音频（目标在场与缺席都用，两种语言都有，使"合成"本身不成为线索）。 起因：ts_asr_crosslingual 上注册语言与混合段不同时真人漏识 18–39%。脚本 scripts/ts_benchmark/tts_training_enrollments.py

### vitw

真实场景中英语音（VITW）；含回声、远场等评测

语言：en、zh · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [vitw@2m-20261013](../../catalog/amphionasr_v4.yaml#L3854) | 1,085.4 | 已登记 | 没有 |
| [vitw@2m-20261013-ctxclean-20261110](../../catalog/context_correction_clean_zh.yaml#L1189) | 1,085.4 | 已登记 | 没有 |
| [vitw@icefall-20260908](../../catalog/icefall_runtime.yaml#L2568) | 1,085.4 | 已登记 | 快照 20260914 |
| [vitw@legacy-20260804](../../catalog/icefall_base.yaml#L2179) | 1,085.4 | 已登记 | 快照 20260914 |
| [vitw_far_field@icefall-20260908](../../catalog/icefall_runtime.yaml#L3075) | 77.3 | 已登记：远场子集 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/vitw_far_field/` |
| [vitw_far_field@punc-teacher-v1-20261029](../../catalog/punc_teacher_v1.yaml#L60) | 4.2 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/vitw_far_field/` |
| [vitw_far_field@punc-written-v1-20261029](../../catalog/zh_punc_written_v1.yaml#L532) | 77.3 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/vitw_far_field/` |
| [vitw_real_distortion@eval-20260804](../../catalog/open_audio_eval.yaml#L2838) | 0.3 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/vitw_real_distortion/` |
| [vitw_real_dropout@eval-20260804](../../catalog/open_audio_eval.yaml#L2871) | 0.3 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/vitw_real_dropout/` |
| [vitw_real_echo@eval-20260804](../../catalog/open_audio_eval.yaml#L2904) | 0.3 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/vitw_real_echo/` |
| [vitw_real_far_field@eval-20260804](../../catalog/open_audio_eval.yaml#L2937) | 0.3 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/vitw_real_far_field/` |
| [vitw_real_mixed@eval-20260804](../../catalog/open_audio_eval.yaml#L2970) | 1.0 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/vitw_real_mixed/` |
| [vitw_real_noise@eval-20260804](../../catalog/open_audio_eval.yaml#L3003) | 0.3 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/vitw_real_noise/` |
| [vitw_real_obstructed@eval-20260804](../../catalog/open_audio_eval.yaml#L3036) | 0.3 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/vitw_real_obstructed/` |
| [vitw_real_recording@eval-20260804](../../catalog/open_audio_eval.yaml#L3069) | 0.3 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/vitw_real_recording/` |
| [vitw_syn_distortion@eval-20260804](../../catalog/open_audio_eval.yaml#L3102) | 0.8 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/vitw_syn_distortion/` |
| [vitw_syn_dropout@eval-20260804](../../catalog/open_audio_eval.yaml#L3135) | 0.8 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/vitw_syn_dropout/` |
| [vitw_syn_echo@eval-20260804](../../catalog/open_audio_eval.yaml#L3168) | 0.8 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/vitw_syn_echo/` |
| [vitw_syn_far_field@eval-20260804](../../catalog/open_audio_eval.yaml#L3201) | 0.8 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/vitw_syn_far_field/` |
| [vitw_syn_mixed@eval-20260804](../../catalog/open_audio_eval.yaml#L3234) | 2.3 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/vitw_syn_mixed/` |
| [vitw_syn_noise@eval-20260804](../../catalog/open_audio_eval.yaml#L3267) | 0.8 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/vitw_syn_noise/` |
| [vitw_syn_obstructed@eval-20260804](../../catalog/open_audio_eval.yaml#L3300) | 0.8 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/vitw_syn_obstructed/` |
| [vitw_syn_recording@eval-20260804](../../catalog/open_audio_eval.yaml#L3333) | 0.8 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/vitw_syn_recording/` |

- `vitw@2m-20261013`：Voices-in-the-Wild 2M 配方全量转写。音频仍在 2M 源目录，按原 jsonl 顺序登记；不是 Bench 的 legacy-20260804
- `vitw@2m-20261013-ctxclean-20261110`：在 vitw@2m-20261013 上做的上下文纠偏清洗：说话人讲字怎么写（组词、拆字、偏旁、否定对比）而标注写成同音别字的，按说明改正；拿不准的窗口整窗去掉。判定依据见 context_correction_clean_zh@v1-20261110。VITW 音频加了回声、噪声和丢帧，Qwen3-ASR 在上面识别不准（试跑 7 个音频不符约 6 个是 ASR 听错），不做音频核对；标注来自干净原音。命中 28 段，隔离 5 段均为标注本来就对、判定模型拿不准的情况，没有改正；2026-11-12 捞回 2 段（“木子”），仍去掉 3 段（约 0.003 h）
- `vitw_far_field@icefall-20260908`：标注片段时长，重叠语音或多麦克风可能重复计时
- `vitw_far_field@punc-teacher-v1-20261029`：vitw_far_field@icefall-20260908 的 train 监督片段里的 Qwen3.8-27B 老师给 2500 句加的书面化标点（2296 句去掉标点后与输入一致，ok=true）：custom.punctuation_teacher 记输出 text、ok 和模型看到的无标点输入 input；custom.punctuation_hint.qwen 是提示用的 Qwen3-ASR 转写；其中 59 句是留出的评测句，另带学生 v1 的输出 custom.punctuation_student。这批句子用来微调 Qwen3-4B 学生，抽样见 amphiondata scripts/punctuation/build_teacher_set.py。只含这些句子，text 与父版本相同，不是标点后的文本；录音沿用父版本，不复制音频。中间产物，供复现和比较学生，不直接用于训练。脚本 scripts/punctuation/register_punc_intermediates.py
- `vitw_far_field@punc-written-v1-20261029`：vitw_far_field@icefall-20260908 训练集原标注加书面化标点（GB/T 15834，逗号从紧）：微调后的 Qwen3-4B（Qwen3.8-27B 的 9.6 万条输出蒸馏）以 Qwen3-ASR-1.7B 听音频得到的带标点转写作语气提示，只往原标注里插标点。模型改动了原文的条目，把模型输出的标点按字对齐搬回原标注；每条以 。？！ 结尾；原标注的字、空格（首尾除外）和大小写不变。没有汉字的条目（英文句子、拼读字母）和标注为空的条目原样保留。文件与源 supervisions 条数、顺序相同，只换 text。试点 200 条人工参照上：WenetSpeech markF1 92.4、其他来源 88.9（老师 93.2 / 88.2，原 FireRedPunc 79.8）。约一半条目是英文句子，原样保留（含原有英文标点）；中文条目原有的标点按新规范重加
- 含派生版本（与源数据可能重叠）

### waxal-asr

19 种非洲语言语音（WAXAL）

语言：ach、aka、am、dag、dga、ee、ff、kpo、lg、ln、mas、mg、nyn、om、sid、sn、sog、ti、wal · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [waxal-asr@hf-e91442a8989b](../../catalog/multilingual_multispeaker.yaml#L290) | — | 未登记 | 快照 20260914 |

### wutheringwaves

《鸣潮》多语配音，TTS 用

语言：en、ja、ko、zh · 任务：语音合成

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [wutheringwaves@tts-unified-v0.1](../../catalog/tts_unified.yaml#L896) | 134.8 | 已登记 | `amphion-tts-data-1373259071:WutheringWaves-2.2/`（原始数据） |

- `wutheringwaves@tts-unified-v0.1`：音频编码字节存放在 Lance 表内；原始划分在 metadata_json.original_split，统一输出全部为 train。ASR 用 tts_lance.iter_asr_samples（tts-asr-rules/v1）读取，会排除原始 dev/test 等

### yodas_granary_es_pt

YouTube 西语/葡语人工字幕语音（YODAS）

语言：es、pt · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [yodas_granary_es_pt@es000-clean-v1-20261111](../../catalog/yodas_granary_es_clean.yaml#L2) | 2,442.9 | 已登记 | 没有 |
| [yodas_granary_es_pt@hf-969944574ea3](../../catalog/yodas_granary_es_pt.yaml#L1) | 3,658.5 | 已登记 | 快照 20260914 |

- `yodas_granary_es_pt@es000-clean-v1-20261111`：YODAS-Granary 西语人工字幕分区 es000 的清洗版本：Parquet 里嵌的 16 kHz WAV 解成 FLAC 放在本版本目录（约 157 GB）， 731,196 句 / 2,452.45 h 经 Qwen3-ASR-1.7B + whisper-large-v3 双引擎清洗（consensus-v7）保留 726,015 句 / 2,442.89 h （asr_only 75.91 h、ast 2,366.98 h；≥30 s 的长段 938.37 h）。丢弃 0.39% 时长，不集中在某类时长或某些视频； 试跑、被拒样本和误杀率见 run_dir README。es000 的视频 99% 也在 yodas_es@legacy 里，不要两者叠加
- `yodas_granary_es_pt@hf-969944574ea3`：YODAS-Granary 里西语、葡语的人工字幕分区（es000、pt000），音频已切成句子；asr_only 与 ast 两个划分都带原文转写，ast 另有英文翻译。自动字幕分区（es100–108、pt100–103，约 4 TB）未下载。地区未区分。es000 的视频 99%（23,976/24,208 个）也在 yodas_es 里，是同一批 YouTube 音频、切分和转写不同，西语部分不要与 yodas_es 一起累计；葡语此前没有登记 YODAS
- 含派生版本（与源数据可能重叠）

### zenless_voice

《绝区零》多语配音，TTS 用

语言：en、ja、ko、zh · 任务：语音合成

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [zenless_voice@tts-unified-v0.1](../../catalog/tts_unified.yaml#L963) | 554.4 | 已登记 | `amphion-tts-data-1373259071:zenless-voice/`（原始数据） |

- `zenless_voice@tts-unified-v0.1`：音频编码字节存放在 Lance 表内；原始划分在 metadata_json.original_split，统一输出全部为 train。ASR 用 tts_lance.iter_asr_samples（tts-asr-rules/v1）读取，会排除原始 dev/test 等

## 其他语言数据

### audioset_road_traffic

AudioSet 道路交通噪声

语言：und · 任务：noise

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [audioset_road_traffic@legacy-20260804](../../catalog/audioset_road_traffic.yaml#L1) | — | 未登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/audioset_road_traffic/` |

### banspeech_bn

孟加拉语语音识别数据（BanSpeech）

语言：bn · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [banspeech_bn@legacy](../../catalog/legacy_multilingual.yaml#L245) | 6.5 | 已登记 | 快照 20260914 |

- 有无标点版本

### casablanca

Casablanca 八种阿拉伯语方言

语言：ar · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [casablanca@hf-8951b1b88e28](../../catalog/multilingual_asr_sources.yaml#L1687) | — | 未登记 | 没有 |

- `casablanca@hf-8951b1b88e28`：UBC-NLP Casablanca 的 test 划分（阿尔及利亚、埃及、约旦、毛里塔尼亚、摩洛哥、巴勒斯坦、阿联酋、也门），音频以 wav 字节存在 parquet 内；validation 未下载。仅限非商业用途

### cbtts_bn

孟加拉语语音识别数据（CBTTS）

语言：bn · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [cbtts_bn@legacy](../../catalog/legacy_multilingual.yaml#L279) | 20.1 | 已登记 | 快照 20260914 |

- 有含标点版本

### ciempiess

墨西哥西班牙语广播语音（CIEMPIESS LIGHT）

语言：es · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [ciempiess_balance@hf-e48eac011954](../../catalog/ciempiess_balance.yaml#L1) | 18.3 | 已登记 | 没有 |
| [ciempiess_complementary@hf-3401a78c38d7](../../catalog/ciempiess_complementary.yaml#L1) | 0.9 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/ciempiess_complementary/` |
| [ciempiess_fem@hf-e49f428d174b](../../catalog/ciempiess_fem.yaml#L1) | 13.9 | 已登记 | 没有 |
| [ciempiess_light@hf-3d6afb2b3b8d](../../catalog/ciempiess_light.yaml#L1) | 18.4 | 已登记 | 快照 20260914 |
| [ciempiess_test@hf-c134fff8e335](../../catalog/ciempiess_test.yaml#L1) | 8.1 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/ciempiess_test/` |

- `ciempiess_balance@hf-e48eac011954`：墨西哥中部口音广播对话，男女时长均衡，官方完整版本
- `ciempiess_complementary@hf-3401a78c38d7`：墨西哥中部口音的孤立词朗读，按音素均衡挑词，用来补足少见音素
- `ciempiess_fem@hf-e49f428d174b`：女声广播语音，大部分为墨西哥口音（12.0 h），另有多米尼加、委内瑞拉、阿根廷、萨尔瓦多少量；按 country 字段可区分
- `ciempiess_light@hf-3d6afb2b3b8d`：墨西哥西语 CIEMPIESS LIGHT 官方完整版本
- `ciempiess_test@hf-c134fff8e335`：墨西哥西语独立测试集，只用于评测，不进训练

### cml_tts_fr

法语有声书朗读（CML-TTS）

语言：fr · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [cml_tts_fr@legacy](../../catalog/legacy_multilingual.yaml#L1237) | 316.0 | 已登记 | 快照 20260914 |

- 有含标点版本

### common_voice_ar

众包朗读阿拉伯语（Common Voice）

语言：ar · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [common_voice_ar@hf-8262c16bf297](../../catalog/multilingual_asr_sources.yaml#L336) | 12.7 | 已登记 | 没有 |
| [common_voice_ar@legacy](../../catalog/legacy_multilingual.yaml#L1) | 58.2 | 已登记 | 快照 20260914 |

- `common_voice_ar@hf-8262c16bf297`：Common Voice 17.0 ar 的非官方 HF 镜像（官方 Mozilla 仓库需要授权），只下载了 test，与 common_voice_pt@hf-8262c16bf297 同一修订
- 有含标点版本

### common_voice_bn

众包朗读孟加拉语（Common Voice）

语言：bn · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [common_voice_bn@legacy](../../catalog/legacy_multilingual.yaml#L313) | 67.4 | 已登记 | 快照 20260914 |

- 有含标点版本

### common_voice_de

众包朗读德语（Common Voice）

语言：de · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [common_voice_de@hf-8262c16bf297](../../catalog/multilingual_asr_sources.yaml#L744) | 27.4 | 已登记 | 没有 |
| [common_voice_de@legacy](../../catalog/legacy_multilingual.yaml#L555) | 1,034.8 | 已登记 | 快照 20260914 |

- `common_voice_de@hf-8262c16bf297`：Common Voice 17.0 de 的非官方 HF 镜像（官方 Mozilla 仓库需要授权），只下载了 test，与 common_voice_pt@hf-8262c16bf297 同一修订
- 有含标点版本

### common_voice_es

众包朗读西班牙语（Common Voice）

语言：es · 任务：语音识别、热词增强语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [common_voice_es@americas-v1-20261103](../../catalog/common_voice_es_americas.yaml#L1) | 261.2 | 已登记 | 没有 |
| [common_voice_es@cv27-train-hwconf-v1-20261111](../../catalog/cv27_es_hotwords.yaml#L67) | 674.7 | 已登记 | 没有 |
| [common_voice_es@cv27-train-v1-20261111](../../catalog/cv27_es_hotwords.yaml#L2) | 1,355.5 | 已登记 | 没有 |
| [common_voice_es@es-train-hwconf-v1-20261111](../../catalog/es_train_v1.yaml#L195) | 247.6 | 已登记 | 没有 |
| [common_voice_es@es-train-v1-20261108](../../catalog/es_train_v1.yaml#L2) | 514.0 | 已登记 | 没有 |
| [common_voice_es@hf-8262c16bf297](../../catalog/multilingual_asr_sources.yaml#L472) | 26.9 | 已登记 | 没有 |
| [common_voice_es@legacy](../../catalog/legacy_multilingual.yaml#L951) | 568.5 | 已登记 | 快照 20260914 |
| [common_voice_es@mdc-27.0](../../catalog/common_voice_27.yaml#L2) | 1,355.5 | 已登记 | 没有 |

- `common_voice_es@americas-v1-20261103`：从现有 Common Voice 西语（CV 24.0）里按说话人自填口音选出美洲六个预设口音的录音，不复制音频，音频仍读原版本。没填口音的录音（约占六成）无法判断地区，没有收入
- `common_voice_es@cv27-train-hwconf-v1-20261111`：common_voice_es@cv27-train-v1-20261111 里有热词的行（469,488 条，全部 clean 通过）的热词训练版本：每行一条 asr_hotwords 记录，文本、热词与父版本相同，metadata.confusable_hotwords 为读音相近的真实西语热词，训练时按 hotword_confusable_prob 作为干扰词放进列表（同 police_terms_single_train@hotwords-confusable-v1-20261102）。近音词检索复用评测集 hotword_bench@es-v1-20261111 的西语读音键（拉美读法：seseo、yeísmo、b/v、h 不发音等）与编辑距离，每个热词最多 3 个，读音最近的优先；词库只用 CV es / MLS es 训练集（es-train-v1）与 CV 27.0 增量的热词标注（120,633 个），去掉了评测集三个 split 的全部正确词。剔除两类候选：与本条热词只是同一个词不同写法的（读音键忽略空格、ñ/ny/gn 与 n、y 与 i 不区分后相同，如 Sara/Sarah、Cataluña/Catalunya、España/espana、Monte Verde/Monteverde，当负例会教模型拒绝与录音一致的写法），以及出现在本条文本里的。310,629 条（66.2%）有近音词，平均每条 3.201 个；近音词与评测正确词重叠 0。录音不复制，audio_index 指向 mdc-27.0 源文件。检索结果见 mined/confusables.jsonl.gz，质检与 20 条样例见 qc.yaml
- `common_voice_es@cv27-train-v1-20261111`：common_voice_es@mdc-27.0 清洗通过的 980,450 句 / 1,355.54 h（CV 24.0 之外的增量）加热词的训练版本：custom.hotwords 是 Qwen3.8-27B 按 amphiondata extract_hotword 提示词标的热词（同 es-train-v1-20261108），只留在文本里整词出现的（不分大小写）；469,488 句有热词。 丢掉的 1,748 个词都出现在 CV 原句删掉连字符后粘连的词里（如 Reino UnidoNueva Zelanda）。文本与录音清单沿用 mdc-27.0
- `common_voice_es@es-train-hwconf-v1-20261111`：common_voice_es@es-train-v1-20261108 里有热词的行（165,693 条，全部 clean 通过）的热词训练版本：每行一条 asr_hotwords 记录，文本、热词与父版本相同，metadata.confusable_hotwords 为读音相近的真实西语热词，训练时按 hotword_confusable_prob 作为干扰词放进列表（同 police_terms_single_train@hotwords-confusable-v1-20261102）。近音词检索复用评测集 hotword_bench@es-v1-20261111 的西语读音键（拉美读法：seseo、yeísmo、b/v、h 不发音等）与编辑距离，每个热词最多 3 个，读音最近的优先；词库只用 CV es / MLS es 训练集的热词标注（34,441 个），去掉了评测集三个 split 的全部正确词。剔除两类候选：与本条热词只是同一个词不同写法的（读音键忽略空格、ñ/ny/gn 与 n、y 与 i 不区分后相同，如 Sara/Sarah、Cataluña/Catalunya、España/espana、Monte Verde/Monteverde，当负例会教模型拒绝与录音一致的写法），以及出现在本条文本里的。90,439 条（54.6%）有近音词，平均每条 2.943 个；近音词与评测正确词重叠 0。录音不复制，audio_index 指向 legacy 源文件。检索结果见 mined/confusables.jsonl.gz，质检与 20 条样例见 qc.yaml
- `common_voice_es@es-train-v1-20261108`：Common Voice 西班牙语 train 的训练版本：Qwen3-ASR-1.7B + whisper-large-v3 双引擎清洗（默认规则 consensus-v7），保留 356,706 句 / 513.98 h（源 357,397 句）；文本用原文的词和标点（书面句子），只规整了 10,562 句的标点前后空格、首字母大写和缺失的句末句号；custom.hotwords 是 Qwen3.8-27B 标的热词。只含清洗通过的行，录音清单沿用 legacy。也是西语 TS 场景池的句子来源。试跑、被拒样本和误杀率见 run_dir README
- `common_voice_es@hf-8262c16bf297`：Common Voice 17.0 es 的非官方 HF 镜像（官方 Mozilla 仓库需要授权），只下载了 test，与 common_voice_pt@hf-8262c16bf297 同一修订
- `common_voice_es@mdc-27.0`：Common Voice Scripted Speech 27.0 西语（Mozilla Data Collective cmu5kitx700pemi073feoiqqu）相对 common_voice_es@legacy（CV 24.0）的增量： validated 新增 + other（未投票够的录音），去掉 24.0 已有录音和 27.0、24.0 dev/test 的说话人和句子后 1,046,251 句 / 1,408.59 h， 经 Qwen3-ASR-1.7B + whisper-large-v3 双引擎清洗（consensus-v7）保留 980,450 句 / 1,355.54 h（validated 27.37 h、other 1,328.17 h）。 与 common_voice_es@legacy / es-train-v1-20261108 没有重复录音，可叠加使用。被拒集中在少数批量上传空录音的说话人和 <2 s 录音； 试跑、被拒样本和误杀率见 run_dir README
- 有含标点版本
- 含派生版本（与源数据可能重叠）

### common_voice_fr

众包朗读法语（Common Voice）

语言：fr · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [common_voice_fr@hf-8262c16bf297](../../catalog/multilingual_asr_sources.yaml#L608) | 26.1 | 已登记 | 没有 |
| [common_voice_fr@legacy](../../catalog/legacy_multilingual.yaml#L1307) | 924.1 | 已登记 | 快照 20260914 |

- `common_voice_fr@hf-8262c16bf297`：Common Voice 17.0 fr 的非官方 HF 镜像（官方 Mozilla 仓库需要授权），只下载了 test，与 common_voice_pt@hf-8262c16bf297 同一修订
- 有含标点版本

### common_voice_hi

Common Voice 17 印地语朗读

语言：hi · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [common_voice_hi@hf-8262c16bf297](../../catalog/multilingual_asr_sources.yaml#L1177) | 7.6 | 已登记 | 没有 |

- `common_voice_hi@hf-8262c16bf297`：Common Voice 17.0 hi 的非官方 HF 镜像（官方 Mozilla 仓库需要授权），只下载了 dev/test，与 common_voice_pt@hf-8262c16bf297 同一修订

### common_voice_id

Common Voice 17 印尼语朗读

语言：id · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [common_voice_id@hf-8262c16bf297](../../catalog/multilingual_asr_sources.yaml#L1502) | 8.0 | 已登记 | 没有 |

- `common_voice_id@hf-8262c16bf297`：Common Voice 17.0 id 的非官方 HF 镜像（官方 Mozilla 仓库需要授权），只下载了 dev/test，与 common_voice_pt@hf-8262c16bf297 同一修订

### common_voice_ja

众包朗读日语（Common Voice）

语言：ja · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [common_voice_ja@hf-8262c16bf297](../../catalog/multilingual_asr_sources.yaml#L880) | 8.9 | 已登记 | 没有 |
| [common_voice_ja@legacy](../../catalog/legacy_multilingual.yaml#L1593) | 48.2 | 已登记 | 快照 20260914 |

- `common_voice_ja@hf-8262c16bf297`：Common Voice 17.0 ja 的非官方 HF 镜像（官方 Mozilla 仓库需要授权），只下载了 test，与 common_voice_pt@hf-8262c16bf297 同一修订
- 有含标点版本

### common_voice_ko

众包朗读韩语（Common Voice）

语言：ko · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [common_voice_ko@hf-8262c16bf297](../../catalog/multilingual_asr_sources.yaml#L1016) | 0.5 | 已登记 | 没有 |
| [common_voice_ko@legacy](../../catalog/legacy_multilingual.yaml#L1801) | 2.6 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/common_voice_ko/` |

- `common_voice_ko@hf-8262c16bf297`：Common Voice 17.0 ko 的非官方 HF 镜像（官方 Mozilla 仓库需要授权），只下载了 test，与 common_voice_pt@hf-8262c16bf297 同一修订
- 有含标点版本

### common_voice_pt

Common Voice 17 葡语朗读

语言：pt · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [common_voice_pt@hf-8262c16bf297](../../catalog/common_voice_pt.yaml#L31) | 184.3 | 已登记 | 没有 |
| [common_voice_pt@mdc-27.0](../../catalog/common_voice_27.yaml#L83) | 93.8 | 已登记 | 没有 |

- `common_voice_pt@hf-8262c16bf297`：Common Voice 17.0 葡语的非官方 HF 镜像（官方 Mozilla 仓库需要授权）。口音字段大多为空，填写的几乎都是巴西口音。镜像另含 validated / other / invalidated（172.6 / 29.0 / 9.4 h），未登记为划分
- `common_voice_pt@mdc-27.0`：Common Voice Scripted Speech 27.0 葡语（Mozilla Data Collective cmu5wui2w00e8nq07idithpm6）训练版本：validated + other（未投票够的录音）， 去掉 27.0 与 CV 17.0 dev/test 的说话人和句子后 82,417 句 / 94.34 h，经 Qwen3-ASR-1.7B + whisper-large-v3 双引擎清洗（consensus-v7）保留 81,960 句 / 93.82 h（validated 78.10 h、other 15.72 h）。包含 CV 17.0 镜像的全部 train 内容，可替代它用于训练。 试跑、被拒样本和误杀率见 run_dir README

### common_voice_ru

众包朗读俄语（Common Voice）

语言：ru · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [common_voice_ru@hf-8262c16bf297](../../catalog/multilingual_asr_sources.yaml#L1341) | 15.9 | 已登记 | 没有 |
| [common_voice_ru@legacy](../../catalog/legacy_multilingual.yaml#L2061) | 69.9 | 已登记 | 快照 20260914 |

- `common_voice_ru@hf-8262c16bf297`：Common Voice 17.0 ru 的非官方 HF 镜像（官方 Mozilla 仓库需要授权），只下载了 test，与 common_voice_pt@hf-8262c16bf297 同一修订
- 有含标点版本

### coraa

巴西葡语多来源语音（CORAA v1.1）

语言：pt · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [coraa@hf-719c91226a79](../../catalog/coraa.yaml#L1) | 290.5 | 已登记 | 没有 |

- `coraa@hf-719c91226a79`：CORAA v1.1：NURC-Recife、ALIP、SP2010、C-ORAL-BRASIL、TEDx 葡语五个来源的人工校对语音，绝大多数为巴西葡语，少量葡萄牙葡语（metadata 的 variety=pt_pt）。train 是 5 个分卷 rar，需整体解压。CC BY-NC-ND，仅限非商用

### coraa_mupe

巴西葡语生活访谈（CORAA MUPE）

语言：pt · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [coraa_mupe@hf-437966f103b3](../../catalog/coraa_mupe.yaml#L1) | 365.2 | 已登记 | 快照 20260914 |

- `coraa_mupe@hf-437966f103b3`：巴西葡语人生经历访谈（Museu da Pessoa），官方 train/validation/test 三个划分完整下载

### coraa_nurc_sp

圣保罗口音葡语自发语音（NURC-SP）

语言：pt · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [coraa_nurc_sp@hf-c02be121ec19](../../catalog/coraa_nurc_sp.yaml#L1) | 239.3 | 已登记 | 没有 |

- `coraa_nurc_sp@hf-c02be121ec19`：CORAA NURC-SP：圣保罗城市口音的巴西葡语自发语音（对话、访谈、讲座），人工校对转写。只下了 filtered 这套 Parquet（已去掉空转写）和全部 CSV 元数据；original 这套 Parquet（同样的句子外加空转写行）和旧版 WAV tar.gz（与 Parquet 同一批音频）内容重复，到 HF 的链路只有约 2 MB/s，没有下载。speaker_id、num_speakers 由 WhisperX 自动生成，不一定准。test 就是 tarsila_asr 里的 NURC-SP 部分（10.23 h），不要一起累计；与 nurc_sp_corpus_minimo 的 21 段录音按录音编号核对没有重合。CC BY-NC-ND，仅限非商用

### demand

16 麦阵列录制的多环境噪声（DEMAND）

语言：und · 任务：noise

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [demand@hf-voice-biomarkers-20261023](../../catalog/demand.yaml#L1) | 46.7 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/demand/` |
| [demand@zenodo-1227121-16k-20261023](../../catalog/demand.yaml#L62) | 22.7 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/demand/` |
| [demand@zenodo-1227121-48k-20261023](../../catalog/demand.yaml#L296) | 24.0 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/demand/` |

- `demand@hf-voice-biomarkers-20261023`：DEMAND 多通道环境噪声：16 麦阵列在 18 种真实环境录的 5 分钟噪声（厨房、客厅、洗衣房、田野、公园、河边、走廊、会议室、办公室、食堂、餐馆、车站、广场、街道、咖啡馆、公交、轿车、地铁），每个通道一个单声道 WAV。这份 parquet 有 16 kHz（17 个环境，没有咖啡馆 SCAFE）和 48 kHz（18 个环境）两种采样率，共 560 个单通道文件、46.7 小时。可当加噪素材用，16 个通道彼此高度相关，混入时按录音取一个通道即可。这份镜像丢了环境名，要按环境挑噪声用 `demand@zenodo-1227121-16k-20261023`
- `demand@zenodo-1227121-16k-20261023`：DEMAND 环境噪声 16 kHz 原版，带环境名：16 麦阵列在 17 种真实环境各录 5 分钟（D 家庭：厨房、客厅、洗衣房；N 户外：运动场、公园、小河边；O 办公：走廊、会议室、办公室；P 公共场所：食堂、餐馆、地铁站；S 街道：广场、路口；T 交通：公交、轿车、地铁），每个通道一个单声道 WAV，共 272 个文件、22.7 小时。咖啡馆 SCAFE 官方只有 48 kHz，见 48 kHz 原版。按环境挑噪声用这一版；16 个通道彼此高度相关，混入时按环境取一个通道即可
- `demand@zenodo-1227121-48k-20261023`：DEMAND 环境噪声 48 kHz 原版，带环境名：16 麦阵列在 18 种真实环境各录 5 分钟（D 家庭：厨房、客厅、洗衣房；N 户外：运动场、公园、小河边；O 办公：走廊、会议室、办公室；P 公共场所：食堂、餐馆、地铁站；S 街道：广场、咖啡馆露台、路口；T 交通：公交、轿车、地铁），每个通道一个单声道 WAV，共 288 个文件、24 小时。比 16 kHz 原版多一个咖啡馆 SCAFE；要 16 kHz 时用 `demand@zenodo-1227121-16k-20261023` 或自行降采样。16 个通道彼此高度相关，混入时按环境取一个通道即可

### dns5_noise_rir

DNS Challenge 5 官方噪声与冲激响应包

语言：und · 任务：rir、speech_enhancement

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [dns5_noise_rir@official-noise-rir-20260924](../../catalog/dns5_noise_rir.yaml#L1) | — | 未登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/dns5_noise_rir/` |

- `dns5_noise_rir@official-noise-rir-20260924`：官方脚本列出的全部 7 个 AudioSet 噪声包、2 个 Freesound 噪声包及 1 个脉冲响应包；不包含干净语音

### dns5_noise_train

训练用 DNS5 噪声与模拟房间响应

语言：und · 任务：noise、rir

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [dns5_noise_train@v1-20261016](../../catalog/dns5_noise_train.yaml#L1) | 252.6 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/dns5_noise_train/` |

- `dns5_noise_train@v1-20261016`：训练用 DNS5 噪声与模拟房间响应：AudioSet 与 Freesound 噪声（16 kHz 单声道 FLAC，≤30 s，RMS 归一到 −30 dBFS），stationary 为电平稳定、适合做噪声底的片段；rir 为 impulse_responses_000 的模拟房间响应。已跳过 ts_asr_benchmark v3 用到的片段与哈希最小的 300 个响应，训练与评测互不重叠。提取脚本 scripts/ts_robust/prepare_training_noise.py

### emilia_ja

Emilia 日语野外语音

语言：ja · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [emilia_ja@legacy](../../catalog/legacy_multilingual.yaml#L1663) | 1,715.5 | 已登记 | 快照 20260914 |

- 有含标点版本

### emilia_ko

Emilia 韩语野外语音

语言：ko · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [emilia_ko@legacy](../../catalog/legacy_multilingual.yaml#L1871) | 217.2 | 已登记 | 快照 20260914 |

- 有含标点版本

### fleurs_ar

多语朗读阿拉伯语部分（FLEURS）

语言：ar · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [fleurs_ar@hf-70bb2e84b976](../../catalog/multilingual_asr_sources.yaml#L273) | 1.3 | 已登记 | 没有 |
| [fleurs_ar@legacy](../../catalog/legacy_multilingual.yaml#L71) | 8.2 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/fleurs_ar/` |

- `fleurs_ar@hf-70bb2e84b976`：Google FLEURS 的 ar_eg 子集（音频归档和 TSV 转写），只下载了 test，与 fleurs_pt 同一修订
- 有含标点版本

### fleurs_bn

多语朗读孟加拉语部分（FLEURS）

语言：bn · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [fleurs_bn@legacy](../../catalog/legacy_multilingual.yaml#L383) | 15.6 | 已登记 | 快照 20260914 |

- 有含标点版本

### fleurs_de

多语朗读德语部分（FLEURS）

语言：de · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [fleurs_de@hf-70bb2e84b976](../../catalog/multilingual_asr_sources.yaml#L681) | 3.2 | 已登记 | 没有 |
| [fleurs_de@legacy](../../catalog/legacy_multilingual.yaml#L625) | 13.4 | 已登记 | 快照 20260914 |

- `fleurs_de@hf-70bb2e84b976`：Google FLEURS 的 de_de 子集（音频归档和 TSV 转写），只下载了 test，与 fleurs_pt 同一修订
- 有含标点版本

### fleurs_es

多语朗读西班牙语部分（FLEURS）

语言：es · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [fleurs_es@hf-70bb2e84b976](../../catalog/multilingual_asr_sources.yaml#L409) | 3.1 | 已登记 | 没有 |
| [fleurs_es@legacy](../../catalog/legacy_multilingual.yaml#L1021) | 13.2 | 已登记 | 快照 20260914 |

- `fleurs_es@hf-70bb2e84b976`：Google FLEURS 的 es_419 子集（音频归档和 TSV 转写），只下载了 test，与 fleurs_pt 同一修订
- 有含标点版本

### fleurs_fr

多语朗读法语部分（FLEURS）

语言：fr · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [fleurs_fr@hf-70bb2e84b976](../../catalog/multilingual_asr_sources.yaml#L545) | 2.0 | 已登记 | 没有 |
| [fleurs_fr@legacy](../../catalog/legacy_multilingual.yaml#L1377) | 13.1 | 已登记 | 快照 20260914 |

- `fleurs_fr@hf-70bb2e84b976`：Google FLEURS 的 fr_fr 子集（音频归档和 TSV 转写），只下载了 test，与 fleurs_pt 同一修订
- 有含标点版本

### fleurs_hi

FLEURS 印地语朗读

语言：hi · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [fleurs_hi@hf-70bb2e84b976](../../catalog/multilingual_asr_sources.yaml#L1089) | 2.1 | 已登记 | 没有 |

- `fleurs_hi@hf-70bb2e84b976`：Google FLEURS 的 hi_in 子集（音频归档和 TSV 转写），只下载了 dev/test，与 fleurs_pt 同一修订

### fleurs_id

FLEURS 印尼语朗读

语言：id · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [fleurs_id@hf-70bb2e84b976](../../catalog/multilingual_asr_sources.yaml#L1414) | 3.5 | 已登记 | 没有 |

- `fleurs_id@hf-70bb2e84b976`：Google FLEURS 的 id_id 子集（音频归档和 TSV 转写），只下载了 dev/test，与 fleurs_pt 同一修订

### fleurs_ja

多语朗读日语部分（FLEURS）

语言：ja · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [fleurs_ja@hf-70bb2e84b976](../../catalog/multilingual_asr_sources.yaml#L817) | 2.4 | 已登记 | 没有 |
| [fleurs_ja@legacy](../../catalog/legacy_multilingual.yaml#L1697) | 10.7 | 已登记 | 快照 20260914 |

- `fleurs_ja@hf-70bb2e84b976`：Google FLEURS 的 ja_jp 子集（音频归档和 TSV 转写），只下载了 test，与 fleurs_pt 同一修订
- 有含标点版本

### fleurs_ko

多语朗读韩语部分（FLEURS）

语言：ko · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [fleurs_ko@hf-70bb2e84b976](../../catalog/multilingual_asr_sources.yaml#L953) | 1.3 | 已登记 | 没有 |
| [fleurs_ko@legacy](../../catalog/legacy_multilingual.yaml#L1905) | 10.1 | 已登记 | 快照 20260914 |

- `fleurs_ko@hf-70bb2e84b976`：Google FLEURS 的 ko_kr 子集（音频归档和 TSV 转写），只下载了 test，与 fleurs_pt 同一修订
- 有含标点版本

### fleurs_pt

FLEURS 巴西葡语朗读

语言：pt · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [fleurs_pt@hf-70bb2e84b976](../../catalog/fleurs_pt.yaml#L1) | 14.7 | 已登记 | 没有 |

- `fleurs_pt@hf-70bb2e84b976`：Google FLEURS 的 pt_br 子集（音频归档和 TSV 转写），其余语种未下载

### fleurs_ru

多语朗读俄语部分（FLEURS）

语言：ru · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [fleurs_ru@hf-70bb2e84b976](../../catalog/multilingual_asr_sources.yaml#L1278) | 2.5 | 已登记 | 没有 |
| [fleurs_ru@legacy](../../catalog/legacy_multilingual.yaml#L2131) | 11.6 | 已登记 | 快照 20260914 |

- `fleurs_ru@hf-70bb2e84b976`：Google FLEURS 的 ru_ru 子集（音频归档和 TSV 转写），只下载了 test，与 fleurs_pt 同一修订
- 有含标点版本

### fsd50k

200 类声音事件（FSD50K）

语言：und · 任务：noise、sound_event

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [fsd50k@zenodo-4060432-20261013](../../catalog/open_noise.yaml#L1) | 108.6 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/noise_open/` |

- `fsd50k@zenodo-4060432-20261013`：FSD50K：200 类 AudioSet 本体声音事件，44.1 kHz 单声道 16 bit，共 51197 条（dev 40966、eval 10231）；可按 ground_truth 的 Crowd、Chatter 等标签筛选背景人声

### galgame

日语视觉小说配音，TTS 用

语言：ja · 任务：语音合成

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [galgame@tts-unified-v0.1](../../catalog/tts_unified.yaml#L368) | 10,173.7 | 已登记 | `amphion-tts-data-1373259071:Galgame-VisualNovel-Reupload/`（原始数据） |

- `galgame@tts-unified-v0.1`：音频编码字节存放在 Lance 表内；原始划分在 metadata_json.original_split，统一输出全部为 train。ASR 用 tts_lance.iter_asr_samples（tts-asr-rules/v1）读取，会排除原始 dev/test 等

### gigaspeech2_id

印尼语网络语音（GigaSpeech 2）；含热词版

语言：id · 任务：语音识别、热词增强语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [gigaspeech2_id@hf-8dc0d0e502b7](../../catalog/multilingual_asr_sources.yaml#L1603) | — | 未登记 | 没有 |
| [gigaspeech2_id@local-20260805](../../catalog/local_lhotse_derived.yaml#L1) | 1,980.1 | 已登记 | 快照 20260914 |
| [gigaspeech2_id_hotwords@hotwords-v1-20260805](../../catalog/local_lhotse_derived.yaml#L41) | 214.9 | 已登记 | 快照 20260914 |

- `gigaspeech2_id@hf-8dc0d0e502b7`：GigaSpeech 2 印尼语 dev/test（YouTube 音频，人工标注，大写无标点）。HF 仓库需同意条款，用团队已获授权的令牌下载；train 见 gigaspeech2_id@local-20260805
- 含派生版本（与源数据可能重叠）

### golos

Golos 俄语语音助手指令评测划分

语言：ru · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [golos@sberdevices-20250324](../../catalog/multilingual_asr_sources.yaml#L2049) | — | 未登记 | 没有 |

- `golos@sberdevices-20250324`：SberDevices Golos 的 test.tar（WAV，16 kHz 单声道），含 crowd 和 farfield 两个测试集。CDN 的 HTTPS 证书已过期，用 HTTP 下载，按 salute-developers/golos 仓库 golos/md5sum.txt 公布的 md5 校验

### google_latam

拉美六国西语朗读（Google 众包）

语言：es · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [google_latam@openslr-20260911](../../catalog/google_latam.yaml#L1) | 38.0 | 已登记 | 快照 20260914 |

- `google_latam@openslr-20260911`：Google 众包录制的拉美西语朗读（阿根廷、智利、哥伦比亚、秘鲁、波多黎各、委内瑞拉），按国家各一个划分，48 kHz 录音棚质量。SLR61 包里另有一小份天气播报（weather_messages），其中 es-es 是西班牙口音，只作源文件保留，不要算进美洲口音

### heroico

墨西哥军校西语朗读与问答（Heroico）

语言：es · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [heroico@openslr-39](../../catalog/heroico.yaml#L1) | 14.9 | 已登记 | 没有 |

- `heroico@openslr-39`：West Point Heroico Spanish Speech（LDC2006S37，OpenSLR 39 转发）。主体是 2001 年在墨西哥军校录的朗读和自由问答，墨西哥口音；另有西点军校的小部分录音，含母语者和美国非母语学员，usma_nonnative 不是母语口音，训练美洲口音时应排除。部分西点录音同时录了喉麦（文件名以 t 开头），已从统计中剔除。22.05 kHz 16-bit；部分西点文件头写的是 20050 Hz，按文件头计时长。转写文本是 Latin-1 编码；heroico_answers 有 1 条音频没有转写

### kathbath

Kathbath 印地语手机朗读评测划分

语言：hi · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [kathbath@ai4bharat-20250409](../../catalog/multilingual_asr_sources.yaml#L1972) | — | 未登记 | 没有 |

- `kathbath@ai4bharat-20250409`：AI4Bharat Kathbath clean 版的 test-known、test-unknown 音频包（m4a，含 12 种印度语言）和 n2w 转写包，只登记印地语两个划分。上游没有发布文件哈希：三个文件按服务器给出的大小下载，再按 16 MiB 分片算出 S3 分片 ETag，与对象存储的 ETag 一致；sha256 为本地计算。转写与音频逐条对齐

### koreaspeech

韩语语音识别数据（KoreaSpeech）

语言：ko · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [koreaspeech@legacy](../../catalog/legacy_multilingual.yaml#L1975) | 3,828.3 | 已登记 | 快照 20260914 |

- 有含标点版本

### librivox_spanish

LibriVox 西语有声书

语言：es · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [librivox_spanish@hf-ef936a31638d](../../catalog/librivox_spanish.yaml#L1) | 73.0 | 已登记 | 没有 |

- `librivox_spanish@hf-ef936a31638d`：LibriVox 西语有声书人工切分转写（LDC2020S01 的 HF 版本），讲者口音未标注

### meeting_room_noise

真实会议室底噪（AliMeeting、AISHELL-4）

语言：und · 任务：noise

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [meeting_room_noise@v2-20261014](../../catalog/meeting_room_noise.yaml#L1) | 2.5 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/meeting_room_noise/` |

- `meeting_room_noise@v2-20261014`：真实会议室底噪：从 AliMeeting 与 AISHELL-4 训练集远场阵列录音里截取无人说话的片段，每场会议取 1 个麦克风拼成 1 条，共 209 条、2.48 小时。先按标注空隙（前后扩 0.5 秒、剔除比该场底噪高 10 dB 的突发声）取候选，再每 4 秒用 Qwen3-ASR 转写，有文字就丢弃，因为部分会议有未标注的说话人。噪声已带录制房间的混响

### mgb2

半岛电视台阿拉伯语广播（MGB-2）

语言：ar · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [mgb2@legacy](../../catalog/legacy_multilingual.yaml#L141) | 1,215.5 | 已登记 | 快照 20260914 |

- 有无标点版本

### mit_ir_survey

MIT 日常环境实测冲激响应（270 条）

语言：und · 任务：rir

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [mit_ir_survey@flac16k-20261026](../../catalog/mit_ir_survey.yaml#L54) | 0.0 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/mit_ir_survey/` |
| [mit_ir_survey@modelscope-benjamin-paine-20261025](../../catalog/mit_ir_survey.yaml#L1) | 0.0 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/mit_ir_survey/` |

- `mit_ir_survey@flac16k-20261026`：MIT 真实环境冲激响应的 16 kHz 训练版：270 条 RIR 从 32 kHz 按 2:1 多相滤波降采样到 16 kHz，存成 24 位单声道 FLAC，带 lhotse 录音清单，可直接放进训练的 rir_sources。文件按调查编号命名（mit-ir-NNN），场所类别、说明与原文件名在 places 元数据文件里
- `mit_ir_survey@modelscope-benjamin-paine-20261025`：MIT 真实环境冲激响应（RIR）：志愿者两周日常生活里到过的地方（办公室、教室、餐厅、商场、地铁站、浴室、车里、户外等 68 类）实测的 RIR，声源和麦克风相距 1.5 米。共 270 条，32 kHz 单声道。可给干净语音加真实混响，补充模拟 RIR 和 `real_rir_slr28`

### mls_de

德语有声书朗读（MLS）

语言：de · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [mls_de@legacy](../../catalog/legacy_multilingual.yaml#L695) | 1,995.1 | 已登记 | 快照 20260914 |

- 有无标点版本

### mls_es

西班牙语有声书朗读（MLS）

语言：es · 任务：语音识别、热词增强语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [mls_es@es-train-hwconf-v1-20261111](../../catalog/es_train_v1.yaml#L326) | 467.8 | 已登记 | 没有 |
| [mls_es@es-train-v1-20261108](../../catalog/es_train_v1.yaml#L78) | 866.1 | 已登记 | 没有 |
| [mls_es@legacy](../../catalog/legacy_multilingual.yaml#L1091) | 937.7 | 已登记 | 快照 20260914 |

- `mls_es@es-train-hwconf-v1-20261111`：mls_es@es-train-v1-20261108 里有热词的行（110,501 条，全部 clean 通过）的热词训练版本：每行一条 asr_hotwords 记录，文本、热词与父版本相同，metadata.confusable_hotwords 为读音相近的真实西语热词，训练时按 hotword_confusable_prob 作为干扰词放进列表（同 police_terms_single_train@hotwords-confusable-v1-20261102）。近音词检索复用评测集 hotword_bench@es-v1-20261111 的西语读音键（拉美读法：seseo、yeísmo、b/v、h 不发音等）与编辑距离，每个热词最多 3 个，读音最近的优先；词库只用 CV es / MLS es 训练集的热词标注（34,441 个），去掉了评测集三个 split 的全部正确词。剔除两类候选：与本条热词只是同一个词不同写法的（读音键忽略空格、ñ/ny/gn 与 n、y 与 i 不区分后相同，如 Sara/Sarah、Cataluña/Catalunya、España/espana、Monte Verde/Monteverde，当负例会教模型拒绝与录音一致的写法），以及出现在本条文本里的。91,888 条（83.2%）有近音词，平均每条 3.657 个；近音词与评测正确词重叠 0。录音不复制，audio_index 指向 legacy 源文件。检索结果见 mined/confusables.jsonl.gz，质检与 20 条样例见 qc.yaml
- `mls_es@es-train-v1-20261108`：MLS 西班牙语 train（有声书）的训练版本：双引擎清洗（consensus-v7），另丢弃两个引擎彼此一致却都与原标注不符的行（label_mismatch_consensus）和含 Google Books 页脚的行（label_footer），保留 208,356 句 / 866.15 h（源 220,701 句）。原标注全小写无标点，文本换成 Qwen3.8-27B 按 es-v1 规范加的书面化标点和大小写（只插标点、改大小写、补重音；改了词的退回原标注加句号，约 15%）；custom.hotwords 是热词。只含清洗通过的行，录音清单沿用 legacy。规则、抽样核对和误杀率见 run_dir README
- 有无标点版本
- 含派生版本（与源数据可能重叠）

### mls_fr

法语有声书朗读（MLS）

语言：fr · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [mls_fr@legacy](../../catalog/legacy_multilingual.yaml#L1447) | 1,096.7 | 已登记 | 快照 20260914 |

- 有无标点版本

### mls_pt

MLS 葡语有声书朗读

语言：pt · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [mls_pt@openslr-94](../../catalog/mls_pt.yaml#L1) | 168.3 | 已登记 | 快照 20260914 |

- `mls_pt@openslr-94`：Multilingual LibriSpeech 葡语完整 FLAC 归档（含 train/dev/test），LibriVox 有声书；未按巴西/葡萄牙口音区分。OpenSLR 镜像没有这个文件，从官方地址直连下载

### musan

噪声与音乐素材（MUSAN）

语言：und · 任务：noise

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [musan@legacy-20260804](../../catalog/musan.yaml#L1) | — | 未登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/musan/` |

### nurc_sp

圣保罗葡语访谈精选（NURC-SP 最小集）

语言：pt · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [nurc_sp_corpus_minimo@hf-551dea2d5a42](../../catalog/nurc_sp_corpus_minimo.yaml#L1) | 13.0 | 已登记 | 没有 |

- `nurc_sp_corpus_minimo@hf-551dea2d5a42`：NURC-SP 1970–90 年代圣保罗口语录音中精选的 21 段，人工转写切段。train 与 validation 来自同一批录音和说话人，不是独立测试集；与 coraa_nurc_sp 同出 NURC-SP，但按录音编号核对没有共同录音

### open_large_bn

孟加拉语大规模语音识别数据

语言：bn · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [open_large_bn@legacy](../../catalog/legacy_multilingual.yaml#L453) | 5,045.8 | 已登记 | 快照 20260914 |

- 有含标点版本

### real_rir_slr28

真实房间冲激响应（OpenSLR 28）

语言：und · 任务：音频增强、rir

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [real_rir_slr28@legacy-20260804](../../catalog/real_rir_slr28.yaml#L1) | — | 未登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/real_rir_slr28/` |
| [real_rir_slr28@prepared-20260908](../../catalog/icefall_runtime.yaml#L4474) | 0.1 | 已登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/real_rir_slr28/` |

- `real_rir_slr28@prepared-20260908`：Real room impulse responses only; not speech/transcription training examples

### rulibrispeech_ru

俄语有声书朗读（Russian LibriSpeech）

语言：ru · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [rulibrispeech_ru@legacy](../../catalog/legacy_multilingual.yaml#L2201) | 98.2 | 已登记 | 快照 20260914 |

- 有含标点版本

### sim_rir_slr26

模拟房间冲激响应（OpenSLR 26）

语言：und · 任务：rir

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [sim_rir_slr26@legacy-20260804](../../catalog/sim_rir_slr26.yaml#L1) | — | 未登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/sim_rir_slr26/` |

### sim_rir_slr28

模拟房间冲激响应（OpenSLR 28）

语言：und · 任务：rir

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [sim_rir_slr28@legacy-20260804](../../catalog/sim_rir_slr28.yaml#L1) | — | 未登记 | 快照 20260914、`amphion-audio-backup-1373259071:audio-data-contract/datasets/sim_rir_slr28/` |

### slr37_bn

孟加拉语高质量 TTS 朗读（OpenSLR 37）

语言：bn · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [slr37_bn@legacy](../../catalog/legacy_multilingual.yaml#L487) | 5.0 | 已登记 | 快照 20260914 |

- 有无标点版本

### tarsila_asr

巴西葡语 ASR 合并测试集（TARSILA）

语言：pt · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [tarsila_asr@hf-2785788cf674](../../catalog/tarsila_asr.yaml#L1) | 72.5 | 已登记 | 没有 |

- `tarsila_asr@hf-2785788cf674`：把多个巴西葡语语料的测试集合在一起的评测集，只用于评测。各来源（MUPE、CV17、MLS、CORAA v1.1、mTEDx、NURC-SP）的测试集与本次登记的 coraa_mupe、common_voice_pt、mls_pt、coraa、mtedx 等的 test 重复，不要和它们一起累计。上游未声明许可

### tedx_spanish

TEDx 西语演讲（仅限非商用）

语言：es · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [tedx_spanish@hf-469308f10c91](../../catalog/tedx_spanish.yaml#L1) | 24.5 | 已登记 | 没有 |

- `tedx_spanish@hf-469308f10c91`：TEDx 西语演讲（OpenSLR 67 的 HF 版本），讲者口音未标注。许可为 CC BY-NC-ND，仅限非商用

### tele_con_ciencia

墨西哥西语科普电视节目

语言：es · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [tele_con_ciencia@hf-d870d927f530](../../catalog/tele_con_ciencia.yaml#L1) | 28.3 | 已登记 | 没有 |

- `tele_con_ciencia@hf-d870d927f530`：墨西哥科普电视节目 TELEconCIENCIA 的语音，墨西哥口音

### voices_noise

VOiCES 真实房间噪声与背景人声

语言：und · 任务：noise

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [voices_noise@hf-prummn-20261023](../../catalog/voices.yaml#L69) | 128.3 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/voices/` |

- `voices_noise@hf-prummn-20261023`：VOiCES 真实房间噪声：4 个房间里只放干扰声、没有目标说话人时的录音，切成 15 秒一段，16 kHz 单声道。分四组：babble（多人说话背景，全部麦克风，58.7 小时）、none（不放干扰的房间底噪，远处麦克风，3.7 小时）、distractors_close（babble、音乐、电视、无干扰四种，近处麦克风，36.7 小时）、distractors_far（同四种，远处麦克风，29.3 小时）。都带真实房间混响，加噪时不要再叠混响。babble 和电视片段里含人声，做“无人说话”负样本前要先筛

### voxconverse

YouTube 视频说话人日志评测（VoxConverse）

语言：und · 任务：说话人分段与归属

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [voxconverse@diarization-benchmark-v1-20261021](../../catalog/diarization_benchmark.yaml#L343) | 43.5 | 已登记 | 没有 |

- `voxconverse@diarization-benchmark-v1-20261021`：Frozen local evaluation slice; audio and RTTM bytes copied unchanged. Not a claim of official release equivalence or training disjointness.

### voxforge_spanish

VoxForge 西语朗读（多为西班牙）

语言：es · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [voxforge_spanish@hf-1ce6b6f9701d](../../catalog/voxforge_spanish.yaml#L1) | 49.7 | 已登记 | 没有 |

- `voxforge_spanish@hf-1ce6b6f9701d`：VoxForge 西语朗读。约 37.0 h 为西班牙口音，阿根廷、拉美、墨西哥、智利共约 11.6 h；可按 country 字段筛选美洲部分。许可为 GPL-3.0

### voxpopuli_de

VoxPopuli 德语欧洲议会发言

语言：de · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [voxpopuli_de@hf-42f01879c780](../../catalog/multilingual_asr_sources.yaml#L1917) | — | 未登记 | 没有 |

- `voxpopuli_de@hf-42f01879c780`：VoxPopuli 人工转写 ASR 数据的 de test（HF parquet 转换版，音频以 wav 字节存在 parquet 内）；train/validation 未下载

### voxpopuli_fr

VoxPopuli 法语欧洲议会发言

语言：fr · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [voxpopuli_fr@hf-42f01879c780](../../catalog/multilingual_asr_sources.yaml#L1862) | — | 未登记 | 没有 |

- `voxpopuli_fr@hf-42f01879c780`：VoxPopuli 人工转写 ASR 数据的 fr test（HF parquet 转换版，音频以 wav 字节存在 parquet 内）；train/validation 未下载

### wham

WHAM! 噪声训练划分

语言：und · 任务：noise

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [wham@tr-20261014](../../catalog/amphionasr_v4.yaml#L3691) | — | 未登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/wham/` |

- `wham@tr-20261014`：WHAM training noise. Paths point at noise_open/wham_noise/extracted/wham_noise/tr.

### wham_noise

湾区餐厅、咖啡馆等真实环境噪声（WHAM!）

语言：und · 任务：noise

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [wham_noise@official-20261013](../../catalog/open_noise.yaml#L177) | 81.7 | 已登记 | `amphion-audio-backup-1373259071:audio-data-contract/datasets/noise_open/` |

- `wham_noise@official-20261013`：WHAM! 噪声：旧金山湾区餐厅、咖啡馆、酒吧和公园的真实环境噪声，双声道 16 kHz float32，共 28000 条（tr 20000、cv 5000、tt 3000）；已切掉听得清的人声，保留含糊的背景人声

### wikipedia_spanish

西语维基百科条目朗读

语言：es · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [wikipedia_spanish@hf-0afbf012ed67](../../catalog/wikipedia_spanish.yaml#L1) | 25.6 | 已登记 | 没有 |

- `wikipedia_spanish@hf-0afbf012ed67`：西语维基百科有声条目（Wikipedia Grabada）朗读，LDC2021S07 的 HF 版本，讲者口音未标注

### yodas_ar

YouTube 多语语音阿拉伯语部分（YODAS）

语言：ar · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [yodas_ar@legacy](../../catalog/legacy_multilingual.yaml#L211) | 289.7 | 已登记 | 快照 20260914 |

- 有含标点版本

### yodas_bn

YouTube 多语语音孟加拉语部分（YODAS）

语言：bn · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [yodas_bn@legacy](../../catalog/legacy_multilingual.yaml#L521) | 27.1 | 已登记 | 快照 20260914 |

- 有含标点版本

### yodas_de

YouTube 多语语音德语部分（YODAS）

语言：de · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [yodas_de@legacy](../../catalog/legacy_multilingual.yaml#L807) | 3,062.9 | 已登记 | 快照 20260914 |

- 有含标点版本

### yodas_es

YouTube 多语语音西班牙语部分（YODAS）

语言：es · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [yodas_es@legacy](../../catalog/legacy_multilingual.yaml#L1203) | 3,737.8 | 已登记 | 快照 20260914 |

- 有含标点版本

### yodas_fr

YouTube 多语语音法语部分（YODAS）

语言：fr · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [yodas_fr@legacy](../../catalog/legacy_multilingual.yaml#L1559) | 2,423.7 | 已登记 | 快照 20260914 |

- 有含标点版本

### yodas_ja

YouTube 多语语音日语部分（YODAS）

语言：ja · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [yodas_ja@legacy](../../catalog/legacy_multilingual.yaml#L1767) | 1,094.2 | 已登记 | 快照 20260914 |

- 有含标点版本

### yodas_ko

YouTube 多语语音韩语部分（YODAS）

语言：ko · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [yodas_ko@legacy](../../catalog/legacy_multilingual.yaml#L2027) | 2,774.3 | 已登记 | 快照 20260914 |

- 有含标点版本

### yodas_ru

YouTube 多语语音俄语部分（YODAS）

语言：ru · 任务：语音识别

| 版本 | 时长（小时） | 口径 | COS |
|---|---:|---|---|
| [yodas_ru@legacy](../../catalog/legacy_multilingual.yaml#L2271) | 5,596.0 | 已登记 | 快照 20260914 |

- 有含标点版本

## 已记录的质量证据

文件校验通过，不等于内容正确。以下仅列有明确记录的版本，缺少记录不代表质量差。

| 数据版本 | 当前结论 | 证据 | 注意事项 |
|---|---|---|---|
| [aidatatang@clean-dual-qwen-moss-v1-20261008](../../catalog/zh_source_clean.yaml#L329) | 有自动筛选记录 | 自动筛选通过 236,834 条、拒绝 431 条，通过率 99.82% | 未登记人工抽检；筛选通过不等于转写完全正确 |
| [aishell2@clean-dual-qwen-moss-v1-20261009](../../catalog/zh_source_clean_20261009.yaml#L2) | 有自动筛选记录 | 自动筛选通过 1,006,205 条、拒绝 3,018 条，通过率 99.70% | 未登记人工抽检；筛选通过不等于转写完全正确 |
| [aishell3@clean-dual-qwen-moss-v1-20261008](../../catalog/zh_source_clean.yaml#L167) | 有自动筛选记录 | 自动筛选通过 63,219 条、拒绝 43 条，通过率 99.93% | 未登记人工抽检；筛选通过不等于转写完全正确 |
| [alimeeting@openslr-119-far-local-20260903](../../catalog/alimeeting_far_raw.yaml#L1) | 有已知标注问题 | 训练集 8 条标注越过音频边界；开发集 0 条；测试集 0 条 | 最大越界 269.375 秒，使用前应处理异常标注 |
| [common_voice_zh@clean-dual-qwen-moss-v1-20261009](../../catalog/zh_source_clean_20261009.yaml#L338) | 有自动筛选记录 | 自动筛选通过 28,448 条、拒绝 1,112 条，通过率 96.24% | 未登记人工抽检；筛选通过不等于转写完全正确 |
| [commonvoice_en_clean@clean-v1-20260805](../../catalog/local_lhotse_derived.yaml#L311) | 有自动筛选记录 | 自动筛选通过 1,142,149 条、拒绝 1,127 条，通过率 99.90% | 未登记人工抽检；筛选通过不等于转写完全正确 |
| [cs_dialogue@clean-dual-qwen-moss-v1-20261009](../../catalog/zh_source_clean_20261009.yaml#L664) | 有自动筛选记录 | 自动筛选通过 13,948 条、拒绝 44 条，通过率 99.69% | 未登记人工抽检；筛选通过不等于转写完全正确 |
| [cs_dialogue_mix@clean-dual-qwen-moss-v1-20261009](../../catalog/zh_source_clean_20261009.yaml#L824) | 有自动筛选记录 | 自动筛选通过 4,941 条、拒绝 12 条，通过率 99.76% | 未登记人工抽检；筛选通过不等于转写完全正确 |
| [kespeech@clean-dual-qwen-moss-v1-20261009](../../catalog/zh_source_clean_20261009.yaml#L165) | 有自动筛选记录 | 自动筛选通过 882,365 条、拒绝 1,656 条，通过率 99.81% | 未登记人工抽检；筛选通过不等于转写完全正确 |
| [magicdata@clean-dual-qwen-moss-v1-20261008](../../catalog/zh_source_clean.yaml#L499) | 有自动筛选记录 | 自动筛选通过 572,637 条、拒绝 841 条，通过率 99.85% | 未登记人工抽检；筛选通过不等于转写完全正确 |
| [magicdata_ramc@clean-dual-qwen-moss-v1-20261008](../../catalog/zh_source_clean.yaml#L663) | 有自动筛选记录 | 自动筛选通过 166,711 条、拒绝 1,753 条，通过率 98.96% | 未登记人工抽检；筛选通过不等于转写完全正确 |
| [primewords@clean-dual-qwen-moss-v1-20261008](../../catalog/zh_source_clean.yaml#L1) | 有自动筛选记录 | 自动筛选通过 50,119 条、拒绝 265 条，通过率 99.47% | 未登记人工抽检；筛选通过不等于转写完全正确 |
| [talcs@clean-dual-qwen-moss-v1-20261009](../../catalog/zh_source_clean_20261009.yaml#L500) | 有自动筛选记录 | 自动筛选通过 347,533 条、拒绝 2,467 条，通过率 99.30% | 未登记人工抽检；筛选通过不等于转写完全正确 |
| [wenetspeech@clean-weak-v1-20260904](../../catalog/wenetspeech_weak.yaml#L49) | 有自动筛选和人工抽检记录 | 自动筛选通过 3,149,292 条、拒绝 73,468 条，通过率 97.72% | 人工抽检 10 条，其中确认 10 条；样本很小，不能代表整集准确率 |

CV EN 的 train/test 清单落地差异见 [CV EN 清洗说明](cv-en-cleaning.md)。

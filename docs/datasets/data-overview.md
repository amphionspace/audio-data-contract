# 数据总览

当前登记 **198 个数据集**；另有 **20 个下载来源声明**和 **1 个训练混合配方**。登记不代表本机文件已齐备。

时长取单个版本的最大值，不跨版本相加；≈ 为参考表或估算值，— 为暂无完整时长。各版本的时长、说明、COS 地址和质量证据见[版本明细](data-versions.md)。

COS 列：

- 快照 20260914：`cos://amphion-audio-backup-1373259071/audio-data-contract/v1/full-catalog-20260914/`
- 快照 20260921：`cos://amphion-audio-backup-1373259071/audio-data-contract/v1/batches/police-v6-acceptance-205-20260921/`
- 快照内的文件按内容去重分批存放，要用 [cos_restore.py](../guides/cos-restore.md) 按版本取回；快照只表示该版本纳入了这次同步，文件是否已上传以 `locate` 结果为准。
- 其他地址是桶内目录，可直接 `ab pull`（备份桶 = `amphion-audio-backup-1373259071`、TTS 桶 = `amphion-tts-data-1373259071`）。标“原始数据”的是登记版本所依据的原始文件，取回后还要按来源说明处理。
- 没有：仓库里没有 COS 记录；“部分版本：”表示只有部分版本有。

## 数据规模与登记覆盖

![数据集时长 Top 20](assets/data-duration-top20.svg)

![时长登记覆盖情况](assets/data-duration-coverage.svg)

Top 20 与下表取值相同；覆盖图按数据集计数，至少一个版本有完整时长即算已登记。

## 英文数据

| 数据集 | 语言 | 任务 | 时长（小时） | 简介 | COS |
|---|---|---|---:|---|---|
| [ami_ihm](data-versions.md#ami_ihm) | en | 语音识别 | 95.5 | AMI 英文会议的近讲耳麦版 | 没有 |
| [audioset_esc_test](data-versions.md#audioset_esc_test) | en | 背景声场景描述 | 6.8 | AudioSet 背景声场景描述评测集 | 快照 20260914 |
| [chime4](data-versions.md#chime4) | en | 语音识别 | 10.1 | 四种噪声环境的英文朗读评测集（CHiME-4） | 没有 |
| [chime6](data-versions.md#chime6) | en | 语音识别、重叠语音检测、带说话人标注的语音识别、说话人分段与归属、目标说话人语音识别 | 174.5 | 家庭聚会英文对话，多通道远场重叠（CHiME-6） | 部分版本：快照 20260914 |
| [common_voice_en](data-versions.md#common_voice_en) | en | 语音识别、热词增强语音识别 | 1,862.7 | Common Voice 英语众包朗读；含清洗、热词、加噪版 | 快照 20260914 |
| [cs_dialogue_en](data-versions.md#cs_dialogue_en) | en | 语音识别 | 26.6 | CS-Dialogue 对话中的纯英文语句 | 快照 20260914 |
| [dipco](data-versions.md#dipco) | en | 语音识别、带说话人标注的语音识别、说话人分段与归属 | 6.5 | 家庭晚宴英文对话，近讲与远场阵列（DiPCo） | 没有 |
| [emilia_en](data-versions.md#emilia_en) | en | 语音识别 | 43,624.0 | Emilia 英语野外语音（已清洗） | 快照 20260914 |
| [emotion1200_en](data-versions.md#emotion1200_en) | en | 说话人情感分类、情感与说话风格描述、语音情感识别 | 5.2 | 英文情感识别与描述评测（Emotion1200） | 快照 20260914 |
| [fleurs_en](data-versions.md#fleurs_en) | en | 语音识别 | 10.3 | 多语朗读英语部分（FLEURS） | 快照 20260914 |
| [gigaspeech](data-versions.md#gigaspeech) | en | 语音识别 | 10,050.7 | 有声书、播客和 YouTube 英语（GigaSpeech） | 快照 20260914 |
| [hifitts](data-versions.md#hifitts) | en | 语音识别、语音合成 | 291.7 | 英文有声书高保真朗读（Hi-Fi TTS） | `TTS 桶:HiFiTTS/`（原始数据） |
| [hifitts2](data-versions.md#hifitts2) | en | 语音识别、语音合成 | 35,932.7 | 英文有声书高保真朗读（Hi-Fi TTS 2） | 没有 |
| [icsi](data-versions.md#icsi) | en | 语音识别、说话人分段与归属 | 71.7 | 伯克利 ICSI 英文工作会议（近讲混合音轨） | 没有 |
| [iemocap_ser](data-versions.md#iemocap_ser) | en | 语音情感识别 | 1.5 | 英文双人表演对话情感识别评测（IEMOCAP） | 快照 20260914 |
| [legco_speech_en](data-versions.md#legco_speech_en) | en | 语音识别 | 249.6 | 香港立法会会议英语 | 快照 20260914 |
| [libri2mix](data-versions.md#libri2mix) | en | 目标说话人语音识别 | 11.2 | LibriMix 两人混合的目标说话人评测 | 快照 20260914 |
| [libri3mix](data-versions.md#libri3mix) | en | 目标说话人语音识别 | 16.3 | LibriMix 三人混合的目标说话人评测 | 快照 20260914 |
| [libricss](data-versions.md#libricss) | en | 语音识别、重叠语音检测、speech_separation | 10.1 | LibriSpeech 外放录制的模拟会议 | 没有 |
| [libriheavy](data-versions.md#libriheavy) | en | 语音识别、语音合成 | 51,044.7 | 英文有声书，带标点和大小写（Libriheavy） | 没有 |
| [librimix](data-versions.md#librimix) | en | 目标说话人语音识别 | 6,921.9 | LibriSpeech 混合的目标说话人数据 | 快照 20260914 |
| [librispeech](data-versions.md#librispeech) | en | 语音识别、热词增强语音识别 | 971.6 | 英文有声书朗读（LibriSpeech）；含热词和加噪版 | 快照 20260914 |
| [libritts_r](data-versions.md#libritts_r) | en | 语音识别、语音合成 | 583.1 | 英文有声书 TTS 语料，音频经修复（LibriTTS-R） | `TTS 桶:LibriTTS-R/`（原始数据） |
| [ljspeech](data-versions.md#ljspeech) | en | 语音识别、语音合成 | 23.9 | 单人英文朗读（LJSpeech） | `TTS 桶:LJSpeech/`（原始数据） |
| [meld_ser](data-versions.md#meld_ser) | en | 语音情感识别 | 2.3 | 美剧《老友记》对话情感识别评测（MELD） | 快照 20260914 |
| [mls](data-versions.md#mls) | en | 语音识别 | 44,691.0 | 英文有声书朗读（MLS 英语） | 快照 20260914 |
| [msp_podcast_ser](data-versions.md#msp_podcast_ser) | en | 语音情感识别 | — | 英文播客情感识别评测（MSP-Podcast） | 快照 20260914 |
| [notsofar](data-versions.md#notsofar) | en | 语音识别、连续语音分离、重叠语音检测、带说话人标注的语音识别、说话人分段与归属 | ≈200.0 | 微软英文远场会议，真实录制与模拟（NOTSOFAR） | 快照 20260914 |
| [singapore_english](data-versions.md#singapore_english) | en | 语音识别 | 3.9 | 新加坡口音英语（Hugging Face 来源） | 快照 20260914 |
| [singaporean](data-versions.md#singaporean) | en | 语音识别 | ≈0.2 | 新加坡口音英语小样本 | 快照 20260914 |
| [tal100_en](data-versions.md#tal100_en) | en | 语音识别 | 4.8 | TAL 英语语音识别数据 | 快照 20260914 |
| [vctk](data-versions.md#vctk) | en | 语音识别、语音合成 | 82.7 | 多口音英语朗读（VCTK） | `TTS 桶:VCTK/`（原始数据） |
| [voicebank_demand](data-versions.md#voicebank_demand) | en | speech_enhancement | 10.0 | 语音增强标准集（VoiceBank-DEMAND） | 没有 |
| [voices](data-versions.md#voices) | en | 语音识别 | 27.9 | 真实房间外放的英文远场评测（VOiCES） | 没有 |

## 中文及粤语数据

| 数据集 | 语言 | 任务 | 时长（小时） | 简介 | COS |
|---|---|---|---:|---|---|
| [3dspeaker](data-versions.md#3dspeaker) | zh | 说话人身份识别、声纹验证 | 1,275.3 | 跨设备、距离和方言的中文声纹数据（3D-Speaker） | 快照 20260914 |
| [OpenSLR 159 AISHELL-5](data-versions.md#openslr-159-aishell-5) | zh | 语音识别、带说话人标注的语音识别 | 445.4 | 车内多人中文对话，远场麦克风（AISHELL-5） | 没有 |
| [aidatatang](data-versions.md#aidatatang) | zh | 语音识别、热词增强语音识别 | 145.5 | 中文手机朗读（aidatatang）；含清洗和热词版 | 部分版本：快照 20260914 |
| [aishell](data-versions.md#aishell) | zh | 语音识别、热词增强语音识别 | 179.0 | 中文朗读（AISHELL-1）；含清洗和热词版 | 快照 20260914 |
| [aishell2](data-versions.md#aishell2) | zh | 语音识别、热词增强语音识别 | ≈1,036.0 | 中文朗读（AISHELL-2）；含清洗和热词版 | 快照 20260914 |
| [aishell3](data-versions.md#aishell3) | zh | 语音识别、热词增强语音识别、语音合成 | 85.6 | 中文多人朗读（AISHELL-3）；含清洗、热词、TTS 版 | 部分版本：快照 20260914、`TTS 桶:AISHELL-3/`（原始数据） |
| [aishell4](data-versions.md#aishell4) | zh | 语音识别、说话人分段与归属、目标说话人语音识别 | 322.3 | 中文多人会议（AISHELL-4）；含轮流说话混合版 | 部分版本：快照 20260914 |
| [aishell4_meeting_sot](data-versions.md#aishell4_meeting_sot) | zh | 带说话人标注的语音识别 | 377.5 | AISHELL-4 会议切窗的多人按人转写数据 | 没有 |
| [aishell5_meeting_sot](data-versions.md#aishell5_meeting_sot) | zh | 带说话人标注的语音识别 | — | AISHELL-5 车内对话切窗的多人按人转写数据 | 没有 |
| [aishellmix](data-versions.md#aishellmix) | zh | 目标说话人语音识别 | 7,489.2 | AISHELL-2 混合的目标说话人训练与测试数据 | 快照 20260914 |
| [alimeeting](data-versions.md#alimeeting) | zh | 语音识别、连续语音分离、重叠语音检测、带说话人标注的语音识别、说话人分段与归属、目标说话人语音识别 | 427.7 | 中文远场会议，多人重叠语音（AliMeeting） | 部分版本：快照 20260914 |
| [alimeeting_near_farsim_meeting_sot](data-versions.md#alimeeting_near_farsim_meeting_sot) | zh | 带说话人标注的语音识别 | 399.5 | AliMeeting 近讲加混响噪声模拟远场的会议窗口 | 没有 |
| [alimeeting_sdm_meeting_sot](data-versions.md#alimeeting_sdm_meeting_sot) | zh | 带说话人标注的语音识别 | 327.3 | AliMeeting 远场会议切窗的多人按人转写数据 | 没有 |
| [biic_podcast_ser](data-versions.md#biic_podcast_ser) | zh | 语音情感识别 | 22.6 | 中文播客情感识别评测（BIIC-Podcast） | 快照 20260914 |
| [business_feedback](data-versions.md#business_feedback) | zh | 目标说话人语音识别 | 0.1 | 业务反馈的目标说话人 bad case，仅评测 | `备份桶:audio-data-contract/datasets/business_feedback/` |
| [childmandarin](data-versions.md#childmandarin) | zh | 语音识别 | 41.0 | 3–5 岁儿童普通话语音（ChildMandarin） | 快照 20260914 |
| [cnceleb1](data-versions.md#cnceleb1) | zh | 说话人身份识别、声纹验证 | 270.1 | 中文跨场景声纹数据（CN-Celeb1） | 快照 20260914 |
| [cnceleb2](data-versions.md#cnceleb2) | zh | 说话人身份识别、声纹验证 | 1,084.3 | 中文跨场景声纹训练数据（CN-Celeb2） | 快照 20260914 |
| [common_voice_zh](data-versions.md#common_voice_zh) | zh | 语音识别、热词增强语音识别 | 76.1 | Common Voice 中文众包朗读；含清洗、热词、加噪版 | 快照 20260914 |
| [common_voice_zh_hk](data-versions.md#common_voice_zh_hk) | yue | 语音识别 | 25.3 | 众包朗读粤语（Common Voice 香港） | 快照 20260914 |
| [context_correction_zh](data-versions.md#context_correction_zh) | zh | 语音识别、目标说话人语音识别 | 17.6 | 中文上下文纠偏评测集，同音词按语境写 | 没有 |
| [csemotions](data-versions.md#csemotions) | zh | 语音合成 | 10.2 | 中文情感语音（CSEMOTIONS），TTS 用 | `TTS 桶:CSEMOTIONS/`（原始数据） |
| [emilia2_zh_dialogue_diarize](data-versions.md#emilia2_zh_dialogue_diarize) | zh | 语音识别、diarization、带说话人标注的语音识别 | 3,167.4 | Emilia2 中文对话的说话人日志伪标签 | 没有 |
| [emilia2_zh_overlap_farsim](data-versions.md#emilia2_zh_overlap_farsim) | zh | 带说话人标注的语音识别 | — | Emilia2 中文对话重排的重叠远场多人数据 | 没有 |
| [emilia_zh](data-versions.md#emilia_zh) | zh | 语音识别 | 40,848.4 | Emilia 中文野外语音（已清洗） | 快照 20260914 |
| [emotion1200_zh](data-versions.md#emotion1200_zh) | zh | 说话人情感分类、情感与说话风格描述、语音情感识别 | 4.9 | 中文情感识别与描述评测（Emotion1200） | 快照 20260914 |
| [fleurs_zh](data-versions.md#fleurs_zh) | zh | 语音识别 | 14.1 | 多语朗读中文部分（FLEURS） | 快照 20260914 |
| [hi_mia](data-versions.md#hi_mia) | zh | 说话人身份识别、声纹验证 | 533.6 | 固定中文唤醒词的远场声纹验证（HI-MIA） | 快照 20260914 |
| [kespeech](data-versions.md#kespeech) | zh | 语音识别、热词增强语音识别 | 1,434.8 | 普通话与 8 种次方言（KeSpeech）；含清洗和热词版 | 部分版本：快照 20260914 |
| [legco_speech](data-versions.md#legco_speech) | yue | 语音识别 | 20,227.2 | 香港立法会会议粤语 | 快照 20260914 |
| [m3ed_ser](data-versions.md#m3ed_ser) | zh | 语音情感识别 | 1.7 | 中文电视剧对话情感识别评测（M3ED） | 快照 20260914 |
| [magicdata](data-versions.md#magicdata) | zh | 语音识别、热词增强语音识别 | 754.7 | 中文手机朗读（MAGICDATA）；含清洗和热词版 | 部分版本：快照 20260914 |
| [magicdata_ramc](data-versions.md#magicdata_ramc) | zh | 语音识别、说话人分段与归属、目标说话人语音识别 | 403.5 | 中文手机通话自然对话（MagicData-RAMC） | 部分版本：快照 20260914 |
| [magicdata_ramc_farsim_meeting_sot](data-versions.md#magicdata_ramc_farsim_meeting_sot) | zh | 带说话人标注的语音识别 | 566.6 | RAMC 对话加混响噪声模拟远场的窗口 | 没有 |
| [magicdata_ramc_meeting_sot](data-versions.md#magicdata_ramc_meeting_sot) | zh | 带说话人标注的语音识别 | — | MagicData-RAMC 对话切窗的按人转写数据 | 没有 |
| [mdcc](data-versions.md#mdcc) | yue | 语音识别 | 73.6 | 香港粤语有声书朗读（MDCC）；含加噪版 | 快照 20260914 |
| [mir1k](data-versions.md#mir1k) | zh | noise | 2.2 | 中文流行歌卡拉 OK 片段，人声伴奏分轨（MIR-1K） | 没有 |
| [police_asr_unified](data-versions.md#police_asr_unified) | zh | 语音识别 | 805.6 | 警务合成语音统合版（V1–V6 合并） | 部分版本：快照 20260914、快照 20260921 |
| [police_scene_bench](data-versions.md#police_scene_bench) | zh | 语音识别、热词增强语音识别、带说话人标注的语音识别、目标说话人语音识别 | 70.7 | 鼎桥验收表各使用场景的模拟评测，仅评测 | 没有 |
| [police_terms_single](data-versions.md#police_terms_single) | zh | 语音识别 | 1.7 | 警务术语单说测试集，仅评测 | 没有 |
| [police_terms_single_train](data-versions.md#police_terms_single_train) | zh | 语音识别 | 11.7 | 警务术语单说训练集 | 没有 |
| [primewords](data-versions.md#primewords) | zh | 语音识别 | 99.0 | 中文手机朗读（Primewords）；含清洗版 | 部分版本：快照 20260914 |
| [realman](data-versions.md#realman) | zh | 语音识别、noise、sound_source_localization、speech_enhancement | 83.7 | 真实录制的中文多通道阵列语音（RealMAN） | 部分版本：快照 20260914 |
| [realman_zh_far_asr](data-versions.md#realman_zh_far_asr) | zh | 语音识别 | 64.0 | RealMAN 远场中文转写训练数据 | 没有 |
| [speechio](data-versions.md#speechio) | zh | 语音识别 | 63.8 | SpeechIO 中文 ASR 排行榜评测集 | 部分版本：快照 20260914 |
| [tal100_zh](data-versions.md#tal100_zh) | zh | 语音识别 | 5.5 | TAL 中文语音识别数据 | 快照 20260914 |
| [thchs30](data-versions.md#thchs30) | zh | 语音识别、热词增强语音识别 | ≈35.0 | 清华中文朗读（THCHS-30）；含热词版 | 快照 20260914 |
| [threed_speaker_zh_far_asr](data-versions.md#threed_speaker_zh_far_asr) | zh | 语音识别 | 75.5 | 3D-Speaker 远场普通话转写训练数据 | 没有 |
| [ts_asr_benchmark](data-versions.md#ts_asr_benchmark) | zh | 目标说话人语音识别 | 46.5 | 合成的中文目标说话人 ASR 评测集 | `备份桶:audio-data-contract/datasets/ts_asr_benchmark/` |
| [ts_asr_dev](data-versions.md#ts_asr_dev) | zh | 目标说话人语音识别 | 10.7 | 合成的中文目标说话人 ASR 开发集 | `备份桶:audio-data-contract/datasets/ts_asr_dev/` |
| [ts_asr_enroll_len](data-versions.md#ts_asr_enroll_len) | zh | 目标说话人语音识别 | 1.5 | 目标说话人评测：注册音频长度 | 没有 |
| [ts_asr_farfield](data-versions.md#ts_asr_farfield) | zh | 目标说话人语音识别 | 5.1 | 目标说话人评测：远场与混响 | `备份桶:audio-data-contract/datasets/ts_asr_farfield/` |
| [ts_asr_handover](data-versions.md#ts_asr_handover) | zh | 目标说话人语音识别 | 3.8 | 目标说话人评测：与他人交替说话 | `备份桶:audio-data-contract/datasets/ts_asr_handover/` |
| [ts_asr_nearfar](data-versions.md#ts_asr_nearfar) | zh | 目标说话人语音识别 | 6.0 | 目标说话人评测：AliMeeting 近场与远场对照 | `备份桶:audio-data-contract/datasets/ts_asr_nearfar/` |
| [ts_asr_nearshort](data-versions.md#ts_asr_nearshort) | zh | 目标说话人语音识别 | 2.5 | 目标说话人评测：他人只说一句约 1 秒短话 | 部分版本：`备份桶:audio-data-contract/datasets/ts_asr_nearshort/` |
| [ts_asr_noise](data-versions.md#ts_asr_noise) | zh | 目标说话人语音识别 | 5.9 | 目标说话人评测：噪声与背景人声 | `备份桶:audio-data-contract/datasets/ts_asr_noise/` |
| [ts_asr_playback](data-versions.md#ts_asr_playback) | zh | 目标说话人语音识别 | 3.4 | 目标说话人评测：外放播放的干扰声 | 没有 |
| [ts_asr_real](data-versions.md#ts_asr_real) | zh | 目标说话人语音识别 | 12.0 | 真实会议对话的目标说话人评测集 | `备份桶:audio-data-contract/datasets/ts_asr_real/` |
| [ts_asr_shortseg](data-versions.md#ts_asr_shortseg) | zh | 目标说话人语音识别 | 0.8 | 目标说话人评测：他人说话的 1–6 秒短片段 | `备份桶:audio-data-contract/datasets/ts_asr_shortseg/` |
| [ts_asr_singing](data-versions.md#ts_asr_singing) | zh | 目标说话人语音识别 | 0.3 | 目标说话人评测：歌声干扰 | `备份桶:audio-data-contract/datasets/ts_asr_singing/` |
| [ts_real_train](data-versions.md#ts_real_train) | zh | 目标说话人语音识别 | 123.6 | 真实会议切出的目标说话人训练窗口 | 没有 |
| [vitw_zh_far_asr](data-versions.md#vitw_zh_far_asr) | zh | 语音识别 | 49.6 | VITW 中文远场转写训练数据 | 没有 |
| [wenetspeech](data-versions.md#wenetspeech) | zh | 语音识别 | 10,025.4 | 中文网络语音万余小时（WenetSpeech）；含清洗版 | 部分版本：快照 20260914、`备份桶:audio-data-contract/datasets/wenetspeech/` |
| [wenetspeech4tts](data-versions.md#wenetspeech4tts) | zh | 语音识别、语音合成 | ≈7,700.0 | WenetSpeech 筛出的中文 TTS 语音 | 快照 20260914、`TTS 桶:WenetSpeech4TTS/`（原始数据） |
| [wenetspeech_chuan](data-versions.md#wenetspeech_chuan) | zh | 语音识别 | 10,259.6 | 川渝方言网络语音（WenetSpeech-Chuan） | 部分版本：快照 20260914 |
| [wenetspeech_diarize](data-versions.md#wenetspeech_diarize) | zh | diarization、带说话人标注的语音识别 | — | WenetSpeech 长音频的说话人日志伪标签 | 没有 |
| [wenetspeech_disfluency](data-versions.md#wenetspeech_disfluency) | zh | 语音识别 | 182.5 | WenetSpeech L 保留口语不流利词的转写 | 快照 20260914、`备份桶:audio-data-contract/datasets/wenetspeech/` |
| [wenetspeech_podcast](data-versions.md#wenetspeech_podcast) | zh | 语音识别 | 3,892.3 | WenetSpeech L 中的播客部分 | 没有 |
| [wenetspeech_wu](data-versions.md#wenetspeech_wu) | zh | 语音识别 | 8,740.7 | 吴语网络语音（WenetSpeech-Wu） | 快照 20260914 |
| [wenetspeech_youtube](data-versions.md#wenetspeech_youtube) | zh | 语音识别 | 6,113.1 | WenetSpeech L 中的 YouTube 部分 | 没有 |
| [wenetspeech_yue](data-versions.md#wenetspeech_yue) | yue | 语音识别 | — | 粤语网络语音（WenetSpeech-Yue）；含清洗版 | 部分版本：快照 20260914 |
| [wenetspeech_yue_all](data-versions.md#wenetspeech_yue_all) | yue | 语音识别 | — | WenetSpeech-Yue 全量，含非 clean 部分 | 快照 20260914 |

## 混合语言及多语数据

| 数据集 | 语言 | 任务 | 时长（小时） | 简介 | COS |
|---|---|---|---:|---|---|
| [BAAI/CS-Dialogue long_wav (ModelScope master)](data-versions.md#baaics-dialogue-long_wav-modelscope-master) | en、zh、zh-en | 语音识别、带说话人标注的语音识别 | 98.3 | 中英语码转换双人对话（CS-Dialogue） | 部分版本：快照 20260914 |
| [ami](data-versions.md#ami) | en、zh | 语音识别、说话人分段与归属、目标说话人语音识别 | 259.3 | 英文会议远场版（AMI SDM）；含轮流说话混合版 | 部分版本：快照 20260914 |
| [asr_babble_bench](data-versions.md#asr_babble_bench) | en、zh | 语音识别 | 10.1 | 普通 ASR 背景人声评测集（中英），仅评测 | `备份桶:audio-data-contract/datasets/asr_babble_bench/` |
| [asr_babble_speech_pool](data-versions.md#asr_babble_speech_pool) | en、zh | 语音识别 | 85.5 | 带房间背景人声的中英 ASR 训练句 | 没有 |
| [babble_noise_synth](data-versions.md#babble_noise_synth) | en、zh | noise | 50.0 | 合成中英背景人声噪声（5–20 人叠加） | 没有 |
| [babble_noise_train](data-versions.md#babble_noise_train) | en、zh | noise | 50.0 | 训练用合成背景人声噪声（中英） | 没有 |
| [cs_dialogue_meeting_sot](data-versions.md#cs_dialogue_meeting_sot) | zh、zh-en | 带说话人标注的语音识别 | — | CS-Dialogue 中英对话切窗的按人转写数据 | 没有 |
| [cs_dialogue_mix](data-versions.md#cs_dialogue_mix) | en、zh | 语音识别 | 31.0 | CS-Dialogue 对话中的中英混说语句 | 快照 20260914 |
| [cumix2017](data-versions.md#cumix2017) | en、yue | 语音识别 | 10.9 | 粤英语码转换语音（CUMIX2017） | 快照 20260914 |
| [emilia](data-versions.md#emilia) | de、en、fr、ja、ko、zh | 语音识别、语音合成 | 101,655.6 | 多语种视频野外语音（Emilia）；含精修文本版 | 部分版本：`TTS 桶:Emilia/`（原始数据） |
| [emilia2](data-versions.md#emilia2) | ar、as、bn、cs、da、de、el、en、es、fa、fi、fil、fr、gu、hi、hu、it、ja、kn、ko、mk、ml、mr、ne、nl、pa、pl、pt、ro、ru、sa、sd、sv、ta、te、th、tr、ur、vi、yue、zh | 语音识别、diarization、语音合成 | 146,325.0 | 多语种视频野外语音（Emilia2）；含中英解包版 | 部分版本：`TTS 桶:Emilia2/`（原始数据） |
| [emilia2_dialog](data-versions.md#emilia2_dialog) | en、zh | 目标说话人语音识别 | 15,172.8 | Emilia2 中英对话的轮流说话目标说话人数据 | 没有 |
| [emilia2_mix](data-versions.md#emilia2_mix) | en、zh | 目标说话人语音识别 | 35,744.6 | Emilia2 长音频合成的 2/3 人目标说话人混合 | 没有 |
| [emilia2_short](data-versions.md#emilia2_short) | en、zh | 语音识别 | 5,102.9 | Emilia2 中英短音频普通转写 | 没有 |
| [emilia_yodas](data-versions.md#emilia_yodas) | de、en、fr、ja、ko、zh | 语音识别、语音合成 | 113,820.6 | Emilia-YODAS 多语种 YouTube 语音 | `TTS 桶:Emilia-YODAS/`（原始数据） |
| [farfield_speech_noise_1spk](data-versions.md#farfield_speech_noise_1spk) | en、zh | noise | 32.7 | 1–3 人远场人声噪声（Emilia 干声加混响） | 没有 |
| [genshin_voice](data-versions.md#genshin_voice) | en-US、ja、ko、zh | 语音合成 | 1,039.7 | 《原神》多语配音，TTS 用 | `TTS 桶:genshin-voice/`（原始数据） |
| [hard_hw_sft](data-versions.md#hard_hw_sft) | en、zh | 热词增强语音识别 | 109.4 | 热词难例 SFT 数据（ShareGPT 格式） | 没有 |
| [hotword_bench](data-versions.md#hotword_bench) | en、zh | 热词增强语音识别 | — | 中英热词评测集，仅评测 | 没有 |
| [hw_sft](data-versions.md#hw_sft) | en、zh | 语音识别、热词增强语音识别 | 2,636.5 | 热词 SFT 数据（ShareGPT 格式），含普通转写 | 没有 |
| [indicvoices](data-versions.md#indicvoices) | as、bn、brx、doi、gu、hi、kn、kok、ks、mai、ml、mni、mr、ne、or、pa、sa、sat、sd、ta、te、ur | 语音识别 | — | 22 种印度语言自然语音（IndicVoices） | 快照 20260914 |
| [meeting_benchmark](data-versions.md#meeting_benchmark) | en、zh、zh-en | 带说话人标注的语音识别 | 21.2 | 约 180 秒长度的中英会议转写评测集 | `备份桶:audio-data-contract/datasets/meeting_180s_benchmark/` |
| [meeting_selection_panel](data-versions.md#meeting_selection_panel) | en、zh | 带说话人标注的语音识别 | 12.4 | 会议模型选模面板（中英真实会议） | `备份桶:audio-data-contract/datasets/meeting_selection_panel/` |
| [mls_sidon](data-versions.md#mls_sidon) | de、en、es、fr、it、nl、pl、pt | 语音识别、语音合成 | 50,834.3 | 8 种语言有声书，音频经 Sidon 修复（MLS） | 没有 |
| [multi-talker-sd](data-versions.md#multi-talker-sd) | en、zh | 语音识别、语码转换语音识别、连续语音分离、重叠语音检测、带说话人标注的语音识别、说话人分段与归属 | — | AISHELL-1、LibriSpeech 合成的多人对话 | 快照 20260914 |
| [opendatalab_multilingual](data-versions.md#opendatalab_multilingual) | ar、cs、hu、ko、ru、sr、th、vi | 语音识别 | 8,588.2 | 8 个语种的语音识别数据（OpenDataLab） | `备份桶:computer-2/audio/`（原始数据）、`备份桶:opendatalab-multilingual/`（原始数据） |
| [sot_multispeaker_zh_en](data-versions.md#sot_multispeaker_zh_en) | en、zh、zh-en | 带说话人标注的语音识别 | 7,664.4 | 1–5 人中英合成混音，按人完整转写 | 没有 |
| [starrail_voice](data-versions.md#starrail_voice) | en、ja、ko、zh-CN | 语音合成 | 692.6 | 《崩坏：星穹铁道》多语配音，TTS 用 | `TTS 桶:starrail-voice/`（原始数据） |
| [talcs](data-versions.md#talcs) | en、zh | 语音识别、热词增强语音识别 | 587.6 | 中英语码转换课堂语音（TALCS）；含热词和加噪版 | 快照 20260914 |
| [ts_hw_test](data-versions.md#ts_hw_test) | en、zh | 目标说话人语音识别 | 7.7 | 目标说话人加热词评测（LibriSpeech 风格） | 快照 20260914 |
| [ts_interference_pool](data-versions.md#ts_interference_pool) | en、zh | ts_asr_interference | 656.6 | 在线混合用的干扰人语音素材池 | 没有 |
| [ts_nonspeech_pool](data-versions.md#ts_nonspeech_pool) | en、zh | 语音识别 | 65.7 | 非人声与背景人声的空输出训练片段 | 没有 |
| [ts_scene_pool](data-versions.md#ts_scene_pool) | en、zh | 目标说话人语音识别 | 386.2 | 目标说话人难例场景素材（相近声音、交接） | 没有 |
| [vitw](data-versions.md#vitw) | en、zh | 语音识别 | 1,085.4 | 真实场景中英语音（VITW）；含回声、远场等评测 | 部分版本：快照 20260914 |
| [waxal-asr](data-versions.md#waxal-asr) | ach、aka、am、dag、dga、ee、ff、kpo、lg、ln、mas、mg、nyn、om、sid、sn、sog、ti、wal | 语音识别 | — | 19 种非洲语言语音（WAXAL） | 快照 20260914 |
| [wutheringwaves](data-versions.md#wutheringwaves) | en、ja、ko、zh | 语音合成 | 134.8 | 《鸣潮》多语配音，TTS 用 | `TTS 桶:WutheringWaves-2.2/`（原始数据） |
| [zenless_voice](data-versions.md#zenless_voice) | en、ja、ko、zh | 语音合成 | 554.4 | 《绝区零》多语配音，TTS 用 | `TTS 桶:zenless-voice/`（原始数据） |

## 其他语言数据

| 数据集 | 语言 | 任务 | 时长（小时） | 简介 | COS |
|---|---|---|---:|---|---|
| [audioset_road_traffic](data-versions.md#audioset_road_traffic) | und | noise | — | AudioSet 道路交通噪声 | 快照 20260914 |
| [banspeech_bn](data-versions.md#banspeech_bn) | bn | 语音识别 | 6.5 | 孟加拉语语音识别数据（BanSpeech） | 快照 20260914 |
| [cbtts_bn](data-versions.md#cbtts_bn) | bn | 语音识别 | 20.1 | 孟加拉语语音识别数据（CBTTS） | 快照 20260914 |
| [ciempiess](data-versions.md#ciempiess) | es | 语音识别 | 18.4 | 墨西哥西班牙语广播语音（CIEMPIESS LIGHT） | 快照 20260914 |
| [cml_tts_fr](data-versions.md#cml_tts_fr) | fr | 语音识别 | 316.0 | 法语有声书朗读（CML-TTS） | 快照 20260914 |
| [common_voice_ar](data-versions.md#common_voice_ar) | ar | 语音识别 | 58.2 | 众包朗读阿拉伯语（Common Voice） | 快照 20260914 |
| [common_voice_bn](data-versions.md#common_voice_bn) | bn | 语音识别 | 67.4 | 众包朗读孟加拉语（Common Voice） | 快照 20260914 |
| [common_voice_de](data-versions.md#common_voice_de) | de | 语音识别 | 1,034.8 | 众包朗读德语（Common Voice） | 快照 20260914 |
| [common_voice_es](data-versions.md#common_voice_es) | es | 语音识别 | 568.5 | 众包朗读西班牙语（Common Voice） | 快照 20260914 |
| [common_voice_fr](data-versions.md#common_voice_fr) | fr | 语音识别 | 924.1 | 众包朗读法语（Common Voice） | 快照 20260914 |
| [common_voice_ja](data-versions.md#common_voice_ja) | ja | 语音识别 | 48.2 | 众包朗读日语（Common Voice） | 快照 20260914 |
| [common_voice_ko](data-versions.md#common_voice_ko) | ko | 语音识别 | 2.6 | 众包朗读韩语（Common Voice） | 快照 20260914 |
| [common_voice_ru](data-versions.md#common_voice_ru) | ru | 语音识别 | 69.9 | 众包朗读俄语（Common Voice） | 快照 20260914 |
| [demand](data-versions.md#demand) | und | noise | 46.7 | 16 麦阵列录制的多环境噪声（DEMAND） | 没有 |
| [dns5_noise_rir](data-versions.md#dns5_noise_rir) | und | rir、speech_enhancement | — | DNS Challenge 5 官方噪声与冲激响应包 | 没有 |
| [dns5_noise_train](data-versions.md#dns5_noise_train) | und | noise、rir | 252.6 | 训练用 DNS5 噪声与模拟房间响应 | 没有 |
| [emilia_ja](data-versions.md#emilia_ja) | ja | 语音识别 | 1,715.5 | Emilia 日语野外语音 | 快照 20260914 |
| [emilia_ko](data-versions.md#emilia_ko) | ko | 语音识别 | 217.2 | Emilia 韩语野外语音 | 快照 20260914 |
| [fleurs_ar](data-versions.md#fleurs_ar) | ar | 语音识别 | 8.2 | 多语朗读阿拉伯语部分（FLEURS） | 快照 20260914 |
| [fleurs_bn](data-versions.md#fleurs_bn) | bn | 语音识别 | 15.6 | 多语朗读孟加拉语部分（FLEURS） | 快照 20260914 |
| [fleurs_de](data-versions.md#fleurs_de) | de | 语音识别 | 13.4 | 多语朗读德语部分（FLEURS） | 快照 20260914 |
| [fleurs_es](data-versions.md#fleurs_es) | es | 语音识别 | 13.2 | 多语朗读西班牙语部分（FLEURS） | 快照 20260914 |
| [fleurs_fr](data-versions.md#fleurs_fr) | fr | 语音识别 | 13.1 | 多语朗读法语部分（FLEURS） | 快照 20260914 |
| [fleurs_ja](data-versions.md#fleurs_ja) | ja | 语音识别 | 10.7 | 多语朗读日语部分（FLEURS） | 快照 20260914 |
| [fleurs_ko](data-versions.md#fleurs_ko) | ko | 语音识别 | 10.1 | 多语朗读韩语部分（FLEURS） | 快照 20260914 |
| [fleurs_ru](data-versions.md#fleurs_ru) | ru | 语音识别 | 11.6 | 多语朗读俄语部分（FLEURS） | 快照 20260914 |
| [fsd50k](data-versions.md#fsd50k) | und | noise、sound_event | 108.6 | 200 类声音事件（FSD50K） | 没有 |
| [galgame](data-versions.md#galgame) | ja | 语音合成 | 10,173.7 | 日语视觉小说配音，TTS 用 | `TTS 桶:Galgame-VisualNovel-Reupload/`（原始数据） |
| [gigaspeech2_id](data-versions.md#gigaspeech2_id) | id | 语音识别、热词增强语音识别 | 1,980.1 | 印尼语网络语音（GigaSpeech 2）；含热词版 | 快照 20260914 |
| [koreaspeech](data-versions.md#koreaspeech) | ko | 语音识别 | 3,828.3 | 韩语语音识别数据（KoreaSpeech） | 快照 20260914 |
| [meeting_room_noise](data-versions.md#meeting_room_noise) | und | noise | 2.5 | 真实会议室底噪（AliMeeting、AISHELL-4） | 没有 |
| [mgb2](data-versions.md#mgb2) | ar | 语音识别 | 1,215.5 | 半岛电视台阿拉伯语广播（MGB-2） | 快照 20260914 |
| [mit_ir_survey](data-versions.md#mit_ir_survey) | und | rir | 0.0 | MIT 日常环境实测冲激响应（270 条） | 没有 |
| [mls_de](data-versions.md#mls_de) | de | 语音识别 | 1,995.1 | 德语有声书朗读（MLS） | 快照 20260914 |
| [mls_es](data-versions.md#mls_es) | es | 语音识别 | 937.7 | 西班牙语有声书朗读（MLS） | 快照 20260914 |
| [mls_fr](data-versions.md#mls_fr) | fr | 语音识别 | 1,096.7 | 法语有声书朗读（MLS） | 快照 20260914 |
| [musan](data-versions.md#musan) | und | noise | — | 噪声与音乐素材（MUSAN） | 快照 20260914 |
| [open_large_bn](data-versions.md#open_large_bn) | bn | 语音识别 | 5,045.8 | 孟加拉语大规模语音识别数据 | 快照 20260914 |
| [real_rir_slr28](data-versions.md#real_rir_slr28) | und | 音频增强、rir | 0.1 | 真实房间冲激响应（OpenSLR 28） | 快照 20260914 |
| [rulibrispeech_ru](data-versions.md#rulibrispeech_ru) | ru | 语音识别 | 98.2 | 俄语有声书朗读（Russian LibriSpeech） | 快照 20260914 |
| [sim_rir_slr26](data-versions.md#sim_rir_slr26) | und | rir | — | 模拟房间冲激响应（OpenSLR 26） | 快照 20260914 |
| [sim_rir_slr28](data-versions.md#sim_rir_slr28) | und | rir | — | 模拟房间冲激响应（OpenSLR 28） | 快照 20260914 |
| [slr37_bn](data-versions.md#slr37_bn) | bn | 语音识别 | 5.0 | 孟加拉语高质量 TTS 朗读（OpenSLR 37） | 快照 20260914 |
| [voices_noise](data-versions.md#voices_noise) | und | noise | 128.3 | VOiCES 真实房间噪声与背景人声 | 没有 |
| [voxconverse](data-versions.md#voxconverse) | und | 说话人分段与归属 | 43.5 | YouTube 视频说话人日志评测（VoxConverse） | 没有 |
| [wham](data-versions.md#wham) | und | noise | — | WHAM! 噪声训练划分 | 没有 |
| [wham_noise](data-versions.md#wham_noise) | und | noise | 81.7 | 湾区餐厅、咖啡馆等真实环境噪声（WHAM!） | 没有 |
| [yodas_ar](data-versions.md#yodas_ar) | ar | 语音识别 | 289.7 | YouTube 多语语音阿拉伯语部分（YODAS） | 快照 20260914 |
| [yodas_bn](data-versions.md#yodas_bn) | bn | 语音识别 | 27.1 | YouTube 多语语音孟加拉语部分（YODAS） | 快照 20260914 |
| [yodas_de](data-versions.md#yodas_de) | de | 语音识别 | 3,062.9 | YouTube 多语语音德语部分（YODAS） | 快照 20260914 |
| [yodas_es](data-versions.md#yodas_es) | es | 语音识别 | 3,737.8 | YouTube 多语语音西班牙语部分（YODAS） | 快照 20260914 |
| [yodas_fr](data-versions.md#yodas_fr) | fr | 语音识别 | 2,423.7 | YouTube 多语语音法语部分（YODAS） | 快照 20260914 |
| [yodas_ja](data-versions.md#yodas_ja) | ja | 语音识别 | 1,094.2 | YouTube 多语语音日语部分（YODAS） | 快照 20260914 |
| [yodas_ko](data-versions.md#yodas_ko) | ko | 语音识别 | 2,774.3 | YouTube 多语语音韩语部分（YODAS） | 快照 20260914 |
| [yodas_ru](data-versions.md#yodas_ru) | ru | 语音识别 | 5,596.0 | YouTube 多语语音俄语部分（YODAS） | 快照 20260914 |

## 下载来源声明

仅登记来源、版本和预期位置，不代表已下载或可训练。

| 数据集 | 版本 | 语言 | 支持任务 |
|---|---|---|---|
| [OpenSLR 159 AISHELL-5](../../catalog/download_queue.yaml#L1) | 1.0 | zh | 语音识别 |
| [ciempiess](../../catalog/ciempiess_original.yaml#L1) | official-2014 | es | 语音识别 |
| [ciempiess](../../catalog/ciempiess_test.yaml#L1) | hf-c134fff8e335 | es | 语音识别 |
| [common_voice_en](../../catalog/download_queue.yaml#L59) | 26.0 | en | 语音识别 |
| [common_voice_es](../../catalog/common_voice_es.yaml#L1) | 26.0 | es | 语音识别 |
| [common_voice_pt](../../catalog/common_voice_pt.yaml#L1) | 26.0 | pt | 语音识别 |
| [common_voice_yue](../../catalog/download_queue.yaml#L139) | 26.0 | yue | 语音识别 |
| [common_voice_zh](../../catalog/download_queue.yaml#L86) | 26.0 | zh | 语音识别 |
| [common_voice_zh_hk](../../catalog/download_queue.yaml#L113) | 26.0 | yue | 语音识别 |
| [coraa_mupe](../../catalog/coraa_mupe.yaml#L1) | hf-437966f103b3 | pt-BR | 语音识别 |
| [gigaspeech2](../../catalog/download_queue.yaml#L165) | hf-8dc0d0e502b7 | id、th、vi | 语音识别 |
| [google_latam](../../catalog/google_latam.yaml#L1) | openslr-20260911 | es | 语音识别 |
| [granary](../../catalog/download_queue.yaml#L200) | hf-0fe23a860e35 | multi | 语音识别、语音翻译 |
| [lemas](../../catalog/download_queue.yaml#L250) | hf-91f0c1b9a29f | multi | 语音识别 |
| [loquacious_set](../../catalog/loquacious_set.yaml#L1) | hf-0e84cdb9e4b8 | en | 语音识别 |
| [mls_pt](../../catalog/mls_pt.yaml#L1) | openslr-94 | pt | 语音识别 |
| [omnilingual-asr-corpus](../../catalog/download_queue.yaml#L225) | hf-8648ba894637 | multi | 语音识别 |
| [peoples_speech](../../catalog/peoples_speech.yaml#L1) | hf-f10597c5d3d3 | en | 语音识别 |
| [reazonspeech](../../catalog/download_queue.yaml#L274) | hf-0df78f991f6a | ja | 语音识别 |
| [yodas_granary_es_pt](../../catalog/yodas_granary_es_pt.yaml#L1) | hf-969944574ea3 | es、pt | 语音识别 |

## 训练混合配方

这些配方复用上面的数据，不增加源数据集数量或时长。

- [icefall_v10_farfield_replay@prepared-20260908](../../catalog/icefall_v10_replay.yaml#L1)

## 数据声明与维护

- [目录说明](../../catalog/README.md)：声明格式、字段和统计规则。
- [组织规范](../reference/data-organization.md)：数据身份、版本、处理层与视图。
- 新增数据时登记任务、语言、`provenance.summary`（一句话简介）和顶层 split 的 `statistics.duration_hours`；未知时长留空，不填 0。
- 更新 catalog（含 `catalog/backups/`）或 views 后运行 `audio-data-contract generate-overview`；CI 用 `--check` 检查本页、版本明细和图表同步。

# 数据总览

按数据集查看语言、支持任务、时长和特性。清洗、热词、加噪、评测入口和训练框架配置归入所属数据集，不另算一套源数据。

当前登记 **103 个数据集条目**；另有 **10 个下载来源声明**和 **1 个训练混合配方**。登记不代表本机文件已齐备。

时长单位为小时。不同版本、子集和标注片段可能重叠，逐项列出，不相加为总量；没有时长的条目仍保留。参考表数字未核实当前文件与划分覆盖；“过滤前”不能当作清洗后时长。

任务是该数据集各已登记版本的能力并集，具体版本和划分以链接内声明为准。标点、热词和文件哈希校验都不能单独证明做过内容清洗。

## 数据规模与登记覆盖

![数据集时长 Top 20](assets/data-duration-top20.svg)

每个数据集仅取最大的一项完整版本登记、参考或估算时长，并标出对应版本。部分划分和过滤前时长不参与排名；不同颜色区分登记值与参考 / 估算值。排名用于查看量级，不代表最新版本或整个数据集的完整时长。

![时长登记覆盖情况](assets/data-duration-coverage.svg)

覆盖图按数据集互斥分类：优先计入“至少一个版本有完整时长登记”，其次是“仅参考、估算或部分时长”，其余为“尚未登记”。完整登记只针对对应版本，不代表整个数据集所有子集和版本均已覆盖。

## 英文数据

| 数据集 | 语言 | 支持任务 | 时长（小时，注明范围） | 特性 / 备注 |
|---|---|---|---|---|
| [ami](../catalog/icefall_runtime.jsonl#L46) | en | 语音识别 | 92.1（已登记；[单远场麦克风标注片段](../catalog/icefall_runtime.jsonl#L46)） | 标注片段时长，重叠语音或多麦克风可能重复计时。训练集缺少 2 场会议（134/136） |
| [audioset_esc_test](../catalog/open_audio_eval.jsonl#L48) | en | 背景声场景描述 | 未登记 | 当前仅登记评测入口 |
| [common_voice_en](../catalog/local_lhotse_derived.jsonl#L8) | en | 语音识别、热词增强语音识别 | 1,854.0（[参考表](https://ccnuebbmik1f.feishu.cn/wiki/CEXFwEjPoi2bIukVjk9c5FdOn12?sheet=3d4d23)；legacy-20260804） | Qwen3-ASR-1.7B + whisper-large-v3 双引擎筛选；train 需过滤 1,127 条失败记录；test 清单尚未应用筛选结果；含派生版本（与源数据可能重叠） |
| [cs_dialogue_en](../catalog/icefall_base.jsonl#L29) | en | 语音识别 | 未登记 | 已登记划分：dev、test、train |
| [emilia_en](../catalog/legacy_multilingual.jsonl#L17) | en | 语音识别 | 43,624.0（已登记；[legacy](../catalog/legacy_multilingual.jsonl#L17)） | 参考表注明 clean2604，Whisper + Qwen3ASR 转录、已有清洗；本次未复核实际样本；有含标点版本 |
| [emotion1200_en](../catalog/open_audio_eval.jsonl#L32) | en | 说话人情感分类、情感与说话风格描述、语音情感识别 | 未登记 | 当前仅登记评测入口 |
| [fleurs_en](../catalog/legacy_multilingual.jsonl#L16) | en | 语音识别 | 10.3（已登记；[legacy](../catalog/legacy_multilingual.jsonl#L16)） | 有含标点版本 |
| [gigaspeech](../catalog/icefall_base.jsonl#L3) | en | 语音识别 | 10,000.0（[参考表](https://ccnuebbmik1f.feishu.cn/wiki/CEXFwEjPoi2bIukVjk9c5FdOn12?sheet=3d4d23)；legacy-20260804） | 已登记划分：dev、test、train |
| [iemocap_ser](../catalog/open_audio_eval.jsonl#L28) | en | 语音情感识别 | 未登记 | 当前仅登记评测入口 |
| [legco_speech_en](../catalog/icefall_base.jsonl#L33) | en | 语音识别 | 未登记 | 已登记划分：train |
| [libri2mix](../catalog/open_audio_eval.jsonl#L37) | en | 目标说话人语音识别 | 未登记 | 当前仅登记评测入口 |
| [libri3mix](../catalog/open_audio_eval.jsonl#L38) | en | 目标说话人语音识别 | 未登记 | 当前仅登记评测入口 |
| [librispeech](../catalog/icefall_base.jsonl#L1) | en | 语音识别、热词增强语音识别 | 960.0（[参考表](https://ccnuebbmik1f.feishu.cn/wiki/CEXFwEjPoi2bIukVjk9c5FdOn12?sheet=3d4d23)；legacy-20260804） | 含派生版本（与源数据可能重叠） |
| [meld_ser](../catalog/open_audio_eval.jsonl#L27) | en | 语音情感识别 | 未登记 | 当前仅登记评测入口 |
| [mls](../catalog/icefall_base.jsonl#L2) | en | 语音识别 | 44,500.0（[参考表](https://ccnuebbmik1f.feishu.cn/wiki/CEXFwEjPoi2bIukVjk9c5FdOn12?sheet=3d4d23)；legacy-20260804） | 已登记划分：dev、test、train |
| [msp_podcast_ser](../catalog/open_audio_eval.jsonl#L29) | en | 语音情感识别 | 未登记 | 当前仅登记评测入口 |
| [notsofar](../catalog/icefall_runtime.jsonl#L47) | en | 语音识别、连续语音分离、重叠语音检测、带说话人标注的语音识别、说话人分段与归属 | 200.0（估算；[hf-ba8fd0f034ce-sim-v1.5-200h](../catalog/multilingual_multispeaker.jsonl#L6)）<br>176.9（已登记；[单远场麦克风标注片段](../catalog/icefall_runtime.jsonl#L47)） | 标注片段时长，重叠语音或多麦克风可能重复计时 |
| [singapore_english](../catalog/icefall_base.jsonl#L6) | en | 语音识别 | 2.0（[参考表](https://ccnuebbmik1f.feishu.cn/wiki/CEXFwEjPoi2bIukVjk9c5FdOn12?sheet=3d4d23)；legacy-20260804） | 新加坡英语；登记 cleaned 标注，尚未核实清洗引擎和规则 |
| [singaporean](../catalog/icefall_base.jsonl#L5) | en | 语音识别 | 0.2（[参考表](https://ccnuebbmik1f.feishu.cn/wiki/CEXFwEjPoi2bIukVjk9c5FdOn12?sheet=3d4d23)；legacy-20260804） | 新加坡英语；登记 cleaned 标注，尚未核实清洗引擎和规则 |
| [tal100_en](../catalog/icefall_base.jsonl#L7) | en | 语音识别 | 未登记 | 已登记划分：dev、test、train |

## 中文及粤语数据

| 数据集 | 语言 | 支持任务 | 时长（小时，注明范围） | 特性 / 备注 |
|---|---|---|---|---|
| [aidatatang](../catalog/icefall_base.jsonl#L21) | zh | 语音识别、热词增强语音识别 | 140.0（[参考表](https://ccnuebbmik1f.feishu.cn/wiki/CEXFwEjPoi2bIukVjk9c5FdOn12?sheet=3d4d23)；legacy-20260804） | 含派生版本（与源数据可能重叠） |
| [aishell](../catalog/icefall_base.jsonl#L13) | zh | 语音识别、热词增强语音识别 | 155.0（[参考表](https://ccnuebbmik1f.feishu.cn/wiki/CEXFwEjPoi2bIukVjk9c5FdOn12?sheet=3d4d23)；legacy-20260804） | 含派生版本（与源数据可能重叠） |
| [aishell2](../catalog/icefall_base.jsonl#L14) | zh | 语音识别、热词增强语音识别 | 1,036.0（[参考表](https://ccnuebbmik1f.feishu.cn/wiki/CEXFwEjPoi2bIukVjk9c5FdOn12?sheet=3d4d23)；legacy-20260804） | 含派生版本（与源数据可能重叠） |
| [aishell3](../catalog/icefall_base.jsonl#L15) | zh | 语音识别、热词增强语音识别 | 65.0（[参考表](https://ccnuebbmik1f.feishu.cn/wiki/CEXFwEjPoi2bIukVjk9c5FdOn12?sheet=3d4d23)；legacy-20260804） | 含派生版本（与源数据可能重叠） |
| [aishell4](../catalog/icefall_base.jsonl#L16) | zh | 语音识别 | 未登记 | 已登记划分：test、train |
| [alimeeting](../catalog/alimeeting_far_raw.jsonl#L1) | zh | 语音识别、连续语音分离、重叠语音检测、带说话人标注的语音识别、说话人分段与归属 | 125.5（已登记；[openslr-119-far-local-20260903](../catalog/alimeeting_far_raw.jsonl#L1)）<br>157.9（已登记；[单远场麦克风标注片段](../catalog/icefall_runtime.jsonl#L45)） | 远场会议、多说话人、重叠语音；训练集 8 条标注越界，使用前需处理；标注片段时长，重叠语音或多麦克风可能重复计时 |
| [biic_podcast_ser](../catalog/open_audio_eval.jsonl#L25) | zh | 语音情感识别 | 未登记 | 当前仅登记评测入口 |
| [childmandarin](../catalog/icefall_base.jsonl#L25) | zh | 语音识别 | 未登记 | 已登记划分：dev、test、train |
| [common_voice_yue](../catalog/icefall_base.jsonl#L37) | yue | 语音识别 | 未登记 | 已登记划分：dev、test、train |
| [common_voice_zh](../catalog/icefall_base.jsonl#L23) | zh | 语音识别、热词增强语音识别 | 43.0（[参考表](https://ccnuebbmik1f.feishu.cn/wiki/CEXFwEjPoi2bIukVjk9c5FdOn12?sheet=3d4d23)；legacy-20260804） | 含派生版本（与源数据可能重叠） |
| [common_voice_zh_hk](../catalog/icefall_base.jsonl#L38) | yue | 语音识别 | 未登记 | 已登记划分：dev、test、train |
| [cs_dialogue](../catalog/icefall_base.jsonl#L28) | zh | 语音识别 | 未登记 | 已登记划分：dev、test、train |
| [emilia_zh](../catalog/legacy_multilingual.jsonl#L41) | zh | 语音识别 | 40,848.4（已登记；[legacy](../catalog/legacy_multilingual.jsonl#L41)）<br>23,956.0（[参考表](https://ccnuebbmik1f.feishu.cn/wiki/CEXFwEjPoi2bIukVjk9c5FdOn12?sheet=3d4d23)；legacy-20260804） | 参考表注明 clean2604，Whisper + Qwen3ASR 转录、已有清洗；本次未复核实际样本；有含标点版本 |
| [emotion1200_zh](../catalog/open_audio_eval.jsonl#L33) | zh | 说话人情感分类、情感与说话风格描述、语音情感识别 | 未登记 | 当前仅登记评测入口 |
| [fleurs_zh](../catalog/legacy_multilingual.jsonl#L40) | zh | 语音识别 | 14.1（已登记；[legacy](../catalog/legacy_multilingual.jsonl#L40)） | 有含标点版本 |
| [kespeech](../catalog/icefall_base.jsonl#L20) | zh | 语音识别、热词增强语音识别 | 1,428.0（[参考表](https://ccnuebbmik1f.feishu.cn/wiki/CEXFwEjPoi2bIukVjk9c5FdOn12?sheet=3d4d23)；legacy-20260804） | 含派生版本（与源数据可能重叠） |
| [legco_speech](../catalog/icefall_base.jsonl#L32) | yue | 语音识别 | 未登记 | 已登记划分：train |
| [m3ed_ser](../catalog/open_audio_eval.jsonl#L26) | zh | 语音情感识别 | 未登记 | 当前仅登记评测入口 |
| [magicdata](../catalog/icefall_base.jsonl#L18) | zh | 语音识别、热词增强语音识别 | 747.0（[参考表](https://ccnuebbmik1f.feishu.cn/wiki/CEXFwEjPoi2bIukVjk9c5FdOn12?sheet=3d4d23)；legacy-20260804） | 含派生版本（与源数据可能重叠） |
| [magicdata_ramc](../catalog/icefall_base.jsonl#L19) | zh | 语音识别 | 未登记 | 已登记划分：dev、test、train |
| [mdcc](../catalog/icefall_base.jsonl#L34) | yue | 语音识别 | 未登记 | 含派生版本（与源数据可能重叠） |
| [police_robust_monitor](../catalog/icefall_runtime.jsonl#L70) | zh | 语音识别 | 未登记 | 尚未登记独立划分 |
| [police_synthetic_zh_accent](../catalog/synthetic_asr.jsonl#L1) | zh | 语音识别 | 46.4（已登记；[v1-20260817](../catalog/synthetic_asr.jsonl#L1)）<br>52.6（已登记；[v2-20260818](../catalog/synthetic_asr.jsonl#L2)）<br>36.0（已登记；[v3-20260820](../catalog/synthetic_asr.jsonl#L3)）<br>41.2（已登记；[v5-20260830-qc](../catalog/synthetic_asr_v5_qc.jsonl#L1)）<br>28.2（已登记；[v5-20260830-qwen75-cosy25](../catalog/synthetic_asr.jsonl#L4)） | 含派生版本（与源数据可能重叠） |
| [police_terms_v5](../catalog/icefall_runtime.jsonl#L12) | zh | 语音识别 | 未登记 | 已登记划分：dev、test、train |
| [primewords](../catalog/icefall_base.jsonl#L22) | zh | 语音识别 | 未登记 | 已登记划分：train |
| [realman](../catalog/icefall_runtime.jsonl#L49) | zh | 语音识别 | 83.7（已登记；[已准备标注片段](../catalog/icefall_runtime.jsonl#L49)） | 标注片段时长，重叠语音或多麦克风可能重复计时 |
| [speechio](../catalog/legacy_multilingual.jsonl#L42) | zh | 语音识别 | 63.8（已登记；[legacy](../catalog/legacy_multilingual.jsonl#L42)） | 有含标点版本 |
| [tal100_zh](../catalog/icefall_base.jsonl#L24) | zh | 语音识别 | 未登记 | 已登记划分：dev、test、train |
| [thchs30](../catalog/icefall_base.jsonl#L17) | zh | 语音识别、热词增强语音识别 | 35.0（[参考表](https://ccnuebbmik1f.feishu.cn/wiki/CEXFwEjPoi2bIukVjk9c5FdOn12?sheet=3d4d23)；legacy-20260804） | 含派生版本（与源数据可能重叠） |
| [wenetspeech](../catalog/icefall_base.jsonl#L8) | zh | 语音识别 | 2,477.9（过滤前；[clean-weak-v1-20260904](../catalog/wenetspeech_weak.jsonl#L2)）<br>2,477.9（已登记；[weak-source-20260904](../catalog/wenetspeech_weak.jsonl#L1)）<br>10,000.0（[参考表](https://ccnuebbmik1f.feishu.cn/wiki/CEXFwEjPoi2bIukVjk9c5FdOn12?sheet=3d4d23)；legacy-20260804） | 含派生版本（与源数据可能重叠） |
| [wenetspeech4tts](../catalog/icefall_base.jsonl#L9) | zh | 语音识别 | 7,700.0（[参考表](https://ccnuebbmik1f.feishu.cn/wiki/CEXFwEjPoi2bIukVjk9c5FdOn12?sheet=3d4d23)；legacy-20260804） | 已登记划分：train |
| [wenetspeech_chuan](../catalog/icefall_base.jsonl#L10) | zh | 语音识别 | 未登记 | 已登记划分：train |
| [wenetspeech_disfluency](../catalog/icefall_runtime.jsonl#L9) | zh | 语音识别 | 未登记 | 已登记划分：train |
| [wenetspeech_wu](../catalog/icefall_base.jsonl#L11) | zh | 语音识别 | 未登记 | 已登记划分：train |
| [wenetspeech_yue](../catalog/icefall_base.jsonl#L35) | yue | 语音识别 | 未登记 | 已登记划分：train |
| [wenetspeech_yue_all](../catalog/icefall_base.jsonl#L36) | yue | 语音识别 | 未登记 | 已登记划分：train |

## 混合语言及多语数据

| 数据集 | 语言 | 支持任务 | 时长（小时，注明范围） | 特性 / 备注 |
|---|---|---|---|---|
| [cs_dialogue_mix](../catalog/icefall_base.jsonl#L30) | en、zh | 语音识别 | 未登记 | 已登记划分：dev、test、train |
| [cumix2017](../catalog/icefall_base.jsonl#L31) | en、yue | 语音识别 | 未登记 | 已登记划分：train |
| [indicvoices](../catalog/multilingual_multispeaker.jsonl#L2) | as、bn、brx、doi、gu、hi、kn、kok、ks、mai、ml、mni、mr、ne、or、pa、sa、sat、sd、ta、te、ur | 语音识别 | 未登记 | 已登记划分：all |
| [multi-talker-sd](../catalog/multilingual_multispeaker.jsonl#L3) | en、zh | 语音识别、语码转换语音识别、连续语音分离、重叠语音检测、带说话人标注的语音识别、说话人分段与归属 | 未登记 | 已登记划分：dev、test、train |
| [talcs](../catalog/icefall_base.jsonl#L27) | en、zh | 语音识别、热词增强语音识别 | 300.0（[参考表](https://ccnuebbmik1f.feishu.cn/wiki/CEXFwEjPoi2bIukVjk9c5FdOn12?sheet=3d4d23)；legacy-20260804） | 含派生版本（与源数据可能重叠） |
| [ts_hw_test](../catalog/open_audio_eval.jsonl#L36) | en、zh | 目标说话人语音识别 | 未登记 | 当前仅登记评测入口 |
| [vitw](../catalog/icefall_runtime.jsonl#L48) | en、zh | 语音识别 | 77.3（已登记；[远场子集](../catalog/icefall_runtime.jsonl#L48)） | 标注片段时长，重叠语音或多麦克风可能重复计时 |
| [waxal-asr](../catalog/multilingual_multispeaker.jsonl#L4) | ach、aka、am、dag、dga、ee、ff、kpo、lg、ln、mas、mg、nyn、om、sid、sn、sog、ti、wal | 语音识别 | 未登记 | 已登记划分：all |

## 其他语言数据

| 数据集 | 语言 | 支持任务 | 时长（小时，注明范围） | 特性 / 备注 |
|---|---|---|---|---|
| [banspeech_bn](../catalog/legacy_multilingual.jsonl#L5) | bn | 语音识别 | 6.5（已登记；[legacy](../catalog/legacy_multilingual.jsonl#L5)） | 有无标点版本 |
| [cbtts_bn](../catalog/legacy_multilingual.jsonl#L6) | bn | 语音识别 | 20.1（已登记；[legacy](../catalog/legacy_multilingual.jsonl#L6)） | 有含标点版本 |
| [cml_tts_fr](../catalog/legacy_multilingual.jsonl#L22) | fr | 语音识别 | 316.0（已登记；[legacy](../catalog/legacy_multilingual.jsonl#L22)） | 有含标点版本 |
| [common_voice_ar](../catalog/legacy_multilingual.jsonl#L1) | ar | 语音识别 | 58.2（已登记；[legacy](../catalog/legacy_multilingual.jsonl#L1)） | 有含标点版本 |
| [common_voice_bn](../catalog/legacy_multilingual.jsonl#L7) | bn | 语音识别 | 67.4（已登记；[legacy](../catalog/legacy_multilingual.jsonl#L7)） | 有含标点版本 |
| [common_voice_de](../catalog/legacy_multilingual.jsonl#L12) | de | 语音识别 | 1,034.8（已登记；[legacy](../catalog/legacy_multilingual.jsonl#L12)） | 有含标点版本 |
| [common_voice_es](../catalog/legacy_multilingual.jsonl#L18) | es | 语音识别 | 568.5（已登记；[legacy](../catalog/legacy_multilingual.jsonl#L18)） | 有含标点版本 |
| [common_voice_fr](../catalog/legacy_multilingual.jsonl#L23) | fr | 语音识别 | 924.1（已登记；[legacy](../catalog/legacy_multilingual.jsonl#L23)） | 有含标点版本 |
| [common_voice_ja](../catalog/legacy_multilingual.jsonl#L27) | ja | 语音识别 | 48.2（已登记；[legacy](../catalog/legacy_multilingual.jsonl#L27)） | 有含标点版本 |
| [common_voice_ko](../catalog/legacy_multilingual.jsonl#L31) | ko | 语音识别 | 2.6（已登记；[legacy](../catalog/legacy_multilingual.jsonl#L31)） | 有含标点版本 |
| [common_voice_ru](../catalog/legacy_multilingual.jsonl#L36) | ru | 语音识别 | 69.9（已登记；[legacy](../catalog/legacy_multilingual.jsonl#L36)） | 有含标点版本 |
| [emilia_ja](../catalog/legacy_multilingual.jsonl#L28) | ja | 语音识别 | 1,715.5（已登记；[legacy](../catalog/legacy_multilingual.jsonl#L28)） | 有含标点版本 |
| [emilia_ko](../catalog/legacy_multilingual.jsonl#L32) | ko | 语音识别 | 217.2（已登记；[legacy](../catalog/legacy_multilingual.jsonl#L32)） | 有含标点版本 |
| [fleurs_ar](../catalog/legacy_multilingual.jsonl#L2) | ar | 语音识别 | 8.2（已登记；[legacy](../catalog/legacy_multilingual.jsonl#L2)） | 有含标点版本 |
| [fleurs_bn](../catalog/legacy_multilingual.jsonl#L8) | bn | 语音识别 | 15.6（已登记；[legacy](../catalog/legacy_multilingual.jsonl#L8)） | 有含标点版本 |
| [fleurs_de](../catalog/legacy_multilingual.jsonl#L13) | de | 语音识别 | 13.4（已登记；[legacy](../catalog/legacy_multilingual.jsonl#L13)） | 有含标点版本 |
| [fleurs_es](../catalog/legacy_multilingual.jsonl#L19) | es | 语音识别 | 13.2（已登记；[legacy](../catalog/legacy_multilingual.jsonl#L19)） | 有含标点版本 |
| [fleurs_fr](../catalog/legacy_multilingual.jsonl#L24) | fr | 语音识别 | 13.1（已登记；[legacy](../catalog/legacy_multilingual.jsonl#L24)） | 有含标点版本 |
| [fleurs_ja](../catalog/legacy_multilingual.jsonl#L29) | ja | 语音识别 | 10.7（已登记；[legacy](../catalog/legacy_multilingual.jsonl#L29)） | 有含标点版本 |
| [fleurs_ko](../catalog/legacy_multilingual.jsonl#L33) | ko | 语音识别 | 10.1（已登记；[legacy](../catalog/legacy_multilingual.jsonl#L33)） | 有含标点版本 |
| [fleurs_ru](../catalog/legacy_multilingual.jsonl#L37) | ru | 语音识别 | 11.6（已登记；[legacy](../catalog/legacy_multilingual.jsonl#L37)） | 有含标点版本 |
| [gigaspeech2_id](../catalog/local_lhotse_derived.jsonl#L1) | id | 语音识别、热词增强语音识别 | 未登记 | 含派生版本（与源数据可能重叠） |
| [koreaspeech](../catalog/legacy_multilingual.jsonl#L34) | ko | 语音识别 | 3,828.3（已登记；[legacy](../catalog/legacy_multilingual.jsonl#L34)） | 有含标点版本 |
| [mgb2](../catalog/legacy_multilingual.jsonl#L3) | ar | 语音识别 | 1,215.5（已登记；[legacy](../catalog/legacy_multilingual.jsonl#L3)） | 有无标点版本 |
| [mls_de](../catalog/legacy_multilingual.jsonl#L14) | de | 语音识别 | 1,995.1（已登记；[legacy](../catalog/legacy_multilingual.jsonl#L14)） | 有无标点版本 |
| [mls_es](../catalog/legacy_multilingual.jsonl#L20) | es | 语音识别 | 937.7（已登记；[legacy](../catalog/legacy_multilingual.jsonl#L20)） | 有无标点版本 |
| [mls_fr](../catalog/legacy_multilingual.jsonl#L25) | fr | 语音识别 | 1,096.7（已登记；[legacy](../catalog/legacy_multilingual.jsonl#L25)） | 有无标点版本 |
| [open_large_bn](../catalog/legacy_multilingual.jsonl#L9) | bn | 语音识别 | 5,045.8（已登记；[legacy](../catalog/legacy_multilingual.jsonl#L9)） | 有含标点版本 |
| [real_rir_slr28](../catalog/icefall_runtime.jsonl#L71) | und | 音频增强 | 未登记 | Real room impulse responses only; not speech/transcription training examples |
| [rulibrispeech_ru](../catalog/legacy_multilingual.jsonl#L38) | ru | 语音识别 | 98.2（已登记；[legacy](../catalog/legacy_multilingual.jsonl#L38)） | 有含标点版本 |
| [slr37_bn](../catalog/legacy_multilingual.jsonl#L10) | bn | 语音识别 | 5.0（已登记；[legacy](../catalog/legacy_multilingual.jsonl#L10)） | 有无标点版本 |
| [yodas_ar](../catalog/legacy_multilingual.jsonl#L4) | ar | 语音识别 | 289.7（已登记；[legacy](../catalog/legacy_multilingual.jsonl#L4)） | 有含标点版本 |
| [yodas_bn](../catalog/legacy_multilingual.jsonl#L11) | bn | 语音识别 | 27.1（已登记；[legacy](../catalog/legacy_multilingual.jsonl#L11)） | 有含标点版本 |
| [yodas_de](../catalog/legacy_multilingual.jsonl#L15) | de | 语音识别 | 3,062.9（已登记；[legacy](../catalog/legacy_multilingual.jsonl#L15)） | 有含标点版本 |
| [yodas_es](../catalog/legacy_multilingual.jsonl#L21) | es | 语音识别 | 3,737.8（已登记；[legacy](../catalog/legacy_multilingual.jsonl#L21)） | 有含标点版本 |
| [yodas_fr](../catalog/legacy_multilingual.jsonl#L26) | fr | 语音识别 | 2,423.7（已登记；[legacy](../catalog/legacy_multilingual.jsonl#L26)） | 有含标点版本 |
| [yodas_ja](../catalog/legacy_multilingual.jsonl#L30) | ja | 语音识别 | 1,094.2（已登记；[legacy](../catalog/legacy_multilingual.jsonl#L30)） | 有含标点版本 |
| [yodas_ko](../catalog/legacy_multilingual.jsonl#L35) | ko | 语音识别 | 2,774.3（已登记；[legacy](../catalog/legacy_multilingual.jsonl#L35)） | 有含标点版本 |
| [yodas_ru](../catalog/legacy_multilingual.jsonl#L39) | ru | 语音识别 | 5,596.0（已登记；[legacy](../catalog/legacy_multilingual.jsonl#L39)） | 有含标点版本 |

## 下载来源声明

以下条目来自下载计划，仅登记来源、版本和预期位置；这里不据此判断已下载或可训练。已有旧版的数据集也可能列有新版本下载计划。

| 数据集 | 版本 | 语言 | 支持任务 |
|---|---|---|---|
| [aishell5](../catalog/download_queue.jsonl#L1) | 1.0 | zh | 语音识别 |
| [common_voice_en](../catalog/download_queue.jsonl#L2) | 26.0 | en | 语音识别 |
| [common_voice_yue](../catalog/download_queue.jsonl#L5) | 26.0 | yue | 语音识别 |
| [common_voice_zh](../catalog/download_queue.jsonl#L3) | 26.0 | zh | 语音识别 |
| [common_voice_zh_hk](../catalog/download_queue.jsonl#L4) | 26.0 | yue | 语音识别 |
| [gigaspeech2](../catalog/download_queue.jsonl#L6) | hf-8dc0d0e502b7 | id、th、vi | 语音识别 |
| [granary](../catalog/download_queue.jsonl#L7) | hf-0fe23a860e35 | multi | 语音识别、语音翻译 |
| [lemas](../catalog/download_queue.jsonl#L9) | hf-91f0c1b9a29f | multi | 语音识别 |
| [omnilingual-asr-corpus](../catalog/download_queue.jsonl#L8) | hf-8648ba894637 | multi | 语音识别 |
| [reazonspeech](../catalog/download_queue.jsonl#L10) | hf-0df78f991f6a | ja | 语音识别 |

## 训练混合配方

这些配方复用上面的数据，不增加源数据集数量或时长。

- [icefall_v10_farfield_replay@prepared-20260908](../catalog/icefall_v10_replay.jsonl#L1)

## 已记录的质量证据

文件校验通过，不等于内容正确。以下仅列有明确记录的版本，缺少记录不代表质量差。

| 数据版本 | 当前结论 | 证据 | 注意事项 |
|---|---|---|---|
| [alimeeting@openslr-119-far-local-20260903](../catalog/alimeeting_far_raw.jsonl#L1) | 有已知标注问题 | 训练集 8 条标注越过音频边界；开发集 0 条；测试集 0 条 | 最大越界 269.375 秒，使用前应处理异常标注 |
| [commonvoice_en_clean@clean-v1-20260805](../catalog/local_lhotse_derived.jsonl#L8) | 有自动筛选记录 | 自动筛选通过 1,142,149 条、拒绝 1,127 条，通过率 99.90% | 未登记人工抽检；筛选通过不等于转写完全正确 |
| [wenetspeech@clean-weak-v1-20260904](../catalog/wenetspeech_weak.jsonl#L2) | 有自动筛选和人工抽检记录 | 自动筛选通过 3,149,292 条、拒绝 73,468 条，通过率 97.72% | 人工抽检 10 条，其中确认 10 条；样本很小，不能代表整集准确率 |

CV EN 的 train/test 清单落地差异见 [CV EN 清洗说明](cv-en-cleaning.md)。

## 数据声明与维护

- [目录说明](../catalog/README.md)：解释历史文件名、下载来源声明与框架适配记录。
- [组织规范](data-organization.md)：数据身份、版本、处理层与视图，与训练框架无关。
- 新增数据时登记任务、语言、特性和顶层 split 的 `statistics.duration_hours`；未知时长留空，不填 0。
- 更新 catalog 或 views 后运行 `audio-data-contract generate-overview`；CI 用 `--check` 检查本页同步。

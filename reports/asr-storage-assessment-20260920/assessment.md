# ASR 数据迁移：高速存储容量评估

调研日期：2026-09-20。统计单位：十进制 TB（1 TB = 10¹² bytes）。

**建议按 400 TB 可用高速存储做全量扩展预算，并选择能扩至 600 TB 的方案。** 如果只纳入下表的成熟公开语料范围，统一为 16 kHz、16-bit、单声道音频，首期约需 300 TB；如果使用 FLAC 等压缩训练音频，成熟范围可按 250 TB、扩展范围按 300 TB 评审。压缩方案的数字依赖实际压缩率和读取方式，不是实测结果。

用户已确定：**全量训练数据常驻高速存储，原始下载包放普通存储。** 因此高速层只保留训练需要的一份音频表示、标注、索引和工作空间；普通存储原始快照不计入本表。未执行下载、转码、迁移或删除。

| 范围 | 统一 PCM 音频方案：计算需求 | 建议可用容量 | FLAC 情景：计算需求 | 建议可用容量 |
|---|---:|---:|---:|---:|
| 核心规划范围：已识别主要源库 + 中小语料预留 | 290–297 TB | **300 TB** | 151–219 TB | **250 TB** |
| 扩展范围：再预留 YTC 抓取、MMS 采集候选、YODAS v3 当前文件 | 约 351 TB | **400 TB** | 最高约 273 TB | **300 TB** |

“核心”表示容量模型范围，不表示每个文件已验收或每个访问许可已具备。WorldSpeech 的部分音频需要从源 URL 获取；ReazonSpeech、部分 Hugging Face 库需同意访问条件。申请型资源已在状态列标注，不等于现在可以匿名下载全部文件。

400 TB 是平台提供给项目的**可用配额**，约 364 TiB。副本、纠删码、RAID 等物理冗余由平台另行折算；本评估未假设具体平台的冗余倍率或价格。

**调研范围与结果可信度**

本次从 OpenSLR 全目录、Hugging Face 官方发布者、Common Voice 官方版本库、项目已有 catalog，以及大规模数据论文和原作者仓库出发。交付包括：

- [容量与去重表](corpus-capacity.csv)：25 个可加总的源库/规划块，11 个汇编或派生归并块。
- [OpenSLR 目录发现表](openslr-directory.csv)：当日目录列出的 156 项资源，包括非 ASR 的软件、文本、音效和说话人数据。该表是目录级覆盖，**不是 156 个均可训练的 ASR 数据集**，也不是逐文件下载验收。
- [容量模型](capacity-model.json)：全部参数、合计、扩展预留与 YODAS v3 固定 revision 元数据。

不能证明覆盖“互联网上所有 ASR 数据”：不存在完整、稳定且无重复的总目录，小语种、新发布、机构申请及商业数据持续变化。这里是**主要公开来源的容量规划**，小型语料另外预留 3–6 万小时；这项预留是工程假设，不是剩余互联网数据的已知上界。未把只有论文、模型权重或商业宣传、没有明确可获取数据范围的训练规模直接加入总量。

来源事实、项目登记、规划假设分开使用；没有下载全库，也没有执行跨库音频指纹比对。网络可访问的发布页或文件树，不等于整库每个音频都能完整取得。

**本项目去重口径**

本次合入的 catalog 有 360 个版本、258 个原始 dataset_id；[项目总览](../../docs/data-overview.md)进一步把别名、版本和派生入口合并成 117 个数据集条目，另列 20 个下载来源声明和 1 个训练混合配方。这几个数字不是同一层级，不能当成相互独立的数据套数。

上次约 13.28 TB 是未完成文件索引的抽样估算加新增目录。其中已知压缩包约 5.45 TB；减去压缩包后的约 7.83 TB 仍只是当时已覆盖范围的非归档文件大小估计。它没有补齐未扫描文件、未完成下载和未配置根目录，**本次没有用 7.83 TB 作为整个现有训练库的精确基数**。

本次对账识别出约 **22.3 万小时的已登记同族参考范围**，主要是 Emilia、MLS、YODAS 部分语言、中文 WenetSpeech 系列和 GigaSpeech。它不是音频级唯一时长，也不证明与最新公开版本逐条匹配。下表的公开全量已经包含这些同族数据，**不会在公开全量之外再加一遍整个现有项目**。其余已登记小库由中小语料块覆盖；多通道、合成混音、业务数据及必要差异波形另预留 10 TB。

| 对账关系 | 容量处理 |
|---|---|
| 同一音频仅有清洗转写、标点、热词、时间戳或任务变化 | 音频一份，多个标注入口 |
| 语言子集、train/dev/test、嵌套 small/medium/large | 保留最大目标范围；不把父集和子集相加 |
| 已登记但仅是下载计划 | 标为计划，不能把整库当作已持有并抵扣 |
| 不同项目引用同一原始录音 | 依靠来源 ID、时间区间和清单关联归并；落地时仍需验证 |
| 已降噪、分离、变速、混音或改变声道的波形 | 不假定哈希相同；需要保留的差异版本占真实空间 |
| 都来自 YouTube、LibriVox 或议会录音，但没有匹配证据 | 不预扣猜测的重复比例，容量按保守方向估计 |

血缘去重是迁移方案中的存储组织方式，不能代替文件去重。特别是 LEMAS、VoxBox、Emilia-YODAS：如果坚持把各发布方的全部处理后波形也独立常驻，下面的“仅加标注”节省将不能全部实现，应在模型中追加相应实体文件。

**主要源库与项目映射**

小时数包含必要开发/测试划分或原始容器的规模预算，因此不是“可直接用于训练的高质量监督小时”。现有参考列只说明同族登记覆盖；“未抵扣”可能是没有登记、只登记下载计划，或登记缺少可比时长，均不能据此断言机器上绝无该数据。

| 源语料 / 规划块 | 全量预算小时 | 已登记同族参考小时 | 项目状态 |
|---|---:|---:|---|
| [YODAS / YODAS2](https://huggingface.co/datasets/espnet/yodas) | 369,510 | 19,006 | 部分语言已登记 |
| [VoxPopuli + MOSEL labels](https://github.com/hlt-mt/mosel) | 383,500 | 未抵扣 | 新增源音频 |
| [LibriHeavy / Libri-Light](https://github.com/k2-fsa/libriheavy) | 50,000–57,706 | 未抵扣 | 新增源音频 |
| [Raon-YouTube-Commons](https://huggingface.co/datasets/KRAFTON/Raon-OpenTTS-Pool) | 335,000 | 未抵扣 | 新增 |
| [Emilia 原版](https://github.com/open-mmlab/Amphion/tree/main/preprocessors/Emilia) | 101,654 | 86,405 | 部分已登记 |
| [Multilingual LibriSpeech 全8语](https://www.openslr.org/94/) | 50,687 | 48,721 | 大部分已登记 |
| [Common Voice SCS27 + SPS5](https://github.com/common-voice/cv-dataset) | 43,134 | 4,738 | 部分语言和旧版 |
| [WorldSpeech](https://huggingface.co/datasets/disco-eth/WorldSpeech) | 65,072 | 未抵扣 | 新增；部分需抓取音频 |
| [ReazonSpeech](https://huggingface.co/datasets/reazon-research/reazonspeech) | 35,000 | 未抵扣 | 计划登记；须同意访问条件 |
| [GigaSpeech2 raw](https://github.com/SpeechColab/GigaSpeech2) | 28,339 | 1,980 | 部分已登记 |
| [GigaSpeech XL](https://github.com/SpeechColab/GigaSpeech) | 10,051 | 10,051 | 已登记 |
| [WenetSpeech 有标注/弱标注](https://github.com/wenet-e2e/WenetSpeech) | 12,503 | 12,503 | 已登记 |
| [WenetSpeech-Yue](https://github.com/ASLP-lab/WenetSpeech-Yue) | 21,800 | 未抵扣 | 登记但缺时长 |
| [WenetSpeech-Chuan](https://github.com/ASLP-lab/WenetSpeech-Chuan) | 10,260 | 10,260 | 已登记 |
| [WenetSpeech-Wu](https://github.com/ASLP-lab/WenetSpeech-Wu-Repo) | 8,741 | 8,741 | 已登记 |
| [HiFiTTS-2](https://arxiv.org/abs/2506.04152) | 36,700 | 未抵扣 | 新增；有转写的TTS兼ASR来源 |
| [People's Speech](https://huggingface.co/datasets/MLCommons/peoples_speech) | 30,000–38,000 | 未抵扣 | 计划登记 |
| [Omnilingual ASR Corpus](https://huggingface.co/datasets/facebook/omnilingual-asr-corpus) | 3,350 | 未抵扣 | 计划登记 |
| [IndicVoices](https://huggingface.co/datasets/ai4bharat/IndicVoices) | 12,000 | 未抵扣 | 有登记但无总时长 |
| [Kathbath](https://huggingface.co/datasets/ai4bharat/Kathbath) | 1,684 | 未抵扣 | 新增；需同意访问条件 |
| [Shrutilipi](https://huggingface.co/datasets/ai4bharat/Shrutilipi) | 6,400 | 未抵扣 | 新增；需同意访问条件 |
| [WAXAL](https://huggingface.co/datasets/google/WaxalNLP) | 2,242 | 未抵扣 | 已登记但缺时长 |
| [FLEURS 全语种](https://huggingface.co/datasets/google/fleurs) | 2,000 | 120 | 部分语言已登记 |
| [本项目 LegCo](../../catalog/icefall_base.jsonl) | 20,477 | 20,477 | 本地登记参考 |
| [其余中小语料及目录覆盖预留](https://www.openslr.org/resources.php) | 30,000–60,000 | 未抵扣 | 规划预留，非实测合计 |
| **合计** | **1,670,103–1,715,809** | **约 223,001** | 目录归并后的规划口径 |

合计约 **167–172 万小时**，对应 16 kHz、16-bit、单声道 PCM 音频约 **192.4–197.7 TB**。同族参考相减约为 145–149 万小时的待补范围，但由于当前文件覆盖和跨版本对应不完整，**不能把这个差值作为精确新增下载量**。

几个影响数字的版本细节：

- [YODAS](https://huggingface.co/datasets/espnet/yodas)当前明确提供的 manual/automatic caption 部分为 369,510 小时；[YODAS2](https://huggingface.co/datasets/espnet/yodas2)说明与其同源，只改变长音频组织和采样率。没有把“500k+”整体规模全部视为已带转写的独立 ASR 小时。
- [Common Voice 官方版本库](https://github.com/common-voice/cv-dataset)已到 SCS v27、SPS v5：全部录音 42,593 + 541 小时，validated 为 29,295 + 302 小时。模型按全部录音留空间，但未验证录音不等于合格训练样本，历史版本不累加。
- [GigaSpeech2](https://github.com/SpeechColab/GigaSpeech2) raw 和 refined 重叠；[WenetSpeech](https://github.com/wenet-e2e/WenetSpeech)有高置信、弱标注和无标注划分，本模型没有再加入约 9,952 小时无标注音频。
- [WAXAL](https://huggingface.co/datasets/google/WaxalNLP)新 ASR v2 分割统计为 2,242 小时，v2 重划分同一批音频；旧介绍的约 1,250 小时不再额外累加。
- [WorldSpeech](https://huggingface.co/datasets/disco-eth/WorldSpeech)总计约 65,072 小时，但五个 RFA 配置仅有标注及 URL。全量预算纳入这些配置，实际获取结果仍需核验。
- [Omnilingual ASR Corpus](https://huggingface.co/datasets/facebook/omnilingual-asr-corpus)是 348 种语言的公开采集部分，约 3,350 小时；不能把模型训练时使用的私有或其他来源总时长当成这一个公开库。
- IndicVoices 按约 12,000 小时录音规模保守留空间，其可用转写比例须核对目标版本。未使用“有声学数据”直接推导“全部已带合格 ASR 标注”。

**不能再次累加的发布名称**

| 发布名称 | 常见宣传 / 发布规模 | 本次处理 |
|---|---:|---|
| [Granary](https://huggingface.co/datasets/nvidia/Granary) | 643,238 h | ASR/AST共用音频；回到YODAS/VoxPopuli/Libri-Light/YTC计数，合计表与分项不一致，不作为全库可加总时长 |
| [MOSEL](https://huggingface.co/datasets/FBK-MT/mosel) | 950,192 h | 950kh是汇总目录；自身主要发布转写，音频归入原始来源 |
| [LEMAS](https://arxiv.org/html/2601.04233v1) | 150,137 h | 论文明确来自GigaSpeech/GigaSpeech2/WenetSpeech4TTS/Emilia/MLS/mTEDx/Alcaim/Golos/YODAS；主要补充标注，差异波形另计 |
| [LoquaciousSet](https://huggingface.co/datasets/speechbrain/LoquaciousSet) | 25,000 h | 由LibriHeavy/YODAS/People's Speech/CV/VoxPopuli/LibriSpeech构成，不再加25kh音频 |
| [VoxBox](https://github.com/SparkAudio/VoxBox) | 102,500 h | 按源库归并，少量未覆盖子库在长尾预留中，不能额外加5.82TB |
| [Emilia-YODAS](https://github.com/open-mmlab/Amphion/tree/main/preprocessors/Emilia) | 113,900 h | 来源YODAS；只有改写标注不增加音频，降噪波形不能哈希等同原始音频 |
| [Raon-OpenTTS-Pool其他子库](https://huggingface.co/datasets/KRAFTON/Raon-OpenTTS-Pool) | 280,000 h | 全615kh仅335kh单列新来源；其余源库归并；Core不另计 |
| [YODAS-Granary](https://huggingface.co/datasets/espnet/yodas-granary) | 192,172 h | YODAS来源，AST是ASR过滤子集；不重复存带相同音频的两个任务 |
| [WenetSpeech4TTS](https://wenetspeech4tts.github.io/wenetspeech4tts/) | 12,800 h | 来源WenetSpeech；降噪/质量版本属于差异波形，计入10TB派生/多通道预算而非再算独立源语料 |
| [LibriSpeech / LibriTTS / LibriTTS-R](https://www.openslr.org/12/) | 960 h | 与MLS/Libri-Light同为LibriVox不是充分去重证据；独立所需音频留在长尾/派生预算，增强版不当成文件相同 |
| [SpeechMatrix / CoVoST2](https://github.com/facebookresearch/covost) | 多任务发布 | 只增加翻译标注时复用源音频；不把翻译任务小时再加一次 |

[LEMAS 论文的数据接入段落](https://arxiv.org/html/2601.04233v1)明确列出来源，因而本次把主要音频回归原始源库；Alcaim、Golos、mTEDx 等较小来源由中小语料预留覆盖。[VoxBox](https://github.com/SparkAudio/VoxBox)及 [LoquaciousSet](https://huggingface.co/datasets/speechbrain/LoquaciousSet)也公开了组成，不能在其源库之外再各加一整套。

Granary 的发布卡还存在数值口径问题：ASR 总数写约 643,238 小时，但当前分来源表列出的 192,172、206,116、122,475 和约 23,500 小时仅合计 544,263 小时。本评估不把这个不一致的总数用于相加，而回到可识别的原始来源计容量；AST 的约 351k 小时也不作为另一份音频。

中小语料预留涵盖以下需要继续逐库确认的来源，不把它们都宣称为已验收下载：TED-LIUM / mTEDx、SPGISpeech、Earnings21/22、Golos、Kazakh KSC/KSD、Samrómur、VoxForge、CORAA、Common Voice 未覆盖语言的独立小库、Zeroth-Korean、Pansori、OpenSLR 南亚及非洲语言系列、ASR 评测集，以及本项目现有 AISHELL、MAGICDATA、KeSpeech、MGB2、Bangla、KoreaSpeech 等未在大库行单列的范围。涉及机构申请或商业授权的版本须按实际获准范围重新定量。

**容量怎么算**

采用不依赖内容压缩率的 PCM 基准：

```text
每小时音频 = 16,000 samples/s × 2 bytes/sample × 1 channel × 3,600 s
           = 115,200,000 bytes = 0.0001152 TB

音频量 A = 目标小时 H × 0.0001152 TB/h

所需可用配额 Q = (A × 1.05 + 10 TB + 20 TB) / 0.80
```

| 参数 | 本次取值 | 属性 |
|---|---:|---|
| 音频采样规格 | 16 kHz、16-bit、单声道 | ASR 容量基准，不是所有上游文件的原格式 |
| 标注、清单、索引 | 音频量的 5% | 规划假设；包括多套文本标注 |
| 业务合成、多通道、需保留的差异波形 | 10 TB | 规划预留，非已完成全量实测 |
| 同时下载转换、重分片、质检工作空间 | 20 TB | 采用分批处理；不假设全库同时复制 |
| 最大规划使用率 | 80% | 留 20% 空闲用于运行和增长 |
| FLAC 大小 / PCM 大小 | 45%–70% | 仅情景假设；应以实际音频抽样压缩率替换 |

核心上限代入：`(197.661 × 1.05 + 10 + 20) / 0.8 = 296.93 TB`，故按 300 TB 立项。这里的 20% 空闲不是简单“再加 20%”，而是除以 0.8。

保留上游 Opus/MP3/FLAC 可以减少常驻空间；不建议为了凑容量统一进行新的有损压缩。高采样率、多声道必须按真实目标格式折算：24 kHz 单声道 PCM 是本基准的 1.5 倍；48 kHz 双声道是 6 倍。训练中解码成 float32 不代表一定要把 float32 波形写满磁盘。

**扩展范围为什么建议 400 TB**

| 扩展项 | 本次追加预留 | 不确定性 |
|---|---:|---|
| Granary 中 YouTube-Commons 音频抓取 | 上限 122,475 小时 ≈ 14.11 TB PCM | [官方下载指南](https://huggingface.co/datasets/nvidia/Granary/blob/main/Data_Downloading.md)明确原库只有文本/链接；与 Raon-YTC 的交集未核，不预先抵扣 |
| MMS 等多语种采集候选 | 44,700 小时 ≈ 5.15 TB PCM | 参考 [MMS 项目](https://github.com/facebookresearch/fairseq/tree/main/examples/mms)的采集候选预算，不是已确认可匿名下载的完整 ASR 包；不拿模型训练量当现成文件 |
| YODAS v3 当前固定 revision 文件 | **21.7627 TB，按原格式** | 文件已公开，但尚未核清 tar 内的转写与有效 ASR 时长，不按论文“百万小时”自动转成可训练量 |

YODAS v3 在 2026-09-20 查询时的 revision 为 `884cd1186d041d3783a7257e0d12e85ed13066d0`。对[该 revision 的官方文件树](https://huggingface.co/datasets/espnet/yodas3/tree/884cd1186d041d3783a7257e0d12e85ed13066d0)进行 3 页元数据汇总，得到 2,584 个文件、21,762,740,953,571 bytes，其中 2,582 个 tar。README 当时仅包含许可；没有据此认定包内没有转写，也没有认定所有音频已能用于 ASR。该数不是含历史对象的 `usedStorage`。

扩展上限：`((197.661 + 14.109 + 5.149 + 21.763) × 1.05 + 30) / 0.8 ≈ 350.77 TB`。取整并给尚未量化的版本变化留空间，建议 400 TB。FLAC 情景上限约 272.94 TB，建议 300 TB。

若后续 YODAS v3 全部纳入、需要解码为 PCM，应以核实后的有效时长重算，不能拿 21.76 TB 原格式包大小当解码后大小。每新增 100,000 小时，单份 PCM 音频增加 11.52 TB；加 5% 标注并维持 80% 使用率，需要再增加约 15.12 TB 可用配额。600 TB 是建议具备的扩容能力，不是对未来全网数据总量的保证。

**会使预算失效的额外常驻产物**

本表没有把每次实验的全库副本、全库 Hugging Face 转换缓存或全量离线声学特征重复算入。缓存应指向受控工作空间并按训练读取方式管理；训练分片是高速层主音频的一种容器形式，不必再同时保留逐文件解压副本。

例如全量离线保存 80 维、100 帧/秒、float32 的 fbank，每小时也约 115.2 MB：对核心上限就是另外约 197.7 TB，尚未算空闲与索引。若需要这种常驻特征，400 TB 方案必须重算。多套 checkpoint、实验日志和训练模型输出也应由训练平台单列配额。

**迁移前最后需要补齐的三项事实**

1. 固定本次实际要引入的源库版本与访问资格，核对 URL-only 数据的音频获取结果；把模型中的 3–6 万小时预留替换成选定小库实数。
2. 完成当前 catalog 的文件依赖扫描，并对有血缘的跨库条目核对来源 ID / 时间区间；仅在验证后宣称具体节省了多少重复文件。
3. 对代表性训练音频验证目标格式和读取吞吐，再决定采用 PCM 还是压缩音频档位。压缩方案的 45%–70% 参数尤其需要实测。

本报告区分了来源事实、项目登记和规划假设。最终建议是预算用的容量区间，不是已经完成全网下载、文件级去重后的精确磁盘清单。

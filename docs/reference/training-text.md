# 训练文本规范（终版 v4）

适用于 open-audio-llm 训练用的中文、英文和西语训练文本（中英最早按交付配方 v7set34 建，西语见[西语（es-v1）](#西语es-v1)）。各轮文本修正都按这份规范执行，并合进同一个终版。训练时每个来源只用它的终版，范围见[使用范围](#使用范围)。

- **终版版本名**：v1 是 `<配方原来用的版本>-final-v1-20261120`，登记在 `catalog/text_final_v1.yaml`，生成脚本是 `scripts/text_final/build.py`。v2（2026-11-23）是 `<配方原来用的版本>-final-v2-20261123`，在 v1 上加规则 7（空格），另含没有 v1 的朗读语料，登记在 `catalog/text_final_v2.yaml`，生成脚本是 `scripts/text_final/build_v2.py`，见[终版 v2](#终版-v2)。规则改不到的来源不建 v2，v1 仍是终版；建了 v2 的 v1 写 `superseded_by` 指向 v2。v3（2026-11-24）是 `<配方原来用的版本>-final-v3-20261124`，在 v2 上加规则 8（拉丁文括注），目前只有 `fleurs_zh`，登记在 `catalog/text_final_v3.yaml`，生成脚本是 `scripts/text_final/build_v3.py`，见[终版 v3](#终版-v3)。v4（2026-11-27）是 `<配方原来用的版本>-final-v4-20261127`，在各来源最新终版上加规则 9（数字写成阿拉伯数字），登记在 `catalog/text_final_v4.yaml`，生成脚本是 `scripts/text_final/build_v4.py`，见[终版 v4](#终版-v4)。**查终版时按 `superseded_by` 跳到最后一个版本。**
- **做法**：从每个来源已登记的修正版本里最深的那个出发，再把下表中适用的规则补齐。规则没有改动的文本文件和录音、音频都引用原文件，不复制。
- **以后增加规则**：先把规则写进本文，再在当前终版上补做新规则，建下一版（`-final-v5-<日期>`），并在上一版的登记里写 `superseded_by`。不要在终版上再派生一层修正后缀。
- **切换到终版时检查记录名单**：大多数来源的记录 ID 是 `<split>:<id>`，与版本无关，`include_records` / `exclude_records` 名单可以照搬。从 Lhotse cut 构建的来源（如 `wenetspeech_clean`）的记录 ID 是 `<dataset_id>@<版本>:<split>:<id>`，带版本号；按旧版本写的名单在终版上一条也匹配不上，会报 `Empty source`。这类名单要把前缀换成终版版本号。只做 dry-run 发现不了这个问题，要真正加载才会报错。v7set34 的名单都不带版本号，不受影响。

## 规则

| # | 规则 | 适用范围 | 执行方式 |
|---|---|---|---|
| 1 | 中文书面化标点：按 GB/T 15834，只插入标点、不改字；只用全角 `，。？！、：；“”《》`；每条以 `。？！` 结尾；逗号从紧，只加在语法需要的地方 | 中文全部来源 | amphiondata `enrichment/written_punctuation.py`，学生模型 punc-student-v1；配方版本 `train-punc-v1-20261102`、`-punc-20261102`、场景池 `-punchw-20261102` 已含 |
| 2 | 英文标点和大小写（en-v1）：只插入 `, . ? ! ; :`，句首、I、专名、缩写大写，不改词；每条以 `. ? !` 结尾 | 英文全部来源 | amphiondata `enrichment/written_punctuation_en.py`；配方版本 `train-punc-v1-20261102`、场景池 `-punchw2-20261102` 已含 |
| 3 | 说字写法：说话人讲某个字怎么写（组词、拆字、偏旁、否定对比），标注却写成同音别字的，按说明改正；拿不准的窗口整窗去掉 | 中文自发语音来源 | 判定 `context_correction_clean_zh@v1-20261110`，脚本 `scripts/context_correction/`；派生版本 `-ctxclean-20261110` |
| 4 | 英文按原文写，不音译、不意译（中英规范规则 1） | WenetSpeech 训练集 | `zhen-fix-en-v1`：whisper-large-v3 和强制中文的 Qwen3-ASR 都听出同一个英文，且标注片段是意译或生造的音译才改；通行的人名、地名译名和外来词不改。脚本 `scripts/zhen_fix/build_wenetspeech.py` |
| 5 | 字母缩写连写、大写（中英规范规则 2）：用空格隔开的单个大写字母连起来，K T V→KTV | 含中文的全部文本 | `zhen-fix-v1`（`scripts/zhen_fix/build.py` 的 `fix`）；终版对全部来源补齐 |
| 6 | 去掉评测录音 | WenetSpeech、Emilia2 混音和对话 | 随规则 3 一起执行：去掉 context_correction_zh 评测录音、ts_asr_real 留出录音 |
| 7 | 空格（中英规范规则 5）：英文词之间留一个空格，汉字之间、汉字和英文之间都不加空格 | 含汉字的全部文本 | v2（`build_v2.py` 的 `rule5`）：连续空白压成一个空格；紧挨汉字、假名或全角符号一侧的空格删掉；两侧都是英文、数字或半角符号的空格保留。只处理含汉字的文本，纯英文句子不动。v2 对全部训练划分执行（含 v7set34 以外的划分），同时补做规则 5 |
| 8 | 中文文本里的拉丁文括注（括号里有拉丁字母、没有汉字，如“孙德尔本斯（Sundarbans）”）：朗读人没读的整段删掉，读了的只去括号、保留内容（再按规则 7 处理空格） | FLEURS 中文训练集 | v3（`build_v3.py`）：每条录音逐处判断，whisper-large-v3（语种 zh）写出括注里的字母，或 whisper 和 Qwen3-ASR-1.7B 都在括注处多出一段音译汉字，算读了；两个 ASR 写出的括注逐处人工复核。Qwen3-ASR 单独写出括注不算证据，它会复现 FLEURS 的括注写法。issue #299 |
| 9 | 数字写成阿拉伯数字（中英规范规则 3 扩展到全部数字；只改数字，其他字不动）：10 及以上的数、逐位读的数字串（年份、电话、证件号、车牌）、挨着字母的数字（5G、A4、H265）、小数、百分数（50%）、日期里的月和日、钟点改成阿拉伯数字；一位数的计数和序数（三个人、第一次）、概数（三四个、十几个）、分数、星期和农历、固定词和成语（一下、十分、千万、五四运动、三点一线、十三香）、约定写汉字的专名（春风十里、降龙十八掌、十八大、十八届三中全会、十二指肠、十里堡）、说一个字怎么写的（数字一百的百）保留汉字 | 含汉字的全部训练文本 | v4（`build_v4.py`，规则 `scripts/text_final/zh_numbers.py`，zh-num-v1）。参照 GB/T 15835-2011；同一行的场景文本和上下文纠偏标签（`labels.context_correction`）跟着改，热词表的词各自转换（原样出现在 target 里的不动）。评测参考文本不改写，打分时两边统一，见[终版 v4](#终版-v4) |

中英写法的细则和评测口径见 [zh-en-transcription.md](zh-en-transcription.md)。

## 没有执行或只部分执行的

| 项目 | 现状 | 原因 |
|---|---|---|
| 英文写成汉字（规则 4） | 只做了 WenetSpeech，改 3,727 条；估计全量约 1.4 万条 | 剩下约 1 万条拿不准：通行译名两种读法相近，三个音频大模型（豆包 seed-2.1-lite、qwen3.8-omni-flash、qwen3.5-omni-plus）的判断互相矛盾，没有可靠的核对方 |
| 繁简统一、去掉非语音标记（中英规范规则 6、7） | 繁简没有统计；非语音标记（`<…>`、`[UNK]`、`**`）终版里有 77 条，在 Emilia2 三个来源 | 评测集版本已处理；训练文本数量很少，暂不处理 |
| 括号里夹着汉字的拉丁文括注（规则 8 以外） | `fleurs_zh` 训练集 7 种、12 处，如“（EVA，俗称“太空漫步”）”“（复数为Kalaallit）”“（荷兰语：Grachtengordel）” | 中文部分多半读了，删整段会删掉读了的字；数量少，暂不处理 |
| FLEURS 中文正文里的外文没读或改读汉字 | `fleurs_zh` 训练集括号外的拉丁字母词，whisper 有 36/216 没写出：读成音译（La Leona→拉里奥纳、eBay→易贝）或跳过（Siriporn、Zoungla） | 每个朗读人读法不同，要逐条按音频改写，不是统一规则能处理的；只在 FLEURS 上明显 |
| 其他来源的拉丁文括注、`(SIL)` 静音标记 | issue #299 报告：Emilia 中文约 0.04% 带拉丁文括注，多是“信息通信技术（ICT）”这类缩写；AliMeeting、`ts_real_train` 约 30 条带 `(SIL)` | 缩写多半读了，不批量删；`(SIL)` 属于非语音标记，和上面“繁简统一、去掉非语音标记”一起处理 |

## 各来源的终版（v1）

所有终版的标点（规则 1、2）都已由配方版本带上。"已含修正"列出起点版本上已经做过的修正；"本次补齐连写"是终版新改的条数。最后两列只统计、不修，按配方实际训练的划分计。

| 终版 | 起点（配方版本之后） | 已含修正 | 本次补齐连写 | 汉字和英文之间有空格 | 非语音标记 |
|---|---|---|---:|---:|---:|
| `aishellmix@pack3-current-audio-record-20260910-punc-20261102-final-v1-20261120` | `（配方版本本身）` | — | 0 | 0 | 0 |
| `librimix@960-current-audio-record-20260910-punc-20261102-final-v1-20261120` | `（配方版本本身）` | — | 0 | 0 | 0 |
| `ts_scene_pool@hard-20261016-punchw-20261102-final-v1-20261120` | `（配方版本本身）` | — | 0 | 1 | 0 |
| `ts_scene_pool@hard-20261016-punchw2-20261102-final-v1-20261120` | `（配方版本本身）` | — | 0 | 0 | 0 |
| `emilia2_mix@mix-20261013-utts-final-v1-20261120` | `-ctxclean-20261110-zhenfix-20261117` | 说字写法、字母连写 | 0 | 59,037 | 29 |
| `emilia2_dialog@dialog-turn-taking-20261013-enroll-final-v1-20261120` | `-ctxclean-20261110-zhenfix-20261117` | 说字写法、字母连写 | 0 | 23,768 | 14 |
| `alimeeting_sdm@turn-taking-20261014-utts-punc-20261102-final-v1-20261120` | `（配方版本本身）` | — | 0 | 0 | 0 |
| `aishell4@turn-taking-20261014-utts-punc-20261102-final-v1-20261120` | `-ctxclean-20261110-zhenfix-20261117` | 说字写法、字母连写 | 0 | 6 | 0 |
| `ami_sdm@turn-taking-20261014-utts-punc-20261102-final-v1-20261120` | `（配方版本本身）` | — | 0 | 0 | 0 |
| `magicdata_ramc@turn-taking-20261014-utts-punc-20261102-final-v1-20261120` | `-ctxclean-20261110-zhenfix-20261117` | 说字写法、字母连写 | 0 | 16 | 0 |
| `chime6@turn-taking-20261014-final-v1-20261120` | `（配方版本本身）` | — | 0 | 0 | 0 |
| `gigaspeech@train-punc-v1-20261102-final-v1-20261120` | `（配方版本本身）` | — | 0 | 0 | 0 |
| `wenetspeech_clean@train-punc-v1-20261102-final-v1-20261120` | `-ctxclean-20261110-zhenfix-20261119` | 说字写法、英文写回 | 0 | 0 | 0 |
| `emilia2_short@short-lance-20261023-final-v1-20261120` | `-ctxclean-20261110-zhenfix-20261117` | 说字写法、字母连写 | 0 | 42,867 | 34 |
| `common_voice_en@train-punc-v1-20261102-final-v1-20261120` | `（配方版本本身）` | — | 0 | 0 | 0 |
| `kespeech@train-punc-v1-20261102-final-v1-20261120` | `（配方版本本身）` | — | 0 | 0 | 0 |
| `police_asr_unified@train-punc-v1-20261102-final-v1-20261120` | `-zhenfix-20261117` | 字母连写 | 0 | 15,032 | 0 |
| `police_terms_single_train@train-punc-v1-20261102-final-v1-20261120` | `（配方版本本身）` | — | 0 | 0 | 0 |
| `police_terms_single_train@hotwords-confusable-v1-20261102-final-v1-20261120` | `（配方版本本身）` | — | 0 | 0 | 0 |
| `vitw@2m-20261013-final-v1-20261120` | `-ctxclean-20261110` | 说字写法 | 0 | 0 | 0 |
| `aishell2@train-punc-v1-20261102-final-v1-20261120` | `（配方版本本身）` | — | 45 | 52 | 0 |
| `librispeech@train-punc-v1-20261102-final-v1-20261120` | `（配方版本本身）` | — | 0 | 0 | 0 |
| `alimeeting_sdm@asr-20261014-punc-20261102-final-v1-20261120` | `（配方版本本身）` | — | 0 | 0 | 0 |
| `aishell4@asr-20261014-punc-20261102-final-v1-20261120` | `-ctxclean-20261110-zhenfix-20261117` | 说字写法、字母连写 | 0 | 7 | 0 |
| `threed_speaker_zh_far_asr@train-punc-v1-20261102-final-v1-20261120` | `（配方版本本身）` | — | 0 | 688 | 0 |
| `ami_sdm@asr-20261014-punc-20261102-final-v1-20261120` | `（配方版本本身）` | — | 0 | 0 | 0 |
| `magicdata_ramc@train-punc-v1-20261102-final-v1-20261120` | `-ctxclean-20261110-zhenfix-20261117` | 说字写法、字母连写 | 0 | 20 | 0 |
| `magicdata_ramc@allspk-asr-v1-20261103-final-v1-20261120` | `-zhenfix-20261117` | 字母连写 | 0 | 14 | 0 |
| `aishell4@allspk-asr-v1-20261103-final-v1-20261120` | `（配方版本本身）` | — | 97 | 4 | 0 |
| `alimeeting_sdm@allspk-asr-v1-20261103-final-v1-20261120` | `（配方版本本身）` | — | 0 | 0 | 0 |
| `magicdata_ramc@allspk-ts-v1-20261104-final-v1-20261120` | `-zhenfix-20261117` | 字母连写 | 0 | 7 | 0 |
| `aishell4@allspk-ts-v1-20261104-final-v1-20261120` | `（配方版本本身）` | — | 45 | 3 | 0 |
| `alimeeting_sdm@allspk-ts-v1-20261104-final-v1-20261120` | `（配方版本本身）` | — | 0 | 0 | 0 |
| `common_voice_zh@train-punc-v1-20261102-final-v1-20261120` | `（配方版本本身）` | — | 0 | 0 | 0 |
| `fleurs_zh@legacy-20260804-final-v1-20261120` | `（配方版本本身）` | — | 2 | 164 | 0 |
| `fleurs_en@legacy-final-v1-20261120` | `（配方版本本身）` | — | 0 | 0 | 0 |
| `ts_nonspeech_pool@v1-20261016-final-v1-20261120` | `（配方版本本身）` | — | 0 | 0 | 0 |
| `ts_nonspeech_pool@babble-20261024-final-v1-20261120` | `（配方版本本身）` | — | 0 | 0 | 0 |
| `asr_babble_speech_pool@v1-20261024-punc-20261102-final-v1-20261120` | `（配方版本本身）` | — | 0 | 0 | 0 |
| `asr_distant_talk_pool@v1-20261102-punc-20261102-final-v1-20261120` | `（配方版本本身）` | — | 0 | 0 | 0 |
| `asr_distant_talk_pool@v1-20261102-final-v1-20261120` | `（配方版本本身）` | — | 0 | 0 | 0 |
| `hw_sft@hw-20261014-final-v1-20261120` | `（配方版本本身）` | — | 4 | 0 | 0 |
| `hard_hw_sft@hard-20261014-final-v1-20261120` | `（配方版本本身）` | — | 0 | 0 | 0 |
| `ts_scene_pool@multi-20261017-punchw-20261102-final-v1-20261120` | `（配方版本本身）` | — | 5 | 13 | 0 |
| `ts_scene_pool@multi-20261017-punchw2-20261102-final-v1-20261120` | `（配方版本本身）` | — | 0 | 0 | 0 |
| `ts_real_train@v1-20261017-utts-punc-20261102-final-v1-20261120` | `（配方版本本身）` | — | 0 | 0 | 0 |
| `ts_real_train@v2-20261018-utts-punc-20261102-final-v1-20261120` | `（配方版本本身）` | — | 0 | 0 | 0 |
| `ts_real_train@v3-20261020-utts-punc-20261102-final-v1-20261120` | `（配方版本本身）` | — | 0 | 0 | 0 |
| `ts_real_train@en-v1-20261101-utts-punc-20261102-final-v1-20261120` | `（配方版本本身）` | — | 0 | 0 | 0 |
| `ts_real_train@en-v1-20261101-utts-final-v1-20261120` | `（配方版本本身）` | — | 0 | 0 | 0 |
| `ts_scene_pool@alt-twins-20261024-punchw-20261102-final-v1-20261120` | `（配方版本本身）` | — | 6 | 3 | 0 |
| `ts_scene_pool@alt-twins-20261024-punchw2-20261102-final-v1-20261120` | `（配方版本本身）` | — | 0 | 0 | 0 |
| `ts_scene_pool@solo-20261020-punchw-20261102-final-v1-20261120` | `（配方版本本身）` | — | 0 | 1 | 0 |
| `ts_scene_pool@solo-20261020-punchw2-20261102-final-v1-20261120` | `（配方版本本身）` | — | 0 | 0 | 0 |
| `ts_scene_pool@handover-20261021-punchw-20261102-final-v1-20261120` | `（配方版本本身）` | — | 2 | 1 | 0 |
| `ts_scene_pool@handover-20261021-punchw2-20261102-final-v1-20261120` | `（配方版本本身）` | — | 0 | 0 | 0 |
| `ts_scene_pool@xsession-near-20261023-punchw-20261102-final-v1-20261120` | `（配方版本本身）` | — | 0 | 0 | 0 |
| `ts_scene_pool@xsession-alt-twins-20261024-punchw-20261102-final-v1-20261120` | `（配方版本本身）` | — | 0 | 0 | 0 |
| `ts_scene_pool@xsession-hard-20261023-punchw-20261102-final-v1-20261120` | `（配方版本本身）` | — | 0 | 0 | 0 |
| `ts_scene_pool@xsession-handover-20261023-punchw-20261102-final-v1-20261120` | `（配方版本本身）` | — | 0 | 0 | 0 |
| `ts_scene_pool@magicdata-near-20261023-punchw-20261102-final-v1-20261120` | `（配方版本本身）` | — | 5 | 0 | 0 |
| `ts_scene_pool@magicdata-alt-twins-20261024-punchw-20261102-final-v1-20261120` | `（配方版本本身）` | — | 2 | 0 | 0 |
| `ts_scene_pool@magicdata-hard-20261023-punchw-20261102-final-v1-20261120` | `（配方版本本身）` | — | 0 | 0 | 0 |
| `ts_scene_pool@magicdata-handover-20261023-punchw-20261102-final-v1-20261120` | `（配方版本本身）` | — | 0 | 0 | 0 |
| `ts_scene_pool@cvaccent-near-20261101-punchw2-20261102-final-v1-20261120` | `（配方版本本身）` | — | 0 | 0 | 0 |
| `ts_scene_pool@cvaccent-alt-twins-20261101-punchw2-20261102-final-v1-20261120` | `（配方版本本身）` | — | 0 | 0 | 0 |
| `ts_scene_pool@cvaccent-hard-20261101-punchw2-20261102-final-v1-20261120` | `（配方版本本身）` | — | 0 | 0 | 0 |
| `ts_scene_pool@cvaccent-handover-20261101-punchw2-20261102-final-v1-20261120` | `（配方版本本身）` | — | 0 | 0 | 0 |
| `ts_scene_pool@cvaccent-solo-20261101-punchw2-20261102-final-v1-20261120` | `（配方版本本身）` | — | 0 | 0 | 0 |
| `ts_scene_pool@csd-near-20261101-punchw2-20261102-final-v1-20261120` | `（配方版本本身）` | — | 0 | 0 | 0 |
| `ts_scene_pool@csd-alt-twins-20261101-punchw2-20261102-final-v1-20261120` | `（配方版本本身）` | — | 0 | 0 | 0 |
| `ts_scene_pool@csd-hard-20261101-punchw2-20261102-final-v1-20261120` | `（配方版本本身）` | — | 0 | 0 | 0 |
| `ts_scene_pool@csd-handover-20261101-punchw2-20261102-final-v1-20261120` | `（配方版本本身）` | — | 0 | 0 | 0 |
| `ts_scene_pool@csd-solo-20261101-punchw2-20261102-final-v1-20261120` | `（配方版本本身）` | — | 0 | 0 | 0 |
| **合计** | | | **213** | **141,704** | **77** |

## 终版 v2

2026-11-23 起。需求来自 open-audio-llm（用户要求训练文本按规范统一空格，并补上没有终版的朗读语料）。

- **规则 7（空格）**：在 v1 终版上补做，对全部训练划分执行（含 v7set34 以外的划分，这些划分同时补做规则 5 字母连写）。英文词之间的空格数量改前改后相同（逐行核对）；场景文本 `metadata.scene.targets[].text` 和热词列表跟着目标一起改。纯英文句子不动，所以 csd 英文场景池等没有 v2。
- **新建朗读语料**：AISHELL-1（`aishell`）、AISHELL-3（`aishell3`）、MagicData 朗读集（`magicdata`）的 train 划分以前没有终版。v2 按 id 套用书面化标点（规则 1；aishell `punc-written-v1-20261029`、magicdata `punc-written-v1-20261102`、aishell3 `punc-written-v1-20261123` 本次新跑），去掉标点、空格和大小写后与原文一致才换，再做规则 7 和规则 5。
- **没有 v2 的 v1 终版仍是终版**；有 v2 的 v1 写了 `superseded_by`。

| 终版 v2 | 书面化标点 | 空格（规则 7） | 字母连写 |
|---|---:|---:|---:|
| `magicdata@legacy-20260804-final-v2-20261123` | 573,477 | 2,708 | 5 |
| `aishell@legacy-20260804-final-v2-20261123` | 120,098 | 0 | 0 |
| `aishell3@legacy-20260804-final-v2-20261123` | 63,262 | 0 | 0 |
| `emilia2_mix@mix-20261013-utts-final-v2-20261123` | 0 | 63,829 | 0 |
| `emilia2_short@short-lance-20261023-final-v2-20261123` | 0 | 44,876 | 0 |
| `emilia2_dialog@dialog-turn-taking-20261013-enroll-final-v2-20261123` | 0 | 44,573 | 0 |
| `police_asr_unified@train-punc-v1-20261102-final-v2-20261123` | 0 | 15,371 | 0 |
| `hw_sft@hw-20261014-final-v2-20261123` | 0 | 2,865 | 4 |
| `fleurs_zh@legacy-20260804-final-v2-20261123` | 0 | 1,005 | 0 |
| `ts_scene_pool@magicdata-near-20261023-punchw-20261102-final-v2-20261123` | 0 | 819 | 0 |
| `threed_speaker_zh_far_asr@train-punc-v1-20261102-final-v2-20261123` | 0 | 799 | 0 |
| `aishell4@asr-20261014-punc-20261102-final-v2-20261123` | 0 | 347 | 0 |
| `aishell4@turn-taking-20261014-utts-punc-20261102-final-v2-20261123` | 0 | 304 | 0 |
| `ts_scene_pool@magicdata-alt-twins-20261024-punchw-20261102-final-v2-20261123` | 0 | 241 | 0 |
| `aishell2@train-punc-v1-20261102-final-v2-20261123` | 0 | 215 | 0 |
| `ts_scene_pool@magicdata-handover-20261023-punchw-20261102-final-v2-20261123` | 0 | 166 | 0 |
| `aishell4@allspk-asr-v1-20261103-final-v2-20261123` | 0 | 156 | 0 |
| `magicdata_ramc@turn-taking-20261014-utts-punc-20261102-final-v2-20261123` | 0 | 100 | 0 |
| `magicdata_ramc@train-punc-v1-20261102-final-v2-20261123` | 0 | 99 | 0 |
| `ts_scene_pool@magicdata-hard-20261023-punchw-20261102-final-v2-20261123` | 0 | 82 | 0 |
| `magicdata_ramc@allspk-asr-v1-20261103-final-v2-20261123` | 0 | 73 | 0 |
| `aishell4@allspk-ts-v1-20261104-final-v2-20261123` | 0 | 63 | 0 |
| `ts_scene_pool@multi-20261017-punchw-20261102-final-v2-20261123` | 0 | 49 | 0 |
| `magicdata_ramc@allspk-ts-v1-20261104-final-v2-20261123` | 0 | 35 | 0 |
| `ts_scene_pool@alt-twins-20261024-punchw-20261102-final-v2-20261123` | 0 | 24 | 0 |
| `hard_hw_sft@hard-20261014-final-v2-20261123` | 0 | 13 | 0 |
| `wenetspeech_clean@train-punc-v1-20261102-final-v2-20261123` | 0 | 8 | 0 |
| `ts_scene_pool@handover-20261021-punchw-20261102-final-v2-20261123` | 0 | 8 | 0 |
| `ts_scene_pool@hard-20261016-punchw-20261102-final-v2-20261123` | 0 | 5 | 0 |
| `ts_scene_pool@solo-20261020-punchw-20261102-final-v2-20261123` | 0 | 4 | 0 |
| **合计** | **756,837** | **178,837** | **9** |

## 终版 v3

2026-11-24 起。需求来自 open-audio-llm（issue #299）：`fleurs_zh` 训练文本有 12.6% 带音频里没读的拉丁文括注，训练后的模型在 FLEURS 中文测试集上凭空输出括注（945 条里 49 条，原版 Qwen3-ASR 11 条），字错率 4.10，只删掉输出里的括注就降到 3.04。

- **规则 8（拉丁文括注）**：在 v2 终版上补做，只有 `fleurs_zh` train 有成批的这类括注。FLEURS 每句约由 3 人朗读，同一句不同人读法不同，所以按录音逐处判断，判定在运行目录 `v3/decisions.json`。
- **结果**：3,246 条里改 399 条，共 559 处括注：没读、整段删掉 480 处（86%），读了、只去括号 79 处（如“汉密尔顿Hamilton”“格林尼治时间GMT”“11:00 UTC+1左右”）。汉字一个不变（逐条核对）。dev、test 划分不动。
- **判定依据**：whisper 写出字母 63 处；两个 ASR 都在括注处多出音译汉字 11 处（如“费卢杰费卢贾”“比达尔歪掉”）；人工复核改判 13 处（字母巧合配上、只读一遍分不出中英文的按没读；英文被写成汉字“齐奥”、被写成“Marinette”的按读了）。抽查两个 ASR 都没写出的 30 处，29 处确实没读，剩下 1 处（Fallujah）已由音译汉字的判法补上。
- **范围以外**：括号里夹着汉字的括注、正文里没读的外文、其他来源的缩写括注，见[没有执行或只部分执行的](#没有执行或只部分执行的)。`fleurs_en`、`fleurs_es` 的括号内容是读出来的，不删。
- `fleurs_zh@legacy-20260804-final-v2-20261123` 写了 `superseded_by` 指向 v3。

### 英文榜单版新增来源（2026-11-25）

open-audio-llm A 线（英文榜单版，open-audio-llm PR #174）用的新英文来源，没有旧版本，直接按 v3 建终版，版本名 `<源版本>-final-v3-20261125`，登记在 `catalog/text_final_v3.yaml`，生成脚本在 `scripts/text_final/en_board/`。记录格式与 `ami_sdm@asr-20261014` 相同（audio-record/1.0 加音频索引），时长 0.5–30 秒。

| 版本 | 划分 | 文本来源 |
|---|---|---|
| `earnings22@github-c05ab6fd8b4b-final-v3-20261125` | train、dev | `nlp_references` 的书面写法，时间取 `force_aligned_nlp_references` |
| `voxpopuli_en@hf-42f01879c780-final-v3-20261125` | train | `raw_text`；为空的 2.9% 用 `normalized_text` 经 en-v1 学生模型补标点和大小写 |
| `ami_ihm@hf-edinburghcstr-20261023-final-v3-20261125` | train | Kaldi 全大写文本经 en-v1 学生模型补标点和大小写 |
| `earnings21@github-c05ab6fd8b4b-final-v3-20261125` | test | `nlp_references` 的书面写法，时间由 `earnings21_align.py` 自己对齐 |
| `spgispeech2@hf-f4ce91de393c-final-v3-20261125` | train、dev、test | `raw_transcript`（S&P Global 专业转写，非逐字），时间取官方词级对齐 |

- **Earnings-22**：
  - 排除 Open ASR 榜单测试用的 6 场；按口音组各取 1 场，共 4 场作 dev。
  - 强制对齐表把实体换成了读法（MTN→`M T N`、2019→`twenty nineteen`），所以文本用参考转写，两表按单元匹配后只取时间；口语重复和 uh/um 保留。
  - 官方对齐有 28% 的词没有时间，对齐失败区域里零星对上的词时间常常放错。处理方法：整场跳过未对齐 ≥40% 的 32 场；其余段用 whisper-large-v3 核对，归一化后 WER > 0.5 的丢掉（23%）。人工看被拒样本，估计误杀约 8%。
  - 结果：train 65.7 h、dev 1.9 h，保留段上 whisper WER 为 10.3%。
- **VoxPopuli 英文**：
  - `raw_text` 按规则 2 只补句首大写和句末标点，不改词。
  - 源文本丢了开引号，留下 2,194 处孤立闭引号（`the word dignity'`），已删掉；s 后面的 `'` 可能是复数所有格，保留。
  - 学生模型输出改了词的 90 条，只补句末标点，保持小写。
  - 超过 30 秒的 1,432 条（14.7 h）没有词级时间，切不开，不收。
  - 结果：train 181,050 条、508.0 h。
  - 抽 300 条 whisper 核对：3% 是 whisper 幻觉（整段输出 “Thank you very much.”，截短后能正确识别），去掉后 WER 6.9%。
- **AMI 近讲**：
  - 人工标注，词、口语重复和半截词都保留，不按 whisper 丢弃。
  - 学生模型保留原词的占 99.9%。
  - 不足 0.5 秒的 22,081 条（1.95 h，几乎都是单字附和）不收；0.5 秒以上的单字附和仍有 1.3 万条。
  - 结果：train 86,417 条、75.9 h。
  - 抽 300 条 whisper 核对：WER 18.7%，其中不足 1 秒的段 43%、5 秒以上 16.5%。差异主要来自 whisper 删掉了重复和 uh，以及近讲话筒串进旁人的声音。
- **Earnings-21**（只作 test）：
  - 参考转写没有时间，自己对齐：
    - whisper-large-v3 按 30 秒窗口识别，Qwen3-ForcedAligner 给识别结果打时间，作为锚点；
    - 在锚点之间的停顿处把会议切成不超过 60 秒的块；
    - 每块用 Qwen3-ForcedAligner 对齐参考转写。
  - whisper 只决定块的边界，所以哪些词有时间与 whisper 认不认得出无关。可对齐的 361,243 个词全部有时间。
  - 切句规则与 Earnings-22 相同。不足 0.5 秒的 360 段（几乎都是 yeah、okay 这类单字）不收。
  - 不按 whisper 丢段，每段的 whisper WER 记在 `metadata.whisper_wer`。WER > 0.5 的有 420 段（0.3 h），按词数分档各看 22 条，约三到五成是 whisper 自己的错（省掉重复、幻觉、听错）。测试集不能按某一个 ASR 认不认得出来挑段，所以只作标记。
  - 源转写里有少量标点和大小写错位一格的地方（如 `Go. ahead`），每场最多 2.4%，Earnings-22 也一样，保持原样。
  - 结果：test 9,466 段、36.2 h，whisper WER 10.2%。
- **SPGISpeech 2.0**：
  - 文本特点：S&P Global 的转写是书面写法，删了口吃和大部分语气词，不是逐字稿，与上面几个来源的“口语重复保留”不同。
  - 切法：原始片段 50–90 秒，按官方词级对齐切成 30 秒以内的单说话人短句。对齐文件把 `U.S.`、`long-term`、`1.5` 拆开写，两边都拆成字母数字再匹配，词全部有时间。
  - 片段边缘可能被截断的首尾词不进文本。
  - 对齐常让相邻词的时间重叠，Earnings 用的“窗口压到别的词就丢”的规则在这里误杀为主（被丢的样本 60 段里 49 段 whisper WER ≤ 0.2），不用。改为丢掉每秒超过 8 个词的段：这些是对齐把一串词挤进很短时间的地方，样本 40 段里 39 段 WER > 0.5。
  - 结果：train 877,748 段、3,106 h，dev 34,647 段、122.8 h，test 38,744 段、137.4 h。whisper 各抽 300 段，WER 5.9–6.7%。
  - 与 Open ASR 榜单的 SPGISpeech 1.0 test 没有同一录音。有 669 条 1.0 test 句子的文本近乎原样出现在 2.0 里，多是主持人结束语和开场免责声明。对应记录在 `metadata.spgispeech1_test_ids` 标出：train 16,058 条、51.1 h，dev 589 条，test 680 条。
  - 许可：Kensho 研究许可，仅限非商用研究，用它训练的模型须免费提供。

## 终版 v4

2026-11-27 起。用户决定数字"都统一阿拉伯数字"，训练文本和评测参考文本都改。

- **规则 9**：见上表。现成的反向正则化工具（wetext 的 zh itn）会改掉数字以外的字（"三百秒"→"300s"、"十分感谢"→"10分感谢"、日期改成斜杠格式），不能直接用。所以 `zh_numbers.py` 只替换数字本身，"公斤"等字一个不动。
- **校准**：四轮试跑，每轮按类别（value、digits、decimal、percent、date、time、latin）各抽 30 条逐条看，最后一轮误改 0–1 条/类。修掉的误改有：片名里的月份（十月围城）、钟点被当成小数（七点四人座、四点一刻、八点一直）、英文单词后的"一样""一个"、结巴的概数（二三五六岁）。过程和样本见运行目录 `v4/README.md`。
- **范围**：59 个中文来源（各链最新终版，加上原版本即终版的 `context_correction_synth_zh` 四个版本、`police_text_gaps_train@v2-20261123`、`police_v6_test_instr_train@v1-20261123`）的 train 类划分。56 个有改动，共 2,145,431 / 35,137,476 条（6.1%），最多的是 aishellmix（29%）、AISHELL-2（18%）、警务（18.5%）。`ami_sdm` 和两个 `ts_nonspeech_pool` 没有改动，上一版仍是终版。
- **热词列表**：同一个热词表里两种写法的同一个词（"大明王朝一五六六"和"大明王朝1566"）转换后相同，只留第一个，否则违反热词不重复的约定（`hard_hw_sft` 12 条、`ts_scene_pool@alt-twins` 干扰热词 1 条）。2026-11-28 起热词表的每个词都按规则 9 单独转换（用户决定"都可以转换"），不再只在 target 有改动时转；原样出现在 target 里的词保持 target 的写法（"蓝牙四点二"），热词表和 target 一致。
- **登记后的修正（2026-11-27，版本名不变）**：上下文纠偏线核对时发现 `labels.context_correction`（segments、marked_text、cot）没有跟着改，“数字一百的百”被改成“100的百”；复查又发现钟点“八点四十五”只改了分钟（写成“八点45”）。修法：segments 按转换位置从新 target 上切，marked_text 和 draft 由它重建；数字词后面跟“的”和它自己的十、百、千、万、亿再接标点时保留汉字；分钟按数值读（十到五十九）、不带“分”的钟点小时和分钟一起改（“这一点十分重要”的“十分”不算）；“十三香”进固定词表。在全部 298 万条原文上比较新旧规则，4,666 条输出不同，抽查无误。改动的版本在 provenance.record_correction 记了原 sha256。同时补建了漏掉的 `context_correction_synth_zh@asr-dialog-v1-20261122`（原版本即终版，当初不在来源名单里）；上下文纠偏合成数据里 target 含竖线的记录（"必须|必需"，受保护词展开时没去掉备选，TTS 两种写法都念了）移到 quarantine 划分：train-v1 148 条、ts-twins 74 条、asr-dialog 159 条，记录内容不变，纠偏线确认。
- **专名词表（2026-11-28，版本名不变）**：转换器没有上下文，会把专名也改成数字（"春风10里""降龙18掌""党的20大""18届三中全会""胃12指肠""北京10里堡"），这是查 `hw_sft` 热词表时发现的。按 GB/T 15835，成语、惯用语和专名保留约定写法，`zh_numbers.py` 补了专名词表：地名和路名、作品名、藏药名、党代会和全会、全国人大和政协的届次。约定写阿拉伯数字的专名（恋曲1990、360安全卫士、58同城、波音777、沪深300指数）不进词表。在 298 万条原文上回归，8,076 条改回汉字，每处差异都落在词表里的词上；改动的版本在 provenance.record_correction 追加了这一轮的原 sha256。
- **字母后的型号和版本号（2026-11-28，同一轮）**：原来数字挨着字母时只改整数部分，小数留成汉字（"PM2点五""Web3点零""iOS26点四点一"）。现在字母后面的"X点Y"整个按小数改，多段版本号连在一起（PM2.5、Web3.0、USB3.1、iOS26.4.1）；回归 1,282 条，全是型号和版本号。"幺"开头的号码（"FM幺零五点四"）还是只改整数部分。
- **已知限制**：原文本身读串或有错的（"十八点百分之三"）只改一部分；说话重复的钟点（"九点九点五十五"）前一个不改；一位数编号保留汉字，所以"一号线"不变而"十号线"改成"10号线"。
- **评测**：评测参考文本不另建版本（用户 2026-11-28 决定"修好打分"）。amphion-eval 原生打分第 6 版（MR !175）在算字错率时，每个阿拉伯数字按最接近另一边的读法读（按数值读、逐位读，或还原成原来的汉字），所以输出汉字数字的旧模型和输出阿拉伯数字的 v4 模型可以直接比，每一行的错误数都不超过第 4 版。第 5 版只转换一边时会多记错，不要用；旧成绩 rescore 到第 6 版再比。
- **icefall**：不在本轮范围（icefall 无标点，等下一次从头预训练时另定）。

## 使用范围

- **open-audio-llm 的所有训练任务都用终版**（2026-11-21 起）：有 `-final-v1-20261120` 版本的来源用它；规则对它没有改动的来源不另建版本，下表列出的原版本就是终版。已经训完的实验按历史保留，不改。
- **终版登记在多个文件里**：中英 v1 `catalog/text_final_v1.yaml`、v2 `catalog/text_final_v2.yaml`、v3 `catalog/text_final_v3.yaml`、v4 `catalog/text_final_v4.yaml`，西语 `catalog/text_final_v1_es.yaml`。按登记查终版的脚本要读全部 `catalog/text_final_v*.yaml`，并按 `superseded_by` 跳到最后一个版本；只读一个文件会漏掉 v2、v3、v4 或西语。
- **icefall 暂不切换**：等下一次从头预训练，再按 icefall 的无标点写法另建 `<数据集>@icefall-20260908-final-v1-20261120`（只补改动字词的修正，评测条目一并登记）。
- 切换时注意带版本号的记录名单，见上文"切换到终版时检查记录名单"。
- **按记录关联的标注表也要换成对应终版**：它们按 `(dataset@version, record_id)` 关联训练记录，配方切到终版后键对不上（加载器会报错）。已建：`context_correction_clean_zh@think-v2-20261113-final-v1-20261120`（上下文纠偏 SFT 的 think 表，dataset 键按 `superseded_by` 换成终版，Lhotse 来源的 record_id 换前缀）。

原版本即终版的来源：

| 来源 | 说明 |
|---|---|
| `context_correction_synth_zh@train-v1-20261114`、`@implicit-v1-20261117`、`@ts-twins-v1-20261121` | 各条规则都没有改动。train-v1 和 ts-twins 约 2.2% 的句子没有标点（规则 1 未满足），由下一版合成数据补，同时同步 segments、think 表和场景文本 |
| `ts_nonspeech_pool@es-babble-20261110` | 目标为空 |
| 葡语：`common_voice_pt@pt-train-v1-20261117`、`mls_pt@pt-train-v1-20261117`、`asr_babble_speech_pool@pt-v1-20261117`、`ts_nonspeech_pool@pt-babble-20261117`、`ts_scene_pool@pt-1spk-v1-20261117`、`ts_scene_pool@pt-{near,alt-twins,solo,hard,handover}-20261117-punchw-20261117` | 见下文[葡语](#葡语) |

## 西语（es-v1）

适用于 open-audio-llm 训练用的西语来源。中英规则 1–6 改不到西语文本（字母连写只作用于含汉字的文本），西语另按下面两条。生成脚本是 `scripts/text_final/build_es.py`（`--scan` 只读统计）。同一行里的场景文本（`metadata.scene.targets[].text`）、热词标注文本和热词列表与目标文本一起改。

| # | 规则 | 适用范围 | 执行方式 |
|---|---|---|---|
| es-1 | Common Voice 句子用原句的词和标点，按书面写法规整：标点 `, ; : . ? !` 前和 `¿ ¡` 后不空格，首字母大写，句末没有 `. ? !` 时补句号 | Common Voice 西语 | `es-train-v1-20261108` 构建时已执行（es-data-20261108 `scripts/finalize.py` 的 `tidy_cv`）。`cv27-train-v1-20261111` 的文本丢了全部标点，部分词粘连（`Reino UnidoNueva Zelanda`、`aquemarropa`）：终版按录音 ID 从 27.0 发布的 validated / other.tsv 取回原句，忽略标点、空格和大小写后字母一致才换（`_` 读作空格），再规整 |
| es-2 | 单字母词按现代正字法写：`á`→`a`、`é`→`e`、`ó`→`o`（旧式写法的介词和连词，如 `cogemos á este`、`inmóvil é inanimado`） | 全部西语来源 | 只改前后都不是字母的单个 `á é ó`，带重音的普通词（`él`、`café`、`mamá`）不受影响 |

没有执行的：

| 项目 | 现状 | 原因 |
|---|---|---|
| 问句补开问号 `¿` | Common Voice、MLS 约 0.1%，场景池约 0.3% 的问句没有 `¿` | 多是英文标题或原文如此；补 `¿` 要判断问句从哪里开始，量少，暂不处理 |
| 数字写法 | 没有统计 | 同中文规则 3，要和评测参考一起改 |

各来源的终版（"改动行"按配方训练的划分计；mls_es@es-train-v1 的两份文本 supervisions 和 punc_all 分开计）：

| 终版 | es-1 | es-2 |
|---|---:|---:|
| `common_voice_es@cv27-train-v1-20261111-final-v1-20261120` | 980,450 | 482 |
| `common_voice_es@es-train-v1-20261108-final-v1-20261120` | 0 | 52 |
| `common_voice_es@es-train-hwconf-v1-20261111-final-v1-20261120` | 0 | 9 |
| `mls_es@es-train-v1-20261108-final-v1-20261120` | 0 | 47,797 + 51,708 |
| `mls_es@es-train-hwconf-v1-20261111-final-v1-20261120` | 0 | 26,410 |
| `asr_babble_speech_pool@es-v1-20261110-final-v1-20261120` | 0 | 2 |
| `ts_scene_pool@es-1spk-v2-20261110-final-v1-20261120` | 0 | 45 |
| `ts_scene_pool@es-near-20261109-punchw-20261109-final-v1-20261120` | 0 | 53 |
| `ts_scene_pool@es-alt-twins-20261109-punchw-20261109-final-v1-20261120` | 0 | 20 |
| `ts_scene_pool@es-solo-20261109-punchw-20261109-final-v1-20261120` | 0 | 7 |
| `ts_scene_pool@es-hard-20261109-punchw-20261109-final-v1-20261120` | 0 | 6 |
| `ts_scene_pool@es-handover-20261109-punchw-20261109-final-v1-20261120` | 0 | 3 |

## 葡语

葡语来源不另建终版，原版本就是终版（2026-11-21 定）。

- Common Voice 葡语（`common_voice_pt@pt-train-v1-20261117`）构建时已按西语 es-1 的做法用原句的词和标点并规整，没有缺标点、小写开头的句子；场景池和 babble 池的目标取自它，同样已是书面写法。
- **没有执行**：MLS 葡语（LibriVox 有声书，`mls_pt@pt-train-v1-20261117` 约 3.6 万句）用 1911 年改革前的旧正字法，如 `elle`、`ella`、`aquelle`、`alli`、`n'um`（现代写法 `ele`、`ela`、`aquele`、`ali`、`num`），常见旧词各出现几百次，另有 `ph`、`y`、双写辅音等零散旧写法。要改得用完整的旧新写法对照，只换常见词会混出半旧半新的写法，暂不处理。

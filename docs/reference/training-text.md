# 训练文本规范（终版 v1）

适用于 open-audio-llm 训练用的中文、英文和西语训练文本（中英最早按交付配方 v7set34 建，西语见[西语（es-v1）](#西语es-v1)）。各轮文本修正都按这份规范执行，并合进同一个终版。训练时每个来源只用它的终版，范围见[使用范围](#使用范围)。

- **终版版本名**：`<配方原来用的版本>-final-v1-20261120`，登记在 `catalog/text_final_v1.yaml`，生成脚本是 `scripts/text_final/build.py`。
- **做法**：从每个来源已登记的修正版本里最深的那个出发，再把下表中适用的规则补齐。规则没有改动的文本文件和录音、音频都引用原文件，不复制。
- **以后增加规则**：先把规则写进本文，再用同一个脚本重建终版 v2，并在 v1 的登记里写 `superseded_by`。不要在终版上再派生一层后缀。
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

中英写法的细则和评测口径见 [zh-en-transcription.md](zh-en-transcription.md)。

## 没有执行或只部分执行的

| 项目 | 现状 | 原因 |
|---|---|---|
| 字母数字词用阿拉伯数字（中英规范规则 3，五G→5G） | 不执行 | 现有评测参考文本大多写汉字数字，ts-asr 评测器不做数字转换；只改训练文本会让评测字错率上升，要改得和评测参考一起改 |
| 英文写成汉字（规则 4） | 只做了 WenetSpeech，改 3,727 条；估计全量约 1.4 万条 | 剩下约 1 万条拿不准：通行译名两种读法相近，三个音频大模型（豆包 seed-2.1-lite、qwen3.8-omni-flash、qwen3.5-omni-plus）的判断互相矛盾，没有可靠的核对方 |
| 汉字和英文之间不加空格（中英规范规则 5） | 不执行。终版里有 141,704 条汉字和英文之间带空格，几乎都在 Emilia2 三个来源（约 12.6 万）和警务训练集（约 1.5 万） | 评测时去掉空格再比，不影响分数；要统一写法得另做一轮，并核对英文短语内部的空格不被误删 |
| 繁简统一、去掉非语音标记（中英规范规则 6、7） | 繁简没有统计；非语音标记（`<…>`、`[UNK]`、`**`）终版里有 77 条，在 Emilia2 三个来源 | 评测集版本已处理；训练文本数量很少，暂不处理 |

## 各来源的终版

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

## 使用范围

- **open-audio-llm 的所有训练任务都用终版**（2026-11-21 起）：有 `-final-v1-20261120` 版本的来源用它；规则对它没有改动的来源不另建版本，下表列出的原版本就是终版。已经训完的实验按历史保留，不改。
- **终版登记在多个文件里**：中英 `catalog/text_final_v1.yaml`，西语 `catalog/text_final_v1_es.yaml`。按登记查终版的脚本要读全部 `catalog/text_final_v1*.yaml`，只读第一个会漏掉西语。
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

# 真实对话的目标说话人评测集（ts_asr_real）

评测版本：`v1-20261013`（824 条、16 个场景，三个人工标注语料）、`v2-20261013`（1,134 条、22 个场景，增加 Emilia2 网络爬取的对话，MOSS 伪标签；v2 包含 v1 的全部场景）、`v3-20261022`（v2 的修正版，见“注册段里的他人语音”）和 `v4-20261022`（v3 的 5 秒注册版，见“5 秒注册”）；另有以目标为锚的重叠窗口 `overlap-v1-20261017` 和开发集 `dev-v1-20261017`（见下文）。只用于评测，不进训练。评测集登记在 AmphionEval：`open-audio-llm/ts-asr-real@v1-20261013` 和 `@v2-20261013`。生成脚本 `scripts/ts_real/build.py`。

与合成评测集 [ts_asr_benchmark](ts-benchmark.md) 互补：那边可以一次只改一个因素，这里是真实的对话、重叠、房间和设备，**不做任何混合**。

## 构造

- 来源（人工标注）：人工标注的测试划分，按完整语句切窗口：AliMeeting 远场（`alimeeting_sdm@icefall-20260908`，取通道 0）、AISHELL-4 远场（取通道 0）、MagicData-RAMC 手机通话（`magicdata_ramc@icefall-20260908`）。
- 窗口：从一条语句的起点开始，向后取 8–22 秒，再扩展到包含与窗口重叠的所有完整语句（不从句中切开），不超过 26 秒（TS 服务单段上限 27 秒）；窗口之间不重叠。
- 每个窗口配一对样本，音频相同：**目标在场**（窗口里说话不少于 1 秒的一位说话人；注册取同一录音窗口外 1 秒以上的另一条不少于 3 秒、被他人重叠不超过 20% 的语句，最长 6 秒）和**目标缺席**（同一录音里没有在窗口里说话的人，注册同样取窗外的语句；没有这样的人时取同一语料另一条录音里的说话人，`labels.absent_source` 标明）。
- 参考文本是目标说话人在窗口内所有语句按时间顺序拼接；目标缺席时为空。
- 场景名 `real-<语料>-<窗口内说话人数>-<pos|neg>`，人数分 `1spk`、`2spk`、`3plus`（电话通话只有两人，没有 `3plus`）。
- `labels`：`corpus`、`recording`、`duration_s`、`speakers_in_window`、`n_interferers`、`target_overlap_ratio`（目标语句时间内有别人说话的比例）、`target_seconds`、`mixture_rms_dbfs`、`absent_source`、`annotation: human`；`metadata.window_utts` 保存窗口内全部语句（说话人、相对起点、时长、文本），用于判断输出是不是转写了别人。

## 注册段里的他人语音（v3-20261022）

TS 客户端只发送注册语句的前 3 秒。v1/v2 选注册时只要求整条语句（3–6 秒）被他人重叠不超过 20%，重叠可能都落在前 3 秒里：v2 有 97 条记录的注册前 3 秒里，标注显示他人说话不少于 0.3 秒（AliMeeting 67、AISHELL-4 22、Emilia2 8、RAMC 0）。这样的注册是一种真实的退化，但被当作干净注册计分；混进来的人在窗口里说话时，模型会转写他，被记为误输出（2026-10-22 核对：混入不少于 0.5 秒、且此人在窗口里说话的目标缺席样本，10.21 版本误输出 21%，干净注册时 3.6%）。

`v3-20261022` 由 v2 派生（`scripts/ts_real/enroll_overlap.py`），窗口和混合音频不变：

- 每条记录加 `labels.enroll_others_s`（注册前 3 秒里他人说话的秒数，按语料标注；Emilia2 按 MOSS 伪标签）和 `labels.enroll_condition`：少于 0.3 秒为 `clean`，否则为 `others_speech`；`metadata.enroll_others` 列出是谁。
- `others_speech` 的记录移入同名加 `-enrollmix` 的划分（如 `real-alimeeting-3plus-neg-enrollmix`），原划分只剩干净注册。评测集把它们单列，不计入干净注册的分数。
- AISHELL-4 有 3 条目标在场样本的注册其实是同场另一个人（ERes2NetV2 声纹：注册更像那个人，而不像窗口里目标本人的语音），改取目标的另一条合格语句（声纹核对通过、前 3 秒无他人），旧注册记在 `metadata.enrollment_replaced`；`real-aishell4-3plus-pos:0024` 窗口里目标只有 2.1 秒且都被重叠，目标的所有语句也都更像另一个人，无法确认目标，删除（v3 共 1,133 条）。
- 记录 ID 与 v2 相同，可以逐条对照。

`build.py` 同时改为：注册候选的前 3 秒里他人说话须少于 0.3 秒（`ENROLL_CROP_OTHERS_MAX`），每条记录写入 `enroll_others_s` 和 `enroll_condition`，以后新建的版本不再混入这类注册。

## 5 秒注册（v4-20261022）

线上注册改为 5 秒后，`build.py` 的 `ENROLL_CROP` 改为 5 秒，并且每条注册存 10 秒（`ENROLL_STORE`）：保留选中的语句，后面接同一人在窗口外（留 1 秒边距）、没有任何他人标注重叠的其他语句（`enrollment_pieces`，按记录自己的随机流打乱），`metadata.enrollment_pieces` 记录各段的起止，`labels.enroll_seconds` 是存的长度。`labels.enroll_others_s` 改按前 5 秒计算，不少于 0.3 秒的在 `-enrollmix` 划分。

`v4-20261022` 由 v3 派生（`scripts/ts_real/enroll_long.py`），窗口、混合音频和记录 ID 不变：1,133 条，1,047 条存满 10 秒、69 条 5–10 秒、17 条不足 5 秒（说话人在录音里没有更多合格的语句）。按 5 秒计，`-enrollmix` 从 97 条增加到 139 条（第一句不足 5 秒时，计算范围包含其后接上的语句，以及第一句之后原来未计入的部分）。AISHELL-4 重新读出的第一段与 v3 是同一文件的通道 0，起点最多差 6 个采样点（FLAC 定位）；Emilia2 的差别是解码的数值舍入。

`ts_asr_nearfar@v3-20261022` 用 v4 源样本同样的语句片段，远场取通道 0，近场取本人头戴麦；`-enrollmix` 为 388 条。

## 目标重叠窗口（overlap-v1，个性化 VAD 用）与开发集（dev-v1）

v1/v2 的窗口要求“与窗口重叠的语句都完整”，重叠多的地方窗口很快超过 26 秒被丢弃，结果 AliMeeting 测试集有 4.56 小时重叠语音，进入 v2 窗口的只有约 0.06 小时。这两个版本改为**以目标说话人为锚**切窗口（`build.py --recipe overlap|dev`）：

- 窗口从目标的一条语句前 0–4 秒开始（不早于目标上一条语句的结束，所以目标不总是第一个开口），向后 8–22 秒，再延伸到期间开始的目标语句结束；目标的语句完整，别人的语句截到窗口边界（`metadata.window_utts` 里标 `clipped: true`）。
- 按目标语音被别人重叠的比例分档：`o0`（< 5%）、`o20`（5–20%）、`o50`（20–50%）、`o100`（> 50%）；与已选窗口重合超过一半的窗口跳过，同一段录音不重复计分。`labels.overlap_bucket` 记档位。
- 去掉含有 train 划分说话人的录音（RAMC dev 去掉 5 条，其余没有）。注册、配对的目标缺席样本与 v2 相同。
- `overlap-v1-20261017`：AliMeeting、AISHELL-4 测试集，场景 `real-<语料>-<o20|o50|o100>-<pos|neg>`。只用于评测，是 `amphion-tse/pvad-benchmark@v2-20261017` 的真实重叠部分。
- `dev-v1-20261017`：AliMeeting dev（`o0`–`o100`）、MagicData-RAMC dev（标注没有重叠，只有 `o0`），场景 `dev-<语料>-<档位>-<pos|neg>`。只用于选模型和阈值（`amphion-tse/pvad-dev@v1-20261017`），不进训练，也不作最终评测。

## Emilia2 网络爬取的对话（v2，MOSS 伪标签）

`emilia2_zh_dialogue_diarize@moss-transcribe-diarize-0.9B` 是 Emilia2 里网络爬取的中文多人对话（访谈、播客等）的说话人日志伪标签：本地 MOSS-Transcribe-Diarize 0.9B 打说话人和文本，在停顿处切成 30–120 秒窗口，整窗经 Qwen3-ASR 核对（文字差异 ≤ 15%），再与 Emilia2 自带的带时间短句核对说话人（登记说明里 100 段抽检的窗口文字错误率约 3%、说话人混淆 0.86%）。

- 取样：只用 2–3 人、同时说话不超过 3 人、40–120 秒的窗口，每个录音取一个窗口，抽 260 个录音；再用同样的窗口规则（完整说话轮、8–22 秒）切成样本，音频是 44.1 kHz AAC 的 m4a，用 ffmpeg 解码到 16 kHz。
- 标注是**伪标签**：`labels.annotation = "moss"`，参考文本可能带有错误（片段里同一人可能被拆成几个说话人，有声剧一人多角会按角色拆分）。目标在场的 CER 因此含有标签噪声，目标缺席的误输出率受影响较小。
- **训练必须排除这些录音**：用到的 260 个 Emilia2 录音 id 写在 `source/<版本>/excluded-recordings.txt`，与 `emilia2@tts-unified-v0.1` 按 `recording_id` 对应，两边都要排除。
  这份清单已登记为 `ts_asr_real@v2-20261013` 的 `emilia2-holdout-recordings`（`provenance.holdout`，按 16 位来源 hash 比较，同一来源的其他对话窗口一并留出），Emilia2 训练数据集声明了 `provenance.source_keys`；open-audio-llm 读取训练数据时自动去掉重叠记录，可用 `audio-data-contract check-holdout` 检查任一划分（见[评测留出与来源键](../../catalog/README.md#评测留出与来源键)）。下面的 `exclude_records` 清单是此前的手工做法。
  训练配置按记录 ID 排除（`exclude_records`），用 `scripts/ts_real/exclusion_records.py` 把录音清单换成某个训练划分的记录 ID。已生成的清单在 `source/v2-20261013/`：`excluded-records-emilia2_zh_dialogue_diarize-train_120s.txt`（1,030 条，225 个录音）和 `excluded-records-emilia2_zh_overlap_farsim-train_120s.txt`（380 条，166 个录音）。这两份清单生成时脚本的正则没匹配带 `_pN` 后缀的录音 ID（260 个里有 35 个），各漏了 106 条和 38 条；脚本已修正，清单本身未重新生成。`exclude_records` 只接受一个文件，和已有的排除清单（例如 4 人以上）一起用时需要合并成一个文件。2026-10-14 正在运行的 `zh-overlap-farsim-acp-20261013` 在建数据时没有排除，约 0.5% 的训练记录来自这些录音。
- 污染说明：这批窗口来自 `train_120s`，34479 的原训练管线用过 Emilia2 对话，新的 SOT 训练轮用过整个 `train_120s`，所以对这些模型这是**可能见过的音频**，结果偏乐观；对以后排除了这些录音的训练才是干净的评测。

## 英文版（en-v2-20261031）

`ts_asr_real@en-v2-20261031`：1,301 条、60 个划分，`build.py --recipe en`（加载与转写清洗在 `english.py`，声纹核对在 `voice_check.py`，需 `--embed-python` 指向装有 onnxruntime 与 torchaudio 的环境，如 conda `k2`）。切窗、正负配对、10 秒注册与 `-enrollmix` 规则与中文 v4 相同；`language: en`，参考文本按时间顺序用空格拼接。`en-v1` 是同一配方的首次构建，声纹缓存按录音名取键，DiPCo 与 CHiME-6 都有 `S01`/`P01–P04` 而串用，已作废、未登记。

| 语料（只用 test / eval） | 通道 | 窗口 1spk/2spk/3plus | 记录 | 与 AmphionASR 2.0 训练的关系 |
| --- | --- | --- | --- | --- |
| AMI（ES2004、IS1009、TS3003、EN2002 四组，16 场） | 单远场麦 Array1-01 | 50/50/56 | 312 | 同域：训练用过 AMI train，测试会议与说话人不在其中 |
| NOTSOFAR-1（官方 eval，`240825.1_eval_full_with_GT`） | 每场随机一台单通道设备 | 50/50/55 | 292 | 跨域 |
| CHiME-6 eval（S01、S21） | 说话人所在房间参考阵列的通道 1，窗口内所有人同一房间 | 11/50/56 | 234 | 同域：训练用过 CHiME-6 train，S01/S21 与其 8 位说话人不在其中 |
| DiPCo eval | 每场随机一台远场设备的通道 1 | 4/27/56 | 151 | 跨域 |
| ICSI（Bmr013、Bmr018、Bro021） | 官方近讲耳麦混音（登记的版本没有桌面麦） | 50/50/56 | 312 | 跨域 |

- **转写清洗**：笑声、噪声、截断词、填充标签直接去掉；听不清、被消音、外语、读数字的语句仍算有人说话（影响窗口边界与在场判断），但不作目标、不作注册；目标在窗口里的话去掉 um/uh/mm 后要留有实词（与英文打分的 Whisper 归一化一致）。每种语料遇到未知标注直接报错。
- **DiPCo 时间轴**：转写给远场设备抄的是近讲麦时间，实测远场整场偏 −0.10 到 +0.25 秒，按场平移后再切窗（互相关测得，`source/en-v2-20261031/report.json` 的 `timeline_offsets_s`）。AMI、NOTSOFAR 核对过不需要修正。
- **声纹核对**（WeSpeaker ECAPA VoxCeleb）：注册前 5 秒要比同场其他人更像本人在本录音的其他语句（有近讲麦的语料用近讲麦之和建档）。换掉 9 条、剔除 43 条（NOTSOFAR 20、DiPCo 23，都是本人在录音里没有别的可用语句、无法建档）；分数在 `metadata.enroll_voice_check`。这是相对判断，没有人工听审。
- **注册含他人声比例**：首句注册沿用 v2 的「他人重叠 ≤ 20%」规则（recipe `enrollmix: true`），前 5 秒他人说话 ≥ 0.3 秒的进 `-enrollmix`，占 22–41%，高于中文；干净注册的划分因此较小。68 条注册不足 10 秒（最短 3.05 秒），客户端补零。
- **没有近远场对照**：登记的 `ami_ihm` 只有切好的句子片段，没有整场耳麦录音，拼不出中文 `ts_asr_nearfar` 那样的近场混合；要做需先登记 AMI 官方 Headset / Mix-Headset 整场录音。顺带发现 AMI turn-taking 的 train 含全部 18 场 AMI dev 会议，AMI dev 对 2.0 不干净。

## 注意

- 34479 的训练用过前三个语料的训练集（不同的录音和说话人），所以这里测的是同域表现，不是脆弱点；它的作用是校准：合成评测集的失败率与同域真实数据差多少。
- 会议语料的录音通道和电平与业务（手机原始麦克风、户外）不同，业务现场录音需要另外的来源；用 MOSS 对新录音做说话人日志转写得到的伪标签应登记为单独的版本，并在 `labels.annotation` 里标为 `moss`。
- 声音、说话人身份没有人工复核，沿用语料的标注。

## 近场与远场对照（ts_asr_nearfar）

`ts_asr_nearfar@v1-20261014`：1,248 条、24 个场景。用 `ts_asr_real@v2-20261013` 的 AliMeeting 窗口（三档说话人数各 50 个），同一窗口、同一条注册语句，注册取远场（`ef`）或说话人的头戴麦（`en`），混合取远场通道 0（`mf`）或该录音所有头戴麦之和（`mn`，电平对齐远场混合，只剩声学差异）。场景名 `nearfar-<人数档>-<注册>-<混合>-<pos|neg>`，`ef-mf` 就是原来的样本。近场与远场录音的时间偏差不超过 0.12 秒。生成脚本 `scripts/ts_real/near_far.py`；AISHELL-4 没有近场录音，所以不含。用来校准合成的远场失配场景，只用于评测。`ts_asr_nearfar@v2-20261022` 是同样的修正版：注册与 v2 窗口相同，所以同一批 67 个注册（×4 种组合，268 条）标为 `others_speech`，移入 `-enrollmix` 划分。

## 谁先开口（ts_asr_nearfar@firstother-v1-20261104）

复现一条内部返回的 TS-ASR badcase：45 秒三人同屋交替说话，注册是另一次单独录的 5 秒声纹，会话开头是非目标说话人清晰地数数，所有版本都整段转写了先开口的人。对照实验表明是两个因素叠加：注册与会话不同录音（匹配信号弱），以及混合开头先是非目标说话人。生成脚本 `scripts/ts_real/first_speaker.py`，评测集配置 `scripts/ts_real/first_speaker_eval_set.py`（AmphionEval `open-audio-llm/ts-asr-first-other@v1-20261104`）。

- 来源：AliMeeting Test 远场通道 0 的人工标注（训练配方只用 train 划分）。从每条语句起点向后取 25–40 秒，再扩到完整语句，保留 25–45 秒、≥3 人说话、目标累计说话 ≥5 秒的窗口。
- `firstother`：窗口第一个开口的不是目标，且目标第一句之前已有非目标一整句 ≥1.2 秒、被他人重叠 ≤20% 的语句（labels `lead_start_s`、`lead_seconds`，`metadata.lead_utterance`）。`firsttarget`：同样规则，但目标先开口，作对照。同一类窗口在一场会议里互不重叠；两类按（会议，窗口人数）取相同个数，所以会议、人数一致，只有谁先开口不同。
- 注册、正负配对和 `-enrollmix` 规则同 `ts_asr_real@v4-20261022`；注册和开头那句都要过声纹核对（头戴麦之和建档），开头那句不过的整窗隔离。注册有三种，混合都是远场通道 0：`ef` 远场通道 0，`en` 本人头戴麦上的同样片段，`ed` 是 `en` 先限带（3.5–5 kHz 低通，或 4 kHz 以上 −6 dB 高架）再加 WHAM! 测试集稳态噪声（SNR 15–25 dB），模拟 badcase 声纹比会话更吵、更闷；参数逐条记在 `metadata.enroll_degradation`。声纹核对按干净注册判定，劣化后的结果在 `metadata.enroll_degraded_voice_check`。
- 结果：1,782 条，12 个划分 `<firstother|firsttarget>-<ef|en|ed>-mf-<pos|neg>`，每个划分 148/149 条，用到 10 场会议，窗口平均 36–37 秒。隔离 1 个窗口（开头那句声纹核对不过），所有注册的前 5 秒都无他人说话，所以没有 `-enrollmix`；劣化注册 594 条全部仍通过声纹核对。窗口须 ≥3 人而会议只有 3–4 人，297 个目标缺席样本中有 285 个只能取其他会议的人（`labels.absent_source`）。明细见 `source/firstother-v1-20261104/report.json`。
- 窗口超过 `ts_asr_real` 的 26 秒上限（原来 TS 服务单段上限 27 秒）：评测要整段送入，客户端或服务若截断，结果不能代表这类场景。
- `first_speaker_windows`、`match_windows` 的划分和阈值都是参数，可以直接在 train 划分上切训练窗口；这一版只做了评测数据。

`ts_asr_nearfar@firstother-v2-20261105`（`scripts/ts_real/first_speaker_near.py`，AmphionEval `open-audio-llm/ts-asr-first-other@v2-20261105`）由 v1 派生，窗口、注册、劣化参数和记录 ID 不变，可以逐条对照：

- 实测发现 badcase 的注册比会话更吵（会话是安静的近讲录音），而 v1 混合是带混响的远场。所以新增 `en-mn`、`ed-mn`：注册分别同 `en-mf`、`ed-mf`，混合取窗口内各说话人头戴麦之和，电平对齐远场混合。`ed-mn` 最接近 badcase。`mf` 各划分不变。
- 每条加 `labels.target_sim`、`impostor_sim`、`sim_margin`、`opener_sim`：ECAPA 计算注册前 5 秒与该条混合里各说话人独自说话部分（标注里无他人、每段 ≥0.3 秒、合计 ≥1 秒）的余弦。impostor 取非目标中最像的那个，margin = target − impostor；每格有 6 个目标在窗口里没有足够的独自说话，这几条不打分。目标在场且 margin ≤ 0.30（badcase 为 0.25）的另列为 `<划分>-hard` 子集。
- 共 3,311 条。正样本 margin 中位数：`ef-mf` 0.38/0.42（firstother/firsttarget，下同），`en-mf` 0.42/0.41，`ed-mf` 0.36/0.36，`en-mn` 0.52/0.53，`ed-mn` 0.44/0.46。hard 条数：`ed-mf` 54/51、`ef-mf` 41/34、`en-mf` 36/40、`ed-mn` 33/29、`en-mn` 9/14。中位数与条数明细见 `source/firstother-v2-20261105/report.json`。

`ts_asr_nearfar@firstother-v3-20261105`（`scripts/ts_real/first_speaker_crowded.py`，AmphionEval `open-audio-llm/ts-asr-first-other@v3-20261105`）按 v2 错人输出的挖掘结果重新取样：错人主要出现在目标被重叠多、说得少、注册匹配弱的时候（重叠 ≥0.3 且 target_sim <0.5 时 27–30%；被重叠 <5% 或说话 >20 秒时为 0%），谁先开口影响小（6.2% 对 3.6%）。

- 来源：AliMeeting Test 与 Eval（icefall `dev`，只在部分训练里作验证集，没进训练数据）、AISHELL-4 test，混合都是远场通道 0。窗口 25–45 秒、≥3 人、目标 ≥5 秒，不再要求开头有一句清晰语句。
- 每个（窗口，目标）分层：`crowded` 指目标被重叠 ≥30% 且说话 <15 秒，`control` 指被重叠 <15% 且说话 ≥20 秒；`control` 在每个（语料，会议，人数）下不超过 `crowded` 的个数。同一目标在同一录音里的样本窗口重合不超过较短者的一半，不同目标可以用同一段。非目标先开口与目标先开口交替取，`labels.first_speaker` 尽量均衡。
- 注册方式：AliMeeting 有 `ef`、`en`、`ed` 三种，AISHELL-4 只有 `ef`。正负配对、声纹核对和劣化做法同 v1；`target_sim` 等相似度标签同 v2，在远场混合上算。`crowded` 正样本里 target_sim <0.5 的另列 `crowded-lowsim-<语料>-<注册>-pos`（子集）。每条样本的混合只存一份，各注册方式和正负样本共用。
- 结果：9,030 条。`crowded` 正样本 AliMeeting 每种注册 956 条（非目标先开口 629、目标先开口 327；目标先开口的候选不够，没能均衡），AISHELL-4 384 条；`control` 正样本 AliMeeting 176、AISHELL-4 246；`crowded-lowsim` 依次为 `ef` 236、`en` 261、`ed` 384、AISHELL-4 97。负样本条数与正样本相同。16 对样本因注册声纹核对换句后仍不过而剔除（都是 AISHELL-4），明细见 `source/firstother-v3-20261105/report.json`。

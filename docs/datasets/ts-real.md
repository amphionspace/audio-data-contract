# 真实对话的目标说话人评测集（ts_asr_real）

评测版本：`v1-20261013`（824 条、16 个场景，三个人工标注语料）、`v2-20261013`（1,134 条、22 个场景，增加 Emilia2 网络爬取的对话，MOSS 伪标签；v2 包含 v1 的全部场景）和 `v3-20261022`（v2 的修正版，见“注册段里的他人语音”）；另有以目标为锚的重叠窗口 `overlap-v1-20261017` 和开发集 `dev-v1-20261017`（见下文）。只用于评测，不进训练。评测集登记在 AmphionEval：`open-audio-llm/ts-asr-real@v1-20261013` 和 `@v2-20261013`。生成脚本 `scripts/ts_real/build.py`。

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
  训练配置按记录 ID 排除（`exclude_records`），用 `scripts/ts_real/exclusion_records.py` 把录音清单换成某个训练划分的记录 ID。已生成的清单在 `source/v2-20261013/`：`excluded-records-emilia2_zh_dialogue_diarize-train_120s.txt`（1,030 条，225 个录音）和 `excluded-records-emilia2_zh_overlap_farsim-train_120s.txt`（380 条，166 个录音）。`exclude_records` 只接受一个文件，和已有的排除清单（例如 4 人以上）一起用时需要合并成一个文件。2026-10-14 正在运行的 `zh-overlap-farsim-acp-20261013` 在建数据时没有排除，约 0.5% 的训练记录来自这些录音。
- 污染说明：这批窗口来自 `train_120s`，34479 的原训练管线用过 Emilia2 对话，新的 SOT 训练轮用过整个 `train_120s`，所以对这些模型这是**可能见过的音频**，结果偏乐观；对以后排除了这些录音的训练才是干净的评测。

## 注意

- 34479 的训练用过前三个语料的训练集（不同的录音和说话人），所以这里测的是同域表现，不是脆弱点；它的作用是校准：合成评测集的失败率与同域真实数据差多少。
- 会议语料的录音通道和电平与业务（手机原始麦克风、户外）不同，业务现场录音需要另外的来源；用 MOSS 对新录音做说话人日志转写得到的伪标签应登记为单独的版本，并在 `labels.annotation` 里标为 `moss`。
- 声音、说话人身份没有人工复核，沿用语料的标注。

## 近场与远场对照（ts_asr_nearfar）

`ts_asr_nearfar@v1-20261014`：1,248 条、24 个场景。用 `ts_asr_real@v2-20261013` 的 AliMeeting 窗口（三档说话人数各 50 个），同一窗口、同一条注册语句，注册取远场（`ef`）或说话人的头戴麦（`en`），混合取远场通道 0（`mf`）或该录音所有头戴麦之和（`mn`，电平对齐远场混合，只剩声学差异）。场景名 `nearfar-<人数档>-<注册>-<混合>-<pos|neg>`，`ef-mf` 就是原来的样本。近场与远场录音的时间偏差不超过 0.12 秒。生成脚本 `scripts/ts_real/near_far.py`；AISHELL-4 没有近场录音，所以不含。用来校准合成的远场失配场景，只用于评测。`ts_asr_nearfar@v2-20261022` 是同样的修正版：注册与 v2 窗口相同，所以同一批 67 个注册（×4 种组合，268 条）标为 `others_speech`，移入 `-enrollmix` 划分。

# 真实对话的目标说话人评测集（ts_asr_real）

`ts_asr_real@v1-20261013`：824 条 `ts_asr` 记录，16 个场景（split），只用于评测，不进训练。评测集登记在 AmphionEval：`open-audio-llm/ts-asr-real@v1-20261013`。生成脚本 `scripts/ts_real/build.py`。

与合成评测集 [ts_asr_benchmark](ts-benchmark.md) 互补：那边可以一次只改一个因素，这里是真实的对话、重叠、房间和设备，**不做任何混合**。

## 构造

- 来源：人工标注的测试划分，按完整语句切窗口：AliMeeting 远场（`alimeeting_sdm@icefall-20260908`，取通道 0）、AISHELL-4 远场（取通道 0）、MagicData-RAMC 手机通话（`magicdata_ramc@icefall-20260908`）。
- 窗口：从一条语句的起点开始，向后取 8–22 秒，再扩展到包含与窗口重叠的所有完整语句（不从句中切开），不超过 26 秒（TS 服务单段上限 27 秒）；窗口之间不重叠。
- 每个窗口配一对样本，音频相同：**目标在场**（窗口里说话不少于 1 秒的一位说话人；注册取同一录音窗口外 1 秒以上的另一条不少于 3 秒、被他人重叠不超过 20% 的语句，最长 6 秒）和**目标缺席**（同一录音里没有在窗口里说话的人，注册同样取窗外的语句；没有这样的人时取同一语料另一条录音里的说话人，`labels.absent_source` 标明）。
- 参考文本是目标说话人在窗口内所有语句按时间顺序拼接；目标缺席时为空。
- 场景名 `real-<语料>-<窗口内说话人数>-<pos|neg>`，人数分 `1spk`、`2spk`、`3plus`（电话通话只有两人，没有 `3plus`）。
- `labels`：`corpus`、`recording`、`duration_s`、`speakers_in_window`、`n_interferers`、`target_overlap_ratio`（目标语句时间内有别人说话的比例）、`target_seconds`、`mixture_rms_dbfs`、`absent_source`、`annotation: human`；`metadata.window_utts` 保存窗口内全部语句（说话人、相对起点、时长、文本），用于判断输出是不是转写了别人。

## 注意

- 34479 的训练用过这三个语料的训练集（不同的录音和说话人），所以这里测的是同域表现，不是脆弱点；它的作用是校准：合成评测集的失败率与同域真实数据差多少。
- 会议语料的录音通道和电平与业务（手机原始麦克风、户外）不同，业务现场录音需要另外的来源；用 MOSS 对新录音做说话人日志转写得到的伪标签应登记为单独的版本，并在 `labels.annotation` 里标为 `moss`。
- 声音、说话人身份没有人工复核，沿用语料的标注。

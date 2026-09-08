# Icefall 运行清单快照

`catalog/icefall_runtime.jsonl` 接管 icefall 的全部 70 个 ASR 数据入口，
版本固定为 `icefall-20260908`，另登记 178 条真实 RIR。
历史版本保留供复现；这份快照不是新增的独立语料时长，不应与历史版本累加作为训练量。

`recipe_parameters.icefall.language` 是评分/展示使用的主导语言；`languages`
仍如实记录混合语言。split 中 `icefall.use_punc/channel` 保留读取策略；
`clean_supervisions_artifacts` / `clean_no_punc_supervisions_artifacts` 分别指定
有、无标点的清洗版本。artifact 的 `metadata.icefall_relative_to_lhotse`
表示该输入继续相对调用者的 LHOTSE 根目录加载，以保持原有命令行行为。

| 新增入口 | 当前状态 | 限制 |
|---|---|---|
| alimeeting_sdm | 可用 | 重叠发言可能重复计时 |
| ami_sdm | 可用，含已知缺口 | train 缺 IS1003b、IS1007d，134/136 个会议 |
| notsofar_sdm | 可用 | 同一会议的多个设备版本不能算独立会议时长 |
| vitw_far_field | 可用 | train/bench ID 无交集不代表底层源音频已去重 |
| real_rir_slr28 | 可用 | 仅作声学增强，没有转写 |
| realman | 下载中 | ASR 清单是计划产物；须待本机 preparation_status 为 ready |

RealMAN 原始文件的期望大小和 LFS SHA-256 来自固定的官方 revision；登记这些
期望值不代表已经完成完整性校验。运行状态位于 `legacy_asr` 下的
`RealMAN/preparation_status.json`。下载范围为 train/ma_speech、val/test 的
ma_noisy_speech、转写及元数据，共 113 个文件、258795986801 bytes；不含独立
训练噪声和 direct-path 等语音增强专用数据。解包只提取 CH0，保留官方划分。

MISP-Meeting 尚待许可申请，未宣称下载完成或可训练。AMI 缺失文件当前无法从
官方地址取得，保留这一缺口供后续补齐。

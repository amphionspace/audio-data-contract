# Icefall 运行清单快照

`catalog/icefall_runtime.yaml` 接管 icefall 的全部 70 个 ASR 数据入口，
版本固定为 `icefall-20260908`，另登记 178 条真实 RIR。
历史版本保留供复现；这份快照不是新增的独立语料时长，不应与历史版本累加作为训练量。

带标点的标注登记为 `punctuated_supervisions`（emilia_zh 为 `punctuated_cuts`），
`clean_supervisions` / `clean_no_punc_supervisions` 分别指定有、无标点的清洗版本。
icefall 用 `--use-punc` 在这些登记的产物之间选择，不再按文件名拼接 `_punc`。
混合语言数据集的评分语言、多声道数据的选用声道属于 icefall 的读取策略，
维护在 icefall 仓库中；catalog 只记录 `languages` 等事实。

| 新增入口 | 当前状态 | 限制 |
|---|---|---|
| alimeeting_sdm | 可用 | 重叠发言可能重复计时 |
| ami_sdm | 可用，含已知缺口 | train 缺 IS1003b、IS1007d，134/136 个会议 |
| notsofar_sdm | 可用 | 同一会议的多个设备版本不能算独立会议时长 |
| vitw_far_field | 可用 | train/bench ID 无交集不代表底层源音频已去重 |
| real_rir_slr28 | 可用 | 仅作声学增强，没有转写 |
| realman | 可用 | train/dev/test 分别为 36816/6698/7633 条，64.03/8.09/11.59 小时 |

RealMAN 原始文件的期望大小和 LFS SHA-256 来自固定的官方 revision；登记这些
期望值不代表已经完成完整性校验。运行状态位于 `legacy_asr` 下的
`RealMAN/preparation_status.json`。下载范围为 train/ma_speech、val/test 的
ma_noisy_speech、转写及元数据，共 113 个文件、258795986801 bytes；不含独立
训练噪声和 direct-path 等语音增强专用数据。解包只提取 CH0，保留官方划分。

MISP-Meeting 尚待许可申请，未宣称下载完成或可训练。AMI 缺失文件当前无法从
官方地址取得，保留这一缺口供后续补齐。

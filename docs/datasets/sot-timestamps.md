# SOT 时间戳版本

已登记两个独立入口，时间戳版本当前为 **building，尚不能用于完整训练**：

| 数据集 | 版本 | 状态 |
| --- | --- | --- |
| `sot_multispeaker_zh_en` | `synthetic-v2-20260915` | 已完成；按人汇总原文，没有字词对齐时间戳 |
| `sot_multispeaker_zh_en` | `synthetic-v2-timestamps-v1-20260919` | 版本已登记；源对齐与质量处理尚未全部完成，目标记录未发布 |

时间戳版从原版派生，复用原音频和固定 train/dev/test 划分，计划覆盖 200 万 train、
1 万 dev、1 万 test。版本声明只登记 `expected_records`，不把计划数量和原版时长
计为时间戳版已完成的数据。它没有可训练 `records_artifact`，也没有提前发布可解析
为训练成品的 View；生成并验收目标记录后再补齐物化产物及 View。

## 时间戳来源

AmphionData 用 Qwen3-ForcedAligner-0.6B 对混音实际引用的单说话人源片段做强制
对齐。英语源为 Common Voice EN clean v1、LibriSpeech；中文源为 AISHELL、
AISHELL-2、KeSpeech。普通 ASR 回放的目标不变。

源结果为中文字／英文词起止时间，相对于所读片段起点。混音时间等于源对齐时间加
`segment.start`。当前训练目标设计为每次发言一行，取完整原句首、末字词的边界：

```text
[S1][0.32-2.48] 你好。
[S2][1.04-3.20] Good morning.
```

原句、来源版本和音频片段必须一致，不把另一 clean 版本的标注贴到旧混音上。
只有 `aligned` 结果可构建时间目标；`needs_review`、`error` 保留为质量状态。
不能通过裁剪时间边界、删除发言或筛掉固定 dev/test 来绕过问题。

## 查询与进度

本机 `roots.json` 已配置；其他机器按 `roots.example.json` 配置
`multispeaker_synthetic`、`amphion_data`、`audio_data_contract` 三个根目录。

```bash
audio-data-contract resolve catalog sot_multispeaker_zh_en \
  synthetic-v2-timestamps-v1-20260919 alignment_inputs --roots roots.json
audio-data-contract resolve catalog sot_multispeaker_zh_en \
  synthetic-v2-timestamps-v1-20260919 preparation_state --roots roots.json
```

`alignment_inputs` 固定四个对齐任务的计划哈希、模型配置哈希、来源版本和覆盖数，
并提供 `root_alias + relative_path` 形式的进度引用。累计需对齐 2,089,307 个源片段，
其中旧英文 train 为 549,056 个，新增中文 train 为 1,495,320 个，dev/test 分别为
21,899、23,032 个。数量是源片段数，与最终混音条数不同。

`preparation_state` 是可变的准备状态，使用 `dataset-state/1.0`，因此不固定文件哈希。
实时对齐进度以输入清单指向的各任务 `progress.json` 为准；即便所有对齐任务结束，
也不自动等同于时间戳训练版本准备完成，还需要完成质量处理和目标发布。

数据处理位于 AmphionData，Catalog 只登记事实和引用，训练渲染由消费项目负责。
本轮登记过程的本地复现记录位于 AmphionData 的
`results/sot-timestamp-registration-20260919/register.py`。

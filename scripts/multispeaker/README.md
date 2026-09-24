# 1～5 人全说话人混音

从已登记的单人语音合成单通道混音，输出每位说话人的完整文字，用于 Qwen3-ASR
的全说话人微调。此入口只准备数据，不启动训练，不修改上游音频或既有 Catalog。
使用现有 preparation 依赖中的 NumPy、SciPy 和 SoundFile，生产并行入口要求 Linux。

## v2：人数、语言与重叠覆盖

[recipe-v2.json](recipe-v2.json) 按 1/2/3/4/5 人等量合成。单人样本也输出 `[S1]`，
训练模型在没有其他说话人时正确结束。多人样本中，纯中文、纯英文、中英同场占
40%/40%/20%；中英同场由不同真实 speaker ID 分别说中文或英文，保留原文，
不声称覆盖同一人的句内中英切换。单人中文、英文各半。

| 重叠条件 | 活动重叠率范围 | 多人样本中的权重 |
| --- | --- | --- |
| none | 0 | 10% |
| low | 0～20% | 20% |
| medium | 20～40% | 25% |
| high | 40～65% | 25% |
| dense | 65～100%，且存在全部说话人同时活动的帧 | 20% |

单人只生成 none。活动重叠率定义为“至少两人活动的帧数 / 至少一人活动的帧数”，
使用下文的 20 ms 能量估计。各区间内按 Beta(2,2) 抽目标，再调整完整原句的起点，
要求实测值落在该区间且与目标相差不超过 5 个百分点；达不到则重采样。
密集组还按首位说话人的句长匹配其他人的完整原句，容差为 15%，使用相同轮数，
避免短回复与长独白在数学上无法达到高重叠目标。最终仍以活动帧实测值验收。
可调整 `overlap_profiles.*.range/weight`、`overlap_beta`、`overlap_tolerance`，
`turn_gap_seconds` 控制压缩前的句间隔。目标区间包含上界不代表一定生成恰好 100%。

每位说话人按 35%/45%/20% 请求 1/2/3 条不同完整原句，受 28 秒预算限制可减少条数。
时间线上优先交替安排不同人，同一人再次发言保持原标签，且不会与自己的语句重叠。
`metadata.primary_language` 取源语句总时长较大的语言，供 Qwen3-ASR 原生语言头使用；
混合样本的 `AudioRecord.language` 仍为 `zh-en`。

策略参考 [MOSS-Transcribe-Diarize 0.9B 技术报告 §3.2](https://arxiv.org/pdf/2601.01554v7)：
借鉴轮换发言与时间轴重叠控制。原报告采样 2～12 人，按词切段、高斯间隔，局部重叠
不超过较短片段的 80%，并加入噪声、混响。本项目没有可靠词级对齐，因此保留完整原句，
使用可配置均匀间隔及整段活动重叠率，不额外加噪或混响；这不是对原配方的逐项复现。

```bash
export PYTHONPATH=$PWD/src
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
OUTPUT=/path/to/sot-multispeaker/synthetic-v2-20260915

python scripts/multispeaker/synthesize.py prepare \
  --recipe scripts/multispeaker/recipe-v2.json \
  --catalog catalog --roots roots.json --output "$OUTPUT" --workers 4 \
  --reuse-pools /path/to/sot-multispeaker/synthetic-v1-20260914
python scripts/multispeaker/synthesize.py generate \
  --output "$OUTPUT" --workers 32 \
  --train 2000000 --dev 10000 --test 10000 --shard-size 500
```

`--reuse-pools` 可省略；复用要求来源、筛选时长、随机种子和划分桶完全相同，并校验池哈希。
v2 保留 v1 的 speaker 划分，避免已经参加 v1 训练的人进入 v2 开发/测试集。
这组数量产生 62 个有效条件：训练集每种人数 40 万条，纯中文、纯英文各 84 万条，
中英同场 32 万条；开发、测试每种人数各 2,000 条。数量是独立混音数，原句会复用。

## v1：既有 3～5 人配方

```bash
export PYTHONPATH=$PWD/src
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
OUTPUT=/path/to/sot-multispeaker/synthetic-v1-20260914

python scripts/multispeaker/synthesize.py prepare \
  --catalog catalog --roots roots.json --output "$OUTPUT" --workers 4
python scripts/multispeaker/synthesize.py generate \
  --output "$OUTPUT" --workers 16 \
  --train 1200000 --dev 6000 --test 6000 --shard-size 500
```

配方固定在 [recipe.json](recipe.json)。中英文各半，每种语言的 3/4/5 人、错开起点
和密集重叠六组等量。默认生成 120 万条训练样本，开发、测试各 6,000 条。
数量是独立混音数，不等于独立原始语音数量。

## 源语料与划分

- 中文：AISHELL 20%、AISHELL-2 45%、KeSpeech 35%，使用固定版本的 train。
  当前登记的对应 clean 版本只有测试集，因此使用原训练标注，不伪称已清洗。
- 英文：Common Voice EN clean v1 占 60%，严格要求 `custom.clean.pass is True`；
  LibriSpeech train-clean-100/360 占 40%。后者的 clean 是原语料的声学子集名称，
  不代表通过本项目的自动转写清洗。
- 比例用于选择源说话人，按来源权重、说话人均匀、合格句子均匀采样。
  时长和混音质量筛选可能改变最终比例，完成分片的 `summary.json` 记录实际来源计数。
- 逐条扫描全部源 manifest，保留 2～20 秒、有文字、有 speaker ID、时间范围有效的
  单声道片段。不截断原句，不按前 N 条限制语料池，不加入噪声或混响。
- 使用 `SHA256(seed:dataset_id:speaker_id)` 固定分出 96%/2%/2% 的说话人桶，
  然后分别合成 train/dev/test。同一来源的说话人及原句不会跨 split；不同语料间
  未做声纹身份去重，不能声称跨语料自然人完全隔离。
- `heldout-speakers.json` 列出开发/测试的身份。后续普通 ASR 回放也必须排除这些
  身份，才能维持此次后训练的说话人隔离。原生基座可能见过原语料，该划分不代表
  相对基座预训练数据隔离。

## 混音和标签

v1 每条混音包含 3～5 个不同 speaker ID；每人有机会连续放入两条不同原句，句间
保留 0.3～0.9 秒间隔。同一个人的两句始终归入同一输出标签；此版本没有模拟任意
长会议中的多轮话语调度。

输入为混音本身，无 enrollment 或固定静音前缀。输出以首次能量活动时间排序：

```text
[S1] 第一位说话人的完整文字。
[S2] 第二位说话人的完整文字。
[S3] 第三位说话人的完整文字。
```

这里的标签为普通文本，不增加 tokenizer special tokens。`AudioRecord.target`
只保存正文；Qwen3-ASR 消费方渲染时再加 `language Chinese<asr_text>` 等模型前缀。
任务名为 `speaker_attributed_asr`，不能作为普通 ASR 样本套用基座 KL 约束。
消费方必须支持该任务；`open-audio-llm` 的 SOT 入口已支持。

每条成品为 16 kHz、单通道、PCM16 FLAC，最多 28 秒；超过预算则重新选样。
密集重叠允许较长原句，错开起点的样本按人数收紧单个说话人的时长预算。
按各说话人活动区域 RMS 归一化后，随机设置 ±6 dB 相对增益，再对整段统一缩放，
将峰值控制在 0.75～0.95。源音频不修改，也不另存各人音轨。

重叠统计使用 20 ms RMS 帧、相对各人峰值 RMS 的 -35 dB 阈值与 1e-5 下限：
v1 错开组要求活动帧中 15%～65% 至少两人活动；密集组要求至少 65%，并实际存在
全部 3/4/5 人同时活动的帧。该统计是合成难度的能量估计，不是人工 VAD、词级
时间戳或真实 DER 标注。非有限数、空音频、解码失败和读到的时长不足会拒绝该候选。
整文件 MP3 解码允许头部长度在一个编码帧（最多 1152 个原采样点）内的高估，
保留全部实际解码波形，并在各 segment 记录 `decode_duration_delta_seconds`；
该例外不用于局部切段、WAV 或超过一帧的缺失。
每个成品 v1 最多尝试 100 个候选，v2 为 200 个（两人高重叠仍需筛选活动密度）；
`summary.max_sample_attempts` 记录实际最大尝试次数。耗尽时记录错误并停止继续提交新工作。

`metadata.speakers` 保存说话人映射、完整正文与最终线性增益；`metadata.segments`
保存各原句的混入时间、完整时长、文字、Catalog 来源及可移植音频引用。
上游 clean 状态和混音检查分别记录，不给派生混音伪造 `clean.pass`。

## 产物与恢复

- `sources.json`、`pools/`：源 manifest 哈希、筛选计数、说话人数量和源片段池。
- `recipe.json`、`generation-plan.json`：固定的生成参数与数量。
- `train|dev|test/<language>/<人数>/<profile>/<shard>/`：FLAC、AudioRecords、
  音频索引、拒绝记录及完成统计。每 500 条一个分片。
- `catalog.jsonl`、`roots.json`：本地可消费的 Catalog 和机器路径映射。
  Catalog 只发布已完成分片，生成期间标记为 `generating`，结束后标记为 `complete`。
- `progress.json`：已完成数量、时长、PID 与更新时间；默认每完成一个分片更新。

相同命令可继续未完成的分片；分片随机种子不依赖 worker 数量和完成顺序。
已有 `summary.json` 的分片跳过，未完成分片确定性重建。重跑时不要并发启动同一
输出目录；改变配方、源语料池、数量或分片大小应使用新目录。活动运行期间不要
修改生成脚本；提交到共享 Catalog 前，等待全部完成并固定最终统计。

实现检查：`pytest -q tests/test_multispeaker_synthesis.py tests/test_multispeaker_coverage.py`，覆盖 speaker 划分、
严格 clean 标记、越界标签、3/4/5 人完整输出、两句同人归属、重采样，以及根据
源引用和增益重新构造波形并与成品逐样本比较。v2 另覆盖 1～5 人、中英同场、
全部重叠区间、目标误差、同人多轮和无自重叠。

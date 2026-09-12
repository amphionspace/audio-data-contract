# 说话人数据的通用训练入口

CN-Celeb1、CN-Celeb2、3D-Speaker、HI-MIA 和 CHiME-6 按 `audio-record/1.0` 整理。原始压缩包版本保留；处理版本为 `speaker-records-v1-20260912`，只有完整解压、音频头和记录检查通过后才登记。

本批已完成处理、登记和项目检查，本机执行记录见[处理进度](/ai_sds_wuzz/DATA_ASR/downloads/speaker-preparation-20260912/progress.md)及同目录 `complete.json`。各 split 的实测时长、记录数和说话人数以 catalog 和[数据总览](data-overview.md)为准。

## 选择数据

| 数据集 | View ID | 训练／评测入口 |
|---|---|---|
| CN-Celeb1 | `cnceleb1/speaker` | `train` 使用官方 `dev.lst`；`test`、`test_enrollment` 和 `test_trials` 保留官方评测协议 |
| CN-Celeb2 | `cnceleb2/speaker` | `train` 为官方说话人标注音频；不额外划分测试集或生成随机配对 |
| 3D-Speaker | `3dspeaker/speaker` | `train`、`test`；`test_cross_device`、`test_cross_distance`、`test_cross_dialect` 为官方验证配对 |
| HI-MIA | `hi_mia/speaker` | `train`、`dev`、`test`；`test_trials_1m`、`test_trials_mic` 为展开麦克风占位符后的官方配对 |
| CHiME-6 | `chime6/speaker` | `train`、`dev`、`test` 为带说话人标签的转写片段；对应 `*_diarization` 为完整会议与分段标注 |

以上 View version 均为 `speaker-records-v1-20260912`，血缘为 `exact`。可用入口位于 `views/speaker.jsonl`。未处理完成的数据不会提前出现在该文件中。

```bash
audio-data-contract resolve-view views catalog \
  cnceleb1/speaker speaker-records-v1-20260912

python scripts/speaker/read.py cnceleb1 train --roots roots.json
python scripts/speaker/read.py cnceleb1 test_trials --roots roots.json
python scripts/speaker/read.py chime6 dev --roots roots.json
```

读取示例返回原始记录、实际音频路径、采样率、通道数、起点和时长。它不执行重采样、音频拼接或模型推理。

## 记录与音频

- 说话人分类记录的 `task` 为 `speaker_identification`，`target` 和 `labels.speaker_id` 为 `<dataset_id>:<官方说话人 ID>`。原始 ID 保留在 `labels.source_speaker_id`。这些标识符用于语料内说话人标签，不关联真实身份。
- 声纹配对的 `task` 为 `speaker_verification`；`audio_slots` 包含 `enrollment` 和 `test`。`target` 为 `target` 或 `nontarget`，`labels.same_speaker` 为布尔值。每个标签都与源说话人 ID 核对。
- CHiME-6 片段的 `task` 为 `speaker_attributed_asr`，`target` 保留原文、标点和事件标签；`AudioRef.start`、`duration` 定位原音频片段。dev/test 使用官方 `ref` 阵列的 CH1；train 无此字段，使用按文件名排序的第一个远场通道。选择策略写入每条记录，不冒充官方指定通道。
- CHiME-6 会议记录的 `task` 为 `speaker_diarization`，`labels.segments` 保存起止时间、说话人、文本和源行号；`target` 为空。各远场通道分别作为音频槽，重叠片段保留。
- 3D-Speaker 保留官方设备、距离、方言和段落 ID。HI-MIA 原文件名及字节不变，修正的通道名称依据官方 filename mapping 写入标签。

每个版本包含一个 `audio-index.jsonl.gz`，沿用项目已有音频索引格式：`cut_id`、`root_alias`、`relative_path`、`sample_rate`、`channels`、`num_frames`、`duration`。另记录 `split` 和文件字节数。`cut_id` 是 `root_alias:relative_path` 的 SHA-256；AudioRef 通过数据集、版本、split 和 cut_id 解析，不含本机绝对路径。

实测值来自每个音频文件的头信息。保持原采样率、声道、编码和字节，不默认降噪、重采样或切成固定长度。

## 官方划分与质量处理

CN-Celeb1 按官方名单选取训练说话人，测试原始音频副本仍在索引中，标记为 `source_eval`，不写入训练清单。官方清单中的 `.wav` 引用按同一路径／文件名解析到此次 v2 包中的 `.flac`。注册音频与测试音频分开读取，不重新拼接注册音频。

HI-MIA 验证清单中的 `{}` 根据实际文件展开为麦克风 ID。两边都有占位符时使用相同麦克风 ID；固定近场注册音频与带占位符测试音频配对时，保留固定注册音频并逐麦克风展开。每条结果保存源行号和麦克风变体。这会增加评测记录数；它们不被计为新增训练音频或新增语料时长。

CHiME-6 使用此前登记的转写修复包。此版本要求片段落在该会议所有远场通道共同覆盖的时间范围内，片段和会议标签使用同一筛选结果。共排除 37 条：S21 有 1 条结束时间早于开始时间；S12 有 36 条超出较短的 U05 录音范围，其他通道可能仍覆盖这些片段。这 36 条不等于转写错误。排除项写入 `excluded-annotations.json`，保留完整源标注与原因；所有原音频和完整转写仍保留，可用于其他通道选择方案。

普通说话人数据的 train/dev/test 检查说话人集合互斥。CHiME-6 保留官方会议划分。文件和结构检查不代表重新人工审核标注质量。

时长按各入口定义统计：普通音频按文件时长，验证配对不重复累计音频时长；CHiME-6 片段按标注时长累计，重叠会重复计时，会议入口按每场一次计时。`*_diarization`、评测配对、注册音频等使用 `group` 归入父 split，避免总览重复累加。

3D-Speaker 的不同设备、HI-MIA 的不同麦克风分别计为物理音频文件，其训练时长会包含同一段话的多次录制，不等于去重后的说话内容时长。

## 位置与复现

使用本机 roots 配置中的 `legacy_asr`，默认布局为：

```text
<dataset>/source/<原版本>/                         # 已校验源包
<dataset>/work/speaker-records-v1-20260912/          # 未完成处理
<dataset>/views/speaker/speaker-records-v1-20260912/
  extracted/<源产物名>/...                         # 按原包保留目录与文件
  inventories/                                    # 解压清单、源哈希和完成凭据
  audio-index.jsonl.gz
  <split>.jsonl.gz
  excluded-annotations.json
  state.json
  registration.json
```

在仓库根目录安装依赖，并配置 `roots.json` 中的 `legacy_asr`。本机路径仅用于示例，其他机器应填写各自的数据根目录：

```bash
python -m pip install -e '.[dev,duration]'
```

```json
{"legacy_asr": "/ai_sds_wuzz/DATA_ASR"}
```

处理单套数据（逐套执行登记）：

```bash
python scripts/speaker/extract.py cnceleb1 --roots roots.json
python scripts/speaker/prepare.py cnceleb1 --roots roots.json --register
audio-data-contract generate-overview
```

解压中断后可重跑：先核对源文件长度与 SHA-256，完整归档凭据匹配时复用，未完成归档在工作目录重新处理。已发布目录不可覆盖；对已有版本执行 `prepare.py --register` 时，先复核文件产物哈希、记录数及解压文件是否齐全。本批 `scripts/speaker/run.py` 依赖已创建的 tmux 会话、任务日志目录和解压退出标记，仅用于原批次收尾；它逐套执行转换、登记和总览更新，全部完成后运行 catalog、View、总览、ruff 与 pytest 检查。

产物写入工作目录，每条 AudioRecord 校验字段、ID、引用及时间范围；关闭压缩文件后完整读取，检查 gzip CRC 和记录数，再计算 SHA-256 并原子发布。源输入哈希、转换脚本哈希、参数和排除记录随版本保存。

本批已发布产物使用的原始处理脚本保存在 Git 提交 `d9779352d50d742863141335638d2ed4e8acc000`，其文件 SHA-256 与 catalog 中的 recipe 一致。后续审查修复了输入核验和恢复登记检查；保留已发布版本的原始 recipe 与音频、清单，不将新脚本哈希回填到历史产物。

# 通用 target-ASR 数据

LibriMix 和 AISHELLMix 已按 `audio-record/1.0` 整理。训练框架只需读取纯转写和两路音频引用，无需解释 Qwen3 标签或 ShareGPT 对话。实际规模见[数据总览](data-overview.md)。

## 选择版本

| 数据集 | 通用版本 | 用途 |
|---|---|---|
| `librimix` | `960-current-audio-record-20260910` | 当前英文训练及五个测试子集，保留当前小写转写 |
| `librimix` | `960-legacy-audio-record-20260910` | 历史训练入口，保留原英文大小写 |
| `aishellmix` | `pack3-current-audio-record-20260910` | pack3 训练；历史与当前文件经逐条核对后复用同一通用表示 |
| `aishellmix` | `original-audio-record-20260910` | 原版历史训练及五个测试子集 |

对应 View ID 为 `<dataset_id>/<版本前缀>/target-asr`，例如 `librimix/960-current/target-asr`；View version 与上表通用版本相同。

训练子集为 `train_1spk`、`train_2spk`、`train_3spk`，含负样本的版本另有 `train_neg`。测试子集为 `test_1spk`、`test_2mix`、`test_3mix`、`test_2mix_neg`、`test_3mix_neg`。当前训练脚本使用双人、三人及负样本；单人数据用于保留历史数据覆盖。

`train`、`test` 是组合入口，`records_artifacts` 列出其子集。`train_base` 对应单人、双人、三人之和，不再生成一份重复的通用文件。转换会逐条核对组合文件的 ID、两路音频、转写、说话人数和负样本语义，并检查数量相等。

源文件作为对应 `*-source-20260910` 版本的产物保留。历史路径登记的是转换时的现存字节，不能证明与过去实验运行时逐字节一致。上游历史处理链标记为推断；本次源快照到通用表示的转换记录为精确血缘。

## 一条记录的含义

- `task="ts_asr"`；`audio_slots` 按顺序包含 `enrollment` 和 `mixture`，各自使用 `AudioRef`。
- `target` 是纯转写。仅移除明确的 `language …<asr_text>` 包装，保留原文字、空格、标点和大小写。
- 负样本使用空字符串目标和 `labels.target_present=false`；正样本使用 `true`。`language` 表示所属语料语言，负样本仍保留 `en` 或 `zh`。
- `labels.n_spk` 表示混合音频的说话人数；原文件已有的样本类型、说话人标签继续保留。没有证据的标签不补猜测值。
- `metadata` 保留来源文件、行号、源 ID，以及源记录已有的 CoT、utterance ID 等辅助字段。CoT 不进入 `target`，训练时是否使用由消费方决定。
- 记录 ID 为 `<子集>:<源 ID>`，避免不同子集重名。`metadata.source_record_id` 保留原 ID。

原音频保持不变。完整 enrollment 和 mixture 分别可读；截取 enrollment 前 3 秒、短音频补零、拼接 3 秒静音、重采样到 16 kHz 等原模型行为，仅保存在 `recipe_parameters.original_consumer` 中，不改变通用音频引用。

## 音频索引和路径

每个通用版本的 catalog 包含 `audio_index` 产物。各 split 的 `audio_index_artifact` 指向它，`records_artifact` 或 `records_artifacts` 指向压缩 AudioRecord JSONL。

索引同样是压缩 JSONL，每行包含：

| 字段 | 含义 |
|---|---|
| `cut_id` | 对 `root_alias:relative_path` 的 UTF-8 字节计算 SHA-256，十六进制字符串 |
| `root_alias`、`relative_path` | 音频的可迁移位置，由本机 roots 配置解析 |
| `sample_rate`、`channels`、`num_frames` | 实际音频头信息 |
| `duration` | `num_frames / sample_rate`，单位秒 |

每个版本内，同一路径只登记一次。AudioRef 的 `dataset_id`、`version`、`split` 定位 catalog 子集，再以 `cut_id` 查索引。索引不要求 Lhotse，也不需要修改协议 Schema。

新清单位于 `amphion_asr_project:data/audio-records/<dataset_id>/<version>/`；原音频复用 `legacy_asr`。两者都只在本机 `roots.json` 配置绝对路径，仓库不提交大文件。

在仓库根目录读取一条记录并解析音频：

```bash
python scripts/target_asr/read.py \
  librimix 960-current-audio-record-20260910 test_2mix \
  --roots roots.json
```

默认读取第一条，也可传 `--id`。示例按需保存所选音频的索引项，输出纯转写记录和两路音频路径。它不执行音频拼接或模型推理。

## 统计、转换与验证

`statistics.duration_hours` 按每条目标样本的 mixture 时长累加，不计 enrollment 和拼接静音。同一混合音频可以对应不同目标说话人或负样本，因此这个数不是去重后的语料时长。

`unique_mixture_duration_hours` 和 `unique_mixture_count` 按音频路径去重；父级 `train`、`test` 跨所属子集去重。子集通过 `group` 关联父级，总览不会重复累加。源快照不另填一份重复时长。

转换需要现有 `[duration]` 依赖（`soundfile`、`orjson`）：

```bash
python -m pip install -e '.[dev,duration]'
python scripts/target_asr/convert.py convert --roots roots.json --workers 16
python scripts/target_asr/convert.py register --roots roots.json
audio-data-contract generate-overview
```

源文件清单及版本固定在 `scripts/target_asr/sources.json`。`--job <通用版本>` 可单独转换一个版本。脚本拒绝覆盖已有版本；新快照应改用新版本号。中断产物留在 `data/audio-records/work/`，不会注册为已完成版本。

转换全量检查源记录格式、ID、音频头、音频引用和输入输出数量；每条结果通过 `AudioRecord.from_dict` 校验。未知标签包装、空目标与负样本标签冲突、缺失音频或组合文件不一致都会终止该版本。产物关闭并计算哈希后才发布版本目录，所有版本完成后才写入 catalog 和 View。

完成后核验压缩产物、引用和统计：

```bash
python scripts/target_asr/verify.py --roots roots.json
audio-data-contract validate-catalog catalog
audio-data-contract validate-views views catalog
audio-data-contract generate-overview --check
ruff check .
pytest -q
```

文件哈希、引用检查和格式验证不代表重新审核了转写准确率；通用版本保留源数据标注质量，不增加新的质量承诺。

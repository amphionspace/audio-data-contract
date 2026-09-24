# 数据声明目录

本目录保存 YAML 数据声明。每个声明对应一个 `dataset_id + version`，记录语言、任务、划分、文件位置和处理来源。已登记的数据见[数据总览](../docs/datasets/data-overview.md)。

## 文件格式

每个文件是一个 YAML 列表，可以包含多个版本。新文件按数据集命名，如 `example.yaml`：

```yaml
- schema_version: dataset-catalog/1.0
  dataset_id: example
  version: '1.0'
  languages: [zh]
  tasks: [asr]
  artifacts:
    - name: train_supervisions
      kind: lhotse-supervisions
      root_alias: legacy_asr
      relative_path: example/manifests/supervisions_train.jsonl.gz
  splits:
    train:
      supervisions_artifact: train_supervisions
      statistics:
        duration_hours: 12.5
```

`root_alias` 在本机 `roots.json` 中配置，`relative_path` 相对于该根目录。版本号、日期和数字样式的 ID 若表示字符串，需要加引号，如 `'1.0'`、`'2026-09-22'`。完整字段定义见 [dataset-catalog Schema](../src/audio_data_contract/schemas/dataset-catalog-1.0.json)。

`views/` 同样使用 YAML 列表；参见 [View 声明](../views/local_lhotse_views.yaml)和[数据组织规范](../docs/reference/data-organization.md)。样本清单和文件级索引仍使用 JSONL 或 JSONL.gz，Schema 与备份回执保留 JSON。

读取器加载目录顶层的 `.yaml`、`.yml`，也支持旧 `.jsonl` 声明，以便读取历史快照。同一数据版本只能登记一次。时长回填和注册脚本写入 YAML 时保留已有注释。

## 现有文件

部分文件沿用历史导入来源命名。按 `dataset_id + version` 查找数据，文件名不参与身份解析。

| 文件 | 实际内容 | 如何理解 |
|---|---|---|
| `icefall_base.yaml` | 从旧 Icefall 注册表导入的基础数据清单 | LibriSpeech、MLS、Common Voice 等数据的历史入口；数据本身不属于 Icefall |
| `icefall_runtime.yaml` | 当前 Icefall 使用的产物引用和参数快照 | 同一数据的消费配置，不是新增源语料；其中也保留了尚未独立迁移的远场数据事实 |
| `icefall_traffic_derived.yaml` | 源语料加交通噪声的派生版本 | 归入源数据集，不重复计总时长 |
| `icefall_v10_replay.yaml` | 训练数据混合和采样配方 | 属于训练配置，单独展示，不计为源数据集 |
| `open_audio_eval.yaml` | 评测程序使用的测试集入口、热词和退化版本 | 任务和产物可复用；评测入口不等于新的源数据 |
| `download_queue.yaml` | 待获取版本的下载来源、预期产物位置 | 不是下载进度文件，不能据此判断已下载、已校验或可训练 |
| `legacy_multilingual.yaml` | 历史多语言数据登记 | 包含部分时长、样本数和标点信息 |
| `local_lhotse_derived.yaml` | 本地清洗、标点、热词等派生清单 | Lhotse 是产物格式；血缘与任务通过协议字段表达 |
| `wenetspeech_weak.yaml` | WenetSpeech W 子集及其清洗版本 | 分别记录源数据与筛选证据 |
| `multilingual_multispeaker.yaml`、`alimeeting_far_raw.yaml` | 多语言、多说话人和会议源数据 | 包含来源、许可证、原始文件及已知质量问题 |
| `synthetic_asr*.yaml` | 合成语音的版本和质检产物 | 同一数据集的不同版本可能复用音频 |
| `local_lhotse_scan.json` | 历史扫描报告 | 不参与 catalog 加载 |
| `inventory/` | 文件级校验清单 | 用于追溯完整性，不作为额外数据集 |
| `backups/cos-20260914.json` | 数据版本、产物与 COS 快照的绑定 | 文件位置由云端验收回执解析，绑定不代表上传已完成；见 [COS 恢复说明](../docs/guides/cos-restore.md) |
| `librimix.yaml`、`aishellmix.yaml` | target-ASR 源快照与通用 AudioRecord 版本 | 包含训练、测试、音频索引及组合关系，见[读取说明](../docs/datasets/target-asr.md) |
| `sot_multispeaker_zh_en.yaml` | 1～5 人中英混音及独立时间戳版本 | 原版已完成，时间戳版正在准备；版本、状态和读取入口见[时间戳说明](../docs/datasets/sot-timestamps.md) |
| `cnceleb1.yaml`、`cnceleb2.yaml`、`3dspeaker.yaml`、`hi_mia.yaml`、`chime6.yaml` | 说话人源包声明与处理后的通用 AudioRecord 版本 | 源包校验见[下载说明](../docs/history/speaker-data-20260911.md)，已准备入口、音频索引和配对规则见[处理说明](../docs/datasets/speaker-preparation.md) |

## 总览的统计规则

- 同一 `dataset_id` 的版本合并展示；派生身份沿 `derived_from` 归入源数据。历史评测别名、单通道版本等没有完整血缘时，用 `provenance.dataset_family` 明确展示归属，不按文件名猜测，也不改变解析 ID。
- 不同语言子集保留独立条目，便于选数据。任务列取各已登记版本的并集，不表示每个版本都支持全部任务。
- `provenance.inventory_status=download_planned` 单列下载来源声明；它表示登记用途，不代替运行状态。下载、校验和准备进度由 `dataset-state` 表达。
- `provenance.inventory_category=training_mixture` 单列训练混合配方，不计为源数据集。
- 各版本时长单独展示，不跨版本相加。会议标注片段可能因重叠语音和多麦克风重复计时；参考表数字不当作当前文件实测值。

## 新增与更新

在对应数据集的 YAML 列表中添加新版本，保留已发布版本。修改声明不需要搬迁音频或重建样本清单。

常用字段：

| 信息 | 登记位置 |
|---|---|
| 语言、支持任务 | `languages`、`tasks` |
| 当前版本时长 | 顶层 split 的 `statistics.duration_hours`，并用 `duration_basis` 说明计时对象 |
| 过滤前参考时长 | `statistics.hours_before_filter` |
| 历史外部参考时长 | `provenance.reference_duration`：`hours`、`basis`、`url`、表格行号及查阅时间 |
| 特性和注意事项 | `provenance.description`；外部来源保留 `description_source` |
| 时长范围标签 | `provenance.duration_label`，例如“单远场麦克风标注片段” |
| 自动清洗证据 | `recipe_parameters` 中的引擎、规则；split 的通过/拒绝统计；`provenance` 中的报告位置和落地状态 |

这些展示信息使用现有 `provenance` 扩展对象，不新增必填字段。协议核心不依赖 Icefall 或 Lhotse；`recipe_parameters.icefall`、split 内的 `icefall` 和 artifact 的 `icefall_relative_to_lhotse` 是兼容适配信息，其他读取方无需解释。后续独立迁移这些适配信息时应保持既有解析接口兼容。

修改后运行 `audio-data-contract generate-overview`，同步 `docs/datasets/data-overview.md` 及同目录 `assets/` 下的两张 SVG 图。`--check` 同时校验 Markdown 和图表，缺失或过期都会失败。

Top 20 每个数据集只取最大的单项完整版本登记、参考或估算时长，不累加版本，不纳入部分划分和过滤前时长；覆盖图按“至少一个版本有完整登记 / 仅参考、估算或部分时长 / 未登记”互斥分类。两图均排除下载来源声明和训练混合配方。

# 数据声明目录

这里保存与训练框架无关的数据事实：数据集身份、版本、语言、任务、产物位置、时长和处理来源。先看[数据总览](../docs/data-overview.md)选数据，再通过声明解析具体版本和文件。

当前文件按历史导入来源拆分，**文件名不代表数据分类，也不代表多出一套数据**。读取器加载本目录下全部 `.jsonl`，按 `dataset_id + version` 定位；不会根据 `icefall`、`download_queue` 等文件名决定协议语义。

| 文件 | 实际内容 | 如何理解 |
|---|---|---|
| `icefall_base.jsonl` | 从旧 Icefall 注册表导入的基础数据清单 | LibriSpeech、MLS、Common Voice 等数据的历史入口；数据本身不属于 Icefall |
| `icefall_runtime.jsonl` | 当前 Icefall 使用的产物引用和参数快照 | 同一数据的消费配置，不是新增源语料；其中也保留了尚未独立迁移的远场数据事实 |
| `icefall_traffic_derived.jsonl` | 源语料加交通噪声的派生版本 | 归入源数据集，不重复计总时长 |
| `icefall_v10_replay.jsonl` | 训练数据混合和采样配方 | 属于训练配置，单独展示，不计为源数据集 |
| `open_audio_eval.jsonl` | 评测程序使用的测试集入口、热词和退化版本 | 任务和产物可复用；评测入口不等于新的源数据 |
| `download_queue.jsonl` | 待获取版本的下载来源、预期产物位置 | 不是下载进度文件，不能据此判断已下载、已校验或可训练 |
| `legacy_multilingual.jsonl` | 历史多语言数据登记 | 包含部分时长、样本数和标点信息 |
| `local_lhotse_derived.jsonl` | 本地清洗、标点、热词等派生清单 | Lhotse 是产物格式；血缘与任务通过协议字段表达 |
| `wenetspeech_weak.jsonl` | WenetSpeech W 子集及其清洗版本 | 分别记录源数据与筛选证据 |
| `multilingual_multispeaker.jsonl`、`alimeeting_far_raw.jsonl` | 多语言、多说话人和会议源数据 | 包含来源、许可证、原始文件及已知质量问题 |
| `synthetic_asr*.jsonl` | 合成语音的版本和质检产物 | 同一数据集的不同版本可能复用音频 |
| `local_lhotse_scan.json` | 历史扫描报告 | 不是 Dataset 声明，不参与 `.jsonl` catalog 加载 |
| `inventory/` | 文件级校验清单 | 用于追溯完整性，不作为额外数据集 |

## 总览的统计规则

- 同一 `dataset_id` 的版本合并展示；派生身份沿 `derived_from` 归入源数据。历史评测别名、单通道版本等没有完整血缘时，用 `provenance.dataset_family` 明确展示归属，不按文件名猜测，也不改变解析 ID。
- 不同语言子集保留独立条目，便于选数据。任务列取各已登记版本的并集，不表示每个版本都支持全部任务。
- `provenance.inventory_status=download_planned` 单列下载来源声明；它表示登记用途，不代替运行状态。下载、校验和准备进度由 `dataset-state` 表达。
- `provenance.inventory_category=training_mixture` 单列训练混合配方，不计为源数据集。
- 各版本时长单独展示，不跨版本相加。会议标注片段可能因重叠语音和多麦克风重复计时；参考表数字不当作当前文件实测值。

## 新增与更新

新声明按数据集命名文件，如 `<dataset_id>.jsonl`，不再按训练框架或下载队列命名。现有文件和 ID 保留，避免破坏已有读取方；无需为了修改总览搬迁音频或重建清单。

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

修改后运行 `audio-data-contract generate-overview`，同步数据清单及 `docs/assets/` 下的两张 SVG 图。`--check` 同时校验 Markdown 和图表，缺失或过期都会失败。

Top 20 每个数据集只取最大的单项完整版本登记、参考或估算时长，不累加版本，不纳入部分划分和过滤前时长；覆盖图按“至少一个版本有完整登记 / 仅参考、估算或部分时长 / 未登记”互斥分类。两图均排除下载来源声明和训练混合配方。

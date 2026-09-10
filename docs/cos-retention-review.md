# COS 同步前的版本保留与去重审阅

2026-09-10 完成首轮核查并补查警务 v5：319 条版本声明中，**100 条可复用其他保留版本的全部直接产物，210 条暂保留独立产物，9 条因路径或大小问题暂缓纳入可上传集合**。所有版本说明、View、划分和配方仍需保留。

本报告是固定范围的审计快照，输入文件见 `summary.json` 的 `input_sha256`。随后登记的 LibriMix/AISHELLMix target-ASR 8 条数据声明和 4 个 View 不在本轮范围内，不能将上述数量视为当前仓库总数。

已通过两侧文件的完整 SHA-256 确认 **480 对不同文件内容相同，合计可避免重复上传 106,554,752,743 bytes（106.55 GB / 99.24 GiB）**。本次生成建议和映射，并补正两套警务源 v5 的 13 个 catalog 路径；没有移动或删除源文件，也没有上传 COS。这不是全库音频去重已经完成的声明。

**更正：两套源 v5 实际存在，原登记路径遗漏了 `LHOTSE/`，此前据原路径判定缺失不准确。** 补正后 13 个文件的大小、完整 SHA-256 和适用的记录数均与原登记一致。`police_terms_v5` 使用的 `v5-20260830-qwen75-cosy25-split80-10-10` 也必须保留；它与使用 v3/v2 的 `police_synthetic_zh_accent` 是并存的训练入口。证据见 [police-v5-verification.json](../reports/cos-retention-20260910/police-v5-verification.json)。

## 版本处理建议

逐版本结果见 [versions.csv](../reports/cos-retention-20260910/versions.csv)，每条都有建议、理由、产物大小、覆盖它的版本、View 和血缘引用。

| 建议 | 数量 | 含义 |
|---|---:|---|
| `retain` | 210 | 有独立产物或源目录，尚无完整替代证据；保留，继续展开音频和特征依赖 |
| `reference_only` | 100 | 全部直接产物已有保留对象；保留版本说明和逻辑入口，物理文件只备份一次 |
| `hold` | 9 | 根目录未配置或大小不符；保留登记，待定位，不能用来替代旧版 |

`reference_only` 的组成：38 个历史基础入口、20 个噪声派生配方、37 个评测入口、4 个清洗视图、1 个重复的开发集入口。它们不能直接从 catalog 删除：既有 View、评测设置和血缘仍会引用这些身份。

选择物理文件的代表时，先覆盖当前运行快照和当前回放配方，再覆盖源数据、独立产物及清洗/热词版本，随后覆盖评测入口，最后处理历史重复入口。这个顺序用于选择备份代表，不是按日期判断数据质量。仅当全部直接产物已被前面保留的对象覆盖、且没有已发现的路径或大小问题时，才列为 `reference_only`。

## 已核实的空间收益

| 项目 | 字节数 | 如何使用这个数字 |
|---|---:|---|
| 直接产物中重复引用同一文件 | 10,468,870,579 | 去除重复路径及同一物理文件的别名后，可避免重复上传；本地原本就是同一文件 |
| 直接产物中不同文件的重复内容 | 30,358,480 | 比较 151 个同大小候选文件的完整 SHA-256，确认 46 对重复 |
| AliMeeting 两套源目录的重复内容 | 106,524,394,263 | 完整读取 868 个文件，确认 434 对内容相同，包含 217 对 WAV 和 217 对标注 |

后两项合计为上述 106.55 GB。第一项另列，避免把共享引用误认为可删除的磁盘副本。以上不是全库总容量，也不是当前可立即释放的磁盘空间。

具体到文件的代表路径、重复路径、大小和 SHA-256 见 [duplicates.csv](../reports/cos-retention-20260910/duplicates.csv)。这里的路径均为 `root_alias:relative_path`。

COS 端每组保存一份内容，同时保存原路径到对象的映射。恢复时必须能重建所有原路径；尤其不能仅因两个 manifest 字节相同，就改变其中相对路径的解析位置。

## 需要保留或暂缓的重点版本

| 数据 | 建议 | 核查依据 |
|---|---|---|
| AliMeeting 远场 | 合并已确认相同的 train/dev 文件；保留两边的目录映射和独有测试数据 | `alimeeting_far_raw:Train_Ali_far` 的 418 个文件、`Eval_Ali_far` 的 16 个文件，均在 `legacy_asr:AliMeeting/` 下找到相同内容；434 对全部 SHA-256 一致。`Test_2023_Ali_far` 的 40 个文件未证明被覆盖 |
| 警务合成 v3 | 保留训练音频、标注和质检信息 | `police_synthetic_zh_accent` 运行入口实际引用 v3 的 14,093 条训练音频；源文件全部存在，共 4,143,442,934 bytes |
| 警务合成 v2 | 保留独有测试集，训练音频与 v1 共享 | v2 复用 v1 的 20,000 条训练音频，另有 2,000 条测试音频；`police_synthetic_zh_accent` 运行入口实际使用 v2 测试集 |
| 警务合成 v1 | 保留源数据和独有元数据；不重复备份 v2 已引用的音频 | 20,000 个源文件全部存在，共 5,348,149,440 bytes；没有证据表明 v3 完整覆盖这些内容 |
| 警务合成 v5 QC 源 | 保留源清单和独有音频 | `legacy_asr:LHOTSE/synthetic/police_synthetic_zh_accent/v5-20260830-qc/` 下 6 个登记文件完整性匹配；14,423 个音频全部存在，共 4,752,616,834 bytes，其中 3,572 条未进入选择版 |
| 警务合成 v5 选择版 | 保留选择清单和摘要，音频与 QC 源共享 | `v5-20260830-qwen75-cosy25` 下 7 个登记文件完整性匹配；10,851 条音频全部来自 QC 源，其中 1,730 条未进入当前划分版 |
| police_terms_v5 划分版 | 必须保留当前 train/dev/test 及划分摘要 | 目录为 `v5-20260830-qwen75-cosy25-split80-10-10`；train 7,878 条、dev 658 条、test 585 条，共 9,121 个音频，全部存在，共 2,722,957,838 bytes。v10/v11 训练脚本同时包含此入口和 `police_synthetic_zh_accent` |
| WenetSpeech clean v3 | 作为当前清洗产物保留；清洗 View 复用运行快照的物理文件 | 当前运行快照已引用它的全部直接产物 |
| WenetSpeech clean v1 | 暂保留独有历史标注；源音频共享 | 固定的 `wenetspeech/clean@v1-20260805` View 仍引用该版本；独有直接文件共 540,552,956 bytes。停止保留该 View 后才适合评估退出，不能据此宣称能删除一套 WenetSpeech 音频 |
| Common Voice EN clean v1 | 保留清洗证据和视图，使用时处理已知缺口 | train 仍含筛选失败记录，test 未应用筛选结果，详见 [清洗说明](cv-en-cleaning.md)；较新的清洗命名不等于可替代原始标注 |
| 当前 v10 回放配方 | 保留配方及当前划分 | 直接引用 1,828 个文件，共 3,184,280,463 bytes。尚未验证从保留源数据完整重建这些划分，不能仅因其属于派生产物就排除 |
| AISHELL-5 | 暂缓纳入可上传集合 | 5 个本地归档的大小均小于 catalog 的 `expected_bytes`；只记录不符事实，未据此判断原因 |
| 8 个使用 managed 根目录的下载声明 | 待定位 | `managed_fast`、`managed_bulk` 尚未配置；这不等于文件不存在 |

警务音频统计完整扫描了 v1/v2/v3、两套源 v5 及 `police_terms_v5` 划分版的所有 RecordingSet，并按实际源文件去重、核查存在性和大小；未对这些 WAV 做跨文件内容哈希。专项数字见 [scoped-audio.json](../reports/cos-retention-20260910/scoped-audio.json)。

v5 的关系已按完整音频路径集合核实：划分版 9,121 条是选择版 10,851 条的子集，选择版又是 QC 源 14,423 条的子集；三个划分之间没有相同的源文件路径。因此源音频只需保存一份，各版本分别保存清单。源音频在 manifest 引用的 AmphionData 生产结果目录中，不能仅备份 `LHOTSE/` 下的清单目录。`police_terms_v5_dev` 的 `reference_only` 仅表示复用同一份 dev 文件，开发集仍保留。

另有一条独立的血缘问题：`police_synthetic_zh_accent@icefall-20260908` 的 `derived_from` 指向 v5，实际训练和测试产物却来自 v3/v2；本轮未改动此血缘声明，也不能据此推断 v5 不存在。

## 完整性缺口和既有排除项

[issues.csv](../reports/cos-retention-20260910/issues.csv) 列出 8 个未配置根目录的路径，以及 5 个大小不符的文件，涉及上述 9 个暂缓版本。两套源 v5 的 13 个缺失项已在路径补正后撤销。暂缓不代表淘汰，未确认位置的文件也不能计入节省空间。

历史扫描已经隔离的 7 个热词清单继续排除，详见 [existing-exclusions.csv](../reports/cos-retention-20260910/existing-exclusions.csv)。这些是已知不完整或未配对产物，原本就不在直接产物集合中，不能再算作本次新增节省。后续展开目录型产物时，也要保留这些排除规则。

## 本轮覆盖范围和下一步

本轮覆盖 319 条版本声明、19 个 View、2,878 次直接产物引用和 2,527 个逻辑路径。路径核查结果：2,458 个文件路径、61 个目录路径、8 个未配置根目录的路径。文件路径对应 2,454 个不同的物理文件。

已完整枚举 AliMeeting 的 7 个相关源目录，并检查警务 v1/v2/v3、两套源 v5 和 v5 划分版的源音频引用。其余目录和 manifest 内引用的全部音频、特征、原始归档尚未全量展开，因此**全库去重后容量与本地可回收空间仍为未知**。`retain` 不代表全部依赖或完整性已验证。

下一步以这份版本建议和重复文件映射为起点，展开保留版本的全部依赖；共享文件只扫描一次。先补齐 9 个暂缓版本的定位或状态，再据实际源文件生成最终 COS 上传清单。后续内容校验优先比较同大小候选，已有 SHA-256 证据仅在源文件状态仍匹配时复用。

本地源文件清理需要在保留范围、使用方依赖和 COS 备份验收完成后另行执行；本轮没有产生可直接运行的删除清单。

## 报告文件与口径

| 文件 | 内容 |
|---|---|
| [summary.json](../reports/cos-retention-20260910/summary.json) | 范围、汇总、限制及输入 catalog/View 的 SHA-256 |
| [versions.csv](../reports/cos-retention-20260910/versions.csv) | 全部 319 个版本的逐项建议 |
| [direct-artifacts.jsonl.gz](../reports/cos-retention-20260910/direct-artifacts.jsonl.gz) | 2,527 个直接产物路径的状态、大小、所有者和代表路径 |
| [duplicates.csv](../reports/cos-retention-20260910/duplicates.csv) | 480 对已完成内容校验的文件映射 |
| [issues.csv](../reports/cos-retention-20260910/issues.csv) | 本轮发现的路径与大小问题 |
| [scoped-audio.json](../reports/cos-retention-20260910/scoped-audio.json) | AliMeeting、警务合成音频专项统计 |
| [police-v5-verification.json](../reports/cos-retention-20260910/police-v5-verification.json) | v5 路径补正、完整性核验、音频集合关系及 Icefall 使用证据 |
| [existing-exclusions.csv](../reports/cos-retention-20260910/existing-exclusions.csv) | 沿用已有隔离记录的排除项 |

CSV 使用 UTF-8 BOM，便于电子表格打开。`direct_file_bytes` 仅计算直接文件，不包括目录内容和 manifest 引用的音频；`exclusive_direct_file_bytes` 指仅被该版本直接登记的文件，不能当作删除容量。`additional_direct_file_bytes_in_order` 是按上述代表选择顺序新增的直接文件量。不同版本的共享大小不能直接相加。

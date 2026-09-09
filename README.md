# 通用语音数据协议

这是一个帮助团队把语音数据说明白、管清楚的通用协议。

它不保存音频本身，而是回答这些实际问题：

- 这批数据是谁、哪个版本，能用于什么任务？
- 音频和标注放在哪里，换一台机器后怎样找到？
- 数据经过哪些清洗、筛选或组合，来源还能不能追溯？
- 文件是否完整，内容质量做过哪些检查，还有哪些已知问题？
- 训练或评测程序最终应该读取哪一种数据表示？

协议使用 JSON、JSONL 和 JSON Schema。仓库里的 Python 包只是参考工具，不是使用协议的前提；任何语言都可以按 Schema 读写同样的数据。

## 先看当前有哪些数据

[数据总览](docs/data-overview.md)按数据集展示：

- 数据集名称、语言、支持任务；
- 各版本或子集的时长，以及实测、历史登记、估算或参考值的区别；
- 标点、清洗、派生版本和已知问题等特性 / 备注；
- 单独列出的下载来源声明和训练混合配方。

清洗版、热词版、评测入口和框架配置归入所属数据集，不按版本累加成总数据量。历史文件名的含义见 [catalog 目录说明](catalog/README.md)，CV EN 的实际清洗状态见 [清洗说明](docs/cv-en-cleaning.md)。

本协议与训练框架无关。Icefall 是现有消费方之一，Lhotse 是可选产物格式；它们的兼容字段不构成其他使用方的必需依赖。

总览由 catalog 自动生成，不需要手工维护数字。修改数据声明后运行：

```bash
audio-data-contract generate-overview
```

CI 会执行 `audio-data-contract generate-overview --check`。数据发生变化但总览没有同步时，检查会失败。

## 协议怎样组织数据

可以把协议理解成五张互相关联的说明书：

| 说明书 | 它回答的问题 |
|---|---|
| 数据集声明 | 这是什么数据、哪个版本、支持什么语言和任务？ |
| 物理产物 | 音频、标注或清单放在哪个逻辑根目录下，大小和哈希是多少？ |
| 数据血缘 | 当前版本从哪里来，经过了哪些处理？ |
| 运行状态 | 数据是否已下载、校验、解包和准备完成？ |
| 样本表示 | 一条音频事实怎样稳定地变成训练或评测输入？ |

本机绝对路径不会写进协议。catalog 只保存根目录别名和相对路径，每个协作者在自己的根目录配置中把别名映射到实际位置。这样换机器、换存储或换训练框架时，不需要改数据声明。

更完整的版本、分层和逻辑视图规则见[数据组织规范](docs/data-organization.md)。

## 时长和质量怎样登记

为了让总览一直可信，新增或修改数据时遵守下面的口径：

1. 在每个顶层 split 的 `statistics.duration_hours` 中登记实际时长。
2. 如果一组数据只是某个 split 的细分，使用 `group` 指向所属 split；总览不会把父级和子分组重复相加。
3. 清洗或过滤后的版本登记处理完成后的实际时长。`hours_before_filter` 只能作为参考，不计入当前版本总量。
4. 名义或估算时长与实际时长分开登记、分开展示，不能混写成精确数字。
5. 文件哈希校验只说明文件未发生变化，不代表转写或标签正确。内容抽检、筛选结果和已知问题要分别记录。

字段与统计规则见 [catalog 目录说明](catalog/README.md)。

## 开始使用

安装参考工具和开发依赖：

```bash
python -m pip install -e ".[dev]"
```

先验证数据声明：

```bash
audio-data-contract validate-catalog catalog
audio-data-contract validate-views views catalog
```

需要在本机访问物理文件时，复制 `roots.example.json`，把根目录别名改成自己的绝对路径。通过 `--roots` 传入该文件，或设置 `AUDIO_DATA_ROOTS_FILE`。本机路径配置不要提交到仓库。

常用命令：

```bash
audio-data-contract validate-records <records>
audio-data-contract validate-state <state-file>
audio-data-contract resolve <catalog> <dataset> <version> <artifact> --roots <roots-file>
audio-data-contract verify-artifact <catalog> <dataset> <version> <artifact> --roots <roots-file>
audio-data-contract resolve-view <views> <catalog> <view> <version>
```

## 修改和提交

修改协议或数据声明时：

1. 更新 catalog、view 或 Schema，写清版本和来源；
2. 运行 `audio-data-contract generate-overview`；
3. 检查总览里的时长、任务和质量变化是否符合预期；
4. 运行 `ruff check .` 和 `pytest -q`。

版本化 Schema 位于 `src/audio_data_contract/schemas/`。新增必填字段、删除已有能力或改变字段含义时，需要发布新的 schema version；同一 schema version 内只能做向后兼容的澄清或校验修正。

## 下载、清洗与数据准备

Icefall 相关的数据处理实现统一维护在 [scripts/icefall](scripts/icefall/README.md)，
包括远场语料下载续传、会议清单、police 数据划分、manifest 规整、特征与评测集生成。
[远场数据状态及复现步骤](docs/farfield-data-preparation.md)记录当前进度和缺口。

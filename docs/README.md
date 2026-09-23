# 文档

安装和基本命令见[项目 README](../README.md)。数据集、版本和时长见[数据总览](datasets/data-overview.md)。

## 使用指南

- [本地音频准备](guides/audio-preparation.md)：提取归档中的音频，按清单生成本地副本。
- [时长统计](guides/duration-statistics.md)：统计清单或音频目录，补齐 catalog 中的缺失时长。
- [COS 恢复](guides/cos-restore.md)：查询备份位置、恢复文件、迁移清单路径。

## 数据集

| 文档 | 内容 |
|---|---|
| [数据总览](datasets/data-overview.md) | 从 catalog 生成的数据集、语言、任务和时长列表 |
| [Common Voice EN](datasets/cv-en-cleaning.md) | 清洗结果、train/test 清单差异 |
| [远场与会议数据](datasets/farfield-data-preparation.md) | AliMeeting、AMI、NOTSOFAR、RealMAN、ViTW 的准备与使用 |
| [Target-ASR](datasets/target-asr.md) | LibriMix、AISHELLMix 的版本、记录格式和音频读取 |
| [说话人数据](datasets/speaker-preparation.md) | CN-Celeb、3D-Speaker、HI-MIA、CHiME-6 的训练和评测入口 |
| [SOT 时间戳](datasets/sot-timestamps.md) | 时间戳来源、版本状态和进度查询 |
| [警言警语 V6](datasets/police-v6.md) | expanded、8h 两批数据及测试范围 |
| [V6 指令验收](datasets/police-v6-acceptance.md) | 205 条指令验收集的生成与评测约定 |

## 协议与框架接入

- [数据声明格式](../catalog/README.md)：YAML 文件结构、字段和统计规则。
- [数据组织规范](reference/data-organization.md)：Dataset、Layer、View 的身份、血缘和发布规则。
- [JSON Schema](../src/audio_data_contract/schemas/)：数据声明、View、样本与运行状态的字段定义。
- [Icefall 运行快照](integrations/icefall-runtime.md)：已有消费配置和数据缺口。
- [Icefall 数据准备工具](../scripts/icefall/README.md)：下载、划分、特征与清单生成。

## 历史记录

以下文档记录指定批次的范围和结果。文中的数量、状态和本机路径以记录日期为准。

| 日期 | 记录 |
|---|---|
| 2026-09-09 | [缺失时长核查](history/duration-missing-review.md) |
| 2026-09-10 | [COS 版本保留与去重审阅](history/cos-retention-review.md) |
| 2026-09-11 | [多语言数据补充下载](history/language-expansion-20260911.md) |
| 2026-09-11～12 | [说话人源包下载与校验](history/speaker-data-20260911.md) |
| 2026-09-14～15 | [COS 备份执行计划与记录](history/cos-upload-plan.md)，含原批次的上传命令 |

JSON、CSV 等核查证据保存在 [reports/](../reports/)，各文档链接到对应批次。

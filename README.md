# 通用语音数据协议

本项目定义一套面向语音数据生产、治理、训练与评测的通用数据协议。它将数据身份、物理位置、处理血缘、运行状态和模型输入表示分离，使数据可以跨机器、跨工具和跨团队稳定流转。

协议以 JSON、JSONL 和 JSON Schema 为边界。Python 包只是轻量参考实现和命令行工具；其他语言可以直接依据 Schema 实现兼容的生产者或消费者，无需引入 Python 运行时。

## 核心对象

| 对象 | 作用 |
|---|---|
| `DatasetSpec` | 描述带版本的数据集、任务、语言、split、物理产物和来源信息 |
| `DatasetViewSpec` | 描述源数据经过有序变换后形成的稳定逻辑视图 |
| `DatasetState` | 记录可变的下载、校验、解包和准备状态 |
| `AudioRecord` | 保存稳定、有序且与模型无关的音频样本事实 |
| `AudioExample` | 保存由样本和提示模板渲染出的多模态消息 |

数据集和 View 使用显式版本；物理产物只保存根目录别名与 POSIX 相对位置。本机根目录映射不进入版本控制，因此协议文件不携带机器路径。

## 当前数据情况

完整的数据规模、任务覆盖、完整性状态、数据集版本索引和逻辑 View 列表见[数据总览](docs/data-overview.md)。该页面由协议声明自动生成，catalog 和 view 文件是唯一事实源。

任何数据声明变动都必须同步更新总览：

```bash
audio-data-contract generate-overview
```

CI 会执行以下命令；总览缺失或内容过期时检查失败：

```bash
audio-data-contract generate-overview --check
```

## 快速开始

安装参考工具及开发依赖：

```bash
python -m pip install -e ".[dev]"
```

常用操作：

```bash
audio-data-contract validate-catalog <catalog>
audio-data-contract validate-records <records>
audio-data-contract validate-state <state-file>
audio-data-contract validate-views <views> <catalog>
audio-data-contract resolve <catalog> <dataset> <version> <artifact> --roots <roots-file>
audio-data-contract verify-artifact <catalog> <dataset> <version> <artifact> --roots <roots-file>
audio-data-contract resolve-view <views> <catalog> <view> <version>
```

根目录配置是一个从 `root_alias` 到本机绝对目录的 JSON 对象。通过 `--roots` 显式传入，或使用 `AUDIO_DATA_ROOTS_FILE` 环境变量；不要将本机配置提交到仓库。

## Schema 与兼容性

版本化 Schema 位于 [`src/audio_data_contract/schemas`](src/audio_data_contract/schemas)，并随 Python wheel 一同发布。解析器严格遵循 Schema，不会静默转换不兼容的数据类型。

同一 schema version 内只允许向后兼容的澄清或校验修正。新增必填字段、改变字段语义或删除已有能力时，必须发布新的 schema version，并保留必要的迁移说明。

更完整的 Dataset、Layer、View 组织原则见[数据组织规范](docs/data-organization.md)。

## 协作流程

修改数据或协议时，依次执行：

1. 更新 catalog、view 或 Schema，并保持版本与血缘信息完整；
2. 运行 `audio-data-contract generate-overview`；
3. 运行 `ruff check .` 和 `pytest -q`；
4. 确认生成的总览变化与本次数据变动一致后再提交。

CI 在 Python 3.10 环境中重复执行这些检查。协议消费者不受该实现语言限制，只需满足对应 JSON Schema 和行为约束。

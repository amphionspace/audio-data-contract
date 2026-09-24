# audio-data-contract

语音数据集的版本、文件位置和处理血缘管理。仓库保存数据声明、JSON Schema 和 Python 工具，音频及样本清单存放在外部数据盘或对象存储中。

数据声明使用 YAML。`catalog/` 登记数据集、版本、划分和文件引用；`views/` 记录清洗、热词等处理结果与源版本的关系。训练或评测程序通过数据 ID 和版本解析文件位置。样本记录使用 JSONL，支持逐条读取。

[数据总览](docs/datasets/data-overview.md) · [文档目录](docs/README.md) · [声明格式](catalog/README.md)

## 安装

需要 Python 3.10 或以上。在仓库根目录执行：

```bash
python -m pip install -e .
```

时长统计、数据准备和 COS 备份分别使用可选依赖 `.[duration]`、`.[preparation]` 和 `.[backup]`，安装步骤见对应文档。

## 使用

检查仓库中的数据声明和 View 引用：

```bash
audio-data-contract validate-catalog catalog
audio-data-contract validate-views views catalog
```

以 WenetSpeech 清洗版为例，查询一个已登记的 View：

```bash
audio-data-contract resolve-view views catalog wenetspeech/clean v3-20260828
```

返回结果包含 `dataset_id: wenetspeech_clean`、`dataset_version: clean-v3-20260828`，以及对应的处理步骤。以上命令只读取仓库中的声明，不需要本地音频。

访问数据文件时，在本机创建 `roots.json`，将声明中的根目录别名映射到数据盘。完整别名列表见 [roots.example.json](roots.example.json)。例如：

```json
{
  "legacy_asr": "/data/asr"
}
```

查询该版本的训练标注路径：

```bash
audio-data-contract resolve catalog wenetspeech_clean clean-v3-20260828 \
  train_supervisions --roots roots.json
```

上述配置会解析为 `/data/asr/WenetSpeech/lhotse/clean/v3-firered/wenetspeech_supervisions_L_clean.jsonl.gz`。`resolve` 只解析路径；文件就绪后，用 `verify-artifact` 核对登记的大小、哈希和记录数：

```bash
audio-data-contract verify-artifact catalog wenetspeech_clean clean-v3-20260828 \
  train_supervisions --roots roots.json
```

`roots.json` 不提交到仓库。也可以通过 `AUDIO_DATA_ROOTS_FILE` 指定配置文件。

## 仓库结构

| 目录 | 内容 |
|---|---|
| [catalog/](catalog/README.md) | YAML 数据声明：版本、划分、文件引用、时长和来源 |
| [views/](views/) | YAML View 声明：源版本、处理步骤和结果版本 |
| [src/audio_data_contract/](src/audio_data_contract/) | Python 读取、校验、路径解析工具及 [JSON Schema](src/audio_data_contract/schemas/) |
| [scripts/](scripts/) | 数据下载、转换、准备和备份脚本；[Icefall 工具](scripts/icefall/README.md)单独说明 |
| [docs/](docs/README.md) | 使用说明、数据专题、协议规范和历史记录 |
| [reports/](reports/) | 核查报告、统计结果和验收记录 |

协议字段不依赖训练框架。Icefall 适配参数与 Lhotse 文件引用用于现有数据接入；其他使用方可以按 Schema 读取声明和样本。Dataset、Layer、View 的定义见[数据组织规范](docs/reference/data-organization.md)。

## 开发

```bash
python -m pip install -e '.[dev,duration,backup]'
audio-data-contract validate-catalog catalog
audio-data-contract validate-views views catalog
audio-data-contract generate-overview
ruff check .
pytest -q
```

修改数据声明后重新生成总览；CI 使用 `generate-overview --check` 检查 Markdown 和图表是否同步。登记字段及统计口径见 [catalog/README.md](catalog/README.md)。

Schema 位于 `src/audio_data_contract/schemas/`。新增必填字段、删除字段或改变字段含义需要新版本；同一版本只接受向后兼容的修改。

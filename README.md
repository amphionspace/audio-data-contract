# audio-data-contract

`audio-data-contract` 是 icefall recipes 与 open-audio-llm 共用的轻依赖数据边界。
它将以下五类关注点相互分离：

1. 带版本的数据集标识和可移植的产物位置；
2. 本机根目录解析；
3. 可变的下载和准备状态；
4. 稳定且有序的音频样本事实（`AudioRecord`）；
5. 渲染后的多模态模型消息（`AudioExample`）。

核心包仅使用 Python 标准库，并要求 Python 3.10 或更高版本。它特意不导入
Lhotse、PyTorch、ms-swift 或 vLLM。

当前纳入版本控制的目录包含 39 个常规 icefall 数据集、20 个派生的流量/SNR
视图、包含 42 个条目的多语言旧版注册表，以及托管下载队列。icefall 快照使用
`legacy-20260804` 版本；此处有意不重复记录各 recipe 特有的标点、清洗和过滤策略。

`eval-20260804` 视图还存储了 open-audio-llm 内置的 108 个评测数据集。其产物使用
根目录别名；vLLM 在本地仅保留标点和后置过滤策略的覆盖配置。

## 根目录配置

目录条目使用 `root_alias` 和相对路径。本机 JSON 文件负责解析这些别名：

```json
{
  "legacy_asr": "/data/asr",
  "multilingual": "/data/multilingual",
  "managed_fast": "/data/managed",
  "managed_bulk": "/bulk/audio"
}
```

请将该文件显式传给 API/CLI，或设置 `AUDIO_DATA_ROOTS_FILE`。包内没有硬编码的
本机路径。

## 命令行界面

```bash
audio-data-contract validate-catalog catalog/datasets.jsonl
audio-data-contract validate-records records.jsonl.gz
audio-data-contract validate-state state/dataset@version.json
audio-data-contract inspect-download archive.tar.gz --expected-bytes 1234
audio-data-contract transition-state state/dataset@version.json downloaded
audio-data-contract resolve catalog/datasets.jsonl DATASET VERSION ARTIFACT \
  --roots roots.json
```

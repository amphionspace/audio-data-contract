# 音频数据组织规范

## 目标

本规范解决同一数据集经过清洗、过滤、标点恢复、热词提取或其他字段增强后，产生多份
manifest，却无法稳定表达身份、血缘和可用状态的问题。

协议核心不依赖训练框架或音频清单格式。数据身份、任务、时长、特性和处理血缘属于共享事实；Icefall 运行参数、采样配比、特征计算属于消费方配置。当前历史文件的边界见 [catalog 目录说明](../catalog/README.md)。

核心原则是分离三类对象：

1. **Dataset**：不可变的源数据事实和物理产物；
2. **Layer**：按稳定记录 ID 表达的一次变换；
3. **View**：源 Dataset 按顺序应用若干 Layer 后得到的逻辑数据版本。

下游依赖 View，不依赖 `/ai_sds_wuzz/DATA_ASR/.../clean`、`cleaned` 或 `hotwords`
等历史路径。

## 身份模型

### Dataset

`dataset_id` 只表示数据来源，例如 `wenetspeech`、`aishell2`。新数据不得再创建
`wenetspeech_clean`、`wenetspeech_hotwords` 这类把变换写进 Dataset ID 的身份。

Dataset 使用不可变版本：

```text
wenetspeech@upstream-20260805
aishell2@upstream-1.0
```

当前 catalog 中带 `_clean`、`_hotwords` 的 ID 是兼容性物化产物，保留但不作为新规范。

### Layer

Layer 表示一次可复现变换，至少声明：

- 名称和版本；
- 读取的父版本；
- 写入的规范字段；
- 参数、工具版本和模型版本；
- 记录覆盖范围；
- 输入与输出记录数。

字段写入使用 `AudioRecord` 规范名，不使用 Lhotse 的物理字段名：

| 规范字段 | Lhotse 兼容字段 | 含义 |
|---|---|---|
| `target` | `text` | 训练或评测目标文本 |
| `hotwords` | `custom.hotwords` | 热词列表 |
| `metadata.clean` | `custom.clean` | 清洗审计信息 |
| `labels.*` | `custom.labels.*` | 训练或评测标签 |
| `$membership` | 无 | 样本被保留或移除 |

默认禁止两个 Layer 写入同一字段；确需覆盖时，后一个 Layer 必须通过 `overrides`
显式声明覆盖字段，View 校验器会拒绝未声明的冲突。

### View

View 是面向下游的稳定入口：

```text
wenetspeech/clean@v1-20260805
wenetspeech/hotwords@v1-20260805
```

View 必须声明源 Dataset、顺序变换链、最终物化 Dataset 以及血缘状态。下游通过
`resolve-view` 获取最终物化版本，不根据文件名猜测能力。

`lineage_status` 有两种值：

- `exact`：每个工具、参数、父版本和字段写入均可追溯；
- `inferred`：从历史文件名或内容推断，只用于迁移旧数据。

## 物理目录

新任务按以下逻辑分层组织；文件格式可选，下面的 manifest 文件名仅以 Lhotse 物化为例。现有目录通过 catalog 映射，不立即搬迁：

```text
<dataset>/
├── source/<source-version>/       # 不可变上游 manifest
├── layers/<layer>/<layer-version>/
│   ├── train.patch.jsonl.gz       # 按 ID 排序的稀疏增量
│   └── manifest.json              # 参数、父哈希、计数和字段声明
├── views/<view>/<view-version>/
│   ├── recordings_<split>.jsonl.gz
│   └── supervisions_<split>.jsonl.gz
├── work/<run-id>/                 # 可变中间状态，不允许下游消费
└── quarantine/                    # 损坏、未完成或血缘不明的产物
```

约束：

- `source`、已发布 `layers` 和已发布 `views` 不可原地修改；
- 任务只写 `work/<run-id>`，校验通过后原子发布；
- `quarantine` 不进入 Dataset catalog 或 View catalog；
- recordings 未改变时不复制，通过 catalog 引用源 recordings；
- 目录名只用小写 ASCII、数字、`_` 和 `-`。

## 增量与物化

默认存储稀疏 Layer，而不是为每个组合复制完整 manifest：

```json
{"id":"sample-1","set":{"hotwords":["美静"]}}
{"id":"sample-2","set":{"target":"修正后的文本","metadata.clean":{"rules":"v2"}}}
{"id":"sample-3","drop":{"reason":"ambiguous"}}
```

完整 Lhotse manifest 是 View 的物化缓存。它可以提高训练加载速度，但必须能由源 Dataset
和 Layer 重新生成。增加新字段时，只新增 Layer；只有字段被多个下游稳定依赖时，才升级
`AudioRecord` 顶层 schema。

当前 `dataset-view/1.0` 支持：

- `materialization=full`：已经生成完整 manifest；
- `materialization=overlay`：结果以增量 Layer 表达。

旧数据先登记为 `full + inferred`，新流水线必须登记为 `exact`。

## 生命周期

```text
building → validating → ready
                 └──→ quarantine
```

来源声明可以先登记预期产物，但必须与已准备数据区分；`download_planned` 条目不宣称文件已存在。只有 `ready` 产物可作为已准备版本供下游消费。以下为 Lhotse 物化产物的发布门槛（其他格式采用对应校验）：

1. gzip 能完整读取；
2. `expected_bytes`、SHA-256 和记录数匹配；
3. 记录 ID 唯一，Layer 按 ID 排序；
4. 所有 supervision 的 recording 引用存在；
5. 输入数、删除数、新增数和输出数守恒；
6. 变换声明的字段与实际字段一致；
7. 先原子发布文件，最后发布 catalog 与 view。

中断任务只能更新工作状态，不得让下游看到半成品。可读前缀可以用于断点续跑，但在记录数
补齐前仍属于 `quarantine`。

## 下游接口

下游只需要两个选择：View ID 和 View version。

```bash
audio-data-contract validate-views views catalog
audio-data-contract resolve-view views catalog \
  wenetspeech/clean v1-20260805
```

Python：

```python
datasets = load_catalog("catalog")
views = load_view_catalog("views", datasets)
result = resolve_view(views, datasets, "wenetspeech/clean", "v1-20260805")
```

下游不得保存绝对路径、拼接 `_clean`/`_hotwords` 文件名，或自行解释变换顺序。

## 当前迁移策略

1. 保留现有物理文件和兼容 Dataset ID；
2. 用 `views/local_lhotse_views.jsonl` 统一暴露逻辑身份；
3. 未完成热词文件继续留在隔离清单，不创建 View；
4. 新增处理任务直接生成稀疏 Layer 和精确血缘；
5. 下游完成 View 接入后，再逐步停止使用历史派生 Dataset ID。

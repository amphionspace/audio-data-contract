# Lance 小范围试验，2026-09-29

**结论：保留为试验性查询后端，尚不进入正式数据或训练链路。** 已完成适配、固定 snapshot、规范 Layer 回写/重建、JSONL/Lhotse 导出，以及真实 CHiME-6 小规模验证。WenetSpeech 清洗 View 和真实规模验收尚未完成，不能据此宣称完成全部六阶段。

用户说明数据仍在传输。检查发现 `/workspace/data/dataset/` 不存在，已有目录是 `/workspace/data/datasets/`；其中没有 WenetSpeech。CHiME-6 已有原始 dev 音频和修复转写，未找到登记中的 AudioRecord 产物。本次从这些原始材料创建独立试验记录与私有 audio-index/catalog，没有修改当前 catalog、View 或训练入口。

## 范围与正确性

- CHiME-6 dev 两场会话共 **7,437 条**真实转写，14 个音频文件；每条同时引用佩戴式双通道和远场单通道音频，保留原始 start/duration。无越界记录，原始数据中无空转写；空转写负样本由契约测试验证。
- 导入和 14 次更新后，与对应 JSONL 的 ID 集合及完整 AudioRecord 均一致。
- 全部记录的音频引用用现有 `scripts/target_asr/read.py` resolver 核对，JSONL/Lance 解析结果一致。
- 两份 Lhotse 导出各 7,437 个 cuts，均经 Lhotse 1.33.0 `validate`；每份实际加载第一条音频，分别得到 `[2, 51520]` 和 `[1, 51520]`。
- 36 项相关测试通过，覆盖原有 records/View 兼容性以及重复 ID、字段/父子路径冲突、固定旧版本、空表/全删除、patch 哈希、源变更、merge 失败、提交后侧车发布失败与重建。
- 清洗字段、文本修正、删除和多个 View 读取同一 snapshot 的机制通过契约测试；本次真实 CHiME-6 只回写试验质量字段，没有运行生产清洗模型。

## 性能

Python 3.12.3、pylance 12.0.0、PyArrow 25.0.1，本地存储；每项重复 7 次，未清空缓存。以下单位为毫秒，均包含 AudioRecord 解码。JSONL ID 查询与 Lance 一样完整消费匹配迭代器，不采用找到第一条即退出的特例。

| 操作 | JSONL p50 / p95 | Lance p50 / p95 |
| --- | ---: | ---: |
| 全量扫描，7,437 条 | 272.5 / 334.7 | 224.3 / 250.9 |
| language/task/split，命中全部 | 272.4 / 330.1 | 249.6 / 306.0 |
| 单 ID 查询 | 261.9 / 294.6 | 4.5 / 9.1 |
| 64 ID 查询 | 243.7 / 281.9 | 8.7 / 11.1 |
| 单条字段更新 | 476.2 / 570.0 | 24.9 / 59.7 |
| 64 条字段更新 | 523.0 / 559.8 | 43.5 / 45.9 |

两种回写使用同一规范 patch，表中更新耗时不含共同的 Layer 准备/发布；该步骤单条 p50 为 5.8 ms，批量为 19.7 ms。

原始数据没有 `metadata.clean.pass`，因此该查询命中 0 条（原始结果仍保存在 JSON 中），**不将这项测量用作清洗筛选收益证据**。language/task/split 命中全量，也未验证混合语言/任务下的实际选择性。

JSONL 全量物化 0.549 秒，新增重复副本 6,073,897 字节；Lance 导入含 ID/字段校验为 2.253 秒，初始表 5,914,790 字节。14 次增量提交后表为 6,347,423 字节，增加 432,633 字节；未建索引，索引额外存储为 0。整个 benchmark 进程 RSS 峰值 689,080 KiB，包含库初始化、两种后端及验证步骤，不能当作单独后端的峰值对比。

单条/批量选择性查询及字段更新在这个小样本上有优势；全扫描差别不大。尚不能外推至约 9,278 万条、压缩源 JSONL、大规模生产清洗批次、冷缓存或长期历史版本积累。

## 复现与待验收项

```bash
pip install -e '.[lance,dev]'
python scripts/lance_chime6_pilot.py \
  /workspace/data/datasets/chime6/source/speaker-records-v1-20260912/extracted \
  /new/chime6-pilot
python scripts/benchmark_lance.py /new/chime6-pilot/records.jsonl \
  /new/chime6-benchmark --source-view 'chime6/lance-pilot@dev-v1' --repeats 7
pytest tests/test_lance.py tests/test_records_render.py tests/test_views.py -q
```

实际试验产物位于 `/tmp/audio-contract-chime6-lance-pilot-20260929` 和 `/tmp/audio-contract-chime6-lance-benchmark-final-20260929`。这些是本机临时实验目录，不是正式注册产物；指标副本保存在本报告目录：

- [JSONL 基线](baseline.json)
- [完整性能和一致性结果](results.json)
- [真实数据准备范围](preparation.json)
- [音频引用与 Lhotse 验证](audio-acceptance.json)

待数据到齐后，用真实 WenetSpeech 清洗 View 和规范 Layer 重跑，测量实际清洗选择率、JSONL.gz、全规模单条/批量读取回写、独立进程峰值内存和历史存储增长，再决定是否正式采用。当前支持边界、失败恢复和导出示例见 [使用说明](../../docs/lance-materialization.md)。

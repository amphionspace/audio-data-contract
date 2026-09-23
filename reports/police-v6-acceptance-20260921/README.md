# 用已有测试音频补齐警言警语 V6.0

已补入 **330 条已有测试音频**，与 OBS 的 14,281 条组成 **14,611 条**本机评测清单。
1,542 个要求中，**1,330 项有原句/明确读法或术语上下文，20 项仅有改写，192 项缺音频**。

缺口集中在 20260915 新增的 205 条指令：2 条有原句（开始录像、开始录音），
20 条只有改写，183 条缺音频。其余历史内容还有 9 项缺音频。

请用 [合成清单](synthesis_requests.tsv) 安排后续处理：192 项补音频，20 项补原句，
共 212 项。原文件中的“机构层级、主要警种、接警环节、反馈与归档、案件分类、
网络犯罪类型”6 项疑似分组标题，已标为“确认范围”；确认需要朗读后再合成。
本报告保留原文条目，不擅自将这些项目从覆盖分母删除。

以用户指定的 OBS 交接包为基础，保留其全部有真值样本，仅从 catalog 已登记的
警务 `test` 划分补充未覆盖内容。没有调用合成服务，没有挪用 train/dev 样本。

## 产物

- [逐项覆盖](coverage.tsv)：包含原始行号、原文、基础包音频数、补齐后音频数及来源。
- [缺音频清单](missing.tsv)：目前没有匹配音频的条目，优先安排合成。
- [仅改写覆盖](paraphrase_only.tsv)：已有来源标注和自动质检通过的改写，但缺原句音频。
- [新增 205 条指令](v6_new_commands.tsv)：单独列出 20260915 新增部分。
- [统计](summary.json)、[来源及校验](provenance.json)、[要求与读法](requirements.jsonl)。
- [产物核验](verification.json)：基础包完整保留、样本与音频无重复、配对清单一致，
  补充样本全部来自 test；全部 14,611 条入选音频已计算 SHA-256，脚本 Ruff 检查通过。

本机可直接使用 `state/police-v6-acceptance-20260921/combined/pairs.tsv`，
三列为 `item_id / audio_path / text`。`manifest.jsonl` 还保留逐条来源、SHA-256、
原始元数据及要求对应关系；`supplement.jsonl` 只列新增样本。音频路径为本机绝对路径，
引用下载后的 OBS 音频和现有测试音频；这些本地数据不随 Git 分发。

## 覆盖口径

原文件经既有解析器去重为 1,533 项，特殊代码一行拆成 10 个指定读法后为 1,542 项。

1. **原句或明确读法**：仅忽略大小写、空白、常用标点，或匹配清单中明确列出的读法。
2. **术语在句中出现**：用于行业词汇、应用/UI 名称、特殊代码，以及 20260731 的
   “签警单/签警情”术语；不据此判定 20260915 新增操作指令覆盖。
   特殊代码仅匹配基础包中明确标为 `special_codes` 的测试材料。
3. **来源标注的改写**：已有 `source_metadata.text` 对应原要求，且自动质检 `clean.pass`
   通过。此类单独统计，不能替代原句逐条验收。
4. **缺音频**：上述证据均不存在。不使用模糊相似度或模型识别结果推定覆盖。

对于基础包尚未覆盖的条目，优先选择原句/读法，最多补入 10 个不同说话人标签的已有音频。
这个上限不是验收所需的最低样本量。已覆盖也不表示口音、噪声、设备和说话人覆盖充分。
历史合成音色可能与训练复用，本次不声明全局训练隔离或人工听审通过。

## 复现

OBS 归档地址及 SHA-256 见 provenance；归档内目录名是 `asr_testsets_handoff_20260821`，
与上传日期不同。解包后运行：

```bash
.venv/bin/python scripts/build_police_v6_acceptance.py \
  --handoff state/police-v6-acceptance-20260921/obs/asr_testsets_handoff_20260821 \
  --requirements reports/police-v6-acceptance-20260921/requirements.jsonl \
  --output state/police-v6-acceptance-20260921/combined \
  --report reports/police-v6-acceptance-20260921
```

脚本读取本机 `roots.json` 及 catalog，保留 test 划分，按音频 SHA-256 去重，
核对 OBS 音频的清单哈希，并拒绝同音频不同真值的冲突。
`police_terms_v5_dev` 虽在消费登记中暴露为 test，实际引用 dev 文件，本次排除。

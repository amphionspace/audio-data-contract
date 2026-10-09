# 警务数据统合版

`police_asr_unified@v1-20261009` 把目前所有警务合成批次（V1–V6）合并成一个数据集，只分 train、dev、test 三个集合。三个集合之间的录音 ID、说话人和规范化文本（去掉标点和空白后的文本）都不重叠。音频没有复制，manifest 直接引用 `aidc_data` 下已有的文件。

| 集合 | 条数 | 时长（小时） | 说话人 | 不同文本 |
|---|---:|---:|---:|---:|
| train | 365,341 | 657.9 | 384 | 62,570 |
| dev | 36,086 | 65.3 | 48 | 4,463 |
| test | 47,006 | 82.4 | 158 | 7,093 |

声明文件：[police_asr_unified.yaml](../../catalog/police_asr_unified.yaml)。每个来源的输入数、保留数和丢弃原因记录在 `build_report` artifact 里。

## 组成

| 集合 | 来源 |
|---|---|
| train | police_terms_v5、旧业务补量 100k、V6 expanded、V6 8h 的 train；过滤后的 v1、v3、v5-qc |
| dev | police_terms_v5、旧业务补量 100k、V6 expanded、V6 8h 的 dev |
| test | 以上四批的 test，加上 v2 test 和 V6 205 条指令验收集 |

- dev/test 沿用各批次原有的 384/48/48 说话人划分。v2 test 和验收集用的是独立的 110 人音色池，所以 test 有 158 个说话人。
- v1、v3、v5-qc 原本没有划分，480 个音色都放在训练里。合并时，凡是说话人或文本出现在 dev/test 的样本都会去掉，v5-qc 中与 police_terms_v5 重复的样本也会去掉。police_terms_v5 train 中有 3 条与 v2 test 文本相同的样本，也已去掉。
- 每条 supervision 的 `custom.source_dataset`、`source_version`、`source_split` 标明原始批次，可以按原集合分别统计结果。

以下内容没有合并：

| 内容 | 原因 |
|---|---|
| `police_robust_monitor` | 是 60 条 v2 test 的加噪副本，只用于监控 |
| 按 TTS 拆分的子集 | 与合并后的集合重复 |
| `v5-20260830-qwen75-cosy25` | 是 v5-qc 的子集 |
| icefall 消费版本 | 与源版本是同一批文件 |

## 读取

```bash
audio-data-contract resolve catalog police_asr_unified v1-20261009 \
  train_supervisions --roots roots.json
```

roots 中 `aidc_data` 指向 `/workspace/data`。重新生成请运行 `python scripts/build_police_unified.py`。

## 使用边界

全部是合成语音，只经过自动质检，没有人工听审。验收集的文本是原指令及其读法变体，不能作为未见语义的泛化测试。

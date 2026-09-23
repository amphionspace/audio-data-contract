# V6 全部 205 条指令验收

`police_v6_acceptance_205` 是 test-only 数据集，覆盖《警言警语-V6.0.txt》中
`20260915新增` 的全部 205 条指令。源版本 `v6-acceptance-20260921`，
Icefall 消费版本 `icefall-20260908`，仅提供 test split，不用于训练。

AmphionData 的 `scripts/synthetic/run_police_v6_acceptance.py` 负责合成及独立
Qwen3-ASR 自动质检。每条指令生成 22 个音色，导出要求每条至少 10 个合格音色。
具体数量、拒绝数量及逐指令覆盖在 catalog 的 coverage artifact 中。
未进行人工听审，不依据待测模型识别结果筛选音频。
验收保留要求中的原始参数，包括车牌示例；仅做读法变体。生成端替换过参数的
音频保留追溯记录，但不进入验收 manifest。首轮不足 10 个合格音色的指令
使用参考池内尚未使用的说话人补量。逐指令等权平均与按音频统计分别展示，
避免补量改变指令权重。

参考池为 `nationwide_test_v1_110`，与 V6 生产使用的 480 人池 ID 不重合；
不宣称说话人在全部通用训练语料中未出现。原句及读法变体可能在训练中出现，
此集评估已学指令在新合成音频上的表现，不应称为未见语义泛化测试。
原有 expanded/8h 留出测试集保留不变。仅评测 Transducer，固定 v11/v14 epoch-4。

注册入口：

```bash
python scripts/icefall/register_police_v6_acceptance.py --amphion-data /path/to/AmphionData
```

注册前核验 205 条覆盖、每条音色数、音频存在、16 kHz、manifest ID 对齐；
catalog 保存 manifest 哈希、大小和数量。消费方只通过 contract adapter 获取路径。

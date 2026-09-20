# 警言警语 V6 合成指令数据

两批数据均已生成，注册来源为 AmphionData。通过 catalog 解析 manifest，
消费方不另行维护数据路径或划分表。

| 数据 ID | 源版本 | train | dev | test | 测试时长 |
|---|---|---:|---:|---:|---:|
| `police_v6_expanded` | `v6-expanded-20260915` | 16,000 | 2,000 | 2,000 | 2.38 小时 |
| `police_v6_8h` | `v6-8h-20260915` | 231,090 | 23,428 | 28,648 | 41.13 小时 |

声明文件：[新表达批次](../catalog/police_v6_expanded.jsonl)、
[八小时扩量批次](../catalog/police_v6_8h.jsonl)。每个文件同时提供源版本和
`icefall-20260908` 消费版本，二者引用同一批音频和原始划分，不应重复计数。

## 读取

在本机 roots 配置中将 `amphion_data` 映射到 AmphionData 根目录。
从 contract 根目录解析测试标注：

```bash
audio-data-contract resolve catalog police_v6_8h v6-8h-20260915 \
  test_supervisions --roots roots.json
audio-data-contract verify-artifact catalog police_v6_8h v6-8h-20260915 \
  test_supervisions --roots roots.json
```

音频清单对应 `test_recordings`。训练和验证使用 `train_*`、`dev_*`。
Icefall 使用现有 catalog adapter，测试数据 ID 为 `police_v6_expanded`
或 `police_v6_8h`；无需添加本地注册表或修改模型代码。

## 评测边界

源要求为 `警言警语-V6.0.txt` 的 `20260915新增` 部分，文件 SHA-256
记录在源版本的 provenance 中。数据涵盖警单选择、开关镜头摄录、媒体配置、
预录延录、AI 求助标记打点、查询系统工具六类业务。

两批 test 分别覆盖 19、20 条源指令的多种表达，**不是全部 205 条指令的逐项
验收集**。测试为 Qwen3-TTS 合成语音，经自动语义和 ASR/动作对象参数质检，
不代表真实现场效果。部分指令的 `target_terms` 为空，不能仅以旧术语召回率
衡量结果；动作、对象、参数可从 supervision 的 `custom` 元数据获取。

保留原有 train/dev/test 划分。注册时核验了清单大小、哈希、数量、ID 对应，
以及每批内部 ID、文本、说话人和语义组的划分隔离；两批测试音频均存在且非空。
历史参考音色可能复用，任意合并历史训练数据前仍需检查与评测的交叉。
本次未重新生成人声、修改标注或进行全量人工听审。

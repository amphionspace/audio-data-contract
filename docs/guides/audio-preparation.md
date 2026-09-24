# 按 manifest 准备原始音频副本

这两个命令只改变原始音频的访问位置，不重编码、不修改标注或训练配置，也不更新 catalog。原数据仍是权威来源，生成的音频和 manifest 是可重新生成的运行环境数据。

先预提取 Chuan/Wu 的 archive 来源：

```bash
audio-data-contract extract-audio \
  --manifest /data/chuan.jsonl.gz /data/wu.jsonl.gz \
  --cache-dir /local/extracted-audio \
  --output-dir /local/extracted-manifests \
  --workers 4
```

按需复制训练语音和增强音频到调用方指定的目录：

```bash
audio-data-contract localize-audio \
  --manifest /local/extracted-manifests/chuan.jsonl.gz \
             /local/extracted-manifests/wu.jsonl.gz \
             /data/musan.jsonl.gz /data/traffic.jsonl.gz /data/rir.jsonl.gz \
  --cache-dir /local/training-audio \
  --output-dir /local/training-manifests \
  --workers 4
```

如果预提取目录已经是训练所需的本地位置，可直接使用预提取 manifest，不必再复制一次。

## 支持范围

- 输入为 `.jsonl` 或 `.jsonl.gz` 的 CutSet、RecordingSet。支持 MonoCut、MultiCut、MixedCut 中的 recording、PaddingCut，以及 `ReverbWithImpulseResponse` 中携带的 Recording/Cut。
- MUSAN、交通噪声和 RIR 可作为独立 manifest 一并传入；不会自动发现训练配置中未传入的外部 manifest。
- `extract-audio` 支持固定的 `tar -xOf ARCHIVE MEMBER` 和 `dd if=ARCHIVE iflag=skip_bytes,count_bytes skip=OFFSET count=SIZE status=none` 模板，以及现有生成脚本的 `timeout --signal=TERM --kill-after=Ns Ns` 包装。路径允许 shell 引号，但命令仅用于参数解析，绝不执行 shell。已有 file 来源保持原样。
- `localize-audio` 只接受 file 来源；command 应先预提取。URL、其他 command 或不支持的 manifest 结构会明确报错，不丢弃样本。
- 相对音频路径按调用时的工作目录解析，也可使用 `--source-root /original/working/directory`。它不默认相对于 manifest 所在目录。预提取保留的 file 来源仍使用原来的路径语义。
- 输出保持记录顺序及其他 JSON 字段，只有音频来源的 `type/source` 改变；JSON 空白格式不保证一致。已有变换继续在线执行。

## 去重、重跑和发布

普通文件按解析后的真实路径去重，tar 按 archive 路径和成员名去重，dd 按 archive 路径和范围去重。不按内容哈希合并不同源文件，也不合并 tar 与 dd 两种不同表达。

音频通过同目录临时文件写入后原子落盘，再写入 `.complete.json` 完成记录。重跑核对来源身份、源大小和修改时间、目标大小，匹配时复用；不重新读取完整文件计算哈希。残留 `.partial-*` 文件和没有完成记录的目标不会被视为完成。此机制处理准备中断，不检测大小及修改时间均未改变的源内容替换，也不检测本地副本等长内容损坏；字节哈希校验属于验收步骤。

所有输入的依赖准备成功后，才将暂存 manifest 目录整体发布到 `--output-dir`。失败返回非零状态，并输出原因；已完成音频保留，供再次运行相同命令复用。

最终输出目录必须不存在。成功后再次生成 manifest 时使用新的输出目录，仍可共享原缓存。输入 manifest 不能同名；发生冲突时分次调用并共享缓存。`--cache-dir` 不能位于待发布的输出目录内。同一缓存目录不支持多个准备进程同时写入；单次调用内用 `--workers` 控制并发，默认 4。

源数据应在准备期间保持稳定。工具不提供缓存版本管理、后台清理或训练入口切换功能。调用方自行选择新 manifest。

## 摘要与验收

命令向标准输出打印 JSON 摘要；成功目录另存 `summary.json`，包括输入到输出的映射。`references` 是遍历到的 AudioSource 引用次数，`unique_files` 是去重后的来源对象数（包括预提取中保持原样的 file 来源）。`copied`、`extracted`、`reused`、`unchanged` 及对应的 `_bytes` 分别记录各类数量和字节数。失败时保留已取得的统计，并给出 manifest、记录 ID、来源和原因；输入解析遇错即停止。

本仓库测试覆盖结构保持、嵌套 RIR、字节与波形一致性、去重、中断恢复及失败发布：

```bash
pytest tests/test_audio_prepare.py tests/test_cli_state.py -q
```

真实训练验收由调用方指定数据范围、目录和现有 icefall 复测命令。在相同 batch 顺序、随机条件和增强配置下比较 128 个 batch 的身份及特征哈希，分别复测冷/热缓存吞吐，并记录准备耗时和空间占用。已有 0.92 秒/步结果仅作为实验基线，不是跨环境硬性门槛。

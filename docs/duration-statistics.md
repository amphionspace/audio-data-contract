# 并行时长统计

`audio-data-contract stats-duration` 支持清单、音频目录及 catalog 三种输入。
清单汇总现有片段时长；音频目录读取文件帧数和采样率，不解码完整波形。
结果表示对应清单或目录的时长，不表示去重后的独立语音总量。

## 使用方式

```bash
python -m pip install -e ".[duration]"

# 统计缺失登记，先输出报告
audio-data-contract stats-duration --catalog catalog --roots roots.json --output /tmp/duration-report.json

# 统计并补登记，更新总览
audio-data-contract stats-duration --catalog catalog --roots roots.json --write --output /tmp/duration-report.json

# 一个或多个清单，支持普通 JSONL 和 gzip
audio-data-contract stats-duration --manifest /data/a.jsonl.gz /data/b.jsonl --output /tmp/manifests.json

# 一个或多个音频目录
audio-data-contract stats-duration --audio-dir /data/audio --workers 128 --output /tmp/audio.json
```

省略 `--workers` 时使用 CPU affinity 允许的全部逻辑核心。统计命令不更改服务器配额。
报告中的 `resources` 给出可见核心数和 cgroup v2 配额；`average_cpu_cores` 是本次统计的 CPU 时间除以墙钟耗时，`cgroup_throttling_delta` 记录所在 cgroup 的节流增量，可能包含同组其他进程。
进度写入 stderr，JSON 结果写入 stdout 或 `--output`。

## 统计口径

- catalog 只补缺失的顶层 split，跳过子分组、下载计划和训练混合配方；已有 `hours` 或 `duration_hours` 不覆盖。
- 同一划分优先使用 cuts，其次 supervisions，最后 recordings。清洗规则 `custom.clean.pass=false` 表示排除未通过样本；无法解释的过滤规则不自动回填。
- cuts 和 supervisions 按片段累计，重叠语音可能重复计时；MixedCut 按混音时间轴长度统计，不相加各音轨。音频文件按帧数除以采样率统计，多声道不乘声道数。
- 同一清单、同一过滤条件只计算一次，结果可复用于多个版本。不同版本不累加为数据总量。
- 没有清单时，仅支持范围明确且没有进一步划分规则的 `source-directory`。其他目录类型暂不自动推断。
- 音频目录递归扫描常见音频后缀，不跟随目录符号链接；同一输入目录内重复指向同一文件的符号链接只计一次。不同输入目录独立报告，不自动判断内容重复。
- 空输入、损坏清单、缺失文件、无效时长和不支持的音频格式均记录为失败。失败来源的成功部分仅供排查，不回填对应划分。

## 并行方式

普通 JSONL 按字节范围分块并对齐换行边界；小 gzip 文件按文件并行，大 gzip 由独立进程通过 rapidgzip 同时解压，再分块交给解析进程池。解压与解析共用并行预算。音频元信息按文件批次并行读取。

解压分块优先通过共享内存传递，避免大块 JSON 在进程间反复序列化。根据 `/dev/shm` 可用空间限制共享块数量，无可用共享空间时通过有界队列传递。待解析任务最多为解析进程数的两倍，避免将全部清单装入内存。

解析使用 orjson，汇总使用 `math.fsum`；不创建长期缓存或修改源数据。实际速度受到文件规模、存储延迟、gzip 压缩结构和 CPU 配额影响。

## 本服务器实测（2026-09-09）

服务器可见 128 个逻辑 CPU，当前容器 cgroup 配额为 60 核当量。以下每次清单测量前读取压缩文件预热；音频先读取元信息预热，再依次运行单 worker 和并行统计。时间包含统计进程池启动和结束，不包含预热。

| 输入 | 有效记录 / 文件数 | 1 worker | 128 workers | 提速 |
|---|---:|---:|---:|---:|
| GigaSpeech2 印尼语训练清单，单个 gzip | 1,811,202 | 2.88 秒 | 0.92 秒 | 3.1 倍 |
| 174 个 gzip 清单 | 7,166,427 | 17.10 秒 | 2.68 秒 | 6.4 倍 |
| RIRS 音频目录 | 284 | 0.18 秒 | 0.19 秒 | 无提速 |
| THCHS-30 训练音频目录 | 10,000 | 5.30 秒 | 0.80 秒 | 6.6 倍 |

以上串行与并行结果一致。少量且已缓存的音频元信息读取很快，进程启动开销可能抵消并行收益；这些单次测量不代表所有存储环境的固定加速比。

本次 catalog 集成运行处理了 92,780,185 条有效记录，用时 **21.52 秒**，平均约 431 万条/秒、26.3 核，所在 cgroup 发生 27 次节流。任务启动和收尾并不会持续占满核心；当前配额也不允许持续使用服务器全部 128 核。

首轮补齐 **189 个版本、262 个划分**，并同步总览。随后对剩余 102 个划分逐项定位：**79 个已补登记、14 个有实际文件但待统计、9 个找不到文件的旧入口已移除**。详见[完整定位与处理清单](duration-missing-review.md)。

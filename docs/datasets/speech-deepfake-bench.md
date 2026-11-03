# 伪造语音检测评测集（speech_deepfake_bench）

`speech_deepfake_bench@v1-20261103` 收录两个伪造语音检测（anti-spoofing / speech deepfake detection）排行榜使用的公开评测集，只用于评测，不进训练：

- [SpoofRadar v1.0](https://tefficlabs.com/spoofradar#leaderboard)：16 个评测集，2,460,822 条；
- [Speech-DF-Arena](https://huggingface.co/spaces/Speech-Arena-2025/Speech-DF-Arena)：14 个评测集，2,341,286 条。

任务是二分类：每条记录的 `target` 为 `bonafide`（真人语音）或 `spoof`（伪造语音），两个榜单都以 EER 为主指标。对应的测试集登记是 amphion-eval 的 `deepfake-detection/spoofradar@v1-20261103` 和 `deepfake-detection/df-arena@v1-20261103`。

## 内容

| split | 集合 | 条数 | 真人 | 伪造 | 时长 | 用于 |
|---|---|---:|---:|---:|---:|---|
| `asvspoof2019-la` | ASVspoof2019-LA | 71,237 | 7,355 | 63,882 | 61.5 h | 两者 |
| `asvspoof2021-la` | ASVspoof2021-LA | 148,176 | 14,816 | 133,360 | 111.8 h | 两者 |
| `asvspoof2021-df` | ASVspoof2021-DF | 533,928 | 14,869 | 519,059 | 454.4 h | 两者 |
| `asvspoof5-eval` | ASVspoof5-Eval | 680,774 | 138,688 | 542,086 | 1340.8 h | 两者 |
| `add2022-t1` | ADD2022-T1 | 109,199 | 31,334 | 77,865 | 106.6 h | 两者 |
| `add2022-t3` | ADD2022-T3 | 126,861 | 20,776 | 106,085 | 116.3 h | 两者 |
| `add2023-r1` | ADD2023-R1 | 111,976 | 80,000 | 31,976 | 171.4 h | 两者 |
| `add2023-r2` | ADD2023-R2 | 118,477 | 87,500 | 30,977 | 161.7 h | 两者 |
| `for-norm` | FoR | 4,634 | 2,264 | 2,370 | 2.7 h | SpoofRadar |
| `for-norm-dfarena` | FoR | 4,528 | 2,264 | 2,264 | 2.6 h | DF-Arena |
| `codecfake` | Codecfake | 304,241 | 92,596 | 211,645 | 296.7 h | 两者 |
| `librisevoc-test` | LibriSeVoc | 18,487 | 2,641 | 15,846 | 48.9 h | SpoofRadar |
| `librisevoc-all` | LibriSeVoc | 92,407 | 13,201 | 79,206 | 242.9 h | DF-Arena |
| `dfadd` | DFADD | 3,755 | 755 | 3,000 | 4.2 h | 两者 |
| `sonar` | SONAR | 3,948 | 2,274 | 1,674 | 8.0 h | 两者 |
| `in-the-wild` | In-the-Wild | 31,779 | 19,963 | 11,816 | 37.9 h | 两者 |
| `xmad-bench` | XMAD-Bench | 102,220 | 51,110 | 51,110 | 229.3 h | SpoofRadar |
| `spoofceleb` | SpoofCeleb | 91,130 | 9,113 | 82,017 | 66.1 h | SpoofRadar |

音频文件共 2,534,742 个（两个榜共用的只存一份）。

两个榜单共用这份数据。SpoofRadar 的评测池是 DF-Arena 的 14 个集合再加 XMAD-Bench 和 SpoofCeleb；共有的 14 个集合里 12 个样本完全相同（DFADD 在 DF-Arena 里是同一批语句转成的 wav；SONAR 的 OpenAI 子集 600 条原始文件其实是 MP3 数据、扩展名写成 `.wav`，DF-Arena 用的 `OpenAI_fixed` 是它们的转码版，这里保留原始文件），只有两处不同，各登记一个 split：

- Fake-or-Real：SpoofRadar 4,634 条（`for-norm`），DF-Arena 少 106 条伪造，4,528 条（`for-norm-dfarena`）；
- LibriSeVoc：SpoofRadar 用 18,487 条测试划分（`librisevoc-test`），DF-Arena 用全部 92,407 条（`librisevoc-all`）。

## 样本清单与标签

两个榜单的官方 protocol 原样保存在 `source/protocols/`：

- `spoofradar-v1.0/`：SpoofRadar 的 protocol 包（`https://tefficlabs.com/api/protocol-packages/v1.0`，2026-09-22 生成），每个集合一个 `sample_id,score` 表，sha256 与包内 `MANIFEST.txt` 一致。SpoofRadar **不公开标签**。
- `df-arena/`：DF-Arena 工具仓库 `Speech-Arena/speech_df_arena` 的 `protocol_files/*.csv`，带标签，路径是维护者机器上的绝对路径。

标签按以下顺序取得，并逐条交叉核对，任何一处不一致构建就失败：

1. DF-Arena protocol 中列出的条目用它的标签；
2. 其余条目（SpoofRadar 独有的 XMAD-Bench、SpoofCeleb，Fake-or-Real 多出的 106 条）按数据集自己的目录约定：Fake-or-Real 与 XMAD-Bench 的 `real/` / `fake/`，SpoofCeleb 的攻击编号 `a00`（真人）/ `a01`–`a23`（TTS），LibriSeVoc 的 `gt/`，DFADD 的 `DATASET_VCTK_BONAFIDE/`，SONAR 的 `real_samples/`；
3. 数据集自带的标签都用来核对：ASVspoof 系列 parquet 打包中的 `label` 列、In-the-Wild 的 `meta.csv`、ADD 2022 的官方标签文件（Zenodo 的 `track1_label.txt`、`track3_R2_label.txt`，放在 `source/ADD2022-*/labels/`）、ADD 2023 评测包内的 `label.txt`，以及上面的目录约定。只有 Codecfake 的标签没有和第二个来源核对过，完全取自 DF-Arena（发布方的 `label.zip` 在 Zenodo 训练集记录 13838106 里，登记时 Zenodo 不可用，没有取到）。

每条记录的 `metadata.protocols` 保存两个榜单 protocol 中的原始样本 ID（`spoofradar-v1.0` 为 `sample_id`，`df-arena` 为 `file_name`），可以直接写出提交用的打分文件；`labels.source` 是所属集合，`labels.subset` 是生成系统或子集（如 Codecfake 的 `C1`–`C7`、LibriSeVoc 的声码器、SpoofCeleb 的攻击编号）。

## 音频来源

音频都是各数据集发布的原始文件，逐字节未改动，放在 `source/<集合名>/` 下，保持原压缩包内的路径（ASVspoof 系列按 SpoofRadar 的 `sample_id` 路径写出）。下载经 hf-mirror；Zenodo 上有 md5 的都逐个核对过：

| 集合 | 来源 |
|---|---|
| ASVspoof 2019 LA / 2021 LA / 2021 DF / 5 | HF `SpeechAntiSpoofingBenchmarks/*` 的 parquet 打包，`audio.bytes` 是原始 flac；只取 protocol 列出的条目（2021 LA/DF 的打包含 progress 阶段，多于榜单） |
| ADD 2022 赛道 1 | HF `shuohann/dfcdata`，与 Zenodo 10843991 的 md5 一致 |
| ADD 2022 赛道 3.2 第二轮 | Zenodo 12188055（`track32test`）。dfcdata 里标成 `Track3_2_R2` 的其实是赛道 3.1 的评测集（112,861 条，文件名相同、内容不同），不能用 |
| ADD 2023 赛道 1.2 第一、二轮 | HF `shuohann/dfcdata`，与 Zenodo 12175884 / 12176326 各分卷的 md5 一致 |
| Codecfake C1–C7 | 版本 1：C5、C6 取自 Zenodo 11169781（dfcdata 是 9 月的版本 2，这两个包变了，DF-Arena 要求用版本 1），C1–C4、C7 取自 dfcdata 并与 Zenodo 11169781 / 11125029 的 md5 核对 |
| LibriSeVoc | HF `shuohann/dfcdata`，与 Zenodo 15127251 的 md5 一致 |
| Fake-or-Real、SONAR、In-the-Wild | HF `shuohann/dfcdata`（Kaggle 打包的 for-norm、存档的 Google Drive 版 SONAR、`release_in_the_wild.zip`） |
| DFADD | HF `isjwdu/DFADD`（作者发布），只取 `test/` |
| XMAD-Bench | HF `unibuc-cs/XMAD-Bench`（作者发布），只取测试用的 7 个来源 |
| SpoofCeleb | HF `xxuan-speech/SpoofCeleb`（官方 `jungjee/spoofceleb` 发布包的解压版），只取 `flac/evaluation/`，每个文件按 Hub 上的 sha256 核对 |

## 读取注意

音频按原样保存，格式和采样率随数据集不同：flac 与 wav 都有，采样率从 16 kHz 到 24 kHz 不等（audio-index 里逐条记录了 `sample_rate`），SONAR 的 OpenAI 子集是扩展名为 `.wav` 的 MP3。读取时按文件内容识别格式（soundfile / libsndfile 可直接读），模型需要的采样率由评测方自己重采样。

## 许可

各数据集许可证不同：ASVspoof 为 ODC-By，ADD 和 Codecfake 为 CC BY-NC-ND 4.0，XMAD-Bench 为 CC BY-NC-SA 4.0，SpoofCeleb 为 CC BY 4.0（需在 HF 上同意使用条款），LibriSeVoc 为 CC BY-SA 4.0。只用于内部研究评测，不得对外再分发。

## 文件与脚本

- `scripts/speech_deepfake_bench/sources.py`：每个集合的来源、split 名和匹配规则；
- `scripts/speech_deepfake_bench/extract.py`：把下载暂存目录中的音频放进 `source/<集合名>/`；
- `scripts/speech_deepfake_bench/build.py`：匹配 protocol、核对标签，写 `versions/v1-20261103/` 下的记录与 audio-index，登记 catalog，并生成 amphion-eval 的两份数据配置（`eval-sets/spoofradar.yaml`、`eval-sets/df-arena.yaml`）。

数据盘上同一目录每秒只能新建约 150 个文件，大目录（ASVspoof 5 的 68 万条在同一目录）解包需要约一小时；脚本按多线程写出，各集合可以并行运行。

## 读取

```bash
audio-data-contract resolve catalog speech_deepfake_bench v1-20261103 records --roots roots.json
```

roots 中的 `speech_deepfake_bench` 指向 `/workspace/data/datasets/speech_deepfake_bench`。

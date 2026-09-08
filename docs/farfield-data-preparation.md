# 远场、会议数据准备

更新：2026-09-08。此次只准备数据和训练入口，不启动训练。

所有数据注册已迁至 [contract 运行快照](icefall-runtime.md)，本仓库维护下载、清洗和准备实现，icefall 消费产物。

## 当前可用

数据根目录：`/ai_sds_wuzz/DATA_ASR`；训练清单根目录：`/ai_sds_wuzz/DATA_ASR/LHOTSE`。

| 训练入口 | 训练录音数 | 训练标注条数 | 标注时长 | 清单目录（相对 LHOTSE） |
|---|---:|---:|---:|---|
| `alimeeting_sdm` | 209 | 186,360 | 140.57 h | `AliMeeting/data/manifests` |
| `ami_sdm` | 134 | 102,690 | 74.80 h | `AMI/data/manifests` |
| `notsofar_sdm` | 346 | 82,850 | 45.61 h | `NOTSOFAR/data/manifests` |
| `realman` | 36,816 | 36,816 | 64.03 h | `RealMAN/data/manifests` |
| `vitw_far_field` | 45,437 | 45,437 | 77.26 h | `Voices-in-the-Wild-2M/data/manifests/by_subset` |

标注时长包含多人重叠；NOTSOFAR 同一会议还包含不同单麦设备的录音，不能把这一列当成独立会议时长，也不能直接按此设训练比例。

三个会议数据集均保留 train/dev/test。AliMeeting 的官方 Eval 映射为 dev；AMI 使用 `full-corpus-asr`；NOTSOFAR 使用本地官方版本 `240825.1_train`、`240825.1_dev1`、`240825.1_eval_full_with_GT`。按会议 ID 检查，三者各自的划分之间均无交集。

AMI 的 `IS1003b`、`IS1007d` 单麦文件本地缺失，官方 AMICorpusMirror 对应 URL 也返回 404，未伪造或替换为其他麦克风。`ES2010d.Array1-01.wav` 实为双声道；在 `AMI/data/mono/` 生成了第一通道副本，恢复该会议的训练标注，原文件保留。

NOTSOFAR 的 ASR 文本使用官方 word timing 中的词，去掉非语音 XML 标签，保留实际说出的语气词。无可识别文字的片段排除；原始标注仍保留。当前入口是普通单路 ASR 的数据准备，未对重叠语音执行分离，也未将多人同时讲话改写为单路目标。

ViTW 原始采样率包含 16/24/48 kHz，现有 loader 会按训练目标重采样到 16 kHz。评测继续使用已有 `vitw` 入口的独立 Bench；训练录音 ID 与 Bench 无交集，这不等于完成了所有底层原始语音的去重。

真实 RIR 共 178 条，均为 16 kHz，已核验源文件可读。训练时可引用：

```text
/ai_sds_wuzz/DATA_ASR/LHOTSE/noise_rir/data/manifests/real_rir_slr28_recordings_all.jsonl.gz
```

配合已有 `--extreme-real-rir-manifest` 和 `--extreme-real-rir-prob` 使用；本次未修改 v9 的增强概率或采样比例。

## RealMAN 自动准备

入口：`scripts/icefall/download_realman_asr.py`。

- 固定官方 `AISHELL/RealMAN` revision：`fea47505cae8041f4b652b0954ba61c77d2b6df1`。
- ASR 下载范围：train 的 `ma_speech`、val/test 的 `ma_noisy_speech`、转写、场景元数据与位置 CSV；113 个文件，总计 258,795,986,801 bytes。
- 原始多通道压缩包保留；ASR 解压第一通道至 `RealMAN/asr_mono/{train,val,test}`。
- 下载保留 `.aria2` 分片并使用官方 LFS SHA-256；超时、连接及校验失败自动等待后重试，只提交未完成文件。默认等待 60 秒，可用 `--retry-delay` 调整。
- 重新启动时复用固定 revision 的下载计划和解包标记；成功后自动解压、验证清单并生成 train/dev/test。文件锁阻止多个进程同时写同一下载目录；本地文件/配置错误会退出等待修复。
- `realman` 已在 `audio-data-contract` 的 `icefall_runtime.jsonl` 注册，但只能在下面的状态文件显示 `ready` 后纳入训练；仅有压缩包或注册项不代表数据就绪。

2026-09-08 已完成 113 个文件下载、LFS SHA-256 校验、57 个压缩包提取及清单验证，状态为 `ready`。

动态状态：`/ai_sds_wuzz/DATA_ASR/RealMAN/preparation_status.json`。

下载清单：`/ai_sds_wuzz/DATA_ASR/RealMAN/asr_download.json`。

完成后的训练清单：`/ai_sds_wuzz/DATA_ASR/LHOTSE/RealMAN/data/manifests/`。

此范围用于 ASR。没有下载语音增强任务专用的重复 direct-path 参考、val_raw/test_raw，以及 367.9 GB 的独立训练噪声包。

```bash
python scripts/icefall/download_realman_asr.py --aria2 /path/to/aria2c --seven-zip /path/to/7zz
```

需要 `requests`、`aria2c`、`7zz` 及下方清单准备依赖。当前机器的执行日志位于 `zh_en/ASR/data/farfield_prep/realman_pipeline.log`。

## 复现与检查

清单脚本依赖 Lhotse（本次使用 1.33.0）、TextGrid、SoundFile；已有上游清单会复用。

```bash
python scripts/icefall/prepare_farfield_manifests.py -d alimeeting_sdm
python scripts/icefall/prepare_farfield_manifests.py -d ami_sdm
python scripts/icefall/prepare_farfield_manifests.py -d notsofar_sdm
```

本次检查包括：全部现有源音频的文件头及首尾各 400 帧、ID 唯一性、标注引用、三个会议集的划分隔离，以及每个训练入口的单声道/16 kHz 加载抽查。未逐帧解码全部长录音。

完整核验结果：`zh_en/ASR/data/farfield_prep/audio_audit.json`。各会议清单目录内还有 `{dataset}_summary.json`。

## MISP-Meeting：等待授权

官方实际使用独立的非商业数据许可协议，要求符合许可范围的机构填写、签署并上传协议，不能仅根据 GitHub 概述将其视为已授权。

已保存协议至 `zh_en/ASR/data/farfield_prep/MISP-Meeting-license.pdf`，尚未代签、提交申请或纳入训练数据。获授权后可补充远场音频和转写，不需要下载全景视频。

来源：[RealMAN](https://github.com/Audio-WestlakeU/RealMAN)、[AliMeeting](https://www.openslr.org/119/)、[NOTSOFAR](https://github.com/microsoft/NOTSOFAR1-Challenge)、[MISP 官方页面](https://challenge.xfyun.cn/misp_dataset)、[MISP 官方协议](https://ai-contest-static.xfyun.cn/misp/Non-commercial%20Data%20License%20Agreement%20for%20MISP-Meeting.pdf)。

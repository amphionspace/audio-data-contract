# 说话人和声纹数据下载

五套源包均已下载、校验并登记。后续解压、通用 AudioRecord、说话人标签和评测配对入口见[说话人数据处理说明](speaker-preparation.md)。下文保留本次源包获取范围和校验依据。

已登记 CN-Celeb1/2、3D-Speaker、HI-MIA 和 CHiME-6，共 21 个源文件、471,979,042,202 字节（约 472 GB），于 2026-09-12 完成下载、校验和发布。本机执行记录见[下载进度](/ai_sds_wuzz/DATA_ASR/downloads/speaker-expansion-20260911/progress.md)。

| 数据集 | 登记版本 | 文件数 | 压缩包及标注 GB | 官方来源 |
|---|---|---:|---:|---|
| [cnceleb1](../catalog/cnceleb1.jsonl) | openslr-82-v2 | 1 | 22.264 | [OpenSLR 82](https://www.openslr.org/82/) |
| [cnceleb2](../catalog/cnceleb2.jsonl) | openslr-82-v2 | 3 | 77.578 | [OpenSLR 82](https://www.openslr.org/82/) |
| [3dspeaker](../catalog/3dspeaker.jsonl) | official-source-20260911 | 7 | 204.483 | [3D-Speaker](https://3dspeaker.github.io/) |
| [hi_mia](../catalog/hi_mia.jsonl) | openslr-85-test-v2 | 4 | 46.638 | [OpenSLR 85](https://www.openslr.org/85/) |
| [chime6](../catalog/chime6.jsonl) | openslr-150-source-20260911 | 6 | 121.015 | [OpenSLR 150](https://www.openslr.org/150/) |

体积来自官方文件的 HTTP 响应头，统一按十进制 GB 计算；不含解压和训练清单。本次范围是完整源包及配套标注，不包含重新获取 VoxCeleb 或采集 VoxBlink2 视频。

## 文件位置与状态

使用现有 `legacy_asr` 根目录别名，本机对应 `/ai_sds_wuzz/DATA_ASR`。

- 下载断点：`<dataset>/work/download-20260911/`。
- 完成校验后的源文件：`<dataset>/source/<version>/`。
- [确切下载计划](/ai_sds_wuzz/DATA_ASR/downloads/speaker-expansion-20260911/http-plan.json)：URL、预期长度、校验依据、临时和发布目录。
- [远端文件快照](/ai_sds_wuzz/DATA_ASR/downloads/speaker-expansion-20260911/remote-files.json)：响应长度、ETag、最后修改时间；ETag 不一律当作 MD5。
- 下载状态：`downloads/speaker-expansion-20260911/<dataset>/state.json`，可通过 catalog 的 `download_state` artifact 解析。

源路径只在全套文件完成校验后发布；`download_planned` 声明不表示文件已经存在，也不表示可直接训练。

## 下载和校验

本批通过本机下载任务执行，任务目录中的计划和日志是历史执行记录，不是仓库自带的下载命令。重新获取时，使用 catalog 中源产物的 URL、长度和 SHA-256 定位并核对同一份文件；源文件就绪后按[处理说明](speaker-preparation.md)解压和转换。

2026-09-12 因原镜像限速和重复超时，CN-Celeb1、CN-Celeb2、HI-MIA 的剩余音频切换到官方 ELDA 镜像，分别使用 1、2、1 个连接，保留断点。切换前核对全部文件长度；CN-Celeb1 的首 1 MiB、CN-Celeb2 的首尾各 1 MiB 与原来源一致；HI-MIA 保留官方 MD5。完整文件仍按原计划校验。

- HI-MIA 使用官方 MD5，测试集只下载修复版 `test_v2.tar.gz`。
- 3D-Speaker 的 train/test 使用官网 MD5，同时下载转写、语句元信息及跨设备、距离、方言的三个验证配对文件。
- CN-Celeb 当前 `checksum.md5` 对应旧版 `.tgz/.rar`，不用于新版 v2。CN-Celeb1 使用长度、gzip CRC 和本地 SHA-256；CN-Celeb2 除逐分包长度及 SHA-256 外，还须将 aa、ab、ac 按顺序流式拼接，通过 `gzip -t` 后才能认定完整归档通过校验。无需额外落盘一份合并包。
- CHiME-6 未找到对应的官方 MD5 清单，音频使用长度、gzip CRC 和本地 SHA-256。trmal/CN 官方转写包的完整 SHA-256 一致，但有效 gzip 内容后有 154 字节尾随数据；另一个官方镜像的 S21 标注不同，不直接替换。保留当前原包，并在 `chime6/layers/transcription-archive-repair/v1-20260912/` 发布只去掉尾随字节的标注包；确认解压内容不变、gzip CRC 和 20 个 JSON 文件均通过检查，再将标注入口指向该产物。
- 官网对 3D-Speaker 的 CC-BY-SA-4.0 声明明确针对 metadata；catalog 保留该范围，没有扩大为整套音频许可。

下载脚本逐文件完成后，还需执行上述跨分包校验，原子发布临时目录，回填实际校验记录并更新 catalog 和总览。源包校验完成不等于音频已解压、内容质量已审核或训练清单已准备。

本批发布任务已完成，任务目录内的 `complete.json` 记录最终状态。每套数据的 `published-inventory.json` 保存源文件 SHA-256 和校验证据，执行日志见 `finish.log`，汇总见 `progress.md` 和 `summary.json`。

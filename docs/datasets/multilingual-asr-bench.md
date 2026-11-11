# 多语种 ASR 评测集（multilingual_asr_bench）

`multilingual_asr_bench` 收录十二种语言的公开 ASR 测试集，只用于评测，不进训练。语言按优先级排列：中文、英语、阿拉伯语、西班牙语、法语、德语、葡萄牙语、日语、韩语、印地语、俄语、印尼语。当前版本是 `v2-20261110`，对应 amphion-eval 的测试集登记 `open-audio-llm/multilingual-asr-benchmark@v2-20261110`。

- **朗读底座**：每种语言都有 FLEURS 和 Common Voice 17.0 的 test，所有语言用同一个上游修订，口径一致。
- **真实场景**：GigaSpeech 2 印尼语 YouTube test、Casablanca 八种阿拉伯语方言的电视剧 test，以及 VoxPopuli 法语和德语的欧洲议会发言 test。
- **手机与远场录音**：Kathbath 印地语手机朗读 test（已知和未知说话人），Golos 俄语语音助手指令 test（众包手机录音和远场录音）。

| 版本 | 内容 |
|---|---|
| `v2-20261110` | v1 全部内容，加 Kathbath、VoxPopuli 和 Golos |
| `v1-20261110` | FLEURS、Common Voice、GigaSpeech 2 和 Casablanca；对应测试集 `…@v1-20261110` |

两个版本共用 `source/` 下的音频，各自的 records 和 audio index 在 `versions/<版本>/` 下。

## 内容

| split | 语言 | 来源 | 条数 | 时长 |
|---|---|---|---:|---:|
| `fleurs-zh` / `cv-zh` | 中文 | FLEURS cmn_hans_cn / CV zh-CN | 945 / 10,626 | 3.1 / 17.5 h |
| `fleurs-en` / `cv-en` | 英语 | FLEURS en_us / CV en | 647 / 16,393 | 1.8 / 27.0 h |
| `fleurs-ar` / `cv-ar` | 阿拉伯语 | FLEURS ar_eg / CV ar | 428 / 10,480 | 1.3 / 12.7 h |
| `fleurs-es` / `cv-es` | 西班牙语 | FLEURS es_419 / CV es | 908 / 15,857 | 3.1 / 27.0 h |
| `fleurs-fr` / `cv-fr` | 法语 | FLEURS fr_fr / CV fr | 676 / 16,159 | 2.0 / 26.1 h |
| `fleurs-de` / `cv-de` | 德语 | FLEURS de_de / CV de | 862 / 16,183 | 3.2 / 27.5 h |
| `fleurs-pt` / `cv-pt` | 葡萄牙语 | FLEURS pt_br / CV pt | 919 / 9,467 | 3.2 / 12.6 h |
| `fleurs-ja` / `cv-ja` | 日语 | FLEURS ja_jp / CV ja | 650 / 6,261 | 2.4 / 8.9 h |
| `fleurs-ko` / `cv-ko` | 韩语 | FLEURS ko_kr / CV ko | 382 / 339 | 1.3 / 0.5 h |
| `fleurs-hi` / `cv-hi` | 印地语 | FLEURS hi_in / CV hi | 418 / 3,154 | 1.3 / 4.4 h |
| `fleurs-ru` / `cv-ru` | 俄语 | FLEURS ru_ru / CV ru | 775 / 10,203 | 2.5 / 15.9 h |
| `fleurs-id` / `cv-id` | 印尼语 | FLEURS id_id / CV id | 687 / 3,641 | 2.4 / 4.2 h |
| `gigaspeech2-id` | 印尼语 | GigaSpeech 2 test（YouTube） | 17,271 | 24.2 h |
| `casablanca-<方言>` | 阿拉伯语 | Casablanca test，8 个方言各一个划分 | 667–1,045，共 6,818 | 约 1 h，共 7.9 h |
| `voxpopuli-fr` / `voxpopuli-de` | 法语 / 德语 | VoxPopuli test（欧洲议会发言） | 1,680 / 1,966 | 4.7 / 4.9 h |
| `kathbath-hi-known` / `kathbath-hi-unknown` | 印地语 | Kathbath test-known / test-unknown（手机朗读，各 20 位说话人） | 3,130 / 1,929 | 5.0 / 3.0 h |
| `golos-crowd` / `golos-farfield` | 俄语 | Golos test（语音助手指令，众包 / 远场） | 9,896 / 1,915 | 11.1 / 1.4 h |

v2 共 39 个划分、171,665 条、273.9 h；v1 是前 33 个划分，151,149 条、243.8 h。Casablanca 的八个方言是阿尔及利亚、埃及、约旦、毛里塔尼亚、摩洛哥、巴勒斯坦、阿联酋和也门。

## 来源与处理

音频从各自登记的上游快照里原样取出：FLEURS、GigaSpeech 2、Casablanca、VoxPopuli 和 Golos 是 wav，Common Voice 是 mp3。只有 Kathbath 例外：它的 m4a（AAC）Lhotse 读不稳，用 ffmpeg 7.0.2 解码成 16 位 FLAC，采样率不变（44.1 kHz）；解码用 bitexact 选项，重跑得到同样的文件。上游快照登记在 `catalog/multilingual_asr_sources.yaml`。Hugging Face 上的快照从 hf-mirror.com 按固定修订下载，并按上游文件哈希校验；Kathbath 和 Golos 从官方地址下载，校验方式见下：

- FLEURS：`google/fleurs@70bb2e84`，转写取 raw transcription（带标点）。
- Common Voice 17.0：非官方镜像 `fsicoli/common_voice_17_0@8262c16b`（官方 Mozilla 仓库需要授权），转写取 `sentence`。
- GigaSpeech 2：`speechcolab/gigaspeech2@8dc0d0e5`，转写全大写、无标点；test 里 2 条空转写没有收入。这个仓库需要先同意条款，团队令牌已有权限。
- Casablanca：`UBC-NLP/Casablanca@8951b1b8`。
- VoxPopuli：`facebook/voxpopuli@42f01879`（HF 上的 parquet 转换版，不需要授权），只下了 fr、de 的 test，转写取 `raw_text`（带大小写和标点）。
- Kathbath：AI4Bharat 官方对象存储上的 clean 版 `testkn_audio.tar`、`testunk_audio.tar` 和 `transcripts_n2w.tar`（版本记为 `ai4bharat-20250409`，即文件的发布日期），转写取 n2w 版（数字已写成词）。上游没有公布文件哈希；下载后按 16 MiB 分片算出 S3 分片 ETag，与对象存储给出的 ETag 一致，sha256 在本地计算后登记。
- Golos：SberDevices 官方 CDN 上的 `test.tar`（版本记为 `sberdevices-20250324`，即文件的发布日期），转写取 `manifest.jsonl` 的 `text`。CDN 的 HTTPS 证书已过期，用 HTTP 下载，按 [salute-developers/golos](https://github.com/salute-developers/golos) 仓库公布的 md5 校验。

葡萄牙语直接沿用已有的 `fleurs_pt@hf-70bb2e84b976` 和 `common_voice_pt@hf-8262c16bf297`。印地语和印尼语的快照还带 dev，但评测集只用 test。

每条记录是 `audio-record/1.0`，`task: asr`。`target` 是上游原文，`language` 是两字母语言代码，`labels` 写明来源和 locale，`metadata` 保留上游 ID、性别和说话人等字段。所有划分共用一份 `audio-index.jsonl.gz`，时长和帧数用 Lhotse 读取（与评测器读取方式一致），每个文件都带 sha256。

## 许可

各部分继承上游许可：

- FLEURS 为 CC BY 4.0。
- Common Voice 为 CC0。
- GigaSpeech 2 为 Apache 2.0。
- **Casablanca 为 CC BY-NC-ND 4.0，仅限非商业用途，不得改编后再分发。**
- VoxPopuli 为 CC0。
- Kathbath 的打包和标注为 CC0；原文取自 IndicCorp（公开网页），AI4Bharat 不拥有其版权。
- Golos 为 SberDevices 的署名-相同方式共享公共许可（参照 CC BY-SA 4.0 改写），允许商用；再分发须署名，改编后须沿用同类许可。

## 已知问题

- **日语计分**：日语按字计分（CER）需要 ts-asr 打分口径版本 4 及以上（amphion-eval MR !130）。版本 3 对日语按空格分词，汉字一字一个单位，连续的假名却合成一个单位，日语错误率不能和其他系统比较。韩语、印地语、阿拉伯语等以空格分词的语言不受影响。
- **转写风格不同**：GigaSpeech 2 是大写无标点，Golos 是小写无标点，其余带大小写和标点。ts-asr 打分前统一大小写、去掉标点，不影响错误率。
- **空转写**：没有转写的条目不收入，在 catalog 的划分统计里记为 `dropped_empty_transcripts`（GigaSpeech 2 2 条，VoxPopuli 法语 62 条、德语 2 条，Golos 众包 98 条、远场 1 条）。
- **Kathbath test-known**：说话人也出现在 Kathbath 训练集；用 Kathbath 训练过的模型应看 test-unknown。
- **Casablanca 音频格式**：Casablanca 音频多为 44.1 或 48 kHz 双声道（电视音轨），这里保持原样；评测器读取时会取声道平均，再重采样到 16 kHz。
- **Common Voice 训练集重叠**：登记 `common_voice_pt` 时发现，这个镜像的 train 是 validated 去掉 test 后的剩余部分，和 test 有说话人与句子重叠（见其 `known_issues`）；其他语种用的是同一镜像，很可能也一样，但本次没有逐个核实。这里只用 test；用这个镜像的 train 训练过的模型，CV 成绩会偏乐观。

## 未收入

下面这些测试集本次没有收入：

| 语言 | 测试集 | 原因 |
|---|---|---|
| 日语 | ReazonSpeech test | 官方仓库需要申请访问 |
| 日语 | CSJ | 需要购买 |
| 韩语 | KsponSpeech | 需要在 AI Hub 注册 |
| 印地语 | Lahaja、IndicVoices | 需要申请访问 |
| 阿拉伯语 | MGB-3/5 | 需要注册 |
| 阿拉伯语 | SADA | 需要 Kaggle 账号 |

## 重新生成

```bash
# amphion-eval 环境（Lhotse 1.33），PATH 上要有 ffmpeg
python scripts/multilingual_asr_bench/register_sources.py --staging /workspace/data/staging/multilingual-asr-eval-20261110
python scripts/multilingual_asr_bench/build.py extract
python scripts/multilingual_asr_bench/build.py build --workers 32 \
    --eval-set /workspace/data/datasets/multilingual_asr_bench/eval-sets/multilingual-asr-benchmark-v2-20261110.yaml
```

`extract` 已经抽好的文件会跳过。`build` 只写 `sources.py` 里 `VERSION` 这一版的 records 和 audio index，并替换 catalog 里这一版的条目，旧版本条目不动；输入不变时每次写出的文件完全相同。

下载计划和日志在 `/workspace/data/staging/multilingual-asr-eval-20261110/`。Kathbath 的服务器对每条连接限速（约 8 KB/s），下载时用两个域名（路径式和虚拟主机式）各开 16 条连接。

# 102 个缺时长划分的定位结果

2026-09-09 核查完成：**79 个已补登记、14 个保留待统计、9 个旧入口移除**。未删除音频或原始数据文件。

此前“未配置根目录”不等于文件丢失。本次依据服务器现有 `audio_data_roots.json` 找到并配置了多语言、情感识别、AudioSet 和混音评测目录。

## 已移除的旧入口

| 数据集 | 版本 | 划分 | 数量 |
|---|---|---|---:|
| `common_voice_yue` | `icefall-20260908` | train, dev, test | 3 |
| `ts_hw_test` | `eval-20260804` | test | 1 |
| `libri2mix` | `eval-20260804` | test | 1 |
| `libri3mix` | `eval-20260804` | test | 1 |
| `common_voice_yue` | `legacy-20260804` | train, dev, test | 3 |

粤语 Common Voice 的旧路径为 `legacy_asr:LHOTSE/common_voice_yue/data/manifests/cv-yue_*`；另一组是 `tsasr_eval` 下的 `ts_hw_test_cuts_all.jsonl.gz`、`libri2mix_test_16k_min_mix_both_cuts.jsonl.gz` 和 `libri3mix_test_16k_min_mix_both_cuts.jsonl.gz`。原目录为空或不存在，相关数据与派生目录中也未找到这些文件。可用的 `common_voice_zh_hk` 及 LibriMix 派生评测入口继续保留。

## 保留待统计的 14 个划分

| 数据 | 划分数 | 找到的实际文件 |
|---|---:|---|
| WenetSpeech-Yue / WenetSpeech-Yue all，两套登记版本 | 4 | `multilingual:zh/WenetSpeech-Yue/data/manifests/wenetspeech_yue_supervisions_{clean,all}.jsonl.gz`；存在 NaN 字段 |
| IndicVoices | 1 | `legacy_asr:IndicVoices/hf-c96f9088f138/hindi/train-00003-of-00082.parquet` 等 |
| Multi-Talker-SD | 3 | train/dev/test 下均找到 `wavs/noisy/*.wav` |
| WAXAL-ASR | 1 | `data/ASR/nyn/nyn-unlabeled-00024.parquet` 等，另有 ASR_v2 划分元信息 |
| NOTSOFAR 录制版 | 3 | train/dev/eval 的 `MTG` 目录均找到麦克风音频 |
| NOTSOFAR 模拟版 | 2 | train/val 下均找到 `dataset-*.tar` |

## 102 个划分逐项清单

同一数据集的多个版本合并列在一行；划分数按版本分别计算。

| 数据集 | 版本 | 各版本划分 | 划分数 | 处理结果 |
|---|---|---|---:|---|
| `audioset_esc_test` | eval-20260804 | test | 1 | 已补登记 |
| `biic_podcast_ser` | eval-20260804 | test | 1 | 已补登记 |
| `common_voice_yue` | icefall-20260908, legacy-20260804 | dev, test, train | 6 | 移除旧登记 |
| `common_voice_zh_hk` | icefall-20260908, legacy-20260804 | dev, test, train | 6 | 已补登记 |
| `cs_dialogue` | icefall-20260908, legacy-20260804 | dev, test, train | 6 | 已补登记 |
| `cs_dialogue_en` | icefall-20260908, legacy-20260804 | dev, test, train | 6 | 已补登记 |
| `cs_dialogue_mix` | icefall-20260908, legacy-20260804 | dev, test, train | 6 | 已补登记 |
| `emotion1200_en_sec` | eval-20260804 | test | 1 | 已补登记 |
| `emotion1200_en_sepc` | eval-20260804 | test | 1 | 已补登记 |
| `emotion1200_en_ser` | eval-20260804 | test | 1 | 已补登记 |
| `emotion1200_zh_sec` | eval-20260804 | test | 1 | 已补登记 |
| `emotion1200_zh_sepc` | eval-20260804 | test | 1 | 已补登记 |
| `emotion1200_zh_ser` | eval-20260804 | test | 1 | 已补登记 |
| `fleurs_zh` | icefall-20260908, legacy-20260804 | dev, test, train | 6 | 已补登记 |
| `iemocap_ser` | eval-20260804 | test | 1 | 已补登记 |
| `indicvoices` | hf-c96f9088f138 | all | 1 | 保留，待统计 |
| `legco_speech` | icefall-20260908, legacy-20260804 | train | 2 | 已补登记 |
| `legco_speech_en` | icefall-20260908, legacy-20260804 | train | 2 | 已补登记 |
| `libri2mix` | eval-20260804 | test | 1 | 移除旧登记 |
| `libri2mix_lib` | eval-20260804 | test | 1 | 已补登记 |
| `libri2mix_snrp10` | eval-20260804 | test | 1 | 已补登记 |
| `libri2mix_snrp5` | eval-20260804 | test | 1 | 已补登记 |
| `libri2mix_tsstyle` | eval-20260804 | test | 1 | 已补登记 |
| `libri3mix` | eval-20260804 | test | 1 | 移除旧登记 |
| `libri3mix_lib` | eval-20260804 | test | 1 | 已补登记 |
| `libri3mix_snrp10` | eval-20260804 | test | 1 | 已补登记 |
| `libri3mix_snrp5` | eval-20260804 | test | 1 | 已补登记 |
| `libri3mix_tsstyle` | eval-20260804 | test | 1 | 已补登记 |
| `m3ed_ser` | eval-20260804 | test | 1 | 已补登记 |
| `magicdata_ramc` | icefall-20260908, legacy-20260804 | dev, test, train | 6 | 已补登记 |
| `mdcc` | icefall-20260908, legacy-20260804 | dev, test, train | 6 | 已补登记 |
| `meld_ser` | eval-20260804 | test | 1 | 已补登记 |
| `mls_de` | legacy | dev_punc, test_punc, train_punc | 3 | 已补登记 |
| `mls_es` | legacy | dev_punc, test_punc, train_punc | 3 | 已补登记 |
| `mls_fr` | legacy | dev_punc, test_punc, train_punc | 3 | 已补登记 |
| `multi-talker-sd` | hf-be2d372003fd | dev, test, train | 3 | 保留，待统计 |
| `notsofar` | hf-ba8fd0f034ce-recorded-240825.1, hf-ba8fd0f034ce-sim-v1.5-200h | dev, eval, train, validation | 5 | 保留，待统计 |
| `ts_hw_test` | eval-20260804 | test | 1 | 移除旧登记 |
| `ts_hw_test_libristyle` | eval-20260804 | test | 1 | 已补登记 |
| `waxal-asr` | hf-e91442a8989b | all | 1 | 保留，待统计 |
| `wenetspeech_chuan` | icefall-20260908, legacy-20260804 | train | 2 | 已补登记 |
| `wenetspeech_wu` | icefall-20260908, legacy-20260804 | train | 2 | 已补登记 |
| `wenetspeech_yue` | icefall-20260908, legacy-20260804 | train | 2 | 保留，待统计 |
| `wenetspeech_yue_all` | icefall-20260908, legacy-20260804 | train | 2 | 保留，待统计 |

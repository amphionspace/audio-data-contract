# 数据总览

> 本文件由 catalog 和 view 声明自动生成，请勿手工编辑。
> 修改数据声明后，请运行 `audio-data-contract generate-overview`；CI 会用 `--check` 检查同步状态。

## 整体状态

| 指标 | 数量 |
|---|---:|
| 数据集标识 | 225 |
| 数据集版本 | 252 |
| 派生版本 | 40 |
| 物理产物 | 641 |
| Split 声明 | 420 |
| 逻辑 View | 19 |

## 完整性状态

| 状态 | 数据集版本 | 占比 |
|---|---:|---:|
| unspecified | 219 | 86.9% |
| verified | 33 | 13.1% |

## 任务覆盖

同一数据集版本可支持多个任务，因此下表数量可能重复计算。

| Task | 数据集版本 |
|---|---:|
| asr | 188 |
| asr_hotwords | 40 |
| ts_asr | 12 |
| ser | 7 |
| continuous_speech_separation | 5 |
| overlap_speech | 5 |
| speaker_attributed_asr | 5 |
| speaker_diarization | 5 |
| sec | 2 |
| sepc | 2 |
| ast | 1 |
| code_switch_asr | 1 |
| esc | 1 |

## Catalog 分布

| 声明文件 | 数据集版本 | 数据集标识 | 物理产物 | 已验证版本 |
|---|---:|---:|---:|---:|
| `alimeeting_far_raw.jsonl` | 1 | 1 | 4 | 1 |
| `download_queue.jsonl` | 10 | 10 | 14 | 0 |
| `icefall_base.jsonl` | 39 | 39 | 222 | 0 |
| `icefall_traffic_derived.jsonl` | 20 | 20 | 25 | 0 |
| `legacy_multilingual.jsonl` | 42 | 42 | 42 | 0 |
| `local_lhotse_derived.jsonl` | 19 | 18 | 49 | 19 |
| `multilingual_multispeaker.jsonl` | 6 | 5 | 24 | 6 |
| `open_audio_eval.jsonl` | 108 | 108 | 210 | 0 |
| `synthetic_asr.jsonl` | 4 | 1 | 40 | 4 |
| `synthetic_asr_v5_qc.jsonl` | 1 | 1 | 6 | 1 |
| `wenetspeech_weak.jsonl` | 2 | 1 | 5 | 2 |

## 数据集版本索引

<details><summary><code>alimeeting_far_raw.jsonl</code> — 1 个版本</summary>

| Dataset | Version | Languages | Tasks | Splits | Artifacts | Integrity | Derived from |
|---|---|---|---|---|---:|---|---|
| alimeeting | openslr-119-far-local-20260903 | zh | asr, speaker_diarization, speaker_attributed_asr, overlap_speech, continuous_speech_separation | train, dev, test | 4 | verified | — |

</details>

<details><summary><code>download_queue.jsonl</code> — 10 个版本</summary>

| Dataset | Version | Languages | Tasks | Splits | Artifacts | Integrity | Derived from |
|---|---|---|---|---|---:|---|---|
| aishell5 | 1.0 | zh | asr | train, dev, eval1, eval2 | 5 | unspecified | — |
| common-voice-en | 26.0 | en | asr | all | 1 | unspecified | — |
| common-voice-yue | 26.0 | yue | asr | all | 1 | unspecified | — |
| common-voice-zh-cn | 26.0 | zh | asr | all | 1 | unspecified | — |
| common-voice-zh-hk | 26.0 | yue | asr | all | 1 | unspecified | — |
| gigaspeech2 | hf-8dc0d0e502b7 | id, th, vi | asr | id, th, vi | 1 | unspecified | — |
| granary | hf-0fe23a860e35 | multi | asr, ast | all | 1 | unspecified | — |
| lemas | hf-91f0c1b9a29f | multi | asr | all | 1 | unspecified | — |
| omnilingual-asr-corpus | hf-8648ba894637 | multi | asr | all | 1 | unspecified | — |
| reazonspeech | hf-0df78f991f6a | ja | asr | all | 1 | unspecified | — |

</details>

<details><summary><code>icefall_base.jsonl</code> — 39 个版本</summary>

| Dataset | Version | Languages | Tasks | Splits | Artifacts | Integrity | Derived from |
|---|---|---|---|---|---:|---|---|
| aidatatang | legacy-20260804 | zh | asr | train | 2 | unspecified | — |
| aishell | legacy-20260804 | zh | asr | train, dev, test | 6 | unspecified | — |
| aishell2 | legacy-20260804 | zh | asr | train, test | 4 | unspecified | — |
| aishell3 | legacy-20260804 | zh | asr | train, test | 4 | unspecified | — |
| aishell4 | legacy-20260804 | zh | asr | train, test | 4 | unspecified | — |
| childmandarin | legacy-20260804 | zh | asr | train, dev, test | 3 | unspecified | — |
| common_voice_en | legacy-20260804 | en | asr | train, dev, test | 6 | unspecified | — |
| common_voice_yue | legacy-20260804 | yue | asr | train, dev, test | 6 | unspecified | — |
| common_voice_zh | legacy-20260804 | zh | asr | train, dev, test | 6 | unspecified | — |
| common_voice_zh_hk | legacy-20260804 | yue | asr | train, dev, test | 6 | unspecified | — |
| cs_dialogue | legacy-20260804 | zh | asr | train, dev, test | 6 | unspecified | — |
| cs_dialogue_en | legacy-20260804 | en | asr | train, dev, test | 6 | unspecified | — |
| cs_dialogue_mix | legacy-20260804 | zh | asr | train, dev, test | 6 | unspecified | — |
| cumix2017 | legacy-20260804 | yue | asr | train | 2 | unspecified | — |
| emilia_zh | legacy-20260804 | zh | asr | train | 1 | unspecified | — |
| fleurs_zh | legacy-20260804 | zh | asr | train, dev, test | 6 | unspecified | — |
| gigaspeech | legacy-20260804 | en | asr | train, dev, test | 6 | unspecified | — |
| kespeech | legacy-20260804 | zh | asr | train, dev, test | 10 | unspecified | — |
| legco_speech | legacy-20260804 | yue | asr | train | 2 | unspecified | — |
| legco_speech_en | legacy-20260804 | en | asr | train | 2 | unspecified | — |
| librispeech | legacy-20260804 | en | asr | train, dev, test_clean, test_other | 14 | unspecified | — |
| magicdata | legacy-20260804 | zh | asr | train, dev, test | 6 | unspecified | — |
| magicdata_ramc | legacy-20260804 | zh | asr | train, dev, test | 6 | unspecified | — |
| mdcc | legacy-20260804 | yue | asr | train, dev, test | 6 | unspecified | — |
| mls | legacy-20260804 | en | asr | train, dev, test | 6 | unspecified | — |
| primewords | legacy-20260804 | zh | asr | train | 2 | unspecified | — |
| singapore_english | legacy-20260804 | en | asr | train, dev | 4 | unspecified | — |
| singaporean | legacy-20260804 | en | asr | train | 2 | unspecified | — |
| tal100_en | legacy-20260804 | en | asr | train, dev, test | 6 | unspecified | — |
| tal100_zh | legacy-20260804 | zh | asr | train, dev, test | 6 | unspecified | — |
| talcs | legacy-20260804 | zh | asr | train, dev, test | 6 | unspecified | — |
| thchs30 | legacy-20260804 | zh | asr | train, dev, test | 6 | unspecified | — |
| vitw | legacy-20260804 | en | asr | train, real_distortion, real_dropout, real_echo, real_far_field, real_mixed, real_noise, real_obstructed, real_recording, syn_distortion, syn_dropout, syn_echo, syn_far_field, syn_mixed, syn_noise, syn_obstructed, syn_recording | 34 | unspecified | — |
| wenetspeech | legacy-20260804 | zh | asr | train, dev, test_net, test_meeting | 8 | unspecified | — |
| wenetspeech4tts | legacy-20260804 | zh | asr | train | 2 | unspecified | — |
| wenetspeech_chuan | legacy-20260804 | zh | asr | train | 1 | unspecified | — |
| wenetspeech_wu | legacy-20260804 | zh | asr | train | 1 | unspecified | — |
| wenetspeech_yue | legacy-20260804 | yue | asr | train, test_long, test_short | 6 | unspecified | — |
| wenetspeech_yue_all | legacy-20260804 | yue | asr | train, test_long, test_short | 6 | unspecified | — |

</details>

<details><summary><code>icefall_traffic_derived.jsonl</code> — 20 个版本</summary>

| Dataset | Version | Languages | Tasks | Splits | Artifacts | Integrity | Derived from |
|---|---|---|---|---|---:|---|---|
| librispeech_traffic_snr0 | recipe-1 | en | asr | test_clean, test_other | 2 | unspecified | librispeech |
| librispeech_traffic_snr10 | recipe-1 | en | asr | test_clean, test_other | 2 | unspecified | librispeech |
| librispeech_traffic_snr15 | recipe-1 | en | asr | test_clean, test_other | 2 | unspecified | librispeech |
| librispeech_traffic_snr20 | recipe-1 | en | asr | test_clean, test_other | 2 | unspecified | librispeech |
| librispeech_traffic_snr5 | recipe-1 | en | asr | test_clean, test_other | 2 | unspecified | librispeech |
| mdcc_traffic_snr0 | recipe-1 | yue | asr | test | 1 | unspecified | mdcc |
| mdcc_traffic_snr10 | recipe-1 | yue | asr | test | 1 | unspecified | mdcc |
| mdcc_traffic_snr15 | recipe-1 | yue | asr | test | 1 | unspecified | mdcc |
| mdcc_traffic_snr20 | recipe-1 | yue | asr | test | 1 | unspecified | mdcc |
| mdcc_traffic_snr5 | recipe-1 | yue | asr | test | 1 | unspecified | mdcc |
| talcs_traffic_snr0 | recipe-1 | zh | asr | test | 1 | unspecified | talcs |
| talcs_traffic_snr10 | recipe-1 | zh | asr | test | 1 | unspecified | talcs |
| talcs_traffic_snr15 | recipe-1 | zh | asr | test | 1 | unspecified | talcs |
| talcs_traffic_snr20 | recipe-1 | zh | asr | test | 1 | unspecified | talcs |
| talcs_traffic_snr5 | recipe-1 | zh | asr | test | 1 | unspecified | talcs |
| wenetspeech_traffic_snr0 | recipe-1 | zh | asr | test_net | 1 | unspecified | wenetspeech |
| wenetspeech_traffic_snr10 | recipe-1 | zh | asr | test_net | 1 | unspecified | wenetspeech |
| wenetspeech_traffic_snr15 | recipe-1 | zh | asr | test_net | 1 | unspecified | wenetspeech |
| wenetspeech_traffic_snr20 | recipe-1 | zh | asr | test_net | 1 | unspecified | wenetspeech |
| wenetspeech_traffic_snr5 | recipe-1 | zh | asr | test_net | 1 | unspecified | wenetspeech |

</details>

<details><summary><code>legacy_multilingual.jsonl</code> — 42 个版本</summary>

| Dataset | Version | Languages | Tasks | Splits | Artifacts | Integrity | Derived from |
|---|---|---|---|---|---:|---|---|
| banspeech_bn | legacy | bn | asr | all | 1 | unspecified | — |
| cbtts_bn | legacy | bn | asr | all | 1 | unspecified | — |
| cml_tts_fr | legacy | fr | asr | dev, test, train | 1 | unspecified | — |
| common_voice_ar | legacy | ar | asr | dev, test, train | 1 | unspecified | — |
| common_voice_bn | legacy | bn | asr | dev, test, train | 1 | unspecified | — |
| common_voice_de | legacy | de | asr | dev, test, train | 1 | unspecified | — |
| common_voice_es | legacy | es | asr | dev, test, train | 1 | unspecified | — |
| common_voice_fr | legacy | fr | asr | dev, test, train | 1 | unspecified | — |
| common_voice_ja | legacy | ja | asr | dev, test, train | 1 | unspecified | — |
| common_voice_ko | legacy | ko | asr | dev, test, train | 1 | unspecified | — |
| common_voice_ru | legacy | ru | asr | dev, test, train | 1 | unspecified | — |
| emilia_en | legacy | en | asr | all | 1 | unspecified | — |
| emilia_ja | legacy | ja | asr | all | 1 | unspecified | — |
| emilia_ko | legacy | ko | asr | all | 1 | unspecified | — |
| emilia_zh | legacy | zh | asr | all | 1 | unspecified | — |
| fleurs_ar | legacy | ar | asr | test, train, validation | 1 | unspecified | — |
| fleurs_bn | legacy | bn | asr | test, train, validation | 1 | unspecified | — |
| fleurs_de | legacy | de | asr | test, train, validation | 1 | unspecified | — |
| fleurs_en | legacy | en | asr | test, train, validation | 1 | unspecified | — |
| fleurs_es | legacy | es | asr | test, train, validation | 1 | unspecified | — |
| fleurs_fr | legacy | fr | asr | test, train, validation | 1 | unspecified | — |
| fleurs_ja | legacy | ja | asr | test, train, validation | 1 | unspecified | — |
| fleurs_ko | legacy | ko | asr | test, train, validation | 1 | unspecified | — |
| fleurs_ru | legacy | ru | asr | test, train, validation | 1 | unspecified | — |
| fleurs_zh | legacy | zh | asr | test, train, validation | 1 | unspecified | — |
| koreaspeech | legacy | ko | asr | train, validation | 1 | unspecified | — |
| mgb2 | legacy | ar | asr | dev, test, train | 1 | unspecified | — |
| mls_de | legacy | de | asr | dev, dev_punc, test, test_punc, train, train_punc | 1 | unspecified | — |
| mls_es | legacy | es | asr | dev, dev_punc, test, test_punc, train, train_punc | 1 | unspecified | — |
| mls_fr | legacy | fr | asr | dev, dev_punc, test, test_punc, train, train_punc | 1 | unspecified | — |
| open_large_bn | legacy | bn | asr | all | 1 | unspecified | — |
| rulibrispeech_ru | legacy | ru | asr | dev, test, train | 1 | unspecified | — |
| slr37_bn | legacy | bn | asr | all | 1 | unspecified | — |
| speechio | legacy | zh | asr | test | 1 | unspecified | — |
| yodas_ar | legacy | ar | asr | all | 1 | unspecified | — |
| yodas_bn | legacy | bn | asr | all | 1 | unspecified | — |
| yodas_de | legacy | de | asr | all | 1 | unspecified | — |
| yodas_es | legacy | es | asr | all | 1 | unspecified | — |
| yodas_fr | legacy | fr | asr | all | 1 | unspecified | — |
| yodas_ja | legacy | ja | asr | all | 1 | unspecified | — |
| yodas_ko | legacy | ko | asr | all | 1 | unspecified | — |
| yodas_ru | legacy | ru | asr | all | 1 | unspecified | — |

</details>

<details><summary><code>local_lhotse_derived.jsonl</code> — 19 个版本</summary>

| Dataset | Version | Languages | Tasks | Splits | Artifacts | Integrity | Derived from |
|---|---|---|---|---|---:|---|---|
| aidatatang_hotwords | hotwords-v1-20260805 | zh | asr_hotwords | train | 2 | verified | aidatatang |
| aishell2_clean | clean-v1-20260805 | zh | asr | test | 2 | verified | aishell2 |
| aishell2_hotwords | hotwords-v1-20260805 | zh | asr_hotwords | test | 2 | verified | aishell2 |
| aishell3_hotwords | hotwords-v1-20260805 | zh | asr_hotwords | train, test | 4 | verified | aishell3 |
| aishell_clean | clean-v1-20260805 | zh | asr | test | 2 | verified | aishell |
| aishell_hotwords | hotwords-v1-20260805 | zh | asr_hotwords | train, test | 4 | verified | aishell |
| commonvoice_en_clean | clean-v1-20260805 | en | asr | train, test | 4 | verified | common_voice_en |
| commonvoice_en_hotwords | hotwords-v1-20260805 | en | asr_hotwords | train, test | 4 | verified | common_voice_en |
| commonvoice_zh_clean | clean-v1-20260805 | zh | asr | test | 2 | verified | common_voice_zh |
| commonvoice_zh_hotwords | hotwords-v1-20260805 | zh | asr_hotwords | train, test | 4 | verified | common_voice_zh |
| gigaspeech2_id | local-20260805 | id | asr | train | 2 | verified | — |
| gigaspeech2_id_hotwords | hotwords-v1-20260805 | id | asr_hotwords | train | 2 | verified | gigaspeech2_id |
| kespeech_clean | clean-v1-20260805 | zh | asr | test | 2 | verified | kespeech |
| kespeech_hotwords | hotwords-v1-20260805 | zh | asr_hotwords | test | 2 | verified | kespeech |
| magicdata_hotwords | hotwords-v1-20260805 | zh | asr_hotwords | train | 2 | verified | magicdata |
| talcs_hotwords | hotwords-v1-20260805 | zh | asr_hotwords | train | 2 | verified | talcs |
| thchs30_hotwords | hotwords-v1-20260805 | zh | asr_hotwords | train | 2 | verified | thchs30 |
| wenetspeech_clean | clean-v1-20260805 | zh | asr | train | 2 | verified | wenetspeech |
| wenetspeech_clean | clean-v3-20260828 | zh | asr | train | 3 | verified | wenetspeech |

</details>

<details><summary><code>multilingual_multispeaker.jsonl</code> — 6 个版本</summary>

| Dataset | Version | Languages | Tasks | Splits | Artifacts | Integrity | Derived from |
|---|---|---|---|---|---:|---|---|
| alimeeting | openslr-119-local-20260826 | zh | asr, speaker_diarization, speaker_attributed_asr, overlap_speech, continuous_speech_separation | train, dev, test | 13 | verified | — |
| indicvoices | hf-c96f9088f138 | as, bn, brx, doi, gu, hi, kn, ks, kok, mai, ml, mni, mr, ne, or, pa, sa, sat, sd, ta, te, ur | asr | all | 1 | verified | — |
| multi-talker-sd | hf-be2d372003fd | en, zh | asr, code_switch_asr, speaker_diarization, speaker_attributed_asr, overlap_speech, continuous_speech_separation | train, dev, test | 3 | verified | — |
| notsofar | hf-ba8fd0f034ce-recorded-240825.1 | en | asr, speaker_diarization, speaker_attributed_asr, overlap_speech, continuous_speech_separation | train, dev, eval | 3 | verified | — |
| notsofar | hf-ba8fd0f034ce-sim-v1.5-200h | en | asr, speaker_diarization, speaker_attributed_asr, overlap_speech, continuous_speech_separation | train, validation | 2 | verified | — |
| waxal-asr | hf-e91442a8989b | ach, aka, am, dag, dga, ee, ff, kpo, ln, lg, mas, mg, nyn, om, sid, sn, sog, ti, wal | asr | all | 2 | verified | — |

</details>

<details><summary><code>open_audio_eval.jsonl</code> — 108 个版本</summary>

| Dataset | Version | Languages | Tasks | Splits | Artifacts | Integrity | Derived from |
|---|---|---|---|---|---:|---|---|
| aishell | eval-20260804 | zh | asr | test | 2 | unspecified | — |
| aishell2 | eval-20260804 | zh | asr | test | 2 | unspecified | — |
| aishell2_hotwords | eval-20260804 | zh | asr_hotwords | test | 2 | unspecified | — |
| aishell3 | eval-20260804 | zh | asr | test | 2 | unspecified | — |
| aishell3_hotwords | eval-20260804 | zh | asr_hotwords | test | 2 | unspecified | — |
| aishell_hotwords | eval-20260804 | zh | asr_hotwords | test | 2 | unspecified | — |
| audioset_esc_test | eval-20260804 | en | esc | test | 1 | unspecified | — |
| biic_podcast_ser | eval-20260804 | zh | ser | test | 2 | unspecified | — |
| commonvoice_en | eval-20260804 | en | asr | test | 3 | unspecified | — |
| commonvoice_en_hotwords | eval-20260804 | en | asr_hotwords | test | 2 | unspecified | — |
| commonvoice_zh | eval-20260804 | zh | asr | test | 2 | unspecified | — |
| commonvoice_zh_hotwords | eval-20260804 | zh | asr_hotwords | test | 2 | unspecified | — |
| cv_en_noise_audioset_esc | eval-20260804 | en | asr | test | 2 | unspecified | — |
| cv_en_noise_audioset_esc_hotwords | eval-20260804 | en | asr_hotwords | test | 2 | unspecified | — |
| cv_en_noise_audioset_traffic | eval-20260804 | en | asr | test | 2 | unspecified | — |
| cv_en_noise_audioset_traffic_hotwords | eval-20260804 | en | asr_hotwords | test | 2 | unspecified | — |
| cv_en_noise_dns | eval-20260804 | en | asr | test | 2 | unspecified | — |
| cv_en_noise_dns_hotwords | eval-20260804 | en | asr_hotwords | test | 2 | unspecified | — |
| cv_en_noise_musan_music | eval-20260804 | en | asr | test | 2 | unspecified | — |
| cv_en_noise_musan_music_hotwords | eval-20260804 | en | asr_hotwords | test | 2 | unspecified | — |
| cv_en_noise_musan_noise | eval-20260804 | en | asr | test | 2 | unspecified | — |
| cv_en_noise_musan_noise_hotwords | eval-20260804 | en | asr_hotwords | test | 2 | unspecified | — |
| cv_en_noise_musan_speech | eval-20260804 | en | asr | test | 2 | unspecified | — |
| cv_en_noise_musan_speech_hotwords | eval-20260804 | en | asr_hotwords | test | 2 | unspecified | — |
| cv_en_noise_wham | eval-20260804 | en | asr | test | 2 | unspecified | — |
| cv_en_noise_wham_hotwords | eval-20260804 | en | asr_hotwords | test | 2 | unspecified | — |
| cv_en_rir_rirmega | eval-20260804 | en | asr | test | 2 | unspecified | — |
| cv_en_rir_rirmega_hotwords | eval-20260804 | en | asr_hotwords | test | 2 | unspecified | — |
| cv_en_rir_slr26 | eval-20260804 | en | asr | test | 2 | unspecified | — |
| cv_en_rir_slr26_hotwords | eval-20260804 | en | asr_hotwords | test | 2 | unspecified | — |
| cv_en_rir_slr28_real | eval-20260804 | en | asr | test | 2 | unspecified | — |
| cv_en_rir_slr28_real_hotwords | eval-20260804 | en | asr_hotwords | test | 2 | unspecified | — |
| cv_en_rir_slr28_sim | eval-20260804 | en | asr | test | 2 | unspecified | — |
| cv_en_rir_slr28_sim_hotwords | eval-20260804 | en | asr_hotwords | test | 2 | unspecified | — |
| cv_zh_noise_audioset_esc | eval-20260804 | zh | asr | test | 2 | unspecified | — |
| cv_zh_noise_audioset_esc_hotwords | eval-20260804 | zh | asr_hotwords | test | 2 | unspecified | — |
| cv_zh_noise_audioset_traffic | eval-20260804 | zh | asr | test | 2 | unspecified | — |
| cv_zh_noise_audioset_traffic_hotwords | eval-20260804 | zh | asr_hotwords | test | 2 | unspecified | — |
| cv_zh_noise_dns | eval-20260804 | zh | asr | test | 2 | unspecified | — |
| cv_zh_noise_dns_hotwords | eval-20260804 | zh | asr_hotwords | test | 2 | unspecified | — |
| cv_zh_noise_musan_music | eval-20260804 | zh | asr | test | 2 | unspecified | — |
| cv_zh_noise_musan_music_hotwords | eval-20260804 | zh | asr_hotwords | test | 2 | unspecified | — |
| cv_zh_noise_musan_noise | eval-20260804 | zh | asr | test | 2 | unspecified | — |
| cv_zh_noise_musan_noise_hotwords | eval-20260804 | zh | asr_hotwords | test | 2 | unspecified | — |
| cv_zh_noise_musan_speech | eval-20260804 | zh | asr | test | 2 | unspecified | — |
| cv_zh_noise_musan_speech_hotwords | eval-20260804 | zh | asr_hotwords | test | 2 | unspecified | — |
| cv_zh_noise_wham | eval-20260804 | zh | asr | test | 2 | unspecified | — |
| cv_zh_noise_wham_hotwords | eval-20260804 | zh | asr_hotwords | test | 2 | unspecified | — |
| cv_zh_rir_rirmega | eval-20260804 | zh | asr | test | 2 | unspecified | — |
| cv_zh_rir_rirmega_hotwords | eval-20260804 | zh | asr_hotwords | test | 2 | unspecified | — |
| cv_zh_rir_slr26 | eval-20260804 | zh | asr | test | 2 | unspecified | — |
| cv_zh_rir_slr26_hotwords | eval-20260804 | zh | asr_hotwords | test | 2 | unspecified | — |
| cv_zh_rir_slr28_real | eval-20260804 | zh | asr | test | 2 | unspecified | — |
| cv_zh_rir_slr28_real_hotwords | eval-20260804 | zh | asr_hotwords | test | 2 | unspecified | — |
| cv_zh_rir_slr28_sim | eval-20260804 | zh | asr | test | 2 | unspecified | — |
| cv_zh_rir_slr28_sim_hotwords | eval-20260804 | zh | asr_hotwords | test | 2 | unspecified | — |
| emotion1200_en_sec | eval-20260804 | en | sec | test | 2 | unspecified | — |
| emotion1200_en_sepc | eval-20260804 | en | sepc | test | 2 | unspecified | — |
| emotion1200_en_ser | eval-20260804 | en | ser | test | 2 | unspecified | — |
| emotion1200_zh_sec | eval-20260804 | zh | sec | test | 2 | unspecified | — |
| emotion1200_zh_sepc | eval-20260804 | zh | sepc | test | 2 | unspecified | — |
| emotion1200_zh_ser | eval-20260804 | zh | ser | test | 2 | unspecified | — |
| gigaspeech | eval-20260804 | en | asr | test | 2 | unspecified | — |
| iemocap_ser | eval-20260804 | en | ser | test | 2 | unspecified | — |
| kespeech | eval-20260804 | zh | asr | test | 2 | unspecified | — |
| libri2mix | eval-20260804 | en | ts_asr | test | 1 | unspecified | — |
| libri2mix_lib | eval-20260804 | en | ts_asr | test | 1 | unspecified | — |
| libri2mix_snrp10 | eval-20260804 | en | ts_asr | test | 1 | unspecified | — |
| libri2mix_snrp5 | eval-20260804 | en | ts_asr | test | 1 | unspecified | — |
| libri2mix_tsstyle | eval-20260804 | en | ts_asr | test | 1 | unspecified | — |
| libri3mix | eval-20260804 | en | ts_asr | test | 1 | unspecified | — |
| libri3mix_lib | eval-20260804 | en | ts_asr | test | 1 | unspecified | — |
| libri3mix_snrp10 | eval-20260804 | en | ts_asr | test | 1 | unspecified | — |
| libri3mix_snrp5 | eval-20260804 | en | ts_asr | test | 1 | unspecified | — |
| libri3mix_tsstyle | eval-20260804 | en | ts_asr | test | 1 | unspecified | — |
| librispeech | eval-20260804 | en | asr | librispeech_test_clean, librispeech_test_other | 4 | unspecified | — |
| librispeech_test_clean | eval-20260804 | en | asr | test | 2 | unspecified | — |
| librispeech_test_clean_hotwords | eval-20260804 | en | asr_hotwords | test | 2 | unspecified | — |
| librispeech_test_other | eval-20260804 | en | asr | test | 2 | unspecified | — |
| librispeech_test_other_hotwords | eval-20260804 | en | asr_hotwords | test | 2 | unspecified | — |
| m3ed_ser | eval-20260804 | zh | ser | test | 2 | unspecified | — |
| magicdata | eval-20260804 | zh | asr | test | 2 | unspecified | — |
| meld_ser | eval-20260804 | en | ser | test | 2 | unspecified | — |
| mls | eval-20260804 | en | asr | test | 2 | unspecified | — |
| msp_podcast_ser | eval-20260804 | en | ser | msp_podcast_test1, msp_podcast_test2 | 4 | unspecified | — |
| talcs | eval-20260804 | zh | asr | test | 2 | unspecified | — |
| thchs30 | eval-20260804 | zh | asr | test | 2 | unspecified | — |
| ts_hw_test | eval-20260804 | en, zh | ts_asr | test | 1 | unspecified | — |
| ts_hw_test_libristyle | eval-20260804 | en, zh | ts_asr | test | 1 | unspecified | — |
| vitw_real_distortion | eval-20260804 | en, zh | asr | test | 2 | unspecified | — |
| vitw_real_dropout | eval-20260804 | en, zh | asr | test | 2 | unspecified | — |
| vitw_real_echo | eval-20260804 | en, zh | asr | test | 2 | unspecified | — |
| vitw_real_far_field | eval-20260804 | en, zh | asr | test | 2 | unspecified | — |
| vitw_real_mixed | eval-20260804 | en, zh | asr | test | 2 | unspecified | — |
| vitw_real_noise | eval-20260804 | en, zh | asr | test | 2 | unspecified | — |
| vitw_real_obstructed | eval-20260804 | en, zh | asr | test | 2 | unspecified | — |
| vitw_real_recording | eval-20260804 | en, zh | asr | test | 2 | unspecified | — |
| vitw_syn_distortion | eval-20260804 | en, zh | asr | test | 2 | unspecified | — |
| vitw_syn_dropout | eval-20260804 | en, zh | asr | test | 2 | unspecified | — |
| vitw_syn_echo | eval-20260804 | en, zh | asr | test | 2 | unspecified | — |
| vitw_syn_far_field | eval-20260804 | en, zh | asr | test | 2 | unspecified | — |
| vitw_syn_mixed | eval-20260804 | en, zh | asr | test | 2 | unspecified | — |
| vitw_syn_noise | eval-20260804 | en, zh | asr | test | 2 | unspecified | — |
| vitw_syn_obstructed | eval-20260804 | en, zh | asr | test | 2 | unspecified | — |
| vitw_syn_recording | eval-20260804 | en, zh | asr | test | 2 | unspecified | — |
| wenetspeech | eval-20260804 | zh | asr | wenetspeech_test_net, wenetspeech_test_meeting | 4 | unspecified | — |
| wenetspeech_test_meeting | eval-20260804 | zh | asr | test | 2 | unspecified | — |
| wenetspeech_test_net | eval-20260804 | zh | asr | test | 2 | unspecified | — |

</details>

<details><summary><code>synthetic_asr.jsonl</code> — 4 个版本</summary>

| Dataset | Version | Languages | Tasks | Splits | Artifacts | Integrity | Derived from |
|---|---|---|---|---|---:|---|---|
| police_synthetic_zh_accent | v1-20260817 | zh | asr | train, train_cosyvoice3, train_qwen3_tts | 8 | verified | — |
| police_synthetic_zh_accent | v2-20260818 | zh | asr | train, train_cosyvoice3, train_qwen3_tts, test, test_cosyvoice3, test_qwen3_tts | 15 | verified | — |
| police_synthetic_zh_accent | v3-20260820 | zh | asr | train, train_cosyvoice3, train_qwen3_tts | 10 | verified | — |
| police_synthetic_zh_accent | v5-20260830-qwen75-cosy25 | zh | asr | train, train_qwen3_tts, train_cosyvoice3 | 7 | verified | police_synthetic_zh_accent |

</details>

<details><summary><code>synthetic_asr_v5_qc.jsonl</code> — 1 个版本</summary>

| Dataset | Version | Languages | Tasks | Splits | Artifacts | Integrity | Derived from |
|---|---|---|---|---|---:|---|---|
| police_synthetic_zh_accent | v5-20260830-qc | zh | asr | train, train_qwen3_tts, train_cosyvoice3 | 6 | verified | — |

</details>

<details><summary><code>wenetspeech_weak.jsonl</code> — 2 个版本</summary>

| Dataset | Version | Languages | Tasks | Splits | Artifacts | Integrity | Derived from |
|---|---|---|---|---|---:|---|---|
| wenetspeech | clean-weak-v1-20260904 | zh | asr | train | 3 | verified | wenetspeech |
| wenetspeech | weak-source-20260904 | zh | asr | train | 2 | verified | — |

</details>

## 逻辑 View

| View | Version | Source | Result | Transforms | Materialization | Lineage |
|---|---|---|---|---|---|---|
| aidatatang/hotwords | v1-20260805 | aidatatang@legacy-20260804 | aidatatang_hotwords@hotwords-v1-20260805 | punctuation@legacy → hotwords@v1 | full | inferred |
| aishell/clean | v1-20260805 | aishell@legacy-20260804 | aishell_clean@clean-v1-20260805 | punctuation@legacy → clean@v1 | full | inferred |
| aishell/hotwords | v1-20260805 | aishell@legacy-20260804 | aishell_hotwords@hotwords-v1-20260805 | punctuation@legacy → clean@v1 → hotwords@v1 | full | inferred |
| aishell2/clean | v1-20260805 | aishell2@legacy-20260804 | aishell2_clean@clean-v1-20260805 | clean@v1 | full | inferred |
| aishell2/hotwords | v1-20260805 | aishell2@legacy-20260804 | aishell2_hotwords@hotwords-v1-20260805 | clean@v1 → hotwords@v1 | full | inferred |
| aishell3/hotwords | v1-20260805 | aishell3@legacy-20260804 | aishell3_hotwords@hotwords-v1-20260805 | punctuation@legacy → hotwords@v1 | full | inferred |
| common_voice_en/clean | v1-20260805 | common_voice_en@legacy-20260804 | commonvoice_en_clean@clean-v1-20260805 | select-original-text@legacy → punctuation@legacy → clean@v1 | full | inferred |
| common_voice_en/hotwords | v1-20260805 | common_voice_en@legacy-20260804 | commonvoice_en_hotwords@hotwords-v1-20260805 | select-original-text@legacy → punctuation@legacy → clean@v1 → hotwords@v1 | full | inferred |
| common_voice_zh/clean | v1-20260805 | common_voice_zh@legacy-20260804 | commonvoice_zh_clean@clean-v1-20260805 | punctuation@legacy → clean@v1 | full | inferred |
| common_voice_zh/hotwords | v1-20260805 | common_voice_zh@legacy-20260804 | commonvoice_zh_hotwords@hotwords-v1-20260805 | punctuation@legacy → clean@v1 → hotwords@v1 | full | inferred |
| gigaspeech2_id/hotwords | v1-20260805 | gigaspeech2_id@local-20260805 | gigaspeech2_id_hotwords@hotwords-v1-20260805 | select-hotword-subset@legacy → hotwords@v1 | full | inferred |
| kespeech/clean | v1-20260805 | kespeech@legacy-20260804 | kespeech_clean@clean-v1-20260805 | punctuation@legacy → clean@v1 | full | inferred |
| kespeech/hotwords | v1-20260805 | kespeech@legacy-20260804 | kespeech_hotwords@hotwords-v1-20260805 | punctuation@legacy → clean@v1 → hotwords@v1 | full | inferred |
| magicdata/hotwords | v1-20260805 | magicdata@legacy-20260804 | magicdata_hotwords@hotwords-v1-20260805 | punctuation@legacy → hotwords@v1 | full | inferred |
| talcs/hotwords | v1-20260805 | talcs@legacy-20260804 | talcs_hotwords@hotwords-v1-20260805 | punctuation@legacy → hotwords@v1 | full | inferred |
| thchs30/hotwords | v1-20260805 | thchs30@legacy-20260804 | thchs30_hotwords@hotwords-v1-20260805 | punctuation@legacy → hotwords@v1 | full | inferred |
| wenetspeech/clean | v1-20260805 | wenetspeech@legacy-20260804 | wenetspeech_clean@clean-v1-20260805 | punctuation@legacy → clean@v1 | full | inferred |
| wenetspeech/clean | v3-20260828 | wenetspeech@legacy-20260804 | wenetspeech_clean@clean-v3-20260828 | clean@consensus-v6+wenetspeech-faithful-v5 | full | exact |
| wenetspeech/clean | weak-v1-20260904 | wenetspeech@weak-source-20260904 | wenetspeech@clean-weak-v1-20260904 | clean@consensus-v6+wenetspeech-faithful-v5 | full | exact |

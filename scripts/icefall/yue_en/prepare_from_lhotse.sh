#!/usr/bin/env bash
#
# 一键从 /ai_sds_wuzz/DATA_ASR/LHOTSE 上准备所有 ASR 数据集的 fbank 与
# 粤英 BBPE-${vocab_size} 词表，供 amphion/yue_en/ASR/zipformer 训练使用。
#
# 设计前提（与 amphion/zh_en 保持思路一致，粤英特化）：
#   - 你已经在 LHOTSE_ROOT 下有各数据集的 lhotse manifests
#     （recordings + supervisions），但还没算 fbank。
#   - 若没有 mdcc / WenetSpeech-Yue / common_voice_yue manifests，
#     脚本会尝试从相应"上游位置"软链过来：
#       mdcc          : 通过 mdcc/ASR/prepare.sh stage 1 自动生成
#       WenetSpeech-Yue: 假设用户已在
#                       /ai_sds_wuzz/MULTILINGUAL_DATA/zh/WenetSpeech-Yue
#                       下跑过 local/prepare.sh 生成 manifests
#       common_voice_yue: 若 LHOTSE 下没有，会跳过
#
# 用法：
#   bash prepare_from_lhotse.sh [--stage N] [--stop-stage M] \
#                               [--lhotse-root /ai_sds_wuzz/DATA_ASR/LHOTSE] \
#                               [--multilingual-root /ai_sds_wuzz/MULTILINGUAL_DATA] \
#                               [--use-cleaned-cumix true] \
#                               [--perturb-speed false] \
#                               [--vocab-size 8000] \
#                               [--yue-text-meta-jsonl /path/to/wenetspeech_yue_meta.jsonl] \
#                               [--yue-text-field rover_result] \
#                               [--yue-text-min-confidence 0.0]
#
# Stage 总览：
#   1   软链所有数据集的 manifests 到对应 recipe / LHOTSE root（一次性）
#   ── 简单数据集 fbank（默认全跑）──
#   2   LibriSpeech                        @ librispeech/ASR
#   3   MUSAN（噪声）                      @ librispeech/ASR
#   4   MDCC（粤语 ~73h）                  @ mdcc/ASR
#   5   cumix2017（粤英 ~17h）             @ amphion/yue_en/ASR/local 自定义
#   6   MLS English                        @ amphion/shared_amphion/compute_fbank_mls.py（共享）
#   13  生成 lhotse 直读训练用的 musan_cuts.jsonl.gz（不带 fbank）
#       输出位置：<lhotse-root>/musan_cuts.jsonl.gz
#       供 train.py（--data-source lhotse）+ CutMix 噪声增强直接读
#   14  生成 lhotse 直读训练用的 traffic_noise_cuts.jsonl.gz（不带 fbank）
#       输入：AudioSet RoadTraffic 子集
#         /ai_sds_wuzz/MULTILINGUAL_DATA/noise/AudioSet_RoadTraffic/data/manifests/
#       输出位置：<lhotse-root>/traffic_noise_cuts.jsonl.gz
#       供 train.py（--enable-traffic-noise 1）作为独立 CutMix transform 使用
#   15  生成 traffic noise robustness 评测用的 deterministic 带噪 test cuts
#       输入：<lhotse-root>/traffic_noise_cuts.jsonl.gz（stage 14 产出）+
#             librispeech / wenetspeech / mdcc / talcs 的 clean test cuts
#       输出位置：<lhotse-root>/eval_traffic/{base}_{sub}_traffic_noisy_snr{N}db_cuts.jsonl.gz
#       供 test.sh -t librispeech_traffic_snr10 等 noisy 数据集名直接消费
#       （lhotse_datasets.py 已注册 20 个 dataset spec × 5 SNR）
#   ── BBPE 词表准备（默认跑） ──
#   80  librispeech lang_bpe_500（从 supervisions）
#   81  amphion lang_char（从 WenetSpeech-Yue meta jsonl，用 pycantonese 分词）
#   82  amphion BBPE-${vocab_size} + 软链 data
#   ── 复杂数据集 fbank（默认不跑，需显式 --stage 50+） ──
#   50  WenetSpeech-Yue（粤语大数据，split 流程，几小时）
#   51  GigaSpeech（split 流程，~1 天）    @ gigaspeech/ASR
#   52  CommonVoice yue                    @ commonvoice/ASR（如有）
#   53  CommonVoice en                     @ commonvoice/ASR

export PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python

set -eou pipefail

# 根据脚本所在位置定位仓库根目录，使脚本可以从任何 cwd 调用。
if [ "${1:-}" != "--icefall-root" ] || [ "$#" -lt 2 ]; then
  echo "Usage: $0 --icefall-root /path/to/icefall [preparation options]" >&2
  exit 2
fi
repo_root="$(cd "$2" && pwd)"
shift 2
script_dir="$repo_root/egs/amphion/yue_en/ASR"
cd "$script_dir"

# icefall is shipped as a source repo (not pip-installed), so we have to
# add the repo root to PYTHONPATH for `import icefall` to work in any
# delegated script (prepare_char.py, validate_manifest.py, ...).
export PYTHONPATH="$repo_root:${PYTHONPATH:-}"

# Auto-locate CUDA libs from pip-installed nvidia-* wheels (cuda_nvrtc,
# cuda_runtime, cudnn, cublas, ...). Without this, importing k2 may fail
# with "libnvrtc.so.12: cannot open shared object file".
if python3 -c "import nvidia" 2>/dev/null; then
  _nvidia_root=$(python3 -c 'import nvidia; print(next(iter(nvidia.__path__)))')
  for _d in "$_nvidia_root"/*/lib; do
    if [ -d "$_d" ]; then
      export LD_LIBRARY_PATH="$_d:${LD_LIBRARY_PATH:-}"
    fi
  done
  unset _nvidia_root _d
fi

stage=1
stop_stage=15               # 默认跑到 fbank 阶段 + lhotse 直读 MUSAN cuts +
                            # AudioSet RoadTraffic noise cuts + 带噪 eval test cuts；
                            # BBPE 准备建议另外用 --stage 80
lhotse_root="/ai_sds_wuzz/DATA_ASR/LHOTSE"
multilingual_root="/ai_sds_wuzz/MULTILINGUAL_DATA"
use_cleaned_cumix=true      # cumix2017 supervisions 优先用 cleaned 版本
perturb_speed=true          # 训练集启用 0.9/1.1 倍速扰动
vocab_size=8000             # BBPE 词表大小（透传给 amphion prepare.sh stage 4）

# Stage 81 — 粤语文本来源（用于 BBPE 词表训练）。
# 默认从 WenetSpeech-Yue 的 meta jsonl 抽取（数据量比 mdcc 大两个数量级，
# 词表覆盖更广）；如需切回 mdcc supervisions，可手工修改 Stage 81 实现。
yue_text_meta_jsonl="$multilingual_root/zh/WenetSpeech-Yue/data/meta/wenetspeech_yue_meta.jsonl"
yue_text_field="rover_result"     # 推荐字段；备选 sensevoice_text / whisper_text / teleasr_text / punc_text
yue_text_min_confidence="0.0"     # 0.0=不过滤；想严过滤可用 0.7~0.9（基于 obj.confidence）

. shared/parse_options.sh || exit 1

log() {
  local fname=${BASH_SOURCE[1]##*/}
  echo -e "$(date '+%Y-%m-%d %H:%M:%S') (${fname}:${BASH_LINENO[0]}:${FUNCNAME[1]}) $*"
}

libri_dir="$repo_root/egs/librispeech/ASR"
mdcc_dir="$repo_root/egs/mdcc/ASR"
gigaspeech_dir="$repo_root/egs/gigaspeech/ASR"
commonvoice_dir="$repo_root/egs/commonvoice/ASR"

log "script_dir:        $script_dir"
log "repo_root:         $repo_root"
log "lhotse_root:       $lhotse_root"
log "multilingual_root: $multilingual_root"

# ---------------------------------------------------------------------------
# 工具函数：把 src 软链到 dst（dst 不存在时）
# ---------------------------------------------------------------------------
link_if_missing() {
  local src="$1"
  local dst="$2"
  if [ ! -e "$src" ]; then
    return
  fi
  if [ -e "$dst" ] || [ -L "$dst" ]; then
    return
  fi
  mkdir -p "$(dirname "$dst")"
  ln -svf "$src" "$dst"
}

# 把整个目录里的 *.jsonl.gz 都软链到目标目录（保持原文件名）
link_all_in_dir() {
  local src_dir="$1"
  local dst_dir="$2"
  if [ ! -d "$src_dir" ]; then
    return
  fi
  mkdir -p "$dst_dir"
  for f in "$src_dir"/*.jsonl.gz; do
    [ -e "$f" ] || continue
    link_if_missing "$f" "$dst_dir/$(basename "$f")"
  done
}

# ===========================================================================
# Stage 1: 软链所有数据集的 manifests
# ===========================================================================
if [ $stage -le 1 ] && [ $stop_stage -ge 1 ]; then
  log "Stage 1: Symlink manifests from $lhotse_root → upstream recipes / LHOTSE root"

  # ---- LibriSpeech ----
  link_all_in_dir "$lhotse_root/LibriSpeech/data/manifests" \
                  "$libri_dir/data/manifests"
  touch "$libri_dir/data/manifests/.librispeech.done" 2>/dev/null || true

  # ---- MUSAN ----
  link_all_in_dir "$lhotse_root/MUSAN/data/manifests" \
                  "$libri_dir/data/manifests"
  touch "$libri_dir/data/manifests/.musan.done" 2>/dev/null || true

  # ---- MDCC ----
  # mdcc recipe 自己用 `lhotse prepare mdcc` 生成 manifests；如果
  # LHOTSE 根下已有 mdcc/data/manifests/，直接软链过去。
  if [ -d "$lhotse_root/mdcc/data/manifests" ]; then
    link_all_in_dir "$lhotse_root/mdcc/data/manifests" \
                    "$mdcc_dir/data/manifests"
    touch "$mdcc_dir/data/manifests/.mdcc_manifests.done" 2>/dev/null || true
  else
    log "Note: $lhotse_root/mdcc/data/manifests not found."
    log "      Will run mdcc/ASR/prepare.sh stage 1 in stage 4 to generate manifests"
    log "      (requires mdcc/ASR/download/mdcc/ to exist; see mdcc/ASR/prepare.sh)."
  fi

  # ---- cumix2017（粤英 code-switch，已在 LHOTSE 根下）----
  # cumix2017 不依赖任何上游 recipe；本 recipe 直接从 LHOTSE 读它。
  cumix_src="$lhotse_root/cumix2017/data/manifests"
  cumix_local="$script_dir/data/manifests/cumix2017"
  link_all_in_dir "$cumix_src" "$cumix_local"

  # ---- WenetSpeech-Yue ----
  # 用户在 /ai_sds_wuzz/MULTILINGUAL_DATA/zh/WenetSpeech-Yue 下跑过
  # local/prepare.sh 后，data/manifests/ 会有 wenetspeech_yue_*.jsonl.gz。
  # 我们把它软链到 lhotse_root/WenetSpeech-Yue/data/manifests/，让 lhotse
  # 直读模式可以用同一 --lhotse-root 找到它。
  yue_src="$multilingual_root/zh/WenetSpeech-Yue/data/manifests"
  yue_dst="$lhotse_root/WenetSpeech-Yue/data/manifests"
  if [ -d "$yue_src" ] && ls "$yue_src"/wenetspeech_yue_*.jsonl.gz >/dev/null 2>&1; then
    link_all_in_dir "$yue_src" "$yue_dst"
  else
    log "Note: $yue_src not populated yet. To use WenetSpeech-Yue, please run:"
    log "      bash $multilingual_root/zh/WenetSpeech-Yue/local/prepare.sh"
  fi

  # ---- common_voice_yue（可选）----
  cv_yue_src="$lhotse_root/common_voice_yue/data/manifests"
  if [ -d "$cv_yue_src" ]; then
    log "common_voice_yue manifests already present at $cv_yue_src"
  else
    # 若 multilingual 目录下有粤语 CommonVoice manifests，可以软链过来。
    cv_yue_alt="$multilingual_root/zh/common_voice_yue/data/manifests"
    if [ -d "$cv_yue_alt" ]; then
      link_all_in_dir "$cv_yue_alt" "$cv_yue_src"
    fi
  fi

  # ---- CommonVoice EN ----
  link_all_in_dir "$lhotse_root/common_voice_en/data/manifests" \
                  "$commonvoice_dir/data/en/manifests"

  # ---- MLS English ----
  link_all_in_dir "$lhotse_root/MLS/data/manifests" \
                  "$script_dir/data/manifests/mls"

  # ---- GigaSpeech（gigaspeech/ASR/data/manifests/） ----
  link_all_in_dir "$lhotse_root/GigaSpeech/data/manifests" \
                  "$gigaspeech_dir/data/manifests"

  log "Stage 1 done."
fi

# ===========================================================================
# Stage 2: LibriSpeech fbank
# ===========================================================================
if [ $stage -le 2 ] && [ $stop_stage -ge 2 ]; then
  log "Stage 2: Compute LibriSpeech fbank (delegating to librispeech recipe)"
  pushd "$libri_dir" >/dev/null
  mkdir -p data/fbank
  if [ ! -e data/fbank/.librispeech.done ]; then
    ./local/compute_fbank_librispeech.py --perturb-speed "$perturb_speed"
    touch data/fbank/.librispeech.done
  fi

  if [ ! -f data/fbank/librispeech_cuts_train-all-shuf.jsonl.gz ]; then
    cat <(gunzip -c data/fbank/librispeech_cuts_train-clean-100.jsonl.gz) \
      <(gunzip -c data/fbank/librispeech_cuts_train-clean-360.jsonl.gz) \
      <(gunzip -c data/fbank/librispeech_cuts_train-other-500.jsonl.gz) | \
      shuf | gzip -c > data/fbank/librispeech_cuts_train-all-shuf.jsonl.gz
  fi

  if [ ! -e data/fbank/.librispeech-validated.done ]; then
    log "Validating data/fbank for LibriSpeech"
    parts=(
      train-clean-100
      train-clean-360
      train-other-500
      test-clean
      test-other
      dev-clean
      dev-other
    )
    for part in ${parts[@]}; do
      python3 ./local/validate_manifest.py \
        data/fbank/librispeech_cuts_${part}.jsonl.gz
    done
    touch data/fbank/.librispeech-validated.done
  fi
  popd >/dev/null
fi

# ===========================================================================
# Stage 3: MUSAN fbank
# ===========================================================================
if [ $stage -le 3 ] && [ $stop_stage -ge 3 ]; then
  log "Stage 3: Compute MUSAN fbank"
  pushd "$libri_dir" >/dev/null
  ./prepare.sh --stage 4 --stop-stage 4
  popd >/dev/null
fi

# ===========================================================================
# Stage 4: MDCC fbank + lang_char（粤语主力 ~73h）
# ===========================================================================
if [ $stage -le 4 ] && [ $stop_stage -ge 4 ]; then
  log "Stage 4: Compute MDCC fbank and prepare lang_char (delegating to mdcc recipe)"
  pushd "$mdcc_dir" >/dev/null

  # stage 1: prepare manifests (如果 stage 1 已经软链好就 idempotent 跳过)
  if [ ! -e data/manifests/.mdcc_manifests.done ]; then
    ./prepare.sh --stage 1 --stop-stage 1
  fi
  # stage 3: compute fbank
  if [ ! -e data/fbank/.mdcc.done ]; then
    ./prepare.sh --stage 3 --stop-stage 3
  fi
  # stage 5: lang_char (用 pycantonese 分词)
  if [ ! -f data/lang_char/text_words_segmentation ]; then
    ./prepare.sh --stage 5 --stop-stage 5
  fi
  popd >/dev/null
fi

# ===========================================================================
# Stage 5: cumix2017 fbank（粤英 code-switch，自定义脚本）
# ---------------------------------------------------------------------------
# icefall 没有 cumix2017 recipe，所以输出到本目录的 data/fbank/ 下。
# ===========================================================================
if [ $stage -le 5 ] && [ $stop_stage -ge 5 ]; then
  log "Stage 5: Compute cumix2017 fbank (custom script)"
  if [ ! -f data/fbank/.cumix2017.done ]; then
    mkdir -p data/fbank
    python3 ./compute_fbank_cumix2017.py \
      --speed-perturb "$perturb_speed" \
      --use-cleaned "$use_cleaned_cumix"
    touch data/fbank/.cumix2017.done
  fi
fi

# ===========================================================================
# Stage 6: MLS English fbank（用 shared_amphion 的 compute_fbank_mls.py）
# ===========================================================================
if [ $stage -le 6 ] && [ $stop_stage -ge 6 ]; then
  log "Stage 6: Compute MLS English fbank (custom script)"
  if [ ! -f data/fbank/.mls.done ]; then
    mkdir -p data/fbank
    python3 ./compute_fbank_mls.py --speed-perturb "$perturb_speed"
    touch data/fbank/.mls.done
  fi
fi

# ===========================================================================
# Stage 13: lhotse-direct MUSAN cuts（不带 fbank）
# ---------------------------------------------------------------------------
# 起因：train.py（--data-source lhotse）在启动时会到 --lhotse-root 根下找
# `musan_cuts.jsonl.gz`，找不到就自动把 enable_musan 关掉（见 train.py 1757-
# 1765 行的兜底逻辑）。这里把 LHOTSE/MUSAN/data/manifests/ 下三类录音合
# 并、按 10 秒切片、过滤掉 < 5 秒的尾段，写到 <lhotse-root>/musan_cuts.jsonl.gz。
#
# 不预算 fbank：lhotse 直读 + OnTheFlyFeatures 模式下，CutMix 在音频层做
# 混合，fbank 在 input_strategy 层即时计算，预算 fbank 是浪费磁盘和时间。
#
# 执行很快（<10 秒），输出 <1 MB（仅元数据）。幂等：已经存在则跳过，加
# --force 强制重生成。该文件由 zh_en / yue_en 共享（两个 recipe 都用同一
# --lhotse-root），任意一个 recipe 跑过 stage 13 后另一个直接受益。
# ===========================================================================
if [ $stage -le 13 ] && [ $stop_stage -ge 13 ]; then
  log "Stage 13: Build lhotse-direct musan_cuts.jsonl.gz under \$lhotse_root"
  # build_musan_cuts.py 是 amphion 私有共享脚本（softlink 到
  # shared_amphion/build_musan_cuts.py）；不能放进 ./local/，因为 ./local
  # 整个目录是 symlink 到 multi_zh_en/ASR/local，写入会污染上游 recipe。
  python3 ./build_musan_cuts.py \
    --lhotse-root "$lhotse_root"
fi

# ===========================================================================
# Stage 14: lhotse-direct AudioSet RoadTraffic noise cuts（不带 fbank）
# ---------------------------------------------------------------------------
# 输入：$multilingual_root/noise/AudioSet_RoadTraffic/data/manifests/
#         audioset_road_traffic_recordings_noise.jsonl.gz
#       已经按 10 秒切段，48 kHz / stereo。
# 输出：<lhotse-root>/traffic_noise_cuts.jsonl.gz（mono 第 0 声道，无 fbank）。
#
# 训练侧消费方式：train.sh 加 --enable-traffic-noise 1 后，
# asr_datamodule 会装一个独立 CutMix transform（与 MUSAN 并行），按
# --traffic-noise-prob / --traffic-noise-snr 控制混入比例和强度。
#
# 与 stage 13 同样幂等（已存在则跳过；--force 覆盖），与 zh_en 共享同一
# --lhotse-root。
# ===========================================================================
if [ $stage -le 14 ] && [ $stop_stage -ge 14 ]; then
  log "Stage 14: Build lhotse-direct traffic_noise_cuts.jsonl.gz under \$lhotse_root"
  python3 ./build_traffic_noise_cuts.py \
    --lhotse-root "$lhotse_root" \
    --recordings-jsonl \
      "$multilingual_root/noise/AudioSet_RoadTraffic/data/manifests/audioset_road_traffic_recordings_noise.jsonl.gz"
fi

# ===========================================================================
# Stage 15: 交通噪声 robustness 评测用的 deterministic 带噪 test cuts
# ---------------------------------------------------------------------------
# 输入：
#   * <lhotse_root>/traffic_noise_cuts.jsonl.gz（stage 14 产出）
#   * librispeech / wenetspeech / mdcc / talcs 的 clean test cuts
#     （由 lhotse_datasets.DATASET_SPECS 自动定位）
#
# 输出：<lhotse_root>/eval_traffic/{base}_{sub}_traffic_noisy_snr{N}db_cuts.jsonl.gz
#       5 个 base sub-split × 5 档 SNR（0/5/10/15/20 dB）= 25 个 manifest 文件。
#       每个仅含 MixedCut metadata（< 30 MB），audio 仍引用原 source；总开销 < 100 MB。
#
# 评测侧消费：lhotse_datasets.py 已注册 20 个 dataset spec（4 base × 5 SNR）。
# 直接用 `bash test.sh -c <ckpt> -t librispeech_traffic_snr10,...` 即可，
# 与 clean test 集走完全相同的 decode → summarize_wer → _summary.html 链路。
#
# Determinism：lhotse cuts.mix(seed=int).to_eager().to_file() 把 noise selection
# / offset / SNR 全部固化到 MixedCut.tracks；同一份 manifest 任意次 load_audio
# 都得到 bit-identical 波形（PoC 已用 np.array_equal 验证）。
#
# 与 stage 13/14 同样幂等（已存在则跳过；--force 覆盖）。
# ===========================================================================
if [ $stage -le 15 ] && [ $stop_stage -ge 15 ]; then
  log "Stage 15: Build deterministic noisy test cuts under \$lhotse_root/eval_traffic/"
  python3 ./build_noisy_test_cuts.py \
    --lhotse-root "$lhotse_root"
fi

# ===========================================================================
# Stage 16: 规整 amphion 私有 manifest 副本（sup.duration + 扫坏 .opus）
# ---------------------------------------------------------------------------
# 目的（详见 docs/training_lessons.md §1.7）：
#   1. sup.duration 规整到 = recording.duration - sup.start，消除 legco-speech
#      等 chunked manifest 的"supervision.duration < cut.duration"现象（这是
#      subsampling assert `x.size(1) == x_lens.max()` 的一类根因；另一类
#      CutMix padding 的运行时根因只能由 dataloader wrapper 修补）。
#   2. --scan-audio：用 multiproc + lhotse backend chain 试 load 每条 cut，
#      把 ffmpeg 也救不回的 ~1e-6 真坏样本从输出 manifest 剔除。剔除后
#      训练时 fault_tolerant 将不再触发，但仍作为防御性兜底保留。
#
# 输出：<lhotse-root>/_amphion_normalized/<dataset>/<supervisions-basename>
#   * 不动 recordings：dangling rec（没 sup 引用）对 amphion training pipeline
#     无害（CutSet.from_manifests 仅按 sup 生成 cuts）。
#   * 配套写出 <dst-sup>.{stats.json,broken.txt,checkpoint}。
#   * `lhotse_datasets.py` 阶段 3.1 后才会切到读这个新路径；本 stage 跑完
#     训练侧仍读原 manifests，没有 immediate behavioural change。
#
# 数据集范围：默认覆盖 yue_en 训练用的全部数据集（与 train.sh 的
# TRAIN_DATASETS 对齐）。如果想限定可以传 --normalize-datasets。
# 耗时：scan-audio 路径下 legco_speech 9.45M cut ~1-2 h（64 worker / ffmpeg
# IO 主导）；其它数据集分别数分钟。整体 1-6 h 视磁盘吞吐而定。
# 幂等：默认跳过已存在的 dst-sup；--normalize-force=true 强制重算。
# ===========================================================================
if [ $stage -le 16 ] && [ $stop_stage -ge 16 ]; then
  log "Stage 16: Normalize manifests under \$lhotse_root/_amphion_normalized/"
  norm_datasets="${normalize_datasets:-librispeech,mls,gigaspeech,common_voice_en,cumix2017,mdcc,wenetspeech_yue,legco_speech,legco_speech_en}"
  norm_splits="${normalize_splits:-train}"
  norm_workers="${normalize_workers:-64}"
  norm_scan="${normalize_scan_audio:-true}"
  norm_force="${normalize_force:-false}"
  scan_audio_flag=""
  if [ "$norm_scan" = "true" ]; then
    scan_audio_flag="--scan-audio"
  fi
  force_flag=""
  if [ "$norm_force" = "true" ]; then
    force_flag="--force"
  fi
  python3 "$repo_root/egs/amphion/shared_amphion/local/normalize_dataset.py" \
    --datasets "$norm_datasets" \
    --splits "$norm_splits" \
    --lhotse-root "$lhotse_root" \
    --dst-root "$lhotse_root/_amphion_normalized" \
    --num-workers "$norm_workers" \
    $scan_audio_flag $force_flag
fi

# ===========================================================================
# Stage 50: WenetSpeech-Yue fbank（粤语大数据；split 流程，几小时）
# ===========================================================================
if [ $stage -le 50 ] && [ $stop_stage -ge 50 ]; then
  log "Stage 50: Compute WenetSpeech-Yue fbank (split pipeline)"
  yue_manifest_dir="$lhotse_root/WenetSpeech-Yue/data/manifests"
  if [ ! -d "$yue_manifest_dir" ]; then
    log "  Skip: $yue_manifest_dir not found. Run stage 1 first."
  elif [ ! -f data/fbank/.wenetspeech_yue.done ]; then
    mkdir -p data/fbank
    python3 ./compute_fbank_wenetspeech_yue.py --speed-perturb "$perturb_speed"
    touch data/fbank/.wenetspeech_yue.done
  fi
fi

# ===========================================================================
# Stage 51: GigaSpeech fbank（split 流程，~1 天；强烈建议多 GPU/多机）
# ===========================================================================
if [ $stage -le 51 ] && [ $stop_stage -ge 51 ]; then
  log "Stage 51: Compute GigaSpeech fbank (split pipeline, very slow)"
  pushd "$gigaspeech_dir" >/dev/null
  ./prepare.sh --stage 4 --stop-stage 6
  popd >/dev/null
fi

# ===========================================================================
# Stage 52: CommonVoice yue fbank（如果有）
# ===========================================================================
if [ $stage -le 52 ] && [ $stop_stage -ge 52 ]; then
  log "Stage 52: Compute CommonVoice yue fbank (if available)"
  if [ -d "$lhotse_root/common_voice_yue/data/manifests" ]; then
    pushd "$commonvoice_dir" >/dev/null
    # 复用 commonvoice/ASR/prepare.sh，但 language=yue
    ./prepare.sh --stage 3 --stop-stage 6 --release "" \
      --use-validated false --use-invalidated false || \
      log "  Note: commonvoice/prepare.sh might require --language argument; check upstream."
    popd >/dev/null
  else
    log "  Skip: $lhotse_root/common_voice_yue/data/manifests not found."
  fi
fi

# ===========================================================================
# Stage 53: CommonVoice en fbank
# ===========================================================================
if [ $stage -le 53 ] && [ $stop_stage -ge 53 ]; then
  log "Stage 53: Compute CommonVoice en fbank"
  pushd "$commonvoice_dir" >/dev/null
  ./prepare.sh --stage 3 --stop-stage 6 --release "" \
    --use-validated false --use-invalidated false || \
    log "  Note: commonvoice/prepare.sh might require --release argument; check upstream."
  popd >/dev/null
fi

# ===========================================================================
# Stage 80: librispeech lang_bpe_500
#
# 直接从 LHOTSE 下的 librispeech_supervisions_*.jsonl.gz 抽 transcript_words.txt
# （不依赖 stage 1 的 manifests 软链，也不依赖原始 LibriSpeech 音频路径下的
# *.trans.txt），然后用 librispeech recipe 自带的 train_bpe_model.py 训 BPE-500。
# ===========================================================================
if [ $stage -le 80 ] && [ $stop_stage -ge 80 ]; then
  log "Stage 80: Build lang_bpe_500 for LibriSpeech (read manifests from LHOTSE)"
  lang_dir="$libri_dir/data/lang_bpe_500"
  mkdir -p "$lang_dir"

  if [ ! -s "$lang_dir/transcript_words.txt" ]; then
    log "  Generating $lang_dir/transcript_words.txt from LHOTSE supervisions..."
    : > "$lang_dir/transcript_words.txt"
    found_any=0
    for part in train-clean-100 train-clean-360 train-other-500; do
      sup="$lhotse_root/LibriSpeech/data/manifests/librispeech_supervisions_${part}.jsonl.gz"
      if [ ! -e "$sup" ]; then
        sup="$libri_dir/data/manifests/librispeech_supervisions_${part}.jsonl.gz"
      fi
      if [ ! -e "$sup" ]; then
        log "  WARNING: librispeech_supervisions_${part}.jsonl.gz not found in either"
        log "           $lhotse_root/LibriSpeech/data/manifests/ or $libri_dir/data/manifests/. Skip."
        continue
      fi
      log "  Reading $sup"
      found_any=1
      python3 - "$sup" >> "$lang_dir/transcript_words.txt" <<'PY'
import gzip, json, sys
src = sys.argv[1]
with gzip.open(src, "rt", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        text = obj.get("text", "")
        if text:
            print(text)
PY
    done
    if [ $found_any -eq 0 ]; then
      log "  ERROR: No LibriSpeech supervisions found. Check --lhotse-root."
      log "         Tried: $lhotse_root/LibriSpeech/data/manifests/"
      exit 1
    fi
    n_lines=$(wc -l < "$lang_dir/transcript_words.txt")
    log "  Done. Lines: $n_lines"
    if [ "$n_lines" -eq 0 ]; then
      log "  ERROR: transcript_words.txt is empty after extraction. Check supervisions content."
      exit 1
    fi
  else
    log "  $lang_dir/transcript_words.txt already exists, skip extraction."
  fi

  if [ ! -f "$lang_dir/bpe.model" ]; then
    log "  Training BPE-500 on transcript_words.txt..."
    pushd "$libri_dir" >/dev/null
    python3 ./local/train_bpe_model.py \
      --lang-dir "$lang_dir" \
      --vocab-size 500 \
      --transcript "$lang_dir/transcript_words.txt"
    popd >/dev/null
  fi
fi

# ===========================================================================
# Stage 81: amphion lang_char（粤语主力，从 WenetSpeech-Yue meta jsonl 抽取）
#
# 不再依赖 mdcc supervisions。改为从 $yue_text_meta_jsonl
# （默认 /ai_sds_wuzz/MULTILINGUAL_DATA/zh/WenetSpeech-Yue/data/meta/wenetspeech_yue_meta.jsonl）
# 抽取粤语转录文本，再用 mdcc/local/preprocess_mdcc.py 做 pycantonese 分词，
# 最终生成 BBPE 训练所需的：
#   - text                       （pycantonese 分词后的版本，与 mdcc stage 5 行为一致）
#   - _text                      （原始未分词版本备份）
#   - text_norm / text_words_segmentation / words_no_ids.txt / words.txt
#   - L_disambig.pt              （prepare_char.py 生成）
#
# 输出目录：amphion/yue_en/ASR/data/lang_char/（本地，不污染 mdcc recipe）。
# 上层 prepare.sh stage 4 已优先读本目录，与 Stage 82 自动衔接。
#
# 可配置参数：
#   --yue-text-meta-jsonl     完整路径，默认见 $yue_text_meta_jsonl
#   --yue-text-field          jsonl 中的字段名，默认 rover_result
#                             （备选：sensevoice_text / whisper_text / teleasr_text / punc_text）
#   --yue-text-min-confidence 按 obj.confidence 过滤，默认 0.0=不过滤
#
# 注意：~6.8M 行的 pycantonese 分词比较耗时（数小时量级，单进程），
#       完成一次后会被 idempotent 跳过。
# ===========================================================================
if [ $stage -le 81 ] && [ $stop_stage -ge 81 ]; then
  log "Stage 81: Build lang_char for amphion/yue_en (from WenetSpeech-Yue meta jsonl)"
  log "  meta jsonl     = $yue_text_meta_jsonl"
  log "  field          = $yue_text_field"
  log "  min_confidence = $yue_text_min_confidence"

  if [ ! -f "$yue_text_meta_jsonl" ]; then
    log "  ERROR: $yue_text_meta_jsonl not found."
    log "         Use --yue-text-meta-jsonl to point to a valid file."
    exit 1
  fi

  lang_char_dir="$script_dir/data/lang_char"

  # 旧行为：amphion/yue_en/ASR/prepare.sh stage 4 可能曾把 data/lang_char
  # 软链到 mdcc/ASR/data/lang_char。如果是软链，删掉换成本地真目录。
  if [ -L "$lang_char_dir" ]; then
    log "  Removing existing symlink $lang_char_dir → $(readlink "$lang_char_dir")"
    rm "$lang_char_dir"
  fi
  mkdir -p "$lang_char_dir"

  # ---- 抽取粤语转录 → $lang_char_dir/text ----
  # 同时存在 text 或 _text 都视为已抽取过，跳过；想重抽请手工删掉两者。
  if [ ! -s "$lang_char_dir/text" ] && [ ! -s "$lang_char_dir/_text" ]; then
    log "  Extracting Cantonese text from $yue_text_meta_jsonl ..."
    python3 - "$yue_text_meta_jsonl" "$yue_text_field" \
              "$yue_text_min_confidence" "$lang_char_dir/text.tmp" <<'PY'
import json, sys

src, field, min_conf, dst = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
min_conf = float(min_conf)

n_in = n_out = n_skip_no_field = n_skip_low_conf = 0
with open(src, "r", encoding="utf-8") as f, \
     open(dst, "w", encoding="utf-8") as g:
    for line in f:
        n_in += 1
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        text = obj.get(field)
        if not isinstance(text, str) or not text.strip():
            n_skip_no_field += 1
            continue
        if min_conf > 0.0:
            conf = obj.get("confidence", 0.0)
            try:
                conf = float(conf)
            except (TypeError, ValueError):
                conf = 0.0
            if conf < min_conf:
                n_skip_low_conf += 1
                continue
        # normalize whitespace and strip
        text = " ".join(text.split())
        if not text:
            continue
        g.write(text + "\n")
        n_out += 1
        if n_in % 500000 == 0:
            print(
                f"  ... read {n_in} lines, written {n_out}",
                file=sys.stderr, flush=True,
            )

print(
    f"  Done. read={n_in}, written={n_out}, "
    f"skipped_no_field={n_skip_no_field}, skipped_low_conf={n_skip_low_conf}",
    file=sys.stderr,
)
PY
    mv "$lang_char_dir/text.tmp" "$lang_char_dir/text"

    n_lines=$(wc -l < "$lang_char_dir/text")
    log "  Lines extracted: $n_lines → $lang_char_dir/text"
    if [ "$n_lines" -eq 0 ]; then
      log "  ERROR: lang_char/text is empty. Check --yue-text-field='$yue_text_field' and"
      log "         --yue-text-min-confidence='$yue_text_min_confidence'."
      exit 1
    fi
  else
    log "  $lang_char_dir/text (or _text) already exists, skip extraction."
  fi

  # ---- pycantonese 分词；产出 text_norm / text_words_segmentation / words.txt 等 ----
  # 注意：mdcc/local/preprocess_mdcc.py 依赖 pycantonese；
  # 若环境缺失，请先 `pip install pycantonese`。
  # 如果之前跑过一次轮换（_text 存在），优先用未分词的 _text 作为输入。
  if [ ! -f "$lang_char_dir/text_words_segmentation" ]; then
    preprocess_input="$lang_char_dir/text"
    if [ -f "$lang_char_dir/_text" ]; then
      preprocess_input="$lang_char_dir/_text"
    fi
    log "  Running pycantonese word segmentation on $preprocess_input"
    log "  (may take hours on millions of lines; one-time, idempotent on success)..."
    python3 "$mdcc_dir/local/preprocess_mdcc.py" \
      --input-file "$preprocess_input" \
      --output-dir "$lang_char_dir"
  fi

  # ---- 与 mdcc/ASR/prepare.sh stage 5 相同的 text/_text 轮换 ----
  # 把原始 text 备份成 _text，分词版变成新的 text；BBPE 训练时直接消费分词版。
  if [ -f "$lang_char_dir/text_words_segmentation" ] && [ ! -f "$lang_char_dir/_text" ]; then
    mv "$lang_char_dir/text" "$lang_char_dir/_text"
    cp "$lang_char_dir/text_words_segmentation" "$lang_char_dir/text"
  fi

  # ---- L_disambig.pt / lexicon.txt / tokens.txt ----
  if [ ! -f "$lang_char_dir/L_disambig.pt" ]; then
    python3 "$mdcc_dir/local/prepare_char.py" --lang-dir "$lang_char_dir"
  fi
fi

# ===========================================================================
# Stage 82: amphion BBPE-${vocab_size} + 软链 data
# ===========================================================================
if [ $stage -le 82 ] && [ $stop_stage -ge 82 ]; then
  log "Stage 82: Build BBPE-${vocab_size} and link data/ (under amphion/yue_en)"
  # Only run BBPE training (amphion stage 4); skip data/ symlink (stage 5)
  # which is only needed for legacy fbank-precompute training.
  ./prepare.sh --stage 4 --stop-stage 4 --vocab-size "$vocab_size"
fi

log ""
log "All requested stages done."
log ""
log "Sanity check:"
log "  ls data/fbank/ | head"
ls data/fbank/ 2>/dev/null | head -20 || true
echo
log "  ls data/lang_bbpe_${vocab_size}/"
ls "data/lang_bbpe_${vocab_size}/" 2>/dev/null || true
echo
log ""
log "Tip: Default range is --stage 1 --stop-stage 15 (basic ASR fbank + MUSAN cuts + RoadTraffic noise cuts + noisy eval cuts)."
log "     To also build BBPE vocab: --stage 1 --stop-stage 82 --vocab-size 8000"
log "     To compute heavy datasets: --stage 50 --stop-stage 51  (WenetSpeech-Yue/GigaSpeech)"
log "     To re-generate only MUSAN cuts: --stage 13 --stop-stage 13"
log "     To re-generate only RoadTraffic noise cuts: --stage 14 --stop-stage 14"
log "     To re-generate only noisy eval test cuts: --stage 15 --stop-stage 15"

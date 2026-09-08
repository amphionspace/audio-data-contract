#!/usr/bin/env bash
#
# 一键从 /ai_sds_wuzz/DATA_ASR/LHOTSE 上准备所有 ASR 数据集的 fbank
# 并训练 BBPE-${vocab_size} 词表，供 amphion/zh_en/ASR/zipformer 训练使用。
#
# 设计前提：
#   - 你已经在 LHOTSE_ROOT 下有各数据集的 lhotse manifests
#     （recordings + supervisions），但还没算 fbank。
#   - 没有原始 LibriSpeech 音频路径下的 *.trans.txt，所以本脚本会从
#     supervisions 直接抽取英文 transcript_words.txt。
#
# 用法：
#   bash prepare_from_lhotse.sh [--stage N] [--stop-stage M] \
#                               [--lhotse-root /ai_sds_wuzz/DATA_ASR/LHOTSE] \
#                               [--multilingual-root /ai_sds_wuzz/MULTILINGUAL_DATA] \
#                               [--use-cleaned-talcs true] \
#                               [--perturb-speed false] \
#                               [--target-sample-rate 16000] \
#                               [--force-recompute-fbank false] \
#                               [--keep-librispeech true]
#
# 强制重算 fbank（覆盖已有）：
#   # 跳过 LibriSpeech、重算其它轻量数据集 + SR 归一化（几个小时）
#   bash prepare_from_lhotse.sh --stage 3 --stop-stage 12 \
#                               --force-recompute-fbank true
#   # 加上重数据集（KeSpeech/WenetSpeech/GigaSpeech/CV，1-2 天）
#   bash prepare_from_lhotse.sh --stage 50 --stop-stage 54 \
#                               --force-recompute-fbank true
#
# Stage 总览：
#   1   软链所有数据集的 manifests 到对应 recipe（一次性）
#   12  归一化所有 recordings 到 --target-sample-rate（默认 16000Hz；
#       仅做 lhotse lazy resample，写回 manifest，文件体积 ≈ 不变）
#   13  生成 lhotse 直读训练用的 musan_cuts.jsonl.gz（不带 fbank）
#       输出位置：<lhotse-root>/musan_cuts.jsonl.gz
#       供 train.py（--data-source lhotse）+ CutMix 噪声增强直接读
#   14  生成 MULTILINGUAL_DATA/zh 下新增普通话/方言数据集的 Lhotse manifests：
#       WenetSpeech-Chuan、WenetSpeech-Wu、magicdata_ramc
#       输出位置：<multilingual-root>/zh/{WenetSpeech-Chuan,WenetSpeech-Wu,
#                 magicdata_ramc}/data/manifests/*.jsonl.gz
#   15  生成 traffic noise robustness 评测用的 deterministic 带噪 test cuts
#       输入：<lhotse-root>/traffic_noise_cuts.jsonl.gz（zh_en 自己不 build；
#             由 amphion/yue_en/prepare_from_lhotse.sh --stage 14 共享产出，
#             或手动跑 ./build_traffic_noise_cuts.py）+
#             librispeech / wenetspeech / mdcc / talcs 的 clean test cuts
#       输出位置：<lhotse-root>/eval_traffic/{base}_{sub}_traffic_noisy_snr{N}db_cuts.jsonl.gz
#       供 test.sh -t librispeech_traffic_snr10 等 noisy 数据集名直接消费
#       （lhotse_datasets.py 已注册 20 个 dataset spec × 5 SNR）
#       默认 stop_stage 13 不跑 stage 15；需要时显式 --stage 15 --stop-stage 15
#   16  为 --shard-rotation 训练把 capped 数据集离线切片（默认不跑）
#       输入：--shard-samples 'name=cap' CSV（与 train.sh TRAIN_DATASET_SAMPLES 一致）
#       输出：<shard-dir>/<name>/<name>.NNNNNNNN.jsonl.gz
#       显式 --stage 16 --stop-stage 16 --shard-samples "..." 触发；
#       动机/收益见 docs/full_data_shard_rotation.md
#   17  规整 amphion 私有 manifest 副本（sup.duration + 扫坏音频；默认不跑）
#   ── 简单数据集 fbank（默认全跑）──
#   2   LibriSpeech                        @ librispeech/ASR
#   3   MUSAN（噪声）                      @ librispeech/ASR
#   4   AiShell-2                          @ aishell2/ASR
#   5   TAL-CSASR                          @ tal_csasr/ASR
#   6   AiShell-1                          @ aishell/ASR
#   7   MAGICDATA                          @ multi_zh-hans/ASR
#   8   primewords                         @ multi_zh-hans/ASR
#   9   THCHS-30                           @ multi_zh-hans/ASR
#   10  aidatatang                         @ aidatatang_200zh/ASR
#   11  MLS English                        @ amphion/zh_en/ASR/local（自定义）
#   ── BBPE 词表准备（默认跑） ──
#   80  librispeech lang_bpe_500（从 supervisions）
#   81  aishell2 lang_char
#   82  amphion BBPE-${vocab_size} + 软链 data
#   ── 复杂数据集 fbank（默认不跑，需显式 --stage 50+） ──
#   50  KeSpeech（split 流程，几小时）     @ multi_zh-hans/ASR
#   51  WenetSpeech（split 流程，~1 天）   @ wenetspeech/ASR
#   52  GigaSpeech（split 流程，~1 天）    @ gigaspeech/ASR
#   53  CommonVoice zh-CN                  @ commonvoice/ASR
#   54  CommonVoice en                     @ commonvoice/ASR
#
# 关于 stage 12（采样率归一化）：
#   - 14 个数据集中，CommonVoice EN/ZH 原生是 32k/48k，其余都是 16k；
#     混合采样率会让 lhotse 的 OnTheFlyFeatures / Fbank extractor 在同
#     batch 内崩溃（assertion `c.sampling_rate == cuts[0].sampling_rate`）
#     或在精算 fbank 时以错误 SR 处理音频。
#   - lhotse 的 Recording.resample 是 lazy 的，只在 load_audio 时触发，
#     manifest 中只是打了一个 transform 标记，文件体积几乎不变。
#   - 默认 --target-sample-rate=16000；传 0 则禁用此 stage（用于不需要
#     混合 SR 的子集训练）。
#
# Prerequisites（环境依赖）：
#   - 跑 stage 2-12 只需要 lhotse 自带的 CPU Fbank extractor，无额外依赖。
#   - 跑 stage 50/51/52/53/54（KeSpeech/WenetSpeech/GigaSpeech/CV-zh/en）
#     需要 GPU 加速的 KaldifeatFbank（lhotse 调 `kaldifeat` 包）。
#   - 直接 `pip install kaldifeat` 会从 PyPI 拉源码包并尝试本地编译，
#     绝大多数环境会失败。务必从官方预编译 wheel 仓库装：
#
#       # 通用引导（自己挑匹配 torch + cuda + python 的 wheel）：
#       https://csukuangfj.github.io/kaldifeat/cuda.html
#
#       # 当前环境（torch 2.5.1+cu121 / py3.10）的精确 wheel URL：
#       pip install \
#         https://huggingface.co/csukuangfj/kaldifeat/resolve/main/cuda/1.25.5.dev20241029/linux/kaldifeat-1.25.5.dev20250203+cuda12.1.torch2.5.1-cp310-cp310-manylinux_2_17_x86_64.manylinux2014_x86_64.whl
#
#   - 脚本本身在跑 stage 50+ 之前会自动 require_kaldifeat 检查，没装会
#     立刻给出上面的安装命令并退出，不会走到上游脚本里再炸。

export PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python

set -eou pipefail

# 根据脚本所在位置定位仓库根目录，使脚本可以从任何 cwd 调用。
if [ "${1:-}" != "--icefall-root" ] || [ "$#" -lt 2 ]; then
  echo "Usage: $0 --icefall-root /path/to/icefall [preparation options]" >&2
  exit 2
fi
repo_root="$(cd "$2" && pwd)"
shift 2
script_dir="$repo_root/egs/amphion/zh_en/ASR"
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
stop_stage=13        # 默认跑到 fbank 阶段 + SR 归一化 + lhotse 直读 MUSAN cuts；
                     # BBPE 另外用 --stage 80
lhotse_root="/ai_sds_wuzz/DATA_ASR/LHOTSE"
multilingual_root="/ai_sds_wuzz/MULTILINGUAL_DATA"
use_cleaned_talcs=true
perturb_speed=true   # 训练集启用 0.9/1.1 倍速扰动
vocab_size=8000      # BBPE 词表大小（透传给 amphion prepare.sh stage 4）
bbpe_lang_dir=""     # 默认 data/lang_bbpe_byte_${vocab_size}；可显式覆盖
target_sample_rate=16000  # stage 12: 把所有 recordings manifest 归一到这个 SR；
                          # 设为 0 则跳过归一化。
force_recompute_fbank=false  # 设为 true 时，stage 2..11 / 50..54 在跑之前先
                             # 清掉自己的 done 标记 + cuts + feats 目录，强制
                             # 重算 fbank。配合 --keep-librispeech 控制是否
                             # 保留已有 LibriSpeech (~31GB)。
keep_librispeech=true        # force=true 时是否保留 LibriSpeech 现有 fbank。
                             # 默认 true：LibriSpeech 本身是 16k，stage 12 对
                             # 它是 no-op，重算意义不大。
shard_samples=""             # stage 16: build_dataset_shards.py 的 'name=cap'
                             # CSV，必须与 train.sh 的 TRAIN_DATASET_SAMPLES
                             # 一致；为空则 stage 16 跳过并打印用法。
shard_dir="../../data/shards" # = egs/amphion/data/shards（amphion 共享层，跨 leaf 复用）；
                             # stage 16 输出根 / train.sh --shard-dir 同值。

. shared/parse_options.sh || exit 1

if [ -z "$bbpe_lang_dir" ]; then
  bbpe_lang_dir="data/lang_bbpe_byte_${vocab_size}"
fi

log() {
  local fname=${BASH_SOURCE[1]##*/}
  echo -e "$(date '+%Y-%m-%d %H:%M:%S') (${fname}:${BASH_LINENO[0]}:${FUNCNAME[1]}) $*"
}

libri_dir="$repo_root/egs/librispeech/ASR"
aishell_dir="$repo_root/egs/aishell/ASR"
aishell2_dir="$repo_root/egs/aishell2/ASR"
talcs_dir="$repo_root/egs/tal_csasr/ASR"
multi_hans_dir="$repo_root/egs/multi_zh-hans/ASR"
aidatatang_dir="$repo_root/egs/aidatatang_200zh/ASR"
wenetspeech_dir="$repo_root/egs/wenetspeech/ASR"
gigaspeech_dir="$repo_root/egs/gigaspeech/ASR"
commonvoice_dir="$repo_root/egs/commonvoice/ASR"

log "script_dir:              $script_dir"
log "repo_root:               $repo_root"
log "lhotse_root:             $lhotse_root"
log "multilingual_root:       $multilingual_root"
log "target_sample_rate:      $target_sample_rate (stage 12; 0 = disabled)"
log "force_recompute_fbank:   $force_recompute_fbank"
log "keep_librispeech:        $keep_librispeech (only consulted when force=true)"

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

# ---------------------------------------------------------------------------
# ensure_dl_dir_placeholder: 一些上游 recipe 的 prepare.sh 会在 fbank 阶段
# 之前先做一个无脑的 `[ ! -d $dl_dir/<Foo> ] && exit 1` 守卫，假定你已经
# 下载了原始数据。但我们从 LHOTSE manifests 直接软链过来，根本不需要原始
# 数据集的下载目录。这里建一个占位目录骗过守卫；后续 `data/manifests/
# .<foo>.done` 标记会让上游跳过 `lhotse prepare`，直接进 fbank 流程。
#
# 用法：
#   ensure_dl_dir_placeholder "$multi_hans_dir" "KeSpeech"
# ---------------------------------------------------------------------------
ensure_dl_dir_placeholder() {
  local recipe_dir="$1"
  local subdir="$2"
  local marker_dir="$recipe_dir/download/$subdir/.lhotse_only_placeholder"
  if [ ! -d "$marker_dir" ]; then
    mkdir -p "$marker_dir"
    log "  [lhotse-mode] created placeholder $marker_dir " \
        "(bypasses upstream dl_dir guard; we use LHOTSE manifests instead)"
  fi
}

# ---------------------------------------------------------------------------
# require_kaldifeat: 在 stage 50+ 进入前确认环境里装了 `kaldifeat`。
# 上游 multi_zh-hans / wenetspeech / gigaspeech / commonvoice 的
# compute_fbank_*_splits.py 都用 KaldifeatFbank 做 GPU fbank 计算；如果
# 没装会在 lhotse.features.kaldifeat:70 抛 AssertionError，错误信息只说
# "pip install kaldifeat"，但裸 `pip install kaldifeat` 会从 PyPI 拉源码
# 包并尝试本地编译，绝大多数环境失败。这里失败时直接给出针对当前 torch+
# cuda+py 的精确 wheel URL，避免用户再踩一次坑。
# ---------------------------------------------------------------------------
require_kaldifeat() {
  if python3 -c 'import kaldifeat' 2>/dev/null; then
    return 0
  fi
  log "ERROR: \`kaldifeat\` is required for stage 50+ (KeSpeech / WenetSpeech /"
  log "       GigaSpeech / CommonVoice fbank computation) but not installed."
  log ""
  log "       DO NOT run \`pip install kaldifeat\` (it will try to compile from"
  log "       source and almost always fail). Use the prebuilt wheel matching"
  log "       your torch + CUDA + python instead, e.g. for torch 2.5.1+cu121,"
  log "       python 3.10:"
  log ""
  log "         pip install \\"
  log "           https://huggingface.co/csukuangfj/kaldifeat/resolve/main/cuda/1.25.5.dev20241029/linux/kaldifeat-1.25.5.dev20250203+cuda12.1.torch2.5.1-cp310-cp310-manylinux_2_17_x86_64.manylinux2014_x86_64.whl"
  log ""
  log "       For other torch/CUDA combinations browse:"
  log "         https://csukuangfj.github.io/kaldifeat/cuda.html"
  exit 1
}

# ---------------------------------------------------------------------------
# force_clean: 仅当 --force-recompute-fbank=true 时，按显式 glob 模式删除
# 已有 fbank 残留（done 标记 + cuts + feats 目录）。否则是 no-op。
#
# 用法：
#   force_clean "<dataset_label>" "<glob1>" ["<glob2>" ...]
#
# 注意：glob 模式不要加引号，让 bash 自己展开；nullglob 防止无匹配时把
# literal 模式当文件去 rm。
# ---------------------------------------------------------------------------
force_clean() {
  if [ "$force_recompute_fbank" != "true" ]; then
    return 0
  fi
  local label="$1"; shift
  log "  [force-recompute] cleaning fbank artifacts for ${label}"
  shopt -s nullglob
  for pat in "$@"; do
    local -a matches=( $pat )
    for f in "${matches[@]}"; do
      log "    rm -rf $f"
      rm -rf -- "$f"
    done
  done
  shopt -u nullglob
}

# ===========================================================================
# Stage 1: 软链所有数据集的 manifests
# ===========================================================================
if [ $stage -le 1 ] && [ $stop_stage -ge 1 ]; then
  log "Stage 1: Symlink manifests from $lhotse_root to upstream recipes"

  # ---- LibriSpeech ----
  link_all_in_dir "$lhotse_root/LibriSpeech/data/manifests" \
                  "$libri_dir/data/manifests"
  touch "$libri_dir/data/manifests/.librispeech.done" 2>/dev/null || true

  # ---- MUSAN ----
  link_all_in_dir "$lhotse_root/MUSAN/data/manifests" \
                  "$libri_dir/data/manifests"
  touch "$libri_dir/data/manifests/.musan.done" 2>/dev/null || true

  # ---- AiShell-2 ----
  link_all_in_dir "$lhotse_root/data_aishell2/data/manifests" \
                  "$aishell2_dir/data/manifests"
  touch "$aishell2_dir/data/manifests/.aishell2_manifests.done" 2>/dev/null || true

  # ---- TALCS（命名转换）----
  declare -A talcs_part_map=( [train]=train_set [dev]=dev_set [test]=test_set )
  for src_part in train dev test; do
    dst_part=${talcs_part_map[$src_part]}
    src="$lhotse_root/TALCS/data/manifests/talcs_recordings_${src_part}.jsonl.gz"
    dst="$talcs_dir/data/manifests/tal_csasr/tal_csasr_recordings_${dst_part}.jsonl.gz"
    link_if_missing "$src" "$dst"

    if [ "$use_cleaned_talcs" = true ]; then
      src_sup="$lhotse_root/TALCS/data/manifests/talcs_supervisions_${src_part}_cleaned.jsonl.gz"
    else
      src_sup="$lhotse_root/TALCS/data/manifests/talcs_supervisions_${src_part}.jsonl.gz"
    fi
    dst_sup="$talcs_dir/data/manifests/tal_csasr/tal_csasr_supervisions_${dst_part}.jsonl.gz"
    link_if_missing "$src_sup" "$dst_sup"
  done
  touch "$talcs_dir/data/manifests/tal_csasr/.manifests.done" 2>/dev/null || true

  # ---- AiShell-1 ----
  link_all_in_dir "$lhotse_root/data_aishell/data/manifests" \
                  "$aishell_dir/data/manifests"
  touch "$aishell_dir/data/manifests/.aishell_manifests.done" 2>/dev/null || true

  # ---- MAGICDATA（multi_zh-hans/ASR/data/manifests/magicdata/） ----
  link_all_in_dir "$lhotse_root/MAGICDATA/data/manifests" \
                  "$multi_hans_dir/data/manifests/magicdata"

  # ---- primewords ----
  link_all_in_dir "$lhotse_root/primewords/data/manifests" \
                  "$multi_hans_dir/data/manifests/primewords"

  # ---- THCHS-30（multi_zh-hans/ASR/data/manifests/thchs30/） ----
  # 注意 multi_zh-hans 里的目录是 thchs30，但 prefix 是 thchs_30，
  # 两者刚好与 lhotse 的命名一致，直接链即可。
  link_all_in_dir "$lhotse_root/data_thchs30/data/manifests" \
                  "$multi_hans_dir/data/manifests/thchs30"

  # ---- aidatatang（命名转换 zhaidatatang_*_all → aidatatang_*_train） ----
  src_dir="$lhotse_root/aidatatang/data/manifests"
  dst_dir="$aidatatang_dir/data/manifests/aidatatang_200zh"
  if [ -e "$src_dir/zhaidatatang_recordings_all.jsonl.gz" ]; then
    link_if_missing "$src_dir/zhaidatatang_recordings_all.jsonl.gz" \
                    "$dst_dir/aidatatang_recordings_train.jsonl.gz"
    # supervisions 优先用 cleaned 版本
    if [ -e "$src_dir/zhaidatatang_supervisions_all_cleaned.jsonl.gz" ]; then
      link_if_missing "$src_dir/zhaidatatang_supervisions_all_cleaned.jsonl.gz" \
                      "$dst_dir/aidatatang_supervisions_train.jsonl.gz"
    else
      link_if_missing "$src_dir/zhaidatatang_supervisions_all.jsonl.gz" \
                      "$dst_dir/aidatatang_supervisions_train.jsonl.gz"
    fi
  fi
  touch "$dst_dir/.manifests.done" 2>/dev/null || true

  # ---- MLS English ----
  link_all_in_dir "$lhotse_root/MLS/data/manifests" \
                  "$script_dir/data/manifests/mls"

  # ---- KeSpeech（multi_zh-hans/ASR/data/manifests/kespeech/） ----
  link_all_in_dir "$lhotse_root/KeSpeech/data/manifests" \
                  "$multi_hans_dir/data/manifests/kespeech"
  touch "$multi_hans_dir/data/manifests/.kespeech.done" 2>/dev/null || true

  # ---- WenetSpeech（wenetspeech/ASR/data/manifests/） ----
  link_all_in_dir "$lhotse_root/WenetSpeech/data/manifests" \
                  "$wenetspeech_dir/data/manifests"

  # ---- GigaSpeech（gigaspeech/ASR/data/manifests/） ----
  link_all_in_dir "$lhotse_root/GigaSpeech/data/manifests" \
                  "$gigaspeech_dir/data/manifests"

  # ---- CommonVoice zh-CN（commonvoice/ASR/data/zh-CN/manifests/） ----
  link_all_in_dir "$lhotse_root/common_voice_zh/data/manifests" \
                  "$commonvoice_dir/data/zh-CN/manifests"

  # ---- CommonVoice en（commonvoice/ASR/data/en/manifests/） ----
  link_all_in_dir "$lhotse_root/common_voice_en/data/manifests" \
                  "$commonvoice_dir/data/en/manifests"

  log "Stage 1 done."
fi

# ===========================================================================
# Stage 2: LibriSpeech fbank
# ===========================================================================
if [ $stage -le 2 ] && [ $stop_stage -ge 2 ]; then
  log "Stage 2: Compute LibriSpeech fbank (delegating to librispeech recipe)"
  if [ "$force_recompute_fbank" = "true" ] && [ "$keep_librispeech" = "true" ]; then
    log "  [skip] --force-recompute-fbank=true but --keep-librispeech=true → " \
        "leaving existing LibriSpeech fbank intact (~31GB). " \
        "Pass --keep-librispeech false to actually wipe it."
  else
    force_clean "librispeech" \
      "$libri_dir/data/fbank/.librispeech.done" \
      "$libri_dir/data/fbank/.librispeech-validated.done" \
      "$libri_dir/data/fbank/librispeech_cuts_*.jsonl.gz" \
      "$libri_dir/data/fbank/librispeech_feats_*"
  fi
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
  # librispeech recipe writes the typo'd marker `.msuan.done` (sic!) plus
  # the more recent `.musan.done`; clean both to be safe.
  force_clean "musan" \
    "$libri_dir/data/fbank/.musan.done" \
    "$libri_dir/data/fbank/.msuan.done" \
    "$libri_dir/data/fbank/musan_cuts.jsonl.gz" \
    "$libri_dir/data/fbank/musan_feats*"
  pushd "$libri_dir" >/dev/null
  ./prepare.sh --stage 4 --stop-stage 4
  popd >/dev/null
fi

# ===========================================================================
# Stage 4: AiShell-2 fbank
# ===========================================================================
if [ $stage -le 4 ] && [ $stop_stage -ge 4 ]; then
  log "Stage 4: Compute AiShell-2 fbank"
  force_clean "aishell2" \
    "$aishell2_dir/data/fbank/.aishell2.done" \
    "$aishell2_dir/data/fbank/aishell2_cuts_*.jsonl.gz" \
    "$aishell2_dir/data/fbank/aishell2_feats_*"
  pushd "$aishell2_dir" >/dev/null
  ./prepare.sh --stage 3 --stop-stage 3
  popd >/dev/null
fi

# ===========================================================================
# Stage 5: TAL-CSASR fbank
# ===========================================================================
if [ $stage -le 5 ] && [ $stop_stage -ge 5 ]; then
  log "Stage 5: Compute TAL-CSASR fbank"
  force_clean "tal_csasr" \
    "$talcs_dir/data/fbank/.tal_csasr.done" \
    "$talcs_dir/data/fbank/tal_csasr_cuts_*.jsonl.gz" \
    "$talcs_dir/data/fbank/tal_csasr_feats_*"
  pushd "$talcs_dir" >/dev/null
  ./prepare.sh --stage 4 --stop-stage 4
  popd >/dev/null
fi

# ===========================================================================
# Stage 6: AiShell-1 fbank
# ===========================================================================
if [ $stage -le 6 ] && [ $stop_stage -ge 6 ]; then
  log "Stage 6: Compute AiShell-1 fbank"
  force_clean "aishell" \
    "$aishell_dir/data/fbank/.aishell.done" \
    "$aishell_dir/data/fbank/aishell_cuts_*.jsonl.gz" \
    "$aishell_dir/data/fbank/aishell_feats_*"
  pushd "$aishell_dir" >/dev/null
  ./prepare.sh --stage 3 --stop-stage 3
  popd >/dev/null
fi

# ===========================================================================
# Stage 7: MAGICDATA fbank
# ===========================================================================
if [ $stage -le 7 ] && [ $stop_stage -ge 7 ]; then
  log "Stage 7: Compute MAGICDATA fbank"
  force_clean "magicdata" \
    "$multi_hans_dir/data/fbank/.magicdata.done" \
    "$multi_hans_dir/data/fbank/magicdata_cuts_*.jsonl.gz" \
    "$multi_hans_dir/data/fbank/magicdata_feats_*"
  pushd "$multi_hans_dir" >/dev/null
  if [ ! -f data/fbank/.magicdata.done ]; then
    ./local/compute_fbank_magicdata.py --speed-perturb "$perturb_speed"
    touch data/fbank/.magicdata.done
  fi
  popd >/dev/null
fi

# ===========================================================================
# Stage 8: primewords fbank
# ===========================================================================
if [ $stage -le 8 ] && [ $stop_stage -ge 8 ]; then
  log "Stage 8: Compute primewords fbank"
  force_clean "primewords" \
    "$multi_hans_dir/data/fbank/.primewords.done" \
    "$multi_hans_dir/data/fbank/primewords_cuts_*.jsonl.gz" \
    "$multi_hans_dir/data/fbank/primewords_feats_*"
  pushd "$multi_hans_dir" >/dev/null
  if [ ! -f data/fbank/.primewords.done ]; then
    ./local/compute_fbank_primewords.py --speed-perturb "$perturb_speed"
    touch data/fbank/.primewords.done
  fi
  popd >/dev/null
fi

# ===========================================================================
# Stage 9: THCHS-30 fbank
# ===========================================================================
if [ $stage -le 9 ] && [ $stop_stage -ge 9 ]; then
  log "Stage 9: Compute THCHS-30 fbank"
  force_clean "thchs30" \
    "$multi_hans_dir/data/fbank/.thchs30.done" \
    "$multi_hans_dir/data/fbank/thchs_30_cuts_*.jsonl.gz" \
    "$multi_hans_dir/data/fbank/thchs_30_feats_*"
  pushd "$multi_hans_dir" >/dev/null
  if [ ! -f data/fbank/.thchs30.done ]; then
    ./local/compute_fbank_thchs30.py --speed-perturb "$perturb_speed"
    touch data/fbank/.thchs30.done
  fi
  popd >/dev/null
fi

# ===========================================================================
# Stage 10: aidatatang fbank
# ===========================================================================
if [ $stage -le 10 ] && [ $stop_stage -ge 10 ]; then
  log "Stage 10: Compute aidatatang fbank"
  force_clean "aidatatang_200zh" \
    "$aidatatang_dir/data/fbank/.aidatatang_200zh.done" \
    "$aidatatang_dir/data/fbank/aidatatang_cuts_*.jsonl.gz" \
    "$aidatatang_dir/data/fbank/aidatatang_feats_*"
  pushd "$aidatatang_dir" >/dev/null
  if [ ! -f data/fbank/.aidatatang_200zh.done ]; then
    # 用户的 LHOTSE 数据只含 'all'，已重命名为 train。
    # 这里用 python 一次性处理 train（绕过 recipe 自带的 dev/test 断言）。
    python3 - <<'PY'
from pathlib import Path
import os
from lhotse import CutSet, Fbank, FbankConfig, LilcomChunkyWriter
from lhotse.recipes.utils import read_manifests_if_cached
from icefall.utils import get_executor

src_dir = Path("data/manifests/aidatatang_200zh")
output_dir = Path("data/fbank")
output_dir.mkdir(parents=True, exist_ok=True)
num_jobs = min(15, os.cpu_count() or 1)

prefix = "aidatatang"
suffix = "jsonl.gz"
manifests = read_manifests_if_cached(
    dataset_parts=("train",),
    output_dir=src_dir,
    prefix=prefix,
    suffix=suffix,
)
extractor = Fbank(FbankConfig(num_mel_bins=80))
with get_executor() as ex:
    for partition, m in manifests.items():
        out_cuts = output_dir / f"{prefix}_cuts_{partition}.{suffix}"
        if out_cuts.is_file():
            print(f"{partition} already exists - skipping.")
            continue
        for sup in m["supervisions"]:
            sup.custom = {"origin": "aidatatang_200zh"}
        cut_set = CutSet.from_manifests(
            recordings=m["recordings"],
            supervisions=m["supervisions"],
        )
        if "train" in partition:
            cut_set = cut_set + cut_set.perturb_speed(0.9) + cut_set.perturb_speed(1.1)
        cut_set = cut_set.compute_and_store_features(
            extractor=extractor,
            storage_path=str(output_dir / f"{prefix}_feats_{partition}"),
            num_jobs=num_jobs if ex is None else 80,
            executor=ex,
            storage_type=LilcomChunkyWriter,
        )
        cut_set.to_file(out_cuts)
PY
    touch data/fbank/.aidatatang_200zh.done
  fi
  popd >/dev/null
fi

# ===========================================================================
# Stage 11: MLS English fbank
# ---------------------------------------------------------------------------
# icefall 没有 mls recipe，所以输出到本目录的 data/fbank/ 下。
# ===========================================================================
if [ $stage -le 11 ] && [ $stop_stage -ge 11 ]; then
  log "Stage 11: Compute MLS English fbank (custom script)"
  force_clean "mls" \
    "$script_dir/data/fbank/.mls.done" \
    "$script_dir/data/fbank/mls-english_cuts_*.jsonl.gz" \
    "$script_dir/data/fbank/mls-english_feats_*"
  if [ ! -f data/fbank/.mls.done ]; then
    mkdir -p data/fbank
    python3 ./compute_fbank_mls.py --speed-perturb "$perturb_speed"
    touch data/fbank/.mls.done
  fi
fi

# ===========================================================================
# Stage 12: Normalize sampling rate across all linked recordings manifests
# ---------------------------------------------------------------------------
# 起因：Lhotse 的 OnTheFlyFeatures / AudioSamples 在同一 batch 内强制要求
# `c.sampling_rate == cuts[0].sampling_rate`；CommonVoice EN/ZH 的原生 SR 是
# 32k/48k，与其它 16k 数据集混合时会触发 AssertionError。即使走预算 fbank
# 路径，Fbank extractor 也假设 16k（mel filterbank / frame_length=25ms /
# frame_shift=10ms 都跟 SR 绑定）。
#
# 这里用 lhotse 的 lazy resample（Recording.resample 只在 manifest 里加一
# 个 transform 标记；后续 load_audio 时才真正重采样）把所有 recordings
# manifest 归一到 ${target_sample_rate}。文件体积几乎不变，操作幂等：
# 已经是目标 SR 的 manifest 会直接跳过。
#
# 该 stage 只重写 *_recordings_*.jsonl.gz；supervisions / cuts / fbank
# 不动（supervisions 的 start/duration 是秒，与 SR 解耦）。
# ===========================================================================
if [ $stage -le 12 ] && [ $stop_stage -ge 12 ] && [ "$target_sample_rate" != "0" ]; then
  log "Stage 12: Normalize sampling rate to ${target_sample_rate} Hz"

  # stage 1 创建过的所有 recordings manifest 落在以下目录里。
  # 注意要包含 stage 1 中链过 *_recordings_*.jsonl.gz 的所有目录：
  norm_dirs=(
    "$libri_dir/data/manifests"
    "$aishell2_dir/data/manifests"
    "$talcs_dir/data/manifests/tal_csasr"
    "$aishell_dir/data/manifests"
    "$multi_hans_dir/data/manifests/magicdata"
    "$multi_hans_dir/data/manifests/primewords"
    "$multi_hans_dir/data/manifests/thchs30"
    "$multi_hans_dir/data/manifests/kespeech"
    "$aidatatang_dir/data/manifests/aidatatang_200zh"
    "$script_dir/data/manifests/mls"
    "$wenetspeech_dir/data/manifests"
    "$gigaspeech_dir/data/manifests"
    "$commonvoice_dir/data/zh-CN/manifests"
    "$commonvoice_dir/data/en/manifests"
  )

  TARGET_SR="$target_sample_rate" python3 - "${norm_dirs[@]}" <<'PY'
import gzip
import json
import os
import sys
from pathlib import Path

from lhotse import RecordingSet

target_sr = int(os.environ["TARGET_SR"])
dirs = [Path(p) for p in sys.argv[1:]]

# Skip irrelevant variants/labels in stage 1 leftovers.
EXCLUDE_SUBSTR = ("_supervisions_", "_cuts_")


def first_sampling_rate(path: Path) -> int | None:
    """Read just the first JSONL line to peek at sampling_rate.

    Avoids loading the entire RecordingSet just to decide whether to skip.
    """
    try:
        with gzip.open(path, "rt") as f:
            line = f.readline()
        return int(json.loads(line)["sampling_rate"])
    except Exception as e:
        print(f"  WARN: could not read first record of {path}: {e}", file=sys.stderr)
        return None


def normalize(path: Path) -> str:
    """Return a one-line status string ('skip' / 'resample N → M' / 'error ...')."""
    sr = first_sampling_rate(path)
    if sr is None:
        return "error: unreadable"
    if sr == target_sr:
        return f"skip (already {sr} Hz)"

    # Re-write in place (after breaking any symlink to avoid clobbering the
    # source under $lhotse_root). lhotse.RecordingSet.to_file dispatches on
    # the *filename suffix* (".jsonl.gz" → gzip; anything else → plain
    # JSONL), so the tmp file name MUST keep a ".jsonl.gz" suffix or the
    # written manifest will be uncompressed garbage when renamed back.
    rs = RecordingSet.from_file(path)
    rs2 = rs.resample(target_sr)
    if path.is_symlink():
        path.unlink()
    tmp = path.parent / f".tmp.{path.name}"
    rs2.to_file(tmp)
    # Sanity check: make sure tmp is actually a gzip stream before we
    # commit it over the original. Catches future regressions in this
    # suffix-dispatch dance immediately.
    with open(tmp, "rb") as f:
        magic = f.read(2)
    if magic != b"\x1f\x8b":
        tmp.unlink(missing_ok=True)
        return (
            "error: lhotse wrote non-gzip output "
            f"(first 2 bytes = {magic!r}); refused to commit."
        )
    tmp.replace(path)
    return f"resampled {len(rs)} recs ({sr} → {target_sr} Hz)"


total = changed = skipped = errors = 0
for d in dirs:
    if not d.is_dir():
        print(f"  [skip] {d} (does not exist)")
        continue
    print(f"  scanning {d}")
    for path in sorted(d.glob("*_recordings_*.jsonl.gz")):
        if any(s in path.name for s in EXCLUDE_SUBSTR):
            continue
        total += 1
        status = normalize(path)
        marker = "[ok]"
        if status.startswith("skip"):
            skipped += 1
            marker = "[==]"
        elif status.startswith("resampled"):
            changed += 1
        else:
            errors += 1
            marker = "[!!]"
        print(f"    {marker} {path.name}: {status}")

print(
    f"Stage 12 summary: scanned={total}, resampled={changed}, "
    f"already_at_target={skipped}, errors={errors}, target_sr={target_sr}"
)
if errors:
    sys.exit(1)
PY
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
# --force 强制重生成。
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
# Stage 14: MULTILINGUAL_DATA/zh 方言与会议数据 manifest
# ---------------------------------------------------------------------------
# WenetSpeech-Chuan / WenetSpeech-Wu 只有 JSONL 元数据 + tar 中的 utterance
# wav；magicdata_ramc 是长 wav + TXT 分段标注。训练走 --data-source lhotse，
# 所以这里先把三者转成可训练的 Lhotse manifests；Chuan/Wu 额外写 cuts，RAMC 由 loader 按 supervision trim。
#
# Chuan/Wu 的 recordings 使用 command source，按 tar member 的 byte offset
# 通过有限时 `dd` 直接读取，不解压 1TB 级音频，也避免每条音频执行
# `tar -xOf` 时从归档头部线性扫描。构建 manifest 需要扫 tar header，首次
# 运行会花一些时间；默认 stop_stage=13 不自动跑，按需显式触发。
# ===========================================================================
if [ $stage -le 14 ] && [ $stop_stage -ge 14 ]; then
  log "Stage 14: Build WenetSpeech-Chuan/Wu and magicdata_ramc manifests"
  python3 "$repo_root/egs/amphion/shared_amphion/build_zh_dialect_manifests.py" \
    --root "$multilingual_root/zh" \
    --datasets wenetspeech_chuan,wenetspeech_wu,magicdata_ramc
fi

# ===========================================================================
# Stage 15: 交通噪声 robustness 评测用的 deterministic 带噪 test cuts
# ---------------------------------------------------------------------------
# zh_en 训练侧目前不开 --enable-traffic-noise（与 yue_en 不同），所以本
# recipe 不 build traffic_noise_cuts.jsonl.gz 自身。traffic_noise_cuts
# 由 yue_en 那侧或手动 build_traffic_noise_cuts.py 共享产出，评测脚本仍可
# 消费写到共享 <lhotse_root> 的同名文件：
#
#   # 一次性：在 yue_en 那侧（或手动）跑 build_traffic_noise_cuts.py
#   bash ../../yue_en/ASR/prepare_from_lhotse.sh --stage 14 --stop-stage 14
#   # 等价：python3 ./build_traffic_noise_cuts.py --lhotse-root "$lhotse_root"
#
# 输入 / 输出 / 评测侧消费 / determinism 同 yue_en stage 15，详见
# build_noisy_test_cuts.py 顶部 docstring。
#
# 默认 stop_stage 13 不跑这一步；需要时显式 --stage 15 --stop-stage 15。
# 与 stage 13 同样幂等。
# ===========================================================================
if [ $stage -le 15 ] && [ $stop_stage -ge 15 ]; then
  log "Stage 15: Build deterministic noisy test cuts under \$lhotse_root/eval_traffic/"
  python3 ./build_noisy_test_cuts.py \
    --lhotse-root "$lhotse_root"
fi

# ===========================================================================
# Stage 16: 为 --shard-rotation 训练离线切分 capped 数据集
# ---------------------------------------------------------------------------
# 起因：训练默认对 capped 大集取 subset(first=cap)（manifest 物理前 cap 条），
# 多 epoch 反复见同一批、大集绝大部分从未进入训练。开启 train.sh 的
# --shard-rotation 后，multi_dataset 改为按 shard[epoch % K] 取片，多 epoch
# 确定性覆盖全量、且占比/epoch 长度/lr 不变。本 stage 产出这些 shard。
#
# 必须传 --shard-samples（与 train.sh TRAIN_DATASET_SAMPLES 一致的 'name=cap'
# CSV）；为空则跳过并打印用法。--use-punc / --target-sampling-rate 默认对齐
# train.sh（0 / 16000）；若 train.sh 改了这两项，请直接跑 build_dataset_shards.py
# 传相应值。一次性、幂等（已存在则跳过，加 build 脚本的 --force 重切）。
# 动机与效率分析详见 docs/full_data_shard_rotation.md。
# 默认 stop_stage 13 不跑；显式 --stage 16 --stop-stage 16 触发。
# ===========================================================================
if [ $stage -le 16 ] && [ $stop_stage -ge 16 ]; then
  log "Stage 16: Build per-dataset shards for --shard-rotation training"
  if [ -z "$shard_samples" ]; then
    log "  [skip] --shard-samples 为空。用法（CSV 必须与 train.sh 一致）："
    log "         bash prepare_from_lhotse.sh --stage 16 --stop-stage 16 \\"
    log "           --shard-samples \"wenetspeech=1000000,wenetspeech_chuan=200000,wenetspeech_wu=200000,magicdata_ramc=80000,...\" \\"
    log "           --shard-dir ../../data/shards"
  else
    # build_dataset_shards.py 是 amphion 私有共享脚本（softlink 到
    # shared_amphion/build_dataset_shards.py）；同 build_musan_cuts.py 不能
    # 放进 ./local/（那是 multi_zh_en 软链，写入会污染上游 recipe）。
    python3 ./build_dataset_shards.py \
      --lhotse-root "$lhotse_root" \
      --shard-dir "$shard_dir" \
      --train-dataset-samples "$shard_samples"
  fi
fi

# ===========================================================================
# Stage 17: 规整 amphion 私有 manifest 副本（sup.duration + 扫坏 .opus）
# ---------------------------------------------------------------------------
# 与 yue_en/ASR/prepare_from_lhotse.sh stage 16 共享同一 dst-root
# (\$lhotse_root/_amphion_normalized/<dataset>/) 与同一 wrapper 脚本
# (shared_amphion/local/normalize_dataset.py)。两个 recipe 都跑过后会得到
# 训练用全集数据集的并集副本；某个数据集若两 recipe 都用，--force=false
# 自然跳过已生成的。详见 yue_en stage 16 顶部注释与
# docs/training_lessons.md §1.7。
# ===========================================================================
if [ $stage -le 17 ] && [ $stop_stage -ge 17 ]; then
  log "Stage 17: Normalize manifests under \$lhotse_root/_amphion_normalized/"
  norm_datasets="${normalize_datasets:-librispeech,mls,gigaspeech,common_voice_en,aishell,aishell2,aishell3,magicdata,aidatatang,primewords,thchs30,common_voice_zh,wenetspeech,wenetspeech4tts,emilia_zh,kespeech,singaporean,singapore_english,talcs,cs_dialogue,cs_dialogue_mix}"
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
# Stage 50: KeSpeech fbank（split 流程，几小时；建议手动监控）
# ===========================================================================
if [ $stage -le 50 ] && [ $stop_stage -ge 50 ]; then
  log "Stage 50: Compute KeSpeech fbank (split pipeline, slow)"
  require_kaldifeat
  # KeSpeech writes a fan-out of done markers, raw cuts, split sub-dirs,
  # and final cuts under multi_zh-hans/ASR/data/fbank/. Wipe the lot so
  # the upstream prepare.sh stage 12 actually re-runs end to end.
  force_clean "kespeech" \
    "$multi_hans_dir/data/fbank/.kespeech.done" \
    "$multi_hans_dir/data/fbank/.kespeech_preprocess_complete" \
    "$multi_hans_dir/data/fbank/.kespeech.train_phase*.split.*.done" \
    "$multi_hans_dir/data/fbank/kespeech" \
    "$multi_hans_dir/data/fbank/kespeech_cuts_*.jsonl.gz" \
    "$multi_hans_dir/data/fbank/kespeech_feats_*"
  # Upstream multi_zh-hans/ASR/prepare.sh stage 12 has an unconditional
  # `[ ! -d $dl_dir/KeSpeech ] && exit 1` guard before checking the
  # `.kespeech.done` marker. Place a placeholder dir so the guard passes;
  # the marker (touched by stage 1 above) then makes upstream skip the
  # `lhotse prepare kespeech` call and go straight to the fbank pipeline,
  # which only consumes data/manifests/kespeech/*.jsonl.gz.
  ensure_dl_dir_placeholder "$multi_hans_dir" "KeSpeech"
  if [ ! -f "$multi_hans_dir/data/manifests/.kespeech.done" ]; then
    log "  ERROR: $multi_hans_dir/data/manifests/.kespeech.done missing. " \
        "Did you run --stage 1 first to symlink KeSpeech manifests?"
    exit 1
  fi
  pushd "$multi_hans_dir" >/dev/null
  ./prepare.sh --stage 12 --stop-stage 12
  popd >/dev/null
fi

# ===========================================================================
# Stage 51: WenetSpeech fbank（split 流程，~1 天；强烈建议多 GPU/多机）
# ===========================================================================
if [ $stage -le 51 ] && [ $stop_stage -ge 51 ]; then
  log "Stage 51: Compute WenetSpeech fbank (split pipeline, very slow)"
  require_kaldifeat
  # WenetSpeech recipe writes:
  #   data/fbank/.preprocess_complete
  #   data/fbank/cuts_{S,M,L}_raw.jsonl.gz
  #   data/fbank/{S,M,L}_split_${num_splits}/        <- split shards + per-shard cuts
  #   data/fbank/cuts_{S,M,L,DEV,TEST_NET,TEST_MEETING}.jsonl.gz
  #   data/fbank/cuts_{DEV,TEST_NET,TEST_MEETING}_raw.jsonl.gz
  #   data/fbank/feats_{S,M,L}_split_*/  (LilcomChunky)
  force_clean "wenetspeech" \
    "$wenetspeech_dir/data/fbank/.preprocess_complete" \
    "$wenetspeech_dir/data/fbank/cuts_S*.jsonl.gz" \
    "$wenetspeech_dir/data/fbank/cuts_M*.jsonl.gz" \
    "$wenetspeech_dir/data/fbank/cuts_L*.jsonl.gz" \
    "$wenetspeech_dir/data/fbank/cuts_DEV*.jsonl.gz" \
    "$wenetspeech_dir/data/fbank/cuts_TEST*.jsonl.gz" \
    "$wenetspeech_dir/data/fbank/S_split_*" \
    "$wenetspeech_dir/data/fbank/M_split_*" \
    "$wenetspeech_dir/data/fbank/L_split_*" \
    "$wenetspeech_dir/data/fbank/feats_*"
  pushd "$wenetspeech_dir" >/dev/null
  # stage 3: preprocess; 4: dev/test; 7: split L; 10: compute L; 13: combine L
  ./prepare.sh --stage 3 --stop-stage 4
  ./prepare.sh --stage 7 --stop-stage 7
  ./prepare.sh --stage 10 --stop-stage 10
  ./prepare.sh --stage 13 --stop-stage 13
  popd >/dev/null
fi

# ===========================================================================
# Stage 52: GigaSpeech fbank（split 流程，~1 天；强烈建议多 GPU/多机）
# ===========================================================================
if [ $stage -le 52 ] && [ $stop_stage -ge 52 ]; then
  log "Stage 52: Compute GigaSpeech fbank (split pipeline, very slow)"
  require_kaldifeat
  # GigaSpeech recipe writes:
  #   data/fbank/.preprocess_complete
  #   data/fbank/gigaspeech_cuts_XL_raw.jsonl.gz
  #   data/fbank/gigaspeech_XL_split/         <- split-lazy shards
  #   data/fbank/gigaspeech_cuts_XL.jsonl.gz, gigaspeech_cuts_{DEV,TEST}.jsonl.gz
  #   data/fbank/gigaspeech_feats_*/
  force_clean "gigaspeech" \
    "$gigaspeech_dir/data/fbank/.preprocess_complete" \
    "$gigaspeech_dir/data/fbank/gigaspeech_cuts_*.jsonl.gz" \
    "$gigaspeech_dir/data/fbank/gigaspeech_XL_split*" \
    "$gigaspeech_dir/data/fbank/gigaspeech_feats_*"
  pushd "$gigaspeech_dir" >/dev/null
  ./prepare.sh --stage 4 --stop-stage 6
  popd >/dev/null
fi

# ===========================================================================
# Stage 53: CommonVoice zh-CN fbank
# ---------------------------------------------------------------------------
# Note: CommonVoice recipe writes under data/<lang>/fbank/ (NOT data/fbank/)
# and uses .cv-<lang>_dev_test.done / .cv-<lang>_train.done markers, plus
# cv-<lang>_train_split_<N>/ shard directories.
# ===========================================================================
if [ $stage -le 53 ] && [ $stop_stage -ge 53 ]; then
  log "Stage 53: Compute CommonVoice zh-CN fbank"
  require_kaldifeat
  force_clean "common_voice_zh-CN" \
    "$commonvoice_dir/data/zh-CN/fbank/.cv-zh-CN_dev_test.done" \
    "$commonvoice_dir/data/zh-CN/fbank/.cv-zh-CN_train.done" \
    "$commonvoice_dir/data/zh-CN/fbank/.cv-zh-CN_validated.done" \
    "$commonvoice_dir/data/zh-CN/fbank/.cv-zh-CN_invalidated.done" \
    "$commonvoice_dir/data/zh-CN/fbank/.preprocess_complete" \
    "$commonvoice_dir/data/zh-CN/fbank/.validated.preprocess_complete" \
    "$commonvoice_dir/data/zh-CN/fbank/.invalidated.preprocess_complete" \
    "$commonvoice_dir/data/zh-CN/fbank/cv-zh-CN_cuts_*.jsonl.gz" \
    "$commonvoice_dir/data/zh-CN/fbank/cv-zh-CN_*_split_*" \
    "$commonvoice_dir/data/zh-CN/fbank/cv-zh-CN_feats_*"
  pushd "$commonvoice_dir" >/dev/null
  ./prepare.sh --stage 3 --stop-stage 6 --release "" --use-validated false --use-invalidated false || \
    log "  Note: commonvoice/prepare.sh might require --release argument; check upstream."
  popd >/dev/null
fi

# ===========================================================================
# Stage 54: CommonVoice en fbank
# ---------------------------------------------------------------------------
# Same path convention as stage 53 above.
# ===========================================================================
if [ $stage -le 54 ] && [ $stop_stage -ge 54 ]; then
  log "Stage 54: Compute CommonVoice en fbank"
  require_kaldifeat
  force_clean "common_voice_en" \
    "$commonvoice_dir/data/en/fbank/.cv-en_dev_test.done" \
    "$commonvoice_dir/data/en/fbank/.cv-en_train.done" \
    "$commonvoice_dir/data/en/fbank/.cv-en_validated.done" \
    "$commonvoice_dir/data/en/fbank/.cv-en_invalidated.done" \
    "$commonvoice_dir/data/en/fbank/.preprocess_complete" \
    "$commonvoice_dir/data/en/fbank/.validated.preprocess_complete" \
    "$commonvoice_dir/data/en/fbank/.invalidated.preprocess_complete" \
    "$commonvoice_dir/data/en/fbank/cv-en_cuts_*.jsonl.gz" \
    "$commonvoice_dir/data/en/fbank/cv-en_*_split_*" \
    "$commonvoice_dir/data/en/fbank/cv-en_feats_*"
  pushd "$commonvoice_dir" >/dev/null
  ./prepare.sh --stage 3 --stop-stage 6 --release "" --use-validated false --use-invalidated false || \
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
      # 优先从 LHOTSE 根读，回退到 librispeech recipe 的 data/manifests/
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
# Stage 81: aishell2 lang_char
#
# 直接从 LHOTSE 下的 aishell2_supervisions_train.jsonl.gz 生成 lang_char/text，
# 再用 aishell2 recipe 自带的脚本完成 text2segments / words.txt / L_disambig.pt。
# ===========================================================================
if [ $stage -le 81 ] && [ $stop_stage -ge 81 ]; then
  log "Stage 81: Build lang_char for AiShell-2 (read manifests from LHOTSE)"

  lang_char_dir="$aishell2_dir/data/lang_char"
  mkdir -p "$lang_char_dir"

  if [ ! -s "$lang_char_dir/text" ]; then
    sup="$lhotse_root/data_aishell2/data/manifests/aishell2_supervisions_train.jsonl.gz"
    if [ ! -e "$sup" ]; then
      sup="$aishell2_dir/data/manifests/aishell2_supervisions_train.jsonl.gz"
    fi
    if [ ! -e "$sup" ]; then
      log "  ERROR: aishell2_supervisions_train.jsonl.gz not found in either"
      log "         $lhotse_root/data_aishell2/data/manifests/ or $aishell2_dir/data/manifests/."
      exit 1
    fi
    log "  Reading $sup → $lang_char_dir/text (char tokenized)"

    # 等价于 aishell2/ASR/prepare.sh stage 5 的:
    #   gunzip -c <sup> | jq '.text' | sed ... | text2token.py -t char
    # 但用 python 抽 text 比 jq 更稳健（无需安装 jq）。
    pushd "$aishell2_dir" >/dev/null
    python3 - "$sup" <<'PY' | ./local/text2token.py -t "char" > "data/lang_char/text"
import gzip, json, sys
with gzip.open(sys.argv[1], "rt", encoding="utf-8") as f:
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
    popd >/dev/null

    n_lines=$(wc -l < "$lang_char_dir/text")
    log "  Done. Lines: $n_lines"
    if [ "$n_lines" -eq 0 ]; then
      log "  ERROR: lang_char/text is empty. Check supervisions content."
      exit 1
    fi
  else
    log "  $lang_char_dir/text already exists, skip extraction."
  fi

  # 剩余步骤：text2segments + words.txt + L_disambig.pt
  # 注意：aishell2/local/text2segments.py 强依赖 paddle（jieba 加速），多数
  # 环境没装；这里用 inline 纯 jieba 替代，效果一致只是稍慢（不开 paddle 时
  # 100 万行约 5-8 分钟）。
  pushd "$aishell2_dir" >/dev/null
  if [ ! -f data/lang_char/text_words_segmentation ]; then
    log "  Running jieba word segmentation (pure-jieba, no paddle; ~5-8 min for 1M lines)..."
    python3 - <<'PY'
import sys
from multiprocessing import Pool

try:
    import jieba
except ImportError:
    sys.stderr.write(
        "ERROR: jieba is required for Chinese word segmentation.\n"
        "Install it via: pip install jieba\n"
    )
    sys.exit(1)

# 关闭 jieba 的 INFO 日志，避免淹没输出
jieba.setLogLevel("ERROR")
# 预热（让子进程共享构建好的 trie）
list(jieba.cut(""))


def cut(line):
    line = line.rstrip("\n")
    if not line:
        return ""
    return " ".join(jieba.cut(line, use_paddle=False))


def main():
    with open("data/lang_char/text", "r", encoding="utf-8") as f:
        lines = f.readlines()
    print(f"  Segmenting {len(lines)} lines with jieba...", file=sys.stderr)
    with Pool(processes=8) as p:
        out = p.map(cut, lines, chunksize=2000)
    with open("data/lang_char/text_words_segmentation", "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    print(f"  Wrote data/lang_char/text_words_segmentation", file=sys.stderr)


main()
PY
  fi

  cat data/lang_char/text_words_segmentation | sed 's/ /\n/g' \
    | sort -u | sed '/^$/d' | uniq > data/lang_char/words_no_ids.txt

  if [ ! -f data/lang_char/words.txt ]; then
    python3 ./local/prepare_words.py \
      --input-file data/lang_char/words_no_ids.txt \
      --output-file data/lang_char/words.txt
  fi

  if [ ! -f data/lang_char/L_disambig.pt ]; then
    python3 ./local/prepare_char.py
  fi
  popd >/dev/null
fi

# ===========================================================================
# Stage 82: amphion BBPE-${vocab_size} + 软链 data
# ===========================================================================
if [ $stage -le 82 ] && [ $stop_stage -ge 82 ]; then
  log "Stage 82: Build BBPE-${vocab_size} and link data/ (under amphion)"
  # Only run BBPE training (amphion stage 4); skip data/ symlink (stage 5)
  # which is only needed for legacy fbank-precompute training.
  ./prepare.sh \
    --stage 4 \
    --stop-stage 4 \
    --vocab-size "$vocab_size" \
    --lang-dir "$bbpe_lang_dir"
fi

log ""
log "All requested stages done."
log ""
log "Sanity check:"
log "  ls data/fbank/ | head"
ls data/fbank/ 2>/dev/null | head -20 || true
echo
log "  ls $bbpe_lang_dir/"
ls "$bbpe_lang_dir/" 2>/dev/null || true
echo
log ""
log "Tip: Default range is --stage 1 --stop-stage 13 (basic ASR fbank + SR norm + MUSAN cuts)."
log "     To also build BBPE vocab: --stage 1 --stop-stage 82 --vocab-size 8000"
log "     To re-generate only MUSAN cuts: --stage 13 --stop-stage 13"
log "     To build zh dialect/RAMC manifests: --stage 14 --stop-stage 14"
log "     To build noisy eval test cuts (requires traffic_noise_cuts.jsonl.gz already built): --stage 15 --stop-stage 15"
log "     To build shard-rotation shards: --stage 16 --stop-stage 16 --shard-samples \"name=cap,...\""
log "     To normalize private manifest copies: --stage 17 --stop-stage 17"
log "     To compute heavy datasets: --stage 50 --stop-stage 54  (KeSpeech/WenetSpeech/GigaSpeech/CV)"
log "     To skip the SR-normalization pass: --target-sample-rate 0"
log "     To re-run only SR-normalization:   --stage 12 --stop-stage 12"
log "     To force-recompute all fbank (skipping LibriSpeech):"
log "       --stage 3 --stop-stage 12 --force-recompute-fbank true   # light datasets"
log "       --stage 50 --stop-stage 54 --force-recompute-fbank true  # heavy datasets"
log "     To also wipe LibriSpeech fbank (~31GB): add --keep-librispeech false"

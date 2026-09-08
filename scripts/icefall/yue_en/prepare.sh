#!/usr/bin/env bash
#
# 粤英流式 ASR 数据准备脚本（amphion/yue_en）
#
# 设计原则（与 amphion/zh_en/ASR/prepare.sh 思路对齐，但改用粤语数据集）：
#   - Stage 1 委派 librispeech/ASR/prepare.sh，把 musan 的 fbank 计算/链接好。
#   - Stage 2 委派 librispeech/ASR/prepare.sh，把 LibriSpeech 的 fbank 算好。
#   - Stage 3 委派 mdcc/ASR/prepare.sh，把 MDCC 的 fbank 与 lang_char 准备好。
#     （只有走 --data-source fbank 训练时才需要这部分；lhotse 直读模式可跳过。）
#   - Stage 4 训练粤英联合 BBPE 词表，vocab size 通过 --vocab-size 控制
#     （默认 8000，与 zh_en 一致）。
#   - Stage 5 把上游各 recipe 的 data/ 软链到本目录的 data/。
#   - Stage 50/51 可选追加 WenetSpeech-Yue / cumix2017 的 fbank（可选，
#     一般在 lhotse 直读模式下不需要）。
#
# 用法示例：
#   1) 仅准备 BBPE 词表（lhotse 直读训练时只需要这一步，约 20-40 分钟）：
#         bash prepare.sh --stage 4 --stop-stage 4 --vocab-size 12000
#
#   2) 完整准备 fbank + BBPE（fbank 预算训练用）：
#         bash prepare.sh --stage 1 --stop-stage 5 --vocab-size 12000
#
#   3) 改 vocab size（粤英大数据建议 8000-16000）：
#         bash prepare.sh --stage 4 --stop-stage 4 --vocab-size 8000
#
# 词表方案（最佳实践，自动启用，无开关）：
#   英文 BBPE merge + 每个 CJK 单字（mdcc 粤语 + 上游里出现过的字）作为 spm
#   user_defined_symbols 强制成原子 piece，剩余预算让 spm 自由 BPE。这点在
#   yue_en 上尤其关键：mdcc 73h vs librispeech 960h（1:13）的不平衡让旧 BBPE
#   完全没学出粤语字 piece，每个粤语字要 2-3 个 byte token；本方案直接消除
#   该退化。词表目录命名形如 data/lang_bbpe_chars_${vocab_size}，与历史
#   data/lang_bbpe_${vocab_size}（无 CJK 原子化）目录共存、互不覆盖。

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
# delegated script (local/prepare_for_bpe_model.py, local/prepare_lang_bbpe.py,
# ...).
export PYTHONPATH="$repo_root:${PYTHONPATH:-}"

stage=-1
stop_stage=100
vocab_size=12000   # 粤英大数据下推荐 8000-16000；旧 8000 词表已废弃为对比快照

. shared/parse_options.sh || exit 1

log() {
  local fname=${BASH_SOURCE[1]##*/}
  echo -e "$(date '+%Y-%m-%d %H:%M:%S') (${fname}:${BASH_LINENO[0]}:${FUNCNAME[1]}) $*"
}

log "vocab_size = $vocab_size"

mkdir -p data

libri_dir=$(realpath ../../../librispeech/ASR)
mdcc_dir=$(realpath ../../../mdcc/ASR)
lang_dir="data/lang_bbpe_chars_${vocab_size}"

# ---------------------------------------------------------------------------
# Stage 1: musan fbank（委派 librispeech recipe）
# ---------------------------------------------------------------------------
if [ $stage -le 1 ] && [ $stop_stage -ge 1 ]; then
  log "Stage 1: Compute musan fbank (delegating to librispeech/ASR/prepare.sh stage 4)"
  pushd "$libri_dir" >/dev/null
  ./prepare.sh --stage 4 --stop-stage 4
  popd >/dev/null
fi

# ---------------------------------------------------------------------------
# Stage 2: LibriSpeech fbank（委派 librispeech recipe）
# ---------------------------------------------------------------------------
if [ $stage -le 2 ] && [ $stop_stage -ge 2 ]; then
  log "Stage 2: Compute LibriSpeech fbank (delegating to librispeech/ASR/prepare.sh stage 3)"
  pushd "$libri_dir" >/dev/null
  ./prepare.sh --stage 3 --stop-stage 3
  popd >/dev/null
fi

# ---------------------------------------------------------------------------
# Stage 3: MDCC fbank + lang_char（委派 mdcc recipe）
# ---------------------------------------------------------------------------
if [ $stage -le 3 ] && [ $stop_stage -ge 3 ]; then
  log "Stage 3: Compute MDCC fbank and prepare lang_char (delegating to mdcc/ASR/prepare.sh)"
  pushd "$mdcc_dir" >/dev/null
  # stage 1: prepare manifests; stage 3: compute fbank; stage 5: prepare lang_char
  # 我们一次性把 1/3/5 都跑了；2 (musan) 和 4 (musan fbank) 已在本脚本 stage 1
  # 通过 librispeech recipe 完成。
  ./prepare.sh --stage 1 --stop-stage 1
  ./prepare.sh --stage 3 --stop-stage 3
  ./prepare.sh --stage 5 --stop-stage 5
  popd >/dev/null
fi

# ---------------------------------------------------------------------------
# Stage 4: BBPE 词表训练（vocab_size 可配置）
#
# 复刻 zh_en/ASR/prepare.sh stage 4 的步骤，但中文部分用 mdcc 的 lang_char
# （粤语繁体单字 / pycantonese 分词），英文部分用 librispeech 的 lang_bpe_500/
# transcript_words.txt。
# ---------------------------------------------------------------------------
if [ $stage -le 4 ] && [ $stop_stage -ge 4 ]; then
  log "Stage 4: Train BBPE model with vocab_size=$vocab_size → $lang_dir"
  log "  (joint Cantonese/English BBPE: combines mdcc lang_char + librispeech lang_bpe_500)"
  mkdir -p "$lang_dir"

  mdcc_lang_char="$mdcc_dir/data/lang_char"
  librispeech_lang_bpe="$libri_dir/data/lang_bpe_500"

  # 解析 lang_char 真实位置：本目录 → mdcc 两处 fallback。
  if [ -d "data/lang_char" ]; then
    src_lang_char="$(realpath data/lang_char)"
  elif [ -d "$mdcc_lang_char" ]; then
    src_lang_char="$mdcc_lang_char"
  else
    log "Abort! Could not find mdcc lang_char in any of:"
    log "  $(pwd)/data/lang_char"
    log "  $mdcc_lang_char"
    log "Please run: ./prepare_from_lhotse.sh --stage 81 --stop-stage 81"
    log "       or:  ./prepare.sh --stage 3 --stop-stage 3"
    exit 1
  fi

  # 解析 lang_bpe_500 真实位置：本目录 → librispeech 两处 fallback。
  if [ -d "data/lang_bpe_500" ]; then
    src_lang_bpe="$(realpath data/lang_bpe_500)"
  elif [ -d "$librispeech_lang_bpe" ]; then
    src_lang_bpe="$librispeech_lang_bpe"
  else
    log "Abort! Could not find librispeech lang_bpe_500 in any of:"
    log "  $(pwd)/data/lang_bpe_500"
    log "  $librispeech_lang_bpe"
    log "Please run: ./prepare_from_lhotse.sh --stage 80 --stop-stage 80"
    exit 1
  fi

  # 把找到的源目录软链到本目录 data/（如果还没有）。
  if [ ! -d "data/lang_char" ]; then
    ln -svf "$src_lang_char" "data/lang_char"
  fi
  if [ ! -d "data/lang_bpe_500" ]; then
    ln -svf "$src_lang_bpe" "data/lang_bpe_500"
  fi

  log "  Using lang_char     = $src_lang_char (粤语部分)"
  log "  Using lang_bpe_500  = $src_lang_bpe  (英语部分)"

  # ---- 训 BBPE ----
  # 粤英联合训练语料 = mdcc 粤语 char text + librispeech 英文 word transcript
  if [ ! -f "$lang_dir/text" ]; then
    cat data/lang_char/text data/lang_bpe_500/transcript_words.txt \
      > "$lang_dir/text"
  fi

  if [ ! -f "$lang_dir/transcript_chars.txt" ]; then
    ./local/prepare_for_bpe_model.py \
      --lang-dir "./$lang_dir" \
      --text "$lang_dir/text"
  fi

  # text_words_segmentation：粤语已分词 (来自 mdcc lang_char，由 pycantonese
  # 分词) + 英文 word；mdcc/ASR/prepare.sh stage 5 已经生成
  # data/lang_char/text_words_segmentation。
  if [ ! -f "$lang_dir/text_words_segmentation" ]; then
    if [ -f data/lang_char/text_words_segmentation ]; then
      log "  Reusing data/lang_char/text_words_segmentation (pycantonese-segmented)"
      cat data/lang_char/text_words_segmentation \
          data/lang_bpe_500/transcript_words.txt \
        > "$lang_dir/text_words_segmentation"
    else
      log "Abort! data/lang_char/text_words_segmentation not found."
      log "Please run: ./prepare.sh --stage 3 --stop-stage 3"
      log "       or:  ./prepare_from_lhotse.sh --stage 81 --stop-stage 81"
      exit 1
    fi
  fi

  cat "$lang_dir/text_words_segmentation" | sed 's/ /\n/g' \
    | sort -u | sed '/^$/d' | uniq > "$lang_dir/words_no_ids.txt"

  if [ ! -f "$lang_dir/words.txt" ]; then
    python3 ./local/prepare_words.py \
      --input-file "$lang_dir/words_no_ids.txt" \
      --output-file "$lang_dir/words.txt"
  fi

  if [ ! -f "$lang_dir/bbpe.model" ]; then
    # --cjk-source 把 lang_char/tokens.txt 里的每个粤语字作为 spm
    # user_defined_symbols 注入，强制每字成原子 piece。这是 yue_en 切换到
    # chars 词表的核心改动；详见 shared_amphion/local/train_bbpe_model.py
    # 的 fork 注释。
    ./local/train_bbpe_model.py \
      --lang-dir "$lang_dir" \
      --vocab-size "$vocab_size" \
      --transcript "$lang_dir/text" \
      --cjk-source "data/lang_char/tokens.txt"
  fi

  if [ ! -f "$lang_dir/L_disambig.pt" ]; then
    ./local/prepare_lang_bbpe.py --lang-dir "$lang_dir"

    log "Validating $lang_dir/lexicon.txt"
    ./local/validate_bpe_lexicon.py \
      --lexicon "$lang_dir/lexicon.txt" \
      --bpe-model "$lang_dir/bbpe.model"
  fi
fi

# ---------------------------------------------------------------------------
# Stage 5: 软链上游 fbank/lang 到本目录 data/（仅 fbank 预算训练时需要）
# ---------------------------------------------------------------------------
if [ $stage -le 5 ] && [ $stop_stage -ge 5 ]; then
  log "Stage 5: Symlink upstream data/ into local data/"

  mkdir -p data/fbank

  # ---- librispeech fbank ----
  libri_fbank="$libri_dir/data/fbank"
  if [ -e "$libri_fbank/.librispeech.done" ]; then
    cd data/fbank
    for pat in librispeech_cuts librispeech_feats musan_cuts musan_feats; do
      for f in $(ls "$libri_fbank" 2>/dev/null | grep -E "^${pat}"); do
        ln -svf "$libri_fbank/$f" .
      done
    done
    cd ../..
  else
    log "Skip librispeech fbank symlink: $libri_fbank/.librispeech.done not found."
  fi

  # ---- mdcc fbank ----
  mdcc_fbank="$mdcc_dir/data/fbank"
  if [ -e "$mdcc_fbank/.mdcc.done" ]; then
    cd data/fbank
    for f in $(ls "$mdcc_fbank" 2>/dev/null | grep -E '^mdcc_(cuts|feats)'); do
      ln -svf "$mdcc_fbank/$f" .
    done
    cd ../..
  else
    log "Skip mdcc fbank symlink: $mdcc_fbank/.mdcc.done not found."
  fi

  # ---- lang_char / lang_bpe_500 ----
  if [ -d "$mdcc_dir/data/lang_char" ] && [ ! -e "data/lang_char" ]; then
    ln -svf "$mdcc_dir/data/lang_char" "data/lang_char"
  fi
  if [ -d "$libri_dir/data/lang_bpe_500" ] && [ ! -e "data/lang_bpe_500" ]; then
    ln -svf "$libri_dir/data/lang_bpe_500" "data/lang_bpe_500"
  fi
fi

# ---------------------------------------------------------------------------
# Stage 50: 追加 WenetSpeech-Yue fbank（可选；大规模粤语，需要先准备好）
# ---------------------------------------------------------------------------
if [ $stage -le 50 ] && [ $stop_stage -ge 50 ]; then
  log "Stage 50: Symlink WenetSpeech-Yue fbank (optional; expects upstream prepared)"
  ws_yue_fbank="../../../wenetspeech_yue/ASR/data/fbank"
  if [ -d "$ws_yue_fbank" ]; then
    cd data/fbank
    for f in $(ls "../../$ws_yue_fbank" 2>/dev/null | grep -E '^wenetspeech_yue_(cuts|feats)'); do
      ln -svf "$(realpath "../../$ws_yue_fbank/$f")" .
    done
    cd ../..
  else
    log "Skip: $ws_yue_fbank not found."
  fi
fi

# ---------------------------------------------------------------------------
# Stage 51: 追加 cumix2017 fbank（可选；粤英 code-switch ~17h）
# ---------------------------------------------------------------------------
if [ $stage -le 51 ] && [ $stop_stage -ge 51 ]; then
  log "Stage 51: Symlink cumix2017 fbank (optional; expects upstream prepared)"
  cumix_fbank="../../../cumix2017/ASR/data/fbank"
  if [ -d "$cumix_fbank" ]; then
    cd data/fbank
    for f in $(ls "../../$cumix_fbank" 2>/dev/null | grep -E '^cumix2017_(cuts|feats)'); do
      ln -svf "$(realpath "../../$cumix_fbank/$f")" .
    done
    cd ../..
  else
    log "Skip: $cumix_fbank not found. (CU-MIX 2017 在 LHOTSE 直读模式下"
    log "       自然可用，无需 fbank 预算。)"
  fi
fi

log "Done. BBPE model: $lang_dir/bbpe.model"
log "  Use it with: --bpe-model $lang_dir/bbpe.model"

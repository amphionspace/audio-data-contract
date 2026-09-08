#!/usr/bin/env bash
#
# 中英流式 ASR 数据准备脚本（amphion/zh_en）
#
# 设计原则：
#   - Stage 1-3 委派 multi_zh_en/ASR/prepare.sh，把 LibriSpeech、AiShell-2、
#     TAL-CSASR、musan 的 fbank 软链到 multi_zh_en/data/fbank/。
#     （只有走 --data-source fbank 训练时才需要这部分。）
#   - Stage 4 自己完成 BBPE 词表训练，vocab size 通过 --vocab-size 控制
#     （默认 8000，比 multi_zh_en 上游硬编码的 2000 大，更适合中英大数据）。
#   - Stage 5 把上游的 data/ 软链回本目录。
#   - Stage 50/51 可选追加 WenetSpeech / GigaSpeech 的 fbank。
#
# 用法示例：
#   1) 仅准备 BBPE 词表（lhotse 直读训练时只需要这一步，约 20-40 分钟）：
#         bash prepare.sh --stage 4 --stop-stage 4 --vocab-size 12000
#
#   2) 完整准备 fbank + BBPE（fbank 预算训练用）：
#         bash prepare.sh --stage 1 --stop-stage 5 --vocab-size 12000
#
#   3) 改 vocab size（中英大数据建议 8000-16000）：
#         bash prepare.sh --stage 4 --stop-stage 4 --vocab-size 8000
#
# 词表方案（最佳实践，自动启用）：
#   英文 BBPE merge + 每个 CJK 单字（aishell2 + 上游里出现过的字）作为 spm
#   user_defined_symbols 强制成原子 piece，并保留完整 256-symbol byte alphabet，
#   剩余预算让 spm 自由 BPE。新目录命名为
#   data/lang_bbpe_byte_${vocab_size}，与两个不完整的历史 ABI
#   data/lang_bbpe_${vocab_size} / data/lang_bbpe_chars_${vocab_size} 共存。

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
# delegated script (local/prepare_for_bpe_model.py, local/text2segments.py,
# local/prepare_lang_bbpe.py, ...).
export PYTHONPATH="$repo_root:${PYTHONPATH:-}"

stage=-1
stop_stage=100
vocab_size=12000   # 新模型建议 8k-16k；现有 179M checkpoint 仍绑定 legacy 8k
lang_dir=""         # 默认在 parse_options 后设为 byte-complete 的版本化目录

. shared/parse_options.sh || exit 1

if [ -z "$lang_dir" ]; then
  lang_dir="data/lang_bbpe_byte_${vocab_size}"
fi

log() {
  local fname=${BASH_SOURCE[1]##*/}
  echo -e "$(date '+%Y-%m-%d %H:%M:%S') (${fname}:${BASH_LINENO[0]}:${FUNCNAME[1]}) $*"
}

log "vocab_size = $vocab_size"

mkdir -p data

upstream_dir=$(realpath ../../../multi_zh_en/ASR)

# ---------------------------------------------------------------------------
# Stage 1-3: fbank 软链（委派 multi_zh_en）
# ---------------------------------------------------------------------------
if [ $stage -le 3 ] && [ $stop_stage -ge 1 ]; then
  log "Stage 1-3: Delegating fbank symlinks to multi_zh_en/ASR/prepare.sh"
  log "  upstream_dir = $upstream_dir"

  upstream_stage=$((stage > 1 ? stage : 1))
  upstream_stop=$((stop_stage < 3 ? stop_stage : 3))

  pushd "$upstream_dir" >/dev/null
  ./prepare.sh --stage "$upstream_stage" --stop-stage "$upstream_stop"
  popd >/dev/null
fi

# ---------------------------------------------------------------------------
# Stage 4: BBPE 词表训练（vocab_size 可配置）
#
# 完整复刻 multi_zh_en/ASR/prepare.sh stage 4 的步骤，但 vocab size 来自
# --vocab-size 参数而非硬编码。
# ---------------------------------------------------------------------------
if [ $stage -le 4 ] && [ $stop_stage -ge 4 ]; then
  log "Stage 4: Train BBPE model with vocab_size=$vocab_size → $lang_dir"
  log "  (joint Chinese/English BBPE: combines aishell2 lang_char + librispeech lang_bpe_500)"
  mkdir -p "$lang_dir"

  aishell2_lang_char="$(realpath ../../../aishell2/ASR)/data/lang_char"
  librispeech_lang_bpe="$(realpath ../../../librispeech/ASR)/data/lang_bpe_500"

  # 解析 lang_char 真实位置：本目录 → multi_zh_en → aishell2 三处 fallback。
  if [ -d "data/lang_char" ]; then
    src_lang_char="$(realpath data/lang_char)"
  elif [ -d "$upstream_dir/data/lang_char" ]; then
    src_lang_char="$upstream_dir/data/lang_char"
  elif [ -d "$aishell2_lang_char" ]; then
    src_lang_char="$aishell2_lang_char"
  else
    log "Abort! Could not find aishell2 lang_char in any of:"
    log "  $(pwd)/data/lang_char"
    log "  $upstream_dir/data/lang_char"
    log "  $aishell2_lang_char"
    log "Please run: ./prepare_from_lhotse.sh --stage 81 --stop-stage 81"
    exit 1
  fi

  # 解析 lang_bpe_500 真实位置：本目录 → multi_zh_en → librispeech 三处 fallback。
  if [ -d "data/lang_bpe_500" ]; then
    src_lang_bpe="$(realpath data/lang_bpe_500)"
  elif [ -d "$upstream_dir/data/lang_bpe_500" ]; then
    src_lang_bpe="$upstream_dir/data/lang_bpe_500"
  elif [ -d "$librispeech_lang_bpe" ]; then
    src_lang_bpe="$librispeech_lang_bpe"
  else
    log "Abort! Could not find librispeech lang_bpe_500 in any of:"
    log "  $(pwd)/data/lang_bpe_500"
    log "  $upstream_dir/data/lang_bpe_500"
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

  log "  Using lang_char     = $src_lang_char (中文部分)"
  log "  Using lang_bpe_500  = $src_lang_bpe  (英文部分)"

  # ---- 训 BBPE ----
  # 中英联合训练语料 = aishell2 中文 char text + librispeech 英文 word transcript
  if [ ! -f "$lang_dir/text" ]; then
    cat data/lang_char/text data/lang_bpe_500/transcript_words.txt \
      > "$lang_dir/text"
  fi

  if [ ! -f "$lang_dir/transcript_chars.txt" ]; then
    ./local/prepare_for_bpe_model.py \
      --lang-dir "./$lang_dir" \
      --text "$lang_dir/text"
  fi

  # text_words_segmentation：中文已分词 (来自 aishell2 lang_char) + 英文 word
  # NOTE: 优先复用 data/lang_char/text_words_segmentation（由 prepare_from_lhotse.sh
  # stage 81 用纯 jieba 生成，无需 paddle）；如果不存在则 fall back 到
  # text2segments.py（依赖 paddle）。
  if [ ! -f "$lang_dir/text_words_segmentation" ]; then
    if [ -f data/lang_char/text_words_segmentation ]; then
      log "  Reusing data/lang_char/text_words_segmentation (jieba-segmented)"
      cat data/lang_char/text_words_segmentation \
          data/lang_bpe_500/transcript_words.txt \
        > "$lang_dir/text_words_segmentation"
    else
      log "  data/lang_char/text_words_segmentation not found, falling back to text2segments.py"
      log "  (this requires paddle; if it fails, run: ./prepare_from_lhotse.sh --stage 81 --stop-stage 81)"
      python3 ./local/text2segments.py \
        --input-file ./data/lang_char/text \
        --output-file "$lang_dir/text_words_segmentation"
      cat ./data/lang_bpe_500/transcript_words.txt \
        >> "$lang_dir/text_words_segmentation"
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
    # --cjk-source 把 lang_char/tokens.txt 里的每个汉字作为 spm
    # user_defined_symbols 注入，强制每字成原子 piece；剩余预算让 spm 学英文
    # BPE merge（顺带可能学到中文多字 piece）。详见 shared_amphion/local/
    # train_bbpe_model.py 的 fork 注释。
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
# Stage 5: 把上游 data/ 软链回本目录（仅 fbank 预算训练时需要）
# ---------------------------------------------------------------------------
if [ $stage -le 5 ] && [ $stop_stage -ge 5 ]; then
  log "Stage 5: Symlink upstream data/ into local data/"
  if [ ! -d "$upstream_dir/data" ]; then
    log "Abort! $upstream_dir/data not found. Please run upstream stages first."
    exit 1
  fi

  for sub in fbank lang_char lang_bpe_500; do
    if [ -d "$upstream_dir/data/$sub" ] && [ ! -e "data/$sub" ]; then
      ln -svf "$upstream_dir/data/$sub" "data/$sub"
    fi
  done
fi

# ---------------------------------------------------------------------------
# Stage 50: 追加 WenetSpeech fbank（可选；约 10000h 中文）
# ---------------------------------------------------------------------------
if [ $stage -le 50 ] && [ $stop_stage -ge 50 ]; then
  log "Stage 50: Symlink WenetSpeech fbank (optional, requires upstream)"
  ws_fbank="../../../wenetspeech/ASR/data/fbank"
  if [ -e "$ws_fbank/.preprocess_complete" ]; then
    cd data/fbank
    for f in cuts_DEV_fixed.jsonl.gz cuts_L_fixed.jsonl.gz \
             cuts_TEST_MEETING.jsonl.gz cuts_TEST_NET.jsonl.gz; do
      if [ -e "../../$ws_fbank/$f" ]; then
        ln -svf "$(realpath "../../$ws_fbank/$f")" .
      fi
    done
    if [ -d "../../$ws_fbank/L_split_1000" ]; then
      ln -svf "$(realpath "../../$ws_fbank/L_split_1000")" .
    fi
    cd ../..
  else
    log "Skip: ../../../wenetspeech/ASR/data/fbank/.preprocess_complete not found."
  fi
fi

# ---------------------------------------------------------------------------
# Stage 51: 追加 GigaSpeech fbank（可选；约 10000h 英文）
# ---------------------------------------------------------------------------
if [ $stage -le 51 ] && [ $stop_stage -ge 51 ]; then
  log "Stage 51: Symlink GigaSpeech fbank (optional, requires upstream)"
  gs_fbank="../../../gigaspeech/ASR/data/fbank"
  if [ -d "$gs_fbank" ]; then
    cd data/fbank
    for f in $(ls "../../$gs_fbank" 2>/dev/null | grep -E '^(gigaspeech_cuts|gigaspeech_feats)'); do
      ln -svf "$(realpath "../../$gs_fbank/$f")" .
    done
    cd ../..
  else
    log "Skip: $gs_fbank not found."
  fi
fi

log "Done. BBPE model: $lang_dir/bbpe.model"
log "  Use it with: --bpe-model $lang_dir/bbpe.model"

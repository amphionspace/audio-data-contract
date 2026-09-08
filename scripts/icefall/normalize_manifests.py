#!/usr/bin/env python3
"""Normalize a (recordings, supervisions) manifest pair for amphion training.

What it does (per supervision):
  1. ``supervision.duration = recording.duration - supervision.start``
     -- extends every supervision to cover the entire recording. Removes the
     manifest-layer source of the subsampling ``x.size(1) == x_lens.max()``
     mismatch documented in docs/training_lessons.md §1.7 (legco-speech
     chunks where ``sup.duration`` was set strictly less than the recording
     duration). The CutMix padding source of the same mismatch is unfixable
     at manifest layer (MixedCut padding is a dataloader-runtime artifact)
     and is handled by the runtime patch in
     ``_SkipEmptyBatchK2Dataset.__getitem__``.

  2. Drop supervisions whose recording fails to load (``--scan-audio``).
     For ``.opus`` datasets this consumes a real broken-rate of ~1e-6 that
     ``_OpusFallbackBackend`` (libsndfile→ffmpeg) is otherwise relying on
     ``fault_tolerant=True`` to skip at training time. Once dropped from
     the manifest the runtime ``fault_tolerant`` becomes a defensive
     no-op (it can still catch *new* corruption introduced after the
     last normalize run, but normal-case batches never trigger it).

Recordings are NOT mutated -- this script only rewrites supervisions and
optionally a sidecar ``broken.txt`` listing dropped supervision IDs.
amphion's ``MultiDataset`` reassembles cuts from
``CutSet.from_manifests(recordings, supervisions)`` so a dangling
recording (no sup referencing it) is harmless.

Output
------
``<dst-sup>``           normalised supervisions jsonl.gz
``<dst-sup>.stats.json`` counters (read / fixed / dropped / scanned)
``<dst-sup>.broken.txt``  one ``<sup_id>\t<reason>`` per dropped sup
``<dst-sup>.checkpoint``  last fully-flushed offset (for ``--resume``)

Concurrency
-----------
``--scan-audio`` parallelises load_audio across ``--num-workers``
processes via ``multiprocessing.Pool`` (fork-based on Linux so the
recording dict is shared via COW with no pickling overhead).

Resume semantics
----------------
``--resume`` reads ``<dst-sup>.checkpoint`` and skips supervisions whose
line index is below the recorded offset. The script flushes the
checkpoint atomically every ``--checkpoint-every`` supervisions; a
mid-flush kill loses at most that many records of progress.
"""

from __future__ import annotations

import argparse
import gzip
import json
import logging
import multiprocessing as mp
import os
import sys
import time
from pathlib import Path

logger = logging.getLogger(__name__)


_REC_DICT: dict[str, dict] | None = None  # populated in _scan_init_worker


def _open_jsonl_for_read(path: Path):
    """Open .jsonl(.gz) for streaming text read."""
    if str(path).endswith(".gz"):
        return gzip.open(str(path), "rt", encoding="utf-8")
    return open(str(path), "rt", encoding="utf-8")


def _open_jsonl_for_write(path: Path, append: bool):
    """Open .jsonl(.gz) for streaming text write (append or new)."""
    mode = "at" if append else "wt"
    if str(path).endswith(".gz"):
        return gzip.open(str(path), mode, encoding="utf-8")
    return open(str(path), mode, encoding="utf-8")


def _load_rec_dict(src_rec: Path) -> dict[str, dict]:
    """Return ``{recording_id: full recording dict}`` from a jsonl(.gz)."""
    logger.info("loading recordings from %s ...", src_rec)
    t0 = time.time()
    out: dict[str, dict] = {}
    with _open_jsonl_for_read(src_rec) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            out[obj["id"]] = obj
    logger.info(
        "  loaded %d recordings in %.1fs (avg %.0f bytes/rec)",
        len(out),
        time.time() - t0,
        # rough estimate of memory; only useful for ops to gauge --num-workers
        os.path.getsize(src_rec) * 8 // max(1, len(out)),
    )
    return out


def _scan_init_worker(rec_dict: dict[str, dict]) -> None:
    """Pool initializer: stash the rec dict in module globals.

    On Linux ``multiprocessing.Pool`` uses ``fork`` by default; the
    initializer's argument is a *reference* to the parent's rec_dict (COW
    memory), not a pickled copy, so this is essentially free.
    """
    global _REC_DICT
    _REC_DICT = rec_dict


def _scan_one(sup_dict: dict) -> tuple[str, bool, str]:
    """Worker: construct a minimal cut and try ``load_audio`` on it.

    Returns (sup_id, ok, error_msg_or_empty).
    """
    sup_id = sup_dict.get("id", "?")
    try:
        rec_id = sup_dict["recording_id"]
        rec_dict = _REC_DICT.get(rec_id) if _REC_DICT is not None else None
        if rec_dict is None:
            return sup_id, False, f"recording_id {rec_id!r} not in source rec set"

        from lhotse import Recording, SupervisionSegment

        rec = Recording.from_dict(rec_dict)
        sup = SupervisionSegment.from_dict(sup_dict)
        cut = rec.to_cut()
        cut.supervisions = [sup]
        cut.load_audio()
        return sup_id, True, ""
    except Exception as e:  # Audio backends expose different exception classes
        logger.debug("Audio scan failed", exc_info=True)
        return sup_id, False, f"{type(e).__name__}: {str(e)[:160]}"


def _write_checkpoint_atomic(path: Path, offset: int) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(str(offset))
    tmp.replace(path)


def _read_checkpoint(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        return int(path.read_text().strip())
    except (OSError, ValueError):
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--src-rec", type=Path, required=True, help="source recordings jsonl(.gz)"
    )
    parser.add_argument(
        "--src-sup", type=Path, required=True, help="source supervisions jsonl(.gz)"
    )
    parser.add_argument(
        "--dst-sup",
        type=Path,
        required=True,
        help="destination normalised supervisions jsonl.gz",
    )
    parser.add_argument(
        "--scan-audio",
        action="store_true",
        help="also drop supervisions whose recording fails to "
        "load (parallelised via --num-workers).",
    )
    parser.add_argument(
        "--num-workers",
        type=int,
        default=64,
        help="workers for --scan-audio (default 64).",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=256,
        help="supervisions per parallel task (default 256).",
    )
    parser.add_argument(
        "--checkpoint-every",
        type=int,
        default=10000,
        help="flush progress checkpoint every N sups (default 10000).",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="skip sups whose line index is below the recorded "
        "checkpoint; appends to existing dst files.",
    )
    parser.add_argument(
        "--log-every",
        type=int,
        default=10000,
        help="emit a progress log every N sups (default 10000).",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    args.dst_sup.parent.mkdir(parents=True, exist_ok=True)
    stats_path = args.dst_sup.with_suffix(args.dst_sup.suffix + ".stats.json")
    broken_path = args.dst_sup.with_suffix(args.dst_sup.suffix + ".broken.txt")
    ckpt_path = args.dst_sup.with_suffix(args.dst_sup.suffix + ".checkpoint")

    start_offset = _read_checkpoint(ckpt_path) if args.resume else 0
    if start_offset > 0:
        logger.info("resuming from sup offset %d (per %s)", start_offset, ckpt_path)
        if not args.dst_sup.exists():
            logger.error(
                "--resume specified but %s does not exist; aborting", args.dst_sup
            )
            return 2

    rec_dict = _load_rec_dict(args.src_rec)

    stats: dict[str, int] = {
        "n_sup_read": 0,
        "n_sup_written": 0,
        "n_sup_fixed_duration": 0,
        "n_sup_dropped_no_recording": 0,
        "n_sup_dropped_negative_target": 0,
        "n_sup_dropped_scan_audio": 0,
        "n_sup_skipped_resume": 0,
        "start_offset": start_offset,
    }

    # ---------- Pass 1: normalize sup.duration, write dst (filter broken refs) ----------
    # If --scan-audio: we'll do a second pass that reads dst back and drops
    # broken cuts. Splitting in two passes keeps the write loop simple and
    # makes resume semantics straightforward.

    pending_for_scan: list[dict] = []
    t0 = time.time()
    with (
        _open_jsonl_for_write(args.dst_sup, append=args.resume) as sup_writer,
        open(
            broken_path, "a" if args.resume else "w", encoding="utf-8"
        ) as broken_writer,
    ):
        for idx, line in enumerate(_open_jsonl_for_read(args.src_sup)):
            line = line.strip()
            if not line:
                continue
            stats["n_sup_read"] += 1
            if idx < start_offset:
                stats["n_sup_skipped_resume"] += 1
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                broken_writer.write(f"?\tparse: {type(e).__name__}: {e}\n")
                continue

            rec_id = obj.get("recording_id")
            rec = rec_dict.get(rec_id)
            if rec is None:
                stats["n_sup_dropped_no_recording"] += 1
                broken_writer.write(f"{obj.get('id', '?')}\tno-recording: {rec_id!r}\n")
                continue

            rec_dur = float(rec["duration"])
            sup_start = float(obj.get("start", 0.0))
            target_dur = rec_dur - sup_start
            if target_dur <= 0:
                stats["n_sup_dropped_negative_target"] += 1
                broken_writer.write(
                    f"{obj.get('id', '?')}\tnegative-target: "
                    f"rec.duration={rec_dur} - sup.start={sup_start} = {target_dur}\n"
                )
                continue

            old_dur = float(obj.get("duration", -1.0))
            if abs(old_dur - target_dur) > 1e-6:
                obj["duration"] = target_dur
                stats["n_sup_fixed_duration"] += 1

            if args.scan_audio:
                # Buffer for parallel scan; written to dst only if scan passes.
                pending_for_scan.append(obj)
                # Flush in chunks to bound memory.
                if len(pending_for_scan) >= args.chunk_size * args.num_workers * 4:
                    _flush_scan(
                        pending_for_scan,
                        rec_dict,
                        sup_writer,
                        broken_writer,
                        stats,
                        args,
                    )
                    pending_for_scan.clear()
            else:
                sup_writer.write(json.dumps(obj, ensure_ascii=False) + "\n")
                stats["n_sup_written"] += 1

            if stats["n_sup_read"] % args.log_every == 0:
                logger.info(
                    "  pass1: read=%d written=%d fixed_dur=%d "
                    "dropped_no_rec=%d dropped_scan=%d (%.1f sup/s)",
                    stats["n_sup_read"],
                    stats["n_sup_written"],
                    stats["n_sup_fixed_duration"],
                    stats["n_sup_dropped_no_recording"],
                    stats["n_sup_dropped_scan_audio"],
                    stats["n_sup_read"] / max(1e-9, time.time() - t0),
                )

            if stats["n_sup_read"] % args.checkpoint_every == 0:
                # Empty pending so the checkpoint reflects fully-written sups.
                if pending_for_scan:
                    _flush_scan(
                        pending_for_scan,
                        rec_dict,
                        sup_writer,
                        broken_writer,
                        stats,
                        args,
                    )
                    pending_for_scan.clear()
                sup_writer.flush()
                broken_writer.flush()
                _write_checkpoint_atomic(ckpt_path, idx + 1)

        # Drain final buffer.
        if pending_for_scan:
            _flush_scan(
                pending_for_scan,
                rec_dict,
                sup_writer,
                broken_writer,
                stats,
                args,
            )
            pending_for_scan.clear()

        sup_writer.flush()
        broken_writer.flush()
        _write_checkpoint_atomic(ckpt_path, stats["n_sup_read"])

    # ---------- Wrap up ----------
    stats["elapsed_sec"] = time.time() - t0
    stats_path.write_text(json.dumps(stats, indent=2, ensure_ascii=False))
    logger.info(
        "DONE: read=%d, written=%d, fixed_dur=%d, dropped_no_rec=%d, "
        "dropped_negative=%d, dropped_scan=%d, elapsed=%.0fs",
        stats["n_sup_read"],
        stats["n_sup_written"],
        stats["n_sup_fixed_duration"],
        stats["n_sup_dropped_no_recording"],
        stats["n_sup_dropped_negative_target"],
        stats["n_sup_dropped_scan_audio"],
        stats["elapsed_sec"],
    )
    logger.info("stats:  %s", stats_path)
    logger.info("broken: %s", broken_path)
    logger.info("output: %s", args.dst_sup)
    return 0


def _flush_scan(
    pending: list[dict],
    rec_dict: dict[str, dict],
    sup_writer,
    broken_writer,
    stats: dict[str, int],
    args,
) -> None:
    """Run parallel ``load_audio`` over ``pending``; write surviving sups."""
    n_in = len(pending)
    if n_in == 0:
        return
    t0 = time.time()
    with mp.Pool(
        processes=args.num_workers,
        initializer=_scan_init_worker,
        initargs=(rec_dict,),
    ) as pool:
        # Pool.imap_unordered preserves no ordering but maximises throughput.
        # We rebuild the surviving set by looking up sup_id back to the
        # pending dicts after the scan completes; ordering of dst doesn't
        # matter for amphion training.
        results = pool.imap_unordered(_scan_one, pending, chunksize=args.chunk_size)
        id_to_status: dict[str, tuple[bool, str]] = {}
        for sup_id, ok, err in results:
            id_to_status[sup_id] = (ok, err)

    for obj in pending:
        sup_id = obj.get("id", "?")
        ok, err = id_to_status.get(sup_id, (False, "scan: no result returned"))
        if ok:
            sup_writer.write(json.dumps(obj, ensure_ascii=False) + "\n")
            stats["n_sup_written"] += 1
        else:
            stats["n_sup_dropped_scan_audio"] += 1
            broken_writer.write(f"{sup_id}\tscan: {err}\n")

    n_ok = sum(1 for s in id_to_status.values() if s[0])
    n_bad = n_in - n_ok
    logger.info(
        "  scan chunk: %d sups in %.1fs (%.0f sup/s); ok=%d bad=%d",
        n_in,
        time.time() - t0,
        n_in / max(1e-9, time.time() - t0),
        n_ok,
        n_bad,
    )


if __name__ == "__main__":
    sys.exit(main())

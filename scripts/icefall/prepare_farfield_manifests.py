#!/usr/bin/env python3
"""Prepare ASR manifests from downloaded meeting and far-field corpora.

Keep official splits and original audio/annotations. The upstream Lhotse
manifests remain alongside the ASR manifests for provenance.
"""

import argparse
import json
from dataclasses import replace
from pathlib import Path

from lhotse import Recording, RecordingSet, SupervisionSet, load_manifest
from lhotse.qa import validate_recordings_and_supervisions


def save_split(output, name, split, recordings, supervisions, language):
    normalized = []
    empty = 0
    for supervision in supervisions:
        text = supervision.text or ""
        if name == "notsofar_sdm":
            # Official word timing excludes non-speech XML tags, but retains
            # spoken fillers (uh, um, etc.) and words inside name tags.
            text = " ".join(
                word.symbol for word in (supervision.alignment or {}).get("word", [])
            )
        text = text.strip()
        if not text:
            empty += 1
            continue
        normalized.append(replace(supervision, text=text, language=language))
    supervisions = SupervisionSet.from_segments(normalized)
    used = {s.recording_id for s in supervisions}
    recordings = RecordingSet.from_recordings(r for r in recordings if r.id in used)
    validate_recordings_and_supervisions(recordings, supervisions)
    output.mkdir(parents=True, exist_ok=True)
    rec_path = output / f"{name}_recordings_{split}.jsonl.gz"
    sup_path = output / f"{name}_supervisions_{split}.jsonl.gz"
    # Readers must not observe a half-written gzip manifest during preparation.
    for path, manifest in ((rec_path, recordings), (sup_path, supervisions)):
        temporary = path.with_name("." + path.name)
        manifest.to_file(temporary)
        temporary.replace(path)
    return {
        "recordings": len(recordings),
        "supervisions": len(supervisions),
        "recording_hours": sum(r.duration for r in recordings) / 3600,
        "supervision_hours": sum(s.duration for s in supervisions) / 3600,
        "empty_text_excluded": empty,
        "recordings_path": str(rec_path),
        "supervisions_path": str(sup_path),
    }


def repair_ami_stereo(root, output, manifests):
    """Recover the known stereo SDM file that upstream AMI preparation skips."""
    import soundfile as sf
    from lhotse.recipes.ami import (
        PARTITIONS,
        parse_ami_annotations,
        prepare_supervision_other,
    )

    session = "ES2010d"
    if any(session in v["recordings"] for v in manifests.values()):
        return
    source = root / "ami_full/sdm" / session / "audio" / f"{session}.Array1-01.wav"
    if not source.exists():
        raise FileNotFoundError(source)
    target = output.parent / "mono" / source.name
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        temporary = target.with_name("." + target.name)
        with (
            sf.SoundFile(source) as src,
            sf.SoundFile(
                temporary, "w", samplerate=src.samplerate, channels=1, subtype="PCM_16"
            ) as dst,
        ):
            for block in src.blocks(blocksize=160000, always_2d=True):
                dst.write(block[:, 0])
        temporary.replace(target)
    recs = RecordingSet.from_recordings(
        [Recording.from_file(target, recording_id=session)]
    )
    annotations = parse_ami_annotations(
        root / "ami_full/ami_public_manual_1.6.2",
        normalize="kaldi",
        max_words_per_segment=30,
        keep_punctuation=False,
    )
    sups = prepare_supervision_other(recs, annotations)
    validate_recordings_and_supervisions(recs, sups)
    part = next(k for k, ids in PARTITIONS["full-corpus-asr"].items() if session in ids)
    manifests[part]["recordings"] += recs
    manifests[part]["supervisions"] += sups


def prepare_meeting(name, root, lhotse_root):
    directory = {
        "alimeeting_sdm": "AliMeeting",
        "ami_sdm": "AMI",
        "notsofar_sdm": "NOTSOFAR",
    }[name]
    output = lhotse_root / directory / "data/manifests"
    if name == "alimeeting_sdm":
        from lhotse.recipes.ali_meeting import prepare_ali_meeting

        raw = {
            part: f"alimeeting-sdm_{{kind}}_{part}.jsonl.gz"
            for part in ("train", "eval", "test")
        }
        if not all(
            (output / pattern.format(kind=kind)).exists()
            for pattern in raw.values()
            for kind in ("recordings", "supervisions")
        ):
            prepare_ali_meeting(
                root / "AliMeeting", output, mic="sdm", normalize_text="m2met"
            )
    elif name == "ami_sdm":
        from lhotse.recipes.ami import prepare_ami

        raw = {
            part: f"ami-sdm_{{kind}}_{part}.jsonl.gz"
            for part in ("train", "dev", "test")
        }
        if not all(
            (output / pattern.format(kind=kind)).exists()
            for pattern in raw.values()
            for kind in ("recordings", "supervisions")
        ):
            prepare_ami(
                root / "ami_full/sdm",
                annotations_dir=root / "ami_full/ami_public_manual_1.6.2",
                output_dir=output,
                mic="sdm",
                partition="full-corpus-asr",
                normalize_text="kaldi",
                max_words_per_segment=30,
            )
    else:
        from lhotse.recipes.notsofar1 import prepare_notsofar1

        raw = {
            "train": "notsofar1_sdm_train_set_240825.1_train_{kind}.jsonl.gz",
            "dev": "notsofar1_sdm_dev_set_240825.1_dev1_{kind}.jsonl.gz",
            "test": "notsofar1_sdm_eval_set_240825.1_eval_full_with_GT_{kind}.jsonl.gz",
        }
        if not all(
            (output / pattern.format(kind=kind)).exists()
            for pattern in raw.values()
            for kind in ("recordings", "supervisions")
        ):
            prepare_notsofar1(root / "NOTSOFAR/hf-ba8fd0f034ce", output)
    manifests = {
        part: {
            kind: load_manifest(output / pattern.format(kind=kind))
            for kind in ("recordings", "supervisions")
        }
        for part, pattern in raw.items()
    }
    if name == "ami_sdm":
        repair_ami_stereo(root, output, manifests)
    ids = {}
    report = {}
    for part, values in manifests.items():
        split = "dev" if part == "eval" else part
        # NOTSOFAR records a meeting through multiple devices. Split checks
        # operate on meetings, not on individual device recordings.
        ids[split] = {
            "_".join(r.id.split("_")[:2]) if name == "notsofar_sdm" else r.id
            for r in values["recordings"]
        }
        report[split] = save_split(
            output,
            name,
            split,
            values["recordings"],
            values["supervisions"],
            "Chinese" if name == "alimeeting_sdm" else "English",
        )
    for left, right in (("train", "dev"), ("train", "test"), ("dev", "test")):
        overlap = ids[left] & ids[right]
        if overlap:
            raise ValueError(
                f"{name}: meetings shared by {left}/{right}: {sorted(overlap)}"
            )
    report["meeting_split_overlap"] = 0
    (output / f"{name}_summary.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def prepare_realman(root, lhotse_root):
    import re

    from lhotse import SupervisionSegment

    corpus = root / "RealMAN"
    complete = corpus / "asr_mono/.complete.json"
    if not complete.exists():
        raise RuntimeError(
            "RealMAN download/extraction is not complete; run download_realman_asr.py first"
        )
    transcripts = {}
    for line in (corpus / "transcriptions.trn").read_text().splitlines():
        match = re.fullmatch(r"(.*?)\s*\(([^()]+)\)\s*", line)
        if match:
            text = " ".join(match[1].split())
            transcripts[match[2]] = re.sub(
                r"(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff])", "", text
            )
    if not transcripts:
        raise ValueError("No RealMAN transcripts parsed")
    output = lhotse_root / "RealMAN/data/manifests"
    report = {}
    for source_split, split in (("train", "train"), ("val", "dev"), ("test", "test")):
        paths = sorted((corpus / "asr_mono" / source_split).rglob("*_CH0.flac"))
        if not paths:
            raise ValueError(f"No extracted RealMAN channel-0 audio for {source_split}")
        recs, sups = [], []
        for path in paths:
            # Numeric and P-prefixed speakers both use S{speaker}-{utterance}
            # in transcriptions.trn (e.g. S0010-0003, SP0002-P0002W0001).
            fields = path.stem.split("_")
            key = f"S{fields[-3]}-{fields[-2]}"
            text = transcripts[key]
            rec = Recording.from_file(path, recording_id="realman-" + path.stem)
            recs.append(rec)
            sups.append(
                SupervisionSegment(
                    id=rec.id,
                    recording_id=rec.id,
                    start=0,
                    duration=rec.duration,
                    channel=0,
                    text=text,
                    language="Chinese",
                    speaker="realman-" + fields[-3],
                    custom={
                        "source_split": source_split,
                        "scene": fields[2],
                        "motion": fields[1],
                    },
                )
            )
        report[split] = save_split(
            output,
            "realman",
            split,
            RecordingSet.from_recordings(recs),
            SupervisionSet.from_segments(sups),
            "Chinese",
        )
    (output / "realman_summary.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-d",
        "--dataset",
        required=True,
        choices=("alimeeting_sdm", "ami_sdm", "notsofar_sdm", "realman"),
    )
    parser.add_argument(
        "-r", "--root", type=Path, default=Path("/ai_sds_wuzz/DATA_ASR")
    )
    parser.add_argument(
        "-l", "--lhotse-root", type=Path, default=Path("/ai_sds_wuzz/DATA_ASR/LHOTSE")
    )
    args = parser.parse_args()
    report = (
        prepare_realman(args.root, args.lhotse_root)
        if args.dataset == "realman"
        else prepare_meeting(args.dataset, args.root, args.lhotse_root)
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

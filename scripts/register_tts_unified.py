"""Write catalog/tts_unified.yaml from published DATA-TTS-UNIFIED release manifests.

Only complete v0.1 releases are declared; datasets still under v0.1.incomplete
are skipped. ASR notes come from the 2026-10-09 text survey
(reports/tts-unified-asr-20261009/README.md).

    python scripts/register_tts_unified.py /workspace/data
"""

import hashlib
import json
import sys
from pathlib import Path

from ruamel.yaml import YAML

VERSION = "tts-unified-v0.1"
RELEASE = "v0.1"
UNIFIED = "DATA-TTS-UNIFIED/datasets"
SOURCE_DIRS = {
    "aishell3": "AISHELL-3",
    "csemotions": "CSEMOTIONS",
    "emilia": "Emilia",
    "emilia2": "Emilia2",
    "emilia_yodas": "Emilia-YODAS",
    "galgame": "Galgame-VisualNovel-Reupload",
    "genshin_voice": "genshin-voice",
    "hifitts": "HiFiTTS",
    "hifitts2": "HiFiTTS2",
    "libriheavy": "libriheavy",
    "libritts_r": "LibriTTS-R",
    "ljspeech": "LJSpeech",
    "mls_sidon": "mls_sidon",
    "starrail_voice": "starrail-voice",
    "vctk": "VCTK",
    "wenetspeech4tts": "WenetSpeech4TTS",
    "wutheringwaves": "WutheringWaves-2.2",
}
# Datasets usable for ASR after the cleaning listed in the survey report.
ASR = {
    "aishell3": "人工转写；须排除 original_split=test（与 AISHELL-3 测试集相同）",
    "hifitts": "有声书原文；须排除 original_split=dev/test",
    "hifitts2": "有声书原文；须排除 dev_*/test_* 划分",
    "libriheavy": "书本原文（带大小写和标点），text_variants 另有 source_asr；超过 30 秒的约 44 万条需切分或过滤",
    "libritts_r": "须排除 dev/test（来自 LibriSpeech dev/test，会污染 LibriSpeech 评测）；音频经修复增强",
    "ljspeech": "单说话人朗读，数字未展开",
    "mls_sidon": "须排除 valid/test（与 MLS 评测集相同）；音频经 Sidon 修复",
    "vctk": "朗读文本；172 条无文本",
    "wenetspeech4tts": "来自 WenetSpeech 的弱标注，建议做置信度或双模型一致性过滤",
    "emilia": "机器转写，须做质量过滤；文本开头带空格",
    "emilia_yodas": "机器转写，须做质量过滤；文本开头带空格",
}

# Upstream defects left for tts-data-pipeline to fix; ASR rules only exclude them.
KNOWN_ISSUES = {
    "starrail_voice": [
        (
            "en/ja/ko 配音约 94% 配的是中文文本（en 中文 78,864 条、英文 4,786 条），疑为接入时各语言共用了中文台词；"
            "待 tts-data-pipeline 修复，本仓库不改，ASR 规则按 script_mismatch 排除"
        ),
    ],
}


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def entry(data_root, dataset_id):
    relative = f"{UNIFIED}/{dataset_id}/{RELEASE}/manifest.json"
    path = data_root / relative
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest["status"] != "complete" or manifest["dataset_id"] != dataset_id:
        raise SystemExit(f"not a complete release: {path}")
    languages = sorted(k for k in manifest["languages"] if k not in ("null", None))
    asr = ASR.get(dataset_id)
    provenance = {
        "source": "DATA-TTS-UNIFIED",
        "contract": "DATA-TTS-UNIFIED/CONTRACT.md",
        "contract_version": manifest["contract_version"],
        "release_id": manifest["release_id"],
        "release_digest": manifest["release_digest"],
        "source_directory": f"DATA-TTS/{SOURCE_DIRS[dataset_id]}",
        "source_files": len(manifest["inputs"]),
        "excluded_source_files": [f["path"] for f in manifest["excluded_source_files"]],
        "finished_at": manifest["finished_at"],
        "description": "音频编码字节存放在 Lance 表内；原始划分在 metadata_json.original_split，统一输出全部为 train。ASR 用 tts_lance.iter_asr_samples（tts-asr-rules/v1）读取，会排除原始 dev/test 等。",
    }
    if asr:
        provenance["asr_notes"] = asr
    if dataset_id in KNOWN_ISSUES:
        provenance["known_issues"] = KNOWN_ISSUES[dataset_id]
    return {
        "schema_version": "dataset-catalog/2.0",
        "dataset_id": dataset_id,
        "version": VERSION,
        "languages": languages,
        "tasks": ["tts", "asr"] if asr else ["tts"],
        "artifacts": [
            {
                "name": "samples",
                "kind": "tts-lance-release",
                "root_alias": "aidc_data",
                "relative_path": relative,
                "expected_bytes": path.stat().st_size,
                "sha256": sha256(path),
                "metadata": {
                    "lance_version": manifest["lance_version"],
                    "rows": manifest["rows"],
                    "schema_sha256": manifest["schema_sha256"],
                    "storage_version": manifest["storage_version"],
                },
            }
        ],
        "splits": {
            "train": {
                "artifacts": {"samples": ["samples"]},
                "statistics": {
                    "rows": manifest["rows"],
                    "duration_hours": round(manifest["duration_seconds"] / 3600, 1),
                },
            }
        },
        "provenance": provenance,
    }


def main():
    data_root = Path(sys.argv[1])
    entries = []
    for dataset_id in sorted(SOURCE_DIRS):
        if not (data_root / UNIFIED / dataset_id / RELEASE / "manifest.json").exists():
            print(f"skip {dataset_id}: no published {RELEASE} release", file=sys.stderr)
            continue
        entries.append(entry(data_root, dataset_id))
    yaml = YAML()
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.width = 4096
    target = Path(__file__).resolve().parents[1] / "catalog/tts_unified.yaml"
    with target.open("w", encoding="utf-8") as stream:
        yaml.dump(entries, stream)
    print(f"wrote {len(entries)} releases to {target}")


if __name__ == "__main__":
    main()

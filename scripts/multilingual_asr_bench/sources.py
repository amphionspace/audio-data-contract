"""Splits of ``multilingual_asr_bench`` and the registered upstream snapshots they are copied from."""

from pathlib import Path

DATASET_ID = "multilingual_asr_bench"
VERSION = "v1-20261110"
ROOT = Path("/workspace/data/datasets") / DATASET_ID
DATA = Path("/workspace/data/datasets")

FLEURS_VERSION = "hf-70bb2e84b976"
CV_VERSION = "hf-8262c16bf297"
GIGASPEECH2_VERSION = "hf-8dc0d0e502b7"
CASABLANCA_VERSION = "hf-8951b1b88e28"

# Bench language -> (FLEURS locale, Common Voice locale), in the priority order of the request.
LANGUAGES = {
    "zh": ("cmn_hans_cn", "zh-CN"),
    "en": ("en_us", "en"),
    "ar": ("ar_eg", "ar"),
    "es": ("es_419", "es"),
    "fr": ("fr_fr", "fr"),
    "de": ("de_de", "de"),
    "pt": ("pt_br", "pt"),
    "ja": ("ja_jp", "ja"),
    "ko": ("ko_kr", "ko"),
    "hi": ("hi_in", "hi"),
    "ru": ("ru_ru", "ru"),
    "id": ("id_id", "id"),
}
NAMES = {
    "zh": "中文", "en": "英语", "ar": "阿拉伯语", "es": "西班牙语", "fr": "法语", "de": "德语",
    "pt": "葡萄牙语", "ja": "日语", "ko": "韩语", "hi": "印地语", "ru": "俄语", "id": "印尼语",
}
CASABLANCA_DIALECTS = {
    "Algeria": "阿尔及利亚", "Egypt": "埃及", "Jordan": "约旦", "Mauritania": "毛里塔尼亚",
    "Morocco": "摩洛哥", "Palestine": "巴勒斯坦", "UAE": "阿联酋", "Yemen": "也门",
}

SPLITS = []
for lang, (fleurs_locale, cv_locale) in LANGUAGES.items():
    fleurs = DATA / f"fleurs_{lang}" / "source" / FLEURS_VERSION / "data" / fleurs_locale
    SPLITS.append({
        "name": f"fleurs-{lang}",
        "kind": "fleurs",
        "language": lang,
        "locale": fleurs_locale,
        "source": "FLEURS",
        "derived_from": f"fleurs_{lang}@{FLEURS_VERSION}",
        "archives": [fleurs / "audio" / "test.tar.gz"],
        "transcripts": fleurs / "test.tsv",
        "description": f"FLEURS {fleurs_locale} test：{NAMES[lang]}朗读维基百科句子，同一句由多位说话人各读一遍。",
    })
    cv = DATA / f"common_voice_{lang}" / "source" / CV_VERSION
    SPLITS.append({
        "name": f"cv-{lang}",
        "kind": "common_voice",
        "language": lang,
        "locale": cv_locale,
        "source": "Common Voice 17.0",
        "derived_from": f"common_voice_{lang}@{CV_VERSION}",
        "archives": sorted((cv / "audio" / cv_locale / "test").glob("*.tar")),
        "transcripts": cv / "transcript" / cv_locale / "test.tsv",
        "description": f"Common Voice 17.0 {cv_locale} test：{NAMES[lang]}众包朗读，录音设备和环境各异。",
    })

gigaspeech2 = DATA / "gigaspeech2_id" / "source" / GIGASPEECH2_VERSION / "data" / "id"
SPLITS.append({
    "name": "gigaspeech2-id",
    "kind": "gigaspeech2",
    "language": "id",
    "locale": "id",
    "source": "GigaSpeech 2",
    "derived_from": f"gigaspeech2_id@{GIGASPEECH2_VERSION}",
    "archives": [gigaspeech2 / "test.tar.gz"],
    "transcripts": gigaspeech2 / "test.tsv",
    "description": "GigaSpeech 2 印尼语 test：YouTube 真实视频（访谈、vlog 等），人工标注，大写无标点；去掉 2 条空转写。",
})

casablanca = DATA / "casablanca" / "source" / CASABLANCA_VERSION
for dialect, label in CASABLANCA_DIALECTS.items():
    SPLITS.append({
        "name": f"casablanca-{dialect.lower()}",
        "kind": "casablanca",
        "language": "ar",
        "locale": dialect,
        "dialect": dialect,
        "source": "Casablanca",
        "derived_from": f"casablanca@{CASABLANCA_VERSION}",
        "parquet_dir": casablanca / dialect,
        "description": f"Casablanca {label}阿拉伯语方言 test：电视剧片段，人工转写，含与法语/英语的语码转换。CC BY-NC-ND 4.0，仅限非商业用途。",
    })

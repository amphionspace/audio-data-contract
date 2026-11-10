"""Splits of ``multilingual_asr_bench`` and the registered upstream snapshots they are copied from."""

from pathlib import Path

DATASET_ID = "multilingual_asr_bench"
# v2 adds Kathbath (hi), VoxPopuli (fr, de) and Golos (ru); v1 keeps its own records.
VERSION = "v2-20261110"
V1 = "v1-20261110"
ROOT = Path("/workspace/data/datasets") / DATASET_ID
DATA = Path("/workspace/data/datasets")

FLEURS_VERSION = "hf-70bb2e84b976"
CV_VERSION = "hf-8262c16bf297"
GIGASPEECH2_VERSION = "hf-8dc0d0e502b7"
CASABLANCA_VERSION = "hf-8951b1b88e28"
VOXPOPULI_VERSION = "hf-42f01879c780"
GOLOS_VERSION = "sberdevices-20250324"
KATHBATH_VERSION = "ai4bharat-20250409"

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

kathbath = DATA / "kathbath" / "source" / KATHBATH_VERSION
for part, folder, archive, label in (
    ("known", "test_known", "testkn_audio.tar", "已知说话人（说话人也出现在 Kathbath 训练集）"),
    ("unknown", "test", "testunk_audio.tar", "未知说话人（说话人不在 Kathbath 训练集）"),
):
    SPLITS.append({
        "name": f"kathbath-hi-{part}",
        "kind": "kathbath",
        "language": "hi",
        "locale": "hindi",
        "source": "Kathbath",
        "derived_from": f"kathbath@{KATHBATH_VERSION}",
        "folder": folder,
        "archives": [kathbath / archive],
        "transcripts": (kathbath / "transcripts_n2w.tar", f"kb_data_clean_m4a/hindi/{folder}/transcription_n2w.txt"),
        "description": f"Kathbath 印地语 test-{part}：众包手机朗读（clean 版）；{label}。转写为数字转写成词的版本（n2w）。音频由 m4a（AAC）解码为 FLAC。",
    })

for lang in ("fr", "de"):
    SPLITS.append({
        "name": f"voxpopuli-{lang}",
        "kind": "voxpopuli",
        "language": lang,
        "locale": lang,
        "source": "VoxPopuli",
        "derived_from": f"voxpopuli_{lang}@{VOXPOPULI_VERSION}",
        "parquet_files": [DATA / f"voxpopuli_{lang}" / "source" / VOXPOPULI_VERSION / lang / "test-00000-of-00001.parquet"],
        "description": f"VoxPopuli {lang} test：欧洲议会{NAMES[lang]}现场发言录音（2009–2020）；转写取 raw_text（带大小写和标点）。",
    })

golos = DATA / "golos" / "source" / GOLOS_VERSION / "test.tar"
for part, label in (("crowd", "众包用户在手机上念语音助手指令"), ("farfield", "在房间里对智能音箱念指令，远场麦克风录音")):
    SPLITS.append({
        "name": f"golos-{part}",
        "kind": "golos",
        "language": "ru",
        "locale": part,
        "source": "Golos",
        "derived_from": f"golos@{GOLOS_VERSION}",
        "part": part,
        "archives": [golos],
        "transcripts": (golos, f"test/{part}/manifest.jsonl"),
        "description": f"Golos {part} test：俄语，{label}；转写为小写、无标点。",
    })

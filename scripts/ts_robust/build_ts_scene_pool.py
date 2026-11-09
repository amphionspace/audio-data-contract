#!/usr/bin/env python3
"""Build ts_scene_pool: target-speaker scenes with several utterances per speaker.

Each record names every utterance of one scene, so the loader only places them in time:
  alternate  target and others take turns without overlap (target may speak twice)
  burst      each other speaker talks several utterances in a row while the target speaks
  short      a 1-3 s target utterance inside the others' speech
Speakers come from corpora with real speaker labels, read through the Lance record index
(speaker, text and span of every utterance). Other speakers always differ from the target
and from each other. The record's slots are the enrollment (another utterance of the target)
and the first target utterance; the whole scene is in metadata.scene.

With ``--multi`` it builds the multi-turn version: the benchmark's base scenes, where every speaker has a
track of its own and the target speaks 2-5 times with other speakers talking in between and over it
  full       parallel tracks; the target and each other speaker have their own silence between utterances
A share of the scenes (``--twin-share`` of the records) is followed by a twin: the same utterances and
timeline, but the enrollment is another speaker (half of the time one that sounds like the target, from
``--neighbors``), the target's utterances become one more interferer's and the transcript is empty.
The twin pairs share ``labels.pair`` so the model can only tell them apart by the voice.

With ``--neighbors neighbors.json`` (from speaker_neighbors.py) it builds the hard version
instead: one of the other speakers is a close neighbour of the target (a random one of the
``--hard-rank`` nearest by ERes2NetV2), in two kinds
  absent   the target is not in the scene: enrollment A, the scene holds a similar voice B
           and others, the transcript is empty (the benchmark's abs-hard)
  present  the target speaks and a similar voice B is among the others

    python build_ts_scene_pool.py --output-dir DIR [--zh 150000 --en 100000]
    python build_ts_scene_pool.py --output-dir DIR --version hard-20261016 --neighbors FILE --zh 40000 --en 25000
    python build_ts_scene_pool.py --output-dir DIR --version multi-20261017 --multi --neighbors FILE --zh 120000 --en 40000

With ``--solo`` it builds the short solo version: the target says one short utterance and nobody else speaks. The
multi-turn and one-target mixes hold almost no target utterance under 3 s (aishellmix / librimix ``train_1spk`` have
none under 3 s for aishellmix), so a model trained on them learns to stay silent on a bare short phrase. A share of the
records are twins: the same utterance, but the enrollment is another speaker, so the transcript is empty. With
``--neighbors`` half of the twins enroll a close neighbour of the target, as in the multi-turn version.

    python build_ts_scene_pool.py --output-dir DIR --version solo-20261019 --solo --twin-share 0.3 --zh 60000 --en 20000
    python build_ts_scene_pool.py --output-dir DIR --version solo-20261020 --solo --neighbors FILE --twin-share 0.3 \\
        --zh 60000 --en 20000

With ``--handover`` it builds the handover version: the target says one utterance and one other speaker says one
utterance, one after the other without overlap, in either order (alternate mode). The other pools never hold this:
alternate scenes have at least two other speakers and the solo scenes have none, and the benchmark's handover scenes
(ts_asr_handover) showed the model staying silent on them. With ``--neighbors`` half of the other speakers are a close
neighbour of the target. A share of the records are twins: the same two utterances, but the enrollment is another
speaker (half of the time a neighbour of the target), so both utterances are interferers and the transcript is empty.

    python build_ts_scene_pool.py --output-dir DIR --version handover-20261021 --handover --neighbors FILE \\
        --twin-share 0.3 --zh 40000 --en 12000

With ``--multi --xsession`` the targets are KeSpeech speakers who recorded both a Mandarin (phase1) and a dialect
(phase2) session. A scene's target utterances come from one session; with XSESSION_CROSS_PROB the enrollment comes
from the other session (``labels.cross_session``), otherwise from the same one. The other pools take their targets from
AISHELL-2 / AISHELL-1, one session per speaker, so the model never has to accept a voice across sessions and can lean on
the channel; on ts-asr-benchmark@v12 a Mandarin/dialect mismatch between enrollment and target leaves 34% of KeSpeech
targets untranscribed (5.7% within one variety). AISHELL-2 stays among the other speakers, and twins enroll another
KeSpeech speaker, so neither the channel nor the corpus tells present from absent.

    python build_ts_scene_pool.py --output-dir DIR --version xsession-20261023 --multi --xsession --twin-share 0.3 \\
        --zh 80000 --en 0

With ``--multi --magicdata`` the targets are MagicData speakers (read speech recorded on phones). On
ts-asr-benchmark@v12 a MagicData target speaking alone is transcribed at 14.5% CER through TS against 1.7% for plain
ASR (mostly untranscribed targets), while AISHELL-1/2/3 targets alone match plain ASR; no pool has had a MagicData
target. Twins enroll another MagicData speaker. 73% of MagicData test utterances repeat a train sentence, so train
utterances whose text is in the test split are dropped (HELD_OUT_TEXT).

    python build_ts_scene_pool.py --output-dir DIR --version magicdata-20261023 --multi --magicdata --twin-share 0.3 \\
        --zh 80000 --en 0

Both pools need ``--neighbors`` from ``speaker_neighbors.py --kespeech-magicdata``: without it every twin enrolls a
random speaker, far from the target (ERes2NetV2 cosine median 0.09 / 0.12 against 0.25 in the AISHELL-2 pools), and
040 (v7set13) learned to transcribe other speakers after a KeSpeech or MagicData target's utterance (MagicData target
with a MagicData other speaker: 1.2% -> 16.9% of the v12 samples). With it half of the twins enroll a close neighbour,
as in every other pool.

    python build_ts_scene_pool.py --output-dir DIR --version xsession-near-20261023 --multi --xsession \\
        --neighbors FILE --twin-share 0.3 --zh 80000 --en 0
    python build_ts_scene_pool.py --output-dir DIR --version magicdata-near-20261023 --multi --magicdata \\
        --neighbors FILE --twin-share 0.3 --zh 80000 --en 0

The near twins did not stop it (041@5000 matches 040@5000): the transcribed other speakers are in turn-taking scenes,
where the target and the others do not overlap (KeSpeech/MagicData targets on v12 handover-* 15-28%, dyn-alternate
18%, dyn-enter/leave 9-14%; overlapped scenes 1-3%; AISHELL targets 0-3% everywhere). AISHELL-2 targets also train on
the turn-taking pools (v2-20261016 alternate/burst/short, hard-20261016, handover-20261021); KeSpeech and MagicData
targets only had full scenes. ``--xsession`` and ``--magicdata`` therefore also build the alternate/burst/short and
the handover version, with the same target corpora, other speakers and (for --xsession) sessions:

    python build_ts_scene_pool.py --output-dir DIR --version xsession-alt-20261023 --xsession --zh 60000 --en 0
    python build_ts_scene_pool.py --output-dir DIR --version xsession-handover-20261023 --handover --xsession \\
        --neighbors FILE --twin-share 0.3 --zh 40000 --en 0
    python build_ts_scene_pool.py --output-dir DIR --version magicdata-alt-20261023 --magicdata --zh 60000 --en 0
    python build_ts_scene_pool.py --output-dir DIR --version magicdata-handover-20261023 --handover --magicdata \\
        --neighbors FILE --twin-share 0.3 --zh 40000 --en 0

The alternate/burst/short version has every target present; AISHELL-2 targets balance it with the hard version
(hard-20261016, 55% absent with a similar voice in the scene). Without that, 042 (alt + handover, no hard) stopped
transcribing the other speakers but answered absent KeSpeech / MagicData enrollments with another speaker's words
(v12 absent false alarms 5.2% -> 13.0% / 2.4% -> 7.6%; AISHELL enrollments unchanged), so they get the hard version too:

    python build_ts_scene_pool.py --output-dir DIR --version xsession-hard-20261023 --xsession --neighbors FILE \\
        --zh 40000 --en 0
    python build_ts_scene_pool.py --output-dir DIR --version magicdata-hard-20261023 --magicdata --neighbors FILE \\
        --zh 40000 --en 0

With ``--alt-twins`` it builds the turn-taking version (alternate / burst / short, as without a mode flag) with twins,
as the multi-turn, solo and handover versions have: a share of the records (``--twin-share``) are the scene again with
another speaker enrolled, half of the time a close neighbour from ``--neighbors``. Without twins these modes are almost
always present: v2-20261016, xsession-alt and magicdata-alt hold no absent scene, and the hard version's absent scenes
are alternate or burst, never short. Checkpoints trained on them transcribe one of the speakers whatever the enrollment
says. Rendered training scenes with another speaker of the same pool enrolled are answered by 10.21 (033 avg3) in 17% of
v2-20261016's scenes (29% of its short ones) and by 044@5000, which added the KeSpeech / MagicData alt pools, in 43% of
xsession-alt's (65% of short ones), against 4-8% on the twinned multi-turn pools. On ts-asr-benchmark@v12 the same
checkpoints answer absent KeSpeech-enrolled samples with another speaker's words (2.6% -> 17.8%).

    python build_ts_scene_pool.py --output-dir DIR --version alt-twins-20261024 --alt-twins --neighbors FILE \\
        --twin-share 0.3
    python build_ts_scene_pool.py --output-dir DIR --version xsession-alt-twins-20261024 --alt-twins --xsession \\
        --neighbors FILE --twin-share 0.3 --zh 60000 --en 0
    python build_ts_scene_pool.py --output-dir DIR --version magicdata-alt-twins-20261024 --alt-twins --magicdata \\
        --neighbors FILE --twin-share 0.3 --zh 60000 --en 0

With ``--hard-twins`` it builds the hard version with twins: every base scene is a present one with a close neighbour of
the target among the others (alternate / burst / short), and a share of the records (``--twin-share``) are the scene
again with another speaker enrolled, half of the time another close neighbour of the target. The hard version's absent
scenes are separate scenes, never short and never the twin of a present one, the last scene family without twins.
048 avg3 still answers the hard absent splits of ts-asr-benchmark@v12 more often than 10.21 (abs-hard, realreg, short),
while every twinned family improved. ``--twin-share 0.5`` twins every base scene (half the records absent, as the
hard version's 55%):

    python build_ts_scene_pool.py --output-dir DIR --version hard-twins-20261026 --hard-twins --neighbors FILE \\
        --twin-share 0.5 --zh 40000 --en 25000
    python build_ts_scene_pool.py --output-dir DIR --version xsession-hard-twins-20261026 --hard-twins --xsession \\
        --neighbors FILE --twin-share 0.5 --zh 40000 --en 0
    python build_ts_scene_pool.py --output-dir DIR --version magicdata-hard-twins-20261026 --hard-twins --magicdata \\
        --neighbors FILE --twin-share 0.5 --zh 40000 --en 0

With ``--ramc`` the targets are MagicData-RAMC speakers: real Mandarin phone conversations (mono, so a target utterance
can carry the partner's back-channel). The KeSpeech and MagicData pools hold read speech; the only conversational TS data
are the real meeting windows. Utterances come from magicdata_ramc@clean-dual-pass-20261027 (clean-pass rows with a Lance
record index); speakers of the RAMC dev and test splits (HELD_OUT_SPEAKERS) are dropped, because ts-asr-benchmark@v12's
real-ramc windows come from the test split and 9 train speakers also talk there. RAMC gives a person a new ID in every
conversation, so ``--same-voice`` (ramc_voice_identities.py) is required: IDs that sound like one person are never
target and other speaker (or twin enrollee) of one scene and are no near voice of each other, and train IDs that sound
like a dev / test speaker are dropped. Other speakers are half AISHELL-2, half RAMC, and the four pool kinds the
MagicData pools of the training recipe use are built (multi-turn with near twins, turn-taking with twins, hard,
handover with twins), neighbours from ``speaker_neighbors.py --ramc``:

    python build_ts_scene_pool.py --output-dir DIR --version ramc-near-20261028 --multi --ramc --same-voice FILE \\
        --neighbors FILE --twin-share 0.3 --zh 40000 --en 0
    python build_ts_scene_pool.py --output-dir DIR --version ramc-alt-twins-20261028 --alt-twins --ramc --same-voice FILE \\
        --neighbors FILE --twin-share 0.3 --zh 30000 --en 0
    python build_ts_scene_pool.py --output-dir DIR --version ramc-hard-20261028 --ramc --same-voice FILE \\
        --neighbors FILE --zh 20000 --en 0
    python build_ts_scene_pool.py --output-dir DIR --version ramc-handover-20261028 --handover --ramc --same-voice FILE \\
        --neighbors FILE --twin-share 0.3 --zh 20000 --en 0

A KeSpeech speaker reads the same prompts in both sessions, so a cross-session enrollment can say the target's own
sentence (3.9% of xsession-near-20261023's present records); the transcript can then be read off the enrollment, and
v12 nonspeech samples with a KeSpeech enrollment come back as the enrollment's words. Enrollments never say a sentence
of the scene's target utterances.

With ``--cv-accents`` or ``--cs-dialogue`` the English targets have the accents the LibriSpeech pools lack (63% of the
English TS targets of 10.28 are LibriSpeech audiobook speakers). On ts-asr-benchmark-en 10.28 leaves 13.8% of VCTK
targets untranscribed (Scottish, Irish, Canadian about 20%, short targets 27%) against 1.8% of LibriSpeech targets,
and transcribes CS-Dialogue (Chinese speakers' English) at 44.6% WER.
  --cv-accents   Common Voice English train speakers with an accent label, drawn by accent group: a group gets
                 speakers ** ACCENT_EXPONENT of the draws, at most MAX_ACCENT_SHARE (United States and England would
                 otherwise take 70%). Text, clean-pass mark and accent come from the dual-engine clean manifest
                 (CV_CLEAN, docs/datasets/cv-en-cleaning.md); rejected utterances are dropped. Other speakers are half
                 these speakers, half LibriSpeech.
  --cs-dialogue  CS-Dialogue English train speakers (140); utterances marked <NPS/> (someone else talking) or ** (not
                 intelligible) are skipped and the other tags removed, as ts-asr-benchmark-en does. Other speakers are
                 half CS-Dialogue, a quarter the accent-labelled Common Voice speakers, a quarter LibriSpeech.
Speakers of the corpora's dev / test splits (HELD_OUT_SPEAKERS) never enter a pool; CS-Dialogue test speakers are
ts-asr-benchmark-en targets. Random twins enroll a speaker drawn like the targets (same corpus, same accent shares). Near
twins enroll a neighbour, and neighbours follow the speaker counts: enrollments with a United States accent are absent
in about half of a pool, the others in 21-28% (cvaccent-near-20261101). Records carry ``labels.accent`` (the enrolled
speaker's accent group). Neighbours from ``speaker_neighbors.py --en-accents``; all five pool kinds are built:

    python build_ts_scene_pool.py --output-dir DIR --version cvaccent-near-20261101 --multi --cv-accents \\
        --neighbors FILE --twin-share 0.3 --zh 0 --en 60000
    python build_ts_scene_pool.py --output-dir DIR --version cvaccent-alt-twins-20261101 --alt-twins --cv-accents \\
        --neighbors FILE --twin-share 0.3 --zh 0 --en 40000
    python build_ts_scene_pool.py --output-dir DIR --version cvaccent-hard-20261101 --cv-accents --neighbors FILE \\
        --zh 0 --en 25000
    python build_ts_scene_pool.py --output-dir DIR --version cvaccent-handover-20261101 --handover --cv-accents \\
        --neighbors FILE --twin-share 0.3 --zh 0 --en 20000
    python build_ts_scene_pool.py --output-dir DIR --version cvaccent-solo-20261101 --solo --cv-accents \\
        --neighbors FILE --twin-share 0.3 --zh 0 --en 30000
    (the same five with --cs-dialogue and csd-*-20261101 versions, smaller: CS-Dialogue has 4.3k usable utterances)
"""

import argparse
import functools
import gzip
import json
import random
import re
import unicodedata
from collections import Counter
from itertools import accumulate
from pathlib import Path

import lance
import numpy as np
import pyarrow as pa
import yaml

DATA = Path("/workspace/data")
REGISTRY = DATA / "registry/catalog/datasets.yaml"
DATASET_ID = "ts_scene_pool"
VERSION = "v2-20261016"
SEED = 20261016
# Corpora per language: (dataset, version, split, weight as other speaker, can be the target)
CORPORA = {
    "zh": [("aishell2", "legacy-20260804", "train", 0.5, True), ("kespeech", "legacy-20260804", "train", 0.5, False)],
    "en": [("librispeech", "legacy-20260804", "train", 0.5, True), ("common_voice_en", "legacy-20260804", "train", 0.5, False)],
}
MODES = {"zh": (("alternate", 0.35), ("burst", 0.35), ("short", 0.30)),
         "en": (("alternate", 0.40), ("burst", 0.40), ("short", 0.20)),
         "es": (("alternate", 0.40), ("burst", 0.40), ("short", 0.20))}
UTTERANCE_SECONDS = {"zh": (1.0, 12.0), "en": (1.0, 8.0), "es": (1.0, 8.0)}
SHORT_TARGET_SECONDS = {"zh": (0.8, 2.5), "en": (1.0, 3.5), "es": (1.0, 3.5)}
ENROLLMENT_SECONDS = (2.5, 8.0)
# --xsession: targets are KeSpeech speakers with both sessions (phase1 Mandarin, phase2 dialect, the directory names).
XSESSION_CORPORA = [("aishell2", "legacy-20260804", "train", 0.5, False), ("kespeech", "legacy-20260804", "train", 0.5, True)]
SESSIONS = ("phase1", "phase2")
XSESSION_CROSS_PROB = 0.5
# --magicdata: targets are MagicData speakers; the other speakers are half AISHELL-2, half MagicData.
MAGICDATA_CORPORA = [("aishell2", "legacy-20260804", "train", 0.5, False), ("magicdata", "legacy-20260804", "train", 0.5, True)]
# --ramc: targets are MagicData-RAMC speakers (clean-pass conversation turns); the other speakers are half AISHELL-2, half RAMC.
RAMC_CORPORA = [("aishell2", "legacy-20260804", "train", 0.5, False), ("magicdata_ramc", "clean-dual-pass-20261027", "train", 0.5, True)]
# Speakers a corpus must not train on: (version, splits) whose speakers are dropped. RAMC dev / test speakers (9 of the
# test speakers also talk in train) are the targets of the benchmark's real-ramc windows.
HELD_OUT_SPEAKERS = {"magicdata_ramc": ("icefall-20260908", ("dev", "test"))}
# Splits whose sentences a corpus must not train on (73% of MagicData test utterances repeat a train sentence).
HELD_OUT_TEXT = {"magicdata": "test"}
# --cv-accents: targets are accent-labelled Common Voice English speakers; other speakers half them, half LibriSpeech.
CV_ACCENT_CORPORA = [("librispeech", "legacy-20260804", "train", 0.5, False), ("common_voice_en", "legacy-20260804", "train", 0.5, True)]
# --cs-dialogue: targets are CS-Dialogue English speakers; other speakers half them, a quarter each LibriSpeech and the
# accent-labelled Common Voice speakers.
# --es: Spanish pools, all from Common Voice es (MLS es has no utterance of 8 s or less): accent-labelled speakers are the
# targets, drawn by accent group as in --cv-accents, and half of the other speakers; speakers without an accent answer
# are the other half (the non-target corpus keeps only them, so the two corpora share no speaker).
ES_CORPORA = [("common_voice_es", "legacy", "train", 0.5, False), ("common_voice_es", "legacy", "train", 0.5, True)]
CS_DIALOGUE_CORPORA = [("librispeech", "legacy-20260804", "train", 0.25, False),
                       ("common_voice_en", "legacy-20260804", "train", 0.25, False),
                       ("cs_dialogue_en", "legacy-20260804", "train", 0.5, True)]
# Speakers a corpus must not train on: (version, splits) whose speakers are dropped. CS-Dialogue test speakers are
# ts-asr-benchmark-en targets; the train splits share no speaker ID with these splits (checked 2026-11-01).
HELD_OUT_SPEAKERS = {"librispeech": ("legacy-20260804", ("dev", "test_clean", "test_other")),
                     "common_voice_en": ("legacy-20260804", ("dev", "test")),
                     "cs_dialogue_en": ("legacy-20260804", ("dev", "test")),
                     "common_voice_es": ("legacy", ("dev", "test"))}
# Common Voice text, clean-pass mark and accent answer of the accent pools: (version, split, artifact role).
CV_CLEAN = {"common_voice_en": ("icefall-20260908", "train", "clean_supervisions"),
            "common_voice_es": ("es-train-v1-20261108", "train", "supervisions")}
# CS-Dialogue marks: <NPS/> someone else talking, ** not intelligible (skipped); other tags (<FIL/>, <SPK/>) are removed.
SKIP_TEXT = {"cs_dialogue_en": re.compile(r"<NPS/>|\*\*")}
TAGGED_TEXT = {"cs_dialogue_en"}
# The enrollment and up to five target turns; ts-asr-benchmark-en's min_utterances_per_speaker.
MIN_SPEAKER_UTTERANCES = 6
# Common Voice accent answers: the site's preset choices, and the free-text answers (exact) whose region is clear.
ACCENT_PRESETS = {"common_voice_en": {
    "United States English": "us", "England English": "england", "Scottish English": "scotland",
    "Irish English": "ireland", "Welsh English": "wales", "Canadian English": "canada",
    "Australian English": "aus_nz", "New Zealand English": "aus_nz",
    "India and South Asia (India, Pakistan, Sri Lanka)": "south_asia",
    "Southern African (South Africa, Zimbabwe, Namibia)": "africa",
    "West Indies and Bermuda (Bahamas, Bermuda, Jamaica, Trinidad)": "caribbean",
    "Filipino": "southeast_asia", "Malaysian English": "southeast_asia", "Singaporean English": "southeast_asia",
    "Hong Kong English": "hong_kong",
}, "common_voice_es": {
    "México": "mexico", "Ciudad de México": "mexico", "América central": "central_america",
    "Caribe: Cuba, Venezuela, Puerto Rico, República Dominicana, Panamá, Colombia caribeña, México caribeño, Costa del golfo de México": "caribbean",
    "Andino-Pacífico: Colombia, Perú, Ecuador, oeste de Bolivia y Venezuela andina": "andean",
    "Rioplatense: Argentina, Uruguay, este de Bolivia, Paraguay": "rioplatense", "Chileno: Chile, Cuyo": "chile",
    "España: Norte peninsular (Asturias, Castilla y León, Cantabria, País Vasco, Navarra, Aragón, La Rioja, Guadalajara, Cuenca)": "spain_north",
    "España: Centro-Sur peninsular (Madrid, Toledo, Castilla-La Mancha)": "spain_centre_south",
    "España: Sur peninsular (Andalucia, Extremadura, Murcia)": "spain_south", "España: Islas Canarias": "canary",
    "Español de Filipinas": "philippines",
}}
FREE_TEXT_ACCENTS = {"common_voice_en": {
    "Northern Irish": "ireland", "Nigerian English": "africa", "Kenyan": "africa", "Kenyan English": "africa",
    "West African": "africa", "Indonesian English": "southeast_asia", "Bangladeshi": "south_asia", "bangladesh": "south_asia"},
    "common_voice_es": {}}
# Draw share of an accent group: speakers ** ACCENT_EXPONENT (a square root, as in multilingual data sampling), capped
# at MAX_ACCENT_SHARE: plain speaker counts give United States 52% and England 16%, already the LibriSpeech pools' voice.
ACCENT_EXPONENT = 0.5
MAX_ACCENT_SHARE = 0.15
# Accent group of every CS-Dialogue speaker (Mandarin speakers' English), for labels.accent.
CORPUS_ACCENT = {"cs_dialogue_en": "mandarin_l1"}
# Longest scene per mode, gaps included. The benchmark's scenes run 5-18 s; the training
# batch holds about a dozen windows, so a 70 s scene would not fit.
SCENE_SECONDS = {"alternate": 30.0, "burst": 22.0, "short": 14.0, "full": 32.0}
MEAN_GAP_SECONDS = {"alternate": 0.6, "burst": 0.25, "short": 0.15}
# The benchmark's pauses between one speaker's utterances: dense, medium and sparse talk.
GAP_PROFILES = ((0.2, 1.0), (0.2, 1.0), (1.0, 3.0), (2.5, 6.0))
FULL_UTTERANCE_SECONDS = (1.5, 9.0)
FULL_TARGET_TURNS = ((2, 3, 4, 5), (0.4, 0.3, 0.2, 0.1))
# --solo: one short target utterance, nobody else. The benchmark's solo-mid clips are 2-6 s with a median of 6 characters.
SOLO_UTTERANCE_SECONDS = (1.0, 3.5)
# --handover: one target utterance and one other utterance in a row. The benchmark's handover utterances are 1.5-5 s.
HANDOVER_UTTERANCE_SECONDS = (1.0, 6.0)
FULL_INTERFERERS = ((1, 2, 3, 4), (0.3, 0.3, 0.25, 0.15))
MAX_UTTERANCES_PER_TRACK = 6
COLUMNS = ["id", "speaker", "text", "duration", "cut_id", "root_alias", "relative_path",
           "start_frame", "num_frames", "sample_rate", "channels"]


@functools.cache
def _registry_file(path):
    return yaml.load(path.read_text(), Loader=getattr(yaml, "CSafeLoader", yaml.SafeLoader)) or []


def catalog_entry(dataset, version):
    """The catalog entry of dataset@version from any file of the registry (datasets.yaml holds most, not all)."""
    for path in sorted(REGISTRY.parent.glob("*.yaml")):
        for entry in _registry_file(path):
            if isinstance(entry, dict) and entry.get("dataset_id") == dataset and entry.get("version") == version:
                return entry
    raise KeyError(f"{dataset}@{version} is not in {REGISTRY.parent}")


def lhotse_rows(entry, split, role):
    """Every row of the Lhotse manifests a split lists under ``role`` (recordings, supervisions, ...)."""
    roots = json.loads((DATA / "registry/roots.json").read_text())
    for name in entry["splits"][split]["artifacts"][role]:
        artifact = next(a for a in entry["artifacts"] if a["name"] == name)
        with gzip.open(Path(roots[artifact["root_alias"]]) / artifact["relative_path"], "rt", encoding="utf-8") as stream:
            yield from (json.loads(line) for line in stream if line.strip())


def held_out_speakers(dataset):
    """Speakers of the held-out splits of HELD_OUT_SPEAKERS[dataset], from that version's lhotse supervisions."""
    version, splits = HELD_OUT_SPEAKERS[dataset]
    entry = catalog_entry(dataset, version)
    return {row["speaker"] for split in splits for row in lhotse_rows(entry, split, "supervisions")}


def lhotse_table(entry, split):
    """COLUMNS of a split that has no Lance record index, from its Lhotse recordings and supervisions."""
    recordings = {r["id"]: r for r in lhotse_rows(entry, split, "recordings")}
    rows = {c: [] for c in COLUMNS}
    for s in lhotse_rows(entry, split, "supervisions"):
        recording = recordings[s["recording_id"]]
        path = Path(recording["sources"][0]["source"])
        rate = recording["sampling_rate"]
        start = round(s["start"] * rate)
        for column, value in (("id", s["id"]), ("speaker", s.get("speaker")), ("text", s.get("text") or ""),
                              ("duration", s["duration"]), ("cut_id", s["id"]), ("root_alias", "aidc_data"),
                              ("relative_path", path.relative_to(DATA).as_posix()), ("start_frame", start),
                              ("num_frames", min(round(s["duration"] * rate), recording["num_samples"] - start)),
                              ("sample_rate", rate), ("channels", len(recording["channel_ids"]))):
            rows[column].append(value)
    return pa.table(rows)


def tagless(text):
    """CS-Dialogue text without its annotation tags (<FIL/> ...), single spaces, no space before punctuation."""
    return re.sub(r" ([.,!?;:])", r"\1", " ".join(re.sub(r"<[^>]*>", " ", text).split()))


def accent_group(answer, dataset="common_voice_en"):
    """The accent group of a Common Voice ``accents`` answer: None when unanswered or naming two groups, "other" for
    free text alone (mostly second-language speakers: German, Russian, Polish ...)."""
    rest, groups = answer or "", set()
    # longest first: "Ciudad de México" before "México"
    for preset, group in sorted(ACCENT_PRESETS[dataset].items(), key=lambda item: -len(item[0])):
        if preset in rest:
            groups.add(group)
            rest = rest.replace(preset, "")
    free = [part.strip() for part in rest.split(",") if part.strip()]
    groups |= {FREE_TEXT_ACCENTS[dataset][part] for part in free if part in FREE_TEXT_ACCENTS[dataset]}
    if len(groups) > 1:
        return None
    return groups.pop() if groups else "other" if free else None


def accent_shares(counts):
    """Draw share per accent group: speakers ** ACCENT_EXPONENT, none above MAX_ACCENT_SHARE (the rest gets the excess)."""
    if MAX_ACCENT_SHARE * len(counts) < 1:
        raise ValueError(f"{len(counts)} accent groups cannot all stay under {MAX_ACCENT_SHARE}")
    raw = {group: n ** ACCENT_EXPONENT for group, n in counts.items()}
    capped = set()
    while True:
        left = 1 - MAX_ACCENT_SHARE * len(capped)
        total = sum(v for group, v in raw.items() if group not in capped)
        shares = {group: MAX_ACCENT_SHARE if group in capped else left * v / total for group, v in raw.items()}
        over = {group for group, share in shares.items() if share > MAX_ACCENT_SHARE} - capped
        if not over:
            return shares
        capped |= over


def _plain(text):
    """Text compared for held-out sentences: NFKC, lower case, no punctuation, symbols or spaces."""
    return "".join(c for c in unicodedata.normalize("NFKC", text or "").lower() if unicodedata.category(c)[0] not in "PSZ")


class Corpus:
    def __init__(self, dataset, version, split, weight, target, language, sessions=False, accents=False, drop=()):
        """``accents``: a corpus of the --cv-accents / --cs-dialogue pools (clean text, accent groups, enough utterances)."""
        self.name, self.weight, self.target = dataset, weight, target
        entry = catalog_entry(dataset, version)
        if "records_lance" in entry["splits"][split]["artifacts"]:
            artifact = next(a for a in entry["artifacts"]
                            if a["name"] == entry["splits"][split]["artifacts"]["records_lance"][0])
            directory = DATA / artifact["relative_path"].rsplit("/", 1)[0]
            manifest = json.loads((directory / "index.json").read_text())
            table = lance.dataset(str(directory / manifest["table_path"])).to_table(
                columns=COLUMNS, filter=f"array_has(splits, '{split}')")
        else:
            table = lhotse_table(entry, split)
        accent_of = {}
        if accents and dataset in CV_CLEAN:
            # The clean manifest's text (original case and punctuation), its pass mark and the speaker's accent answer.
            version, *where = CV_CLEAN[dataset]
            clean = {row["id"]: row for row in lhotse_rows(catalog_entry(dataset, version), *where)}
            rows = [clean.get(i) for i in table["id"].to_pylist()]
            passed = [r is not None and (r.get("custom", {}).get("clean") or {}).get("pass") is True for r in rows]
            groups = [accent_group(r.get("custom", {}).get("accents"), dataset) if r else None for r in rows]
            # A speaker's group is the one of their utterances; the --es other-speaker corpus keeps the unlabelled ones.
            accent_of = {r["speaker"]: g for r, g in zip(rows, groups) if g}
            unlabelled = dataset == "common_voice_es" and not target
            wanted = [p and (r["speaker"] not in accent_of if unlabelled else g is not None)
                      for p, r, g in zip(passed, rows, groups)]
            if unlabelled:
                accent_of = {}
            print(dataset, "clean-pass utterances", sum(passed), "without an accent group" if unlabelled else "with an accent group",
                  sum(wanted), flush=True)
            table = table.filter(pa.array(wanted))
            table = table.set_column(table.schema.get_field_index("text"), "text",
                                     pa.array([clean[i]["text"] for i in table["id"].to_pylist()], pa.large_string()))
        duration = table["duration"].to_numpy(zero_copy_only=False)
        text = table["text"].to_pylist()
        if dataset in SKIP_TEXT:
            skipped = np.array([bool(SKIP_TEXT[dataset].search(t or "")) for t in text])
            print(dataset, "skipped", int(skipped.sum()), "utterances with", SKIP_TEXT[dataset].pattern, flush=True)
            table, duration = table.filter(~skipped), duration[~skipped]
            text = [t for t, s in zip(text, skipped) if not s]
        if dataset in TAGGED_TEXT:
            text = [tagless(t) for t in text]
            table = table.set_column(table.schema.get_field_index("text"), "text", pa.array(text, table.schema.field("text").type))
        speaker = table["speaker"].to_pylist()
        keep = np.array([bool(t and len(t.strip()) >= 2) and bool(s) for t, s in zip(text, speaker)]
                        ) & (duration >= UTTERANCE_SECONDS[language][0]) & (duration <= UTTERANCE_SECONDS[language][1])
        if dataset in HELD_OUT_TEXT:
            held = {_plain(t) for t in lance.dataset(str(directory / manifest["table_path"])).to_table(
                columns=["text"], filter=f"array_has(splits, '{HELD_OUT_TEXT[dataset]}')")["text"].to_pylist()}
            same = np.array([_plain(t) in held for t in text])
            print(dataset, "dropped", int((keep & same).sum()), "utterances with a", HELD_OUT_TEXT[dataset], "sentence", flush=True)
            keep &= ~same
        if dataset in HELD_OUT_SPEAKERS:
            held = held_out_speakers(dataset)
            out = np.array([s in held for s in speaker], dtype=bool)  # a set: np.isin sorts 10^6 long strings
            print(dataset, "dropped", int((keep & out).sum()), "utterances of", len(held & set(speaker)), "held-out speakers", flush=True)
            keep &= ~out
        if drop:
            out = np.array([s in drop for s in speaker], dtype=bool)
            print(dataset, "dropped", int((keep & out).sum()), "utterances of", len(set(drop) & set(speaker)), "speakers (--same-voice drop)", flush=True)
            keep &= ~out
        if accents:
            counts = Counter(s for s, k in zip(speaker, keep) if k)
            keep &= np.array([counts[s] >= MIN_SPEAKER_UTTERANCES for s in speaker], dtype=bool)
        session = None
        if sessions:
            # Keep only speakers with an utterance in every session, so any scene can enroll across sessions.
            session = np.array([path.rsplit("/", 2)[-2] for path in table["relative_path"].to_pylist()])
            names = np.array(speaker)
            both = set.intersection(*(set(names[keep & (session == s)]) for s in SESSIONS))
            keep &= np.isin(names, sorted(both))
        self.rows = table.filter(keep).to_pydict()
        self.plain = [_plain(t) for t in self.rows["text"]]
        self.session = session[keep] if sessions else None
        self.duration = duration[keep]
        # np.unique's order and inverse, without sorting 10^6 long strings (Common Voice IDs have 128 characters)
        names = sorted(set(self.rows["speaker"]))
        position = {n: i for i, n in enumerate(names)}
        inverse = np.fromiter((position[s] for s in self.rows["speaker"]), dtype=np.int64, count=len(self.rows["speaker"]))
        order = np.argsort(inverse, kind="stable")
        bounds = np.searchsorted(inverse[order], np.arange(len(names) + 1))
        self.speakers = [f"{dataset}:{n}" for n in names]
        self.by_speaker = [order[bounds[i]:bounds[i + 1]] for i in range(len(names))]
        print(dataset, "utterances", int(keep.sum()), "speakers", len(names), flush=True)
        groups = [accent_of.get(n, CORPUS_ACCENT.get(dataset)) for n in names] if accents else []
        self.accent = {s: g for s, g in zip(self.speakers, groups) if g}
        self.cum_weights = None
        if accent_of:
            counts = Counter(groups)
            shares = accent_shares(counts)
            self.cum_weights = list(accumulate(shares[g] / counts[g] for g in groups))
            print(dataset, "accent groups (speakers, draw share)",
                  {g: (counts[g], round(shares[g], 3)) for g in sorted(shares, key=shares.get, reverse=True)}, flush=True)

    def draw_speaker(self, rng):
        """A speaker index: uniform, or by accent group share (the --cv-accents speakers)."""
        if self.cum_weights is None:
            return rng.randrange(len(self.speakers))
        return rng.choices(range(len(self.speakers)), cum_weights=self.cum_weights)[0]

    def pick(self, rng, speaker, count, low=None, high=None, exclude=(), session=None):
        """``count`` distinct utterances of one speaker, optionally within a duration range and one session."""
        rows = [i for i in self.by_speaker[speaker] if i not in exclude
                and (low is None or low <= self.duration[i] <= high)
                and (session is None or self.session[i] == session)]
        return rng.sample(rows, count) if len(rows) >= count else None

    def not_enrollment(self, speaker, targets):
        """The target utterances and every other utterance of the speaker that says one of their sentences."""
        said = {self.plain[i] for i in targets}
        return set(targets) | {i for i in self.by_speaker[speaker] if self.plain[i] in said}

    def usable(self, speaker, count):
        return len(self.by_speaker[speaker]) >= count


class Builder:
    def __init__(self, language, rng, neighbors=None, hard_rank=10, xsession=False, magicdata=False, ramc=False, same_voice=None,
                 cv_accents=False, cs_dialogue=False):
        self.language, self.rng, self.xsession = language, rng, xsession
        spanish = language == "es"
        corpora = XSESSION_CORPORA if xsession else MAGICDATA_CORPORA if magicdata else RAMC_CORPORA if ramc \
            else CV_ACCENT_CORPORA if cv_accents else CS_DIALOGUE_CORPORA if cs_dialogue else ES_CORPORA if spanish \
            else CORPORA[language]
        drop = {n.split(":", 1)[1] for n in (same_voice or {}).get("drop", {})}
        self.corpora = [Corpus(*c, language, sessions=xsession and c[4], accents=cv_accents or cs_dialogue or spanish,
                               drop=drop if c[0] == "magicdata_ramc" else ())
                        for c in corpora]
        self.targets = [c for c in self.corpora if c.target]
        self.accent = {name: group for c in self.corpora for name, group in c.accent.items()}
        # IDs that sound like one person (--same-voice): kept apart like one speaker, and no near voice of each other.
        self.alike = {}
        for a, b, _ in (same_voice or {}).get("same_voice", []):
            self.alike.setdefault(a, set()).add(b)
            self.alike.setdefault(b, set()).add(a)
        if neighbors and self.alike:
            neighbors = {k: [x for x in v if x[0] not in self.alike.get(k, ())] for k, v in neighbors.items()}
        self.neighbors, self.hard_rank = neighbors, hard_rank
        self.where = {name: (c, i) for c in self.corpora for i, name in enumerate(c.speakers)}
        self.audio, self.pending = {}, {}

    def blocked(self, names):
        """The speakers who must not join a scene of ``names``: those speakers and every ID that sounds like one of them."""
        return set(names).union(*(self.alike.get(n, ()) for n in names))

    def ref(self, corpus, i):
        rows = corpus.rows
        cut = f"{corpus.name}:{rows['cut_id'][i]}"
        rate, start, frames = rows["sample_rate"][i], rows["start_frame"][i], rows["num_frames"][i]
        self.pending.setdefault(cut, {
            "cut_id": cut, "root_alias": rows["root_alias"][i], "relative_path": rows["relative_path"][i],
            "sample_rate": rate, "channels": rows["channels"][i] or 1,
            "num_frames": start + frames, "duration": round((start + frames) / rate, 3)})
        return {"cut_id": cut, "start": round(start / rate, 3), "duration": round(frames / rate, 3)}

    def sessions(self):
        """(target session, enrollment session) of a --xsession scene: the other session with XSESSION_CROSS_PROB."""
        if not self.xsession:
            return None, None
        own = self.rng.choice(SESSIONS)
        return own, next(s for s in SESSIONS if s != own) if self.rng.random() < XSESSION_CROSS_PROB else own

    def other_speaker(self, used, count):
        """A (corpus, speaker, utterances) for one other speaker, never one already in the scene."""
        rng = self.rng
        for _ in range(200):
            corpus = rng.choices(self.corpora, [c.weight for c in self.corpora])[0]
            speaker = corpus.draw_speaker(rng)
            if corpus.speakers[speaker] in self.blocked(used) or not corpus.usable(speaker, count):
                continue
            picks = corpus.pick(rng, speaker, count)
            if picks:
                used.add(corpus.speakers[speaker])
                return corpus, speaker, picks
        raise RuntimeError("no other speaker found")

    def scene(self, mode, hard=None):
        """A scene no longer than SCENE_SECONDS[mode]; draws again when one comes out too long."""
        while True:
            self.pending = {}
            scene, joiner, seconds = self.draw(mode, hard)
            if seconds <= SCENE_SECONDS[mode]:
                self.audio.update(self.pending)
                return scene, joiner

    def draw(self, mode, hard=None):
        rng = self.rng
        corpus = rng.choice(self.targets)
        short_low, short_high = SHORT_TARGET_SECONDS[self.language]
        while True:
            speaker = corpus.draw_speaker(rng)
            if hard:
                near = [n for n, _ in self.neighbors.get(corpus.speakers[speaker], [])[: self.hard_rank] if n in self.where]
                if not near:
                    continue
            wanted = 0 if hard == "absent" else 1 if mode != "alternate" else (2 if rng.random() < 0.4 else 1)
            own, enrolled = self.sessions()
            targets = corpus.pick(rng, speaker, wanted, *((short_low, short_high) if mode == "short" else (None, None)),
                                  session=own) if wanted else []
            enrollment = corpus.pick(rng, speaker, 1, *ENROLLMENT_SECONDS, exclude=corpus.not_enrollment(speaker, targets),
                                     session=enrolled) if targets is not None else None
            if targets is not None and enrollment:
                break
        used = {corpus.speakers[speaker]}
        if mode == "alternate":
            k, per_speaker = rng.choices((2, 3, 4, 5, 6), (0.25, 0.25, 0.2, 0.15, 0.15))[0], lambda: 2 if rng.random() < 0.3 else 1
        elif mode == "burst":
            k, per_speaker = rng.choices((1, 2, 3, 4, 5, 6), (0.1, 0.15, 0.2, 0.2, 0.2, 0.15))[0], lambda: rng.randint(2, 4)
        else:
            k, per_speaker = rng.choices((1, 2, 3, 4, 5), (0.25, 0.2, 0.2, 0.2, 0.15))[0], lambda: rng.randint(1, 2)
        others, lengths = [], []
        if hard:
            # The similar voice is the first of the others; its cosine is kept for analysis.
            name = rng.choice(near)
            close, who = self.where[name]
            count = per_speaker()
            picks = close.pick(rng, who, count) if close.usable(who, count) else close.pick(rng, who, 1)
            if not picks:
                raise RuntimeError("similar speaker has no usable utterance")
            used.add(name)
            others.append({"speaker": name, "utts": [self.ref(close, i) for i in picks]})
            lengths.append(sum(close.duration[i] for i in picks) + MEAN_GAP_SECONDS[mode] * (len(picks) - 1))
        for _ in range(k - len(others)):
            count = per_speaker()
            while True:
                try:
                    other, who, picks = self.other_speaker(used, count)
                    break
                except RuntimeError:
                    count = max(1, count - 1)
            others.append({"speaker": other.speakers[who], "utts": [self.ref(other, i) for i in picks]})
            lengths.append(sum(other.duration[i] for i in picks) + MEAN_GAP_SECONDS[mode] * (len(picks) - 1))
        target_seconds = sum(corpus.duration[i] for i in targets) + MEAN_GAP_SECONDS[mode] * max(len(targets) - 1, 0)
        # alternate puts everything in a row; burst and short last as long as the longest speaker
        seconds = sum(lengths) + target_seconds + MEAN_GAP_SECONDS[mode] * (len(lengths) + 1) if mode == "alternate" \
            else max([target_seconds, *lengths])
        joiner = "" if self.language == "zh" else " "
        scene = {"hard": {"kind": hard, "neighbor": name,
                          "cosine": dict(self.neighbors[corpus.speakers[speaker]])[name]}} if hard else {}
        if self.xsession and targets:
            scene["session"] = {"targets": own, "enrollment": enrolled}
        return {
            **scene, "mode": mode, "target_speaker": corpus.speakers[speaker],
            "targets": [{**self.ref(corpus, i), "text": corpus.rows["text"][i].strip()} for i in targets],
            "enrollment": self.ref(corpus, enrollment[0]), "interferers": others}, joiner, seconds

    def full_pair(self, twin):
        """A multi-turn scene and, when ``twin``, its twin. Draws again when the scene is too long.

        The twin keeps every utterance and gap of the scene but enrolls another speaker, so the
        target's utterances turn into one more interferer's and the transcript is empty.
        """
        while True:
            self.pending = {}
            scene, seconds = self.draw_full()
            if seconds > SCENE_SECONDS["full"]:
                continue
            paired = self.draw_twin(scene) if twin else None
            self.audio.update(self.pending)
            return scene, paired

    def draw_full(self):
        rng = self.rng
        corpus = rng.choice(self.targets)
        turns = rng.choices(*FULL_TARGET_TURNS)[0]
        low, high = FULL_UTTERANCE_SECONDS
        while True:
            speaker = corpus.draw_speaker(rng)
            own, enrolled = self.sessions()
            targets = corpus.pick(rng, speaker, turns, low, high, session=own)
            enrollment = corpus.pick(rng, speaker, 1, *ENROLLMENT_SECONDS, exclude=corpus.not_enrollment(speaker, targets), session=enrolled) if targets else None
            if enrollment:
                break
        used = {corpus.speakers[speaker]}
        target_gap = rng.choice(GAP_PROFILES)
        mean = lambda gap: (gap[0] + gap[1]) / 2
        target_length = sum(corpus.duration[i] for i in targets) + mean(target_gap) * (turns - 1)
        seconds = target_length + (target_gap[1] - mean(target_gap)) * (turns - 1)
        others = []
        for _ in range(rng.choices(*FULL_INTERFERERS)[0]):
            gap = rng.choice(GAP_PROFILES)
            other, who, picks = self.other_speaker(used, 1)
            wanted, length = target_length * rng.uniform(0.7, 1.3), other.duration[picks[0]]
            while length < wanted and len(picks) < MAX_UTTERANCES_PER_TRACK:
                more = other.pick(rng, who, 1, low, high, exclude=set(picks))
                if not more:
                    break
                picks += more
                length += mean(gap) + other.duration[more[0]]
            others.append({"speaker": other.speakers[who], "gap": list(gap), "utts": [self.ref(other, i) for i in picks]})
            seconds = max(seconds, sum(other.duration[i] for i in picks) + gap[1] * (len(picks) - 1))
        return {
            **({"session": {"targets": own, "enrollment": enrolled}} if self.xsession else {}),
            "mode": "full", "target_speaker": corpus.speakers[speaker], "target_gap": list(target_gap),
            "targets": [{**self.ref(corpus, i), "text": corpus.rows["text"][i].strip()} for i in targets],
            "enrollment": self.ref(corpus, enrollment[0]), "interferers": others}, seconds

    def solo_pair(self, twin):
        """One short target utterance and, when ``twin``, the scene with another speaker enrolled (transcript empty)."""
        rng = self.rng
        self.pending = {}
        corpus = rng.choice(self.targets)
        while True:
            speaker = corpus.draw_speaker(rng)
            targets = corpus.pick(rng, speaker, 1, *SOLO_UTTERANCE_SECONDS)
            enrollment = corpus.pick(rng, speaker, 1, *ENROLLMENT_SECONDS, exclude=corpus.not_enrollment(speaker, targets)) if targets else None
            if enrollment:
                break
        gap = rng.choice(GAP_PROFILES)
        scene = {"mode": "full", "target_speaker": corpus.speakers[speaker], "target_gap": list(gap),
                 "targets": [{**self.ref(corpus, targets[0]), "text": corpus.rows["text"][targets[0]].strip()}],
                 "enrollment": self.ref(corpus, enrollment[0]), "interferers": []}
        paired = self.draw_twin(scene) if twin else None
        self.audio.update(self.pending)
        return scene, paired

    def handover_pair(self, twin):
        """One target utterance and one other speaker's utterance in a row; when ``twin``, the same with another speaker enrolled."""
        rng = self.rng
        self.pending = {}
        corpus = rng.choice(self.targets)
        low, high = HANDOVER_UTTERANCE_SECONDS
        while True:
            speaker = corpus.draw_speaker(rng)
            own, enrolled = self.sessions()
            targets = corpus.pick(rng, speaker, 1, low, high, session=own)
            enrollment = corpus.pick(rng, speaker, 1, *ENROLLMENT_SECONDS, exclude=corpus.not_enrollment(speaker, targets), session=enrolled) if targets else None
            if enrollment:
                break
        name = corpus.speakers[speaker]
        hard, other = None, None
        near = [(n, c) for n, c in (self.neighbors or {}).get(name, [])[: self.hard_rank] if n in self.where]
        if near and rng.random() < 0.5:
            neighbor, cosine = rng.choice(near)
            close, who = self.where[neighbor]
            picks = close.pick(rng, who, 1, low, high)
            if picks:
                hard, other = {"kind": "handover", "neighbor": neighbor, "cosine": cosine}, (close, who, picks)
        while other is None:
            close, who, _ = self.other_speaker({name}, 1)
            picks = close.pick(rng, who, 1, low, high)
            other = (close, who, picks) if picks else None
        close, who, picks = other
        scene = {**({"hard": hard} if hard else {}),
                 **({"session": {"targets": own, "enrollment": enrolled}} if self.xsession else {}),
                 "mode": "alternate", "target_speaker": name,
                 "targets": [{**self.ref(corpus, targets[0]), "text": corpus.rows["text"][targets[0]].strip()}],
                 "enrollment": self.ref(corpus, enrollment[0]),
                 "interferers": [{"speaker": close.speakers[who], "utts": [self.ref(close, picks[0])]}]}
        paired = self.draw_twin(scene) if twin else None
        self.audio.update(self.pending)
        return scene, paired

    def alt_pair(self, twin):
        """An alternate / burst / short scene and, when ``twin``, the scene with another speaker enrolled (transcript empty)."""
        modes, weights = zip(*MODES[self.language])
        scene, _ = self.scene(self.rng.choices(modes, weights)[0])
        self.pending = {}
        paired = self.draw_twin(scene) if twin else None
        self.audio.update(self.pending)
        return scene, paired

    def hard_pair(self, twin):
        """A present scene with a close neighbour of the target among the others and, when ``twin``, the scene with another speaker enrolled."""
        modes, weights = zip(*MODES[self.language])
        scene, _ = self.scene(self.rng.choices(modes, weights)[0], "present")
        self.pending = {}
        paired = self.draw_twin(scene) if twin else None
        self.audio.update(self.pending)
        return scene, paired

    def draw_twin(self, scene):
        """The scene with another speaker enrolled; half of the time one close to the real target."""
        rng = self.rng
        present = self.blocked({scene["target_speaker"], *(o["speaker"] for o in scene["interferers"])})
        kind, cosine = "random", None
        near = [(n, c) for n, c in (self.neighbors or {}).get(scene["target_speaker"], [])[: self.hard_rank]
                if n in self.where and n not in present]
        enrollment = None
        if near and rng.random() < 0.5:
            name, cosine = rng.choice(near)
            corpus, who = self.where[name]
            picks = corpus.pick(rng, who, 1, *ENROLLMENT_SECONDS)
            if picks:
                kind, enrollment = "near", (corpus, who, picks[0])
        while enrollment is None:
            corpus = rng.choice(self.targets)
            who = corpus.draw_speaker(rng)
            picks = corpus.pick(rng, who, 1, *ENROLLMENT_SECONDS) if corpus.speakers[who] not in present else None
            enrollment = (corpus, who, picks[0]) if picks else None
        corpus, who, utterance = enrollment
        timed = scene["mode"] == "full"  # alternate scenes take their gaps from the loader
        former = {"speaker": scene["target_speaker"], **({"gap": scene["target_gap"]} if timed else {}),
                  "utts": [{k: t[k] for k in ("cut_id", "start", "duration")} for t in scene["targets"]]}
        interferers = [*scene["interferers"], former]
        rng.shuffle(interferers)
        return {"mode": scene["mode"], "target_speaker": corpus.speakers[who],
                **({"target_gap": scene["target_gap"]} if timed else {}),
                "targets": [], "enrollment": self.ref(corpus, utterance), "interferers": interferers,
                "twin": {"kind": kind, **({"cosine": cosine} if cosine is not None else {})}}


def record(language, number, scene, joiner, pair=None, accent=None):
    """One audio record of a scene; ``accent`` is the enrolled speaker's accent group (--cv-accents / --cs-dialogue)."""
    base = {"dataset_id": DATASET_ID, "version": VERSION, "split": language}
    target = joiner.join(t["text"] for t in scene["targets"])
    present = bool(scene["targets"])
    # With no target, the mixture slot points at the first other speaker's first utterance.
    mixture = scene["targets"][0] if present else scene["interferers"][0]["utts"][0]
    kind = f"{scene['hard']['kind']}-" if "hard" in scene else "twin-" if "twin" in scene else ""
    labels = {"target_present": present, "schedule": scene["mode"], "n_interferers": len(scene["interferers"])}
    if scene["mode"] == "full" and present:
        labels["n_target_turns"] = len(scene["targets"])
    if "hard" in scene:
        labels["hard_cosine"] = scene["hard"]["cosine"]
    if pair is not None:
        labels["pair"] = pair
    if "session" in scene:
        labels["cross_session"] = scene["session"]["targets"] != scene["session"]["enrollment"]
    if "twin" in scene:
        labels["twin_enrollment"] = scene["twin"]["kind"]
        if "cosine" in scene["twin"]:
            labels["hard_cosine"] = scene["twin"]["cosine"]
    if accent:
        labels["accent"] = accent
    return {
        "schema_version": "audio-record/1.0", "id": f"{DATASET_ID}:{language}:{kind}{scene['mode']}:{number:07d}",
        "task": "ts_asr", "target": target, "language": language, "labels": labels,
        "hotwords": [],
        "audio_slots": [
            {"name": "enrollment", "purpose": "enrollment", "ref": {**base, **scene["enrollment"]}},
            {"name": "mixture", "purpose": "mixture", "ref": {**base, **{k: mixture[k] for k in ("cut_id", "start", "duration")}}}],
        "metadata": {"scene": {**scene, "enrollment": scene["enrollment"]}, "source_group": scene["target_speaker"]}}


def main():
    global VERSION
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--zh", type=int, default=150000)
    parser.add_argument("--en", type=int, default=100000)
    parser.add_argument("--es", type=int, default=0, help="Spanish records (Common Voice es, by accent); pass --zh 0 --en 0")
    parser.add_argument("--version", default=VERSION)
    parser.add_argument("--neighbors", type=Path, help="neighbors.json: build the hard (similar voice) version")
    parser.add_argument("--hard-rank", type=int, default=10)
    parser.add_argument("--absent-share", type=float, default=0.55)
    parser.add_argument("--multi", action="store_true", help="build the multi-turn (full) version with twins")
    parser.add_argument("--twin-share", type=float, default=0.26, help="share of the records that are twins")
    parser.add_argument("--solo", action="store_true", help="build the short solo version (one short target utterance, nobody else) with twins")
    parser.add_argument("--handover", action="store_true", help="build the handover version (target and one other speaker, one utterance each, in a row) with twins")
    parser.add_argument("--alt-twins", action="store_true", help="build the turn-taking version (alternate / burst / short) with twins")
    parser.add_argument("--hard-twins", action="store_true", help="build the hard (similar voice) version with twins")
    parser.add_argument("--xsession", action="store_true", help="KeSpeech targets enrolled from the same or the other session (zh only)")
    parser.add_argument("--magicdata", action="store_true", help="MagicData targets (zh only)")
    parser.add_argument("--ramc", action="store_true", help="MagicData-RAMC conversation targets (zh only)")
    parser.add_argument("--same-voice", type=Path, help="identities.json of ramc_voice_identities.py (required with --ramc)")
    parser.add_argument("--cv-accents", action="store_true", help="accent-labelled Common Voice targets, balanced by accent (en only)")
    parser.add_argument("--cs-dialogue", action="store_true", help="CS-Dialogue English targets: Mandarin speakers' English (en only)")
    args = parser.parse_args()
    english = args.cv_accents or args.cs_dialogue
    if sum((args.multi, args.solo, args.handover, args.alt_twins, args.hard_twins)) > 1:
        parser.error("--multi, --solo, --handover, --alt-twins and --hard-twins build different pools; pick one")
    if args.hard_twins and not args.neighbors:
        parser.error("--hard-twins needs --neighbors")
    if (args.xsession or args.magicdata or args.ramc) and (args.en or args.solo):
        parser.error("--xsession, --magicdata and --ramc build zh pools: pass --en 0, without --solo")
    if args.ramc != bool(args.same_voice):
        parser.error("--ramc needs --same-voice, and --same-voice is for --ramc")
    if english and args.zh:
        parser.error("--cv-accents and --cs-dialogue build en pools: pass --zh 0")
    if args.es and (args.zh or args.en or args.xsession or args.magicdata or args.ramc or english):
        parser.error("--es builds the Spanish pools alone: pass --zh 0 --en 0, without a zh/en target option")
    if sum((args.xsession, args.magicdata, args.ramc, args.cv_accents, args.cs_dialogue)) > 1:
        parser.error("--xsession, --magicdata, --ramc, --cv-accents and --cs-dialogue take their targets from different corpora; pick one")
    twinned = args.multi or args.solo or args.handover or args.alt_twins or args.hard_twins
    if twinned and not 0 <= args.twin_share < 1:
        parser.error("--twin-share must be in [0, 1)")
    VERSION = args.version
    args.output_dir.mkdir(parents=True, exist_ok=True)
    neighbors = json.loads(args.neighbors.read_text()) if args.neighbors else None
    same_voice = json.loads(args.same_voice.read_text()) if args.same_voice else None
    report = {}
    for language, count in (("zh", args.zh), ("en", args.en), ("es", args.es)):
        if (args.xsession or args.magicdata or args.ramc or english or args.es or language == "es") and not count:
            continue
        builder = Builder(language, random.Random(f"{SEED}:{language}:{args.version}"),
                          neighbors and neighbors[language], args.hard_rank, args.xsession, args.magicdata, args.ramc, same_voice,
                          args.cv_accents, args.cs_dialogue)
        modes, weights = zip(*MODES[language])
        records, tally = [], Counter()
        if twinned:
            twin_chance = args.twin_share / (1 - args.twin_share)  # twins per base scene
            number = 0
            while number < count:
                draw = builder.solo_pair if args.solo else builder.handover_pair if args.handover \
                    else builder.alt_pair if args.alt_twins else builder.hard_pair if args.hard_twins else builder.full_pair
                scene, paired = draw(builder.rng.random() < twin_chance)
                joiner = "" if language == "zh" else " "
                records.append(record(language, number, scene, joiner, pair=number if paired else None,
                                      accent=builder.accent.get(scene["target_speaker"])))
                tally["solo" if args.solo else f"handover-{'near' if 'hard' in scene else 'random'}" if args.handover
                      else scene["mode"] if args.alt_twins else f"present-{scene['mode']}" if args.hard_twins
                      else f"full-{len(scene['targets'])}turns"] += 1
                number += 1
                if paired and number < count:
                    records.append(record(language, number, paired, joiner, pair=number - 1,
                                          accent=builder.accent.get(paired["target_speaker"])))
                    tally[f"twin-{paired['twin']['kind']}"] += 1
                    number += 1
                if number % 25000 < 2:
                    print(language, number, flush=True)
        else:
            for number in range(count):
                hard = None
                if neighbors:
                    hard = "absent" if builder.rng.random() < args.absent_share else "present"
                if hard == "absent":
                    mode = builder.rng.choices(("alternate", "burst"), (0.35, 0.65))[0]  # no target, so no short
                else:
                    mode = builder.rng.choices(modes, weights)[0]
                scene, joiner = builder.scene(mode, hard)
                records.append(record(language, number, scene, joiner, accent=builder.accent.get(scene["target_speaker"])))
                tally[f"{hard}-{mode}" if hard else mode] += 1
                if (number + 1) % 25000 == 0:
                    print(language, number + 1, flush=True)
        with gzip.open(args.output_dir / f"records_{language}.jsonl.gz", "wt", encoding="utf-8") as stream:
            for row in records:
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
        with gzip.open(args.output_dir / f"audio_index_{language}.jsonl.gz", "wt", encoding="utf-8") as stream:
            for row in sorted(builder.audio.values(), key=lambda r: r["cut_id"]):
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
        report[language] = {"records": count, "modes": dict(tally), "audio_files": len(builder.audio)}
        if builder.accent:
            report[language]["enrolled_accents"] = dict(Counter(r["labels"].get("accent") for r in records).most_common())
        print(language, report[language], flush=True)
    (args.output_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()

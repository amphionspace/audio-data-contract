"""The 16 evaluation sets of SpoofRadar v1.0 and the 14 of Speech-DF-Arena, and where their audio comes from.

Both leaderboards score the same public speech deepfake (anti-spoofing) sets; SpoofRadar's pool is
DF-Arena's 14 plus XMAD-Bench and SpoofCeleb. The official sample lists sit unchanged under
``source/protocols/``: SpoofRadar's protocol package v1.0 (sample ids only, labels withheld) and
DF-Arena's ``protocol_files/*.csv`` (absolute paths of the maintainers' machines, with labels).

Audio is the original files, byte for byte, under ``source/<name>/``:

- ``parquet``: the SpeechAntiSpoofingBenchmarks packaging on Hugging Face keeps each original flac in
  the ``audio.bytes`` column; it is written out at the SpoofRadar sample path.
- ``hf_files``: a Hugging Face copy that stores the release unpacked; only the protocol's files are
  fetched, each checked against the sha256 the Hub lists.
- ``archive``: the original archives (Zenodo releases, via the shuohann/dfcdata Hugging Face copy or
  Zenodo itself where that copy differs) are extracted keeping their member paths.

``key`` is how a protocol entry finds its file: the last ``depth`` path components, after the
directory renames in ``aliases`` (DF-Arena and SpoofRadar spell a few directories differently).
"""

SR = "spoofradar-v1.0"
DFA = "df-arena"

HF = "hf"  # under the staging directory
DFC = "hf/shuohann__dfcdata"
SASB = "hf/SpeechAntiSpoofingBenchmarks__{}"

SOURCES = {
    "ASVspoof2019-LA": {
        "split": "asvspoof2019-la", "language": "en", "dfa": "asvspoof_2019.csv",
        "parquet": SASB.format("ASVspoof2019_LA"), "depth": 1,
        "origin": "ASVspoof 2019 LA evaluation (Zenodo 6906306), via HF SpeechAntiSpoofingBenchmarks/ASVspoof2019_LA",
    },
    "ASVspoof2021-LA": {
        "split": "asvspoof2021-la", "language": "en", "dfa": "asvspoof_2021_la.csv",
        "parquet": SASB.format("ASVspoof2021_LA"), "depth": 1,
        "origin": "ASVspoof 2021 LA evaluation (Zenodo 4837263), via HF SpeechAntiSpoofingBenchmarks/ASVspoof2021_LA",
    },
    "ASVspoof2021-DF": {
        "split": "asvspoof2021-df", "language": "en", "dfa": "asvspoof_2021_df.csv",
        "parquet": SASB.format("ASVspoof2021_DF"), "depth": 1,
        "origin": "ASVspoof 2021 DF evaluation (Zenodo 4835108), via HF SpeechAntiSpoofingBenchmarks/ASVspoof2021_DF",
    },
    "ASVspoof5-Eval": {
        "split": "asvspoof5-eval", "language": "en", "dfa": "asvspoof_2024.csv",
        "parquet": SASB.format("ASVspoof5"), "depth": 1,
        "origin": "ASVspoof 5 evaluation flac_E_eval (Zenodo 14498691), via HF SpeechAntiSpoofingBenchmarks/ASVspoof5",
    },
    "ADD2022-T1": {
        "split": "add2022-t1", "language": "zh", "dfa": "add_2022_track_1.csv",
        "archives": [f"{DFC}/add2022/ADD2022_Track1_Eval/track1test.zip"], "depth": 1,
        "origin": "ADD 2022 track 1 evaluation (Zenodo 10843991, md5 checked), via HF shuohann/dfcdata",
    },
    "ADD2022-T3": {
        "split": "add2022-t3", "language": "zh", "dfa": "add_2022_track_3.csv",
        "archives": ["zenodo/12188055/track32test.zip.001"], "depth": 1,
        "origin": "ADD 2022 track 3.2 round 2 evaluation (Zenodo 12188055); the dfcdata copy is track 3.1",
    },
    "ADD2023-R1": {
        "split": "add2023-r1", "language": "zh", "dfa": "add_2023_round_1.csv",
        "tars": [f"{DFC}/add2023/ADD2023_Track1_2_Eval_R1/track1_2-testR1.tar.gz.0*"], "depth": 1,
        "origin": "ADD 2023 track 1.2 round 1 evaluation (Zenodo 12175884, md5 checked), via HF shuohann/dfcdata",
    },
    "ADD2023-R2": {
        "split": "add2023-r2", "language": "zh", "dfa": "add_2023_round_2.csv",
        "tars": [f"{DFC}/add2023/ADD2023_Track1_2_Eval_R2/track1_2-testR2.tar.gz"], "depth": 1,
        "origin": "ADD 2023 track 1.2 round 2 evaluation (Zenodo 12176326, md5 checked), via HF shuohann/dfcdata",
    },
    "FoR": {
        "split": "for-norm", "language": "en", "dfa": "fake_or_real.csv", "dfa_split": "for-norm-dfarena",
        "archives": [f"{DFC}/the_fake_or_real/the-fake-or-real-dataset.zip"],
        "include": ["for-norm/for-norm/testing/*"], "depth": 2,
        "origin": "Fake-or-Real for-norm testing (York University), via HF shuohann/dfcdata (Kaggle packaging)",
    },
    "Codecfake": {
        "split": "codecfake", "dfa": "codecfake.csv",
        "archives": [
            *(f"{DFC}/codecfake/Codecfake_Test_Pt1/C{i}.zip" for i in (1, 2, 3, 4)),
            "zenodo/11169781/C5.zip", "zenodo/11169781/C6.zip",
            f"{DFC}/codecfake/Codecfake_Test_Pt2/C7_split.zip",
        ],
        "depth": 2,
        "origin": "Codecfake (Xie et al.) test C1-C7, version 1 (Zenodo 11169781 / 11125029, md5 checked); "
                  "C5 and C6 from Zenodo version 1, the rest via HF shuohann/dfcdata",
    },
    "LibriSeVoc": {
        "split": "librisevoc-test", "language": "en", "dfa": "librisevoc.csv", "dfa_split": "librisevoc-all",
        "archives": [f"{DFC}/librisevoc/LibriSeVoc/LibriSeVoc.zip"], "depth": 2,
        "aliases": {"parallel_wave_gan": "pwg"},
        "origin": "LibriSeVoc (Zenodo 15127251, md5 checked), via HF shuohann/dfcdata",
    },
    "DFADD": {
        "split": "dfadd", "language": "en", "dfa": "dfadd.csv",
        "archives": [f"hf/isjwdu__DFADD/DATASET_{s}.zip" for s in
                     ("GradTTS", "MatchaTTS", "NaturalSpeech2", "PflowTTS", "StyleTTS2", "VCTK_BONAFIDE")],
        "include": ["*/test/*"], "depth": 1, "stem": True,
        "origin": "DFADD test (HF isjwdu/DFADD, the authors' release); DF-Arena lists the same clips converted to wav",
    },
    "SONAR": {
        "split": "sonar", "language": "en", "dfa": "sonar.csv",
        "archives": [f"{DFC}/sonar/SONAR/SONAR_dataset-20251206T035810Z-3-001.zip"], "depth": 2,
        "aliases": {"OpenAI_fixed": "OpenAI"},
        "origin": "SONAR (archived Google Drive release), via HF shuohann/dfcdata",
    },
    "In-the-Wild": {
        "split": "in-the-wild", "language": "en", "dfa": "in_the_wild.csv",
        "archives": [f"{DFC}/release_in_the_wild/release_in_the_wild.zip"], "depth": 1,
        "origin": "In-the-Wild (deepfake-total.com release_in_the_wild.zip), via HF shuohann/dfcdata",
    },
    "XMAD-Bench": {
        "split": "xmad-bench",
        "archives": [f"hf/unibuc-cs__XMAD-Bench/{lang}.zip" for lang in ("ar", "de", "en", "es", "ro", "ru", "zh-cn")],
        "include": ["*masc/*", "*mailabs-*/*", "*voxpopuli/*", "*aishell3/*"], "depth": 3,
        "origin": "XMAD-Bench test sources (HF unibuc-cs/XMAD-Bench, the authors' release)",
    },
    "SpoofCeleb": {
        "split": "spoofceleb",
        "hf_files": {"repo": "xxuan-speech/SpoofCeleb", "prefix": "data/spoofceleb/", "path": "flac/evaluation"},
        "depth": 3,
        "origin": "SpoofCeleb evaluation flac (the jungjee/spoofceleb release unpacked, HF xxuan-speech/SpoofCeleb, "
                  "sha256 checked per file)",
    },
}

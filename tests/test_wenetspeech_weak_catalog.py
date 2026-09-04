from pathlib import Path

from audio_data_contract import load_catalog, load_view_catalog, resolve_view

ROOT = Path(__file__).parents[1]


def test_wenetspeech_weak_source_and_clean_view_are_registered():
    catalog = load_catalog(ROOT / "catalog")
    source = catalog.get("wenetspeech", "weak-source-20260904")
    clean = catalog.get("wenetspeech", "clean-weak-v1-20260904")

    assert source.artifact("train_recordings").metadata["record_count"] == 58511
    assert source.artifact("train_supervisions").metadata["record_count"] == 3222760
    assert clean.derived_from == "wenetspeech"
    assert clean.artifact("train_supervisions").metadata == {
        "record_count": 3222760,
        "pass_count": 3149292,
        "punctuated": False,
    }
    assert clean.artifact("train_supervisions_punc").metadata["punctuated"] is True
    assert clean.provenance["manual_review"] == {
        "policy": "confirm proposed transcription; answer no only when correction is needed",
        "content_review": 6,
        "replaced_review": 4,
        "proposal_confirmed": 10,
        "proposal_rejected": 0,
    }

    views = load_view_catalog(ROOT / "views", catalog)
    resolved = resolve_view(
        views,
        catalog,
        "wenetspeech/clean",
        "weak-v1-20260904",
    )
    assert resolved.key == clean.key

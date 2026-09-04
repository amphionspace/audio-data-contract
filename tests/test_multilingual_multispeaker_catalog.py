from pathlib import Path

from audio_data_contract import load_catalog


CATALOG_DIR = Path(__file__).parents[1] / "catalog"


def test_multispeaker_catalog_uses_specific_task_types():
    catalog = load_catalog(CATALOG_DIR)
    alimeeting = catalog.get("alimeeting", "openslr-119-local-20260826")

    assert set(alimeeting.tasks) == {
        "asr",
        "speaker_diarization",
        "speaker_attributed_asr",
        "overlap_speech",
        "continuous_speech_separation",
    }
    assert set(alimeeting.splits) == {"train", "dev", "test"}
    assert alimeeting.provenance["integrity"] == "verified"


def test_catalog_distinguishes_multilingual_and_multispeaker_tasks():
    catalog = load_catalog(CATALOG_DIR)

    waxal = catalog.get("waxal-asr", "hf-e91442a8989b")
    assert waxal.tasks == ("asr",)
    assert waxal.provenance["integrity"] == "verified"
    indicvoices = catalog.get("indicvoices", "hf-c96f9088f138")
    assert indicvoices.tasks == ("asr",)
    assert indicvoices.provenance["integrity"] == "verified"

    recorded = catalog.get(
        "notsofar", "hf-ba8fd0f034ce-recorded-240825.1"
    )
    simulated = catalog.get(
        "notsofar", "hf-ba8fd0f034ce-sim-v1.5-200h"
    )
    expected_meeting_tasks = {
        "asr",
        "speaker_diarization",
        "speaker_attributed_asr",
        "overlap_speech",
        "continuous_speech_separation",
    }
    assert set(recorded.tasks) == expected_meeting_tasks
    assert set(simulated.tasks) == expected_meeting_tasks
    assert recorded.provenance["integrity"] == "verified"
    assert simulated.provenance["integrity"] == "verified"

    multi_talker = catalog.get("multi-talker-sd", "hf-be2d372003fd")
    assert set(multi_talker.tasks) == expected_meeting_tasks | {
        "code_switch_asr"
    }
    assert multi_talker.provenance["integrity"] == "verified"

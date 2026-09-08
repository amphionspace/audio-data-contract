from prepare_police_v5_split import split_supervisions


def _row(i: int, speaker: str, sentence: str, provider: str = "qwen3_tts") -> dict:
    return {
        "id": f"id-{i}",
        "recording_id": f"id-{i}",
        "speaker": speaker,
        "duration": 1.0,
        "custom": {
            "sentence_id": sentence,
            "tts_provider": provider,
            "target_terms": [f"term-{i % 3}"],
            "clean": {"pass": True},
        },
    }


def test_split_is_deterministic_and_has_no_speaker_or_sentence_leakage():
    rows = []
    for i in range(100):
        rows.append(_row(i, f"speaker-{i % 20}", f"sentence-{i}"))
    # A duplicated sentence across speakers must survive in only one split.
    rows.append(_row(100, "speaker-19", "sentence-0", "cosyvoice3"))

    first, first_summary = split_supervisions(rows, "seed")
    second, second_summary = split_supervisions(rows, "seed")
    assert first == second
    assert first_summary == second_summary

    speaker_sets = [{r["speaker"] for r in first[s]} for s in ("train", "dev", "test")]
    sentence_sets = [
        {r["custom"]["sentence_id"] for r in first[s]} for s in ("train", "dev", "test")
    ]
    for i in range(3):
        for j in range(i + 1, 3):
            assert speaker_sets[i].isdisjoint(speaker_sets[j])
            assert sentence_sets[i].isdisjoint(sentence_sets[j])
    assert sum(len(rows) for rows in first.values()) <= len(rows)

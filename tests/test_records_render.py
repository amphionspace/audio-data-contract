import json

from audio_data_contract import (
    AudioExample,
    AudioRecord,
    AudioRef,
    AudioSlot,
    PromptAudio,
    PromptTemplate,
    PromptText,
    extract_audio_refs,
    render_example,
)


def _record(count=2):
    names = ("enrollment", "mixture", "context")[:count]
    return AudioRecord(
        id=f"record-{count}",
        task="ts_asr",
        audio_slots=tuple(
            AudioSlot(
                name=name,
                purpose=name,
                ref=AudioRef("demo", "1.0", "train", f"cut-{index}"),
            )
            for index, name in enumerate(names)
        ),
        target="answer",
        language="en",
        hotwords=("alpha", "beta"),
    )


def test_one_two_three_audio_order_and_round_trip():
    for count in (1, 2, 3):
        record = _record(count)
        blocks = tuple(
            block
            for slot in record.audio_slots
            for block in (PromptText(f"before-{slot.name}"), PromptAudio(slot.name))
        )
        template = PromptTemplate("ordered", "1", (blocks,))
        example = render_example(record, template, seed=3)
        assert [ref.cut_id for ref in extract_audio_refs(example)] == [
            f"cut-{index}" for index in range(count)
        ]
        assert AudioExample.from_dict(json.loads(json.dumps(example.to_dict()))) == example


def test_prompt_seed_is_deterministic_and_can_select_variants():
    template = PromptTemplate(
        "variants",
        "1",
        (
            (PromptText("A"), PromptAudio("enrollment")),
            (PromptText("B"), PromptAudio("enrollment")),
        ),
    )
    first = render_example(_record(1), template, seed=7)
    assert first == render_example(_record(1), template, seed=7)
    observed = {
        render_example(_record(1), template, seed=seed).metadata["prompt_template"][
            "variant"
        ]
        for seed in range(20)
    }
    assert observed == {0, 1}

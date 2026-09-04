import json
from importlib.resources import files

import pytest
from jsonschema import Draft202012Validator, ValidationError

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
from audio_data_contract.errors import ContractError


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


def _schema(name):
    return json.loads(
        files("audio_data_contract").joinpath("schemas", name).read_text()
    )


def test_record_and_example_round_trips_match_json_schemas():
    record = _record(2)
    example = render_example(record, PromptTemplate("one", "1", ((PromptText("A"),),)))

    Draft202012Validator(_schema("audio-record-1.0.json")).validate(record.to_dict())
    Draft202012Validator(_schema("audio-example-1.0.json")).validate(
        example.to_dict()
    )


@pytest.mark.parametrize(
    "change",
    [
        lambda data: data.update(target=123),
        lambda data: data.update(language=123),
        lambda data: data["audio_slots"][0]["ref"].update(channel=["1", 2.9]),
    ],
)
def test_record_rejects_non_schema_types(change):
    data = _record(1).to_dict()
    change(data)

    with pytest.raises(ValidationError):
        Draft202012Validator(_schema("audio-record-1.0.json")).validate(data)
    with pytest.raises(ContractError):
        AudioRecord.from_dict(data)


def test_record_rejects_nonfinite_times():
    data = _record(1).to_dict()
    data["audio_slots"][0]["ref"]["start"] = float("inf")

    with pytest.raises(ContractError, match="must be finite"):
        AudioRecord.from_dict(data)


def test_example_rejects_non_string_text_and_invalid_audio_ref():
    base = render_example(
        _record(1), PromptTemplate("one", "1", ((PromptText("A"), PromptAudio("enrollment")),))
    ).to_dict()
    base["messages"][0]["content"][0]["text"] = 123
    with pytest.raises(ValidationError):
        Draft202012Validator(_schema("audio-example-1.0.json")).validate(base)
    with pytest.raises(ContractError, match="text_content.text must be a string"):
        AudioExample.from_dict(base)

    base = render_example(
        _record(1), PromptTemplate("one", "1", ((PromptAudio("enrollment"),),))
    ).to_dict()
    base["messages"][0]["content"][0]["ref"]["unknown"] = True
    with pytest.raises(ValidationError):
        Draft202012Validator(_schema("audio-example-1.0.json")).validate(base)
    with pytest.raises(ContractError, match="unknown fields"):
        AudioExample.from_dict(base)

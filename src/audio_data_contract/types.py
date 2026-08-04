"""Strict, JSON-serializable public contract types."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any, Mapping, Sequence

from .errors import ContractError

CATALOG_SCHEMA_VERSION = "dataset-catalog/1.0"
RECORD_SCHEMA_VERSION = "audio-record/1.0"
EXAMPLE_SCHEMA_VERSION = "audio-example/1.0"


def _mapping(value: Any, where: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractError(f"{where} must be an object")
    return value


def _fields(
    data: Mapping[str, Any],
    *,
    required: set[str],
    optional: set[str],
    where: str,
) -> None:
    missing = required - set(data)
    unknown = set(data) - required - optional
    if missing:
        raise ContractError(f"{where} missing required fields: {sorted(missing)}")
    if unknown:
        raise ContractError(f"{where} has unknown fields: {sorted(unknown)}")


def _non_empty(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{where} must be a non-empty string")
    return value


def _strings(value: Any, where: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise ContractError(f"{where} must be an array")
    result = tuple(_non_empty(item, f"{where}[]") for item in value)
    if len(result) != len(set(result)):
        raise ContractError(f"{where} must not contain duplicates")
    return result


def _portable_path(value: Any, where: str) -> str:
    path = _non_empty(value, where)
    if "\\" in path:
        raise ContractError(f"{where} must use POSIX separators")
    parsed = PurePosixPath(path)
    if parsed.is_absolute() or ".." in parsed.parts:
        raise ContractError(f"{where} must be relative and may not contain '..'")
    return str(parsed)


def _json_object(value: Any, where: str) -> dict[str, Any]:
    if value is None:
        return {}
    return dict(_mapping(value, where))


@dataclass(frozen=True)
class ArtifactRef:
    name: str
    kind: str
    root_alias: str
    relative_path: str
    expected_bytes: int | None = None
    sha256: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _non_empty(self.name, "artifact.name"))
        object.__setattr__(self, "kind", _non_empty(self.kind, "artifact.kind"))
        object.__setattr__(
            self, "root_alias", _non_empty(self.root_alias, "artifact.root_alias")
        )
        object.__setattr__(
            self,
            "relative_path",
            _portable_path(self.relative_path, "artifact.relative_path"),
        )
        if self.expected_bytes is not None and self.expected_bytes < 0:
            raise ContractError("artifact.expected_bytes must be non-negative")
        if self.sha256 is not None:
            digest = self.sha256.lower()
            if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                raise ContractError("artifact.sha256 must be a 64-character hex digest")
            object.__setattr__(self, "sha256", digest)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "name": self.name,
            "kind": self.kind,
            "root_alias": self.root_alias,
            "relative_path": self.relative_path,
        }
        if self.expected_bytes is not None:
            data["expected_bytes"] = self.expected_bytes
        if self.sha256 is not None:
            data["sha256"] = self.sha256
        if self.metadata:
            data["metadata"] = self.metadata
        return data

    @classmethod
    def from_dict(cls, value: Any) -> "ArtifactRef":
        data = _mapping(value, "artifact")
        _fields(
            data,
            required={"name", "kind", "root_alias", "relative_path"},
            optional={"expected_bytes", "sha256", "metadata"},
            where="artifact",
        )
        return cls(
            name=data["name"],
            kind=data["kind"],
            root_alias=data["root_alias"],
            relative_path=data["relative_path"],
            expected_bytes=data.get("expected_bytes"),
            sha256=data.get("sha256"),
            metadata=_json_object(data.get("metadata"), "artifact.metadata"),
        )


@dataclass(frozen=True)
class DatasetSpec:
    dataset_id: str
    version: str
    languages: tuple[str, ...]
    tasks: tuple[str, ...]
    artifacts: tuple[ArtifactRef, ...]
    splits: dict[str, dict[str, Any]]
    aliases: tuple[str, ...] = ()
    provenance: dict[str, Any] = field(default_factory=dict)
    derived_from: str | None = None
    recipe_parameters: dict[str, Any] = field(default_factory=dict)
    schema_version: str = CATALOG_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != CATALOG_SCHEMA_VERSION:
            raise ContractError(
                f"unsupported dataset schema_version: {self.schema_version!r}"
            )
        object.__setattr__(self, "dataset_id", _non_empty(self.dataset_id, "dataset_id"))
        object.__setattr__(self, "version", _non_empty(self.version, "version"))
        if not self.languages:
            raise ContractError("languages may not be empty")
        if not self.tasks:
            raise ContractError("tasks may not be empty")
        names = [artifact.name for artifact in self.artifacts]
        if len(names) != len(set(names)):
            raise ContractError(f"duplicate artifact names in {self.dataset_id}@{self.version}")
        known = set(names)
        for split_name, split in self.splits.items():
            _non_empty(split_name, "split name")
            split_data = _mapping(split, f"split {split_name}")
            for key, artifact_name in split_data.items():
                if key.endswith("_artifact") and artifact_name not in known:
                    raise ContractError(
                        f"split {split_name} references unknown artifact {artifact_name!r}"
                    )

    @property
    def key(self) -> str:
        return f"{self.dataset_id}@{self.version}"

    def artifact(self, name: str) -> ArtifactRef:
        for artifact in self.artifacts:
            if artifact.name == name:
                return artifact
        raise ContractError(f"unknown artifact {name!r} for {self.key}")

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "schema_version": self.schema_version,
            "dataset_id": self.dataset_id,
            "version": self.version,
            "languages": list(self.languages),
            "tasks": list(self.tasks),
            "aliases": list(self.aliases),
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
            "splits": self.splits,
            "provenance": self.provenance,
        }
        if self.derived_from is not None:
            data["derived_from"] = self.derived_from
        if self.recipe_parameters:
            data["recipe_parameters"] = self.recipe_parameters
        return data

    @classmethod
    def from_dict(cls, value: Any) -> "DatasetSpec":
        data = _mapping(value, "dataset")
        _fields(
            data,
            required={
                "schema_version",
                "dataset_id",
                "version",
                "languages",
                "tasks",
                "artifacts",
                "splits",
            },
            optional={"aliases", "provenance", "derived_from", "recipe_parameters"},
            where="dataset",
        )
        artifacts = data["artifacts"]
        if not isinstance(artifacts, Sequence) or isinstance(artifacts, str):
            raise ContractError("dataset.artifacts must be an array")
        splits = _mapping(data["splits"], "dataset.splits")
        return cls(
            schema_version=data["schema_version"],
            dataset_id=data["dataset_id"],
            version=data["version"],
            languages=_strings(data["languages"], "dataset.languages"),
            tasks=_strings(data["tasks"], "dataset.tasks"),
            aliases=_strings(data.get("aliases", []), "dataset.aliases"),
            artifacts=tuple(ArtifactRef.from_dict(item) for item in artifacts),
            splits={name: dict(_mapping(split, f"split {name}")) for name, split in splits.items()},
            provenance=_json_object(data.get("provenance"), "dataset.provenance"),
            derived_from=data.get("derived_from"),
            recipe_parameters=_json_object(
                data.get("recipe_parameters"), "dataset.recipe_parameters"
            ),
        )


@dataclass(frozen=True)
class AudioRef:
    dataset_id: str
    version: str
    split: str
    cut_id: str
    channel: int | tuple[int, ...] | None = None
    start: float | None = None
    duration: float | None = None
    purpose: str | None = None

    def __post_init__(self) -> None:
        for name in ("dataset_id", "version", "split", "cut_id"):
            object.__setattr__(self, name, _non_empty(getattr(self, name), name))
        if self.start is not None and self.start < 0:
            raise ContractError("audio ref start must be non-negative")
        if self.duration is not None and self.duration <= 0:
            raise ContractError("audio ref duration must be positive")

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "dataset_id": self.dataset_id,
            "version": self.version,
            "split": self.split,
            "cut_id": self.cut_id,
        }
        if self.channel is not None:
            data["channel"] = list(self.channel) if isinstance(self.channel, tuple) else self.channel
        if self.start is not None:
            data["start"] = self.start
        if self.duration is not None:
            data["duration"] = self.duration
        if self.purpose is not None:
            data["purpose"] = self.purpose
        return data

    @classmethod
    def from_dict(cls, value: Any) -> "AudioRef":
        data = _mapping(value, "audio_ref")
        _fields(
            data,
            required={"dataset_id", "version", "split", "cut_id"},
            optional={"channel", "start", "duration", "purpose"},
            where="audio_ref",
        )
        channel = data.get("channel")
        if isinstance(channel, list):
            channel = tuple(int(item) for item in channel)
        return cls(
            dataset_id=data["dataset_id"],
            version=data["version"],
            split=data["split"],
            cut_id=data["cut_id"],
            channel=channel,
            start=data.get("start"),
            duration=data.get("duration"),
            purpose=data.get("purpose"),
        )


@dataclass(frozen=True)
class AudioSlot:
    name: str
    ref: AudioRef
    purpose: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _non_empty(self.name, "audio_slot.name"))

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"name": self.name, "ref": self.ref.to_dict()}
        if self.purpose is not None:
            data["purpose"] = self.purpose
        return data

    @classmethod
    def from_dict(cls, value: Any) -> "AudioSlot":
        data = _mapping(value, "audio_slot")
        _fields(data, required={"name", "ref"}, optional={"purpose"}, where="audio_slot")
        return cls(
            name=data["name"],
            ref=AudioRef.from_dict(data["ref"]),
            purpose=data.get("purpose"),
        )


@dataclass(frozen=True)
class AudioRecord:
    id: str
    task: str
    audio_slots: tuple[AudioSlot, ...]
    target: str
    language: str = "N/A"
    labels: dict[str, Any] = field(default_factory=dict)
    hotwords: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = RECORD_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != RECORD_SCHEMA_VERSION:
            raise ContractError(f"unsupported record schema_version: {self.schema_version!r}")
        object.__setattr__(self, "id", _non_empty(self.id, "record.id"))
        object.__setattr__(self, "task", _non_empty(self.task, "record.task"))
        if not self.audio_slots:
            raise ContractError("record.audio_slots may not be empty")
        names = [slot.name for slot in self.audio_slots]
        if len(names) != len(set(names)):
            raise ContractError("record.audio_slots names must be unique")

    def slot(self, name: str) -> AudioSlot:
        for slot in self.audio_slots:
            if slot.name == name:
                return slot
        raise ContractError(f"record {self.id!r} has no audio slot {name!r}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "task": self.task,
            "audio_slots": [slot.to_dict() for slot in self.audio_slots],
            "target": self.target,
            "language": self.language,
            "labels": self.labels,
            "hotwords": list(self.hotwords),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, value: Any) -> "AudioRecord":
        data = _mapping(value, "audio_record")
        _fields(
            data,
            required={"schema_version", "id", "task", "audio_slots", "target"},
            optional={"language", "labels", "hotwords", "metadata"},
            where="audio_record",
        )
        slots = data["audio_slots"]
        if not isinstance(slots, Sequence) or isinstance(slots, str):
            raise ContractError("audio_record.audio_slots must be an array")
        return cls(
            schema_version=data["schema_version"],
            id=data["id"],
            task=data["task"],
            audio_slots=tuple(AudioSlot.from_dict(item) for item in slots),
            target=str(data["target"]),
            language=str(data.get("language", "N/A")),
            labels=_json_object(data.get("labels"), "audio_record.labels"),
            hotwords=_strings(data.get("hotwords", []), "audio_record.hotwords"),
            metadata=_json_object(data.get("metadata"), "audio_record.metadata"),
        )


@dataclass(frozen=True)
class TextContent:
    text: str
    type: str = "text"

    def to_dict(self) -> dict[str, Any]:
        return {"type": "text", "text": self.text}


@dataclass(frozen=True)
class AudioContent:
    ref: AudioRef
    slot: str
    purpose: str | None = None
    type: str = "audio"

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "type": "audio",
            "slot": self.slot,
            "ref": self.ref.to_dict(),
        }
        if self.purpose is not None:
            data["purpose"] = self.purpose
        return data


Content = TextContent | AudioContent


def content_from_dict(value: Any) -> Content:
    data = _mapping(value, "content")
    content_type = data.get("type")
    if content_type == "text":
        _fields(data, required={"type", "text"}, optional=set(), where="text content")
        return TextContent(text=str(data["text"]))
    if content_type == "audio":
        _fields(
            data,
            required={"type", "slot", "ref"},
            optional={"purpose"},
            where="audio content",
        )
        return AudioContent(
            slot=data["slot"],
            ref=AudioRef.from_dict(data["ref"]),
            purpose=data.get("purpose"),
        )
    raise ContractError(f"unsupported content type: {content_type!r}")


@dataclass(frozen=True)
class Message:
    role: str
    content: tuple[Content, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "role", _non_empty(self.role, "message.role"))

    def to_dict(self) -> dict[str, Any]:
        return {"role": self.role, "content": [item.to_dict() for item in self.content]}

    @classmethod
    def from_dict(cls, value: Any) -> "Message":
        data = _mapping(value, "message")
        _fields(data, required={"role", "content"}, optional=set(), where="message")
        content = data["content"]
        if not isinstance(content, Sequence) or isinstance(content, str):
            raise ContractError("message.content must be an array")
        return cls(role=data["role"], content=tuple(content_from_dict(item) for item in content))


@dataclass(frozen=True)
class AudioExample:
    id: str
    task: str
    messages: tuple[Message, ...]
    labels: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = EXAMPLE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != EXAMPLE_SCHEMA_VERSION:
            raise ContractError(f"unsupported example schema_version: {self.schema_version!r}")
        object.__setattr__(self, "id", _non_empty(self.id, "example.id"))
        object.__setattr__(self, "task", _non_empty(self.task, "example.task"))
        if not self.messages:
            raise ContractError("example.messages may not be empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "task": self.task,
            "messages": [message.to_dict() for message in self.messages],
            "labels": self.labels,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, value: Any) -> "AudioExample":
        data = _mapping(value, "audio_example")
        _fields(
            data,
            required={"schema_version", "id", "task", "messages"},
            optional={"labels", "metadata"},
            where="audio_example",
        )
        messages = data["messages"]
        if not isinstance(messages, Sequence) or isinstance(messages, str):
            raise ContractError("audio_example.messages must be an array")
        return cls(
            schema_version=data["schema_version"],
            id=data["id"],
            task=data["task"],
            messages=tuple(Message.from_dict(item) for item in messages),
            labels=_json_object(data.get("labels"), "audio_example.labels"),
            metadata=_json_object(data.get("metadata"), "audio_example.metadata"),
        )


@dataclass(frozen=True)
class PromptText:
    text: str


@dataclass(frozen=True)
class PromptAudio:
    slot: str


PromptBlock = PromptText | PromptAudio


@dataclass(frozen=True)
class PromptTemplate:
    template_id: str
    version: str
    user_variants: tuple[tuple[PromptBlock, ...], ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "template_id", _non_empty(self.template_id, "template_id"))
        object.__setattr__(self, "version", _non_empty(self.version, "template.version"))
        if not self.user_variants or any(not variant for variant in self.user_variants):
            raise ContractError("template.user_variants may not be empty")

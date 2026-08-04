"""Portable contracts for shared audio datasets."""

from .catalog import DatasetCatalog, load_catalog, resolve_artifact, validate_catalog
from .records import load_examples, load_records, write_examples, write_records
from .render import extract_audio_refs, render_example
from .roots import load_roots
from .state import (
    DatasetState,
    DownloadState,
    inspect_download,
    load_state,
    write_state_atomic,
)
from .types import (
    ArtifactRef,
    AudioContent,
    AudioExample,
    AudioRecord,
    AudioRef,
    AudioSlot,
    DatasetSpec,
    Message,
    PromptAudio,
    PromptTemplate,
    PromptText,
    TextContent,
)

__all__ = [
    "ArtifactRef",
    "AudioContent",
    "AudioExample",
    "AudioRecord",
    "AudioRef",
    "AudioSlot",
    "DatasetCatalog",
    "DatasetSpec",
    "DatasetState",
    "DownloadState",
    "Message",
    "PromptAudio",
    "PromptTemplate",
    "PromptText",
    "TextContent",
    "extract_audio_refs",
    "inspect_download",
    "load_catalog",
    "load_examples",
    "load_records",
    "load_roots",
    "load_state",
    "render_example",
    "resolve_artifact",
    "validate_catalog",
    "write_examples",
    "write_records",
    "write_state_atomic",
]

__version__ = "0.1.0"

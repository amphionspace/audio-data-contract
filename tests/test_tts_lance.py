"""DATA-TTS-UNIFIED releases: pinned manifest/snapshot and AudioRecord streaming."""

import hashlib
import json

import pytest

from audio_data_contract import ArtifactRef, DatasetCatalog, DatasetSpec, Split
from audio_data_contract.errors import ContractError
from audio_data_contract.tts_lance import iter_samples, open_release, read_audio

lance = pytest.importorskip("lance")
pa = pytest.importorskip("pyarrow")


def write_release(root, texts):
    release = root / "demo" / "v0.1"
    release.mkdir(parents=True)
    n = len(texts)
    table = pa.table(
        {
            "sample_id": [f"s{i}" for i in range(n)],
            "text": texts,
            "text_kind": [None if t is None else "source_transcript" for t in texts],
            "language": ["zh"] * (n - 1) + [None],
            "speaker_id": ["spk"] * n,
            "speaker_scope": ["demo"] * n,
            "duration_seconds": [1.0] * n,
            "sample_rate": pa.array([16000] * n, pa.int32()),
            "channels": pa.array([1] * n, pa.int16()),
            "audio": [{"bytes": f"wav{i}".encode(), "path": f"{i}.wav"} for i in range(n)],
        }
    )
    dataset = lance.write_dataset(table, str(release / "samples.lance"))
    manifest = {
        "status": "complete",
        "rows": n,
        "lance_version": dataset.version,
        "table_path": "samples.lance",
    }
    path = release / "manifest.json"
    path.write_text(json.dumps(manifest))
    return path, manifest


def catalog_for(path, manifest, **overrides):
    artifact = {
        "name": "samples",
        "kind": "tts-lance-release",
        "root_alias": "tts",
        "relative_path": "demo/v0.1/manifest.json",
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "metadata": {"lance_version": manifest["lance_version"], "rows": manifest["rows"]},
    }
    artifact.update(overrides)
    spec = DatasetSpec(
        dataset_id="demo",
        version="tts-unified-v0.1",
        languages=("zh",),
        tasks=("tts", "asr"),
        artifacts=(ArtifactRef.from_dict(artifact),),
        splits={"train": Split({"samples": ("samples",)})},
    )
    return DatasetCatalog([spec])


def test_streams_records_with_text_and_audio(tmp_path):
    path, manifest = write_release(tmp_path, ["你好", None, "世界", "再见"])
    catalog = catalog_for(path, manifest)
    release = open_release(catalog, "demo", "tts-unified-v0.1", "samples", {"tts": tmp_path})

    rows = list(iter_samples(release))
    assert [record.id for record, _ in rows] == ["s0", "s2", "s3"]
    record, audio = rows[0]
    assert (record.target, record.language, audio) == ("你好", "zh", b"wav0")
    assert record.slot("audio").ref.to_dict() == {
        "dataset_id": "demo",
        "version": "tts-unified-v0.1",
        "split": "train",
        "cut_id": "s0",
    }
    assert record.metadata["text_kind"] == "source_transcript"
    assert rows[-1][0].language == "N/A"
    assert [r.id for r, a in iter_samples(release, filter="language = 'zh'", with_audio=False)] == ["s0", "s2"]
    shards = [
        {r.id for r, _ in iter_samples(release, shard=i, num_shards=2)} for i in range(2)
    ]
    assert shards[0] | shards[1] == {"s0", "s2", "s3"} and not shards[0] & shards[1]
    assert read_audio(release, ["s3", "s1"]) == {"s3": b"wav3", "s1": b"wav1"}
    with pytest.raises(ContractError, match="unknown sample IDs"):
        read_audio(release, ["missing"])


def test_rejects_changed_manifest_or_snapshot(tmp_path):
    path, manifest = write_release(tmp_path, ["a", "b"])
    roots = {"tts": tmp_path}
    stale = catalog_for(path, manifest, sha256="0" * 64)
    with pytest.raises(ContractError, match="sha256 differs"):
        open_release(stale, "demo", "tts-unified-v0.1", "samples", roots)
    wrong = catalog_for(path, manifest, metadata={"lance_version": 1, "rows": 3})
    with pytest.raises(ContractError, match="rows differs"):
        open_release(wrong, "demo", "tts-unified-v0.1", "samples", roots)


def test_catalog_requires_pins():
    base = {"name": "s", "kind": "tts-lance-release", "root_alias": "r", "relative_path": "m.json"}
    with pytest.raises(ContractError, match="sha256"):
        ArtifactRef.from_dict({**base, "metadata": {"lance_version": 1, "rows": 1}})
    with pytest.raises(ContractError, match="lance_version"):
        ArtifactRef.from_dict({**base, "sha256": "0" * 64, "metadata": {"rows": 1}})

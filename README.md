# audio-data-contract

`audio-data-contract` is the dependency-light data boundary shared by icefall
recipes and open-audio-llm. It separates five concerns:

1. versioned dataset identity and portable artifact locations;
2. machine-local root resolution;
3. mutable download/preparation state;
4. stable ordered audio sample facts (`AudioRecord`); and
5. rendered multimodal model messages (`AudioExample`).

The core package uses only the Python standard library and requires Python
3.10 or newer. It deliberately does not import Lhotse, PyTorch, ms-swift, or
vLLM.

## Root configuration

Catalog entries use `root_alias` plus a relative path. A machine-local JSON
file resolves aliases:

```json
{
  "legacy_asr": "/data/asr",
  "multilingual": "/data/multilingual",
  "managed_fast": "/data/managed",
  "managed_bulk": "/bulk/audio"
}
```

Pass it explicitly to the API/CLI or set `AUDIO_DATA_ROOTS_FILE`. There are no
hard-coded machine paths in the package.

## CLI

```bash
audio-data-contract validate-catalog catalog/datasets.jsonl
audio-data-contract validate-records records.jsonl.gz
audio-data-contract resolve catalog/datasets.jsonl DATASET VERSION ARTIFACT \
  --roots roots.json
```

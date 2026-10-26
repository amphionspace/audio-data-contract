# Diarization benchmark: frozen local evaluation slices

This registration freezes the six local slices requested for
`amphion-diarization/diarization-benchmark@20261019`. It does not register model
scores or modify the AmphionEval benchmark. A consumer must bind a new benchmark
revision to these catalog identities and agree on its scoring protocol.

| Local slice | Dataset ID | Version | Recordings |
|---|---|---|---:|
| aishell4 | aishell4 | diarization-benchmark-v1-20261021 | 20 |
| alimeeting | alimeeting | diarization-benchmark-v1-20261021 | 20 |
| alimeeting_2023test | alimeeting | diarization-benchmark-v1-20261021-2023test | 20 |
| ami_near | ami | diarization-benchmark-v1-20261021 | 20 |
| ramc | magicdata_ramc | diarization-benchmark-v1-20261021 | 43 |
| voxconverse | voxconverse | diarization-benchmark-v1-20261021 | 232 |

All splits are `test`, task `speaker_diarization`. Each slice exposes a View named
`<local_slice>/diarization-benchmark@diarization-benchmark-v1-20261021`.
The extra 16 AMI far-field recordings in the original 371-record manifest are excluded.

## Storage and format

Configure `diarization_benchmark` in an untracked `roots.json` to the published
snapshot root. Catalog paths and audio-index paths are relative to this alias.
The data provider's local roots file resolves the snapshot in the current data
workspace under `registration/snapshots/diarization-benchmark-v1-20261021`.
Other machines must mount or copy that snapshot and configure their own root.
No remote/shared-storage availability beyond this host is claimed.

Each slice includes:

- `records.jsonl`: standard AudioRecord, one whole recording per record.
  `labels.segments` holds `{start, duration, speaker_id}` from the reference RTTM.
  Speaker IDs are local to each recording, not global person identities.
  `metadata.reference_rttm` gives a root alias and relative path.
  The original manifest row is retained as provenance; its historical absolute
  paths are evidence only and must not be used for audio resolution.
- `audio-index.jsonl`: maps `cut_id` to the frozen WAV, with measured frame count,
  sample rate, channel count, and duration.
- `files.jsonl`: SHA-256 and byte count for every WAV and RTTM, plus its source
  relative path. `audio/` and `rttm/` contain byte-preserving copies.
- `test.jsonl`: compatibility manifest with absolute paths to this snapshot.
  Portable consumers use AudioRecord and audio-index instead.

The snapshot also contains the combined 355-row `test.jsonl` and `validation.json`.
All snapshot files are mode 0444 and directories 0555 after atomic publication.
These permissions protect against accidental edits, not privileged writes.
Published files must not be edited in place; changes require a new version.

## Provenance and limits

This is a verified local artifact snapshot with **inferred historical lineage**.
`ready` means the local registered artifacts exist and validate; it does not mean
upstream official release equivalence or scoring parity has been established.

- AISHELL-4: original manifest says test, extraction of source channel 0, and
  `lhotse_supervisions`. C01/C02 in the recording name is not treated as proof
  of the selected waveform channel. Official split completeness is unconfirmed.
- AliMeeting: source paths say `Test_Ali/Test_Ali_far`, extraction of channel 0,
  and `lhotse_supervisions`. Conversion/merging/filtering details remain unconfirmed.
- AliMeeting 2023: local 20-record slice. M2MeT 2.0 equivalence, selection procedure,
  microphone channel and RTTM lineage remain unconfirmed.
- AMI near: local 20-record slice. Headset mixing/channel preparation and official
  scenario-only test equivalence remain unconfirmed.
- RAMC: local legacy test manifest, mono audio reused, RTTM from
  `lhotse_supervisions`. Official completeness and conversion rules unconfirmed.
- VoxConverse: local 232-record slice. Release v0.3 and original-versus-edited RTTM
  remain unconfirmed. Language is `und` because these records do not declare it.

The registration preserves RTTM bytes and does not merge, filter, clamp, or
otherwise repair annotations. No UEM is supplied. The request reports historical
collar=0; scorer version, no-UEM extent and overlap policy are unconfirmed.
Do not assume equivalence to ae's default collar=0.25 or its default scoring extent.
No train/test disjointness claim is made.

`voxconverse:vylyk` audio and reference are included. No prediction or rerun score
is supplied, and the reported SIGABRT is not resolved by this data registration.

## Reproduction and checks

Use `scripts/diarization/register_benchmark.py --source DATA_ROOT --output NEW_SNAPSHOT
--repo CONTRACT_CHECKOUT` with soundfile and the contract package installed. The
script refuses to overwrite an existing snapshot. It preserves existing roots.json
entries, rejects a conflicting diarization_benchmark alias before copying audio,
and writes the merged configuration atomically. It checks all audio headers,
RTTM syntax and speaker counts, and reports any out-of-bounds segments without
silently changing the reference. This snapshot had zero bounds warnings.

```bash
audio-data-contract validate-catalog catalog
audio-data-contract validate-views views catalog
audio-data-contract check-registration catalog aishell4 diarization-benchmark-v1-20261021 --roots roots.json --sample 355
audio-data-contract generate-overview --check
```

Repeat `check-registration` for each identity in the table. Artifact hashes and
record counts are recorded in the catalog. Check WAV/RTTM hashes against each
`files.jsonl` when copying the snapshot to another host.

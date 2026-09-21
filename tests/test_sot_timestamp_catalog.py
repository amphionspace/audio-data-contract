from pathlib import Path

from audio_data_contract import load_catalog, load_view_catalog

ROOT = Path(__file__).resolve().parents[1]
DATASET = 'sot_multispeaker_zh_en'
SOURCE = 'synthetic-v2-20260915'
TIMED = 'synthetic-v2-timestamps-v1-20260919'


def test_timestamp_registration_preserves_source_and_exact_version_lineage():
    catalog = load_catalog(ROOT / 'catalog')
    source, timed = catalog.get(DATASET, SOURCE), catalog.get(DATASET, TIMED)
    assert source.provenance['preparation_status'] == 'ready'
    assert {part: value['statistics']['records'] for part, value in source.splits.items()} == {
        'train': 2000000, 'dev': 10000, 'test': 10000}
    assert timed.derived_from == DATASET
    assert timed.recipe_parameters['source'] == {'dataset_id': DATASET, 'version': SOURCE}
    assert timed.recipe_parameters['audio_policy'] == 'reuse_source_mixture_bytes'
    assert timed.recipe_parameters['fixed_eval_membership'] == 'preserve_all_dev_and_test_records'
    assert 'no word-level timestamps' in source.provenance['label_scope']
    assert timed.recipe_parameters['target_format'] == 'aligned_utterance_timestamps_v1'


def test_incomplete_timestamp_version_cannot_masquerade_as_ready_records():
    catalog = load_catalog(ROOT / 'catalog')
    timed = catalog.get(DATASET, TIMED)
    assert timed.provenance['preparation_status'] == 'building'
    assert timed.provenance['ready_for_training'] is False
    assert {a.kind for a in timed.artifacts} == {'alignment-plan', 'dataset-state'}
    for split in timed.splits.values():
        assert split['preparation_status'] == 'building'
        assert not any(key in split for key in ('records_artifact', 'records_artifacts', 'cuts_artifact'))
        assert 'duration_hours' not in split['statistics'] and 'records' not in split['statistics']
    for view in load_view_catalog(ROOT / 'views', catalog):
        assert (view.result.dataset_id, view.result.version) != (DATASET, TIMED)

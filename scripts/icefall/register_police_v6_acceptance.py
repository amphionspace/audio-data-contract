"""Register the producer's test-only 205-command V6 acceptance release."""
import argparse
import copy
import gzip
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'src'))
from audio_data_contract import load_catalog
from audio_data_contract.catalog import verify_artifact_file


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--amphion-data', type=Path, required=True)
    args = p.parse_args()
    repo = Path(__file__).resolve().parents[2]
    root = args.amphion_data.resolve()/'results/police-v6-acceptance-205-20260921'
    coverage = json.loads((root/'coverage.json').read_text())
    plan = json.loads((root/'plan.json').read_text())
    assert coverage['source_commands'] == 205 and coverage['minimum_voices'] >= 10
    artifacts = []
    for name, kind, path in [
        ('test_recordings','lhotse-recordings',root/'manifests/police_synthetic_recordings_test.jsonl.gz'),
        ('test_supervisions','lhotse-supervisions',root/'manifests/police_synthetic_supervisions_test.jsonl.gz'),
        ('coverage','json-metadata',root/'coverage.json'),
        ('plan','json-metadata',root/'plan.json'),
    ]:
        item = dict(name=name,kind=kind,root_alias='amphion_data',relative_path=str(path.relative_to(args.amphion_data.resolve())),expected_bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        if name.startswith('test_'): item['metadata']={'record_count':coverage['accepted']}
        artifacts.append(item)
    with gzip.open(root/'manifests/police_synthetic_supervisions_test.jsonl.gz','rt') as f:
        sups=[json.loads(line) for line in f]
    with gzip.open(root/'manifests/police_synthetic_recordings_test.jsonl.gz','rt') as f:
        recs=[json.loads(line) for line in f]
    assert len(sups)==len(recs)==coverage['accepted']
    assert len({r['id'] for r in recs})==len(recs)
    assert {r['id'] for r in recs}=={r['id'] for r in sups}
    for r in recs:
        assert r['sampling_rate']==16000 and Path(r['sources'][0]['source']).stat().st_size>44
    stats=dict(recordings=len(recs),supervisions=len(sups),duration_hours=coverage['duration_hours'],duration_basis='sum_of_recording_durations',source_commands=205,minimum_voices_per_command=coverage['minimum_voices'],speakers=len({r['speaker'] for r in sups}))
    spec=dict(schema_version='dataset-catalog/1.0',dataset_id='police_v6_acceptance_205',version='v6-acceptance-20260921',languages=['zh'],tasks=['asr'],artifacts=artifacts,
        splits={'test':dict(recordings_artifact='test_recordings',supervisions_artifact='test_supervisions',statistics=stats)},
        provenance=dict(source='AmphionData synthetic speech pipeline',status='ready',source_requirements={'filename':'警言警语-V6.0.txt','sha256':plan['source_sha256'],'section':'20260915新增'},evaluation_limitations=plan['policy'],human_review=False),
        recipe_parameters=dict(tts_provider='qwen3_tts',sample_rate=16000,channels=1))
    view=copy.deepcopy(spec);view['version']='icefall-20260908';view['splits']['test']['icefall']={'use_punc':False};view['recipe_parameters']['icefall']={'language':'zh'}
    view['provenance'].update(source_dataset_id=spec['dataset_id'],source_version=spec['version'])
    target=repo/'catalog/police_v6_acceptance_205.jsonl'
    if target.exists(): raise FileExistsError(target)
    target.write_text(''.join(json.dumps(s,ensure_ascii=False)+'\n' for s in [spec,view]))
    catalog=load_catalog(repo/'catalog')
    for a in catalog.get(spec['dataset_id'],spec['version']).artifacts:
        verify_artifact_file(a,args.amphion_data/a.relative_path)
    print(json.dumps(stats,ensure_ascii=False))

if __name__=='__main__': main()

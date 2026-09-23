"""Extend an existing portable ASR handoff with the registered V6 test release."""
import argparse
import csv
import gzip
import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
import wave
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from audio_data_contract import load_catalog, resolve_artifact, verify_artifact_file


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(4*1024*1024),b''):h.update(block)
    return h.hexdigest()


def rows(path):
    with (gzip.open(path,'rt') if path.suffix=='.gz' else path.open()) as f:
        return [json.loads(line) for line in f if line.strip()]


def jsonl(path, values):
    path.write_text(''.join(json.dumps(v,ensure_ascii=False)+'\n' for v in values))


def tsv(path, fields, values):
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,delimiter='\t',extrasaction='ignore',lineterminator='\n')
        w.writeheader();w.writerows(values)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base-archive',type=Path,required=True)
    p.add_argument('--base-sha256',required=True)
    p.add_argument('--work',type=Path,required=True)
    p.add_argument('--amphion-data',type=Path,required=True)
    args=p.parse_args()
    work=args.work.resolve();work.mkdir(parents=True,exist_ok=True)
    repo=Path(__file__).resolve().parents[1]
    assert digest(args.base_archive)==args.base_sha256, 'Base archive checksum differs'
    root=work/'asr_testsets_handoff_20260821'
    assert not root.exists(), 'Use an empty work directory'
    subprocess.run(['tar','--zstd','-xf',str(args.base_archive.resolve()),'-C',str(work)],check=True)
    original=rows(root/'manifest.jsonl')
    base_sums={name:sha for sha,name in (line.split('  ',1) for line in (root/'SHA256SUMS').read_text().splitlines())}
    with ThreadPoolExecutor(max_workers=8) as pool:
        actual=list(pool.map(digest,(root/name for name in base_sums)))
    assert all(value==base_sums[name] for name,value in zip(base_sums,actual)), 'Base internal checksums differ'
    print('Verified original archive and',len(base_sums),'internal files',flush=True)
    name='police_v6_acceptance_205';version='v6-acceptance-20260921'
    catalog=load_catalog(repo/'catalog');spec=catalog.get(name,version)
    paths={a.name:resolve_artifact(catalog,name,version,a.name,{'amphion_data':args.amphion_data}) for a in spec.artifacts}
    for a in spec.artifacts:verify_artifact_file(a,paths[a.name])
    sups=rows(paths['test_supervisions']);recs={r['id']:r for r in rows(paths['test_recordings'])}
    assert len(sups)==3773 and set(recs)=={s['recording_id'] for s in sups}
    assert name not in {r['dataset_id'] for r in original}
    sources=[Path(recs[s['recording_id']]['sources'][0]['source']) for s in sups]
    with ThreadPoolExecutor(max_workers=8) as pool: hashes=list(pool.map(digest,sources))
    known={r['audio_sha256']:r for r in original}
    added=[]
    for sup,source,sha in zip(sups,sources,hashes):
        audio_path=f'audio/{sha[:2]}/{sha}.wav';text_path=audio_path[:-4]+'.txt'
        target=root/audio_path;target.parent.mkdir(exist_ok=True)
        if sha in known:assert known[sha]['text']==sup['text'], 'Audio/transcript conflict'
        else:
            shutil.copyfile(source,target);(root/text_path).write_text(sup['text']+'\n')
        with wave.open(str(target)) as w:
            rate,channels,bits,duration=w.getframerate(),w.getnchannels(),w.getsampwidth()*8,w.getnframes()/w.getframerate()
        assert rate==16000 and channels==1 and abs(duration-sup['duration'])<0.001
        row={'schema_version': 1,'dataset_id': name,'item_id': sup['id'],'audio_path': audio_path,'text_path': text_path,
                 'text': sup['text'],'lang': 'zh','sample_rate_hz': rate,'channels': channels,'sample_width_bits': bits,
                 'duration_sec': duration,'audio_sha256': sha,'audio_bytes': target.stat().st_size,'audio_origin': 'synthetic_tts',
                 'scope': 'current','category': 'police_v6_commands','source_kind': 'registered_asr_test',
                 'source_manifest': f'source_manifests/{name}/test_supervisions.jsonl.gz','source_dataset': name,
                 'source_version': version,'source_split': 'test','speaker': sup['speaker'],'target_terms': sup['custom'].get('target_terms',[]),
                 'source_metadata': sup['custom']}
        known[sha]=row;added.append(row)
    combined=original+added
    assert len({(r['dataset_id'],r['item_id']) for r in combined})==len(combined)
    group=root/'datasets'/name;group.mkdir()
    jsonl(group/'manifest.jsonl',added)
    tsv(group/'pairs.tsv',['item_id','audio_path','text_path','text'],added)
    source_dir=root/'source_manifests'/name;source_dir.mkdir()
    for key,path in paths.items():
        shutil.copyfile(path,source_dir/(key+'.jsonl.gz' if key.startswith('test_') else key+'.json'))
    shutil.copyfile(repo/'catalog'/f'{name}.yaml',source_dir/'catalog.yaml')
    (group/'README.md').write_text('''# 警言警语 V6 新增 205 条指令验收\n\n3,773 条合格合成音频，205/205 条指令，每条至少 10 个音色。仅 test split。\npairs.tsv 的音频及文本路径相对交付包根目录。真值来自 contract supervision。\n原文和读法变体可能在训练中出现，不能当作未见指令泛化测试；独立 ASR 自动质检，无人工听审。\nsource_manifests/police_v6_acceptance_205 保存注册信息、来源和逐指令覆盖。\n''')
    jsonl(root/'manifest.jsonl',combined)
    with (root/'manifest.tsv').open() as f:fields=next(csv.reader(f,delimiter='\t'))
    tsv(root/'manifest.tsv',fields,combined)
    summary=json.loads((root/'SUMMARY.json').read_text())
    unique={r['audio_sha256']:r for r in combined}
    summary.update(datasets=len({r['dataset_id'] for r in combined}),pair_memberships=len(combined),unique_audio=len(unique),
                   unique_audio_bytes=sum(r['audio_bytes'] for r in unique.values()),unique_audio_hours=sum(r['duration_sec'] for r in unique.values())/3600,
                   updated_utc=datetime.now(timezone.utc).isoformat(),base_archive_sha256=args.base_sha256,
                   added_dataset=name,added_pairs=len(added))
    for field,key in [('channels','channels'),('sample_rates','sample_rate_hz'),('sample_width_bits','sample_width_bits')]:
        summary[field]=dict(Counter(str(r[key]) for r in unique.values()))
    (root/'SUMMARY.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    dataset_rows=[]
    for dataset in sorted({r['dataset_id'] for r in combined}):
        subset=[r for r in combined if r['dataset_id']==dataset]
        uq={r['audio_sha256']:r for r in subset}
        dataset_rows.append({'dataset_id': dataset,'pair_count': len(subset),'unique_audio_count': len(uq),'duration_hours': f"{sum(r['duration_sec'] for r in uq.values())/3600:.6f}"})
    tsv(root/'DATASET_SUMMARY.tsv',['dataset_id','pair_count','unique_audio_count','duration_hours'],dataset_rows)
    readme=(root/'README.md').read_text().replace('14,281',f"{len(combined):,}").replace('数据集：18','数据集：19').replace('约 21.76 小时',f"约 {summary['unique_audio_hours']:.2f} 小时")
    marker='\n## 已知缺口'
    readme=readme.replace(marker,f"\n| {name} | current | {len(added)} | {len({r['audio_sha256'] for r in added})} | {sum(r['duration_sec'] for r in added)/3600:.2f} | V6 新增 205 条指令，独立 ASR 自动质检 |\n\n2026-09-21 更新：加入 `police_v6_acceptance_205`，原有 18 个数据集保留。新增集的使用边界见其 README。\n"+marker)
    (root/'README.md').write_text(readme)
    # Check all packaged relationships before compressing, without changing original rows.
    assert combined[:len(original)]==original
    assert len({r['source_metadata']['source_metadata']['id'] for r in added})==205
    for r in combined:
        assert (root/r['audio_path']).is_file() and (root/r['text_path']).read_text().strip()==r['text'].strip()
    files=sorted(p for p in root.rglob('*') if p.is_file() and p.name!='SHA256SUMS')
    with ThreadPoolExecutor(max_workers=8) as pool:checks=list(pool.map(digest,files))
    expected={str(p.relative_to(root)):sha for p,sha in zip(files,checks)}
    (root/'SHA256SUMS').write_text(''.join(f'{sha}  {name}\n' for name,sha in expected.items()))
    archive=work/args.base_archive.name
    print('Packing',len(combined),'pairs;',len(expected),'files',flush=True)
    subprocess.run(['tar','-I','zstd -T4 -3','-cf',str(archive),'-C',str(work),root.name],check=True)
    # Verify compressed output, including every audio and all updated metadata.
    actual={}
    process=subprocess.Popen(['zstd','-dc',str(archive)],stdout=subprocess.PIPE)
    with tarfile.open(fileobj=process.stdout,mode='r|') as tar:
        for member in tar:
            if not member.isfile():continue
            relative=str(Path(member.name).relative_to(root.name))
            assert relative not in actual, 'Duplicate tar member'
            h=hashlib.sha256()
            stream=tar.extractfile(member)
            for block in iter(lambda stream=stream:stream.read(4*1024*1024),b''):h.update(block)
            actual[relative]=h.hexdigest()
    assert process.wait()==0
    assert actual.pop('SHA256SUMS')==digest(root/'SHA256SUMS')
    assert actual==expected,'Compressed archive verification failed'
    archive_hash=digest(archive)
    checksum=f'{archive_hash}  {archive.name}\n'
    (work/(archive.name+'.sha256')).write_text(checksum)
    upload_summary=work/'summary';upload_summary.mkdir()
    for name in ['CONFLICTS.jsonl','DATASET_SUMMARY.tsv','MANUAL_REVIEW.tsv','README.md','SOURCE_ALIASES.tsv','SUMMARY.json','TEXT_ONLY_OR_MISSING_AUDIO.tsv']:
        shutil.copyfile(root/name,upload_summary/name)
    (upload_summary/'ARCHIVE_SHA256.txt').write_text(checksum)
    result={'archive': str(archive),'sha256': archive_hash,'bytes': archive.stat().st_size,'original_pairs': len(original),'added_pairs': len(added),'total_pairs': len(combined),'datasets': summary['datasets'],'source_commands': 205,'verified_archive_files': len(expected)+1,'original_rows_unchanged': True}
    (work/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False),flush=True)

if __name__=='__main__':main()

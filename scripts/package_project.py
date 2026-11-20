"""Create a source/data/results delivery archive without credentials or runtime databases."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import zipfile
from pathlib import Path
from dotenv import dotenv_values

ROOT=Path(__file__).resolve().parent.parent

def build(destination):
    files=[]
    skip_parts={'.git','.venv','__pycache__','.pytest_cache','.preparation-tools','node_modules'}
    for folder in ['.github','app','scripts','tests','docs','eval','data/demo','data/evaluation','data/manifests','data/licenses','upstream/khoj','reproducibility']:
        for p in (ROOT/folder).rglob('*'):
            rel=p.relative_to(ROOT)
            if p.is_file() and not skip_parts.intersection(rel.parts) and p.name not in ('.env','.env.local','proposal-extracted.txt') and p.suffix not in ('.zip','.pyc'):
                files.append(p)
    # Only canonical collections from the frozen task files, not interrupted cache leftovers.
    collections=set()
    for name in ['frames-dev','frames-test','hotpotqa-dev','hotpotqa-test']:
        path=ROOT/'data/evaluation'/f'{name}.jsonl'
        if path.exists():
            for line in path.read_text(encoding='utf-8').splitlines():
                if line.strip(): collections.add(json.loads(line)['collection_id'])
    for cid in sorted(collections):
        files.extend(p for p in (ROOT/'data/corpus'/cid).rglob('*') if p.is_file())
    for name in ['README.md','LICENSE','THIRD_PARTY_NOTICES.md','pyproject.toml','requirements-lock.txt','requirements-report.txt','pytest.ini','.gitignore','.gitattributes','.env.example','Start-Khoj-Research-Lab.cmd','Stop-Khoj-Research-Lab.cmd']:
        files.append(ROOT/name)
    files=sorted(set(files))
    # Fail closed if the configured secret appears in any shareable file.
    secrets=set()
    settings = dict(dotenv_values(ROOT/'.env')) if (ROOT/'.env').exists() else {}
    # Scan both file and process credentials, including quoted dotenv values.
    candidates = [v for k,v in settings.items() if any(t in k.upper() for t in ('API_KEY','TOKEN','SECRET'))]
    candidates += [v for k,v in os.environ.items() if any(t in k.upper() for t in ('API_KEY','TOKEN','SECRET'))]
    for candidate in candidates:
        if candidate and len(candidate)>15 and candidate not in {'replace-with-your-own-api-key', 'local-not-a-secret'}:
            secrets.add(candidate.encode())
    manifest=[]
    destination.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(destination,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for p in files:
            data=p.read_bytes()
            if any(secret in data for secret in secrets):
                raise RuntimeError(f'Credential detected in shareable path: {p.relative_to(ROOT)}; archive not ready')
            rel=p.relative_to(ROOT).as_posix()
            manifest.append({'path':rel,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
            archive.writestr('khoj-personal-research/'+rel,data)
        archive.writestr('khoj-personal-research/DELIVERY-MANIFEST.json',json.dumps({
            'files':manifest,'excluded':['.env','.venv','runtime','downloaded model weights','raw downloads','noncanonical corpus caches'],
            'upstream_commit':'ae229ca894c0b80ad84664afcfdde523b5e87057'},ensure_ascii=False,indent=2))
    result={'archive':str(destination),'files':len(files),'bytes':destination.stat().st_size,
            'sha256':hashlib.sha256(destination.read_bytes()).hexdigest(),'credential_scan':'passed'}
    destination.with_suffix('.manifest.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--output',type=Path,default=ROOT.parent/'outputs/Khoj-Research-Lab/Khoj-Research-Lab-Source.zip')
    a=p.parse_args()
    build(a.output)

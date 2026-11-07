"""Install the verified local candidate, preserving the previous desktop model."""
import argparse,hashlib,json,shutil
from pathlib import Path

ROOT=Path(__file__).resolve().parent

def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--candidate',default='candidate-v4');p.add_argument('--backup-name',default='previous-model-v3')
    args=p.parse_args()
    if any(Path(x).name!=x for x in (args.candidate,args.backup_name)):raise ValueError('Expected directory names')
    source=ROOT/'artifacts/desktop-200950'/args.candidate;models=ROOT/'models'
    report=json.loads((ROOT/'artifacts/desktop-200950/final-evaluation.json').read_text())
    if report['errors']:raise ValueError('Candidate has unresolved reviewed-card errors')
    backup=ROOT/'artifacts/desktop-200950'/args.backup_name
    backup.mkdir(exist_ok=False)
    preserved={p.name:digest(p) for p in models.glob('pokerstars.*') if p.is_file()}
    metadata=json.loads((source/'pokerstars-nine.manifest.json').read_text())
    if report.get('model_sha256')!=metadata['files'][0]['sha256']:
        raise ValueError('Evaluation does not match this candidate')
    for item in metadata['files']:
        if digest(source/item['local'])!=item['sha256']:raise ValueError('Candidate checksum mismatch')
    names=['pokerstars-nine.onnx','pokerstars-nine.classes.json','pokerstars-nine.manifest.json']
    before={name:digest(models/name) for name in names}
    for name in names:shutil.copy2(models/name,backup/name)
    staging=models/'pokerstars-nine-symbols-200950-staging'
    shutil.copytree(source/'pokerstars-nine-symbols',staging)
    (models/'pokerstars-nine-symbols').rename(backup/'pokerstars-nine-symbols')
    staging.rename(models/'pokerstars-nine-symbols')
    for name in names:
        temporary=models/(name+'.200950-tmp');shutil.copy2(source/name,temporary);temporary.replace(models/name)
    for name,value in preserved.items():
        if digest(models/name)!=value:raise RuntimeError('Independent browser profile changed')
    result=dict(before=before,after={name:digest(models/name) for name in names},
                browser_profile_unchanged=preserved,backup=str(backup.relative_to(ROOT)),
                reviewed_evaluation=report['counts'])
    (ROOT/'artifacts/desktop-200950/promotion.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()

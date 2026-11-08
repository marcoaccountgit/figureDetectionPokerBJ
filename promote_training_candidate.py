"""Install a locally validated candidate, keeping its prior model and symbol bank."""
import argparse, hashlib, json, shutil
from pathlib import Path

ROOT=Path(__file__).resolve().parent

def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--candidate',type=Path,required=True)
    p.add_argument('--report',type=Path,required=True)
    p.add_argument('--legacy-report',type=Path,required=True)
    args=p.parse_args()
    candidate=args.candidate.resolve();report=json.loads(args.report.read_text())
    legacy=json.loads(args.legacy_report.read_text())
    if report['regressions'] or legacy['errors']:raise ValueError('Candidate has runtime regressions')
    for result in report['summary'].values():
        if result['after']['wrong_accepted'] or result['after']['visible_correct'] < result['before']['visible_correct']:
            raise ValueError('Accuracy regressed')
    before=sum(r['before']['mean_ms']*r['before']['frames'] for r in report['summary'].values())
    after=sum(r['after']['mean_ms']*r['after']['frames'] for r in report['summary'].values())
    if after>before:raise ValueError('Measured mean recognition time regressed')
    model=candidate/'pokerstars-nine.onnx'
    if digest(model)!=report['candidate_sha256']:raise ValueError('Report does not match candidate weights')
    if legacy['model_sha256']!=digest(model):raise ValueError('Legacy report does not match weights')
    manifest=json.loads((candidate/'pokerstars-nine.manifest.json').read_text())
    for item in manifest['files']:
        if digest(candidate/item['local'])!=item['sha256']:raise ValueError('Candidate checksum mismatch')
    installed=ROOT/'models'
    browser_hash=digest(installed/'pokerstars.onnx')
    bank_name='pokerstars-nine-symbols-212305-'+report['candidate_sha256'][:8]
    bank=installed/bank_name
    if bank.exists():raise ValueError('Candidate symbol bank already installed')
    shutil.copytree(candidate/manifest['symbol_references'],bank)
    manifest.update(symbol_references=bank_name,
        runtime_validation_report=str(args.report.resolve().relative_to(ROOT)),
        legacy_runtime_validation_report=str(args.legacy_report.resolve().relative_to(ROOT)))
    # Preserve the running process: it already has its network and glyphs in RAM.
    # A fresh launch reads this manifest and the new independent glyph bank.
    for item in manifest['files']:
        staged=installed/(item['local']+'.212305.new')
        shutil.copy2(candidate/item['local'],staged)
        staged.replace(installed/item['local'])
    staged=installed/'pokerstars-nine.manifest.json.212305.new'
    staged.write_text(json.dumps(manifest,indent=2))
    staged.replace(installed/'pokerstars-nine.manifest.json')
    if digest(installed/'pokerstars.onnx')!=browser_hash:raise ValueError('Browser weights changed unexpectedly')
    record=dict(installed_sha256=digest(installed/'pokerstars-nine.onnx'),symbol_bank=bank_name,
        previous_model='artifacts/desktop-212305/previous-model',browser_weights_unchanged=True)
    (candidate.parent/'promotion.json').write_text(json.dumps(record,indent=2))
    print(json.dumps(record,indent=2))

if __name__=='__main__':main()

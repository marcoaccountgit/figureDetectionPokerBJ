"""Install only a candidate with matching successful new and legacy reports."""
import hashlib,json,shutil
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def preserve_desktop_six(previous,installed):
    """Pin the previously validated desktop weights without changing nine."""
    old_manifest=json.loads((previous/'pokerstars-nine.manifest.json').read_text())
    six={key:old_manifest[key] for key in ('license','symbol_references','crop','crop_reference_size')}
    six.update(profile='pokerstars-desktop-six',runtime_profile='pokerstars-nine',
        source_backup=str(previous),source_training_run=old_manifest.get('training_run'),files=[])
    for extension in ('onnx','classes.json'):
        source=previous/('pokerstars-nine.'+extension)
        destination=installed/('pokerstars-desktop-six.'+extension)
        staged=destination.with_name(destination.name+'.135641.new')
        shutil.copy2(source,staged);staged.replace(destination)
        six['files'].append(dict(local=destination.name,sha256=digest(destination)))
    (installed/'pokerstars-desktop-six.manifest.json').write_text(json.dumps(six,indent=2))


def main():
    root=Path('artifacts/nine-135641');candidate=root/'candidate'
    new=json.loads((root/'evaluation-validated.json').read_text())
    legacy=json.loads((root/'legacy-validated.json').read_text())
    original=json.loads((root/'original-nine-validated.json').read_text())
    observer=json.loads((root/'original-observer-validated.json').read_text())
    model=candidate/'pokerstars-nine.onnx';checksum=digest(model)
    if new['model_sha256']!=checksum or legacy['candidate_sha256']!=checksum:
        raise ValueError('Reports do not describe these weights')
    for name,checksum_code in new['runtime_sha256'].items():
        if digest(Path(name))!=checksum_code:raise ValueError('Runtime changed after validation')
    if legacy['regressions']:raise ValueError('Legacy regressions remain')
    if original['regressions'] or original['summary']['after']['wrong'] or observer['regressions']:
        raise ValueError('Original nine-seat regression remains')
    for results in legacy['summary'].values():
        if results['after']['wrong_accepted'] or results['after']['visible_correct']<results['before']['visible_correct']:
            raise ValueError('Legacy accuracy regressed')
    for key,counts in new['summary'].items():
        if key.startswith('after-'):
            if counts['wrong_cards'] or counts['wrong_seats']:raise ValueError('Incorrect confident reading remains')
            if key.endswith('-test') and counts['exact_seats']!=counts['frames']:
                raise ValueError('Held-out opponent counts incomplete')
    manifest=json.loads((candidate/'pokerstars-nine.manifest.json').read_text())
    for item in manifest['files']:
        if digest(candidate/item['local'])!=item['sha256']:raise ValueError('Candidate checksum mismatch')
    installed=Path('models')
    browser_checksum=digest(installed/'pokerstars.onnx')
    # Keep the established six-seat desktop network independent of nine-seat
    # fine-tuning. Its runtime geometry is still the desktop geometry.
    previous=root/'previous-model'
    preserve_desktop_six(previous,installed)
    bank=manifest['symbol_references']
    if not (installed/bank).exists():shutil.copytree(candidate/bank,installed/bank)
    for path in (candidate/bank).rglob('*.png'):
        if digest(path)!=digest(installed/bank/path.relative_to(candidate/bank)):
            raise ValueError('Installed glyph bank differs from validated bank')
    manifest.pop('symbol_reference_deduplication',None)
    dataset_manifest=root/'dataset/manifest.json'
    dataset=json.loads(dataset_manifest.read_text())
    manifest['dataset_manifest']=dict(source=dataset['source'],source_sha256=dataset['sha256'],
        annotation_revision=dataset['annotation_revision'],manifest_path=str(dataset_manifest),
        manifest_sha256=digest(dataset_manifest),replay_preserved=True,
        new_train_samples=sum(r['split']=='train' for r in dataset['real']),
        new_validation_samples=sum(r['split']=='val' for r in dataset['real']))
    manifest.update(runtime_validation_report=str(root/'evaluation-validated.json'),
        legacy_runtime_validation_report=str(root/'legacy-validated.json'),
        opponent_training_provenance='assets/table-nine/variants/135641-provenance.json',
        runtime_code_sha256=new['runtime_sha256'],desktop_six_profile='pokerstars-desktop-six')
    for item in manifest['files']:
        staged=installed/(item['local']+'.135641.new')
        shutil.copy2(candidate/item['local'],staged)
        staged.replace(installed/item['local'])
    staged=installed/'pokerstars-nine.manifest.json.135641.new'
    staged.write_text(json.dumps(manifest,indent=2))
    staged.replace(installed/'pokerstars-nine.manifest.json')
    if browser_checksum!=digest(installed/'pokerstars.onnx'):raise ValueError('Browser weights changed')
    record=dict(installed_sha256=checksum,previous_model=str(root/'previous-model'),
        new_report=str(root/'evaluation-validated.json'),legacy_report=str(root/'legacy-validated.json'),
        symbol_bank=bank,browser_weights_unchanged=True)
    (root/'promotion.json').write_text(json.dumps(record,indent=2))
    print(json.dumps(record,indent=2))


if __name__=='__main__':main()

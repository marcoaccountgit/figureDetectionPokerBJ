"""Fine-tune a pinned 52-class YOLO11n in the isolated GPU training environment."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import urllib.request

ROOT = Path(__file__).parent.resolve()
CONFIG = ROOT / 'artifacts/training-config'
CONFIG.mkdir(parents=True, exist_ok=True)
os.environ.setdefault('YOLO_CONFIG_DIR', str(CONFIG))
os.environ['YOLO_AUTOINSTALL'] = 'false'
os.environ['YOLO_OFFLINE'] = 'true'

BASE_MODEL = {
    'repository': 'shrimantasatpati/yolov11_playing_cards_detection',
    'revision': '7b8e6a71f0392544624dfc0b67730e679ece19ee',
    'sha256': '2617719f994cbb91e974c9f3c3a7f63e83a5cd0d9004342636099c79260260b6',
    'file': 'detect/yolo11n_playing_cards/weights/best.pt'}


def ensure_checkpoint(path):
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix('.part')
        url = (f"https://huggingface.co/{BASE_MODEL['repository']}/resolve/"
               f"{BASE_MODEL['revision']}/{BASE_MODEL['file']}")
        try:
            with urllib.request.urlopen(url, timeout=60) as response, temporary.open('wb') as output:
                shutil.copyfileobj(response, output)
            with temporary.open('rb') as stream:
                if hashlib.file_digest(stream, 'sha256').hexdigest() != BASE_MODEL['sha256']:
                    raise ValueError('Downloaded base checkpoint checksum mismatch')
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
    with path.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != BASE_MODEL['sha256']:
            raise ValueError('Unexpected base checkpoint: verify the documented source revision')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, default=ROOT / 'artifacts/table-195129/dataset-v2')
    parser.add_argument('--checkpoint', type=Path, default=ROOT / 'artifacts/table-195129/base-yolo11n.pt')
    parser.add_argument('--epochs', type=int, default=20)
    parser.add_argument('--warm-start', type=Path, help='Local trusted checkpoint to continue training')
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'models')
    parser.add_argument('--run-name', default='pokerstars-195129')
    parser.add_argument('--learning-rate', type=float, default=.001)
    args = parser.parse_args()
    if args.epochs < 1:
        parser.error('epochs must be positive')
    if args.warm_start:
        if not args.warm_start.is_file():
            parser.error('warm-start checkpoint does not exist')
        with args.warm_start.open('rb') as stream:
            warm_digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    else:
        ensure_checkpoint(args.checkpoint)
    import torch
    from ultralytics import YOLO
    from training_validator import DeploymentTrainer
    print('Torch:', torch.__version__, 'CUDA:', torch.cuda.is_available(), flush=True)
    if not torch.cuda.is_available():
        raise RuntimeError('GPU training environment unavailable; install the documented CUDA wheels')
    torch.set_num_threads(4)
    model = YOLO(str(args.warm_start or args.checkpoint))
    names = json.loads((ROOT / 'models/lgd-cards-gen3.classes.json').read_text())
    if list(model.names.values()) != names:
        raise ValueError(f'Base checkpoint class order differs: {model.names}')
    print('GPU:', torch.cuda.get_device_name(0), flush=True)
    model.train(trainer=DeploymentTrainer, data=str(args.dataset / 'data.yaml'), epochs=args.epochs, imgsz=640,
                batch=32, device=0, workers=0, cache='ram', freeze=10,
                optimizer='AdamW', lr0=args.learning_rate, lrf=.1, patience=6, seed=195129,
                warmup_bias_lr=args.learning_rate if args.warm_start else .1,
                warmup_epochs=1 if args.warm_start else 3,
                deterministic=True, amp=True, mosaic=0, mixup=0, copy_paste=0,
                fliplr=0, flipud=0, degrees=0, translate=.04, scale=.12,
                hsv_h=0, hsv_s=.1, hsv_v=.15, project=str(ROOT / 'artifacts/training'),
                name=args.run_name, plots=False, save=True, exist_ok=False)
    best = Path(model.trainer.best)
    trained = YOLO(str(best))
    export = Path(trained.export(format='onnx', imgsz=640, opset=12, dynamic=False,
                                simplify=False, half=False, device='cpu', batch=1))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    target = args.output_dir / 'pokerstars.onnx'
    shutil.copy2(export, target)
    classes = args.output_dir / 'pokerstars.classes.json'
    classes.write_text(json.dumps(names), encoding='utf-8')
    from prepare_table_dataset import export_symbol_references
    export_symbol_references(args.dataset, args.output_dir / 'pokerstars-symbols')
    spec = json.loads((ROOT / 'datasets/table-195129.json').read_text())
    width, height = spec['size']
    manifest = {
        'profile': 'pokerstars', 'license': 'AGPL-3.0 (Ultralytics derivative)',
        'symbol_references': 'pokerstars-symbols',
        'source_checkpoint': BASE_MODEL,
        'crop': [value / (width if i % 2 == 0 else height) for i, value in enumerate(spec['crop'])],
        'crop_reference_size': [width, height],
        'dataset_manifest': json.loads((args.dataset / 'manifest.json').read_text()),
        'training_run': str(best.parent.parent.relative_to(ROOT)),
        'epochs_requested': args.epochs, 'files': []}
    for path in (target, classes):
        with path.open('rb') as stream:
            checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
        manifest['files'].append({'local': path.name, 'sha256': checksum})
    # Keep the large per-frame inventory beside the run, not in the runtime manifest.
    manifest['dataset_manifest'].pop('real', None)
    if args.warm_start:
        manifest['warm_start'] = {'file': str(args.warm_start), 'sha256': warm_digest}
    rows = list(csv.DictReader((best.parent.parent / 'results.csv').open()))
    # Ultralytics overwrites best.pt on ties as well as improvements.
    best_row = max(reversed(rows), key=lambda row: float(row['deployment/f1']))
    manifest['epochs_completed'] = len(rows)
    manifest['best_epoch'] = int(best_row['epoch'])
    manifest['deployment_validation'] = {key: float(value) for key, value in best_row.items()
                                         if key.startswith('deployment/')}
    (args.output_dir / 'pokerstars.manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print('Exported candidate:', target, flush=True)


if __name__ == '__main__':
    main()

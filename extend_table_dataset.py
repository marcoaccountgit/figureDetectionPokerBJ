"""Append reviewed hands and stable adjacent frames without altering replay splits."""
import argparse
from collections import Counter
import json
from pathlib import Path
import shutil

from card_detector import cv2
from download_model import file_digest
from prepare_table_dataset import annotations_for, stable_indices, write_sample


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('video_directory', type=Path)
    parser.add_argument('--annotations', type=Path, nargs='+', required=True)
    parser.add_argument('--replay', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    data = json.loads((args.replay / 'data.yaml').read_text())
    names = data['names']
    sources = []
    hands = {}
    for path in args.annotations:
        spec = json.loads(path.read_text())
        video = args.video_directory / spec['source']
        if file_digest(video) != spec['source_sha256']:
            raise ValueError(f'Video differs from reviewed source: {video}')
        for entry in spec['frames']:
            key = (spec['source_sha256'], entry['hand'])
            if entry['split'] not in ('train', 'val', 'test'):
                raise ValueError('Unknown dataset split')
            if key in hands and hands[key] != entry['split']:
                raise ValueError('A reviewed hand crosses dataset splits')
            hands[key] = entry['split']
        sources.append((path, video, spec))
    args.output.mkdir(parents=True, exist_ok=False)
    for kind in ('images', 'labels'):
        for split in ('train', 'val', 'test'):
            shutil.copytree(args.replay / kind / split, args.output / kind / split)
    added = []
    skipped = 0
    for path, video, spec in sources:
        cap = cv2.VideoCapture(str(video))
        if not cap.isOpened() or [round(cap.get(3)), round(cap.get(4))] != spec['size']:
            cap.release()
            raise ValueError('Video dimensions differ from reviewed annotations')
        x1, y1, x2, y2 = spec['crop']
        if not (0 <= x1 < x2 <= spec['size'][0] and 0 <= y1 < y2 <= spec['size'][1]):
            cap.release()
            raise ValueError('Invalid annotation crop')
        try:
            for entry in spec['frames']:
                cap.set(cv2.CAP_PROP_POS_MSEC, entry['time']*1000)
                ok, reference = cap.read()
                if not ok:
                    raise ValueError('Cannot decode reviewed reference')
                labels = annotations_for(entry, spec, names)
                for offset in ((-.4, -.2, 0, .2, .4) if entry['split'] == 'train' else (0,)):
                    t = entry['time']+offset
                    if t < 0:
                        continue
                    cap.set(cv2.CAP_PROP_POS_MSEC, t*1000)
                    ok, frame = cap.read()
                    if not ok or (offset and not stable_indices(reference, frame, entry, spec)):
                        skipped += 1
                        continue
                    stem = f'extra_{spec["source_sha256"][:12]}_{t:.1f}'
                    if any((args.output / 'images' / split / (stem+'.jpg')).exists()
                           for split in ('train', 'val', 'test')):
                        raise ValueError(f'Duplicate sample: {stem}')
                    write_sample(args.output, entry['split'], stem, frame[y1:y2, x1:x2], labels)
                    added.append({'file': stem, 'source_sha256': spec['source_sha256'], 'time': t,
                                  'hand': entry['hand'], 'split': entry['split'],
                                  'codes': entry['board']+entry['hole']})
        finally:
            cap.release()
    data['path'] = args.output.resolve().as_posix()
    (args.output / 'data.yaml').write_text(json.dumps(data, indent=2))
    real_codes = set()
    for path in (args.output / 'labels/train').glob('*.txt'):
        if not path.stem.startswith('synthetic_'):
            real_codes.update(names[int(row.split()[0])] for row in path.read_text().splitlines())
    manifest = {'replay_manifest_sha256': file_digest(args.replay / 'manifest.json'),
                'sources': [{'source': v.name, 'source_sha256': s['source_sha256'],
                             'annotation': p.name, 'annotation_sha256': file_digest(p)} for p,v,s in sources],
                'protocol': 'Additional reviewed prefix training hands; old validation/test and synthetic replay unchanged. Adjacent frames accepted only when annotated indices are virtually unchanged.',
                'added_frames_by_split': dict(Counter(e['split'] for e in added)),
                'skipped_unstable_neighbours': skipped,
                'images_by_split': {split: len(list((args.output / 'images' / split).glob('*.jpg')))
                                    for split in ('train', 'val', 'test')},
                'real_training_codes': sorted(real_codes),
                'missing_real_training_codes': sorted(set(names)-real_codes),
                'real': added}
    (args.output / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    print(json.dumps({k:v for k,v in manifest.items() if k!='real'}, indent=2))


if __name__ == '__main__':
    main()

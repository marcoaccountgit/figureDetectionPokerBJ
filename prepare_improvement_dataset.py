"""Add reviewed early hands and real ten glyphs to the existing training replay."""
import argparse
from collections import Counter
import json
from pathlib import Path
import shutil

from PIL import Image
from card_detector import cv2, np
from download_model import file_digest
from prepare_table_dataset import add_synthetic_replay, annotations_for, stable_indices, write_sample

ROOT = Path(__file__).resolve().parent


def glyph_mask(image):
    """Keep all substantial components, including both digits of ten."""
    mask = (cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) < 170).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    keep = [i for i in range(1, count) if stats[i, cv2.CC_STAT_AREA] >= 8
            and stats[i, cv2.CC_STAT_HEIGHT] >= 5]
    selected = np.isin(labels, keep).astype(np.uint8)
    ys, xs = np.nonzero(selected)
    if not len(xs):
        raise ValueError('Empty training glyph')
    return Image.fromarray(selected[ys.min():ys.max()+1, xs.min():xs.max()+1]*255)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('video_directory', type=Path)
    parser.add_argument('--replay', type=Path, default=ROOT / 'artifacts/table-195129/dataset-v2')
    parser.add_argument('--output', type=Path, default=ROOT / 'artifacts/table-improvement/dataset')
    args = parser.parse_args()
    names = json.loads((args.replay / 'data.yaml').read_text())['names']
    sources = []
    for stamp in ('211955', '213508'):
        spec_path = ROOT / f'datasets/table-{stamp}.json'
        spec = json.loads(spec_path.read_text())
        video = args.video_directory / spec['source']
        if file_digest(video) != spec['source_sha256']:
            raise ValueError(f'Recording differs from annotations: {video}')
        sources.append((stamp, video, spec_path, spec))
    # Never overwrite a previous dataset or alter its split inventory.
    args.output.mkdir(parents=True, exist_ok=False)
    for kind in ('images', 'labels'):
        for split in ('train', 'val', 'test'):
            (args.output / kind / split).mkdir(parents=True)
            for path in (args.replay / kind / split).iterdir():
                shutil.copy2(path, args.output / kind / split / path.name)
    glyph_bank = {'rank': {}, 'suit': {}}
    # Native glyph proportions from the old training-only synthetic replay.
    for path in sorted((args.replay / 'images/train').glob('synthetic_*.jpg')):
        code = path.stem.split('_')[1]
        if code.startswith('10'):
            continue  # replace the old fallback font with an actual reviewed ten
        image = cv2.imread(str(path))
        _, x, y, w, h = map(float, (args.replay / 'labels/train' / (path.stem+'.txt')).read_text().split())
        ih, iw = image.shape[:2]
        ax, ay, bx, by = round((x-w/2)*iw), round((y-h/2)*ih), round((x+w/2)*iw), round((y+h/2)*ih)
        index = image[ay:by, ax:bx]
        glyph_bank['rank'].setdefault(code[:-1], glyph_mask(index[:46]))
        glyph_bank['suit'].setdefault(code[-1], glyph_mask(index[46:]))
    inventory = []
    background = None
    for stamp, video, spec_path, spec in sources:
        spec = dict(spec, crop=[560, 380, 1200, 840])
        cap = cv2.VideoCapture(str(video))
        if not cap.isOpened() or [round(cap.get(3)), round(cap.get(4))] != spec['size']:
            cap.release()
            raise ValueError('Video dimensions do not match reviewed source')
        try:
            for entry in spec['frames']:
                # Guard gap of >=180s between adaptation and held-out suffix.
                # Only 213508 at 540s enters validation; never training.
                split = 'train' if entry['time'] <= 300 else 'val' if stamp == '213508' and entry['time'] == 540 else None
                if split is None:
                    continue
                cap.set(cv2.CAP_PROP_POS_MSEC, entry['time']*1000)
                ok, reference = cap.read()
                if not ok:
                    raise ValueError('Cannot decode reviewed frame')
                if background is None:
                    background = reference[380:840, 560:1200].copy()
                labels = annotations_for(entry, spec, names)
                if split == 'train':
                    for group in ('board', 'hole'):
                        for code, box in zip(entry[group], spec['index_boxes'][group]):
                            if code[:-1] == '10':
                                ax, ay, bx, by = box
                                cut = 45 if group == 'board' else 52
                                glyph_bank['rank'].setdefault('10', glyph_mask(reference[ay:ay+cut, ax:bx]))
                for offset in ((-.4, -.2, 0, .2, .4) if split == 'train' else (0,)):
                    actual = entry['time']+offset
                    if actual < 0:
                        continue
                    cap.set(cv2.CAP_PROP_POS_MSEC, actual*1000)
                    ok, image = cap.read()
                    if not ok or (offset and not stable_indices(reference, image, entry, spec)):
                        continue
                    stem = f'added_{stamp}_{actual:.1f}'
                    write_sample(args.output, split, stem, image[380:840, 560:1200], labels)
                    inventory.append({'file': stem, 'source': stamp, 'time': actual, 'split': split,
                                      'codes': entry['board']+entry['hole']})
        finally:
            cap.release()
    if '10' not in glyph_bank['rank']:
        raise ValueError('No reviewed real ten found in training prefix')
    # Replace all synthetic replay with consistent real training glyphs.
    add_synthetic_replay(args.output, background, names, glyph_bank)
    data = {'path': args.output.resolve().as_posix(), 'train': 'images/train',
            'val': 'images/val', 'test': 'images/test', 'names': names}
    (args.output / 'data.yaml').write_text(json.dumps(data, indent=2))
    manifest = {'replay_manifest_sha256': file_digest(args.replay / 'manifest.json'),
                'sources': [{'source': p.name, 'source_sha256': s['source_sha256'],
                             'annotations_sha256': file_digest(a)} for _, p, a, s in sources],
                'protocol': 'Both prefixes <=300s training; 213508 at 540s validation; other suffix samples excluded. Previous replay splits retained. Suffixes were reviewed in earlier development, not untouched benchmarks.',
                'real_ten_glyph': '211955 at 300s, first board card (training)',
                'added_frames_by_split': dict(Counter(e['split'] for e in inventory)),
                'real': inventory}
    (args.output / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    print(json.dumps({k:v for k,v in manifest.items() if k!='real'}, indent=2))


if __name__ == '__main__':
    main()

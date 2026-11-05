"""Build reviewed real frames plus synthetic replay for the captured digital table."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random

from card_detector import cv2, np, stacked_index_symbols
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).parent


def export_symbol_references(dataset, destination):
    """Reuse ONLY synthetic training indices as a compositional fallback."""
    dataset, destination = Path(dataset), Path(destination)
    for kind in ('rank', 'suit'):
        (destination / kind).mkdir(parents=True, exist_ok=True)
    names = json.loads((dataset / 'data.yaml').read_text())['names']
    for path in (dataset / 'images/train').glob('synthetic_*.jpg'):
        image = cv2.imread(str(path))
        height, width = image.shape[:2]
        label = (dataset / 'labels/train' / (path.stem+'.txt')).read_text().split()
        index, x, y, w, h = map(float, label)
        x1, y1 = round((x-w/2)*width), round((y-h/2)*height)
        x2, y2 = round((x+w/2)*width), round((y+h/2)*height)
        symbols = stacked_index_symbols(image[y1:y2, x1:x2])
        if symbols is None:
            continue
        code = names[int(index)]
        for kind, key, mask in zip(('rank', 'suit'), (code[:-1], code[-1]), symbols[0]):
            cv2.imwrite(str(destination / kind / f'{key}_{path.stem}.png'), mask*255)


def annotations_for(frame, specification, names):
    labels = []
    x0, y0, x2, y2 = specification['crop']
    for group in ('board', 'hole'):
        if len(frame[group]) > len(specification['index_boxes'][group]):
            raise ValueError(f'Too many annotated cards in {group}')
        for code, box in zip(frame[group], specification['index_boxes'][group]):
            left, top, right, bottom = box
            if not (x0 <= left < right <= x2 and y0 <= top < bottom <= y2):
                raise ValueError(f'Index outside crop: {code} {box}')
            labels.append([names.index(code), (left+right-2*x0)/2/(x2-x0),
                           (top+bottom-2*y0)/2/(y2-y0), (right-left)/(x2-x0), (bottom-top)/(y2-y0)])
    return labels


def write_sample(out, split, stem, image, labels):
    if not cv2.imwrite(str(out / 'images' / split / f'{stem}.jpg'), image, [cv2.IMWRITE_JPEG_QUALITY, 95]):
        raise OSError(f'Cannot write image {stem}')
    text = '\n'.join(' '.join(str(v) for v in row) for row in labels)
    (out / 'labels' / split / f'{stem}.txt').write_text(text + ('\n' if text else ''), encoding='utf-8')


def stable_indices(reference, candidate, entry, specification):
    # Propagate labels only inside the same hand and with virtually unchanged ink.
    # Also compare empty slots: an unchanged flop does not imply that a new
    # turn card has not appeared beside it during label propagation.
    regions = [box for group in ('board', 'hole')
               for box in specification['index_boxes'][group]]
    if not regions:
        regions = [[560, 390, 1190, 560], [640, 640, 815, 840]]
    for x1, y1, x2, y2 in regions:
        a = reference[y1:y2, x1:x2]
        b = candidate[y1:y2, x1:x2]
        delta = np.abs(a.astype(np.int16) - b.astype(np.int16))
        if delta.mean() > 2 or np.mean(delta > 20) > .005:
            return False
        aa = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY) < 160
        bb = cv2.cvtColor(b, cv2.COLOR_BGR2GRAY) < 160
        union = np.count_nonzero(aa | bb)
        if union and np.count_nonzero(aa & bb) / union < .985:
            return False
    return True


def index_ink(image):
    mask = (cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) < 170).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    if count <= 1:
        raise ValueError('No glyph in reviewed training index')
    largest = 1 + int(stats[1:, cv2.CC_STAT_AREA].argmax())
    x, y, w, h, _ = stats[largest]
    return Image.fromarray(((labels[y:y+h, x:x+w] == largest) * 255).astype(np.uint8))


def add_synthetic_replay(out, background, names, glyph_bank):
    """All 52 codes, without using validation/test card pixels or fonts."""
    rng = random.Random(195129)
    fonts = [Path('C:/Windows/Fonts') / name for name in ('arialnb.ttf', 'arialbd.ttf', 'arial.ttf')]
    suit_font_path = Path('C:/Windows/Fonts/seguisym.ttf')
    if not all(path.is_file() for path in [*fonts, suit_font_path]):
        raise ValueError('Synthetic replay requires the documented Windows Arial/Segoe fonts')
    symbols = dict(C='♣', D='♦', H='♥', S='♠')
    for index, code in enumerate(names):
        for variant, font_path in enumerate(fonts):
            image = Image.fromarray(cv2.cvtColor(background, cv2.COLOR_BGR2RGB))
            draw = ImageDraw.Draw(image)
            width, height = rng.randrange(100, 126), rng.randrange(150, 185)
            x, y = rng.randrange(10, 640-width-10), rng.randrange(10, 460-height-10)
            draw.rounded_rectangle((x, y, x+width, y+height), radius=5, fill=(250, 250, 250), outline=(150, 150, 150))
            color = (165, 15, 25) if code[-1] in 'DH' else (8, 12, 20)
            rank_font = ImageFont.truetype(str(font_path), 43 if code[:-1] != '10' else 35)
            suit_font = ImageFont.truetype(str(suit_font_path), 30)
            symbol = symbols[code[-1]]
            if code[:-1] in glyph_bank['rank']:
                rank_mask = glyph_bank['rank'][code[:-1]].copy()
                rank_height = [39, 42, 45][variant]
                rank_width = round(rank_mask.width * rank_height / rank_mask.height)
                rank_mask = rank_mask.resize((rank_width, rank_height), Image.Resampling.BICUBIC)
                image.paste(color, (x+5, y+5, x+5+rank_width, y+5+rank_height), rank_mask)
                right = x+7+rank_width
            else:
                draw.text((x+5, y+5), code[:-1], font=rank_font, fill=color, anchor='lt')
                right = draw.textbbox((x+5, y+5), code[:-1], font=rank_font, anchor='lt')[2] + 2
            suit_mask = glyph_bank['suit'][code[-1]].copy()
            suit_height = 29
            suit_width = round(suit_mask.width * suit_height / suit_mask.height)
            suit_mask = suit_mask.resize((suit_width, suit_height), Image.Resampling.BICUBIC)
            image.paste(color, (x+5, y+49, x+5+suit_width, y+49+suit_height), suit_mask)
            draw.text((x+width//2, y+height*.55), symbol,
                      font=ImageFont.truetype(str(suit_font_path), 68), fill=color, anchor='mm')
            right = max(right, x+7+suit_width)
            left, top, bottom = x+3, y+3, y+80
            label = [[index, (left+right)/1280, (top+bottom)/920,
                      (right-left)/640, (bottom-top)/460]]
            bgr = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
            write_sample(out, 'train', f'synthetic_{code}_{variant}', bgr, label)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('video', type=Path)
    parser.add_argument('--annotations', type=Path, default=ROOT / 'datasets/table-195129.json')
    parser.add_argument('--output', type=Path, default=ROOT / 'artifacts/table-195129/dataset-v2')
    args = parser.parse_args()
    spec = json.loads(args.annotations.read_text(encoding='utf-8'))
    with args.video.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    if digest != spec['source_sha256']:
        raise ValueError('Recording differs from the manually reviewed annotation source')
    names = json.loads((ROOT / 'models/lgd-cards-gen3.classes.json').read_text())
    groups = {}
    for entry in spec['frames']:
        if entry['hand'] in groups and groups[entry['hand']] != entry['split']:
            raise ValueError('A hand appears in multiple splits')
        groups[entry['hand']] = entry['split']
    cap = cv2.VideoCapture(str(args.video))
    if not cap.isOpened():
        raise ValueError('Cannot open recording')
    if [round(cap.get(3)), round(cap.get(4))] != spec['size']:
        cap.release()
        raise ValueError('Recording dimensions do not match the reviewed annotations')
    args.output.mkdir(parents=True, exist_ok=False)
    for kind in ('images', 'labels'):
        for split in ('train', 'val', 'test'):
            (args.output / kind / split).mkdir(parents=True)
    manifest = []
    background = None
    glyph_bank = {'rank': {}, 'suit': {}}
    x1, y1, x2, y2 = spec['crop']
    try:
        for entry in spec['frames']:
            timestamp = entry['time']
            cap.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000)
            ok, reference = cap.read()
            if not ok:
                raise ValueError(f'Cannot decode {timestamp}s')
            if timestamp == 0:
                background = reference[y1:y2, x1:x2].copy()
            labels = annotations_for(entry, spec, names)
            if entry['split'] == 'train':
                for group in ('board', 'hole'):
                    for code, box in zip(entry[group], spec['index_boxes'][group]):
                        ax, ay, bx, by = box
                        index = reference[ay:by, ax:bx]
                        cut = 45 if group == 'board' else 52
                        glyph_bank['rank'].setdefault(code[:-1], index_ink(index[:cut]))
                        glyph_bank['suit'].setdefault(code[-1], index_ink(index[cut:]))
            offsets = [-.4, -.2, 0, .2, .4] if entry['split'] == 'train' else [0]
            for offset in offsets:
                actual = max(0, timestamp + offset)
                if timestamp == 0 and offset < 0:
                    continue
                cap.set(cv2.CAP_PROP_POS_MSEC, actual * 1000)
                ok, image = cap.read()
                if not ok or (offset and not stable_indices(reference, image, entry, spec)):
                    continue
                stem = f'real_{timestamp:04d}_{actual:.1f}'
                write_sample(args.output, entry['split'], stem, image[y1:y2, x1:x2], labels)
                manifest.append({'file': stem, 'time': actual, 'hand': entry['hand'],
                                 'split': entry['split'], 'codes': entry['board'] + entry['hole']})
    finally:
        cap.release()
    add_synthetic_replay(args.output, background, names, glyph_bank)
    data = {'path': str(args.output.resolve()).replace('\\', '/'),
            'train': 'images/train', 'val': 'images/val', 'test': 'images/test', 'names': names}
    (args.output / 'data.yaml').write_text(json.dumps(data, indent=2), encoding='utf-8')
    report = {'source_sha256': digest, 'source': args.video.name, 'real': manifest,
              'real_frames_by_split': dict(Counter(item['split'] for item in manifest)),
              'real_training_codes': sorted({code for item in manifest if item['split'] == 'train' for code in item['codes']}),
              'synthetic_train_frames': len(names)*3, 'synthetic_classes': len(names), 'seed': 195129}
    report['synthetic_glyph_source'] = 'Reviewed training hands only; no validation/test pixels'
    report['real_rank_glyphs'] = sorted(glyph_bank['rank'])
    (args.output / 'manifest.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'real'}, indent=2))


if __name__ == '__main__':
    main()

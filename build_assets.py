"""Reproduce small symbol references from manually labelled recording frames."""
import argparse
import json
import os
import re
import tempfile
from pathlib import Path
from card_detector import cv2, candidates, glyphs, physical_candidates

# Sorted left-to-right detections. '-' denotes a covered card, never a label.
LABELS = {
    60: ['10H', '-', '-', '-', '-', 'JH', '7D', '9H', '8S', 'AC'],
    240: ['9D', '3H', 'AH', '7H', '5S', '7C'],
    300: ['8S', 'KH', '8H', 'AC', '7D', '2D', 'KD', '6D', 'QH', '5D'],
    420: ['JH', '8C', '9H', '10H', '9S'],
    480: ['5S', '-', '-', '-', '-', '8H', 'QH', '2S', '6D', '9D'],
    840: ['10D', '7C', 'JD', '2C', '8S', 'JH', 'AC', '6C', 'QH'],
    1200: ['-', '4D'],
}

PHYSICAL_LABELS = {
    60: ('stud', {'dealer': ['10H'], 'player': ['JH', '7D', '9H', '8S', 'AC']}),
    300: ('stud', {'player': ['2D', 'KD', '6D', 'QH', '5D']}),
    840: ('holdem', {'dealer': ['10D', '7C'], 'board': ['JD', '2C', '8S', 'JH', 'AC'], 'player': ['6C', 'QH']}),
    1200: ('holdem', {'player': ['4D']}),
    1380: ('holdem', {'board': ['3S', '8S', '7D'], 'player': ['6S', '2C']}),
}


def _extract(cap, video, out):
    for name in ('rank', 'suit', 'scene'):
        (out / name).mkdir(parents=True, exist_ok=True)
    (out / 'examples').mkdir(exist_ok=True)
    for name in ('rank', 'suit'):
        (out / 'physical' / name).mkdir(parents=True, exist_ok=True)
    for sec, labels in LABELS.items():
        cap.set(cv2.CAP_PROP_POS_MSEC, sec * 1000)
        ok, frame = cap.read()
        if not ok:
            raise RuntimeError(f'Cannot read {sec}s')
        boxes = candidates(frame)
        if len(boxes) != len(labels):
            raise RuntimeError(f'{sec}s: expected {len(labels)} boxes, got {boxes}')
        for i, ((x, y, w, h), label) in enumerate(zip(boxes, labels)):
            if label == '-':
                continue
            rank, suit = glyphs(frame[y:y+h, x:x+w])
            for name, symbol, image in [('rank', label[:-1], rank), ('suit', label[-1], suit)]:
                cv2.imwrite(str(out / name / f'{symbol}_{sec}_{i}.png'), image * 255)
        if sec in (60, 1200):
            name = 'stud' if sec == 60 else 'holdem'
            cv2.imwrite(str(out / 'scene' / f'{name}.png'), frame[0:32, 105:260])
        if sec == 60:
            for name, index in [('covered', 1), ('JH', 5)]:
                x, y, w, h = boxes[index]
                cv2.imwrite(str(out / 'examples' / f'{name}.png'), frame[y:y+h, x:x+w])
    for sec, (scene, groups) in PHYSICAL_LABELS.items():
        cap.set(cv2.CAP_PROP_POS_MSEC, sec * 1000)
        ok, frame = cap.read()
        if not ok:
            raise RuntimeError(f'Cannot read {sec}s')
        detections = list(physical_candidates(frame, scene))
        for group, labels in groups.items():
            cards = [c for g, _, _, c in detections if g == group]
            if len(cards) != len(labels):
                raise RuntimeError(f'{sec}s {group}: expected {len(labels)} cards, got {len(cards)}')
            for i, (card, label) in enumerate(zip(cards, labels)):
                for kind, symbol, image in zip(('rank', 'suit'), (label[:-1], label[-1]), glyphs(card, physical=True)):
                    cv2.imwrite(str(out / 'physical' / kind / f'{symbol}_{sec}_{group}_{i}.png'), image * 255)
    (out / 'provenance.json').write_text(json.dumps({
        'source': Path(video).name,
        'reference_timestamps_seconds': list(LABELS),
        'labels': LABELS,
        'physical_labels': PHYSICAL_LABELS,
        'note': 'Manually read references; not an independently labelled evaluation set.'
    }, indent=2), encoding='utf-8')


def regenerate(video, destination):
    """Validate all reference frames before replacing any existing templates."""
    destination = Path(destination)
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        cap.release()
        raise ValueError(f'Cannot open video: {video}')
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.card-assets-', dir=destination.parent) as folder:
            staging = Path(folder)
            _extract(cap, video, staging)
            generated = {path.relative_to(staging) for path in staging.rglob('*') if path.is_file()}
            # Each file replacement is atomic; input/annotation failures above
            # leave the previous complete reference set untouched.
            for relative in sorted(generated):
                target = destination / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(staging / relative, target)
            for name in ('rank', 'suit', 'physical/rank', 'physical/suit'):
                for path in (destination / name).glob('*.png'):
                    if path.relative_to(destination) not in generated and re.fullmatch(
                        r'(?:10|[2-9AJQKCDHS])_\d+_(?:(?:dealer|player|board)_)?\d+\.png', path.name
                    ):
                        path.unlink()
    finally:
        cap.release()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('video')
    parser.add_argument('--output', default='assets')
    args = parser.parse_args()
    regenerate(args.video, args.output)


if __name__ == '__main__':
    main()

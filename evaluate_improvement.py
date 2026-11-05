"""Compare frozen and candidate profiles before promoting updated weights."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
from unittest.mock import patch

from card_detector import annotate, cv2, np
import download_model
import learned_detector
from download_model import file_digest
from evaluate_table_model import score_frame

ROOT = Path(__file__).resolve().parent


def load_profile(directory):
    with patch.object(download_model, 'MODEL_DIR', directory), patch.object(learned_detector, 'MODEL_DIR', directory):
        return learned_detector.LearnedCardDetector('pokerstars')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('video_directory', type=Path)
    parser.add_argument('--previous', type=Path, default=ROOT / 'artifacts/table-improvement/previous-model')
    parser.add_argument('--candidate', type=Path, default=ROOT / 'artifacts/table-improvement/candidate')
    parser.add_argument('--output', type=Path, default=ROOT / 'artifacts/table-improvement/evaluation')
    parser.add_argument('--extra-annotations', type=Path, nargs='*', default=[])
    parser.add_argument('--saved-frames', type=Path,
                        help='Explicit JPEG regression mode: table-STAMP/inspection/TIME.jpg; no source-video equivalence claim')
    args = parser.parse_args()
    detectors = {name: load_profile(path) for name, path in (('previous', args.previous), ('candidate', args.candidate))}
    args.output.mkdir(parents=True, exist_ok=True)
    cases = defaultdict(list)

    def check(key, frame, expected, crop=False):
        for name, detector in detectors.items():
            original_crop = detector.crop
            if crop:
                detector.crop = None
            try:
                result = detector.detect(frame)
            finally:
                detector.crop = original_crop
            scores = score_frame(expected, result['cards'])
            cases[name].append({'case': key, **scores, 'processing_ms': result['processing_ms'],
                                'cards': result['cards']})
            cv2.imwrite(str(args.output / f'{name}-{key}.jpg'), annotate(frame, result))

    sources = []
    annotation_sources = [(stamp, ROOT / f'datasets/table-{stamp}.json') for stamp in ('211955', '213508')]
    annotation_sources += [(None, path) for path in args.extra_annotations]
    for stamp, annotations in annotation_sources:
        spec = json.loads(annotations.read_text())
        video = args.video_directory / spec['source']
        if args.saved_frames and stamp is None:
            raise ValueError('Saved-frame mode supports the two original timestamp inventories only')
        if not args.saved_frames and file_digest(video) != spec['source_sha256']:
            raise ValueError('Recording differs from reviewed annotations')
        source = {'video': video.name, 'sha256': spec['source_sha256'],
                  'annotations_sha256': file_digest(annotations), 'saved_frames': []}
        sources.append(source)
        cap = None if args.saved_frames else cv2.VideoCapture(str(video))
        if cap is not None and (not cap.isOpened() or [round(cap.get(3)), round(cap.get(4))] != spec['size']):
            cap.release()
            raise ValueError('Video dimensions differ from annotations')
        try:
            for entry in spec['frames']:
                t = entry['time']
                partition = ('extra_adaptation' if stamp is None else 'adaptation' if t <= 300
                             else 'validation' if stamp == '213508' and t == 540 else 'heldout')
                if args.saved_frames:
                    path = args.saved_frames / f'table-{stamp}/inspection/{int(t):04d}.jpg'
                    frame = cv2.imread(str(path))
                    ok = frame is not None and [frame.shape[1], frame.shape[0]] == spec['size']
                    source['saved_frames'].append({'time': t, 'sha256': file_digest(path)})
                else:
                    cap.set(cv2.CAP_PROP_POS_MSEC, t*1000)
                    ok, frame = cap.read()
                if not ok:
                    raise ValueError(f'Cannot decode {video} at {t}')
                expected = [(code, box) for group in spec['index_boxes']
                            for code, box in zip(entry[group], spec['index_boxes'][group])]
                check(f'{partition}-{stamp or annotations.stem}-{t}', frame, expected)
        finally:
            if cap is not None:
                cap.release()
    # Original recording removed by user; preserved labelled crops still allow
    # classifier regression checks, but do not verify full-frame opponent tiling.
    replay = ROOT / 'artifacts/table-195129/dataset-v2'
    names = json.loads((replay / 'data.yaml').read_text())['names']
    for split in ('val', 'test'):
        for path in sorted((replay / 'images' / split).glob('*.jpg')):
            frame = cv2.imread(str(path))
            h, w = frame.shape[:2]
            expected = []
            for row in (replay / 'labels' / split / (path.stem+'.txt')).read_text().splitlines():
                cls, x, y, bw, bh = map(float, row.split())
                expected.append((names[int(cls)], [round((x-bw/2)*w), round((y-bh/2)*h),
                                                  round((x+bw/2)*w), round((y+bh/2)*h)]))
            check(f'regression-{split}-{path.stem}', frame, expected, crop=True)
    summaries = {}
    for name, entries in cases.items():
        summaries[name] = {}
        for partition in ('adaptation', 'extra_adaptation', 'validation', 'heldout', 'regression'):
            selected = [e for e in entries if e['case'].startswith(partition+'-')]
            if not selected:
                continue
            tp = sum(len(e['correct']) for e in selected)
            fp = sum(len(e['false_positive']) for e in selected)
            fn = sum(len(e['missed']) for e in selected)
            summaries[name][partition] = {'frames': len(selected), 'correct': tp, 'false_positive': fp,
                                         'missed': fn, 'expected': tp+fn,
                                         'processing_ms_median': float(np.median([e['processing_ms'] for e in selected])),
                                         'processing_ms_p95': float(np.percentile([e['processing_ms'] for e in selected],95))}
    report = {'protocol': 'Adaptation <=300s; 213508 540s validation; other suffixes excluded from this weight update. Suffixes reviewed previously: development holdout, not untouched benchmark.',
              'input_mode': 'preserved JPEG frames; original videos unavailable, JPEG compression can change predictions' if args.saved_frames else 'original source video',
              'sources': sources, 'manifests': {name: file_digest(path / 'pokerstars.manifest.json')
                                              for name, path in (('previous', args.previous), ('candidate', args.candidate))},
              'summary': summaries, 'cases': cases}
    (args.output / 'report.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(summaries, indent=2))


if __name__ == '__main__':
    main()

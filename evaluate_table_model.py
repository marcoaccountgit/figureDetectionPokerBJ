"""Position-aware real-video evaluation of the calibrated table model."""
import argparse
from collections import Counter
import json
from pathlib import Path
from card_detector import annotate, cv2, np
from learned_detector import LearnedCardDetector
from download_model import file_digest, model_manifest

ROOT = Path(__file__).parent


def box_iou(a, b):
    left, top = max(a[0], b[0]), max(a[1], b[1])
    right, bottom = min(a[2], b[2]), min(a[3], b[3])
    intersection = max(0, right-left) * max(0, bottom-top)
    union = (a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - intersection
    return intersection / union if union > 0 else 0


def score_frame(expected, predictions):
    """Match identity AND position; repeated codes remain separate indices."""
    matched = set()
    correct, wrong = [], []
    for prediction in sorted((p for p in predictions if p['accepted']),
                             key=lambda p: p.get('confidence', 0), reverse=True):
        overlaps = [(box_iou(prediction['bbox'], box), i, code)
                    for i, (code, box) in enumerate(expected) if i not in matched]
        best = max(overlaps, default=(0, -1, None))
        if best[0] >= .3 and prediction['card'] == best[2]:
            matched.add(best[1])
            correct.append(prediction['card'])
        else:
            wrong.append(prediction['card'])
    missed = [code for i, (code, _) in enumerate(expected) if i not in matched]
    return {'correct': correct, 'false_positive': wrong, 'missed': missed}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('video')
    parser.add_argument('--annotations', type=Path, default=ROOT / 'datasets/table-195129.json')
    parser.add_argument('--split', choices=('val', 'test'), default='test')
    parser.add_argument('--output', type=Path, default=ROOT / 'artifacts/table-195129/evaluation')
    args = parser.parse_args()
    spec = json.loads(args.annotations.read_text())
    metadata = model_manifest('pokerstars')
    source_hash = file_digest(args.video)
    if source_hash != spec['source_sha256']:
        raise ValueError('Recording differs from the source of the reviewed annotations')
    candidate = LearnedCardDetector('pokerstars')
    baseline = LearnedCardDetector()
    baseline_crop = LearnedCardDetector()
    baseline_crop.crop = candidate.crop
    baseline_crop.crop_reference_size = candidate.crop_reference_size
    detectors = {'original_full_frame': baseline, 'original_same_crop': baseline_crop,
                 'finetuned_pokerstars': candidate}
    base_nano_path = ROOT / 'artifacts/table-195129/base-yolo11n.onnx'
    if base_nano_path.is_file():
        base_nano = LearnedCardDetector()
        base_nano.crop = candidate.crop
        base_nano.crop_reference_size = candidate.crop_reference_size
        base_nano.net = cv2.dnn.readNetFromONNX(str(base_nano_path))
        detectors['base_nano_same_crop'] = base_nano
    report = {'split': args.split, 'source_sha256': source_hash,
              'annotation_sha256': file_digest(args.annotations),
              'candidate_sha256': metadata['files'][0]['sha256'],
              'matching': 'identity and index bbox IoU >= 0.30',
              'development_note': spec.get('note', ''),
              'pipeline_note': 'The original training-video test was reviewed during pipeline development. For other recordings consult the annotation protocol.',
              'models': {}}
    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        raise ValueError('Cannot open recording')
    if [round(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), round(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))] != spec['size']:
        cap.release()
        raise ValueError('Recording dimensions differ from reviewed annotations')
    args.output.mkdir(parents=True, exist_ok=True)
    try:
        for name, detector in detectors.items():
            cases = []
            tp = fp = fn = 0
            for entry in spec['frames']:
                if entry['split'] != args.split:
                    continue
                cap.set(cv2.CAP_PROP_POS_MSEC, entry['time']*1000)
                ok, frame = cap.read()
                if not ok:
                    raise ValueError(f"Cannot decode {entry['time']}s")
                expected = [(code, box) for group in spec['index_boxes']
                            for code, box in zip(entry.get(group, []), spec['index_boxes'][group])]
                result = detector.detect(frame)
                scores = score_frame(expected, result['cards'])
                tp += len(scores['correct'])
                fp += len(scores['false_positive'])
                fn += len(scores['missed'])
                cases.append({'time': entry['time'], 'hand': entry.get('hand'), **scores,
                              'decision_sources': dict(Counter(c.get('decision_source', 'model')
                                                               for c in result['cards'] if c['accepted'])),
                              'regions_analyzed': result.get('regions_analyzed', 1),
                              'processing_ms': result['processing_ms']})
                cv2.imwrite(str(args.output / f'{name}-{entry["time"]}.jpg'), annotate(frame, result))
            timings = [c['processing_ms'] for c in cases]
            report['models'][name] = {
                'true_positive': tp, 'false_positive': fp, 'false_negative': fn,
                'precision': tp/(tp+fp) if tp+fp else None, 'recall': tp/(tp+fn) if tp+fn else None,
                'processing_ms': {str(p): float(np.percentile(timings, p)) for p in (50, 95)},
                'cases': cases}
    finally:
        cap.release()
    (args.output / f'{args.split}-report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({name: {k: v for k, v in stats.items() if k != 'cases'}
                      for name, stats in report['models'].items()}, indent=2))


if __name__ == '__main__':
    main()

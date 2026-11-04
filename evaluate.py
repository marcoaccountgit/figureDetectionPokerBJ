"""Report accepted identities and misses against a small manual check set."""
import argparse
from collections import Counter
import json
from pathlib import Path
from card_detector import Detector, annotate, cv2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('video')
    parser.add_argument('--cases', type=Path, default=Path(__file__).parent / 'evaluation_cases.json')
    parser.add_argument('--output', type=Path, default=Path('artifacts/evaluation'))
    args = parser.parse_args()
    specification = json.loads(args.cases.read_text(encoding='utf-8'))
    detector = Detector()
    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        raise SystemExit('Cannot open video')
    args.output.mkdir(parents=True, exist_ok=True)
    details = []
    totals = {domain: {'expected': 0, 'accepted': 0, 'correct_identity_counts': 0, 'wrong_identity_counts': 0}
              for domain in ('digital', 'physical')}
    try:
        for case in specification['cases']:
            timestamp = case['timestamp_s']
            cap.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000)
            ok, frame = cap.read()
            if not ok:
                raise RuntimeError(f'Cannot read {timestamp}s')
            result = detector.detect(frame)
            entry = {'timestamp_s': timestamp, 'scene_correct': result['scene'] == case['scene'],
                     'processing_ms': result['processing_ms']}
            for domain in totals:
                expected = Counter(case[domain])
                predicted = Counter(c['card'] for c in result['cards']
                                    if c['domain'] == domain and c['accepted'])
                correct = sum((expected & predicted).values())
                stats = {'expected': sum(expected.values()), 'accepted': sum(predicted.values()),
                         'correct_identity_counts': correct,
                         'wrong_identity_counts': sum(predicted.values()) - correct}
                entry[domain] = {**stats, 'predicted': list(predicted.elements()),
                                 'missed': list((expected - predicted).elements())}
                for key, value in stats.items():
                    totals[domain][key] += value
            details.append(entry)
            cv2.imwrite(str(args.output / f'{timestamp}-annotated.jpg'), annotate(frame, result))
    finally:
        cap.release()
    for stats in totals.values():
        stats['coverage'] = stats['correct_identity_counts'] / stats['expected'] if stats['expected'] else None
        stats['accepted_precision'] = stats['correct_identity_counts'] / stats['accepted'] if stats['accepted'] else None
    report = {'note': specification['note'], 'totals': totals, 'cases': details}
    (args.output / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()

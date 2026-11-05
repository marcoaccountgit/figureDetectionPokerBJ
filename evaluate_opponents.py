"""Check covered-pair counting against reviewed frames from existing videos."""
import argparse
import json
from pathlib import Path
from hashlib import sha256

from card_detector import cv2
from opponent_detector import OpponentDetector

ROOT = Path(__file__).resolve().parent


def evaluate():
    detector = OpponentDetector()
    spec = json.loads((ROOT/'datasets/opponents-reviewed.json').read_text())
    cases = []
    for entry in spec['frames']:
        source, time = entry['source'], entry['time']
        relative = (f'artifacts/capture10-improvement/dataset/reviewed/{time}.png' if source == 'capture10'
                    else f'artifacts/table-{source}/inspection/{time:04d}.jpg')
        path = ROOT/relative
        frame = cv2.imread(str(path))
        if frame is None:
            raise RuntimeError(f'Fotogramma conservato mancante: {path}')
        seats = detector.detect(frame)
        predicted = [int(s['present']) if s['present'] is not None else None for s in seats]
        cases.append(dict(entry, file=relative, sha256=sha256(path.read_bytes()).hexdigest(),
                          predicted=predicted, scores=[s['score'] for s in seats],
                          exact=predicted == entry['seats']))
    development = [c for c in cases if c['split'] != 'reference']
    return dict(protocol=spec['protocol'], reference_frames=len(cases)-len(development),
                development_frames=len(development),
                exact_frames=sum(c['exact'] for c in development),
                correct_seats=sum(a == b for c in development for a,b in zip(c['predicted'],c['seats'])),
                total_seats=len(development)*5, cases=cases)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'artifacts/opponents/report.json')
    args = parser.parse_args()
    report = evaluate()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k != 'cases'}))
    if report['exact_frames'] != report['development_frames']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()

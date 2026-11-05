"""Compare two profiles on full, manually reviewed canonical capture frames."""
import argparse
from collections import defaultdict
import json
from pathlib import Path

from card_detector import annotate, cv2
from download_model import file_digest
from evaluate_improvement import load_profile
from evaluate_table_model import score_frame


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--annotations', type=Path, required=True)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--previous', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    spec = json.loads(args.annotations.read_text())
    manifest = json.loads((args.dataset / 'manifest.json').read_text())
    if manifest['annotations_sha256'] != file_digest(args.annotations):
        raise ValueError('Annotations differ from prepared capture dataset')
    args.output.mkdir(parents=True, exist_ok=False)
    cases, summary = {}, {}
    for name, path in (('previous', args.previous), ('candidate', args.candidate)):
        detector = load_profile(path)
        rows, counts = [], defaultdict(lambda: dict(frames=0, expected=0, correct=0,
                                                   false_positive=0, missed=0))
        for entry in spec['frames']:
            frame = cv2.imread(str(args.dataset / 'reviewed' / f"{entry['time']}.png"))
            if frame is None:
                raise ValueError('Missing reviewed capture frame')
            expected = [(code, box) for group in ('board', 'hole')
                        for code, box in zip(entry[group], spec['index_boxes'][group])]
            result = detector.detect(frame)
            scored = score_frame(expected, result['cards'])
            rows.append(dict(time=entry['time'], split=entry['split'], hand=entry['hand'],
                             **scored, cards=result['cards']))
            totals = counts[entry['split']]
            totals['frames'] += 1
            totals['expected'] += len(expected)
            for key in ('correct', 'false_positive', 'missed'):
                totals[key] += len(scored[key])
            cv2.imwrite(str(args.output / f"{name}-{entry['time']}.jpg"), annotate(frame, result))
        cases[name], summary[name] = rows, dict(counts)
    report = dict(protocol='Full-frame exact identity and index IoU>=0.30. Hands separated across splits; reviewed development holdout, not an untouched benchmark. Native decoding and canonical alignment required.',
                  source_sha256=spec['source_sha256'],
                  annotations_sha256=file_digest(args.annotations),
                  models={name: file_digest(path / 'pokerstars.manifest.json')
                          for name, path in (('previous', args.previous), ('candidate', args.candidate))},
                  summary=summary, cases=cases)
    (args.output / 'report.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()

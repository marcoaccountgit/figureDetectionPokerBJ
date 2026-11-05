"""Compare original and supplemental symbol recovery on preserved video frames."""
import argparse
from hashlib import sha256
import json
from pathlib import Path

from card_detector import cv2
from capture_alignment import CaptureAligner, restore_coordinates
from evaluate_table_model import score_frame
from learned_detector import LearnedCardDetector

ROOT = Path(__file__).resolve().parent


def evaluate():
    before = LearnedCardDetector(profile='pokerstars')
    before.reviewed_symbol_classifier = None
    after = LearnedCardDetector(profile='pokerstars')
    totals = {key:dict(correct=0,false_positive=0,missed=0) for key in ('before','after')}
    cases = []
    for source in ('211955','213508','capture10'):
        spec = json.loads((ROOT/f'datasets/table-{source}.json').read_text())
        for entry in spec['frames']:
            timestamp = entry['time']
            path = (ROOT/f'artifacts/capture10-improvement/dataset/reviewed/{timestamp}.png' if source=='capture10'
                    else ROOT/f'artifacts/table-{source}/inspection/{timestamp:04d}.jpg')
            frame = cv2.imread(str(path))
            if frame is None:
                raise RuntimeError(f'Fotogramma mancante: {path}')
            game,viewport = CaptureAligner().align(frame)
            expected = [(code,box) for group in ('board','hole','opponent')
                        for code,box in zip(entry.get(group,[]),spec['index_boxes'].get(group,[]))]
            case = dict(source=source,time=timestamp,sha256=sha256(path.read_bytes()).hexdigest())
            for label,model in [('before',before),('after',after)]:
                result = restore_coordinates(model.detect(game),viewport,frame.shape)
                score = score_frame(expected,result['cards'])
                case[label] = {key:sorted(value) for key,value in score.items()}
                for key,value in score.items():
                    totals[label][key] += len(value)
            cases.append(case)
    return dict(protocol='Preserved development video frames, compared by identity and bbox IoU >= .30. The original classifier is preserved for strong readings; reviewed templates are fallback only. Screenshot adaptation samples are evaluated separately, not as independent accuracy.',
                frames=len(cases),totals=totals,cases=cases)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'artifacts/hand-fix-1927/regression.json')
    args = parser.parse_args()
    report = evaluate()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(dict(frames=report['frames'],totals=report['totals'])))
    before,after = report['totals']['before'],report['totals']['after']
    if after['correct'] < before['correct'] or after['false_positive'] > before['false_positive']:
        raise SystemExit(1)


if __name__=='__main__':
    main()

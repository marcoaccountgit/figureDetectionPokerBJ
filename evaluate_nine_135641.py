"""Evaluate reviewed per-seat labels and card slots, including held-out hands."""
import argparse,hashlib
from collections import Counter
import json
from pathlib import Path
from card_detector import cv2
from capture_alignment import CaptureAligner
from learned_detector import TableCardDetector
from opponent_detector import OpponentDetector
from table_layout import arrange_table
from table_profiles import NINE
from table_observer import TableVisualReader


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--widths',default='960')
    parser.add_argument('--candidate',type=Path)
    parser.add_argument('--output',type=Path,default=Path('artifacts/nine-135641/evaluation.json'))
    args=parser.parse_args()
    spec=json.loads(Path('datasets/nine-135641.json').read_text())
    baseline={f['time']:f for f in json.loads(Path('artifacts/nine-135641/baseline.json').read_text())['frames']}
    detector=TableCardDetector();opponents=OpponentDetector()
    reader=TableVisualReader(None,NINE)
    if args.candidate:
        from evaluate_training_candidate import load_model
        detector.models[NINE]=load_model(args.candidate)
    summary={};reports=[]
    for row in spec['frames']:
        source=cv2.imread(f'artifacts/nine-135641/source/{row["time"]:06.1f}.png')
        wanted=row['board']+[None]*(5-len(row['board']))+row['hole']+[None]*(2-len(row['hole']))
        for width in map(int,args.widths.split(',')):
            image=cv2.resize(source,(width,round(source.shape[0]*width/source.shape[1])))
            aligner=CaptureAligner();game,viewport=aligner.align(image)
            detector.profile=aligner.profile
            result=arrange_table(detector.detect(game),game.shape)
            actual=[c['card'] for c in result['board']+result['player_hand']]
            seats=opponents.detect(game,profile=aligner.profile)
            packet=dict(time=row['time'],split=row['split'],width=width,profile=aligner.profile,
                expected=wanted,actual=actual,seats=seats,
                button=reader.dealer_button(game),expected_button=row['button'],
                seat_errors=[dict(seat=s['seat'],actual=s['present'],expected=row['seats'].get(s['seat']),score=s['score']) for s in seats if s['present']!=row['seats'].get(s['seat'])])
            reports.append(packet)
            for version,readings,card_values,profile in [('after',seats,actual,aligner.profile)]+(
                [('before',baseline[row['time']]['seats'],baseline[row['time']]['actual'],baseline[row['time']]['profile'])] if width==960 else []):
                counts=summary.setdefault(f'{version}-{width}-{row["split"]}',Counter())
                exact=len(readings)==8 and all(s['present']==row['seats'].get(s['seat']) for s in readings)
                counts.update(frames=1,exact_seats=exact,profile_correct=profile==NINE,
                    exact_cards=card_values==wanted,visible_cards=sum(c is not None for c in wanted),
                    correct_visible=sum(a==b and b is not None for a,b in zip(card_values,wanted)),
                    wrong_cards=sum(a is not None and a!=b for a,b in zip(card_values,wanted)),
                    unknown_seats=sum(s['present'] is None for s in readings),
                    wrong_seats=sum(s['present'] is not None and s['present']!=row['seats'].get(s['seat']) for s in readings))
                if version=='after':counts.update(correct_button=packet['button']['seat']==row['button'])
    model_dir=args.candidate or Path('models')
    digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    args.output.write_text(json.dumps(dict(summary=summary,frames=reports,
        model_sha256=digest(model_dir/'pokerstars-nine.onnx'),
        runtime_sha256={name:digest(Path(name)) for name in ('learned_detector.py','download_model.py','opponent_detector.py','capture_alignment.py','table_profiles.py','table_observer.py')},
        caveat='Selected manually reviewed frames, not a full-video accuracy estimate; complete hands separated.'),indent=2))
    print(json.dumps(summary,indent=2))
    print('Remaining errors:',json.dumps([dict(time=r['time'],width=r['width'],seats=r['seat_errors'],cards=r['actual'] if r['actual']!=r['expected'] else []) for r in reports if r['seat_errors'] or r['actual']!=r['expected']]))


if __name__=='__main__':main()

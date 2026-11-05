"""Evaluate local OCR/button/action extraction on annotated preserved frames."""
import argparse
from hashlib import sha256
import json
from pathlib import Path

from card_detector import cv2
from table_observer import ROOT, TableStateTracker, TableVisualReader, WindowsOCR


def evaluate():
    spec = json.loads((ROOT/'datasets/table-observations-reviewed.json').read_text())
    reader = TableVisualReader(WindowsOCR())
    cases = []
    try:
        for entry in spec['cases']:
            path = ROOT/entry['file']
            frame = cv2.imread(str(path))
            if frame is None:
                raise RuntimeError(f'Fotogramma mancante: {path}')
            result = reader.read(frame)
            seats = {row['seat']:row for row in result['seats']}
            checks = []
            if 'button' in entry:
                checks.append(dict(field='button',expected=entry['button'],actual=result['button']['seat']))
            for field in ('pot','collected_pot'):
                if field in entry:
                    checks.append(dict(field=field,expected=entry[field],actual=result[field]['value'] if result[field] else None))
            if 'street' in entry:
                tracker = TableStateTracker()
                context = dict(hand_id=1,active=True,street=entry['street'])
                tracker.update(result,context,0)
                tracked = tracker.update(result,context,.2)
                phase = tracked['street_pots'].get(entry['street'],{})
                amount = phase.get('first_total')
                checks.append(dict(field='first_total:'+entry['street'],expected=entry['pot'],actual=amount['value'] if amount else None))
            for field,target in (('actions','action'),('stacks','stack'),('wagers','wager')):
                for seat,expected in entry.get(field,{}).items():
                    actual = seats[seat][target]
                    if target in ('stack','wager'):
                        actual = actual['value'] if actual else None
                    checks.append(dict(field=field+':'+seat,expected=expected,actual=actual))
            for seat in entry.get('empty',[]):
                checks.append(dict(field='empty:'+seat,expected=True,actual=seats[seat]['empty']))
            for action in entry.get('offered',[]):
                checks.append(dict(field='offered:'+action,expected=True,actual=any(a['action']==action for a in result['available_actions'])))
            cases.append(dict(file=entry['file'],sha256=sha256(path.read_bytes()).hexdigest(),
                              checks=checks,exact=all(c['actual']==c['expected'] for c in checks),result=result))
    finally:
        reader.ocr.close()
    return dict(protocol=spec['protocol'],frames=len(cases),exact_frames=sum(c['exact'] for c in cases),
                fields=sum(len(c['checks']) for c in cases),
                correct_fields=sum(v['expected']==v['actual'] for c in cases for v in c['checks']),cases=cases)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'artifacts/table-observer/report.json')
    args = parser.parse_args()
    report = evaluate()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='cases'}))
    for case in report['cases']:
        for check in case['checks']:
            if check['expected']!=check['actual']:
                print(case['file'],check)
    if report['fields']!=report['correct_fields']:
        raise SystemExit(1)


if __name__=='__main__':
    main()

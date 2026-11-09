"""Recheck the preserved original nine-seat recording against both weight sets."""
import json
from pathlib import Path
from card_detector import cv2
from capture_alignment import CaptureAligner
from evaluate_training_candidate import load_model
from table_layout import arrange_table
from opponent_detector import OpponentDetector


def main():
    root=Path('artifacts/nine-135641')
    models={name:load_model(root/folder) for name,folder in [('before','previous-model'),('after','candidate')]}
    spec=json.loads(Path('datasets/nine-seat-125816.json').read_text())
    rows=[];regressions=[]
    for label in spec['frames']:
        source=cv2.imread(f'artifacts/nine-seat-125816/inspection/{label["time"]:04d}.jpg')
        expected=label['board']+[None]*(5-len(label['board']))+label['hole']+[None]*(2-len(label['hole']))
        for width in (1918,1280):
            image=cv2.resize(source,(width,round(source.shape[0]*width/source.shape[1])))
            aligner=CaptureAligner();game,_=aligner.align(image)
            row=dict(time=label['time'],width=width,expected=expected)
            for name,model in models.items():
                model.table_profile=aligner.profile
                result=dict(model.detect(game),table_profile=aligner.profile)
                result=arrange_table(result,game.shape)
                row[name]=[c['card'] for c in result['board']+result['player_hand']]
            if any((b==e and a!=e) or (a is not None and a!=e and b!=a)
                   for b,a,e in zip(row['before'],row['after'],expected)):
                regressions.append(row)
            rows.append(row)
    summary={name:dict(frames=len(rows),exact=sum(r[name]==r['expected'] for r in rows),
        correct_visible=sum(a==e and e is not None for r in rows for a,e in zip(r[name],r['expected'])),
        wrong=sum(a is not None and a!=e for r in rows for a,e in zip(r[name],r['expected']))) for name in models}
    report=dict(summary=summary,regressions=regressions,frames=rows)
    (root/'original-nine-validated.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(dict(summary=summary,regressions=regressions),indent=2))


if __name__=='__main__':main()

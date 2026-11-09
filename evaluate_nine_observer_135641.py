"""Check learned back references and button geometry on the earlier nine-seat video."""
import json
from pathlib import Path
from card_detector import cv2
from capture_alignment import CaptureAligner
from opponent_detector import OpponentDetector
from table_observer import TableVisualReader


def main():
    spec=json.loads(Path('datasets/nine-seat-observations.json').read_text())
    detector=OpponentDetector();previous=OpponentDetector();previous.nine_variants={}
    reader=TableVisualReader(None,'pokerstars-nine')
    rows=[];regressions=[]
    for row in spec['frames']:
        t=row['time'];key=str(t)
        source=cv2.imread(f'artifacts/nine-seat-125816/inspection/{t:04d}.jpg')
        for width in (1918,1280):
            image=cv2.resize(source,(width,round(source.shape[0]*width/source.shape[1])))
            a=CaptureAligner();game,_=a.align(image)
            result=dict(time=t,width=width,button=reader.dealer_button(game))
            if 'button' in row:
                result['expected_button']=row['button']
                if result['button']['seat']!=row['button']:regressions.append(result)
            if key in spec['covered_seats']:
                expected=spec['covered_seats'][key]
                result['expected_seats']=expected
                result['before']=previous.detect(game,profile=a.profile)
                result['after']=detector.detect(game,profile=a.profile)
                before={s['seat']:s for s in result['before']}
                for seat in result['after']:
                    wanted=seat['seat'] in expected
                    if seat['present']!=wanted and before[seat['seat']]['present']==wanted:
                        regressions.append(dict(time=t,width=width,seat=seat,expected=wanted))
            rows.append(result)
    report=dict(frames=rows,regressions=regressions,
        exact_back_frames=sum(all(s['present']==(s['seat'] in r['expected_seats']) for s in r['after']) for r in rows if 'expected_seats'in r),
        reviewed_back_frames=sum('expected_seats'in r for r in rows))
    Path('artifacts/nine-135641/original-observer-validated.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k!='frames'},indent=2))


if __name__=='__main__':main()

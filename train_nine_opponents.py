"""Learn compact back references strictly from visually labelled TRAIN hands."""
import json
from pathlib import Path
from card_detector import cv2
from capture_alignment import CaptureAligner
from opponent_detector import OpponentDetector, features
from table_profiles import NINE_BACKS, NINE


def main():
    spec=json.loads(Path('datasets/nine-135641.json').read_text())
    detector=OpponentDetector()
    out=Path('assets/table-nine/variants')
    inventory=[]
    # Diverse unoccluded and HUD-covered training hands; no validation/test pixels.
    for row in spec['frames']:
        if row['split']!='train' or row['time'] not in (0,45,60,205,240,415,550,600):
            continue
        source=Path(f'artifacts/nine-135641/source/{row["time"]:06.1f}.png')
        aligner=CaptureAligner();game,_=aligner.align(cv2.imread(str(source)))
        if aligner.profile!=NINE:raise ValueError('Unexpected training geometry')
        game=cv2.resize(game,(1762,round(game.shape[0]*1762/game.shape[1])))
        for seat, present in row['seats'].items():
            if not present:continue
            x,y,r,b=NINE_BACKS[seat]
            roi=game[y:b,x:r]
            template=detector.nine_templates[seat]
            _,score,_,(dx,dy)=cv2.minMaxLoc(cv2.matchTemplate(features(roi),template,cv2.TM_CCOEFF_NORMED))
            if score<.5:raise ValueError(f'Unreliable crop {row["time"]} {seat}: {score}')
            # Keep both white top borders; HUDs only vary below this strip.
            patch=roi[dy:dy+20,dx:dx+template.shape[1]]
            target=out/seat/f'135641-{row["time"]:04d}.png'
            target.parent.mkdir(parents=True,exist_ok=True)
            cv2.imwrite(str(target),patch)
            inventory.append(dict(file=str(target),time=row['time'],hand=row['hand'],split=row['split'],seat=seat,location=[x+dx,y+dy],match_score=score))
    (out/'135641-provenance.json').write_text(json.dumps(dict(source=spec['source'],sha256=spec['sha256'],
        protocol='Manual positive labels; old template locates upper 20px of two backs. No threshold reduction. Complete held-out hands excluded.',references=inventory),indent=2))
    print('Learned',len(inventory),'references across',len({r['seat'] for r in inventory}),'seats')


if __name__=='__main__':main()

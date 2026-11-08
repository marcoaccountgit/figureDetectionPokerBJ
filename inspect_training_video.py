"""Extract reviewed card sheets and baseline predictions without pseudo labels."""
import argparse, hashlib, json
from pathlib import Path
from card_detector import cv2, np
from capture_alignment import CaptureAligner
from learned_detector import LearnedCardDetector
from table_layout import arrange_table

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('video',type=Path);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--step',type=int,default=5);args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    for folder in ('review','source'): (args.output/folder).mkdir(exist_ok=True)
    detector=LearnedCardDetector('pokerstars-nine')
    cap=cv2.VideoCapture(str(args.video));fps=cap.get(5);total=int(cap.get(7))
    inventory=[];sheets=[];sheet_index=0
    for index in range(total):
        if index % round(fps*args.step):
            if not cap.grab():break
            continue
        ok,frame=cap.read()
        if not ok:break
        t=round(index/fps)
        aligner=CaptureAligner();game,viewport=aligner.align(frame)
        result=detector.detect(game);result['table_profile']=aligner.profile
        result=arrange_table(result,game.shape)
        native=cv2.resize(game,(1918,round(game.shape[0]*1918/game.shape[1])))
        cv2.imwrite(str(args.output/'source'/f'{t:04d}.png'),frame)
        cv2.imwrite(str(args.output/'review'/f'{t:04d}.png'),native)
        actual=[c['card'] for c in result['board']+result['player_hand']]
        inventory.append(dict(time=t,profile=aligner.profile,ready=aligner.alignment_ready,
                              viewport=viewport,actual=actual,cards=result['cards'],ms=result['processing_ms']))
        row=np.full((165,1080,3),35,np.uint8)
        cv2.putText(row,f'{t:03d}s', (8,22),0,.65,(255,255,255),1)
        row[32:162,0:630]=native[365:495,650:1280]
        row[40:140,650:1000]=native[700:800,800:1150]
        # Predictions stay in the JSON; visual transcription must use the pixels.
        sheets.append(row)
        if len(sheets)==10:
            cv2.imwrite(str(args.output/f'sheet-{sheet_index:02d}.png'),np.vstack(sheets))
            sheet_index+=1;sheets=[]
            print(f'Baseline through {t}s',flush=True)
    cap.release()
    if sheets:cv2.imwrite(str(args.output/f'sheet-{sheet_index:02d}.png'),np.vstack(sheets))
    with args.video.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
    report=dict(source=str(args.video),source_sha256=digest,duration=total/fps,fps=fps,frames=inventory,
        protocol='Baseline proposals are diagnostic only; annotations must be visually reviewed.')
    (args.output/'inspection.json').write_text(json.dumps(report,indent=2))
    print('Extracted',len(inventory),'frames',flush=True)

if __name__=='__main__':main()

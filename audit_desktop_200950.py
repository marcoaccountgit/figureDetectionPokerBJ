"""Sample the video for operational gaps; this is not labelled accuracy."""
import argparse,json,time
from pathlib import Path
from collections import Counter
from card_detector import cv2,np
from capture_alignment import CaptureAligner
from table_layout import arrange_table

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('video',type=Path)
 p.add_argument('--model-dir',type=Path);p.add_argument('--step',type=int,default=5);args=p.parse_args()
 import learned_detector,download_model
 if args.model_dir:learned_detector.MODEL_DIR=download_model.MODEL_DIR=args.model_dir.resolve()
 detector=learned_detector.LearnedCardDetector('pokerstars-nine');aligner=CaptureAligner()
 root=Path(__file__).resolve().parent/'artifacts/desktop-200950';out=root/'audit';out.mkdir(exist_ok=True)
 cap=cv2.VideoCapture(str(args.video));rows=[];counts=Counter();times=[]
 try:
  for t in range(0,720,args.step):
   cap.set(cv2.CAP_PROP_POS_MSEC,t*1000);ok,frame=cap.read()
   if not ok:break
   frame=cv2.resize(frame,(1280,round(frame.shape[0]*1280/frame.shape[1])))
   start=time.perf_counter();game,viewport=aligner.align(frame)
   if not aligner.alignment_ready:
    counts['suspended']+=1;rows.append(dict(time=t,ready=False));continue
   r=detector.detect(game);r['table_profile']=aligner.profile;r=arrange_table(r,game.shape)
   elapsed=(time.perf_counter()-start)*1000;times.append(elapsed)
   cards=[c['card'] for c in r['board']+r['player_hand'] if c['accepted']]
   duplicates=len(cards)!=len(set(cards));gaps=[]
   # Flag clearly white index strips without an accepted reading for review.
   native=cv2.resize(game,(1918,round(game.shape[0]*1918/game.shape[1])))
   boxes=[(696+110*i,397,729+110*i,463) for i in range(5)]+[(863,723,895,786),(967,723,999,786)]
   for i,(x,y,right,bottom) in enumerate(boxes):
    image=native[y:bottom,x:right]
    if not image.size:continue
    hsv=cv2.cvtColor(image,cv2.COLOR_BGR2HSV)
    white=float(np.mean((hsv[:,:,1]<65)&(hsv[:,:,2]>180)))
    if white>.55 and not (r['board']+r['player_hand'])[i]['accepted']:gaps.append(i)
   counts['analyzed']+=1;counts['duplicates']+=duplicates;counts['white_index_gaps']+=bool(gaps)
   counts['cards_accepted']+=len(cards)
   row=dict(time=t,ready=True,profile=aligner.profile,cards=cards,duplicates=duplicates,gaps=gaps,processing_ms=round(elapsed,2))
   rows.append(row)
   if duplicates:
    row['readings']=r['cards'];row['viewport']=viewport
    cv2.imwrite(str(out/f'{t:04d}-game.png'),game)
   if duplicates or gaps:cv2.imwrite(str(out/f'{t:04d}.jpg'),frame)
 finally:cap.release()
 report=dict(counts=dict(counts),median_ms=float(np.median(times)),p95_ms=float(np.percentile(times,95)),frames=rows,
  caveat='Unlabelled operational sampling; white-face heuristic and duplicate checks do not establish recognition accuracy.')
 (root/'audit.json').write_text(json.dumps(report,indent=2));print(json.dumps({k:v for k,v in report.items() if k!='frames'},indent=2))

if __name__=='__main__':main()

"""Extract original review frames and card contact sheets; no pseudo labels."""
from pathlib import Path
import argparse,hashlib,json
from card_detector import cv2,np
from capture_alignment import CaptureAligner

def main():
 p=argparse.ArgumentParser();p.add_argument('video',type=Path);args=p.parse_args()
 out=Path('artifacts/desktop-200950');(out/'review').mkdir(parents=True,exist_ok=True)
 cap=cv2.VideoCapture(str(args.video));rows=[];inventory=[]
 for t in sorted(set(range(0,720,15))|{640,695}):
  cap.set(cv2.CAP_PROP_POS_MSEC,t*1000);ok,frame=cap.read()
  if not ok:break
  a=CaptureAligner();game,viewport=a.align(frame)
  native=cv2.resize(game,(1918,round(game.shape[0]*1918/game.shape[1])))
  cv2.imwrite(str(out/'review'/f'{t:04d}.jpg'),native,[cv2.IMWRITE_JPEG_QUALITY,98])
  row=np.full((185,1000,3),35,np.uint8)
  cv2.putText(row,f'{t}s {a.profile} ready={a.alignment_ready}',(8,22),0,.6,(255,255,255),1)
  row[30:180,:630]=native[360:510,650:1280]
  row[40:140,650:960]=native[700:800,810:1120]
  rows.append(row);inventory.append(dict(time=t,profile=a.profile,ready=a.alignment_ready,viewport=viewport))
  if len(rows)==8:
   cv2.imwrite(str(out/f'review-{t//120:02d}.jpg'),np.vstack(rows));rows=[]
 if rows:cv2.imwrite(str(out/'review-last.jpg'),np.vstack(rows))
 cap.release()
 with args.video.open('rb') as stream:checksum=hashlib.file_digest(stream,'sha256').hexdigest()
 (out/'inspection.json').write_text(json.dumps(dict(source=args.video.name,source_sha256=checksum,frames=inventory),indent=2))
 print('Review frames:',len(inventory))

if __name__=='__main__':main()

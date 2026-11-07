"""Runtime evaluation of manually reviewed video frames and preserved holdouts."""
import argparse,json,time
from pathlib import Path
from collections import Counter
from card_detector import cv2,np
from capture_alignment import CaptureAligner
from table_layout import arrange_table

ROOT=Path(__file__).resolve().parent

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--model-dir',type=Path)
 p.add_argument('--output',type=Path,required=True);p.add_argument('--widths',default='1918,1280,960');args=p.parse_args()
 import learned_detector,download_model
 if args.model_dir:
  learned_detector.MODEL_DIR=download_model.MODEL_DIR=args.model_dir.resolve()
 detector=learned_detector.LearnedCardDetector('pokerstars-nine')
 spec=json.loads((ROOT/'datasets/desktop-200950.json').read_text());counts=Counter();rows=[];errors=[]
 for entry in spec['frames']:
  source=cv2.imread(str(ROOT/'artifacts/desktop-200950/review'/f'{entry["time"]:04d}.jpg'))
  for width in map(int,args.widths.split(',')):
   frame=cv2.resize(source,(width,round(source.shape[0]*width/source.shape[1])))
   a=CaptureAligner();game,viewport=a.align(frame);r=detector.detect(game);r['table_profile']=a.profile
   r=arrange_table(r,game.shape)
   actual=[c['card'] for c in r['board']+r['player_hand']]
   expected=entry['board']+[None]*(5-len(entry['board']))+entry['hole']+[None]*(2-len(entry['hole']))
   prefix=entry['split']
   counts[prefix+'_slots']+=7;counts[prefix+'_slots_correct']+=sum(x==y for x,y in zip(actual,expected))
   counts[prefix+'_visible']+=sum(x is not None for x in expected)
   counts[prefix+'_visible_correct']+=sum(x==y and y is not None for x,y in zip(actual,expected))
   if entry['profile'] is not None:
    counts['profiles']+=1;counts['profiles_correct']+=a.profile==entry['profile']
   row=dict(time=entry['time'],split=prefix,width=width,profile=a.profile,actual=actual,expected=expected)
   rows.append(row)
   if actual!=expected:errors.append(row)
 # Historical holdouts are rebuilt in their original crop coordinates.
 old=ROOT/'artifacts/nine-seat-125816/dataset-reviewed';names=detector.names
 for split in ('val','test'):
  for path in sorted((old/'images'/split).glob('*.jpg')):
   crop=cv2.imread(str(path));image=np.zeros((1198,1918,3),np.uint8);image[360:900,650:1280]=crop
   result=detector.detect(image)
   actual=sorted(c['card'] for c in result['cards'] if c['accepted'])
   expected=sorted(names[int(line.split()[0])] for line in (old/'labels'/split/(path.stem+'.txt')).read_text().splitlines())
   counts['legacy_frames']+=1;counts['legacy_frames_correct']+=actual==expected
   if actual!=expected:errors.append(dict(legacy=path.name,actual=actual,expected=expected))
 args.output.parent.mkdir(exist_ok=True,parents=True)
 args.output.write_text(json.dumps(dict(model_sha256=download_model.model_manifest('pokerstars-nine')['files'][0]['sha256'],counts=dict(counts),errors=errors,frames=rows,
  protocol='Manual annotations; hands split before training; selected reviewed frames, not full-video accuracy'),indent=2))
 print(json.dumps(dict(counts=dict(counts),errors=errors),indent=2))

if __name__=='__main__':main()

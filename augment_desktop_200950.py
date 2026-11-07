"""Additional TRAIN-only low-resolution samples; held-out hands stay untouched."""
import json
from pathlib import Path
from card_detector import cv2
from prepare_table_dataset import annotations_for,write_sample

def main():
 root=Path(__file__).resolve().parent;out=root/'artifacts/desktop-200950/dataset'
 spec=json.loads((root/'datasets/desktop-200950.json').read_text())
 names=json.loads((out/'data.yaml').read_text())['names'];inventory=[]
 for e in spec['frames']:
  if e['split']!='train':continue
  image=cv2.imread(str(root/'artifacts/desktop-200950/review'/f'{e["time"]:04d}.jpg'))
  x,y,r,b=spec['crop'];crop=image[y:b,x:r];labels=annotations_for(e,spec,names)
  for scale in (.5,.4):
   stem=f'real_200950_{e["time"]:04d}_{scale:.1f}'
   write_sample(out,'train',stem,cv2.resize(crop,None,fx=scale,fy=scale,interpolation=cv2.INTER_AREA),labels)
   inventory.append(dict(file=stem,time=e['time'],hand=e['hand'],scale=scale))
 for cache in out.rglob('*.cache'):cache.unlink()
 manifest=json.loads((out/'manifest.json').read_text());manifest['low_resolution_training']=inventory
 (out/'manifest.json').write_text(json.dumps(manifest,indent=2))
 print('Additional lower-resolution train samples:',len(inventory))

if __name__=='__main__':main()

"""Reviewed labels from the 200950 recording, mixed with preserved replay."""
import argparse,hashlib,json,shutil
from pathlib import Path
from collections import Counter
from card_detector import cv2
from prepare_table_dataset import annotations_for,write_sample

ROOT=Path(__file__).resolve().parent
# Manually transcribed from the original contact sheets, not model predictions.
REVIEW=[
 (0,1,'','KS 6C'),(15,1,'QC 4S 3C','KS 6C'),(30,2,'','QH 7S'),
 (45,3,'6H 8D 8H',''),(75,4,'','10H 8S'),(90,5,'3C 10S 9C','6D 5C'),
 (105,6,'','9S 8H'),(120,7,'9H 10D 3D','KS 10S'),(135,7,'9H 10D 3D QS','KS 10S'),
 (150,7,'9H 10D 3D QS','KS 10S'),(165,8,'','AC QC'),(180,8,'7C 5H 5S 4D','AC QC'),
 (195,9,'','KD 10H'),(210,9,'','KD 10H'),(225,9,'10C QS 9S','KD 10H'),
 (240,9,'10C QS 9S 9D 5S','KD 10H'),(255,10,'',''),(270,11,'','7C 6D'),
 (285,12,'','QH 2H'),(300,13,'7S JS 3S','8D 7D'),(315,14,'','KS 3S'),
 (330,14,'8D JH 2C JD','KS 3S'),(345,14,'8D JH 2C JD 9S','KS 3S'),
 (360,15,'','KS 8S'),(390,15,'10C 6C 8D','KS 8S'),(405,15,'10C 6C 8D 9C','KS 8S'),
 (420,16,'','QS 7C'),(435,17,'','10H 10D'),(450,17,'4D 6C QC','10H 10D'),
 (465,18,'','9S 9C'),(480,18,'','9S 9C'),(495,19,'2C 5C JH','8H 4D'),
 (510,19,'2C 5C JH 6H','8H 4D'),(525,23,'',''),(540,20,'','3S 3C'),
 (555,20,'5S 8C 2C 2D','3S 3C'),(570,24,'',''),(585,24,'',''),
 (600,21,'','10C 9C'),(615,21,'JC JD KS','10C 9C'),(630,21,'JC JD KS 5C 9H','10C 9C'),
 (645,22,'','KC KD'),(660,22,'','KC KD'),(675,22,'7H 4D 5H','KC KD'),
 (690,22,'7H 4D 5H KS','KC KD'),(705,22,'7H 4D 5H KS 3D','KC KD'),
 (640,25,'','6H 4C'),(695,22,'7H 4D 5H KS','KC KD')]

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('video',type=Path);args=p.parse_args()
 source=ROOT/'artifacts/nine-seat-125816/dataset-reviewed'
 out=ROOT/'artifacts/desktop-200950/dataset'
 if out.exists():raise ValueError('Dataset already exists')
 shutil.copytree(source,out)
 for cache in out.rglob('*.cache'):cache.unlink()
 spec=json.loads((ROOT/'datasets/nine-seat-125816.json').read_text())
 with args.video.open('rb') as stream:checksum=hashlib.file_digest(stream,'sha256').hexdigest()
 inspection=json.loads((ROOT/'artifacts/desktop-200950/inspection.json').read_text())
 if not isinstance(inspection,dict) or inspection.get('source_sha256')!=checksum:
  raise ValueError('Run the inspection on this video before building reviewed labels')
 spec.update(source=args.video.name,source_sha256=checksum,max_time_exclusive=720,
             source_size=[1920,1140],annotation_revision='200950-manual-v1',frames=[])
 names=json.loads((out/'data.yaml').read_text())['names'];inventory=[]
 for t,hand,board,hole in REVIEW:
  split='test' if hand in (5,13,20) else 'val' if hand in (2,11,17) else 'train'
  entry=dict(time=t,hand=f'200950-{hand}',split=split,board=board.split(),hole=hole.split(),
             profile=None if t in (255,570) else 'pokerstars-desktop-six')
  if t==705:entry['revealed_opponents']=['JH','JD','4H','6H']
  spec['frames'].append(entry)
  image=cv2.imread(str(ROOT/'artifacts/desktop-200950/review'/f'{t:04d}.jpg'))
  labels=annotations_for(entry,spec,names);x,y,r,b=spec['crop'];crop=image[y:b,x:r]
  for scale in ((1.,.8,.6) if split=='train' else (1.,)):
   im=cv2.resize(crop,None,fx=scale,fy=scale,interpolation=cv2.INTER_AREA)
   stem=f'real_200950_{t:04d}_{scale:.1f}'
   write_sample(out,split,stem,im,labels)
   inventory.append(dict(file=stem,time=t,split=split,hand=entry['hand'],scale=scale,codes=entry['board']+entry['hole']))
 data=json.loads((out/'data.yaml').read_text());data['path']=str(out.resolve()).replace('\\','/')
 (out/'data.yaml').write_text(json.dumps(data,indent=2))
 manifest=json.loads((out/'manifest.json').read_text())
 manifest['replay_source']={k:manifest.get(k) for k in ('source','source_sha256','cutoff_seconds','annotation_revision')}
 manifest.pop('cutoff_seconds',None)
 manifest.update(source=args.video.name,source_sha256=spec['source_sha256'],source_duration_seconds=719.9333333333,
  annotation_revision=spec['annotation_revision'],new_real=inventory,new_frames_by_split=dict(Counter(x['split'] for x in inventory)),
  new_training_codes=sorted({c for x in inventory if x['split']=='train' for c in x['codes']}),
  protocol='Manual labels; complete hands separated across train/val/test; preserved old replay; lower-resolution training only')
 (out/'manifest.json').write_text(json.dumps(manifest,indent=2))
 (ROOT/'datasets/desktop-200950.json').write_text(json.dumps(spec,indent=2))
 print(json.dumps({k:manifest[k] for k in ('new_frames_by_split','new_training_codes')},indent=2))

if __name__=='__main__':main()

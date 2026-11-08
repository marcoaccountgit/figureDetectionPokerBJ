"""Visually reviewed 212305 recording; hard cases plus preserved old replay."""
import hashlib, json, shutil
from collections import Counter
from pathlib import Path
from card_detector import cv2
from prepare_table_dataset import annotations_for, write_sample

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'artifacts/desktop-212305'

def reviewed_frames():
    rows=[]
    def add(times,hand,board='',hole=''):
        split='val' if hand in (3,8) else 'test' if hand in (4,10) else 'train'
        for t in times:
            rows.append(dict(time=t,hand=f'212305-{hand}',split=split,board=board.split(),hole=hole.split(),profile='pokerstars-desktop-six'))
    add([0],1,'3S 8D 7H 9C');add([5,10],1,'3S 8D 7H 9C 6C')
    add([15,20,25],2,hole='10D 2D');add([30,35,45,50],2,'5C 9D 10H','10D 2D')
    add([55],2,'5C 9D 10H 9S','10D 2D');add([60,65,70],2,'5C 9D 10H 9S KC','10D 2D')
    add([85],3,hole='7H 6D');add([90,95],3)
    add([105,115,120],4);add([110],4,hole='10D 8C')
    add([125,130,135],4,'4D 5S 3D');add([140,145],4,'4D 5S 3D KD');add([150],4,'4D 5S 3D KD 3C')
    add([155,170],5);add([160,165],5,hole='QS 6H')
    add([175,180,185],6,hole='QC QD');add([190,195],6,'7D 3C 4D','QC QD')
    add([200],6,'7D 3C 4D AH','QC QD');add([205,210,215],6,'7D 3C 4D AH 3D','QC QD')
    add([225],7,hole='JS 5D');add([230,235],7);add([240,245,250,255,260],7,'5H 6D 7S')
    add([265],7,'5H 6D 7S 9H');add([270,275,280,285,290],7,'5H 6D 7S 9H KC')
    add([295,300,305],8,hole='QC 10S');add([310,315],8,'7S 6D 6S','QC 10S');add([320],8,'7S 6D 6S')
    add([325,330,335,340,345],9,hole='KC QC');add([350,355,360],9,'6C 6S JS','KC QC')
    add([365,370],9,'6C 6S JS');add([380],9,'6C 6S JS AS 9D')
    add([385,390,395,400],10);add([405,410],10,'7D 10D JS');add([415,420],10,'7D 10D JS QD')
    add([425,430,435],10,'7D 10D JS QD 3C')
    add([440,445,450],11,hole='AH 3S');add([455,460],11)
    add([475,495],11,'4C AC 3D 9H');add([480,485,490],11,'4C AC 3D 9H','AH 3S')
    add([500,510],12);add([505],12,hole='7S 2H');add([515,520],12,'KS KC QS')
    add([525,530],12,'KS KC QS 3H');add([535,540,545],12,'KS KC QS 3H 4C')
    add([555,560],13,hole='QS QC');add([565,570,575,580],13,'5C AH AS','QS QC')
    add([585],13,'5C AH AS 5H 4C','QS QC')
    return sorted(rows,key=lambda e:e['time'])

def main():
    inspection=json.loads((OUT/'inspection.json').read_text())
    previous=json.loads((ROOT/'datasets/desktop-200950.json').read_text())
    spec={k:previous[k] for k in ('size','crop','index_boxes')}
    spec.update(source=Path(inspection['source']).name,source_sha256=inspection['source_sha256'],
        source_size=[932,680],duration=inspection['duration'],annotation_revision='212305-manual-v1',
        frames=reviewed_frames(), excluded_times=[40,75,80,100,220,375,465,470,550,590,595],
        protocol='Visual transcription of original pixels, not pseudo labels. Complete hands separated; no holdout glyphs exported.')
    (ROOT/'datasets/desktop-212305.json').write_text(json.dumps(spec,indent=2))
    baseline={e['time']:e for e in inspection['frames']}
    failures=[]
    for e in spec['frames']:
        wanted=e['board']+[None]*(5-len(e['board']))+e['hole']+[None]*(2-len(e['hole']))
        actual=baseline[e['time']]['actual']
        if wanted!=actual:failures.append(dict(time=e['time'],split=e['split'],actual=actual,expected=wanted))
    (OUT/'baseline-errors.json').write_text(json.dumps(failures,indent=2))
    dataset=OUT/'dataset'
    if dataset.exists():raise ValueError('Dataset already exists')
    shutil.copytree(ROOT/'artifacts/desktop-200950/dataset',dataset)
    for cache in dataset.rglob('*.cache'):cache.unlink()
    data=json.loads((dataset/'data.yaml').read_text());names=data['names']
    selected=[];seen=Counter();bad={e['time'] for e in failures}
    for e in spec['frames']:
        signature=(e['hand'],tuple(e['board']),tuple(e['hole']))
        seen[signature]+=1
        # Retain both sides of the observed fold, even with identical board.
        if e['split']=='train' and seen[signature]>1 and e['time'] not in bad and e['time'] not in (215,370):continue
        image=cv2.imread(str(OUT/'review'/f"{e['time']:04d}.png"))
        x,y,r,b=spec['crop'];crop=image[y:b,x:r];labels=annotations_for(e,spec,names)
        for scale in ((1.,.7,.5,.4) if e['split']=='train' else (1.,)):
            stem=f"real_212305_{e['time']:04d}_{scale:.1f}"
            write_sample(dataset,e['split'],stem,cv2.resize(crop,None,fx=scale,fy=scale,interpolation=cv2.INTER_AREA),labels)
            selected.append(dict(file=stem,time=e['time'],hand=e['hand'],split=e['split'],scale=scale,codes=e['board']+e['hole'],baseline_error=e['time'] in bad))
    data['path']=str(dataset.resolve()).replace('\\','/')
    (dataset/'data.yaml').write_text(json.dumps(data,indent=2))
    old=json.loads((dataset/'manifest.json').read_text())
    manifest=dict(source=spec['source'],source_sha256=spec['source_sha256'],duration=inspection['duration'],
        annotation_revision=spec['annotation_revision'],replay_source=old,new_real=selected,
        new_frames_by_split=dict(Counter(e['split'] for e in selected)),
        new_training_codes=sorted({c for e in selected if e['split']=='train' for c in e['codes']}),
        protocol=spec['protocol'])
    (dataset/'manifest.json').write_text(json.dumps(manifest,indent=2))
    backup=OUT/'previous-model';backup.mkdir(exist_ok=False)
    for name in ('pokerstars-nine.onnx','pokerstars-nine.classes.json','pokerstars-nine.manifest.json'):
        shutil.copy2(ROOT/'models'/name,backup/name)
    shutil.copytree(ROOT/'models/pokerstars-nine-symbols',backup/'pokerstars-nine-symbols')
    print(json.dumps(dict(reviewed=len(spec['frames']),baseline_errors=failures,new_counts=manifest['new_frames_by_split']),indent=2))

if __name__=='__main__':main()

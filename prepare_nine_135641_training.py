"""Build a candidate dataset with old replay and disjoint reviewed new hands."""
from collections import Counter
import json
from pathlib import Path
import shutil
from card_detector import cv2
from capture_alignment import CaptureAligner
from prepare_table_dataset import annotations_for, write_sample


def main():
    root=Path('artifacts/nine-135641')
    spec=json.loads(Path('datasets/nine-135641.json').read_text())
    geometry=json.loads(Path('datasets/desktop-212305.json').read_text())
    dataset=root/'dataset'
    if dataset.exists():raise ValueError('Candidate dataset already exists')
    shutil.copytree('artifacts/desktop-212305/dataset',dataset)
    for path in dataset.rglob('*.cache'):path.unlink()
    data=json.loads((dataset/'data.yaml').read_text())
    names=data['names'];seen=set();inventory=[]
    for row in spec['frames']:
        if row['split']=='test' or row['time']==125:continue
        signature=(row['hand'],tuple(row['board']),tuple(row['hole']))
        if signature in seen and row['time'] not in (255,400):continue
        seen.add(signature)
        a=CaptureAligner();game,_=a.align(cv2.imread(str(root/'source'/f'{row["time"]:06.1f}.png')))
        native=cv2.resize(game,(1918,round(game.shape[0]*1918/game.shape[1])))
        x,y,r,b=geometry['crop'];image=native[y:b,x:r]
        labels=annotations_for(row,geometry,names)
        for scale in ((1,.7,.5,.4) if row['split']=='train' else (1,)):
            stem=f'real_135641_{row["time"]:04d}_{scale:.1f}'
            write_sample(dataset,row['split'],stem,cv2.resize(image,None,fx=scale,fy=scale,interpolation=cv2.INTER_AREA),labels)
            inventory.append(dict(file=stem,time=row['time'],hand=row['hand'],split=row['split'],scale=scale,codes=row['board']+row['hole']))
    old=json.loads((dataset/'manifest.json').read_text())
    (dataset/'manifest.json').write_text(json.dumps(dict(source=spec['source'],sha256=spec['sha256'],
        replay_source=old,real=inventory,annotation_revision='135641-manual-v1',
        protocol='Manual card slots; complete hands disjoint. No held-out pixels used for weights or symbol references.'),indent=2))
    data['path']=str(dataset.resolve()).replace('\\','/')
    (dataset/'data.yaml').write_text(json.dumps(data,indent=2))
    geometry.update(source=spec['source'],source_sha256=spec['sha256'],frames=spec['frames'])
    (root/'training-spec.json').write_text(json.dumps(geometry,indent=2))
    backup=root/'previous-model';backup.mkdir()
    manifest=json.loads(Path('models/pokerstars-nine.manifest.json').read_text())
    for name in ('pokerstars-nine.onnx','pokerstars-nine.classes.json','pokerstars-nine.manifest.json'):
        shutil.copy2(Path('models')/name,backup/name)
    shutil.copytree(Path('models')/manifest['symbol_references'],backup/manifest['symbol_references'])
    print(json.dumps(dict(new_samples=dict(Counter(row['split'] for row in inventory)),replay_preserved=True)))


if __name__=='__main__':main()

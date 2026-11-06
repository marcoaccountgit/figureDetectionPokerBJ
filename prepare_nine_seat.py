"""Build reviewed nine-seat data strictly before the disconnect cutoff."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from PIL import Image
from card_detector import cv2
from prepare_table_dataset import annotations_for, write_sample, stable_indices, index_ink, add_synthetic_replay

ROOT=Path(__file__).resolve().parent


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('video',type=Path)
    parser.add_argument('--output',type=Path,default=ROOT/'artifacts/nine-seat-125816/dataset')
    args=parser.parse_args()
    spec=json.loads((ROOT/'datasets/nine-seat-125816.json').read_text())
    with args.video.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
    if digest!=spec['source_sha256']:raise ValueError('Video differs from reviewed annotation source')
    names=json.loads((ROOT/'models/lgd-cards-gen3.classes.json').read_text())
    out=args.output;out.mkdir(parents=True,exist_ok=False)
    for kind in ('images','labels'):
        for split in ('train','val','test'):(out/kind/split).mkdir(parents=True)
    cap=cv2.VideoCapture(str(args.video))
    if [round(cap.get(3)),round(cap.get(4))]!=spec['size']:raise ValueError('Unexpected video dimensions')
    bank={'rank':{},'suit':{}};inventory=[];background=None
    crop=spec['crop'];x1,y1,x2,y2=crop
    splits={}
    for entry in spec['frames']:
        if entry['time']>=spec['max_time_exclusive']:raise ValueError('Frame after cutoff')
        if splits.setdefault(entry['hand'],entry['split'])!=entry['split']:raise ValueError('Hand leaks across splits')
        cap.set(cv2.CAP_PROP_POS_MSEC,entry['time']*1000);ok,reference=cap.read()
        if not ok:raise ValueError('Frame unavailable')
        if entry['time']==30:background=reference[y1:y2,x1:x2].copy()
        labels=annotations_for(entry,spec,names)
        if entry['split']=='train':
            for group in ('board','hole'):
                for code,(a,b,c,d) in zip(entry[group],spec['index_boxes'][group]):
                    index=reference[b:d,a:c]
                    for kind,key,region in [('rank',code[:-1],index[:35]),('suit',code[-1],index[35:])]:
                        bank[kind].setdefault(key,index_ink(region))
        offsets=(-.4,-.2,0,.2,.4) if entry['split']=='train' else (0,)
        for delta in offsets:
            actual=entry['time']+delta
            if not 0<=actual<spec['max_time_exclusive']:continue
            cap.set(cv2.CAP_PROP_POS_MSEC,actual*1000);ok,frame=cap.read()
            if not ok or delta and not stable_indices(reference,frame,entry,spec):continue
            stem=f'real_{entry["time"]:04d}_{actual:.1f}'
            write_sample(out,entry['split'],stem,frame[y1:y2,x1:x2],labels)
            inventory.append(dict(file=stem,time=actual,split=entry['split'],hand=entry['hand'],codes=entry['board']+entry['hole']))
    cap.release()
    add_synthetic_replay(out,background,names,bank)
    # Preserve glyph provenance separately from replay images.
    glyphs=out/'reviewed-glyphs'
    for kind,values in bank.items():
        (glyphs/kind).mkdir(parents=True)
        for code,mask in values.items():mask.save(glyphs/kind/(code+'.png'))
    data=dict(path=str(out.resolve()).replace('\\','/'),train='images/train',val='images/val',test='images/test',names=names)
    (out/'data.yaml').write_text(json.dumps(data,indent=2))
    manifest=dict(source=args.video.name,source_sha256=digest,cutoff_seconds=840,real=inventory,
                  annotation_revision=spec['annotation_revision'],
                  real_frames_by_split=dict(Counter(e['split'] for e in inventory)),
                  real_training_codes=sorted({c for e in inventory if e['split']=='train' for c in e['codes']}),
                  glyph_source='training hands only',synthetic_train_frames=156)
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2))
    print(json.dumps({k:v for k,v in manifest.items() if k!='real'},indent=2))


if __name__=='__main__':main()

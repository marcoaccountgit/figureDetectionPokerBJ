"""Compare candidate weights and symbol bank against a preserved runtime model."""
import argparse, hashlib, json, statistics
from collections import Counter
from pathlib import Path
from time import perf_counter
import download_model, learned_detector
from card_detector import cv2
from capture_alignment import CaptureAligner
from table_layout import arrange_table


def load_model(path):
    original=(learned_detector.MODEL_DIR,download_model.MODEL_DIR)
    try:
        learned_detector.MODEL_DIR=download_model.MODEL_DIR=path.resolve()
        return learned_detector.LearnedCardDetector('pokerstars-nine')
    finally:
        learned_detector.MODEL_DIR,download_model.MODEL_DIR=original


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--candidate',type=Path,required=True)
    p.add_argument('--baseline',type=Path,default=Path('artifacts/desktop-212305/previous-model'))
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    models={'before':load_model(args.baseline),'after':load_model(args.candidate)}
    samples=[]
    for dataset,widths in (('desktop-212305',(932,762)),('desktop-200950',(960,1280))):
        spec=json.loads(Path(f'datasets/{dataset}.json').read_text())
        for entry in spec['frames']:
            path=Path(f'artifacts/{dataset}/source/{entry["time"]:04d}.png') if dataset=='desktop-212305' else Path(f'artifacts/{dataset}/review/{entry["time"]:04d}.jpg')
            original=cv2.imread(str(path))
            if original is None:raise ValueError(f'Missing {path}')
            for width in widths:
                frame=cv2.resize(original,(width,round(original.shape[0]*width/original.shape[1])))
                a=CaptureAligner();game,_=a.align(frame)
                wanted=entry['board']+[None]*(5-len(entry['board']))+entry['hole']+[None]*(2-len(entry['hole']))
                samples.append((dataset,entry,width,a.profile,game,wanted))
    for model in models.values():model.detect(samples[0][4])
    rows=[]
    for index,(dataset,entry,width,profile,game,wanted) in enumerate(samples):
        row=dict(dataset=dataset,time=entry['time'],split=entry['split'],width=width,expected=wanted)
        for name in (('before','after') if index%2==0 else ('after','before')):
            start=perf_counter();result=models[name].detect(game);ms=(perf_counter()-start)*1000
            result['table_profile']=profile;arranged=arrange_table(result,game.shape)
            actual=[c['card'] for c in arranged['board']+arranged['player_hand']]
            sources=Counter(c.get('decision_source') for c in arranged['cards'] if c.get('accepted') and c.get('table_group') in ('board','player_hand'))
            neural_ready=sum(c.get('accepted') and c.get('table_group') in ('board','player_hand') and
                (c.get('decision_source')=='model' or
                 c.get('neural_candidate')==c.get('card') and c.get('neural_confidence',0) is not None and
                 c.get('neural_confidence',0)>=.60 and c.get('class_margin',0)>=.15)
                for c in arranged['cards'])
            row[name]=dict(actual=actual,ms=ms,sources=dict(sources),retries=result.get('uncertain_retries',0),neural_ready=neural_ready)
        rows.append(row)
        if (index+1)%25==0:print('Evaluated',index+1,'/',len(samples),flush=True)
    summary={}
    for dataset in ('desktop-212305','desktop-200950'):
        summary[dataset]={}
        for name in models:
            entries=[r for r in rows if r['dataset']==dataset]
            counts=Counter()
            for r in entries:
                counts.update(r[name]['sources'])
            summary[dataset][name]=dict(frames=len(entries),
                visible=sum(e is not None for r in entries for e in r['expected']),
                visible_correct=sum(a==e and e is not None for r in entries for a,e in zip(r[name]['actual'],r['expected'])),
                wrong_accepted=sum(a is not None and a!=e for r in entries for a,e in zip(r[name]['actual'],r['expected'])),
                exact_frames=sum(r[name]['actual']==r['expected'] for r in entries),
                mean_ms=statistics.mean(r[name]['ms'] for r in entries),
                median_ms=statistics.median(r[name]['ms'] for r in entries),sources=dict(counts),
                neural_ready=sum(r[name]['neural_ready'] for r in entries),
                retries=sum(r[name]['retries'] for r in entries))
            held=[r for r in entries if r['split'] in ('val','test')]
            summary[dataset][name]['holdout']=dict(frames=len(held),visible=sum(e is not None for r in held for e in r['expected']),
                visible_correct=sum(a==e and e is not None for r in held for a,e in zip(r[name]['actual'],r['expected'])))
    with (args.candidate/'pokerstars-nine.onnx').open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
    errors=[r for r in rows if r['after']['actual']!=r['expected']]
    regressions=[r for r in rows if any(
        (before==expected and after!=expected) or (after is not None and after!=expected and after!=before)
        for before,after,expected in zip(r['before']['actual'],r['after']['actual'],r['expected']))]
    report=dict(candidate_sha256=digest,summary=summary,errors=errors,regressions=regressions,rows=rows,
        protocol='Visually reviewed labels, full-hand splits. Includes train examples; accuracy is not an independent full-video estimate. Paired timings include retries and symbol recovery, exclude decoding/alignment.')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2))
    print(json.dumps(dict(summary=summary,regressions=regressions,error_count=len(errors)),indent=2),flush=True)


if __name__=='__main__':main()

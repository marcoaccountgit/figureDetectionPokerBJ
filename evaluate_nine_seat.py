"""Evaluate reviewed nine-seat frames; never decode after the 840-second cutoff."""
import argparse,json
from collections import Counter
from pathlib import Path
from card_detector import cv2
from capture_alignment import CaptureAligner
from learned_detector import LearnedCardDetector
from table_layout import arrange_table
from opponent_detector import OpponentDetector
from table_observer import TableVisualReader,WindowsOCR

ROOT=Path(__file__).resolve().parent


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('video',type=Path)
    p.add_argument('--no-ocr',action='store_true');p.add_argument('--widths',default='1918,1280')
    p.add_argument('--output',type=Path,default=ROOT/'artifacts/nine-seat-125816/evaluation')
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    spec=json.loads((ROOT/'datasets/nine-seat-125816.json').read_text())
    expected=json.loads((ROOT/'datasets/nine-seat-observations.json').read_text())
    obs_by_time={r['time']:r for r in expected['frames']}
    detector=LearnedCardDetector('pokerstars-nine');opponents=OpponentDetector()
    reader=None if args.no_ocr else TableVisualReader(WindowsOCR(),'pokerstars-nine')
    cap=cv2.VideoCapture(str(args.video));reports=[];counts=Counter();errors=[]
    def check(key,actual,wanted,time,width):
        counts[key+'_total']+=1
        if actual==wanted:counts[key+'_correct']+=1
        else:errors.append(dict(metric=key,time=time,width=width,actual=actual,expected=wanted))
    try:
        for entry in spec['frames']:
            timestamp=entry['time']
            if not 0<=timestamp<840:raise ValueError('Frame outside authorized interval')
            cap.set(cv2.CAP_PROP_POS_MSEC,timestamp*1000);ok,source=cap.read()
            if not ok:raise ValueError(f'Cannot decode {timestamp}')
            for width in map(int,args.widths.split(',')):
                im=cv2.resize(source,(width,round(source.shape[0]*width/source.shape[1])))
                aligner=CaptureAligner();game,viewport=aligner.align(im)
                result=arrange_table(detector.detect(game),game.shape)
                check('profile',aligner.profile,'pokerstars-nine',timestamp,width)
                actual_board=[c['card'] if c['accepted'] else None for c in result['board']]
                actual_hero=[c['card'] if c['accepted'] else None for c in result['player_hand']]
                wanted_board=entry['board']+[None]*(5-len(entry['board']))
                wanted_hero=entry['hole']+[None]*(2-len(entry['hole']))
                for got,wanted in zip(actual_board+actual_hero,wanted_board+wanted_hero):
                    check('card_slots',got,wanted,timestamp,width)
                    if wanted is not None:check('visible_cards',got,wanted,timestamp,width)
                check('complete_board',actual_board,wanted_board,timestamp,width)
                other=[c['card'] for c in result['cards'] if c['accepted'] and c['table_group']=='other']
                if str(timestamp) in expected['revealed_cards']:
                    check('revealed_cards',sorted(other),sorted(expected['revealed_cards'][str(timestamp)]),timestamp,width)
                backs=opponents.detect(game,profile=aligner.profile)
                if str(timestamp) in expected['covered_seats']:
                    wanted=expected['covered_seats'][str(timestamp)]
                    for seat in backs:check('covered_seats',seat['present'],seat['seat'] in wanted,timestamp,width)
                observation=None
                if reader and width==1918:
                    observation=reader.read(game);review=obs_by_time[timestamp]
                    if 'pot' in review:check('pot',observation['pot']['value'] if observation['pot'] else None,review['pot'],timestamp,width)
                    if 'button' in review:check('button',observation['button']['seat'],review['button'],timestamp,width)
                    for group,field in [('actions','action'),('stacks','stack'),('wagers','wager')]:
                        for seat,wanted in review.get(group,{}).items():
                            got=next(s[field] for s in observation['seats'] if s['seat']==seat)
                            if field!='action':got=got['value'] if got else None
                            check(group,got,wanted,timestamp,width)
                reports.append(dict(time=timestamp,width=width,split=entry['split'],board=actual_board,hero=actual_hero,other=other,observation=observation))
                print(timestamp,width,actual_board,actual_hero,'errors',len(errors),flush=True)
    finally:
        cap.release()
        if reader:reader.ocr.close()
    report=dict(cutoff_seconds=840,counts=dict(counts),errors=errors,frames=reports,
                caveat='Selected frames; calibration overlaps evaluation; not a full-video independent accuracy estimate.')
    (args.output/'report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(dict(counts=dict(counts),errors=errors),indent=2))


if __name__=='__main__':main()

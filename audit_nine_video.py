"""Sample the permitted first 14 minutes for coverage, not accuracy claims."""
import argparse,json
from collections import Counter
from pathlib import Path
from time import perf_counter
from card_detector import cv2
from capture_alignment import CaptureAligner
from learned_detector import LearnedCardDetector
from table_layout import arrange_table
from table_observer import TableVisualReader,WindowsOCR


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('video',type=Path)
    p.add_argument('--step',type=int,default=5);args=p.parse_args()
    if args.step<=0:raise ValueError('Step must be positive')
    reader=TableVisualReader(WindowsOCR(),'pokerstars-nine');detector=LearnedCardDetector('pokerstars-nine')
    cap=cv2.VideoCapture(str(args.video));counts=Counter();rows=[];start=perf_counter()
    try:
        for t in range(0,840,args.step):
            cap.set(cv2.CAP_PROP_POS_MSEC,t*1000);ok,im=cap.read()
            if not ok:raise ValueError(f'Frame unavailable: {t}')
            aligner=CaptureAligner();game,viewport=aligner.align(im)
            result=arrange_table(detector.detect(game),game.shape);observation=reader.read(game)
            board=[c['card'] if c['accepted'] else None for c in result['board']]
            hero=[c['card'] if c['accepted'] else None for c in result['player_hand']]
            known=[c for c in board+hero if c is not None]
            actions=[(s['seat'],s['action']) for s in observation['seats'] if s['action']]
            counts.update(a for _,a in actions);counts['frames']+=1
            if len(known)!=len(set(known)):counts['duplicate_primary_cards']+=1
            if aligner.profile!='pokerstars-nine':counts['wrong_layout']+=1
            if observation['pot'] is None:counts['unread_pot_frames']+=1
            rows.append(dict(time=t,board=board,hero=hero,pot=observation['pot'],actions=actions,
                             processing_ms=result['processing_ms'],profile=aligner.profile))
            if t%60==0:print('Sampled through',t,'seconds',dict(counts),flush=True)
    finally:
        cap.release();reader.ocr.close()
    report=dict(cutoff_exclusive=840,step_seconds=args.step,counts=dict(counts),
                elapsed_seconds=round(perf_counter()-start,2),
                caveat='Coverage/consistency audit only. Unannotated frames do not measure recognition accuracy.',frames=rows)
    path=Path('artifacts/nine-seat-125816/timeline-audit.json');path.write_text(json.dumps(report,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k!='frames'},indent=2))


if __name__=='__main__':main()

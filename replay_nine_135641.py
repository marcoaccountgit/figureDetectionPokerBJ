"""Replay actual timestamps through live confirmation, memory and opponent tracking."""
import argparse,json
from pathlib import Path
from card_detector import cv2
from capture_alignment import CaptureAligner
from learned_detector import TableCardDetector
from browser_capture import live_confirmation
from temporal_cards import HandCardMemory
from hand_counter import HandCounter,player_card_presence
from live_card_cache import card_inference_needed,unconfirmed_card_frame
from opponent_detector import OpponentDetector,OpponentTracker
from table_layout import arrange_table
from table_observer import TableVisualReader


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,default=Path('artifacts/nine-135641/replay.json'))
    p.add_argument('--sample-fps',type=float,default=5)
    p.add_argument('--candidate',type=Path)
    p.add_argument('--start',type=float,default=0)
    args=p.parse_args()
    spec=json.loads(Path('datasets/nine-135641.json').read_text())
    expected={row['time']:row for row in spec['frames']}
    cap=cv2.VideoCapture(spec['source']);fps=cap.get(5)
    aligner=CaptureAligner();detector=TableCardDetector();opponents=OpponentDetector()
    if args.candidate:
        from evaluate_training_candidate import load_model
        detector.models['pokerstars-nine']=load_model(args.candidate)
    temporal=live_confirmation();memory=HandCardMemory();hands=HandCounter();tracker=OpponentTracker()
    reader=TableVisualReader(None,'pokerstars-nine')
    old_viewport=None;old_profile=None;rows=[]
    for index in range(int(cap.get(7))):
        if index/fps<args.start:
            if not cap.grab():break
            continue
        if index%round(fps/args.sample_fps):
            if not cap.grab():break
            continue
        ok,image=cap.read()
        if not ok:break
        t=round(index/fps,4)
        game,viewport=aligner.align(image);profile=aligner.profile;aligned=aligner.alignment_ready
        if old_profile is not None and profile!=old_profile:
            temporal=live_confirmation();memory=HandCardMemory();hands=HandCounter();tracker=OpponentTracker()
        elif old_viewport is not None and viewport!=old_viewport:
            memory.rescale(game.shape[1]/(old_viewport[2]-old_viewport[0]))
            temporal=live_confirmation();tracker=OpponentTracker();hands.reset_observations()
        old_viewport,old_profile=viewport,profile
        detector.profile=profile
        presence=player_card_presence(game,profile) if aligned else [dict(present=None)]*2
        needed,cache=card_inference_needed(game,memory,hands.active,presence,profile)
        result=detector.detect(unconfirmed_card_frame(game,memory,hands.active,profile,cache)) if aligned and needed else dict(cards=[],processing_ms=0)
        result['table_profile']=profile
        result=arrange_table(result,game.shape)
        cycle=hands.update(presence,result['player_hand'],t,board_cleared=cache.get('board_cleared',False))
        cycle['board_cleared']=cache.get('board_cleared',False)
        if cycle['started'] and cycle['count']>1:temporal=live_confirmation()
        result=temporal.update(result,t,game.shape)
        result=arrange_table(memory.update(result,cycle),game.shape)
        if cycle['started']:tracker=OpponentTracker()
        seats=opponents.detect(game,profile=profile)
        if not aligned:seats=[dict(s,present=None,bbox=None) for s in seats]
        tracked=tracker.update(seats,t,result['player_hand'])
        if index%round(fps)==0:
            reader.set_profile(profile) if reader.profile!=profile else None
            row=dict(time=t,profile=profile,aligned=aligned,hand_id=cycle['count'],active=cycle['active'],
                actual=[c['card'] for c in result['board']+result['player_hand']],count=tracked['count'],
                seat_states={s['seat']:s['in_hand'] for s in tracked['seats']},
                button=reader.dealer_button(game) if aligned else None,cache=cache)
            if t in expected:
                label=expected[t]
                row['expected']=label['board']+[None]*(5-len(label['board']))+label['hole']+[None]*(2-len(label['hole']))
                row['expected_count']=sum(label['seats'].values())
            rows.append(row)
            if t%40==0:print(f'Replayed {t:.0f}s',flush=True)
    cap.release()
    reviewed=[r for r in rows if 'expected' in r]
    report=dict(sample_fps=args.sample_fps,frames=rows,summary=dict(reviewed=len(reviewed),
        exact_cards=sum(r['actual']==r['expected'] for r in reviewed),
        exact_count=sum(r['count']==r['expected_count'] for r in reviewed),
        pending_count=sum(r['count'] is None for r in reviewed),
        wrong_count=sum(r['count'] is not None and r['count']!=r['expected_count'] for r in reviewed)),
        caveat='Replay of actual timestamps, not frozen frames. Changes need five observations; labels exist only at reviewed sample times.')
    args.output.write_text(json.dumps(report,indent=2))
    print(json.dumps(report['summary']))


if __name__=='__main__':main()

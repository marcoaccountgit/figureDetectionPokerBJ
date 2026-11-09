"""Preserve baseline proposals and visual sheets for manual video review."""
import argparse
import hashlib
import json
from pathlib import Path
from card_detector import cv2, np
from capture_alignment import CaptureAligner
from learned_detector import TableCardDetector
from opponent_detector import OpponentDetector
from table_layout import arrange_table
from table_profiles import NINE_BACKS
from hand_counter import player_card_presence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('video', type=Path)
    parser.add_argument('--step', type=float, default=5)
    parser.add_argument('--output', type=Path, default=Path('artifacts/nine-135641'))
    args = parser.parse_args()
    out = args.output
    for directory in ('source', 'review', 'cards', 'tables', 'backs'):
        (out/directory).mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(str(args.video))
    fps, count = cap.get(5), int(cap.get(7))
    detector, opponents = TableCardDetector(), OpponentDetector()
    rows, table_rows, back_rows, inventory = [], [], [], []
    def flush():
        sheet = (len(inventory)-1)//8
        if rows:
            cv2.imwrite(str(out/'cards'/f'{sheet:02d}.jpg'), np.vstack(rows))
            cv2.imwrite(str(out/'backs'/f'{sheet:02d}.jpg'), np.vstack(back_rows))
            cv2.imwrite(str(out/'tables'/f'{sheet:02d}.jpg'), np.vstack(table_rows))
            rows.clear(); table_rows.clear(); back_rows.clear()
    for frame_index in range(count):
        if frame_index % round(fps*args.step):
            if not cap.grab():
                break
            continue
        ok, frame = cap.read()
        if not ok:
            break
        t = frame_index/fps
        aligner = CaptureAligner()
        game, viewport = aligner.align(frame)
        detector.profile = aligner.profile
        result = arrange_table(detector.detect(game), game.shape)
        seats = opponents.detect(game, profile=aligner.profile)
        cv2.imwrite(str(out/'source'/f'{t:06.1f}.png'), frame)
        canonical = cv2.resize(game, (1762, round(game.shape[0]*1762/game.shape[1])))
        cv2.imwrite(str(out/'review'/f'{t:06.1f}.png'), canonical)
        inventory.append(dict(time=t,profile=aligner.profile,ready=aligner.alignment_ready,
            viewport=viewport,actual=[c['card'] for c in result['board']+result['player_hand']],
            cards=result['cards'],seats=seats,presence=player_card_presence(game,aligner.profile)))
        row = np.full((180, 1050, 3), 35, np.uint8)
        cv2.putText(row, f'{t:.1f}s', (5,22), 0, .65, (255,255,255), 1)
        row[35:165,:630] = canonical[330:460,600:1230]
        row[45:165,650:1000] = canonical[625:745,760:1110]
        rows.append(row)
        table = cv2.resize(frame, (480,350))
        cv2.putText(table, f'{t:.1f}s', (5,25), 0, .8, (0,255,255), 2)
        table_rows.append(table)
        back = np.full((105, 1440, 3), 35, np.uint8)
        for i,(key,(x,y,r,b)) in enumerate(NINE_BACKS.items()):
            patch = canonical[max(0,y-10):b+10,max(0,x-5):r+5]
            back[25:105,i*180:(i+1)*180] = cv2.resize(patch,(180,80))
            cv2.putText(back, key if i else f'{t:.0f}s {key}', (i*180,18),0,.43,(255,255,255),1)
        back_rows.append(back)
        if len(rows)==8:
            flush()
            print(f'Inspected {t:.0f}s / {count/fps:.1f}s',flush=True)
    flush();cap.release()
    with args.video.open('rb') as stream:
        digest = hashlib.file_digest(stream,'sha256').hexdigest()
    (out/'baseline.json').write_text(json.dumps(dict(source=str(args.video),sha256=digest,
        duration=count/fps,fps=fps,frames=inventory,
        protocol='Predictions are proposals only. Labels require visual review; split by complete hands.'),indent=2))


if __name__ == '__main__':
    main()

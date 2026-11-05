"""Validate physical player-card presence and replay the preserved fold sequence."""
import argparse
import json
from hashlib import sha256
from pathlib import Path

from card_detector import cv2
from hand_counter import HandCounter, player_card_presence

ROOT = Path(__file__).resolve().parent


def evaluate():
    cases = []
    for source in ('211955','213508','capture10'):
        spec = json.loads((ROOT/f'datasets/table-{source}.json').read_text())
        for entry in spec['frames']:
            t = entry['time']
            path = (ROOT/f'artifacts/capture10-improvement/dataset/reviewed/{t}.png' if source == 'capture10'
                    else ROOT/f'artifacts/table-{source}/inspection/{t:04d}.jpg')
            presence = player_card_presence(cv2.imread(str(path)))
            expected = [bool(entry['hole'])]*2
            actual = [s['present'] for s in presence]
            cases.append(dict(source=source,time=t,expected=expected,actual=actual,
                              exact=expected==actual,sha256=sha256(path.read_bytes()).hexdigest()))
    tracker = HandCounter()
    spec = json.loads((ROOT/'datasets/table-213508-sequence.json').read_text())
    replay = []
    for entry in spec['frames']:
        t = entry['time']
        path = ROOT/f'artifacts/sequence-improvement/inspection/fold-{t:.1f}.jpg'
        presence = player_card_presence(cv2.imread(str(path)))
        cycle = tracker.update(presence,[],t)
        expected = [bool(entry['hole'])]*2
        replay.append(dict(time=t,expected=expected,exact=expected==[s['present'] for s in presence],cycle=cycle))
    return dict(protocol='Preserved frames from existing recordings. Physical presence compared with reviewed hole-card annotations. Sparse frames are not replayed as continuous hands. Fold sequence replay uses original timestamps; it contains only four absent frames, so closure must remain pending until a fifth actual observation.',
                presence_frames=len(cases),exact_presence_frames=sum(c['exact'] for c in cases),
                fold_frames=len(replay),exact_fold_frames=sum(c['exact'] for c in replay),
                fold_count=tracker.count,fold_pending_samples=tracker.samples,cases=cases,fold_replay=replay)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'artifacts/hand-counter/report.json')
    args = parser.parse_args()
    report = evaluate()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('cases','fold_replay')}))
    if (report['exact_presence_frames'] != report['presence_frames']
            or report['exact_fold_frames'] != report['fold_frames'] or report['fold_count'] != 1):
        raise SystemExit(1)


if __name__ == '__main__':
    main()

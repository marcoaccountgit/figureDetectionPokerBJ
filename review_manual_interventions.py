"""Replay saved interventions without changing models or live sessions."""
import json
from pathlib import Path

from card_detector import cv2
from capture_alignment import CaptureAligner
from learned_detector import TableCardDetector
from table_layout import arrange_table
from hand_counter import player_card_presence


def main():
    root = Path('artifacts/manual-interventions')
    detector = TableCardDetector()
    rows = []
    for path in sorted(root.glob('*/analysis.json')):
        saved = json.loads(path.read_text(encoding='utf-8'))
        frame = cv2.imread(str(path.parent / 'screenshot.png'))
        aligner = CaptureAligner()
        game, _ = aligner.align(frame)
        detector.profile = aligner.profile
        result = arrange_table(detector.detect(game), game.shape)
        action = saved['action']
        row = dict(sample=path.parent.name, action=action['kind'],
                   profile=aligner.profile, alignment_ready=aligner.alignment_ready,
                   presence=player_card_presence(game, aligner.profile),
                   board=[c['card'] for c in result['board']],
                   player_hand=[c['card'] for c in result['player_hand']])
        if action['kind'] == 'card':
            group, slot = action['group'], action['slot']
            previous = saved['before'][group][slot]
            row.update(group=group, slot=slot, expected=action['card'],
                       before=previous['card'], current=result[group][slot]['card'])
        rows.append(row)
        print(json.dumps(row), flush=True)
    (root / 'replay-review.json').write_text(json.dumps(rows, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()

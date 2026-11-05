import json
from pathlib import Path
import unittest

from table_layout import arrange_table
from temporal_cards import TemporalCards

ROOT = Path(__file__).resolve().parents[1]


def detection(code, slot, confidence=.9, accepted=True):
    x = 595+116*slot
    return dict(card=code if accepted else None, accepted=accepted,
                confidence=confidence, bbox=[x, 402, x+40, 480])


class TableLayoutTests(unittest.TestCase):
    def arrange(self, cards, shape=(840, 1762, 3)):
        return arrange_table({'cards': cards, 'processing_ms': 1}, shape)

    def test_confidence_changes_and_turn_river_do_not_reorder_flop(self):
        temporal = TemporalCards()
        codes = ['JC', '2D', '5H', 'AD', 'KD']
        for frame, count in enumerate([3, 3, 4, 4, 5, 5]):
            cards = [detection(code, i, .6+.08*((i+frame) % 5))
                     for i, code in enumerate(codes[:count])][::-1]
            filtered = temporal.update({'cards': cards, 'processing_ms': 1}, frame*.1, (840,1762))
            board = arrange_table(filtered, (840,1762))['board']
            self.assertEqual([c['card'] for c in board[:3]], codes[:3] if frame else [None]*3)
            self.assertEqual([c['slot'] for c in board], list(range(5)))
        self.assertEqual([c['card'] for c in board], codes)

    def test_missing_middle_card_does_not_shift_turn_or_river(self):
        cards = [detection('KD', 4), detection('JC', 0), detection('AD', 3),
                 detection('5H', 2, accepted=False)]
        board = self.arrange(cards)['board']
        self.assertEqual([c['card'] for c in board], ['JC', None, None, 'AD', 'KD'])
        self.assertTrue(board[2]['detected'])
        self.assertFalse(board[1]['detected'])
        self.assertEqual([c['card'] for c in self.arrange([])['board']], [None]*5)

    def test_player_and_opponent_cards_are_separate_and_duplicates_do_not_replace_confirmed(self):
        cards = [detection('JC', 0, .65), detection(None, 0, .99, False),
                 dict(card='AS', accepted=True, bbox=[648,650,686,746]),
                 dict(card='KD', accepted=True, bbox=[1515,273,1554,352])]
        result = self.arrange(cards)
        self.assertEqual(result['board'][0]['card'], 'JC')
        self.assertEqual(sum(c['table_group']=='other' for c in result['cards']), 1)
        self.assertEqual([c['card'] for c in result['player_hand']], ['AS', None])
        self.assertNotIn('table_group', cards[0])

    def test_reviewed_video_annotations_at_multiple_scales_and_with_bottom_controls(self):
        count = 0
        for name in ('195129', '211955', '213508', 'capture10'):
            spec = json.loads((ROOT/f'datasets/table-{name}.json').read_text())
            for frame in spec['frames']:
                for scale in (.5, 1, 1.5):
                    cards = []
                    for group in ('board', 'hole', 'opponent'):
                        for code, box in zip(frame.get(group, []), spec['index_boxes'].get(group, [])):
                            cards.append(dict(card=code, accepted=True, confidence=.9,
                                              bbox=[v*scale for v in box]))
                    result = self.arrange(cards[::-1], (round(spec['size'][1]*scale), round(spec['size'][0]*scale)))
                    self.assertEqual([c['card'] for c in result['board']],
                                     frame['board']+[None]*(5-len(frame['board'])), (name, frame['time']))
                    hole = frame.get('hole', [])
                    self.assertEqual([c['card'] for c in result['player_hand']],
                                     hole+[None]*(2-len(hole)), (name, frame['time']))
                    count += 1
        self.assertGreater(count, 100)

    def test_missing_left_hand_card_does_not_move_right_and_no_old_hand_is_retained(self):
        right = dict(card='KH', accepted=True, confidence=.9, bbox=[688,662,736,760])
        left = dict(card=None, accepted=False, confidence=.8, bbox=[648,650,686,746])
        result = self.arrange([right,left])
        self.assertEqual([c['card'] for c in result['player_hand']], [None,'KH'])
        self.assertTrue(result['player_hand'][0]['detected'])
        self.assertEqual([c['card'] for c in self.arrange([])['player_hand']], [None,None])


if __name__ == '__main__':
    unittest.main()

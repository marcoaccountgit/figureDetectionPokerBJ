import unittest

from card_detector import np
from hand_counter import HandCounter, player_card_presence


def presence(left=True, right=True):
    return [dict(present=left), dict(present=right)]


def cards(codes=('3S','4C'), accepted=True):
    return [dict(card=c if accepted else None,accepted=accepted) for c in codes]


class HandCounterTests(unittest.TestCase):
    def test_reviewed_compact_faces_survive_partial_hud_cover_at_multiple_sizes(self):
        from pathlib import Path
        from card_detector import cv2
        from capture_alignment import CaptureAligner
        for name in ('compact-ten-nine', 'compact-next-preflop'):
            source = cv2.imread(str(Path(__file__).parent/'fixtures'/f'{name}.png'))
            aligner = CaptureAligner()
            game, _ = aligner.align(source)
            for factor in (1, .8, 1.5):
                frame = cv2.resize(game, (round(game.shape[1]*factor), round(game.shape[0]*factor)))
                with self.subTest(name=name, factor=factor):
                    self.assertEqual([s['present'] for s in player_card_presence(frame, aligner.profile)], [True, True])
            # Local white pixels without surrounding felt are not a deal.
            game[:] = 255
            self.assertEqual([s['present'] for s in player_card_presence(game, aligner.profile)], [None, None])

    def setUp(self):
        self.counter = HandCounter()

    def feed(self, start, visible, hand):
        return [self.counter.update(visible,hand,start+i*.1) for i in range(5)]

    def test_starts_at_zero_then_counts_a_confirmed_hand_only_once(self):
        self.assertEqual(self.counter.count,0)
        results = self.feed(0,presence(),cards())
        self.assertEqual([r['count'] for r in results],[0,0,0,0,1])
        self.assertTrue(results[-1]['started'])
        for result in self.feed(.5,presence(),cards()):
            self.assertEqual(result['count'],1)
            self.assertFalse(result['started'])

    def test_fold_then_same_cards_can_start_a_new_hand(self):
        self.feed(0,presence(),cards())
        closed = self.feed(.5,presence(False,False),cards(accepted=False))[-1]
        self.assertTrue(closed['ended'])
        self.assertEqual(closed['count'],1)
        self.assertFalse(closed['active'])
        started = self.feed(1,presence(),cards())[-1]
        self.assertEqual(started['count'],2)
        self.assertTrue(started['started'])

    def test_board_reset_recovers_missed_end_without_restarting_on_one_frame(self):
        self.feed(0, presence(), cards())
        self.counter.update(presence(), cards(), .5, board_cleared=True)
        self.counter.update(presence(), cards(), .6)
        self.assertEqual(self.counter.count, 1)
        for i in range(5):
            result = self.counter.update(presence(), cards(('AS','8H')), .7+i*.1, board_cleared=True)
        self.assertTrue(result['started'])
        self.assertEqual(result['count'], 2)
        self.assertTrue(result['active'])

    def test_missing_reading_single_card_or_occlusion_does_not_close_hand(self):
        self.feed(0,presence(),cards())
        for t, visible in ((.5,presence()),(1,presence(True,False)),(1.5,presence(None,None))):
            result = self.feed(t,visible,cards(accepted=False))[-1]
            self.assertTrue(result['active'])
            self.assertEqual(result['count'],1)
            self.assertFalse(result['ended'])
        self.assertEqual(self.feed(2,presence(),cards(('AS','KH')))[-1]['count'],1)

    def test_partial_pair_blips_do_not_open_hand_but_unreadable_pair_does(self):
        self.feed(0,presence(True,False),cards(('AS','AS')))
        self.assertEqual(self.counter.count,0)
        for i, visible in enumerate((presence(),presence(None,True))*3):
            self.counter.update(visible,cards(),.5+i*.1)
        self.assertEqual(self.counter.count,0)
        self.assertEqual(self.feed(1.2,presence(),cards(accepted=False))[-1]['count'],1)
        self.counter.update(presence(False,False),cards(accepted=False),1.8)
        self.assertEqual(self.feed(1.9,presence(),cards())[-1]['count'],1)

    def test_minimum_span_gap_and_alignment_reset_do_not_invent_hands(self):
        for i in range(5):
            self.counter.update(presence(),cards(),i*.01)
        self.assertEqual(self.counter.count,0)
        self.assertEqual(self.counter.update(presence(),cards(),.4)['count'],1)
        self.counter.reset_observations()
        self.assertEqual(self.feed(4,presence(),cards())[-1]['count'],1)

    def test_presence_uses_card_faces_and_green_felt_not_rank_output(self):
        frame = np.full((984,1762,3),(30,65,30),np.uint8)
        self.assertEqual([s['present'] for s in player_card_presence(frame)],[False,False])
        frame[650:746,648:686] = 255
        frame[662:760,688:736] = 255
        self.assertEqual([s['present'] for s in player_card_presence(frame)],[True,True])
        frame[:] = 0
        self.assertEqual([s['present'] for s in player_card_presence(frame)],[None,None])
        frame[:] = 255
        self.assertEqual([s['present'] for s in player_card_presence(frame)],[None,None])

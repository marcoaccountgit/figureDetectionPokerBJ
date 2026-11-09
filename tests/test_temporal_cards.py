import copy
import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from temporal_cards import TemporalCards, HandCardMemory
from card_detector import np
from recognize import main


def reading(code='AS', box=None, accepted=True):
    return {'accepted': accepted, 'card': code if accepted else None,
            'rank': code[:-1], 'suit': code[-1], 'confidence': .9,
            'bbox': box or [10, 10, 40, 80]}


class HandCardMemoryTests(unittest.TestCase):
    def test_folded_board_memory_ends_when_board_is_physically_cleared(self):
        memory = HandCardMemory()
        card = dict(reading(), table_group='board', board_slot=0)
        memory.update(dict(cards=[card]), dict(active=True, started=False, ended=False))
        folded = dict(active=False, started=False, ended=True)
        self.assertEqual(memory.update(dict(cards=[]), folded)['cards'][0]['card'], 'AS')
        cleared = dict(active=False, started=False, ended=False, board_cleared=True)
        self.assertEqual(memory.update(dict(cards=[]), cleared)['cards'], [])

    def test_confirmed_cards_survive_missing_uncertain_and_changed_readings(self):
        memory = HandCardMemory()
        cycle = dict(active=True, started=False, ended=False)
        card = dict(reading(), table_group='board', board_slot=0)
        memory.update(dict(cards=[card]), cycle)
        for cards in ([], [dict(card, accepted=False, card=None)], [dict(card, card='KD')]):
            result = memory.update(dict(cards=cards), cycle)
            self.assertEqual(result['cards'][0]['card'], 'AS')
            self.assertTrue(result['cards'][0]['accepted'])
            self.assertTrue(result['cards'][0]['retained'])
        turn = dict(reading('KD'), table_group='board', board_slot=3)
        hero = dict(reading('QH'), table_group='player_hand', hand_slot=0)
        result = memory.update(dict(cards=[turn, hero]), cycle)
        self.assertEqual({c['card'] for c in result['cards']}, {'AS', 'KD', 'QH'})

    def test_new_hand_clears_all_cards_but_fold_preserves_board(self):
        for boundary in (dict(active=False, started=False, ended=True),
                         dict(active=True, started=True, ended=False)):
            memory = HandCardMemory()
            cycle = dict(active=True, started=False, ended=False)
            cards = [dict(reading(), table_group='board', board_slot=0),
                     dict(reading('KD'), table_group='player_hand', hand_slot=0)]
            memory.update(dict(cards=cards), cycle)
            remaining = memory.update(dict(cards=[]), boundary)['cards']
            self.assertEqual([c['card'] for c in remaining], ['AS'] if boundary['ended'] else [])
            new = dict(reading('QH'), table_group='player_hand', hand_slot=0)
            updated = memory.update(dict(cards=[new]), cycle)['cards']
            self.assertEqual(next(c['card'] for c in updated if c.get('table_group') == 'player_hand'), 'QH')


class TemporalTests(unittest.TestCase):
    def test_winning_card_animation_keeps_same_slot_confirmation(self):
        from browser_capture import live_confirmation
        tracker = live_confirmation()
        for i in range(6):
            card = dict(reading('5H', [480, 215 if i % 2 else 236, 499, 253 if i % 2 else 274]),
                        table_group='board', board_slot=1)
            result = tracker.update({'cards': [card], 'processing_ms': 1}, i*.2, (714,1143))
            self.assertEqual(result['cards'][0]['accepted'], i >= 4)

    def test_slot_matching_does_not_retain_a_missing_or_changed_card(self):
        tracker = TemporalCards()
        card = dict(reading('5H'), table_group='board', board_slot=1)
        tracker.update({'cards': [card], 'processing_ms': 1}, 0, (840,1762))
        changed = dict(card, card='6H')
        self.assertFalse(tracker.update({'cards': [changed], 'processing_ms': 1}, .1, (840,1762))['cards'][0]['accepted'])
        self.assertEqual(tracker.update({'cards': [], 'processing_ms': 1}, .2, (840,1762))['cards'], [])

    def test_slot_matching_does_not_cross_between_board_and_hand(self):
        tracker = TemporalCards()
        tracker.update({'cards': [dict(reading(), table_group='board', board_slot=0)], 'processing_ms': 1}, 0, (840,1762))
        card = dict(reading(box=[400,400,420,440]), table_group='player_hand', hand_slot=0)
        self.assertFalse(tracker.update({'cards': [card], 'processing_ms': 1}, .1, (840,1762))['cards'][0]['accepted'])

    def test_live_five_consecutive_slow_cycles_can_confirm_beyond_two_seconds(self):
        from browser_capture import live_confirmation
        tracker = live_confirmation()
        results = [tracker.update({'cards':[reading()],'processing_ms':1},i*.7,(840,1762))
                   for i in range(5)]
        self.assertEqual([r['cards'][0]['accepted'] for r in results],[False,False,False,False,True])
        result = tracker.update({'cards':[reading()],'processing_ms':1},5,(840,1762))
        self.assertFalse(result['cards'][0]['accepted'])

    def test_live_confirmation_requires_repeated_spaced_observations(self):
        from browser_capture import live_confirmation
        tracker = live_confirmation()
        for t in (0, .02, .04, .06, .08):
            self.assertFalse(tracker.update({'cards': [reading()], 'processing_ms': 1}, t, (840,1762))['cards'][0]['accepted'])
        self.assertTrue(tracker.update({'cards': [reading()], 'processing_ms': 1}, .35, (840,1762))['cards'][0]['accepted'])

    def test_live_four_readings_over_300_ms_are_not_enough(self):
        from browser_capture import live_confirmation
        tracker = live_confirmation()
        for t in (0, .15, .3, .45):
            self.assertFalse(tracker.update({'cards': [reading()], 'processing_ms': 1}, t, (840,1762))['cards'][0]['accepted'])
        self.assertTrue(tracker.update({'cards': [reading()], 'processing_ms': 1}, .6, (840,1762))['cards'][0]['accepted'])

    def test_live_conflicting_or_missing_reading_breaks_confirmation(self):
        from browser_capture import live_confirmation
        for interruption in ([reading('KD')], [], [reading(accepted=False)]):
            tracker = live_confirmation()
            for t in (0, .1, .2, .3, .4):
                tracker.update({'cards': [reading()], 'processing_ms': 1}, t, (840,1762))
            tracker.update({'cards': interruption, 'processing_ms': 1}, .5, (840,1762))
            for t in (.6, .7, .8, .9):
                self.assertFalse(tracker.update({'cards': [reading()], 'processing_ms': 1}, t, (840,1762))['cards'][0]['accepted'])
            self.assertTrue(tracker.update({'cards': [reading()], 'processing_ms': 1}, 1, (840,1762))['cards'][0]['accepted'])

    def setUp(self):
        self.filter = TemporalCards()

    def update(self, t, cards, shape=(840, 1762, 3)):
        return self.filter.update({'cards': cards, 'processing_ms': 50}, t, shape)

    def test_two_matching_observations_confirm_without_mutating_raw_output(self):
        raw = [reading()]
        original = copy.deepcopy(raw)
        first = self.update(0, raw)
        self.assertFalse(first['cards'][0]['accepted'])
        second = self.update(.2, [reading()])
        self.assertTrue(second['cards'][0]['accepted'])
        self.assertEqual(second['cards'][0]['confirmation_span_ms'], 200)
        self.assertEqual(raw, original)
        self.assertTrue(first['raw_cards'][0]['accepted'])

    def test_isolated_wrong_reading_is_suppressed_then_correct_reading_recovers(self):
        self.update(0, [reading()])
        self.update(.2, [reading()])
        wrong = self.update(.4, [reading('AC')])
        self.assertFalse(wrong['cards'][0]['accepted'])
        self.assertIsNone(wrong['cards'][0]['card'])
        self.assertTrue(self.update(.6, [reading()])['cards'][0]['accepted'])

    def test_disappeared_card_is_never_carried_forward(self):
        self.update(0, [reading()])
        self.update(.2, [reading()])
        self.assertEqual(self.update(.4, [])['cards'], [])

    def test_changed_card_at_same_position_requires_new_confirmation(self):
        self.update(0, [reading()])
        result = self.update(.2, [reading('KD')])
        self.assertFalse(result['cards'][0]['accepted'])
        self.assertTrue(self.update(.4, [reading('KD')])['cards'][0]['accepted'])

    def test_uncertain_current_reading_cannot_be_promoted_from_history(self):
        self.update(0, [reading()])
        self.update(.2, [reading()])
        self.assertFalse(self.update(.4, [reading(accepted=False)])['cards'][0]['accepted'])

    def test_same_code_at_different_position_does_not_confirm(self):
        self.update(0, [reading()])
        result = self.update(.2, [reading(box=[100, 10, 130, 80])])
        self.assertFalse(result['cards'][0]['accepted'])

    def test_duplicate_codes_at_distinct_positions_remain_separate(self):
        cards = [reading(), reading(box=[100, 10, 130, 80])]
        self.update(0, cards)
        result = self.update(.2, cards)
        self.assertEqual(sum(c['accepted'] for c in result['cards']), 2)

    def test_one_past_index_cannot_confirm_two_overlapping_current_indices(self):
        self.update(0, [reading()])
        result = self.update(.2, [reading(), reading(box=[11, 10, 41, 80])])
        self.assertEqual(sum(c['accepted'] for c in result['cards']), 1)

    def test_history_expires_after_gap_and_resets_after_rewind_or_resize(self):
        for t, shape in ((0, (840,1762,3)), (1, (840,1762,3)),
                         (.5, (840,1762,3)), (.7, (984,1764,3))):
            self.assertFalse(self.update(t, [reading()], shape)['cards'][0]['accepted'])

    def test_nonfinite_timestamp_is_rejected(self):
        with self.assertRaises(ValueError):
            self.update(float('nan'), [])

    def test_pokerstars_stream_confirms_by_default_and_logs_raw_observations(self):
        result = {'cards': [dict(reading(), domain='physical')], 'processing_ms': 50, 'scene': 'card_model'}
        model = Mock()
        model.detect.side_effect = [copy.deepcopy(result), copy.deepcopy(result)]
        frame = np.zeros((100,100,3), np.uint8)
        with TemporaryDirectory() as directory:
            with (patch('sys.argv', ['recognize.py', '--video', 'unused.mp4', '--detector', 'model',
                                     '--profile', 'pokerstars', '--fps', '5', '--save-every', '0',
                                     '--output', directory]),
                  patch('learned_detector.LearnedCardDetector', return_value=model),
                  patch('recognize.video_frames', return_value=iter([(0, frame), (.2, frame)])),
                  patch('builtins.print')):
                main()
            summary = json.loads((Path(directory)/'summary.json').read_text())
            packets = [json.loads(line) for line in (Path(directory)/'detections.jsonl').read_text().splitlines()]
            self.assertTrue(summary['temporal_confirmation'])
            self.assertEqual(summary['accepted_appearances'], 1)
            self.assertTrue(packets[0]['raw_cards'][0]['accepted'])
            self.assertFalse(packets[0]['cards'][0]['accepted'])
            self.assertTrue(packets[1]['cards'][0]['accepted'])


if __name__ == '__main__':
    unittest.main()

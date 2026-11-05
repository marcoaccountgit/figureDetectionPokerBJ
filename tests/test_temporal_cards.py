import copy
import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from temporal_cards import TemporalCards
from card_detector import np
from recognize import main


def reading(code='AS', box=None, accepted=True):
    return {'accepted': accepted, 'card': code if accepted else None,
            'rank': code[:-1], 'suit': code[-1], 'confidence': .9,
            'bbox': box or [10, 10, 40, 80]}


class TemporalTests(unittest.TestCase):
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

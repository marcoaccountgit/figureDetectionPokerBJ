import json
from pathlib import Path
import unittest

from card_detector import np
from prepare_capture_improvement import canonical_frame


class CaptureImprovementTests(unittest.TestCase):
    def test_black_capture_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Empty capture'):
            canonical_frame(np.zeros((956, 1854, 3), np.uint8))

    def test_side_margins_removed_without_stretching_game(self):
        image = np.zeros((1000, 1802, 3), np.uint8)
        image[:, 20:1782] = 100
        image[400:480, 620:660] = 255
        result = canonical_frame(image)
        self.assertEqual(result.shape, (1100, 1762, 3))
        self.assertTrue(np.all(result[400:480, 600:640] == 255))
        self.assertTrue(np.all(result[1000:] == 0))

    def test_reviewed_capture_hands_never_cross_splits(self):
        spec = json.loads((Path(__file__).resolve().parents[1] /
                           'datasets/table-capture10.json').read_text())
        hands = {}
        for entry in spec['frames']:
            self.assertEqual(hands.setdefault(entry['hand'], entry['split']), entry['split'])


if __name__ == '__main__':
    unittest.main()

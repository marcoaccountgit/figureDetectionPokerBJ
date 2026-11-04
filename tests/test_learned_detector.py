import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from card_detector import np
from learned_detector import decode_indices, letterbox

NAMES = [rank + suit for rank in ['10', *'23456789', 'A', 'J', 'K', 'Q'] for suit in 'CDHS']


def output_for(rows):
    output = np.zeros((1, 56, len(rows)), np.float32)
    for index, (box, scores) in enumerate(rows):
        output[0, :4, index] = box
        for code, score in scores.items():
            output[0, 4 + NAMES.index(code), index] = score
    return output


class LearnedDetectorTests(unittest.TestCase):
    def test_letterbox_preserves_aspect_and_converts_bgr_to_rgb(self):
        frame = np.full((800, 400, 3), (10, 20, 30), np.uint8)
        blob, scale, left, top = letterbox(frame)
        self.assertEqual(blob.shape, (1, 3, 640, 640))
        self.assertEqual((scale, left, top), (.8, 160, 0))
        np.testing.assert_allclose(blob[0, :, 100, 200], np.array([30, 20, 10]) / 255, atol=1e-6)

    def test_box_coordinates_remove_padding_and_scale(self):
        # Portrait image: x padding is 160. Original box [50,100,100,200].
        output = output_for([([220, 120, 40, 80], {'10D': .9})])
        result = decode_indices(output, NAMES, (800, 400, 3), .8, 160, 0)
        self.assertEqual(result[0]['bbox'], [50, 100, 100, 200])
        self.assertEqual(result[0]['card'], '10D')

    def test_nms_removes_duplicate_boxes_without_merging_same_code_elsewhere(self):
        output = output_for([
            ([100, 200, 40, 80], {'10D': .9}),
            ([101, 200, 40, 80], {'10D': .85}),
            ([400, 200, 40, 80], {'10D': .88}),
        ])
        result = decode_indices(output, NAMES, (640, 640, 3), 1, 0, 0)
        self.assertEqual(len(result), 2)
        self.assertTrue(all(card['card'] == '10D' for card in result))

    def test_ambiguous_suit_is_not_confirmed(self):
        output = output_for([([100, 200, 40, 80], {'10D': .7, '10H': .65})])
        result = decode_indices(output, NAMES, (640, 640, 3), 1, 0, 0)
        self.assertFalse(result[0]['accepted'])
        self.assertIsNone(result[0]['card'])

    def test_invalid_and_outside_boxes_do_not_create_detections(self):
        output = output_for([
            ([np.nan, 200, 40, 80], {'10D': .9}),
            ([-200, -200, 40, 80], {'10D': .9}),
            ([100, 200, -40, 80], {'10D': .9}),
        ])
        self.assertEqual(decode_indices(output, NAMES, (640, 640, 3), 1, 0, 0), [])

    def test_unexpected_model_output_fails_explicitly(self):
        with self.assertRaisesRegex(RuntimeError, 'Output ONNX inatteso'):
            decode_indices(np.zeros((1, 5, 8400)), NAMES, (640, 640, 3), 1, 0, 0)


if __name__ == '__main__':
    unittest.main()

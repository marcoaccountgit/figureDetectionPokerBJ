import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from card_detector import np
from evaluate_table_model import score_frame
from learned_detector import LearnedCardDetector
from learned_detector import additional_table_regions
from card_detector import stacked_index_symbols, cv2
from prepare_table_dataset import annotations_for
from prepare_table_dataset import stable_indices
from recognize import main
from prepare_improvement_dataset import glyph_mask

ROOT = Path(__file__).resolve().parents[1]


class TableProfileTests(unittest.TestCase):
    def test_new_card_in_previously_empty_slot_blocks_label_propagation(self):
        before = np.zeros((100, 200, 3), np.uint8)
        after = before.copy()
        after[10:50, 50:80] = 255
        spec = {'index_boxes': {'board': [[10,10,40,50], [50,10,80,50]], 'hole': []}}
        self.assertFalse(stable_indices(before, after, {'board':['AS'], 'hole':[]}, spec))

    def test_training_ten_keeps_both_disconnected_digits(self):
        image = np.full((45, 40, 3), 255, np.uint8)
        image[3:40, 3:7] = 0
        cv2.rectangle(image, (13, 3), (29, 39), (0, 0, 0), 3)
        glyph = np.asarray(glyph_mask(image)) > 0
        count, _ = cv2.connectedComponents(glyph.astype(np.uint8))
        self.assertEqual(count-1, 2)
        self.assertGreater(glyph.shape[1], 20)

    def test_reviewed_hands_do_not_cross_dataset_splits(self):
        spec = json.loads((ROOT / 'datasets/table-195129.json').read_text())
        groups = {split: {f['hand'] for f in spec['frames'] if f['split'] == split}
                  for split in ('train', 'val', 'test')}
        self.assertFalse(groups['train'] & groups['val'])
        self.assertFalse(groups['train'] & groups['test'])
        self.assertFalse(groups['val'] & groups['test'])

    def test_dataset_index_coordinates_reconstruct_reviewed_original_box(self):
        spec = json.loads((ROOT / 'datasets/table-195129.json').read_text())
        names = json.loads((ROOT / 'models/lgd-cards-gen3.classes.json').read_text())
        entry = {'board': ['2D'], 'hole': []}
        label = annotations_for(entry, spec, names)[0]
        index, x, y, width, height = label
        x0, y0, x2, y2 = spec['crop']
        restored = [round((x-width/2)*(x2-x0)+x0), round((y-height/2)*(y2-y0)+y0),
                    round((x+width/2)*(x2-x0)+x0), round((y+height/2)*(y2-y0)+y0)]
        self.assertEqual(restored, spec['index_boxes']['board'][0])
        self.assertEqual(names[index], '2D')

    def test_evaluation_does_not_count_correct_code_at_wrong_position(self):
        expected = [('AS', [0, 0, 20, 40]), ('AS', [100, 0, 120, 40])]
        predictions = [{'accepted': True, 'card': 'AS', 'bbox': [0, 0, 20, 40], 'confidence': .9},
                       {'accepted': True, 'card': 'AS', 'bbox': [200, 0, 220, 40], 'confidence': .8}]
        scores = score_frame(expected, predictions)
        self.assertEqual(scores, {'correct': ['AS'], 'false_positive': ['AS'], 'missed': ['AS']})

    def test_profile_crop_offsets_are_returned_in_full_frame_coordinates(self):
        detector = LearnedCardDetector.__new__(LearnedCardDetector)
        detector.names = json.loads((ROOT / 'models/lgd-cards-gen3.classes.json').read_text())
        detector.profile = 'pokerstars'
        detector.crop = [.25, .25, .75, .75]
        detector.net = Mock()
        output = np.zeros((1, 56, 1), np.float32)
        output[0, :4, 0] = [160, 160, 64, 64]
        output[0, 4 + detector.names.index('AS'), 0] = .9
        detector.net.forward.return_value = output
        result = detector.detect(np.zeros((400, 400, 3), np.uint8))
        self.assertEqual(result['cards'][0]['bbox'], [140, 140, 160, 160])
        self.assertEqual(result['cards'][0]['polygon'][0], [140, 140])

    def test_cancelled_screen_selection_does_not_load_or_capture(self):
        with (patch('sys.argv', ['recognize.py', '--screen', '--select-region']),
              patch('preview.select_screen_region', return_value=None),
              patch('learned_detector.LearnedCardDetector') as model):
            main()
            model.assert_not_called()

    def test_extra_bottom_controls_do_not_move_the_table_crop(self):
        detector = LearnedCardDetector.__new__(LearnedCardDetector)
        detector.profile = 'general'
        detector.crop = [560/1762, 380/840, 1200/1762, 1]
        detector.crop_reference_size = [1762, 840]
        detector.names = ['AS'] * 52
        detector.net = Mock()
        detector.net.forward.return_value = np.zeros((1, 56, 0), np.float32)
        with patch('learned_detector.letterbox', wraps=__import__('learned_detector').letterbox) as boxed:
            for height in (840, 984):
                detector.detect(np.zeros((height, 1762, 3), np.uint8))
                self.assertEqual(boxed.call_args.args[0].shape[:2], (460, 640))

    def test_revealed_opponent_cards_get_an_additional_native_resolution_tile(self):
        frame = np.zeros((840, 1762, 3), np.uint8)
        frame[270:435, 1510:1650] = 255
        frame[400:550, 595:700] = 255  # already inside the main crop
        regions, indices = additional_table_regions(frame, [560, 380, 1200, 840])
        self.assertEqual(len(regions), 1)
        self.assertEqual(len(indices), 1)
        x1, y1, x2, y2 = regions[0]
        self.assertTrue(x1 <= 1510 < 1650 <= x2 and y1 <= 270 < 435 <= y2)

    def test_small_white_avatar_does_not_trigger_an_opponent_tile(self):
        frame = np.zeros((840, 1762, 3), np.uint8)
        frame[200:240, 1500:1540] = 255
        self.assertEqual(additional_table_regions(frame, [560, 380, 1200, 840]), ([], []))

    def test_neighbouring_card_border_is_not_joined_to_the_index_symbols(self):
        image = np.full((100, 50, 3), 255, np.uint8)
        cv2.putText(image, 'A', (3, 32), cv2.FONT_HERSHEY_SIMPLEX, .9, (0, 0, 0), 2)
        cv2.circle(image, (16, 68), 10, (0, 0, 0), -1)
        cv2.line(image, (46, 0), (46, 99), (80, 80, 80), 1)
        self.assertIsNotNone(stacked_index_symbols(image))


if __name__ == '__main__':
    unittest.main()

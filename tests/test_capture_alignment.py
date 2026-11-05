import unittest

from card_detector import np
from capture_alignment import align_capture, restore_coordinates
from table_layout import arrange_table


class CaptureAlignmentTests(unittest.TestCase):
    def test_black_side_bars_are_removed_and_board_boxes_return_to_preview_coordinates(self):
        frame = np.zeros((984, 1892, 3), np.uint8)
        frame[:, 65:1827] = (40, 80, 40)
        game, viewport = align_capture(frame)
        self.assertEqual(viewport, (65, 0, 1827, 984))
        self.assertEqual(game.shape, (984,1762,3))
        original = dict(card='2D', accepted=True, confidence=.9,
                        bbox=[711,402,751,480], polygon=[[711,402],[751,480]])
        result = arrange_table({'cards':[original], 'raw_cards':[original]}, game.shape)
        restored = restore_coordinates(result, viewport, frame.shape)
        self.assertEqual(restored['board'][1]['card'], '2D')
        self.assertEqual(restored['board'][1]['bbox'], [776,402,816,480])
        self.assertEqual(restored['cards'][0]['polygon'][0], [776,402])
        self.assertEqual(restored['raw_cards'][0]['bbox'], [776,402,816,480])
        self.assertEqual(original['bbox'], [711,402,751,480])

    def test_hand_coordinates_are_restored_after_side_bar_removal(self):
        result = arrange_table({'cards':[dict(card='AS',accepted=True,bbox=[648,650,686,746])]}, (984,1762))
        restored = restore_coordinates(result,(65,0,1827,984),(984,1892))
        self.assertEqual(restored['player_hand'][0]['card'], 'AS')
        self.assertEqual(restored['player_hand'][0]['bbox'], [713,650,751,746])

    def test_aligned_scene_keeps_its_coordinates(self):
        frame = np.full((840,1762,3), 80, np.uint8)
        game, viewport = align_capture(frame)
        self.assertEqual(viewport, (0,0,1762,840))
        self.assertTrue(np.array_equal(game,frame))

    def test_black_or_too_narrow_source_is_rejected(self):
        frame = np.zeros((100,200,3), np.uint8)
        with self.assertRaises(ValueError):
            align_capture(frame)
        frame[:,70:130] = 100
        with self.assertRaises(ValueError):
            align_capture(frame)

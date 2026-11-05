import unittest

from pathlib import Path
from card_detector import cv2, np
from capture_alignment import CaptureAligner, align_capture, restore_coordinates
from table_layout import arrange_table


class CaptureAlignmentTests(unittest.TestCase):
    def shifted_frame(self, offset=0):
        frame = np.full((1100,1762,3),(30,65,30),np.uint8)
        path = Path(__file__).resolve().parents[1]/'assets/alignment/player-open-edge.png'
        anchor = cv2.imread(str(path))
        frame[691+offset:827+offset,1042:1094] = anchor
        frame[650+offset:746+offset,648:686] = 255
        return frame

    def test_vertical_shift_is_registered_and_boxes_return_to_source_coordinates(self):
        source = self.shifted_frame(-156)
        aligner = CaptureAligner()
        aligned,viewport = aligner.align(source)
        self.assertEqual(viewport,(0,-156,1762,1100))
        self.assertTrue(np.array_equal(aligned[650:746,648:686],source[494:590,648:686]))
        result = restore_coordinates({'cards':[dict(card='10C',bbox=[648,650,686,746])]},viewport,source.shape)
        self.assertEqual(result['cards'][0]['bbox'],[648,494,686,590])

    def test_established_vertical_alignment_needs_three_agreeing_frames_to_change(self):
        aligner = CaptureAligner()
        self.assertEqual(aligner.align(self.shifted_frame())[1][1],0)
        for _ in range(2):
            self.assertEqual(aligner.align(self.shifted_frame(-156))[1][1],0)
        self.assertEqual(aligner.align(self.shifted_frame(-156))[1][1],-156)
        self.assertEqual(aligner.align(self.shifted_frame(-155))[1][1],-156)

    def test_side_bar_pixel_jitter_does_not_change_the_viewport(self):
        frame = np.zeros((984,1892,3),np.uint8)
        frame[:,65:1827] = (30,65,30)
        aligner = CaptureAligner()
        first = aligner.align(frame)[1]
        frame[:,65:67] = 0
        self.assertEqual(aligner.align(frame)[1],first)

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

"""Regressions using only screenshots saved with manual interventions."""
import unittest
from copy import deepcopy
from pathlib import Path

from card_detector import cv2
from capture_alignment import CaptureAligner
from learned_detector import TableCardDetector
from table_layout import arrange_table
from temporal_cards import HandCardMemory
from browser_capture import live_confirmation


class ManualImageRegressions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.detector = TableCardDetector()

    def test_saved_images_recover_board_without_session_history(self):
        cases = [
            ('manual-cold-desktop', ['7S','AS','QD',None,None]),
            ('manual-cold-desktop-fold', ['7S','AS','QD',None,None]),
            ('manual-conflicting-kings', ['4H','KC','KS','5C','4S']),
            ('manual-missing-nine', ['5C','9S','AH',None,None]),
        ]
        for name, expected in cases:
            with self.subTest(image=name):
                frame = cv2.imread(str(Path(__file__).parent/'fixtures'/f'{name}.png'))
                aligner = CaptureAligner()
                game, _ = aligner.align(frame)
                self.assertTrue(aligner.alignment_ready)
                self.assertEqual(aligner.profile, 'pokerstars-desktop-six')
                self.detector.profile = aligner.profile
                result = arrange_table(self.detector.detect(game), game.shape)
                self.assertEqual([c['card'] for c in result['board']], expected)
                self.assertFalse(result['card_conflicts'])
                if name == 'manual-conflicting-kings':
                    # Reproduce a locked initial error, then feed only fresh
                    # readings of this same reviewed image through both filters.
                    memory = HandCardMemory()
                    cycle = dict(active=True, started=False, ended=False)
                    memory.update(deepcopy(result), cycle)
                    memory.cards[('board', 4)]['card'] = '4C'
                    tracker = live_confirmation()
                    for i in range(8):
                        observed = tracker.update(deepcopy(result), i*.5, game.shape)
                        observed['card_revalidation'] = True
                        recovered = memory.update(observed, cycle)
                        if i < 6:
                            self.assertEqual(memory.cards[('board',4)]['card'], '4C')
                    recovered = arrange_table(recovered, game.shape)
                    self.assertEqual([c['card'] for c in recovered['board']], expected)


if __name__ == '__main__':
    unittest.main()

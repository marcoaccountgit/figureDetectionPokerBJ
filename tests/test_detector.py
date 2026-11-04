import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from card_detector import Detector, Recognizer, choose_reading, physical_candidates, suit_color, cv2, np
from recognize import video_frames
from build_assets import regenerate

ROOT = Path(__file__).resolve().parents[1]


class DetectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.detector = Detector(ROOT / 'assets')

    def test_blank_frame_has_no_invented_cards_or_scene(self):
        result = self.detector.detect(np.zeros((920, 1480, 3), np.uint8))
        self.assertEqual(result['cards'], [])
        self.assertEqual(result['scene'], 'unknown')

    def test_covered_card_is_never_assigned_an_identity(self):
        card = cv2.imread(str(ROOT / 'assets/examples/covered.png'))
        result = self.detector.digital.classify(card)
        self.assertFalse(result['accepted'])
        self.assertIsNone(result['card'])

    def test_visible_identity_and_original_coordinate_mapping(self):
        frame = np.zeros((920, 1480, 3), np.uint8)
        card = cv2.imread(str(ROOT / 'assets/examples/JH.png'))
        h, w = card.shape[:2]
        frame[722:722+h, 919:919+w] = card
        result = self.detector.detect(cv2.resize(frame, (2960, 1840), interpolation=cv2.INTER_NEAREST))
        recognized = [c for c in result['cards'] if c['accepted']]
        self.assertEqual(len(recognized), 1)
        self.assertEqual(recognized[0]['card'], 'JH')
        self.assertEqual(recognized[0]['domain'], 'digital')
        self.assertLessEqual(abs(recognized[0]['bbox'][0] - 1838), 2)
        self.assertLessEqual(abs(recognized[0]['bbox'][1] - 1444), 2)

    def test_view_switch_is_stateless(self):
        for name in ('stud', 'holdem', 'stud'):
            frame = np.zeros((920, 1480, 3), np.uint8)
            template = cv2.imread(str(ROOT / 'assets/scene' / f'{name}.png'))
            frame[:32, 105:260] = template
            self.assertEqual(self.detector.scene(frame)[0], name)

    def test_both_domains_have_all_ranks_and_suits(self):
        for domain in ('digital', 'physical'):
            recognizer = Recognizer(ROOT / 'assets', domain)
            self.assertEqual(set(recognizer.templates['rank']), set(['A', 'J', 'Q', 'K', '10'] + list('23456789')))
            self.assertEqual(set(recognizer.templates['suit']), set('CDHS'))

    def test_ink_color_distinguishes_red_black_and_absent_symbols(self):
        card = cv2.imread(str(ROOT / 'assets/examples/JH.png'))
        self.assertEqual(suit_color(card), 'red')
        gray = cv2.cvtColor(card, cv2.COLOR_BGR2GRAY)
        black = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
        self.assertEqual(suit_color(black), 'black')
        self.assertEqual(suit_color(np.full_like(card, 255)), 'unknown')

    def test_conflicting_indices_stay_uncertain_across_geometry_refinements(self):
        a = {'accepted': True, 'card': 'JH', 'rank_score': .95, 'suit_score': .95}
        b = {'accepted': True, 'card': '7H', 'rank_score': .96, 'suit_score': .96}
        conflict = choose_reading([a, b])
        self.assertFalse(conflict['accepted'])
        self.assertIsNone(conflict['card'])
        self.assertFalse(choose_reading([conflict, a])['accepted'])
        self.assertEqual(choose_reading([a, a])['card'], 'JH')

    def test_alternate_geometry_recovers_shaded_card_edge(self):
        frame = np.zeros((920, 1480, 3), np.uint8)
        frame[560:593, 662:693] = 190
        frame[560:593, 693:711] = 145
        strict = list(physical_candidates(frame, 'holdem'))
        shaded = list(physical_candidates(frame, 'holdem', white_level=130))
        self.assertEqual(len(strict), 1)
        self.assertEqual(len(shaded), 1)
        strict_width = np.ptp(strict[0][2][:, 0])
        shaded_width = np.ptp(shaded[0][2][:, 0])
        self.assertGreater(shaded_width, strict_width + 10)

    def test_video_sampling_respects_start_and_duration(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'sample.avi'
            writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'MJPG'), 10, (64, 48))
            self.assertTrue(writer.isOpened())
            for i in range(20):
                writer.write(np.full((48, 64, 3), i * 10, np.uint8))
            writer.release()
            frames = list(video_frames(path, .5, .8, 5))
            self.assertEqual([round(t, 1) for t, _ in frames], [.5, .7, .9, 1.1])
            self.assertLess(abs(float(frames[0][1].mean()) - 50), 3)

    def test_reference_extraction_failure_preserves_existing_assets(self):
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / 'assets'
            destination.mkdir()
            existing = destination / 'provenance.json'
            existing.write_text('original', encoding='utf-8')
            with patch('build_assets.cv2.VideoCapture') as factory:
                factory.return_value.isOpened.return_value = True
                with patch('build_assets._extract', side_effect=RuntimeError('annotation mismatch')):
                    with self.assertRaisesRegex(RuntimeError, 'annotation mismatch'):
                        regenerate('recording.mp4', destination)
                factory.return_value.release.assert_called_once()
            self.assertEqual(existing.read_text(encoding='utf-8'), 'original')


if __name__ == '__main__':
    unittest.main()

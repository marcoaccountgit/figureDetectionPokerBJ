import sys
import time
import unittest
import json
import tempfile
import contextlib
import io
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from card_detector import cv2, np
from webcam import CameraDetector, camera_frames
from recognize import main

ROOT = Path(__file__).resolve().parents[1]


def example_card():
    card = np.full((280, 200, 3), 255, np.uint8)
    for kind, name, top in [('rank', 'J_60_5.png', 16), ('suit', 'H_60_5.png', 50)]:
        mask = cv2.imread(str(ROOT / 'assets' / kind / name), cv2.IMREAD_GRAYSCALE) > 0
        region = card[top:top+26, 12:34]
        region[mask] = (20, 20, 160)
    return card


class WebcamTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.detector = CameraDetector()

    def test_card_recognition_outside_table_positions_with_perspective(self):
        source = np.float32([[0, 0], [199, 0], [199, 279], [0, 279]])
        target = np.float32([[90, 90], [270, 70], [290, 365], [70, 385]])
        transform = cv2.getPerspectiveTransform(source, target)
        frame = cv2.warpPerspective(example_card(), transform, (800, 600), borderValue=(20, 50, 20))
        result = self.detector.detect(frame)
        self.assertEqual(len(result['cards']), 1)
        self.assertEqual(result['cards'][0]['card'], 'JH')
        self.assertTrue(result['cards'][0]['accepted'])
        self.assertLess(abs(result['cards'][0]['bbox'][0] - 70), 5)

    def test_inverted_card_uses_opposite_orientation(self):
        frame = np.full((480, 640, 3), 20, np.uint8)
        frame[100:380, 100:300] = cv2.rotate(example_card(), cv2.ROTATE_180)
        result = self.detector.detect(frame)
        self.assertEqual(result['cards'][0]['card'], 'JH')

    def test_blank_white_card_is_detected_but_not_identified(self):
        frame = np.full((480, 640, 3), 20, np.uint8)
        frame[100:380, 100:300] = 255
        result = self.detector.detect(frame)
        self.assertEqual(len(result['cards']), 1)
        self.assertFalse(result['cards'][0]['accepted'])
        self.assertIsNone(result['cards'][0]['card'])

    def test_empty_camera_view_has_no_cards(self):
        result = self.detector.detect(np.full((480, 640, 3), 20, np.uint8))
        self.assertEqual(result['cards'], [])

    def test_card_on_light_background_uses_border_instead_of_white_blob(self):
        frame = np.full((480, 640, 3), 230, np.uint8)
        frame[100:380, 100:300] = example_card()
        cv2.rectangle(frame, (100, 100), (299, 379), (80, 80, 80), 2)
        result = self.detector.detect(frame)
        self.assertEqual(len(result['cards']), 1)
        self.assertEqual(result['cards'][0]['card'], 'JH')

    def test_small_card_below_old_area_limit_is_still_located(self):
        frame = np.full((720, 1280, 3), 20, np.uint8)
        frame[200:312, 200:280] = cv2.resize(example_card(), (80, 112))
        result = self.detector.detect(frame)
        self.assertEqual(len(result['cards']), 1)
        self.assertLess(abs(result['cards'][0]['bbox'][0] - 200), 5)

    def test_rounded_corners_do_not_prevent_detection(self):
        frame = np.full((480, 640, 3), 20, np.uint8)
        mask = np.zeros((280, 200), np.uint8)
        cv2.rectangle(mask, (16, 0), (183, 279), 255, -1)
        cv2.rectangle(mask, (0, 16), (199, 263), 255, -1)
        for center in ((16, 16), (183, 16), (16, 263), (183, 263)):
            cv2.circle(mask, center, 16, 255, -1)
        region = frame[100:380, 100:300]
        region[mask > 0] = example_card()[mask > 0]
        result = self.detector.detect(frame)
        self.assertEqual(len(result['cards']), 1)

    def test_camera_open_failure_is_reported_and_released(self):
        with patch('webcam.cv2.VideoCapture') as factory:
            factory.return_value.isOpened.return_value = False
            frames = camera_frames(0, 10, 1)
            with self.assertRaisesRegex(RuntimeError, 'Impossibile aprire'):
                next(frames)
            factory.return_value.release.assert_called_once()

    def test_capture_drops_old_frames_and_releases_on_close(self):
        class FakeCamera:
            def __init__(self):
                self.index = 0
                self.released = False

            def isOpened(self):
                return True

            def set(self, *args):
                return True

            def read(self):
                time.sleep(.005)
                self.index += 1
                return True, np.full((10, 10, 3), self.index % 255, np.uint8)

            def release(self):
                self.released = True

        camera = FakeCamera()
        with patch('webcam.cv2.VideoCapture', return_value=camera):
            frames = camera_frames(0, 30, 1)
            first_time, first = next(frames)
            time.sleep(.06)
            last_time, last = next(frames)
            frames.close()
        self.assertGreater(last_time, first_time)
        self.assertGreater(int(last[0, 0, 0]), int(first[0, 0, 0]) + 3)
        self.assertTrue(camera.released)

    def test_camera_command_opens_preview_saves_snapshot_and_closes_source(self):
        closed = []

        def frames():
            try:
                frame = np.full((480, 640, 3), 20, np.uint8)
                frame[100:380, 100:300] = example_card()
                yield 0.0, frame
            finally:
                closed.append(True)

        with tempfile.TemporaryDirectory() as folder:
            with (patch('sys.argv', ['recognize.py', '--camera', '0', '--output', folder]),
                  patch('webcam.camera_frames', return_value=frames()),
                  patch('learned_detector.LearnedCardDetector', return_value=self.detector),
                  patch('preview.LivePreview') as preview_factory,
                  contextlib.redirect_stdout(io.StringIO())):
                preview = preview_factory.return_value
                preview.show.return_value = False
                preview.save_requested = True
                main()
                preview.close.assert_called_once()
                preview.saved.assert_called_once()
            sessions = list(Path(folder).glob('session-*'))
            self.assertEqual(len(sessions), 1)
            summary = json.loads((sessions[0] / 'summary.json').read_text())
            self.assertEqual(summary['frames'], 1)
            self.assertEqual(summary['source'], 'camera')
            self.assertEqual(len(list(sessions[0].glob('snapshot-*-raw.png'))), 1)
            self.assertEqual(len(list(sessions[0].glob('snapshot-*-annotated.jpg'))), 1)
            self.assertEqual(closed, [True])


if __name__ == '__main__':
    unittest.main()

import http.client
import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import Mock, patch

from browser_capture import make_handler
from card_detector import cv2, np


class BrowserCaptureTests(unittest.TestCase):
    def setUp(self):
        self.detector = Mock()
        self.detector.detect.return_value = {'cards': [], 'processing_ms': 1}
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.detector, 'test-token'))
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()
        self.client = http.client.HTTPConnection('127.0.0.1', self.server.server_port)

    def tearDown(self):
        self.client.close()
        self.server.shutdown()
        self.server.server_close()
        self.worker.join()

    def request(self, method, path, body=None, headers=None):
        self.client.request(method, path, body, headers or {})
        response = self.client.getresponse()
        return response.status, response.read()

    def test_panel_requires_session_url(self):
        self.assertEqual(self.request('GET', '/')[0], 404)
        status, body = self.request('GET', '/?token=test-token')
        self.assertEqual(status, 200)
        self.assertIn(b'getDisplayMedia', body)

    def test_frames_require_token_and_valid_image(self):
        self.assertEqual(self.request('POST', '/frame', b'bad')[0], 403)
        headers = {'X-Capture-Token': 'test-token', 'X-Capture-Session': 'session-1'}
        self.assertEqual(self.request('POST', '/frame', b'bad', headers)[0], 400)
        self.detector.detect.assert_not_called()
        image = cv2.imencode('.jpg', np.full((100, 200, 3), 80, np.uint8))[1].tobytes()
        status, body = self.request('POST', '/frame', image, headers)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['cards'], [])
        self.detector.detect.assert_called_once()

    def test_opponent_count_is_confirmed_via_api_and_new_session_resets_it(self):
        from pathlib import Path
        frame = np.full((984,1762,3),(30,65,30),np.uint8)
        template = cv2.imread(str(Path(__file__).resolve().parents[1]/'assets/opponents/covered-pair.png'))
        frame[92:140,827:937] = template
        encoded = cv2.imencode('.jpg',frame)[1].tobytes()
        headers = {'X-Capture-Token':'test-token','X-Capture-Session':'one'}
        with patch('browser_capture.perf_counter', side_effect=[i*.1 for i in range(100)]):
            for index in range(5):
                status, body = self.request('POST','/frame',encoded,headers)
                self.assertEqual(status,200)
                result = json.loads(body)
                self.assertEqual(result['opponents']['count'],1 if index==4 else None)
            headers['X-Capture-Session'] = 'two'
            status, body = self.request('POST','/frame',encoded,headers)
            self.assertEqual(status,200)
            self.assertIsNone(json.loads(body)['opponents']['count'])

    def test_hand_count_survives_unreadable_cards_and_increments_after_physical_removal(self):
        frame = np.full((984,1762,3),(30,65,30),np.uint8)
        empty = cv2.imencode('.jpg',frame)[1].tobytes()
        frame[650:746,648:686] = 255
        frame[662:760,688:736] = 255
        dealt = cv2.imencode('.jpg',frame)[1].tobytes()
        headers = {'X-Capture-Token':'test-token','X-Capture-Session':'hands'}
        with patch('browser_capture.perf_counter', side_effect=[i*.04 for i in range(500)]):
            for payload, count in ((dealt,1),(dealt,1),(empty,1),(dealt,2)):
                for _ in range(5):
                    status, body = self.request('POST','/frame',payload,headers)
                    self.assertEqual(status,200)
                result = json.loads(body)
                self.assertEqual(result['hand_cycle']['count'],count)
                self.assertEqual(result['cards'],[])
            headers['X-Capture-Session'] = 'new-capture'
            status, body = self.request('POST','/frame',dealt,headers)
            self.assertEqual(status,200)
            self.assertEqual(json.loads(body)['hand_cycle']['count'],0)


if __name__ == '__main__':
    unittest.main()

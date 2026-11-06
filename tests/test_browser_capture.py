import http.client
import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import Mock, patch

from browser_capture import make_handler
from card_detector import cv2, np


class BrowserCaptureTests(unittest.TestCase):
    def test_http_confirmation_tracks_the_slot_during_card_lift(self):
        from temporal_cards import TemporalCards
        card=dict(card='AS',rank='A',suit='S',accepted=True,confidence=.99)
        self.detector.detect.side_effect=[
            dict(cards=[dict(card,bbox=[603,425,623,455])],processing_ms=1),
            dict(cards=[dict(card,bbox=[603,390,623,420])],processing_ms=1)]
        with patch('browser_capture.live_confirmation',side_effect=TemporalCards):
            self.server.RequestHandlerClass=make_handler(self.detector,'test-token')
            frame=cv2.imencode('.png',np.full((840,1762,3),80,np.uint8))[1].tobytes()
            headers={'X-Capture-Token':'test-token','X-Capture-Session':'animated-slot'}
            status,body=self.request('POST','/frame',frame,headers)
            self.assertEqual(status,200)
            self.assertFalse(json.loads(body)['board'][0]['accepted'])
            status,body=self.request('POST','/frame',frame,headers)
            self.assertEqual(status,200)
            self.assertEqual(json.loads(body)['board'][0]['card'],'AS')

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

    def test_equity_receives_confirmed_result_and_configuration(self):
        service = Mock()
        service.submit.return_value = dict(status='waiting',message='Carte non confermate')
        self.server.RequestHandlerClass = make_handler(self.detector,'test-token',equity_service=service)
        image = cv2.imencode('.jpg',np.full((100,200,3),80,np.uint8))[1].tobytes()
        headers = {'X-Capture-Token':'test-token','X-Capture-Session':'equity-one',
                   'X-Equity-Profile':'BALANCED','X-Equity-Opponents':'3','X-Equity-Seed':'42'}
        status,body = self.request('POST','/frame',image,headers)
        self.assertEqual(status,200)
        self.assertEqual(json.loads(body)['equity']['status'],'waiting')
        self.assertEqual(json.loads(body)['poker_advice']['status'],'waiting')
        data,session = service.submit.call_args.args
        self.assertEqual(session,'equity-one')
        self.assertIn('player_hand',data)
        self.assertIn('board',data)
        self.assertIn('opponents',data)
        self.assertEqual(service.submit.call_args.kwargs,
                         dict(profile='BALANCED',manual_opponents=3,random_seed=42))

    def test_table_observer_receives_aligned_frame_and_session_context(self):
        observer = Mock()
        observer.submit.return_value = dict(status='error',error='OCR non disponibile')
        self.server.RequestHandlerClass = make_handler(self.detector,'test-token',observer)
        frame = np.zeros((984,1892,3),np.uint8)
        frame[:,65:1827] = (30,65,30)
        encoded = cv2.imencode('.png',frame)[1].tobytes()
        headers = {'X-Capture-Token':'test-token','X-Capture-Session':'observed-session'}
        status,body = self.request('POST','/frame',encoded,headers)
        self.assertEqual(status,200)
        result = json.loads(body)
        self.assertEqual(result['table_observation']['status'],'error')
        self.assertIn('hand_cycle',result)
        game,context = observer.submit.call_args.args
        self.assertEqual(game.shape,(984,1762,3))
        self.assertEqual(context['viewport'],(65,0,1827,984))
        self.assertEqual(context['capture_session'],'observed-session')
        self.assertEqual(context['hand_id'],0)
        self.assertEqual(context['street'],'preflop')

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

    def test_player_fold_does_not_reset_confirmation_of_the_visible_board(self):
        board = dict(card='5C',accepted=True,confidence=.95,bbox=[595,402,635,480])
        hero = [dict(card='10C',accepted=True,confidence=.95,bbox=[648,650,686,746]),
                dict(card='QS',accepted=True,confidence=.95,bbox=[688,662,736,760])]
        self.detector.detect.side_effect = [dict(cards=[board]+hero,processing_ms=1) for _ in range(5)] + [
            dict(cards=[board],processing_ms=1) for _ in range(6)]
        frame = np.full((1100,1762,3),(30,65,30),np.uint8)
        folded = cv2.imencode('.png',frame)[1].tobytes()
        frame[650:746,648:686] = 255
        frame[662:760,688:736] = 255
        dealt = cv2.imencode('.png',frame)[1].tobytes()
        headers = {'X-Capture-Token':'test-token','X-Capture-Session':'fold-board'}
        with patch('browser_capture.perf_counter',side_effect=[i*.04 for i in range(500)]):
            for index,payload in enumerate([dealt]*5+[folded]*6):
                status,body = self.request('POST','/frame',payload,headers)
                self.assertEqual(status,200)
                result = json.loads(body)
                if index >= 4:
                    self.assertEqual(result['board'][0]['card'],'5C')
            self.assertFalse(result['hand_cycle']['active'])
            self.assertEqual(result['hand_cycle']['count'],1)


if __name__ == '__main__':
    unittest.main()

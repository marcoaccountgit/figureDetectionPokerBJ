import http.client
import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import Mock, patch

from browser_capture import make_handler
from card_detector import cv2, np


class BrowserCaptureTests(unittest.TestCase):
    def test_statistics_panel_returns_unknown_opponents_without_inference(self):
        from pathlib import Path
        payload=(Path(__file__).parent/'fixtures/nine-statistics-covered.png').read_bytes()
        headers={'X-Capture-Token':'test-token','X-Capture-Session':'covered-nine'}
        status,body=self.request('POST','/frame',payload,headers)
        self.assertEqual(status,200)
        result=json.loads(body)
        self.assertFalse(result['alignment_ready'])
        self.assertEqual(result['table_profile'],'pokerstars-nine')
        self.assertEqual(result['opponents']['max_opponents'],8)
        self.assertIsNone(result['opponents']['count'])
        self.detector.detect.assert_not_called()

    def test_reviewed_compact_hands_recover_missed_deals_and_partial_reads(self):
        from pathlib import Path
        from learned_detector import TableCardDetector
        self.server.RequestHandlerClass = make_handler(TableCardDetector(), 'test-token')
        headers = {'X-Capture-Token': 'test-token', 'X-Capture-Session': 'reviewed'}
        cases = [
            ('compact-ten-nine', ['10D', '9H'], ['3C', 'QC', '8D', '5H', None], 1),
            # The old turn disappeared, but the new flop is already visible.
            ('compact-next-flop', ['AS', '9C'], ['5H', '9D', '8D', None, None], 2),
            ('compact-next-preflop', ['JC', '9D'], [None]*5, 3),
        ]
        with patch('browser_capture.perf_counter', side_effect=[i*.04 for i in range(5000)]):
            for name, hand, board, count in cases:
                payload = (Path(__file__).parent/'fixtures'/f'{name}.png').read_bytes()
                for _ in range(12):
                    status, body = self.request('POST', '/frame', payload, headers)
                    self.assertEqual(status, 200)
                    result = json.loads(body)
                with self.subTest(name=name):
                    self.assertEqual([c['card'] for c in result['player_hand']], hand)
                    self.assertEqual([c['card'] for c in result['board']], board)
                    self.assertEqual(result['hand_cycle']['count'], count)
                    self.assertTrue(result['card_cache']['inference_skipped'])
            headers['X-Capture-Session'] = 'partial-four-clubs'
            payload = (Path(__file__).parent/'fixtures/compact-nine-four.png').read_bytes()
            for _ in range(12):
                status, body = self.request('POST', '/frame', payload, headers)
                self.assertEqual(status, 200)
                result = json.loads(body)
            self.assertEqual([c['card'] for c in result['player_hand']], ['9C', '4C'])
            self.assertEqual([c['card'] for c in result['board']], ['9S', '7H', 'JH', None, None])

    def test_manual_correction_persists_and_new_hand_saves_diagnostics(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from test_live_card_cache import known_flop
        source, _, _, _, cards, _ = known_flop()
        self.detector.detect.return_value = dict(cards=cards, processing_ms=1)
        headers = {'X-Capture-Token': 'test-token', 'X-Capture-Session': 'manual'}
        def frame():
            status, body = self.request('POST', '/frame', cv2.imencode('.png', source)[1].tobytes(), headers)
            self.assertEqual(status, 200)
            return json.loads(body)
        def intervene(**action):
            return self.request('POST', '/intervention', json.dumps(dict(session='manual', hand_id=packet['hand_cycle']['count'], **action)), headers)
        with TemporaryDirectory() as directory, patch('browser_capture.ROOT', Path(directory)), patch('browser_capture.perf_counter', side_effect=[i*.05 for i in range(3000)]):
            for _ in range(5):
                packet = frame()
            self.assertEqual(intervene(kind='card', group='board', slot=0, card='ZZ')[0], 400)
            self.assertEqual(intervene(kind='card', group='board', slot=0, card='AH')[0], 200)
            for _ in range(3):
                packet = frame()
                self.assertEqual(packet['board'][0]['card'], 'AH')
                self.assertTrue(packet['board'][0]['manual'])
            old_count = packet['hand_cycle']['count']
            self.assertEqual(intervene(kind='new_hand')[0], 200)
            packet = frame()
            self.assertEqual(packet['hand_cycle']['count'], old_count+1)
            self.assertTrue(packet['hand_cycle']['started'])
            self.assertFalse(packet['board'][0].get('manual', False))
            reports = list(Path(directory).rglob('analysis.json'))
            self.assertEqual(len(reports), 2)
            for report in reports:
                self.assertIsNotNone(cv2.imread(str(report.with_name('screenshot.png'))))
                self.assertIn('before', json.loads(report.read_text(encoding='utf-8')))

    def test_fast_new_deal_clears_old_board_without_observing_empty_hero(self):
        from test_live_card_cache import known_flop
        source, game, viewport, _, cards, _ = known_flop()
        self.detector.detect.return_value = dict(cards=cards, processing_ms=1)
        headers = {'X-Capture-Token': 'test-token', 'X-Capture-Session': 'fast-deal'}
        def send(frame):
            status, body = self.request('POST', '/frame', cv2.imencode('.png', frame)[1].tobytes(), headers)
            self.assertEqual(status, 200)
            return json.loads(body)
        with patch('browser_capture.perf_counter', side_effect=[i*.05 for i in range(2000)]):
            for _ in range(5):
                packet = send(source)
            self.assertEqual(packet['hand_cycle']['count'], 1)
            self.assertEqual(packet['board'][0]['card'], '7S')
            scale = game.shape[1] / 1762
            new_deal = source.copy()
            for slot in range(3):
                cx = 654 + 101*slot
                a, b, c, d = [round(v*scale) for v in (cx-24,365,cx+26,430)]
                new_deal[b+viewport[1]:d+viewport[1], a+viewport[0]:c+viewport[0]] = (30,120,30)
            self.detector.detect.return_value = dict(
                cards=[dict(card, card=code) for card, code in zip(cards[3:], ('AC','8H'))], processing_ms=1)
            for _ in range(9):
                packet = send(new_deal)
            self.assertEqual(packet['hand_cycle']['count'], 2)
            self.assertEqual([c['card'] for c in packet['player_hand']], ['AC','8H'])
            self.assertEqual([c['card'] for c in packet['board']], [None]*5)
            self.assertTrue(send(new_deal)['card_cache']['inference_skipped'])

    def test_confirmed_cards_skip_detector_across_actions_resize_and_read_new_turn(self):
        from test_live_card_cache import known_flop
        source, game, viewport, _, cards, _ = known_flop()
        self.detector.detect.return_value = dict(cards=cards, processing_ms=1)
        headers = {'X-Capture-Token': 'test-token', 'X-Capture-Session': 'card-cache'}
        def send(frame):
            data = cv2.imencode('.png', frame)[1].tobytes()
            status, body = self.request('POST', '/frame', data, headers)
            self.assertEqual(status, 200)
            return json.loads(body)
        with patch('browser_capture.perf_counter', side_effect=[i * .05 for i in range(2000)]):
            for _ in range(5):
                packet = send(source)
            self.assertEqual(self.detector.detect.call_count, 5)
            original_board = [c['card'] for c in packet['board']]
            changed = source.copy()
            cv2.putText(changed, 'CALL / RAISE', (20, changed.shape[0] - 20), 0, .5, (255,255,255), 1)
            for _ in range(3):
                packet = send(changed)
                self.assertTrue(packet['card_cache']['inference_skipped'])
                self.assertEqual([c['card'] for c in packet['board']], original_board)
            smaller = cv2.resize(changed, (round(changed.shape[1] * .8), round(changed.shape[0] * .8)))
            packet = send(smaller)
            self.assertTrue(packet['card_cache']['inference_skipped'])
            self.assertEqual(self.detector.detect.call_count, 5)
            # Return to the original pose and reveal the previously empty turn.
            x, y = 654 + 101 * 3, 395
            scale = game.shape[1] / 1762
            box = [round(v * scale) for v in (x - 24, y - 30, x + 26, y + 35)]
            left, top, right, bottom = box
            source[top + viewport[1]:bottom + viewport[1], left + viewport[0]:right + viewport[0]] = 255
            turn = dict(card='AS', accepted=True, confidence=.99,
                        bbox=[round(v * scale) for v in (x - 12, y - 20, x + 12, y + 20)])
            self.detector.detect.return_value = dict(cards=cards + [turn], processing_ms=1)
            for _ in range(5):
                packet = send(source)
                self.assertFalse(packet['card_cache']['inference_skipped'])
                recognition_frame = self.detector.detect.call_args.args[0]
                for card in cards:
                    a,b,c,d = card['bbox']
                    self.assertFalse(np.any(recognition_frame[b:d,a:c]))
            self.assertEqual(packet['board'][3]['card'], 'AS')
            packet = send(source)
            self.assertTrue(packet['card_cache']['inference_skipped'])
            self.assertEqual(self.detector.detect.call_count, 10)
            # Removing the hero's physical cards must end this cycle, and a
            # new deal must acquire fresh identities rather than cached ones.
            from table_profiles import NINE_HERO
            folded = source.copy()
            for region in NINE_HERO:
                a, b, c, d = [round(v * scale) for v in region]
                folded[b + viewport[1]:d + viewport[1], a + viewport[0]:c + viewport[0]] = (30, 120, 30)
            self.detector.detect.return_value = dict(cards=cards[:3] + [turn], processing_ms=1)
            for _ in range(5):
                packet = send(folded)
                self.assertTrue(packet['card_cache']['inference_skipped'])
            self.assertFalse(packet['hand_cycle']['active'])
            self.assertEqual([c['card'] for c in packet['player_hand']], [None, None])
            new_deal = source.copy()
            for slot in range(4):
                cx = 654 + 101 * slot
                a, b, c, d = [round(v * scale) for v in (cx - 24, 365, cx + 26, 430)]
                new_deal[b + viewport[1]:d + viewport[1], a + viewport[0]:c + viewport[0]] = (30,120,30)
            new_hand = [dict(card, card=code) for card, code in zip(cards[3:], ('AH', 'KD'))]
            self.detector.detect.return_value = dict(cards=new_hand, processing_ms=1)
            for _ in range(9):
                packet = send(new_deal)
            self.assertEqual(packet['hand_cycle']['count'], 2)
            self.assertEqual([c['card'] for c in packet['player_hand']], ['AH', 'KD'])
            self.assertEqual([c['card'] for c in packet['board']], [None] * 5)
            packet = send(new_deal)
            self.assertTrue(packet['card_cache']['inference_skipped'])

    def test_fixed_bet_model_option_reaches_service_without_player_profiles(self):
        service = Mock()
        service.submit.return_value = dict(status='waiting', bet_scenario=dict(status='waiting'))
        self.server.RequestHandlerClass = make_handler(self.detector, 'test-token', equity_service=service)
        frame = cv2.imencode('.png', np.full((100, 200, 3), 80, np.uint8))[1].tobytes()
        headers = {'X-Capture-Token': 'test-token', 'X-Capture-Session': 'fixed-bets',
                   'X-Equity-Bet-Model': '1'}
        status, body = self.request('POST', '/frame', frame, headers)
        self.assertEqual(status, 200)
        self.assertTrue(service.submit.call_args.kwargs['bet_model'])
        self.assertEqual(json.loads(body)['poker_advice_bets']['status'], 'waiting')

    def test_desktop_six_diagnosis_confirms_five_opponents_via_http(self):
        from pathlib import Path
        frame = cv2.imread(str(Path(__file__).resolve().parent / 'fixtures/six-five-covered-opponents.jpg'))
        encoded = cv2.imencode('.jpg', frame)[1].tobytes()
        headers = {'X-Capture-Token': 'test-token', 'X-Capture-Session': 'six-five-opponents'}
        with patch('browser_capture.perf_counter', side_effect=[i * .1 for i in range(200)]):
            for index in range(5):
                status, body = self.request('POST', '/frame', encoded, headers)
                self.assertEqual(status, 200)
                result = json.loads(body)
                self.assertTrue(result['alignment_ready'])
                self.assertEqual(result['table_profile'], 'pokerstars-desktop-six')
                self.assertEqual(result['opponents']['count'], 5 if index == 4 else None)

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

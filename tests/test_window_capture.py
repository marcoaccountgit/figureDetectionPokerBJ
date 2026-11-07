"""Regression from the user's 14:06:38 screenshot, plus resize/offset cases."""
from pathlib import Path
import unittest

from card_detector import cv2,np
from capture_alignment import CaptureAligner,restore_coordinates
from hand_counter import player_card_presence
from opponent_detector import OpponentDetector,OpponentTracker
from table_profiles import DESKTOP_SIX,desktop_table_viewport
from table_observer import parse_table_amount
from equity_service import EquityService

ROOT=Path(__file__).resolve().parents[1]


class WindowCaptureTests(unittest.TestCase):
    @unittest.skipUnless((ROOT/'models/pokerstars-nine.onnx').exists(),'Local trained weights unavailable')
    def test_chip_stack_frame_through_http_confirms_cards_hand_and_opponents(self):
        import http.client,json,threading,time
        from http.server import ThreadingHTTPServer
        from browser_capture import make_handler
        from learned_detector import TableCardDetector
        from equity_service import OCRGameState
        detector=TableCardDetector()
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(detector,'fixture-test'))
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        client=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=30)
        payload=(ROOT/'tests/fixtures/adelinda-six-chip-stack.jpg').read_bytes()
        try:
            for _ in range(10):
                client.request('POST','/frame',payload,{'X-Capture-Token':'fixture-test','X-Capture-Session':'chip-stack'})
                response=client.getresponse();result=json.loads(response.read())
                self.assertEqual(response.status,200)
                time.sleep(.08)
            self.assertTrue(result['capture_alignment']['ready'])
            self.assertEqual([c['card'] for c in result['board']],['8H','AH','5D',None,None])
            self.assertEqual([c['card'] for c in result['player_hand']],['QD','8S'])
            self.assertEqual(result['hand_cycle']['count'],1)
            self.assertTrue(result['hand_cycle']['active'])
            self.assertEqual(result['opponents']['count'],2)
            state=OCRGameState().update(result,'chip-stack')
            self.assertEqual(state['opponents_count'],2)
            self.assertEqual(state['community_cards'],['8h','Ah','5d'])
        finally:
            client.close();server.shutdown();server.server_close();worker.join()

    def test_chip_stack_does_not_block_registration_and_card_reading(self):
        from learned_detector import TableCardDetector
        from table_layout import arrange_table
        from browser_capture import live_confirmation
        frame=cv2.imread(str(ROOT/'tests/fixtures/adelinda-six-chip-stack.jpg'))
        aligner=CaptureAligner();game,_=aligner.align(frame)
        self.assertTrue(aligner.alignment_ready)
        self.assertEqual(aligner.profile,DESKTOP_SIX)
        self.assertEqual([c['present'] for c in player_card_presence(game,aligner.profile)],[True,True])
        if not (ROOT/'models/pokerstars-nine.onnx').exists():
            self.skipTest('Local trained weights unavailable')
        detector=TableCardDetector();detector.profile=aligner.profile
        result=arrange_table(detector.detect(game),game.shape)
        tracker=live_confirmation()
        for i in range(5):
            confirmed=arrange_table(tracker.update(result,i*.1,game.shape),game.shape)
        self.assertEqual([c['card'] for c in confirmed['board']],['8H','AH','5D',None,None])
        self.assertEqual([c['card'] for c in confirmed['player_hand']],['QD','8S'])

    def test_alternative_rails_require_two_consistent_references(self):
        from unittest.mock import patch
        frame=cv2.imread(str(ROOT/'tests/fixtures/adelinda-six-chip-stack.jpg'))
        with patch('table_profiles._match_desktop_rail',side_effect=[None,((0,0,1192,860),.99),None,None,None]):
            self.assertIsNone(desktop_table_viewport(frame))
        with patch('table_profiles._match_desktop_rail',side_effect=[None,((0,0,1192,860),.99),((100,100,1292,960),.99),None,None]):
            self.assertIsNone(desktop_table_viewport(frame))

    def test_chip_stack_frame_recovers_a_previously_lost_alignment(self):
        frame=cv2.imread(str(ROOT/'tests/fixtures/adelinda-six-chip-stack.jpg'))
        aligner=CaptureAligner();aligner.desktop_viewport=(-110,19,1301,901)
        aligner.desktop_shape=frame.shape[:2];aligner.profile=DESKTOP_SIX
        states=[]
        for _ in range(3):
            aligner.align(frame);states.append(aligner.alignment_ready)
        self.assertEqual(states,[False,False,True])

    def test_live_nine_showdown_animation_keeps_all_board_cards_confirmed(self):
        from learned_detector import TableCardDetector
        from table_layout import arrange_table
        from browser_capture import live_confirmation
        if not (ROOT/'models/pokerstars-nine.onnx').exists():
            self.skipTest('Desktop model unavailable')
        detector=TableCardDetector();aligner=CaptureAligner();tracker=live_confirmation();readings=[]
        for name in ('nine-showdown-rest.png','nine-showdown-raised.png'):
            frame=cv2.imread(str(ROOT/'tests/fixtures'/name))
            game,_=aligner.align(frame);detector.profile=aligner.profile
            result=arrange_table(detector.detect(game),game.shape)
            self.assertEqual([c['card'] for c in result['board']],['4D','5H','JH','10C','QD'])
            readings.append((result,game.shape))
        for i in range(8):
            result,shape=readings[i%2]
            confirmed=arrange_table(tracker.update(result,i*.2,shape),shape)
            if i>=4:
                self.assertEqual([c['card'] for c in confirmed['board']],['4D','5H','JH','10C','QD'])

    @classmethod
    def setUpClass(cls):
        cls.frame=cv2.imread(str(ROOT/'tests/fixtures/themis-window.png'))

    def test_small_desktop_window_registers_table_instead_of_browser(self):
        aligner=CaptureAligner();game,viewport=aligner.align(self.frame)
        self.assertEqual(aligner.profile,DESKTOP_SIX)
        self.assertTrue(aligner.alignment_ready)
        self.assertEqual(aligner.last_anchor['method'],'table_rail')
        self.assertLess(viewport[0],0)
        self.assertEqual(game.shape[1],viewport[2]-viewport[0])
        self.assertEqual(game.shape[0],viewport[3]-viewport[1])
        self.assertEqual([p['present'] for p in player_card_presence(game,aligner.profile)],[True,True])

    def test_border_anchor_does_not_reclassify_the_old_browser_layout(self):
        frame=cv2.imread(str(ROOT/'artifacts/capture10-improvement/dataset/reviewed/80.png'))
        if frame is None:self.skipTest('Local legacy recording fixture unavailable')
        self.assertIsNone(desktop_table_viewport(frame))

    def test_resize_and_window_position_preserve_registration(self):
        for factor in (.8,1.,1.3):
            resized=cv2.resize(self.frame,None,fx=factor,fy=factor)
            frame=np.zeros((round(resized.shape[0]+150),round(resized.shape[1]+320),3),np.uint8)
            frame[60:60+resized.shape[0],150:150+resized.shape[1]]=resized
            aligner=CaptureAligner();game,viewport=aligner.align(frame)
            self.assertEqual(aligner.profile,DESKTOP_SIX)
            self.assertTrue(aligner.alignment_ready)

    def test_lost_reference_suspends_analysis_and_recovers(self):
        aligner=CaptureAligner();aligner.align(self.frame)
        aligner.align(np.zeros_like(self.frame))
        self.assertFalse(aligner.alignment_ready)
        self.assertEqual(aligner.profile,DESKTOP_SIX)
        aligner.align(self.frame)
        self.assertTrue(aligner.alignment_ready)
        service=EquityService()
        try:
            result=service.submit(dict(alignment_ready=False),'test')
            self.assertEqual(result['status'],'waiting')
            self.assertIn('Allineamento',result['message'])
        finally:service.close()

    def test_desktop_six_counts_two_visible_opponents(self):
        aligner=CaptureAligner();game,_=aligner.align(self.frame)
        seats=OpponentDetector().detect(game,profile=aligner.profile)
        self.assertEqual([s['seat'] for s in seats if s['present']],['lower_left','lower_right'])
        tracker=OpponentTracker()
        for i in range(5):result=tracker.update(seats,i*.1,[dict(detected=True)]*2)
        self.assertEqual(result['count'],2)
        self.assertEqual(result['max_opponents'],5)

    def test_bare_chips_ending_in_88_are_not_misread_as_bb(self):
        for text,value in [('15,188',15188),('1.288',1288),('1288',1288)]:
            self.assertEqual(parse_table_amount(text,DESKTOP_SIX)['value'],value)
            self.assertEqual(parse_table_amount(text,DESKTOP_SIX)['unit'],'CHIPS')

    @unittest.skipUnless((ROOT/'models/pokerstars-nine.onnx').exists(),'Local trained weights unavailable')
    def test_actual_model_reads_hero_and_board_after_window_registration(self):
        from learned_detector import TableCardDetector
        from table_layout import arrange_table
        aligner=CaptureAligner();game,viewport=aligner.align(self.frame)
        detector=TableCardDetector();detector.profile=aligner.profile
        result=arrange_table(detector.detect(game),game.shape)
        self.assertEqual([c['card'] for c in result['board']],['3C','KS','AH',None,None])
        self.assertEqual([c['card'] for c in result['player_hand']],['2C','2D'])
        restored=restore_coordinates(result,viewport,self.frame.shape)
        for c in restored['cards']:
            if c['accepted']:
                self.assertGreaterEqual(c['bbox'][0],0)
                self.assertLessEqual(c['bbox'][2],self.frame.shape[1])


if __name__=='__main__':unittest.main()

import json,unittest
from pathlib import Path
from card_detector import cv2,np
from capture_alignment import CaptureAligner
from table_profiles import DESKTOP_SIX,desktop_stack_box,desktop_seat_profile

ROOT=Path(__file__).resolve().parents[1]

class NewDesktopVideoTests(unittest.TestCase):
    def test_training_splits_keep_complete_hands_separate(self):
        spec=json.loads((ROOT/'datasets/desktop-200950.json').read_text())
        hands={}
        for e in spec['frames']:
            self.assertEqual(hands.setdefault(e['hand'],e['split']),e['split'])
            self.assertGreaterEqual(e['time'],0);self.assertLess(e['time'],720)
            cards=e['board']+e['hole'];self.assertEqual(len(cards),len(set(cards)))

    def test_highlighted_six_seat_hud_is_not_nine_seats(self):
        for name in ('six-highlight.jpg','six-highlight-focus.jpg'):
            f=cv2.imread(str(ROOT/'tests/fixtures'/name))
            for width in (960,1280,1918):
                frame=cv2.resize(f,(width,round(f.shape[0]*width/f.shape[1])))
                a=CaptureAligner();a.align(frame)
                self.assertEqual(a.profile,DESKTOP_SIX,(name,width))

    def test_waiting_for_opponents_keeps_confirmed_six_seat_layout(self):
        active=cv2.imread(str(ROOT/'tests/fixtures/six-highlight.jpg'))
        waiting=cv2.imread(str(ROOT/'tests/fixtures/six-waiting.jpg'))
        a=CaptureAligner();a.align(active);a.align(waiting)
        self.assertEqual(a.profile,DESKTOP_SIX)

    def test_desktop_without_adaptive_viewport_suspends_when_source_disappears(self):
        active=cv2.imread(str(ROOT/'tests/fixtures/six-highlight.jpg'))
        a=CaptureAligner();a.align(active)
        a.desktop_viewport=None
        a.align(np.zeros_like(active))
        self.assertFalse(a.alignment_ready)

    def test_hero_stack_crop_keeps_the_top_of_digits_and_all_in(self):
        _,top,_,bottom=desktop_stack_box(DESKTOP_SIX,'hero')
        self.assertLessEqual(top,round(850*1762/1918))
        self.assertGreaterEqual(bottom,round(872*1762/1918))

    @unittest.skipUnless((ROOT/'models/pokerstars-nine.onnx').exists(),'Local trained weights unavailable')
    def test_trained_model_handles_ace_black_three_and_four_clubs(self):
        from learned_detector import TableCardDetector
        from table_layout import arrange_table
        d=TableCardDetector()
        cases=[('nine-ace-clubs-preview.png',[],['AC','3D']),
               ('six-black-three.jpg',['7S','JS','3S'],['8D','7D']),
               ('six-four-clubs.jpg',[],['6H','4C']),
               ('six-all-in-kings.jpg',['7H','4D','5H','KS'],['KC','KD'])]
        for name,board,hole in cases:
            frame=cv2.imread(str(ROOT/'tests/fixtures'/name));a=CaptureAligner();game,_=a.align(frame)
            d.profile=a.profile;r=arrange_table(d.detect(game),game.shape)
            self.assertEqual([c['card'] for c in r['board']],board+[None]*(5-len(board)),name)
            self.assertEqual([c['card'] for c in r['player_hand']],hole,name)

    @unittest.skipUnless((ROOT/'models/pokerstars-nine.onnx').exists(),'Local trained weights unavailable')
    def test_four_exposed_opponent_cards_are_read_at_showdown(self):
        from learned_detector import TableCardDetector
        from table_layout import arrange_table
        frame=cv2.imread(str(ROOT/'tests/fixtures/six-revealed-showdown.jpg'))
        a=CaptureAligner();game,_=a.align(frame);d=TableCardDetector();d.profile=a.profile
        r=arrange_table(d.detect(game),game.shape)
        self.assertEqual(sorted(c['card'] for c in r['cards'] if c['accepted'] and c['table_group']=='other'),
                         ['4H','6H','JD','JH'])

if __name__=='__main__':unittest.main()

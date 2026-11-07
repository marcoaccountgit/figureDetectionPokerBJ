import unittest
from pathlib import Path

from card_detector import cv2, np
from opponent_detector import OpponentDetector, OpponentTracker
from capture_alignment import restore_coordinates


def observations(active=(True,False,False,False,False)):
    return [dict(seat=str(i), label=str(i), present=v, bbox=[1,2,3,4] if v else None)
            for i,v in enumerate(active)]


class OpponentTests(unittest.TestCase):
    def test_six_seat_showdown_faces_are_not_counted_as_covered_pairs(self):
        from capture_alignment import CaptureAligner
        frame = cv2.imread(str(Path(__file__).resolve().parent / 'fixtures/six-revealed-showdown.jpg'))
        aligner = CaptureAligner()
        game, _ = aligner.align(frame)
        self.assertEqual([s['present'] for s in OpponentDetector().detect(game, profile=aligner.profile)],
                         [False] * 5)

    def test_six_seat_diagnoses_count_all_five_or_only_two_real_opponents(self):
        from capture_alignment import CaptureAligner
        from table_profiles import DESKTOP_SIX
        detector = OpponentDetector()
        root = Path(__file__).resolve().parent / 'fixtures'
        for name, expected in (
                ('six-five-covered-opponents.jpg', [True] * 5),
                ('six-two-covered-opponents.png', [True, False, False, True, False])):
            original = cv2.imread(str(root / name))
            for width in (762, 960, 1192, 1536):
                frame = cv2.resize(original, (width, round(original.shape[0] * width / original.shape[1])))
                aligner = CaptureAligner()
                game, viewport = aligner.align(frame)
                self.assertEqual(aligner.profile, DESKTOP_SIX)
                visible_y = (max(0, -viewport[1]) * 1762 / game.shape[1],
                             (min(frame.shape[0], viewport[3]) - viewport[1]) * 1762 / game.shape[1])
                visible_x = (max(0, -viewport[0]) * 1762 / game.shape[1],
                             (min(frame.shape[1], viewport[2]) - viewport[0]) * 1762 / game.shape[1])
                seats = detector.detect(game, visible_y, aligner.profile, visible_x)
                self.assertEqual([s['present'] for s in seats], expected, (name, width, seats))
                tracker = OpponentTracker()
                for i in range(5):
                    result = tracker.update(seats, i * .1, [])
                self.assertEqual(result['count'], sum(expected), (name, width))

    def test_variable_table_capacity_and_fold_count(self):
        for capacity in (2,5,6,8,9,10):
            tracker=OpponentTracker()
            values=(True,)*(capacity-1)
            for i in range(5):
                result=tracker.update(observations(values),i*.1,[])
            self.assertEqual(result['count'],capacity-1)
            self.assertEqual(result['max_opponents'],capacity-1)
            for i in range(5,10):
                result=tracker.update(observations((True,)+(False,)*(capacity-2)),i*.1,[])
            self.assertEqual(result['count'],1)

    def test_changed_layout_requires_new_confirmation(self):
        tracker=OpponentTracker()
        for i in range(5):tracker.update(observations(),i*.1,[])
        result=tracker.update(observations((True,)*9),.5,[])
        self.assertIsNone(result['count'])
        for i in range(6,10):result=tracker.update(observations((True,)*9),i*.1,[])
        self.assertEqual(result['count'],9)

    def test_duplicate_seats_do_not_make_a_confirmed_count(self):
        tracker=OpponentTracker()
        for i in range(5):
            result=tracker.update([observations()[0]]*5,i*.1,[])
        self.assertIsNone(result['count'])

    def test_a_seat_outside_the_visible_capture_is_unknown_not_absent(self):
        detector = OpponentDetector()
        frame = np.full((1100,1762,3),(30,65,30),np.uint8)
        seats = detector.detect(frame,visible_y=(156,1100))
        self.assertIsNone(seats[0]['present'])
        self.assertTrue(seats[0]['occluded'])
        self.assertFalse(seats[1]['present'])

    def test_counter_requires_five_spaced_observations_and_rechecks_fold(self):
        tracker = OpponentTracker()
        hand = [dict(detected=True),dict(detected=True)]
        for t in (0,.1,.2,.3):
            self.assertIsNone(tracker.update(observations(),t,hand)['count'])
        result = tracker.update(observations(),.4,hand)
        self.assertEqual(result['count'],1)
        self.assertEqual(result['players_with_cards'],2)
        self.assertIsNone(tracker.update(observations((False,)*5),.5,hand)['count'])
        for t in (.6,.7,.8,.9):
            result = tracker.update(observations((False,)*5),t,hand)
        self.assertEqual(result['count'],0)
        self.assertEqual(result['players_with_cards'],1)

    def test_fast_samples_ambiguity_and_session_gap_do_not_confirm(self):
        tracker = OpponentTracker()
        for t in (0,.01,.02,.03,.04):
            self.assertIsNone(tracker.update(observations(),t,[])['count'])
        self.assertEqual(tracker.update(observations(),.4,[])['count'],1)
        self.assertIsNone(tracker.update(observations((None,False,False,False,False)),.5,[])['count'])
        self.assertIsNone(tracker.update(observations(),.6,[])['count'])
        self.assertIsNone(tracker.update(observations(),3,[])['count'])

    def test_pair_template_is_found_at_correct_seat_at_multiple_scales(self):
        detector = OpponentDetector()
        # The template consists only of red backs and white borders.
        image = cv2.imread('assets/opponents/covered-pair.png')
        frame = np.full((984,1762,3),(30,65,30),np.uint8)
        frame[92:140,827:937] = image
        for scale in (1,.7):
            resized = cv2.resize(frame,(round(1762*scale),round(984*scale)))
            seats = detector.detect(resized)
            self.assertEqual([s['present'] for s in seats],[True,False,False,False,False])

    def test_nameplates_and_single_red_card_are_not_a_pair(self):
        detector = OpponentDetector()
        frame = np.full((984,1762,3),(30,65,30),np.uint8)
        cv2.putText(frame,'Giocatore seduto',(800,200),0,.7,(255,255,255),1)
        cv2.rectangle(frame,(830,95),(900,145),(255,255,255),-1)
        cv2.rectangle(frame,(834,99),(896,141),(30,30,150),-1)
        self.assertIsNot(detector.detect(frame)[0]['present'],True)

    def test_opponent_boxes_follow_capture_side_bar_offset(self):
        result = restore_coordinates({'opponents':{'seats':observations()}},(65,0,1827,984),(984,1892))
        self.assertEqual(result['opponents']['seats'][0]['bbox'],[66,2,68,4])

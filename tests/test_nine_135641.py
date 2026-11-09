import json
from pathlib import Path
import unittest
from unittest.mock import Mock,patch
from card_detector import cv2
from capture_alignment import CaptureAligner
from opponent_detector import OpponentDetector,OpponentTracker
from table_profiles import NINE,NINE_BACKS
from table_observer import TableVisualReader

ROOT=Path(__file__).resolve().parents[1]


class ReviewedNineVideoTests(unittest.TestCase):
    def test_nine_finetuning_keeps_the_desktop_six_network_independent(self):
        from learned_detector import TableCardDetector
        from table_profiles import DESKTOP_SIX
        with patch('learned_detector.LearnedCardDetector') as factory:
            browser,nine,six=Mock(),Mock(),Mock()
            nine.detect.return_value=dict(cards=[])
            six.detect.return_value=dict(cards=[])
            factory.side_effect=[browser,nine,six]
            detector=TableCardDetector()
            detector.profile=NINE;detector.detect(None)
            detector.profile=DESKTOP_SIX;detector.detect(None)
            self.assertIs(detector.models[NINE],nine)
            self.assertIs(detector.models[DESKTOP_SIX],six)
            self.assertEqual(factory.call_args.kwargs,dict(asset_profile=DESKTOP_SIX))

    def test_back_training_never_uses_held_out_hands(self):
        spec=json.loads((ROOT/'datasets/nine-135641.json').read_text())
        hands={}
        for row in spec['frames']:
            self.assertEqual(hands.setdefault(row['hand'],row['split']),row['split'])
        provenance=json.loads((ROOT/'assets/table-nine/variants/135641-provenance.json').read_text())
        labels={row['time']:row for row in spec['frames']}
        for row in provenance['references']:
            self.assertEqual(labels[row['time']]['split'],'train')
            self.assertTrue(labels[row['time']]['seats'][row['seat']])
        self.assertEqual({row['seat'] for row in provenance['references']},set(NINE_BACKS))

    def test_reviewed_seats_confirm_the_correct_count_across_sizes(self):
        detector=OpponentDetector()
        cases={
            'nine-eight-compact':set(NINE_BACKS),
            'nine-six-compact':{'top_left','upper_left','upper_right','middle_right','lower_left','lower_right'},
            'nine-three-green-avatar':{'top_left','middle_left','lower_right'},
            'nine-two-dimmed':{'upper_left','middle_left'},
            'nine-three-folded-left':{'upper_right','middle_right','lower_right'},
        }
        for name,expected in cases.items():
            source=cv2.imread(str(ROOT/'tests/fixtures'/f'{name}.png'))
            for width in (768,960,1280):
                with self.subTest(name=name,width=width):
                    image=cv2.resize(source,(width,round(source.shape[0]*width/source.shape[1])))
                    aligner=CaptureAligner();game,_=aligner.align(image)
                    self.assertEqual(aligner.profile,NINE)
                    seats=detector.detect(game,profile=aligner.profile)
                    self.assertEqual({s['seat'] for s in seats if s['present'] is True},expected)
                    self.assertFalse(any(s['present'] is None for s in seats))
                    tracker=OpponentTracker()
                    for i in range(5):result=tracker.update(seats,i*.1,[])
                    self.assertEqual(result['count'],len(expected))

    def test_statistics_panel_cannot_be_interpreted_as_empty_seats(self):
        normal=cv2.imread(str(ROOT/'tests/fixtures/nine-eight-compact.png'))
        covered=cv2.imread(str(ROOT/'tests/fixtures/nine-statistics-covered.png'))
        for prior_frame in (None,normal):
            for width in (768,960,1280):
                aligner=CaptureAligner()
                if prior_frame is not None:aligner.align(prior_frame)
                image=cv2.resize(covered,(width,round(covered.shape[0]*width/covered.shape[1])))
                aligner.align(image)
                self.assertFalse(aligner.alignment_ready)
                self.assertEqual(aligner.profile,NINE)
                self.assertEqual(aligner.last_anchor['reason'],'table_occluded')

    def test_middle_right_dealer_button_is_not_assigned_to_lower_right(self):
        source=cv2.imread(str(ROOT/'tests/fixtures/nine-three-folded-left.png'))
        reader=TableVisualReader(None,NINE)
        for width in (768,960,1280):
            image=cv2.resize(source,(width,round(source.shape[0]*width/source.shape[1])))
            game,_=CaptureAligner().align(image)
            self.assertEqual(reader.dealer_button(game)['seat'],'middle_right')

    def test_compact_two_spades_is_not_locked_as_two_clubs(self):
        from learned_detector import TableCardDetector
        from table_layout import arrange_table
        source=cv2.imread(str(ROOT/'tests/fixtures/nine-ten-two-spades.png'))
        detector=TableCardDetector()
        for width in (768,960,1280):
            image=cv2.resize(source,(width,round(source.shape[0]*width/source.shape[1])))
            aligner=CaptureAligner();game,_=aligner.align(image)
            detector.profile=aligner.profile
            result=arrange_table(detector.detect(game),game.shape)
            self.assertEqual([c['card'] for c in result['player_hand']],['10S','2S'])


if __name__=='__main__':unittest.main()

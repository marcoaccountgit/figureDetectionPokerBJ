import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from card_detector import Recognizer, cv2, np
from learned_detector import LearnedCardDetector, decode_indices, letterbox

NAMES = [rank + suit for rank in ['10', *'23456789', 'A', 'J', 'K', 'Q'] for suit in 'CDHS']


def output_for(rows):
    output = np.zeros((1, 56, len(rows)), np.float32)
    for index, (box, scores) in enumerate(rows):
        output[0, :4, index] = box
        for code, score in scores.items():
            output[0, 4 + NAMES.index(code), index] = score
    return output


class LearnedDetectorTests(unittest.TestCase):
    def test_weaker_neural_duplicate_cannot_suppress_confirmed_symbol_reading(self):
        detector=LearnedCardDetector.__new__(LearnedCardDetector)
        detector.profile='pokerstars-nine';detector.crop=None;detector.names=NAMES
        detector.net=Mock()
        detector.net.forward.side_effect=[
            output_for([([100,200,40,80],{'7D':.98})]),
            output_for([([100,200,22,78],{'JD':.71})])]
        detector._symbol_reading=Mock(side_effect=[dict(
            rank='7',suit='D',card='7D',accepted=True,confidence=.92,
            decision_source='training_symbol_references'),None])
        detector._recover_nine_indices=Mock()
        with patch('learned_detector.additional_table_regions',return_value=([[0,0,640,640]],[])):
            result=detector.detect(np.full((640,640,3),255,np.uint8))
        self.assertEqual([c['card'] for c in result['cards']],['7D'])

    def test_real_small_window_recovers_5c_without_changing_8c(self):
        from capture_alignment import CaptureAligner
        from table_layout import arrange_table
        frame = cv2.imread(str(Path(__file__).parent/'fixtures/six-8c5c-uncertain.png'))
        aligner = CaptureAligner(); game, _ = aligner.align(frame)
        detector = LearnedCardDetector('pokerstars-nine')
        result = detector.detect(game)
        result['table_profile'] = aligner.profile
        arranged = arrange_table(result,game.shape)
        self.assertEqual([c['card'] for c in arranged['player_hand']],['8C','5C'])
        recovered = [c for c in result['cards'] if c['card']=='5C'][0]
        self.assertGreaterEqual(recovered['confidence'],.60)
        if recovered['decision_source'] in ('model','enlarged_model_recovery'):
            self.assertGreaterEqual(recovered['class_margin'],.15)
        else:
            self.assertGreaterEqual(recovered['rank_score'],.90)
            self.assertGreaterEqual(recovered['suit_score'],.90)
        self.assertLessEqual(result['uncertain_retries'],1)

    def test_symbol_cache_reuses_comparison_but_returns_independent_results(self):
        detector = LearnedCardDetector.__new__(LearnedCardDetector)
        detector.symbol_classifier = Mock()
        detector.symbol_classifier.classify_symbols.return_value = dict(
            card='5C',accepted=True,rank_score=.96,suit_score=.95)
        glyph = np.ones((26,22),np.uint8)
        with patch('learned_detector.stacked_index_symbols',return_value=((glyph,glyph),'black')):
            first = detector._symbol_reading(np.zeros((40,20,3),np.uint8))
            first['card'] = 'AS'
            self.assertEqual(detector._symbol_reading(np.zeros((40,20,3),np.uint8))['card'], '5C')
            detector.symbol_classifier.classify_symbols.assert_called_once()
            glyph[0,0] = 0
            detector._symbol_reading(np.zeros((40,20,3),np.uint8))
            self.assertEqual(detector.symbol_classifier.classify_symbols.call_count,2)

    def test_enlarged_retry_is_bounded_and_rejects_conflicting_codes(self):
        detector = LearnedCardDetector.__new__(LearnedCardDetector)
        detector.net = Mock(); detector.names = NAMES
        detector._symbol_reading = Mock(return_value=None)
        card = dict(card=None,rank='5',suit='C',accepted=False,confidence=.32,bbox=[100,100,120,140])
        proposal = dict(card='5C',rank='5',suit='C',accepted=True,confidence=.8,class_margin=.6,bbox=[100,100,120,140])
        frame = np.full((640,640,3),255,np.uint8)
        with patch('learned_detector.decode_indices', return_value=[proposal]):
            self.assertEqual(detector._retry_uncertain_indices(frame,[card]),1)
        self.assertEqual(card['card'],'5C')
        self.assertEqual(card['decision_source'],'enlarged_model_recovery')
        detector.net.forward.assert_called_once()
        detector.net.reset_mock()
        self.assertEqual(detector._retry_uncertain_indices(frame,[card]),0)
        detector.net.forward.assert_not_called()
        card.update(card=None,accepted=False)
        with patch('learned_detector.decode_indices', return_value=[dict(proposal,card='6C')]):
            detector._retry_uncertain_indices(frame,[card])
        self.assertFalse(card['accepted'])
        self.assertIsNone(card['card'])

    def test_retry_does_not_infer_cards_from_background(self):
        detector = LearnedCardDetector.__new__(LearnedCardDetector)
        detector.net = Mock()
        card = dict(card=None,rank='5',suit='C',accepted=False,bbox=[100,100,120,140])
        self.assertEqual(detector._retry_uncertain_indices(np.zeros((640,640,3),np.uint8),[card]),0)
        detector.net.forward.assert_not_called()

    def test_reviewed_references_cannot_override_an_existing_strong_symbol_reading(self):
        detector = LearnedCardDetector.__new__(LearnedCardDetector)
        detector.symbol_classifier = Mock()
        detector.reviewed_symbol_classifier = Mock()
        detector.symbol_classifier.classify_symbols.return_value = dict(
            card='4S',accepted=True,rank_score=.95,suit_score=.94)
        with patch('learned_detector.stacked_index_symbols',return_value=((None,None),'black')):
            result = detector._symbol_reading(np.zeros((100,40,3),np.uint8))
        self.assertEqual(result['card'],'4S')
        self.assertEqual(result['decision_source'],'training_symbol_references')
        detector.reviewed_symbol_classifier.classify_symbols.assert_not_called()

    def test_reviewed_references_recover_ambiguity_without_lowering_score_requirement(self):
        detector = LearnedCardDetector.__new__(LearnedCardDetector)
        detector.symbol_classifier = Mock()
        detector.reviewed_symbol_classifier = Mock()
        detector.symbol_classifier.classify_symbols.return_value = dict(
            card=None,accepted=False,rank_score=.88,suit_score=.89)
        detector.reviewed_symbol_classifier.classify_symbols.return_value = dict(
            card='3C',accepted=True,rank_score=.95,suit_score=.94)
        with patch('learned_detector.stacked_index_symbols',return_value=((None,None),'black')):
            result = detector._symbol_reading(np.zeros((100,40,3),np.uint8))
        self.assertEqual(result['card'],'3C')
        self.assertEqual(result['decision_source'],'reviewed_symbol_references')

    def test_reviewed_club_glyphs_are_loaded_without_changing_base_references(self):
        root = Path(__file__).resolve().parents[1]
        base = Recognizer(root/'models/pokerstars-symbols')
        extended = Recognizer(root/'models/pokerstars-symbols',extra_assets=[root/'assets/pokerstars-reviewed-symbols'])
        self.assertGreater(len(extended.templates['rank']['3']),len(base.templates['rank']['3']))
        self.assertGreater(len(extended.templates['suit']['C']),len(base.templates['suit']['C']))
        for rank,source in [('3','192703'),('4','192744')]:
            glyphs = [cv2.imread(str(root/f'assets/pokerstars-reviewed-symbols/{kind}/{label}_reviewed_{source}_native.png'),cv2.IMREAD_GRAYSCALE)>0
                      for kind,label in [('rank',rank),('suit','C')]]
            result = extended.classify_symbols(glyphs,'black')
            self.assertTrue(result['accepted'])
            self.assertEqual(result['card'],rank+'C')
            self.assertGreaterEqual(min(result['rank_score'],result['suit_score']),.90)
    def test_missing_player_index_is_recovered_at_reference_scale_without_duplicates(self):
        detector = LearnedCardDetector.__new__(LearnedCardDetector)
        detector._symbol_reading = Mock(side_effect=lambda image: dict(
            rank='3',suit='S',card='3S',accepted=True,confidence=.93))
        frame = np.full((984,1762,3),(30,65,30),np.uint8)
        frame[650:746,648:686] = 255
        cards = []
        detector._recover_player_indices(frame,cards)
        self.assertEqual([c['card'] for c in cards],['3S'])
        self.assertEqual(cards[0]['bbox'],[648,650,686,746])
        self.assertEqual(detector._symbol_reading.call_args.args[0].shape,(96,38,3))
        detector._recover_player_indices(frame,cards)
        self.assertEqual(len(cards),1)
        self.assertEqual(detector._symbol_reading.call_count,1)

    def test_player_recovery_does_not_accept_background_or_weak_symbols(self):
        detector = LearnedCardDetector.__new__(LearnedCardDetector)
        detector._symbol_reading = Mock(return_value=None)
        frame = np.full((984,1762,3),(30,65,30),np.uint8)
        cards = []
        detector._recover_player_indices(frame,cards)
        detector._symbol_reading.assert_not_called()
        frame[650:746,648:686] = 255
        detector._recover_player_indices(frame,cards)
        self.assertEqual(cards,[])
        detector._symbol_reading.assert_called_once()

    def test_uncertain_existing_index_is_rechecked_and_replaced_without_duplicates(self):
        detector = LearnedCardDetector.__new__(LearnedCardDetector)
        detector._symbol_reading = Mock(return_value=dict(rank='K',suit='S',card='KS',accepted=True,confidence=.93))
        frame = np.full((984,1762,3),(30,65,30),np.uint8)
        frame[650:746,648:686] = 255
        cards = [dict(rank='K',suit='S',card=None,accepted=False,confidence=.31,bbox=[647,649,687,747])]
        detector._recover_player_indices(frame,cards)
        self.assertEqual(len(cards),1)
        self.assertEqual(cards[0]['card'],'KS')
        self.assertEqual(cards[0]['neural_confidence'],.31)
        self.assertEqual(cards[0]['decision_source'],'fixed_player_index_recovery')
        detector._recover_player_indices(frame,cards)
        self.assertEqual(len(cards),1)
        self.assertEqual(detector._symbol_reading.call_count,1)

    def test_confident_wrong_rank_is_cross_checked_against_strong_symbols(self):
        detector = LearnedCardDetector.__new__(LearnedCardDetector)
        detector.profile = 'pokerstars'
        detector.crop = None
        detector.names = NAMES
        detector.net = Mock()
        detector.net.forward.return_value = output_for([([100,200,40,80], {'AS':.92})])
        detector._symbol_reading = Mock(return_value=dict(
            rank='4',suit='S',card='4S',accepted=True,confidence=.91,
            decision_source='training_symbol_references'))
        result = detector.detect(np.zeros((640,640,3),np.uint8))
        card = result['cards'][0]
        self.assertEqual(card['card'], '4S')
        self.assertEqual(card['neural_candidate'], 'AS')
        self.assertEqual(card['neural_confidence'], .92)
        self.assertTrue(card['symbol_corrected'])
        self.assertTrue(card['accepted'])

    def test_no_strong_symbol_reading_preserves_network_prediction(self):
        detector = LearnedCardDetector.__new__(LearnedCardDetector)
        detector.profile = 'pokerstars'
        detector.crop = None
        detector.names = NAMES
        detector.net = Mock()
        detector.net.forward.return_value = output_for([([100,200,40,80], {'AS':.92})])
        detector._symbol_reading = Mock(return_value=None)
        card = detector.detect(np.zeros((640,640,3),np.uint8))['cards'][0]
        self.assertEqual(card['card'], 'AS')
        self.assertNotIn('symbol_corrected', card)

    def test_letterbox_preserves_aspect_and_converts_bgr_to_rgb(self):
        frame = np.full((800, 400, 3), (10, 20, 30), np.uint8)
        blob, scale, left, top = letterbox(frame)
        self.assertEqual(blob.shape, (1, 3, 640, 640))
        self.assertEqual((scale, left, top), (.8, 160, 0))
        np.testing.assert_allclose(blob[0, :, 100, 200], np.array([30, 20, 10]) / 255, atol=1e-6)

    def test_box_coordinates_remove_padding_and_scale(self):
        # Portrait image: x padding is 160. Original box [50,100,100,200].
        output = output_for([([220, 120, 40, 80], {'10D': .9})])
        result = decode_indices(output, NAMES, (800, 400, 3), .8, 160, 0)
        self.assertEqual(result[0]['bbox'], [50, 100, 100, 200])
        self.assertEqual(result[0]['card'], '10D')

    def test_nms_removes_duplicate_boxes_without_merging_same_code_elsewhere(self):
        output = output_for([
            ([100, 200, 40, 80], {'10D': .9}),
            ([101, 200, 40, 80], {'10D': .85}),
            ([400, 200, 40, 80], {'10D': .88}),
        ])
        result = decode_indices(output, NAMES, (640, 640, 3), 1, 0, 0)
        self.assertEqual(len(result), 2)
        self.assertTrue(all(card['card'] == '10D' for card in result))

    def test_ambiguous_suit_is_not_confirmed(self):
        output = output_for([([100, 200, 40, 80], {'10D': .7, '10H': .65})])
        result = decode_indices(output, NAMES, (640, 640, 3), 1, 0, 0)
        self.assertFalse(result[0]['accepted'])
        self.assertIsNone(result[0]['card'])

    def test_invalid_and_outside_boxes_do_not_create_detections(self):
        output = output_for([
            ([np.nan, 200, 40, 80], {'10D': .9}),
            ([-200, -200, 40, 80], {'10D': .9}),
            ([100, 200, -40, 80], {'10D': .9}),
        ])
        self.assertEqual(decode_indices(output, NAMES, (640, 640, 3), 1, 0, 0), [])

    def test_unexpected_model_output_fails_explicitly(self):
        with self.assertRaisesRegex(RuntimeError, 'Output ONNX inatteso'):
            decode_indices(np.zeros((1, 5, 8400)), NAMES, (640, 640, 3), 1, 0, 0)


if __name__ == '__main__':
    unittest.main()

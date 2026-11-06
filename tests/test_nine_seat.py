import json
from pathlib import Path
import unittest
from unittest.mock import Mock,patch

from card_detector import cv2,np
from capture_alignment import CaptureAligner
from equity_service import OCRGameState
from hand_counter import player_card_presence
from opponent_detector import OpponentTracker
from table_layout import arrange_table
from table_profiles import NINE,NINE_ORDER,NINE_HERO,NINE_BACKS,nine_header
from table_observer import parse_table_amount,positions_from_button,ocr_mosaic
from table_number_reader import ChipNumberReader

ROOT=Path(__file__).resolve().parents[1]


class NineSeatTests(unittest.TestCase):
    def test_training_frames_stop_before_disconnect_and_hands_are_disjoint(self):
        spec=json.loads((ROOT/'datasets/nine-seat-125816.json').read_text())
        self.assertTrue(all(0<=f['time']<840 for f in spec['frames']))
        hands={}
        for f in spec['frames']:
            self.assertEqual(hands.setdefault(f['hand'],f['split']),f['split'])
        self.assertEqual(spec['annotation_revision'],2)

    def test_chip_units_are_explicit_profile_specific_and_thousands_not_decimals(self):
        for text,expected in [('1.500',1500),('49,500',49500),('1 .ooo',1000),('51 *872',51872),('250',250)]:
            value=parse_table_amount(text,NINE)
            self.assertEqual(value['value'],expected)
            self.assertEqual(value['unit'],'CHIPS')
            self.assertIsNone(parse_table_amount(text))
        for invalid in ('Gdemy57','12.34','OOO','NaN','-50','500 chips'):
            self.assertIsNone(parse_table_amount(invalid,NINE))
        self.assertEqual(parse_table_amount('1.5BB',NINE)['unit'],'BB')

    def test_nine_positions_include_all_players_and_heads_up(self):
        positions=positions_from_button('top_left',NINE_ORDER,NINE_ORDER)
        self.assertEqual(len(positions),9)
        self.assertEqual(positions['top_left'],'BTN')
        self.assertEqual(positions['top_right'],'SB')
        self.assertEqual(positions['upper_right'],'BB')
        self.assertEqual(positions['upper_left'],'CO')
        self.assertEqual(positions_from_button('hero',['hero','top_left'],NINE_ORDER),{'hero':'BTN/SB','top_left':'BB'})

    def test_board_and_hero_are_assigned_in_new_geometry(self):
        cards=[]
        for code,box in [('AH',[696,397,729,463]),('KS',[806,397,839,463]),('KD',[863,723,895,786]),('JS',[967,723,999,786])]:
            cards.append(dict(card=code,bbox=box,accepted=True))
        r=arrange_table(dict(cards=cards,profile=NINE),(1198,1918,3))
        self.assertEqual([c['card'] for c in r['board']],['AH','KS',None,None,None])
        self.assertEqual([c['card'] for c in r['player_hand']],['KD','JS'])

    def test_detected_client_keeps_dark_wallpaper_and_vertical_offsets(self):
        image=np.zeros((1101,1762,3),np.uint8)
        header=nine_header();h,w=header.shape
        image[31:31+h,170:170+w]=cv2.cvtColor(header,cv2.COLOR_GRAY2BGR)
        aligner=CaptureAligner();game,viewport=aligner.align(image)
        self.assertEqual(aligner.profile,NINE)
        self.assertEqual(viewport,(0,0,1762,1101))
        self.assertEqual(game.shape,image.shape)

    def test_presence_counts_only_both_visible_personal_cards(self):
        image=np.full((1101,1762,3),(30,120,30),np.uint8)
        for x,y,r,b in NINE_HERO:image[y:b,x:r]=255
        self.assertEqual([s['present'] for s in player_card_presence(image,NINE)],[True,True])

    def test_eight_opponents_confirm_and_equity_accepts_eight(self):
        tracker=OpponentTracker()
        seats=[dict(seat=s,present=True) for s in NINE_BACKS]
        for i in range(5):result=tracker.update(seats,i*.1,[dict(detected=True)]*2)
        self.assertEqual(result['count'],8)
        self.assertEqual(result['max_opponents'],8)
        self.assertEqual(result['players_with_cards'],9)
        from test_poker_equity import frame
        data=frame(opponents=8);data['table_profile']=NINE
        self.assertEqual(OCRGameState().update(data,'nine')['max_opponents'],8)
        data['table_profile']='pokerstars'
        with self.assertRaises(ValueError):OCRGameState().update(data,'six')

    def test_ocr_mosaic_supports_nine_names_and_stacks_without_overlapping_cells(self):
        frame=np.full((1198,1918,3),(30,120,30),np.uint8)
        mosaic,placements=ocr_mosaic(frame,NINE)
        self.assertEqual(len([p for p in placements if p['key'].startswith('seat:')]),9)
        self.assertEqual(len([p for p in placements if p['key'].startswith('stack:')]),9)
        self.assertTrue(all(p['width']<=750 and p['height']<=350 for p in placements))

    def test_digit_reader_rejects_blank_card_backs_and_labels(self):
        reader=ChipNumberReader()
        self.assertEqual(len(reader.templates),10)
        self.assertIsNone(reader.read(np.zeros((45,200,3),np.uint8)))
        crop=np.zeros((45,200,3),np.uint8)
        cv2.putText(crop,'All-in',(2,30),cv2.FONT_HERSHEY_SIMPLEX,.8,(255,255,255),2)
        self.assertIsNone(reader.read(crop))

    def test_detector_loads_nine_weights_lazily_without_replacing_six(self):
        from learned_detector import TableCardDetector
        with patch('learned_detector.LearnedCardDetector') as factory:
            old=Mock();nine=Mock();nine.detect.return_value=dict(cards=[])
            factory.side_effect=[old,nine]
            detector=TableCardDetector();self.assertEqual(factory.call_count,1)
            detector.profile=NINE
            self.assertEqual(detector.detect(None)['table_profile'],NINE)
            detector.detect(None);self.assertEqual(factory.call_count,2)
            self.assertIs(detector.models['pokerstars'],old)


if __name__=='__main__':unittest.main()

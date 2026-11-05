import copy
import threading
import time
import unittest
from unittest.mock import Mock

from card_detector import cv2, np
from table_observer import (ActionTemplates, CLOCKWISE, NAME_REGIONS, ROOT,
                            TableObservationService, TableStateTracker, TableVisualReader,
                            group_ocr, ocr_mosaic, parse_action, parse_amount,
                            positions_from_button)


def observation(action=None, wager=None):
    return dict(button=dict(seat='top',score=.99),
                seats=[dict(seat=key,name='Player'+key if not action or key!='hero' else None,
                            action=action if key=='hero' else None,
                            stack=dict(value=50,unit='BB'),wager=wager if key=='hero' else None,
                            empty=False,sit_out=False,raw_text=[],raw_wager=[])
                       for key in CLOCKWISE],pot=dict(value=3,unit='BB'),contribution=None,
                available_actions=[dict(action='fold',text='Fold')],ocr_language='en-GB')


def context(**changes):
    return dict(dict(hand_id=1,street='preflop',active=True,
                     dealt_seats=list(CLOCKWISE),capture_session='one',viewport=(0,0,1762,984)),**changes)


class TableObserverTests(unittest.TestCase):
    def test_amount_units_decimal_separators_and_common_ocr_suffixes(self):
        for raw,value in [('0.5BB',.5),('12,5 BB',12.5),('47.58B',47.5),('1288',12),('IBB',1),('O.5BB',.5),('IOBB',10),('3EUR',3)]:
            self.assertEqual(parse_amount(raw)['value'],value,raw)
        for text in ('12','Vedi 12BB','€0.02','Player123','-5BB','NaNBB','1.2.3BB'):
            self.assertIsNone(parse_amount(text),text)

    def test_action_vocabulary_and_names_not_actions(self):
        for text,action in [('Vedi','call'),('Rilancia a','raise'),('Puntata','bet'),('All-in','all_in'),('Check','check'),('Fold','fold')]:
            self.assertEqual(parse_action(text),action)
        self.assertIsNone(parse_action('CheckMaster42'))

    def test_all_positions_and_heads_up_are_based_on_deal_roster(self):
        positions = positions_from_button('top',list(CLOCKWISE))
        self.assertEqual([positions[s] for s in CLOCKWISE],['BTN','SB','BB','UTG','HJ','CO'])
        self.assertEqual(positions_from_button('hero',['hero','upper_left']),{'hero':'BTN/SB','upper_left':'BB'})
        self.assertEqual(positions_from_button('top',['hero','upper_left']),{})
        self.assertEqual(positions_from_button('top',['top']),{})

    def test_offered_buttons_never_become_performed_events_and_fields_need_confirmation(self):
        tracker = TableStateTracker()
        first = tracker.update(observation(),context(),0)
        self.assertIsNone(first['pot'])
        self.assertFalse(first['positions_complete'])
        second = tracker.update(observation(),context(),.2)
        self.assertEqual(second['events'],[])
        self.assertEqual(second['button'],'top')
        self.assertEqual(second['pot']['value'],3)
        self.assertTrue(second['positions_complete'])

    def test_white_username_check_is_not_a_yellow_action_label(self):
        frame = np.full((984,1762,3),(30,65,30),np.uint8)
        cv2.putText(frame,'Check',(740,190),cv2.FONT_HERSHEY_SIMPLEX,1,(255,255,255),2)
        ocr = Mock()
        ocr.recognize.return_value = dict(lines=[dict(words=[dict(text='Check',x=30,y=30,width=100,height=30)])])
        result = TableVisualReader(ocr).read(frame)
        top = next(row for row in result['seats'] if row['seat']=='top')
        self.assertEqual(top['name'],'Check')
        self.assertIsNone(top['action'])
        self.assertFalse(top['yellow_action_label'])

    def test_ambiguous_yellow_label_cannot_rearm_an_existing_action(self):
        tracker = TableStateTracker()
        for t in (0,.2):
            tracker.update(observation('call'),context(),t)
        ambiguous = observation()
        next(row for row in ambiguous['seats'] if row['seat']=='hero')['yellow_action_label'] = True
        for t in (.4,.6):
            tracker.update(ambiguous,context(),t)
        for t in (.8,1):
            result = tracker.update(observation('call'),context(),t)
        self.assertEqual(len(result['events']),1)

    def test_completing_event_amount_does_not_mutate_previous_snapshot(self):
        tracker = TableStateTracker()
        for t in (0,.2):
            before = tracker.update(observation('raise'),context(),t)
        for t in (.4,.6):
            after = tracker.update(observation('raise',dict(value=8,unit='BB')),context(),t)
        self.assertIsNone(before['events'][0]['amount'])
        self.assertEqual(after['events'][0]['amount']['value'],8)
        after['events'][0]['amount']['value'] = 999
        self.assertEqual(tracker.events[0]['amount']['value'],8)

    def test_fold_does_not_move_blinds_and_a_new_button_invalidates_old_roster(self):
        tracker = TableStateTracker()
        for t in (0,.2):
            tracker.update(observation(),context(),t)
        # Participants who fold remain in the original positional ordering.
        result = tracker.update(observation('fold'),context(dealt_seats=['top','hero']),.4)
        self.assertEqual(next(r for r in result['seats'] if r['seat']=='hero')['position'],'UTG')
        moved = observation()
        moved['button']['seat'] = 'upper_right'
        for t in (.6,.8):
            result = tracker.update(moved,context(active=False),t)
        self.assertFalse(result['positions_complete'])
        self.assertTrue(all(row['position'] in (None,'BTN') for row in result['seats']))

    def test_actions_are_deduplicated_and_street_change_does_not_repeat_old_label(self):
        tracker = TableStateTracker()
        sample = observation('check',dict(value=1,unit='BB'))
        for t in (0,.2,.4):
            result = tracker.update(sample,context(),t)
        self.assertEqual(len(result['events']),1)
        self.assertIsNone(result['events'][0]['amount'])
        self.assertEqual(result['events'][0]['amount_kind'],'not_applicable')
        for t in (.6,.8):
            result = tracker.update(sample,context(street='flop'),t)
        self.assertEqual(len(result['events']),1)
        # A normal name plate confirmed twice re-arms subsequent actions.
        for t in (1,1.2):
            tracker.update(observation(),context(street='flop'),t)
        for t in (1.4,1.6):
            result = tracker.update(observation('call',dict(value=5,unit='BB')),context(street='flop'),t)
        self.assertEqual(len(result['events']),2)
        self.assertEqual(result['events'][-1]['amount_kind'],'street_total')
        self.assertEqual(result['events'][-1]['amount']['value'],5)

    def test_missing_amount_is_not_zero_and_later_amount_does_not_duplicate_event(self):
        tracker = TableStateTracker()
        for t in (0,.2):
            result = tracker.update(observation('raise'),context(),t)
        self.assertIsNone(result['events'][0]['amount'])
        for t in (.4,.6):
            result = tracker.update(observation('raise',dict(value=8,unit='BB')),context(),t)
        self.assertEqual(len(result['events']),1)
        self.assertEqual(result['events'][0]['amount']['value'],8)
        for t in (.8,1):
            result = tracker.update(observation(),context(hand_id=2),t)
        self.assertEqual(result['events'],[])

    def test_incomplete_roster_does_not_assert_blinds_or_move_positions_after_folds(self):
        tracker = TableStateTracker()
        ctx = context(dealt_seats=['top','hero'])
        for t in (0,.2):
            result = tracker.update(observation(),ctx,t)
        hero = next(s for s in result['seats'] if s['seat']=='hero')
        self.assertIsNone(hero['position'])
        self.assertEqual(hero['position_estimate'],'BB')
        self.assertFalse(result['positions_complete'])

    def test_street_pots_preserve_first_amount_and_track_collected_separately(self):
        tracker = TableStateTracker()
        sample = observation()
        sample['pot'] = dict(value=10,unit='BB')
        sample['collected_pot'] = dict(value=8,unit='BB')
        for t in (0,.2):
            result = tracker.update(sample,context(street='flop'),t)
        first = result
        self.assertEqual(result['street_pots']['flop']['first_total']['value'],10)
        self.assertEqual(result['street_pots']['flop']['first_collected']['value'],8)
        sample['pot'] = dict(value=14,unit='BB')
        for t in (.4,.6):
            result = tracker.update(sample,context(street='flop'),t)
        self.assertEqual(result['street_pots']['flop']['first_total']['value'],10)
        self.assertEqual(result['street_pots']['flop']['last_total']['value'],14)
        self.assertEqual(first['street_pots']['flop']['last_total']['value'],10)
        for street,amount,t in [('turn',20,1),('river',35,2)]:
            sample['pot'] = dict(value=amount,unit='BB')
            sample['collected_pot'] = dict(value=amount,unit='BB')
            tracker.update(sample,context(street=street),t)
            result = tracker.update(sample,context(street=street),t+.2)
            self.assertEqual(result['street_pots'][street]['first_total']['value'],amount)
        self.assertEqual(set(result['street_pots']),{'flop','turn','river'})
        result = tracker.update(observation(),context(hand_id=2),2.6)
        self.assertEqual(result['street_pots'],{})

    def test_unknown_or_skipped_street_does_not_invent_pot_snapshots(self):
        tracker = TableStateTracker()
        sample = observation()
        sample['pot'] = None
        for t in (0,.2):
            result = tracker.update(sample,context(street='river'),t)
        self.assertIsNone(result['street_pots']['river']['first_total'])
        self.assertNotIn('flop',result['street_pots'])
        self.assertNotIn('turn',result['street_pots'])
        self.assertIsNone(result['collected_pot'])
        for t in (.4,.6):
            result = tracker.update(observation(),context(street='flop'),t)
        self.assertNotIn('flop',result['street_pots'])

    def test_real_action_templates_are_distinguishable(self):
        classifier = ActionTemplates()
        for label,_,_ in classifier.references:
            glyph = cv2.imread(str(ROOT/f'assets/table-observer/actions/{label}.png'),cv2.IMREAD_GRAYSCALE)
            self.assertEqual(classifier.classify(glyph)['action'],label)
        self.assertIsNone(classifier.classify(None))

    def test_dealer_template_is_assigned_to_each_seat(self):
        from table_observer import SEAT_CENTRES
        reader = TableVisualReader(Mock())
        template = cv2.imread(str(ROOT/'assets/table-observer/dealer-button.png'))
        for seat,(x,y) in SEAT_CENTRES.items():
            frame = np.full((984,1762,3),(30,65,30),np.uint8)
            frame[y:y+39,x:x+40] = template
            self.assertEqual(reader.dealer_button(frame)['seat'],seat)

    def test_ocr_grouping_does_not_merge_text_from_separate_regions(self):
        placements=[dict(key='seat:hero',x=0,y=0,width=100,height=100),dict(key='option:0',x=200,y=0,width=100,height=100)]
        words=[dict(text='Player',x=10,y=10,width=40,height=15),dict(text='Fold',x=210,y=10,width=40,height=15)]
        groups=group_ocr(dict(lines=[dict(words=words)]),placements)
        self.assertEqual(groups,{'seat:hero':['Player'],'option:0':['Fold']})

    def test_background_service_discards_previous_capture_result(self):
        entered,release = threading.Event(),threading.Event()
        reader = Mock(spec=['read'])
        def read(frame):
            entered.set()
            release.wait(timeout=1)
            return observation()
        reader.read.side_effect=read
        service=TableObservationService(lambda:reader,interval=0)
        try:
            frame=np.zeros((30,30,3),np.uint8)
            service.submit(frame,context())
            self.assertTrue(entered.wait(timeout=1))
            service.submit(frame,context(capture_session='two',hand_id=2))
            release.set()
            deadline=time.monotonic()+2
            while time.monotonic()<deadline:
                with service.lock:
                    result=dict(service.latest)
                if result.get('status')=='ready':
                    break
                threading.Event().wait(.01)
            self.assertEqual(result['hand_id'],2)
        finally:
            release.set()
            service.close()

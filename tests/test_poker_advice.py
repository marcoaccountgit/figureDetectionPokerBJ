import copy
import unittest

from poker_advice import analyze_decision
from table_observer import TableStateTracker, parse_call_amount
from test_table_observer import observation, context


def equity(value=.35, interval=(.34,.36), street='river'):
    metric=dict(value=value,ci95=list(interval),standard_error=.01)
    return dict(status='ready',complete=True,street=street,opponents_count=1,
                metrics=dict(equity=metric,win=copy.deepcopy(metric),tie=dict(value=0),lose=dict(value=1-value)))


def table(cost=50,pot=150):
    return dict(status='ready',hand_id=1,street='river',age_ms=0,
                pot=dict(value=pot,unit='BB'),collected_pot=dict(value=100,unit='BB'),
                available_actions_confirmed=[dict(action='call',amount=dict(value=cost,unit='BB'))],
                seats=[dict(seat='hero',stack=dict(value=200,unit='BB'))])


class AdviceTests(unittest.TestCase):
    def test_cost_can_be_on_same_line_as_call_button(self):
        self.assertEqual(parse_call_amount('Vedi 12 BB')['value'],12)
        self.assertEqual(parse_call_amount('Call 0,50 EUR')['value'],.5)
        for invalid in ('Vedi 12','Rilancia a 12 BB','Contributo 12 BB','Call NaN BB'):
            self.assertIsNone(parse_call_amount(invalid))

    def test_conditional_call_formula_and_no_double_counted_pot(self):
        r=analyze_decision(equity(),table(),1)
        self.assertEqual(r['status'],'conditional')
        self.assertEqual(r['signal'],'call_model')
        self.assertEqual(r['pot_after_call'],200)
        self.assertEqual(r['required_equity'],.25)
        self.assertEqual(r['expected_value'],20)
        self.assertAlmostEqual(r['margin'],.10)
        self.assertEqual(r['expected_value_ci95'],[18,22])

    def test_fold_and_uncertain(self):
        self.assertEqual(analyze_decision(equity(.2,(.19,.21)),table(),1)['signal'],'fold_model')
        self.assertEqual(analyze_decision(equity(.25,(.24,.26)),table(),1)['signal'],'uncertain')

    def test_no_stale_or_mismatched_result(self):
        for changes in (dict(status='stale'),dict(hand_id=2),dict(street='flop'),dict(age_ms=3000)):
            data=table();data.update(changes)
            self.assertEqual(analyze_decision(equity(),data,1)['status'],'waiting')
        self.assertEqual(analyze_decision(dict(status='waiting'),table(),1)['status'],'waiting')

    def test_missing_invalid_mixed_units_and_side_pots(self):
        cases=[]
        for cost in (None,0,-1,float('nan'),float('inf')):
            t=table();t['available_actions_confirmed'][0]['amount']['value']=cost;cases.append(t)
        t=table();t['pot']=None;cases.append(t)
        t=table();t['pot']['unit']='EUR';cases.append(t)
        t=table();t['available_actions_confirmed']=[];cases.append(t)
        t=table();t['seats'][0]['stack']['value']=20;cases.append(t)
        t=table();t['side_pots']=[10];cases.append(t)
        for t in cases:
            self.assertEqual(analyze_decision(equity(),t,1)['status'],'waiting')

    def test_check_without_bet_recommendation(self):
        t=table();t['available_actions_confirmed']=[dict(action='check')]
        r=analyze_decision(equity(),t,1)
        self.assertEqual(r['status'],'free_check')
        self.assertNotIn('expected_value',r)

    def test_multiway_ties_use_equity_not_win(self):
        e=equity(.4,(.39,.41),street='flop');e['opponents_count']=3
        e['metrics']['win']['value']=.1
        e['metrics']['tie']['value']=.6
        t=table();t['street']='flop'
        r=analyze_decision(e,t,1)
        self.assertEqual(r['signal'],'call_model')
        self.assertEqual(r['equity'],.4)
        self.assertTrue(any('Più avversari' in line for line in r['limits']))
        self.assertTrue(any('pagare adesso' in line for line in r['limits']))

    def test_buttons_need_temporal_confirmation_and_reset_on_change(self):
        tracker=TableStateTracker()
        data=observation()
        data['available_actions']=[dict(action='call',text='Vedi',amount=dict(value=1,unit='BB'))]
        self.assertEqual(tracker.update(data,context(),0)['available_actions_confirmed'],[])
        self.assertEqual(len(tracker.update(data,context(),.2)['available_actions_confirmed']),1)
        data=copy.deepcopy(data);data['available_actions'][0]['amount']['value']=2
        self.assertEqual(tracker.update(data,context(),.4)['available_actions_confirmed'],[])
        self.assertEqual(len(tracker.update(data,context(),.6)['available_actions_confirmed']),1)
        self.assertEqual(tracker.update(data,context(street='flop'),.8)['available_actions_confirmed'],[])
        self.assertEqual(tracker.update(data,context(hand_id=2),1)['available_actions_confirmed'],[])

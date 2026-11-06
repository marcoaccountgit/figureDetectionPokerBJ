import itertools
import random
import time
import unittest
from collections import Counter
from unittest.mock import patch

from poker_equity import calculate_equity, evaluate, normalize_card, validate
from equity_service import EquityService, OCRGameState


def cards(text):
    return tuple(map(normalize_card, text.split()))


def reference_five(hand):
    """Independent five-card classifier for the 21-subset regression oracle."""
    ranks = sorted((c//4+2 for c in hand), reverse=True)
    groups = sorted(((ranks.count(r), r) for r in set(ranks)), reverse=True)
    flush = len({c % 4 for c in hand}) == 1
    unique = sorted(set(ranks))
    straight = (max(ranks) if len(unique) == 5 and max(ranks)-min(ranks) == 4
                else 5 if unique == [2,3,4,5,14] else 0)
    if straight and flush: return (8,straight)
    shape = [g[0] for g in groups]
    ordered = tuple(g[1] for g in groups)
    if shape == [4,1]: return (7,*ordered)
    if shape == [3,2]: return (6,*ordered)
    if flush: return (5,*ranks)
    if straight: return (4,straight)
    return ({(3,1,1):3,(2,2,1):2,(2,1,1,1):1}.get(tuple(shape),0),*ordered)


def frame(board=(), hero=('AS','KH'), count=1, active=True, opponents=2):
    return dict(hand_cycle=dict(count=count,active=active),
                player_hand=[dict(card=c,accepted=True,detected=True) for c in hero],
                board=[dict(card=board[i] if i<len(board) else None,
                            accepted=i<len(board),detected=i<len(board)) for i in range(5)],
                opponents=dict(count=opponents,pending=False))


class EvaluatorTests(unittest.TestCase):
    def test_categories(self):
        examples = ['As Kd 9c 7h 3s','As Ad Kc 7h 3s','As Ad Kc Kh 3s',
                    'As Ad Ac Kh 3s','As 2d 3c 4h 5s','As Js 9s 7s 3s',
                    'As Ad Ac Kh Ks','As Ad Ac Ah Ks','As Ks Qs Js Ts']
        for category, hand in enumerate(examples):
            self.assertEqual(evaluate(cards(hand))[0],category)

    def test_kickers_wheel_and_two_trips(self):
        self.assertGreater(evaluate(cards('As Ad Kc 7h 3s')),evaluate(cards('Ah Ac Qc 7s 3h')))
        self.assertLess(evaluate(cards('As 2d 3c 4h 5s')),evaluate(cards('2s 3d 4c 5h 6s')))
        self.assertEqual(evaluate(cards('As Ad Ac Kh Ks Kd 2h')),(6,14,13))
        self.assertEqual(evaluate(cards('As 2s 3s 4s 5s Kd Qh')),(8,5))

    def test_independent_five_card_oracle(self):
        rng=random.Random(822)
        for _ in range(400):
            hand=rng.sample(range(52),7)
            self.assertEqual(evaluate(hand),max(reference_five(c) for c in itertools.combinations(hand,5)))

    def test_normalization_and_duplicates(self):
        self.assertEqual(normalize_card('10H'),normalize_card('Th'))
        self.assertEqual(normalize_card(' A♥ '),normalize_card('ah'))
        for value in ('',None,'1S','ZZ'):
            with self.assertRaises(ValueError): normalize_card(value)
        with self.assertRaises(ValueError): validate(['AS','as'],[],1)
        with self.assertRaises(ValueError): validate(['AS','KH'],['AS','3H','4H'],1)
        for board in (['2H'],['2H','3H']):
            with self.assertRaises(ValueError): validate(['AS','KH'],board,1)
        for count in (0,10,True,None):
            with self.assertRaises(ValueError): validate(['AS','KH'],[],count)


class EquityTests(unittest.TestCase):
    def test_shared_royal_and_multiway_shares(self):
        for opponents in (1,2,3,5,9):
            r=calculate_equity(['2c','3d'],['As','Ks','Qs','Js','Ts'],opponents,simulations=200,random_seed=1)
            self.assertEqual(r['metrics']['tie']['value'],1)
            self.assertAlmostEqual(r['metrics']['equity']['value'],1/(opponents+1))
            self.assertEqual(r['metrics']['current_strength']['value'],0)
            self.assertEqual(r['metrics']['category_improvement']['value'],0)

    def test_exact_vs_monte_carlo(self):
        args=(['As','Ad'],['Ac','Kh','Ks','2d','3c'],1)
        exact=calculate_equity(*args,simulations=100,random_seed=7)
        self.assertEqual(exact['method'],'exact')
        self.assertEqual(exact['simulations'],990)
        self.assertEqual(exact['metrics']['equity']['standard_error'],0)
        mc=calculate_equity(*args,simulations=6000,random_seed=7,exact_threshold=0)
        self.assertLess(abs(exact['metrics']['equity']['value']-mc['metrics']['equity']['value']),.025)

    def test_probabilities_seed_and_preflop(self):
        for opponents in (1,2,4):
            r=calculate_equity(['As','Kh'],[],opponents,simulations=200,random_seed=55)
            self.assertIsNone(r['metrics']['current_strength'])
            self.assertIsNone(r['metrics']['category_improvement'])
            self.assertAlmostEqual(sum(r['metrics'][k]['value'] for k in ('win','tie','lose')),1)
            self.assertAlmostEqual(sum(v['value'] for v in r['categories'].values()),1)
            repeat=calculate_equity(['As','Kh'],[],opponents,simulations=200,random_seed=55)
            self.assertEqual(r['metrics'],repeat['metrics'])

    def test_joint_multiway_and_confidence(self):
        head=calculate_equity(['As','Ad'],[],1,simulations=3000,random_seed=5)
        multi=calculate_equity(['As','Ad'],[],4,simulations=3000,random_seed=5)
        self.assertGreater(head['metrics']['equity']['value'],multi['metrics']['equity']['value'])
        self.assertTrue(.80<head['metrics']['equity']['value']<.90)
        self.assertTrue(.48<multi['metrics']['equity']['value']<.62)
        r=calculate_equity(['As','Kh'],['2s','3d','4c'],3,simulations=400,random_seed=5)
        self.assertAlmostEqual(sum(r['metrics'][k]['value'] for k in ('current_strength','currently_behind','current_tie')),1)
        self.assertLessEqual(r['metrics']['category_improvement']['value']+r['metrics']['same_category_value_improvement']['value'],1)
        eq=r['metrics']['equity']
        self.assertLessEqual(eq['ci95'][0],eq['value'])
        self.assertGreater(eq['standard_error'],0)

    def test_cancellation_and_progress(self):
        self.assertIsNone(calculate_equity(['As','Kh'],[],2,cancelled=lambda:True))
        results=[]
        final=calculate_equity(['As','Kh'],[],1,simulations=5001,random_seed=7,progress=results.append)
        self.assertEqual(results[0]['simulations'],5000)
        self.assertFalse(results[0]['complete'])
        self.assertTrue(final['complete'])

    def test_sampling_uses_distinct_joint_cards(self):
        observed=[]
        real_sample=random.Random.sample
        def inspect(rng,population,k):
            sample=real_sample(rng,population,k)
            self.assertEqual(len(set(sample)),k)
            self.assertFalse(set(sample) & set(cards('As Kh 2s 3d 4c')))
            observed.append(k)
            return sample
        with patch.object(random.Random,'sample',inspect):
            calculate_equity(['As','Kh'],['2s','3d','4c'],5,simulations=100,random_seed=42)
        self.assertEqual(observed,[12]*100)

    def test_equity_variance_uses_fractional_shares(self):
        from poker_equity import uncertainty
        # Samples [1, 1/3, 0], not Bernoulli observations.
        result=uncertainty(4/3,10/9,3)
        self.assertAlmostEqual(result['standard_error'],(7/81)**.5)

    def test_kicker_improvement_is_separate_from_category(self):
        r=calculate_equity(['As','Ad'],['2s','3d','7c'],1,simulations=1000,random_seed=51)
        self.assertGreater(r['metrics']['kicker_improvement']['value'],0)
        self.assertLessEqual(r['metrics']['kicker_improvement']['value'],r['metrics']['same_category_value_improvement']['value'])


class OCRIntegrationTests(unittest.TestCase):
    def test_advertised_table_capacity_reaches_equity_input(self):
        for capacity in (5,6,8,9,10):
            data=frame(opponents=capacity-1)
            data['opponents']['max_opponents']=capacity-1
            result=OCRGameState().update(data,'variable-capacity')
            self.assertEqual(result['opponents_count'],capacity-1)
            self.assertEqual(result['max_opponents'],capacity-1)
        data['opponents']['max_opponents']=10
        with self.assertRaises(ValueError):OCRGameState().update(data,'invalid-capacity')

    def test_streets_gaps_and_new_hand(self):
        adapter=OCRGameState()
        for board in ((),('2S','3D','4C'),('2S','3D','4C','5H'),('2S','3D','4C','5H','6H')):
            self.assertEqual(len(adapter.update(frame(board),'one')['community_cards']),len(board))
        with self.assertRaises(ValueError): adapter.update(frame(),'one')
        with self.assertRaises(ValueError): adapter.update(frame(hero=('AS',)),'one')
        self.assertEqual(adapter.update(frame(count=2),'one')['community_cards'],[])
        pending=frame();pending['board'][0]=dict(detected=True,accepted=False,card=None)
        with self.assertRaises(ValueError): adapter.update(pending,'two')
        hole=frame(('2S','3D','4C'));hole['board'][1]=dict(detected=False,accepted=False,card=None)
        with self.assertRaises(ValueError): adapter.update(hole,'three')

    def test_manual_opponents_and_corrections(self):
        adapter=OCRGameState();data=frame();data['opponents']=dict(count=None,pending=True)
        with self.assertRaises(ValueError): adapter.update(data,'one')
        self.assertEqual(adapter.update(data,'one',3)['opponents_count'],3)
        self.assertEqual(adapter.update(frame(hero=('AD','KH')),'one',1)['hero_cards'],['Ad','Kh'])

    def test_partial_and_invalid_board_do_not_reset_or_poison_street(self):
        adapter=OCRGameState()
        partial=frame(('2s',))
        with self.assertRaises(ValueError): adapter.update(partial,'one')
        with self.assertRaises(ValueError): adapter.update(frame(),'one')
        duplicate=frame(('2s','3d','4c','5h','2s'))
        with self.assertRaises(ValueError): adapter.update(duplicate,'one')
        self.assertEqual(len(adapter.update(frame(('2s','3d','4c')),'one')['community_cards']),3)

    def test_old_queued_response_and_identical_frames(self):
        from queue import Queue
        service=EquityService(debounce=100)
        original=service.responses
        service.responses=Queue()
        try:
            data=frame(('2s','3d','4c'))
            service.submit(data,'one')
            old=service.generation.value
            service.submit(data,'one')
            self.assertEqual(service.generation.value,old)
            data['opponents']['count']=3
            service.submit(data,'one')
            service.responses.put((old,dict(status='ready',complete=True)))
            self.assertEqual(service.submit(data,'one')['status'],'debouncing')
            self.assertIsNone(service.result)
            data['hand_cycle']['count']=2
            service.submit(data,'one')
            self.assertGreater(service.generation.value,old+1)
        finally:
            service.responses=original
            service.close()

    def test_preflop_starts_from_confirmed_hole_cards_before_cycle_confirmation(self):
        service=EquityService(debounce=100)
        data=frame(count=0,active=False)
        try:
            first=service.submit(data,'preflop',random_seed=42)
            self.assertEqual(first['status'],'calculating')
            deadline=time.monotonic()+15
            while time.monotonic()<deadline:
                result=service.submit(data,'preflop',random_seed=42)
                if result.get('complete'):
                    break
                time.sleep(.03)
            else:
                self.fail('Preflop worker timeout')
            self.assertEqual(result['street'],'preflop')
            self.assertEqual(result['community_cards'],[])
            self.assertGreater(result['metrics']['equity']['value'],0)
            self.assertIsNone(result['current_category'])
            self.assertIsNone(result['metrics']['current_strength'])
        finally:
            service.close()

    def test_ended_hand_cannot_restart_until_new_physical_cycle(self):
        adapter=OCRGameState()
        data=frame(active=False)
        self.assertEqual(adapter.update(data,'one')['community_cards'],[])
        data['hand_cycle']['ended']=True
        with self.assertRaises(ValueError): adapter.update(data,'one')
        data['hand_cycle']['ended']=False
        with self.assertRaises(ValueError): adapter.update(data,'one')
        data['hand_cycle']['count']=2
        self.assertEqual(adapter.update(data,'one')['community_cards'],[])

    def test_worker_stale_cache_and_incomplete(self):
        service=EquityService(debounce=0)
        try:
            data=frame(('As','Ks','Qs','Js','Ts'),hero=('2c','3d'),opponents=1)
            def ready(value):
                deadline=time.monotonic()+15
                while time.monotonic()<deadline:
                    response=service.submit(value,'one',random_seed=12)
                    if response.get('complete'): return response
                    time.sleep(.03)
                self.fail('Worker timeout')
            first=ready(data)
            self.assertEqual(first['metrics']['equity']['value'],.5)
            self.assertTrue(service.submit(data,'one',random_seed=12)['cached'])
            data['opponents']['count']=2
            pending=service.submit(data,'one',random_seed=12)
            self.assertNotEqual(pending.get('status'),'ready')
            second=ready(data)
            self.assertAlmostEqual(second['metrics']['equity']['value'],1/3)
            data['player_hand'][0]['accepted']=False
            self.assertEqual(service.submit(data,'one')['status'],'waiting')
            self.assertIsNone(service.result)
        finally:
            service.close()


if __name__=='__main__':
    unittest.main()

import copy
from itertools import combinations
import time
import unittest
from unittest.mock import patch

from bet_equity_model import fixed_bet_model
from equity_service import EquityService
from native_equity import load_native
from poker_equity import calculate_equity, evaluate, normalize_card
from test_poker_equity import frame


def observed():
    result = frame(('2s', '7d', 'Jh'), opponents=2)
    result['opponents']['seats'] = [dict(seat=k, label=k, confirmed=True, in_hand=True)
                                   for k in ('top', 'lower_left')]
    result['opponents']['pending'] = False
    result['table_observation'] = dict(status='ready', hand_id=1, street='flop', age_ms=0,
                                     pot=dict(value=200, unit='CHIPS'),
                                     seats=[dict(seat='top', wager=dict(value=20, unit='CHIPS')),
                                            dict(seat='lower_left', wager=dict(value=80, unit='CHIPS'))])
    return result


class FixedBetModelTests(unittest.TestCase):
    def test_changed_bet_reuses_uniform_equity_in_the_worker(self):
        from queue import Queue
        from types import SimpleNamespace
        from equity_service import _worker
        requests, responses = Queue(), Queue(maxsize=8)
        baseline = dict(status='ready', complete=True, metrics={'equity': {'value': .5}})
        scenario = dict(status='ready', complete=True, metrics={'equity': {'value': .3}})
        requests.put((1, dict(_uniform_result=baseline, bet_strengths=(3,))))
        requests.put(None)
        with patch('equity_service.calculate_equity', return_value=scenario) as calculate:
            _worker(requests, responses, SimpleNamespace(value=1))
            calculate.assert_called_once()
            self.assertEqual(calculate.call_args.kwargs['opponent_strengths'], (3,))
        output = [responses.get_nowait()[1] for _ in range(responses.qsize())][-1]
        self.assertEqual(output['metrics'], baseline['metrics'])
        self.assertEqual(output['bet_scenario']['metrics'], scenario['metrics'])

    def test_invalid_sampling_levels_are_rejected_before_native_call(self):
        for levels in ([], [4], [True], [.5], '3'):
            with self.assertRaises(ValueError):
                calculate_equity(['As', 'Kh'], [], 1, opponent_strengths=levels)

    def test_buckets_use_current_total_including_wagers(self):
        result = fixed_bet_model(observed(), 2)
        self.assertEqual(result['status'], 'ready')
        self.assertEqual(result['strengths'], [3, 1])
        self.assertEqual([s['strong_weight'] for s in result['seats']], [10, 3])
        self.assertEqual([s['ratio'] for s in result['seats']], [.4, .1])

    def test_names_history_and_offered_buttons_cannot_change_weights(self):
        source = observed()
        expected = fixed_bet_model(source, 2)
        other = copy.deepcopy(source)
        other['table_observation']['events'] = [dict(action='raise', amount=999999)]
        other['table_observation']['available_actions_confirmed'] = [dict(action='raise')]
        for row in other['table_observation']['seats']:
            row.update(name='different player', stack=dict(value=1000000, unit='CHIPS'))
        self.assertEqual(fixed_bet_model(other, 2), expected)

    def test_stale_mismatched_uncertain_and_side_pot_inputs_are_unavailable(self):
        for change in (dict(age_ms=2001), dict(hand_id=2), dict(street='turn'),
                       dict(side_pots=[1]), dict(pot=None), dict(status='pending'),
                       dict(pot=dict(value=10, unit='CHIPS'))):
            source = observed()
            source['table_observation'].update(change)
            self.assertEqual(fixed_bet_model(source, 2)['status'], 'waiting')
        source = observed()
        source['opponents']['pending'] = True
        self.assertEqual(fixed_bet_model(source, 2)['status'], 'waiting')
        self.assertEqual(fixed_bet_model(observed(), 3, manual_opponents=3)['status'], 'waiting')
        source = observed()
        source['table_observation']['seats'][0]['wager']['unit'] = 'BB'
        self.assertEqual(fixed_bet_model(source, 2)['status'], 'waiting')

    def test_preflop_blinds_do_not_select_stronger_hands(self):
        source = observed()
        source['board'] = frame()['board']
        source['table_observation']['street'] = 'preflop'
        self.assertEqual(fixed_bet_model(source, 2)['strengths'], [0, 0])
        source['table_observation']['seats'][0]['action'] = 'raise'
        self.assertEqual(fixed_bet_model(source, 2)['strengths'], [0, 1])

    def test_missing_amount_is_uniform_not_a_fabricated_bet(self):
        source = observed()
        source['table_observation']['seats'][0]['wager'] = None
        model = fixed_bet_model(source, 2)
        self.assertEqual(model['strengths'], [3, 0])
        self.assertIn('non confermato', model['seats'][1]['note'])


@unittest.skipUnless(load_native(), 'Rust library required')
class BetSamplingTests(unittest.TestCase):
    def test_uniform_levels_reproduce_native_uniform_samples(self):
        args = dict(hero_cards=['As', 'Kh'], community_cards=['2s', '7d', 'Jh'],
                    opponents_count=3, random_seed=42, exact_threshold=0)
        base = calculate_equity(**args)
        scenario = calculate_equity(**args, opponent_strengths=[0, 0, 0])
        self.assertEqual(base['metrics'], scenario['metrics'])
        self.assertEqual(scenario['opponent_model'], 'fixed_bets')

    def test_weighted_two_opponent_monte_carlo_matches_joint_exact_oracle(self):
        hero = tuple(map(normalize_card, ('As', 'Kh')))
        board = tuple(map(normalize_card, ('2s', '7d', 'Jh', 'Tc', '9c')))
        pairs = list(combinations([c for c in range(52) if c not in hero + board], 2))
        scores = [evaluate(p + board) for p in pairs]
        cutoff = sorted(scores)[len(scores) * 3 // 4]
        masks = [(1 << a) | (1 << b) for a, b in pairs]
        ours = evaluate(hero + board)
        weight_sum, share_sum = 0, 0.
        # Labelled opponents with different weights (0,3). Sequentially
        # resampling just the colliding second player would bias this result.
        for mask, score in zip(masks, scores):
            for other_mask, other_score in zip(masks, scores):
                if mask & other_mask:
                    continue
                weight = 10 if other_score >= cutoff else 1
                weight_sum += weight
                if ours >= max(score, other_score):
                    share_sum += weight / (1 + (score == ours) + (other_score == ours))
        result = calculate_equity(['As', 'Kh'], ['2s', '7d', 'Jh', 'Tc', '9c'], 2,
                                  simulations=50000, random_seed=123, opponent_strengths=[0, 3])
        metric = result['metrics']['equity']
        self.assertLess(abs(metric['value'] - share_sum / weight_sum), 4 * metric['standard_error'] + .001)

    def test_repeat_progress_and_cancel_even_during_rejections(self):
        args = dict(hero_cards=['As', 'Kh'], community_cards=['2s', '7d', 'Jh'],
                    opponents_count=8, simulations=5001, random_seed=8, opponent_strengths=[3] * 8)
        updates = []
        result = calculate_equity(**args, progress=updates.append)
        self.assertEqual([r['simulations'] for r in updates], [256, 1024, 5000])
        self.assertEqual(result['metrics'], calculate_equity(**args)['metrics'])
        self.assertIsNone(calculate_equity(**args, cancelled=lambda: True))

    def test_service_delivers_both_results_and_invalidates_changed_commitment(self):
        service = EquityService(debounce=0)
        data = observed()
        try:
            def ready():
                deadline = time.monotonic() + 15
                while time.monotonic() < deadline:
                    result = service.submit(data, 'bets', random_seed=42, bet_model=True)
                    if result.get('bet_scenario', {}).get('complete'):
                        return result
                    time.sleep(.02)
                self.fail('Bet scenario worker timeout')
            first = ready()
            self.assertEqual(len(service.uniform_cache), 1)
            self.assertEqual(first['opponent_model'], 'uniform')
            self.assertEqual(first['bet_scenario']['opponent_model'], 'fixed_bets')
            self.assertEqual(first['bet_model']['strengths'], [3, 1])
            version = service.generation.value
            data['table_observation']['seats'][0]['wager']['value'] = 75
            service.submit(data, 'bets', random_seed=42, bet_model=True)
            self.assertGreater(service.generation.value, version)
            second = ready()
            self.assertEqual(len(service.uniform_cache), 1)
            self.assertEqual(first['metrics'], second['metrics'])
            self.assertEqual(second['bet_model']['strengths'], [3, 3])
            self.assertTrue(service.submit(data, 'bets', random_seed=42, bet_model=True)['cached'])
            data['table_observation']['age_ms'] = 3000
            result = service.submit(data, 'bets', random_seed=42, bet_model=True)
            self.assertEqual(result['bet_scenario']['status'], 'waiting')
        finally:
            service.close()

    def test_scenario_failure_keeps_uniform_result(self):
        from queue import Queue
        from types import SimpleNamespace
        from equity_service import _worker
        requests, responses = Queue(), Queue(maxsize=8)
        requests.put((1, dict(bet_strengths=(3,))))
        requests.put(None)
        baseline = dict(status='ready', complete=True, metrics={})
        with patch('equity_service.calculate_equity', side_effect=[baseline, RuntimeError('Rust unavailable')]):
            _worker(requests, responses, SimpleNamespace(value=1))
        output = [responses.get_nowait()[1] for _ in range(responses.qsize())][-1]
        self.assertEqual(output['status'], 'ready')
        self.assertEqual(output['bet_scenario']['status'], 'error')

    def test_no_usable_bet_reuses_exact_baseline_instead_of_resampling(self):
        from queue import Queue
        from types import SimpleNamespace
        from equity_service import _worker
        requests, responses = Queue(), Queue(maxsize=8)
        requests.put((1, dict(bet_strengths=(0,))))
        requests.put(None)
        baseline = dict(status='ready', complete=True, method='exact', metrics={'equity': {'value': .5}})
        with patch('equity_service.calculate_equity', return_value=baseline) as calculate:
            _worker(requests, responses, SimpleNamespace(value=1))
            calculate.assert_called_once()
        output = responses.get_nowait()[1]
        self.assertEqual(output['metrics'], output['bet_scenario']['metrics'])
        self.assertEqual(output['bet_scenario']['method'], 'exact')


if __name__ == '__main__':
    unittest.main()

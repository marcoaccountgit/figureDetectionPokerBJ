"""Cross-language checks: exact rankings and every metric on identical deals."""
import ctypes as ct
import itertools
import random
import unittest
from unittest.mock import patch

from native_equity import METRICS, Totals, evaluate_many, load_native
from poker_equity import calculate_equity, evaluate, normalize_card
from equity_service import _worker


def packed(score):
    return (score[0] << 20) | sum(value << (16 - 4 * i) for i, value in enumerate(score[1:]))


@unittest.skipUnless(load_native(), 'Build the Rust library with python build_native_equity.py')
class NativeEquityTests(unittest.TestCase):
    def test_all_legal_rank_histograms_for_five_six_and_seven_cards(self):
        for width in (5, 6, 7):
            hands = []
            for ranks in itertools.combinations_with_replacement(range(13), width):
                if any(ranks.count(r) > 4 for r in set(ranks)):
                    continue
                # Rotate suits globally: duplicates stay distinct and no flush
                # can mask an incorrect nonflush-table entry.
                hands.append(tuple(r * 4 + i % 4 for i, r in enumerate(ranks)))
            actual = evaluate_many(hands)
            self.assertEqual(actual, [packed(evaluate(hand)) for hand in hands])

    def test_every_flush_mask_with_five_six_or_seven_ranks(self):
        for width in (5, 6, 7):
            hands = [tuple(r * 4 for r in ranks)
                     for ranks in itertools.combinations(range(13), width)]
            self.assertEqual(evaluate_many(hands), [packed(evaluate(hand)) for hand in hands])

    def test_random_hands_match_python_with_arbitrary_card_order(self):
        rng = random.Random(20261107)
        for width in (5, 6, 7):
            hands = [rng.sample(range(52), width) for _ in range(10000)]
            self.assertEqual(evaluate_many(hands), [packed(evaluate(hand)) for hand in hands])

    def test_all_metrics_match_python_on_identical_joint_deals(self):
        library = load_native()
        for board_text in ('', '2s 7d Jh', '2s 7d Jh Tc', '2s 7d Jh Tc 9c'):
            hero_text = ['As', 'Kh']
            hero = tuple(map(normalize_card, hero_text))
            board = tuple(map(normalize_card, board_text.split()))
            known = hero + board
            deck = tuple(c for c in range(52) if c not in known)
            for opponents in (1, 3, 8, 9):
                width = 5 - len(board) + opponents * 2
                rng = random.Random(42)
                samples = [rng.sample(deck, width) for _ in range(512)]
                data = (ct.c_uint8 * (len(samples) * width))(*(c for sample in samples for c in sample))
                known_buffer = (ct.c_uint8 * len(known))(*known)
                totals = Totals()
                code = library.poker_score_deals(known_buffer, len(known), opponents, data, len(samples), ct.byref(totals))
                self.assertEqual(code, 0)
                with patch('poker_equity.random.Random.sample', side_effect=samples):
                    reference = calculate_equity(hero_text, board_text.split(), opponents,
                                                 simulations=len(samples), exact_threshold=0, backend='python')
                for i, name in enumerate(METRICS):
                    metric = reference['metrics'][name]
                    if metric is not None:
                        self.assertAlmostEqual(metric['value'], totals.sums[i] / totals.n, places=14)
                        from poker_equity import uncertainty
                        self.assertEqual(metric, uncertainty(totals.sums[i], totals.squares[i], totals.n))
                for i, metric in enumerate(reference['categories'].values()):
                    self.assertEqual(metric['value'], totals.categories[i] / totals.n)
                for phase, counts in [('current', totals.threats_now), ('final', totals.threats_final)]:
                    threats = reference['opponent_threats'][phase]
                    if threats is not None:
                        for i, metric in enumerate(threats.values()):
                            self.assertEqual(metric['value'], counts[i] / totals.n)

    def test_native_progress_seed_and_cancellation(self):
        updates = []
        args = dict(hero_cards=['As', 'Kh'], community_cards=['2s', '7d', 'Jh'],
                    opponents_count=8, simulations=5001, random_seed=-12345678901234567890,
                    backend='rust')
        final = calculate_equity(**args, progress=updates.append)
        self.assertEqual(final['backend'], 'rust')
        self.assertEqual([r['simulations'] for r in updates], [256, 1024, 5000])
        self.assertEqual(final['metrics'], calculate_equity(**args)['metrics'])
        self.assertTrue(final['complete'])
        self.assertIsNone(calculate_equity(**args, cancelled=lambda: True))
        updates.clear()
        self.assertIsNone(calculate_equity(**args, progress=updates.append,
                                          cancelled=lambda: bool(updates)))
        self.assertEqual(len(updates), 1)

    def test_callback_exceptions_propagate(self):
        def fail(_):
            raise RuntimeError('test callback')
        with self.assertRaisesRegex(RuntimeError, 'test callback'):
            calculate_equity(['As', 'Kh'], [], 2, backend='rust', progress=fail)


class NativeFallbackTests(unittest.TestCase):
    def test_progress_cannot_block_or_displace_final_result(self):
        from queue import Queue
        from types import SimpleNamespace
        requests, responses = Queue(), Queue(maxsize=2)
        requests.put((1, {}))
        requests.put(None)

        def calculate(**kwargs):
            for n in range(12):
                kwargs['progress'](dict(status='ready', complete=False, simulations=n))
            return dict(status='ready', complete=True, simulations=250000)

        with patch('equity_service.calculate_equity', side_effect=calculate):
            _worker(requests, responses, SimpleNamespace(value=1))
        results = [responses.get_nowait() for _ in range(responses.qsize())]
        self.assertTrue(results[-1][1]['complete'])
        self.assertEqual(results[-1][1]['simulations'], 250000)

    def test_unavailable_library_falls_back_but_explicit_rust_reports_error(self):
        with patch('native_equity.load_native', return_value=None):
            result = calculate_equity(['As', 'Kh'], [], 2, simulations=20)
            self.assertEqual(result['backend'], 'python')
            with self.assertRaisesRegex(RuntimeError, 'Rust'):
                calculate_equity(['As', 'Kh'], [], 2, simulations=20, backend='rust')

    def test_invalid_backend_is_rejected(self):
        with self.assertRaises(ValueError):
            calculate_equity(['As', 'Kh'], [], 2, backend='invalid')


if __name__ == '__main__':
    unittest.main()

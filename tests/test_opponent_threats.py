import unittest

from poker_equity import calculate_equity


class OpponentThreatTests(unittest.TestCase):
    def test_flush_can_beat_trips_against_two_opponents(self):
        result = calculate_equity(['7c', '7d'], ['7h', '2h', 'Kh'], 2,
                                  simulations=2000, random_seed=42, backend='python')
        threats = result['opponent_threats']
        self.assertGreater(threats['current']['Flush']['value'], 0)
        self.assertGreater(threats['final']['Flush']['value'], 0)
        for phase, metric in [('current', 'currently_behind'), ('final', 'lose')]:
            self.assertAlmostEqual(sum(m['value'] for m in threats[phase].values()),
                                   result['metrics'][metric]['value'])

    def test_royal_flush_board_is_a_tie_without_threats(self):
        result = calculate_equity(['2c', '3d'], ['Th', 'Jh', 'Qh', 'Kh', 'Ah'], 1,
                                  backend='python')
        for phase in ('current', 'final'):
            self.assertTrue(all(m['value'] == 0 for m in result['opponent_threats'][phase].values()))
        self.assertEqual(result['metrics']['tie']['value'], 1)

    def test_river_counts_same_category_with_better_kicker(self):
        result = calculate_equity(['As', '2d'], ['Ac', 'Kh', '9s', '6d', '3c'], 1,
                                  backend='python')
        self.assertGreater(result['opponent_threats']['current']['One Pair']['value'], 0)
        self.assertEqual(result['opponent_threats']['current'], result['opponent_threats']['final'])

    def test_preflop_has_only_final_threats(self):
        result = calculate_equity(['As', 'Ad'], [], 2, simulations=100,
                                  random_seed=7, backend='python')
        self.assertIsNone(result['opponent_threats']['current'])
        self.assertAlmostEqual(sum(m['value'] for m in result['opponent_threats']['final'].values()),
                               result['metrics']['lose']['value'])

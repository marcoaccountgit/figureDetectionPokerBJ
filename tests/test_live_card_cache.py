from pathlib import Path
import unittest

from card_detector import cv2, np
from capture_alignment import CaptureAligner
from hand_counter import player_card_presence
from live_card_cache import card_inference_needed, unconfirmed_card_frame
from table_profiles import NINE_HERO, desktop_layout
from temporal_cards import HandCardMemory


def known_flop():
    source = cv2.imread(str(Path(__file__).resolve().parent / 'fixtures/six-black-three.jpg'))
    aligner = CaptureAligner()
    game, viewport = aligner.align(source)
    scale = game.shape[1] / 1762
    cards = []
    for slot, code in enumerate(('7S', 'JS', '3S')):
        x, y = 654 + 101 * slot, 395
        cards.append(dict(card=code, accepted=True, confidence=.99, table_group='board', board_slot=slot,
                          bbox=[round(v * scale) for v in (x - 12, y - 20, x + 12, y + 20)]))
    for slot, (code, box) in enumerate(zip(('8D', '7D'), NINE_HERO)):
        cards.append(dict(card=code, accepted=True, confidence=.99, table_group='player_hand', hand_slot=slot,
                          bbox=[round(v * scale) for v in box]))
    memory = HandCardMemory()
    memory.update(dict(cards=cards), dict(active=True, started=False, ended=False))
    return source, game, viewport, aligner.profile, cards, memory


class LiveCardCacheTests(unittest.TestCase):
    def test_periodic_revalidation_exposes_locked_cards_in_a_bounded_burst(self):
        _, game, _, profile, _, memory = known_flop()
        presence = [dict(present=True)]*2
        for _ in range(39):
            self.assertFalse(card_inference_needed(game,memory,True,presence,profile)[0])
        for _ in range(8):
            needed, info = card_inference_needed(game,memory,True,presence,profile)
            self.assertTrue(needed)
            self.assertTrue(info['revalidate'])
            self.assertIs(unconfirmed_card_frame(game,memory,True,profile,info),game)
        self.assertFalse(card_inference_needed(game,memory,True,presence,profile)[0])

    def test_missing_old_turn_detects_new_flop_but_not_a_dark_occlusion(self):
        _, game, _, profile, cards, memory = known_flop()
        scale = game.shape[1] / 1762
        cx = 654 + 101*3
        box = [round(v*scale) for v in (cx-24,365,cx+26,430)]
        turn = dict(cards[0], card='KH', board_slot=3, bbox=box)
        memory.cards[('board', 3)] = turn
        a,b,c,d = box
        game[b:d,a:c] = 0
        presence = player_card_presence(game, profile)
        self.assertFalse(card_inference_needed(game, memory, True, presence, profile)[1].get('board_cleared', False))
        game[b:d,a:c] = (30,120,30)
        needed, info = card_inference_needed(game, memory, True, presence, profile)
        self.assertTrue(needed)
        self.assertTrue(info['board_cleared'])
        self.assertIs(unconfirmed_card_frame(game, memory, True, profile, info), game)
        # Also clear a folded board while one hero identity is still unknown.
        memory.cards.pop(('player_hand', 1))
        self.assertTrue(card_inference_needed(game, memory, False, presence, profile)[1]['board_cleared'])

    def test_cleared_board_requests_new_cycle_only_with_exposed_felt(self):
        _, game, _, profile, _, memory = known_flop()
        scale = game.shape[1] / 1762
        for slot in range(3):
            cx = 654 + 101 * slot
            a, b, c, d = [round(v * scale) for v in (cx-24, 365, cx+26, 430)]
            game[b:d, a:c] = (30,120,30)
        needed, info = card_inference_needed(game, memory, True, player_card_presence(game, profile), profile)
        self.assertTrue(needed)
        self.assertTrue(info['board_cleared'])
        game[b:d, a:c] = 0  # Occlusion cannot certify a new deal.
        self.assertFalse(card_inference_needed(game, memory, True, player_card_presence(game, profile), profile)[1].get('board_cleared', False))

    def test_actions_and_fold_outside_card_slots_do_not_require_recognition(self):
        _, game, _, profile, _, memory = known_flop()
        presence = player_card_presence(game, profile)
        self.assertFalse(card_inference_needed(game, memory, True, presence, profile)[0])
        scale = game.shape[1] / 1762
        for box in desktop_layout(profile)['backs'].values():
            x, y, r, b = [round(v * scale) for v in box]
            game[y:b, x:r] = (25, 30, 35)  # A fold removes backs, not our cards.
        cv2.putText(game, 'CALL / RAISE', (20, game.shape[0] - 15), 0, .5, (255, 255, 255), 1)
        self.assertFalse(card_inference_needed(game, memory, True, presence, profile)[0])

    def test_new_turn_is_retried_until_it_is_confirmed_even_after_an_ocr_miss(self):
        _, game, _, profile, _, memory = known_flop()
        scale = game.shape[1] / 1762
        x, y = 654 + 101 * 3, 395
        left, top, right, bottom = [round(v * scale) for v in (x - 24, y - 30, x + 26, y + 35)]
        game[top:bottom, left:right] = 255
        presence = player_card_presence(game, profile)
        for _ in range(6):
            needed, info = card_inference_needed(game, memory, True, presence, profile)
            self.assertTrue(needed)
            self.assertEqual(info['reason'], 'new_board_card')
            memory.update(dict(cards=[]), dict(active=True, started=False, ended=False))

    def test_only_a_new_cycle_invalidates_confirmed_identities(self):
        _, game, _, profile, _, memory = known_flop()
        presence = player_card_presence(game, profile)
        self.assertTrue(card_inference_needed(game, memory, False, presence, profile)[0])
        self.assertFalse(card_inference_needed(game, memory, True, [dict(present=False)] * 2, profile)[0])
        self.assertFalse(card_inference_needed(game, memory, True, [dict(present=None)] * 2, profile)[0])
        scale = game.shape[1] / 1762
        x, y, r, b = [round(v * scale) for v in desktop_layout(profile)['backs']['top']]
        game[y:b, x:r] = 255
        needed, info = card_inference_needed(game, memory, True, presence, profile)
        self.assertFalse(needed)
        self.assertEqual(info['reason'], 'confirmed_slots_unchanged')

    def test_partial_flop_and_occlusion_do_not_reread_locked_slots(self):
        _, game, _, profile, _, memory = known_flop()
        memory.cards.pop(('board', 2))
        presence = player_card_presence(game, profile)
        self.assertEqual(card_inference_needed(game, memory, True, presence, profile)[1]['new_slot'], 2)
        scale = game.shape[1] / 1762
        # A dialog hides a confirmed card; the remaining unknown flop card
        # still triggers reading, but the known identity remains locked.
        game[round(365*scale):round(430*scale), round(630*scale):round(680*scale)] = 0
        info = card_inference_needed(game, memory, True, presence, profile)[1]
        masked = unconfirmed_card_frame(game, memory, True, profile, info)
        for group, slot in memory.cards:
            box = memory.cards[(group,slot)]['bbox']
            left, top, right, bottom = box
            self.assertFalse(np.any(masked[top:bottom,left:right]))
        cx = 654 + 101*2
        left,top,right,bottom = [round(v*scale) for v in (cx-12,375,cx+12,415)]
        self.assertTrue(np.array_equal(masked[top:bottom,left:right], game[top:bottom,left:right]))
        self.assertIs(unconfirmed_card_frame(game, memory, True, profile, {'board_cleared':True}), game)

    def test_new_turn_does_not_expose_confirmed_cards_to_model(self):
        _, game, _, profile, _, memory = known_flop()
        scale = game.shape[1] / 1762
        cx = 654 + 101*3
        left,top,right,bottom = [round(v*scale) for v in (cx-24,365,cx+26,430)]
        game[top:bottom,left:right] = 255
        masked = unconfirmed_card_frame(game, memory, True, profile, {'reason':'new_board_card'})
        self.assertTrue(np.all(masked[top:bottom,left:right] == 255))
        for card in memory.cards.values():
            a,b,c,d = card['bbox']
            self.assertFalse(np.any(masked[b:d,a:c]))

    def test_viewport_resize_preserves_identities_and_reprojects_boxes(self):
        _, game, _, profile, _, memory = known_flop()
        before = {key: dict(card) for key, card in memory.cards.items()}
        smaller = cv2.resize(game, (round(game.shape[1] * .8), round(game.shape[0] * .8)))
        memory.rescale(smaller.shape[1] / game.shape[1])
        self.assertEqual({k: c['card'] for k, c in memory.cards.items()}, {k: c['card'] for k, c in before.items()})
        self.assertFalse(card_inference_needed(smaller, memory, True,
                                             player_card_presence(smaller, profile), profile)[0])


if __name__ == '__main__':
    unittest.main()

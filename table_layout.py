"""PokerStars board slots from the reviewed 195129/211955/213508/capture10 videos.

Coordinates scale uniformly with game width, as in the model crop. Extra
bottom controls do not move the board. No historical identities are retained.
"""

LABELS = ('Flop 1', 'Flop 2', 'Flop 3', 'Turn', 'River')


def arrange_table(result, shape):
    from table_profiles import is_desktop, NINE_HERO
    nine = is_desktop(result.get('table_profile',result.get('profile')))
    scale = shape[1] / 1762
    slots = [None] * 5
    hand_slots = [None] * 2
    cards = []
    for original in result['cards']:
        card = dict(original, table_group='other', board_slot=None, hand_slot=None)
        x1, y1, x2, y2 = card['bbox']
        x, y = (x1+x2)/2/scale, (y1+y2)/2/scale
        board_x,board_step,board_y = (654,101,395) if nine else (615,116,441)
        slot = min(range(5), key=lambda i: abs(x-(board_x+board_step*i)))
        # Reviewed index centres: x=615+116*i, y approximately 441.
        # Reject neighbouring player cards and detections between slots.
        if abs(x-(board_x+board_step*slot)) <= (33 if nine else 46) and abs(y-board_y) <= (44 if nine else 58):
            card.update(table_group='board', board_slot=slot)
            previous = slots[slot]
            if previous is None or (card['accepted'], card.get('confidence', 0)) > (
                    previous['accepted'], previous.get('confidence', 0)):
                slots[slot] = card
        else:
            # Hole-card index centres in all four reviewed layouts. The
            # second card is slightly lower because the cards overlap.
            hand_x = [(b[0]+b[2])/2 for b in NINE_HERO] if nine else [667,712]
            hand_y = [(b[1]+b[3])/2 for b in NINE_HERO] if nine else [698,711]
            hand_slot = min(range(2), key=lambda i: abs(x-hand_x[i]))
            if abs(x-hand_x[hand_slot]) <= 25 and abs(y-hand_y[hand_slot]) <= 65:
                card.update(table_group='player_hand', hand_slot=hand_slot)
                previous = hand_slots[hand_slot]
                if previous is None or (card['accepted'], card.get('confidence', 0)) > (
                        previous['accepted'], previous.get('confidence', 0)):
                    hand_slots[hand_slot] = card
        cards.append(card)
    # Preserve all detections for overlays; order presentation by spatial position.
    cards.sort(key=lambda c: ({'board': 0, 'player_hand': 1, 'other': 2}[c['table_group']],
                              c['board_slot'] if c['board_slot'] is not None else
                              c['hand_slot'] if c['hand_slot'] is not None else c['bbox'][1],
                              c['bbox'][0]))
    board = [dict(slot=i, label=label, card=c['card'] if c and c['accepted'] else None,
                  detected=c is not None, accepted=bool(c and c['accepted']),
                  bbox=c['bbox'] if c else None)
             for i, (label, c) in enumerate(zip(LABELS, slots))]
    player_hand = [dict(slot=i, label=label, card=c['card'] if c and c['accepted'] else None,
                        detected=c is not None, accepted=bool(c and c['accepted']),
                        bbox=c['bbox'] if c else None)
                   for i, (label, c) in enumerate(zip(('Sinistra', 'Destra'), hand_slots))]
    return dict(result, cards=cards, board=board, player_hand=player_hand)

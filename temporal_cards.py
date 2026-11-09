"""Confirm current card indices using recent, spatially matching observations."""
from collections import deque
import math
from time import perf_counter


def overlap(a, b):
    area = max(0, min(a[2], b[2])-max(a[0], b[0])) * max(0, min(a[3], b[3])-max(a[1], b[1]))
    union = (a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - area
    return area/union if union > 0 else 0


def same_table_slot(current, previous):
    """A reviewed table slot survives the client's winning-card lift animation."""
    group = current.get('table_group')
    field = {'board': 'board_slot', 'player_hand': 'hand_slot'}.get(group)
    return (field is not None and previous.get('table_group') == group
            and isinstance(current.get(field), int)
            and current[field] == previous.get(field))


class HandCardMemory:
    """Keep confirmed slot identities until the physical hand cycle changes."""

    def __init__(self):
        self.cards = {}

    def rescale(self, factor):
        """A registered viewport resize changes geometry, not card identities."""
        for key, card in self.cards.items():
            item = dict(card, bbox=[round(v * factor) for v in card['bbox']])
            if card.get('polygon') is not None:
                item['polygon'] = [[round(x * factor), round(y * factor)] for x, y in card['polygon']]
            self.cards[key] = item

    def update(self, result, cycle):
        if cycle['started'] or (not cycle['active'] and cycle.get('board_cleared')):
            self.cards.clear()
        elif cycle['ended']:
            # Folding removes the hero's cards, not the shared board.
            self.cards = {key: card for key, card in self.cards.items() if key[0] == 'board'}
        if not cycle['active']:
            result = dict(result, cards=[card for card in result['cards']
                                        if card.get('table_group') != 'player_hand'])
        current = []
        seen = set()
        for card in result['cards']:
            group = card.get('table_group')
            field = {'board': 'board_slot', 'player_hand': 'hand_slot'}.get(group)
            slot = card.get(field) if field else None
            if not isinstance(slot, int):
                current.append(card)
                continue
            key = (group, slot)
            if key in seen:
                continue
            seen.add(key)
            if key not in self.cards and card['accepted']:
                self.cards[key] = dict(card)
            saved = self.cards.get(key)
            current.append(dict(saved, bbox=card['bbox'],
                                retained=not card['accepted'] or card['card'] != saved['card'])
                           if saved else card)
        current.extend(dict(card, retained=True) for key, card in self.cards.items() if key not in seen)
        return dict(result, cards=current)


class TemporalCards:
    """Require a matching reading in one of the two preceding frames (<=650ms).

    Never emit historical cards: the current detector must accept the same code.
    A disappeared or changed card is therefore removed immediately. Persistent
    classification errors can still pass this filter.
    """
    def __init__(self, required_observations=2, min_span=0, max_age=.65, window_frames=3,
                 consecutive=False, max_gap=None):
        if required_observations < 2 or window_frames < required_observations or not 0 <= min_span < max_age:
            raise ValueError('Invalid temporal confirmation settings')
        self.required_observations = required_observations
        self.min_span, self.max_age = min_span, max_age
        self.window_frames, self.consecutive = window_frames, consecutive
        if max_gap is not None and max_gap <= 0:
            raise ValueError('Invalid maximum observation gap')
        self.max_gap = max_gap
        self.history = deque(maxlen=window_frames-1)
        self.shape = None
        self.last_timestamp = None

    def update(self, result, timestamp, shape):
        start = perf_counter()
        if not math.isfinite(timestamp):
            raise ValueError('Temporal timestamp must be finite')
        shape = tuple(shape[:2])
        if (self.shape != shape or (self.last_timestamp is not None and
                (timestamp <= self.last_timestamp or (self.max_gap is not None and timestamp-self.last_timestamp > self.max_gap)))):
            self.history.clear()
        self.shape, self.last_timestamp = shape, timestamp
        while self.history and timestamp-self.history[0][0] > self.max_age:
            self.history.popleft()
        raw = result['cards']
        current = []
        # A previous index supports at most one current index in each frame.
        used = [set() for _ in self.history]
        for card in sorted(raw, key=lambda c: c.get('confidence', 0), reverse=True):
            item = dict(card, frame_accepted=card['accepted'], temporal_confirmed=False,
                        temporal_support=0)
            if card['accepted']:
                matches = []
                for slot in reversed(range(len(self.history))):
                    when, observations = self.history[slot]
                    candidates = [(1.0 if same_table_slot(card, previous) else overlap(card['bbox'], previous['bbox']), i)
                                  for i, previous in enumerate(observations)
                                  if i not in used[slot] and previous['card'] == card['card']]
                    iou, index = max(candidates, default=(0, -1))
                    if iou >= .3:
                        used[slot].add(index)
                        matches.append(when)
                    elif self.consecutive:
                        break
                item['temporal_support'] = 1+len(matches)
                confirmed = (1+len(matches) >= self.required_observations
                             and timestamp-min(matches, default=timestamp) >= self.min_span)
                item['temporal_confirmed'] = confirmed
                if confirmed:
                    item['confirmation_span_ms'] = round((timestamp-min(matches))*1000, 3)
                else:
                    item['accepted'] = False
                    item['card'] = None
            current.append(item)
        observations = [{key: c[key] for key in
                         ('card', 'bbox', 'table_group', 'board_slot', 'hand_slot') if key in c}
                        for c in raw if c['accepted']]
        self.history.append((timestamp, observations))
        elapsed = (perf_counter()-start)*1000
        return dict(result, cards=current, raw_cards=raw,
                    frame_processing_ms=result['processing_ms'],
                    processing_ms=round(result['processing_ms']+elapsed, 3),
                    temporal={'enabled': True, 'required_observations': self.required_observations,
                              'window_frames': self.window_frames, 'max_age_ms': self.max_age*1000,
                              'min_span_ms': self.min_span*1000, 'consecutive': self.consecutive,
                              'max_gap_ms': self.max_gap*1000 if self.max_gap is not None else None,
                              'processing_ms': round(elapsed, 3)})

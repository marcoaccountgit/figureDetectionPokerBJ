"""Confirm current card indices using recent, spatially matching observations."""
from collections import deque
import math
from time import perf_counter


def overlap(a, b):
    area = max(0, min(a[2], b[2])-max(a[0], b[0])) * max(0, min(a[3], b[3])-max(a[1], b[1]))
    union = (a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - area
    return area/union if union > 0 else 0


class TemporalCards:
    """Require a matching reading in one of the two preceding frames (<=650ms).

    Never emit historical cards: the current detector must accept the same code.
    A disappeared or changed card is therefore removed immediately. Persistent
    classification errors can still pass this filter.
    """
    def __init__(self):
        self.history = deque(maxlen=2)
        self.shape = None
        self.last_timestamp = None

    def update(self, result, timestamp, shape):
        start = perf_counter()
        if not math.isfinite(timestamp):
            raise ValueError('Temporal timestamp must be finite')
        shape = tuple(shape[:2])
        if self.shape != shape or (self.last_timestamp is not None and timestamp <= self.last_timestamp):
            self.history.clear()
        self.shape, self.last_timestamp = shape, timestamp
        while self.history and timestamp-self.history[0][0] > .65:
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
                for slot, (when, observations) in enumerate(self.history):
                    candidates = [(overlap(card['bbox'], previous['bbox']), i)
                                  for i, previous in enumerate(observations)
                                  if i not in used[slot] and previous['card'] == card['card']]
                    iou, index = max(candidates, default=(0, -1))
                    if iou >= .3:
                        used[slot].add(index)
                        matches.append(when)
                item['temporal_support'] = 1+len(matches)
                item['temporal_confirmed'] = bool(matches)
                if matches:
                    item['confirmation_span_ms'] = round((timestamp-min(matches))*1000, 3)
                else:
                    item['accepted'] = False
                    item['card'] = None
            current.append(item)
        observations = [{'card': c['card'], 'bbox': list(c['bbox'])} for c in raw if c['accepted']]
        self.history.append((timestamp, observations))
        elapsed = (perf_counter()-start)*1000
        return dict(result, cards=current, raw_cards=raw,
                    frame_processing_ms=result['processing_ms'],
                    processing_ms=round(result['processing_ms']+elapsed, 3),
                    temporal={'enabled': True, 'required_observations': 2,
                              'window_frames': 3, 'max_age_ms': 650,
                              'processing_ms': round(elapsed, 3)})

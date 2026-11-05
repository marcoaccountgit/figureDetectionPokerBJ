"""Detect exposed pairs of red card backs in the reviewed PokerStars layout.

Calibrated from existing recordings; does not read names or infer occupancy.
"""
from pathlib import Path
from card_detector import cv2, np

SEATS = (
    ('top', 'Alto', (805, 70, 970, 170)),
    ('upper_left', 'Sinistra alta', (250, 240, 410, 335)),
    ('upper_right', 'Destra alta', (1380, 240, 1540, 335)),
    ('lower_left', 'Sinistra bassa', (250, 495, 410, 590)),
    ('lower_right', 'Destra bassa', (1380, 495, 1540, 590)),
)


def features(image):
    hue, saturation, value = cv2.split(cv2.cvtColor(image, cv2.COLOR_BGR2HSV))
    white = (saturation < 85) & (value > 165)
    red = ((hue < 12) | (hue > 170)) & (saturation > 100) & (value > 75)
    return np.where(white, 255, np.where(red, 100, 0)).astype(np.uint8)


class OpponentDetector:
    def __init__(self):
        path = Path(__file__).parent / 'assets/opponents/covered-pair.png'
        image = cv2.imread(str(path))
        if image is None:
            raise RuntimeError('Riferimento delle carte coperte mancante')
        self.template = features(image)

    def detect(self, frame):
        scale = frame.shape[1] / 1762
        canonical = cv2.resize(frame, (1762, round(frame.shape[0]/scale)))
        seats = []
        for key, label, (x, y, right, bottom) in SEATS:
            roi = canonical[y:bottom, x:right]
            bbox, score = None, 0.0
            if roi.shape[0] >= self.template.shape[0] and roi.shape[1] >= self.template.shape[1]:
                _, score, _, location = cv2.minMaxLoc(cv2.matchTemplate(features(roi), self.template, cv2.TM_CCOEFF_NORMED))
                if score >= .72:
                    px, py = x+location[0], y+location[1]
                    bbox = [round(v*scale) for v in (px, py, px+self.template.shape[1], py+self.template.shape[0])]
                present = True if score >= .72 else None if score >= .5 else False
            else:
                present = None
            seats.append(dict(seat=key, label=label, present=present, score=round(score,4), bbox=bbox))
        return seats


class OpponentTracker:
    """Confirm presence AND absence with five consecutive samples over 300 ms."""
    def __init__(self):
        self.states = {}
        self.last_timestamp = None

    def update(self, seats, timestamp, player_hand):
        if self.last_timestamp is not None and (timestamp <= self.last_timestamp or timestamp-self.last_timestamp > 2):
            self.states.clear()
        self.last_timestamp = timestamp
        output = []
        for seat in seats:
            key, value = seat['seat'], seat['present']
            state = self.states.get(key)
            if value is None:
                self.states.pop(key, None)
                state = None
            elif state is None or state['value'] != value:
                state = dict(value=value, samples=1, start=timestamp)
                self.states[key] = state
            else:
                state['samples'] += 1
            confirmed = bool(state and state['samples'] >= 5 and timestamp-state['start'] >= .3)
            output.append(dict(seat, confirmed=confirmed, in_hand=value if confirmed else None))
        ready = len(output) == 5 and all(s['confirmed'] for s in output)
        count = sum(s['in_hand'] is True for s in output) if ready else None
        hero = len(player_hand) == 2 and all(c['detected'] for c in player_hand)
        return dict(seats=output, count=count, pending=not ready,
                    player_in_hand=hero, players_with_cards=count+int(hero) if ready else None,
                    method='visible_covered_pairs', required_observations=5, min_span_ms=300)

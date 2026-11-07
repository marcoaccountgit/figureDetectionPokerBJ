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
        nine = cv2.imread(str(Path(__file__).parent/'assets/table-nine/covered-pair.png'))
        self.nine_template = features(nine) if nine is not None else None
        self.nine_templates={}
        for path in (Path(__file__).parent/'assets/table-nine').glob('covered-*.png'):
            if path.stem=='covered-pair':continue
            self.nine_templates[path.stem.removeprefix('covered-')]=features(cv2.imread(str(path)))
        self.desktop_six_templates={path.stem.removeprefix('covered-'):features(cv2.imread(str(path)))
                                    for path in (Path(__file__).parent/'assets/table-desktop-six').glob('covered-*.png')}
        self.desktop_six_variants={}
        for path in (Path(__file__).parent/'assets/table-desktop-six/variants').glob('*/*.png'):
            self.desktop_six_variants.setdefault(path.parent.name,[]).append(features(cv2.imread(str(path))))

    def detect(self, frame, visible_y=None, profile='pokerstars',visible_x=None):
        from table_profiles import NINE, DESKTOP_SIX,is_desktop,desktop_layout
        nine = is_desktop(profile)
        template = self.nine_template if nine else self.template
        if template is None:raise RuntimeError('Riferimento delle carte coperte a nove posti mancante')
        labels={'top':'Alto','top_left':'Alto sinistra','top_right':'Alto destra','upper_left':'Sinistra alta',
                'upper_right':'Destra alta','middle_left':'Sinistra centro','middle_right':'Destra centro',
                'lower_left':'Sinistra bassa','lower_right':'Destra bassa'}
        definitions = [(key,labels[key],box) for key,box in desktop_layout(profile)['backs'].items()] if nine else SEATS
        scale = frame.shape[1] / 1762
        canonical = cv2.resize(frame, (1762, round(frame.shape[0]/scale)))
        seats = []
        for key, label, (x, y, right, bottom) in definitions:
            if nine:template=self.nine_templates.get('top_left' if key=='top' else key,self.nine_template)
            if profile==DESKTOP_SIX:template=self.desktop_six_templates.get(key,template)
            if ((visible_y is not None and (y < visible_y[0] or bottom > visible_y[1])) or
                    (visible_x is not None and (x < visible_x[0] or right > visible_x[1]))):
                seats.append(dict(seat=key,label=label,present=None,score=0,bbox=None,
                                  occluded=True,reason='outside_visible_capture'))
                continue
            roi = canonical[y:bottom, x:right]
            bbox, score = None, 0.0
            candidates=[template]+(self.desktop_six_variants.get(key,[]) if profile==DESKTOP_SIX else [])
            if profile==DESKTOP_SIX and 'pair' in self.desktop_six_templates:
                # Match only the shared upper strip of both backs. Avatars
                # and HUDs hide different lower edges in the six-seat client.
                candidates.append(self.desktop_six_templates['pair'])
            matches=[]
            for candidate in candidates:
                if roi.shape[0]>=candidate.shape[0] and roi.shape[1]>=candidate.shape[1]:
                    _,value,_,location=cv2.minMaxLoc(cv2.matchTemplate(features(roi),candidate,cv2.TM_CCOEFF_NORMED))
                    matches.append((value,location,candidate))
            if matches:
                score,location,matched=max(matches,key=lambda m:m[0])
                if score >= .72:
                    px, py = x+location[0], y+location[1]
                    bbox = [round(v*scale) for v in (px, py, px+matched.shape[1], py+matched.shape[0])]
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
        self.seat_keys = None

    def update(self, seats, timestamp, player_hand):
        keys = frozenset(seat['seat'] for seat in seats)
        if keys != self.seat_keys:
            self.states.clear()
            self.seat_keys = keys
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
        ready = (1 <= len(output) <= 9 and len(keys) == len(output)
                 and all(s['confirmed'] for s in output))
        count = sum(s['in_hand'] is True for s in output) if ready else None
        hero = len(player_hand) == 2 and all(c['detected'] for c in player_hand)
        return dict(seats=output, count=count, pending=not ready,
                    max_opponents=len(output),
                    player_in_hand=hero, players_with_cards=count+int(hero) if ready else None,
                    method='visible_covered_pairs', required_observations=5, min_span_ms=300)

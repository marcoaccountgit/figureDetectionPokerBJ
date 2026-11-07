"""Count observed player hands, separately from rank recognition failures.

Geometry/colour calibrated against the existing PokerStars recording frames.
No table-wide hand identifier or absolute poker hand number is inferred.
"""
from card_detector import cv2, np

PLAYER_INDICES = ((648,650,686,746), (688,662,736,760))


def player_card_presence(frame, profile='pokerstars'):
    """True=white card face, False=exposed green felt, None=occluded/ambiguous."""
    scale = frame.shape[1] / 1762
    canonical = cv2.resize(frame, (1762, round(frame.shape[0]/scale)))
    def felt_fraction(image):
        if not image.size:
            return 0.0
        h,s,v = cv2.split(cv2.cvtColor(image,cv2.COLOR_BGR2HSV))
        return float(np.mean((h > 30) & (h < 100) & (s > 65) & (v > 35)))

    # A white dialog covering the whole player region must not look like
    # two new cards. Check exposed felt above and to the left as context.
    from table_profiles import is_desktop, NINE_HERO
    nine = is_desktop(profile)
    context_ok = (felt_fraction(canonical[630:645,790:930]) >= .3 if nine else
                  felt_fraction(canonical[615:635,645:735]) >= .4
                  and felt_fraction(canonical[660:730,620:637]) >= .4)
    slots = []
    for box in NINE_HERO if nine else PLAYER_INDICES:
        x,y,right,bottom = box
        if bottom > canonical.shape[0]:
            slots.append(dict(present=None, white_fraction=0, felt_fraction=0))
            continue
        hue,saturation,value = cv2.split(cv2.cvtColor(canonical[y:bottom,x:right],cv2.COLOR_BGR2HSV))
        white = float(np.mean((saturation < 65) & (value > 180)))
        felt = float(np.mean((hue > 30) & (hue < 100) & (saturation > 65) & (value > 35)))
        visible_face = (white >= .4 and felt <= .2) if nine else (white >= .4 and felt <= .1)
        present = (True if context_ok and visible_face else
                   False if context_ok and white <= .08 and felt >= .3 else None)
        slots.append(dict(present=present, white_fraction=round(white,4), felt_fraction=round(felt,4)))
    return slots


class HandCounter:
    def __init__(self):
        self.count = 0
        self.active = False
        self.last_timestamp = None
        self.reset_observations()

    def reset_observations(self):
        """Forget pending evidence, retaining the count and current cycle."""
        self.candidate = None
        self.samples = 0
        self.since = None

    def update(self, presence, hand, timestamp):
        if self.last_timestamp is not None and (timestamp <= self.last_timestamp or timestamp-self.last_timestamp > 2):
            self.reset_observations()
        self.last_timestamp = timestamp
        visible = [s['present'] for s in presence]
        candidate = None
        if len(visible) == 2:
            if self.active:
                if all(value is False for value in visible):
                    candidate = ('end',)
            elif all(value is True for value in visible):
                # Count physical deals, even if a rank/suit is unreadable.
                candidate = ('start',)
        if candidate is None:
            self.reset_observations()
        elif candidate != self.candidate:
            self.candidate, self.samples, self.since = candidate, 1, timestamp
        else:
            self.samples += 1
        started = ended = False
        if candidate and self.samples >= 5 and timestamp-self.since >= .3:
            if candidate[0] == 'start':
                self.count += 1
                self.active = started = True
            else:
                self.active = False
                ended = True
            self.reset_observations()
        return dict(count=self.count, active=self.active, started=started, ended=ended,
                    presence=presence, pending_samples=self.samples,
                    recognized_cards=sum(bool(c.get('accepted')) for c in hand),
                    required_observations=5, min_span_ms=300)

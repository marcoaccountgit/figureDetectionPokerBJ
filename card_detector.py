"""Local recognition of digital and physical cards in the supplied casino video.

No network calls, game interaction, strategy or hidden-card inference.
"""
from pathlib import Path
import sys
from time import perf_counter

try:
    import cv2
    import numpy as np
except ImportError:
    # Development fallback; an activated virtual environment takes precedence.
    sys.path.insert(0, str(Path(__file__).parent / '.local-deps'))
    import cv2
    import numpy as np

cv2.setNumThreads(1)


BASE_SIZE = (1480, 920)

# Search bands and approximate card widths for the two recorded camera views.
PHYSICAL_BANDS = {
    'stud': [('dealer', (600, 500, 940, 557), 52),
             ('player', (600, 580, 940, 650), 53)],
    'holdem': [('dealer', (680, 470, 840, 520), 41),
               ('board', (620, 550, 925, 595), 49),
               ('player', (680, 600, 850, 660), 54)],
}


def ordered_quad(points):
    points = np.float32(points).reshape(4, 2)
    # Sort into left and right pairs, then vertically within each pair.
    left, right = np.split(points[np.argsort(points[:, 0])], 2)
    left = left[np.argsort(left[:, 1])]
    right = right[np.argsort(right[:, 1])]
    return np.float32([left[0], right[0], right[1], left[1]])


def physical_candidates(frame, scene, *, white_level=160):
    for group, (x1, y1, x2, y2), card_width in PHYSICAL_BANDS.get(scene, []):
        roi = frame[y1:y2, x1:x2]
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, np.array([0, 0, white_level]), np.array([179, 65, 255]))
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for contour in sorted(contours, key=lambda c: cv2.boundingRect(c)[0]):
            x, y, w, h = cv2.boundingRect(contour)
            if cv2.contourArea(contour) < 550 or h < 20 or w < 29:
                continue
            hull = cv2.convexHull(contour)
            approx = cv2.approxPolyDP(hull, .04 * cv2.arcLength(hull, True), True)
            points = approx if len(approx) == 4 else cv2.boxPoints(cv2.minAreaRect(hull))
            points = ordered_quad(points) + np.float32([x1, y1])
            if cv2.contourArea(points) < 100:
                continue
            count = max(1, min(5, round(w / card_width)))
            width, height = count * 36, 50
            target = np.float32([[0, 0], [width-1, 0], [width-1, height-1], [0, height-1]])
            transform = cv2.getPerspectiveTransform(points, target)
            if abs(np.linalg.det(transform)) < 1e-9:
                continue
            row = cv2.warpPerspective(frame, transform, (width, height))
            inverse = np.linalg.inv(transform)
            for slot in range(count):
                card = row[:, slot*36:(slot+1)*36]
                corners = np.float32([[[slot*36, 0], [min(width-1, (slot+1)*36), 0],
                                       [min(width-1, (slot+1)*36), height-1], [slot*36, height-1]]])
                polygon = cv2.perspectiveTransform(corners, inverse)[0]
                yield group, slot, polygon, card


def normalize(frame):
    return cv2.resize(frame, BASE_SIZE, interpolation=cv2.INTER_AREA)


def candidates(frame):
    """Find upright, white UI cards; physical cards are outside this band."""
    roi = frame[650:790, 400:1130]
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array([0, 0, 180]), np.array([179, 85, 255]))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if 27 <= w <= 40 and 40 <= h <= 54 and .55 <= w / h <= .85:
            if cv2.contourArea(contour) / (w * h) > .65:
                boxes.append((x + 400, y + 650, w, h))
    return sorted(boxes, key=lambda b: (b[1] // 15, b[0]))


def ink(card):
    card = cv2.resize(card, (36, 50), interpolation=cv2.INTER_LINEAR)
    gray = cv2.cvtColor(card, cv2.COLOR_BGR2GRAY)
    return (gray < 155).astype(np.uint8)


def glyphs(card, physical=False):
    mask = ink(card)
    bottom = 24 if physical else 21
    return clean_glyph(mask[:bottom, :20], rank=True), clean_glyph(mask[:bottom, 20:36])


def clean_glyph(mask, rank=False):
    """Align each symbol independently of the card's margin and scale."""
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    components = [i for i in range(1, count)
                  if stats[i, cv2.CC_STAT_AREA] >= 4 and stats[i, cv2.CC_STAT_HEIGHT] >= 4]
    canvas = np.zeros((26, 22), np.uint8)
    if not components:
        return canvas
    largest = max(components, key=lambda i: stats[i, cv2.CC_STAT_AREA])
    keep = [largest]
    if rank:
        # Preserve the separate '1' in '10', excluding a neighbouring suit.
        keep += [i for i in components if i != largest
                 and stats[i, cv2.CC_STAT_LEFT] < stats[largest, cv2.CC_STAT_LEFT]
                 and stats[i, cv2.CC_STAT_WIDTH] <= 5
                 and stats[i, cv2.CC_STAT_HEIGHT] >= .8 * stats[largest, cv2.CC_STAT_HEIGHT]]
    selected = np.isin(labels, keep).astype(np.uint8)
    ys, xs = np.nonzero(selected)
    symbol = selected[ys.min():ys.max()+1, xs.min():xs.max()+1]
    canvas[2:24, 2:20] = cv2.resize(symbol, (18, 22), interpolation=cv2.INTER_NEAREST)
    return canvas


class Recognizer:
    def __init__(self, assets='assets', domain='digital', extra_assets=()):
        self.assets = Path(assets)
        self.domain = domain
        self.templates = {}
        for kind in ('rank', 'suit'):
            self.templates[kind] = {}
            folders = [self.assets / kind]
            folders.extend(Path(extra)/kind for extra in extra_assets)
            if domain == 'physical':
                folders.append(self.assets / 'physical' / kind)
            for path in sorted(path for folder in folders for path in folder.glob('*.png')):
                arr = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
                if arr is None:
                    raise ValueError(f'Unreadable template: {path}')
                if arr.shape != (26, 22):
                    raise ValueError(f'Outdated template {path}; regenerate with build_assets.py')
                self.templates[kind].setdefault(path.stem.split('_')[0], []).append((arr > 0).astype(np.uint8))
            if not self.templates[kind]:
                raise ValueError(f'Missing {kind} templates in {assets}')
        self.pools = {}
        for kind, classes in self.templates.items():
            images, labels = [], []
            for label, templates in classes.items():
                for template in templates:
                    vector = template.astype(np.float32).ravel()
                    vector -= vector.mean()
                    norm = np.linalg.norm(vector)
                    if norm > 0:
                        images.append(vector / norm)
                        labels.append(label)
            self.pools[kind] = np.stack(images), np.array(labels)

    def scores(self, kind, glyph):
        pool, labels = self.pools[kind]
        padded = np.pad(glyph.astype(np.float32), 1)
        windows = np.lib.stride_tricks.sliding_window_view(padded, glyph.shape).reshape(9, -1).copy()
        windows -= windows.mean(axis=1, keepdims=True)
        norms = np.linalg.norm(windows, axis=1, keepdims=True)
        windows /= np.maximum(norms, 1e-6)
        correlations = np.einsum('ij,kj->ik', windows, pool, optimize=False).max(axis=0)
        return sorted(((float(correlations[labels == label].max()), label)
                       for label in self.templates[kind]), reverse=True)

    def classify(self, card):
        if self.domain == 'physical':
            options = [self._classify(card), self._classify(cv2.rotate(card, cv2.ROTATE_180))]
            return choose_reading(options)
        return self._classify(card)

    def _classify(self, card):
        return self.classify_symbols(glyphs(card, self.domain == 'physical'), suit_color(card))

    def classify_symbols(self, symbols, color):
        """Shared symbol decision for casino faces and conventional corner indices."""
        result = {}
        for kind, glyph in zip(('rank', 'suit'), symbols):
            scores = self.scores(kind, glyph)
            if kind == 'suit' and color != 'unknown':
                allowed = 'HD' if color == 'red' else 'CS'
                scores = [(score, label) for score, label in scores if label in allowed]
            score, label = scores[0]
            margin = score - scores[1][0] if len(scores) > 1 else 0
            result[kind] = label
            result[kind + '_score'] = round(score, 4)
            result[kind + '_margin'] = round(margin, 4)
        threshold = .84 if self.domain == 'physical' else .78
        result['accepted'] = (result['rank_score'] >= threshold and result['suit_score'] >= threshold
                              and result['rank_margin'] >= .07 and result['suit_margin'] >= .07)
        result['card'] = result['rank'] + result['suit'] if result['accepted'] else None
        result['suit_color'] = color
        return result


def suit_color(card):
    """Read ink chroma, never infer a suit from the game or another card."""
    card = cv2.resize(card, (36, 50), interpolation=cv2.INTER_LINEAR)
    return ink_color(card[2:21, 20:35])


def ink_color(region):
    top = region.astype(np.int16)
    foreground = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY) < 155
    if foreground.sum() < 12:
        return 'unknown'
    blue, green, red = cv2.split(top)
    red_fraction = np.mean(((red-green > 25) & (red-blue > 25))[foreground])
    if red_fraction >= .5:
        return 'red'
    if red_fraction <= .1:
        return 'black'
    return 'unknown'


def stacked_index_symbols(region):
    """Extract vertically stacked rank/suit glyphs from a cropped index."""
    gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
    threshold, _ = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    mask = (gray < min(180, max(80, threshold))).astype(np.uint8)
    count, _, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    components = [stats[i] for i in range(1, count)
                  if stats[i, cv2.CC_STAT_AREA] >= 8
                  and 5 <= stats[i, cv2.CC_STAT_HEIGHT] <= .7 * region.shape[0]]
    rows = []
    for x, y, w, h, _ in sorted(components, key=lambda stat: stat[1]):
        if rows and y < rows[-1][3] and y+h > rows[-1][1]:
            old = rows[-1]
            rows[-1] = [min(x, old[0]), min(y, old[1]), max(x+w, old[2]), max(y+h, old[3])]
        else:
            rows.append([x, y, x+w, y+h])
    if len(rows) < 2:
        return None
    rank, suit = rows[:2]
    if rank[1] > .3 * region.shape[0] or suit[1]-rank[3] > .3 * region.shape[0]:
        return None
    x1, y1, x2, y2 = rank
    rank_symbol = clean_glyph(mask[y1:y2, x1:x2], rank=True)
    x1, y1, x2, y2 = suit
    suit_symbol = clean_glyph(mask[y1:y2, x1:x2])
    return (rank_symbol, suit_symbol), ink_color(region[y1:y2, x1:x2])


def choose_reading(options):
    """Conflicting confident readings of one card must stay uncertain."""
    best = max(options, key=lambda r: (r['accepted'], min(r['rank_score'], r['suit_score']))).copy()
    identities = {r['card'] for r in options if r['accepted']}
    for result in options:
        identities.update(result.get('conflicting_identities', []))
    if len(identities) > 1:
        best.update(accepted=False, card=None, rejection_reason='conflicting_readings',
                    conflicting_identities=sorted(identities))
    return best


def polygon_overlap(a, b):
    a, b = np.float32(a), np.float32(b)
    intersection, _ = cv2.intersectConvexConvex(a, b)
    union = cv2.contourArea(a) + cv2.contourArea(b) - intersection
    return float(intersection / union) if union > 0 else 0.0


class Detector:
    """Stateless: report visible appearances, including duplicate physical/UI cards."""
    def __init__(self, assets=None):
        assets = Path(assets) if assets else Path(__file__).parent / 'assets'
        self.digital = Recognizer(assets)
        self.physical = Recognizer(assets, 'physical')
        self.scenes = {}
        for name in PHYSICAL_BANDS:
            path = assets / 'scene' / f'{name}.png'
            template = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
            if template is None:
                raise ValueError(f'Missing scene template: {path}')
            self.scenes[name] = template

    def scene(self, frame):
        strip = cv2.cvtColor(frame[:36, 60:450], cv2.COLOR_BGR2GRAY)
        scores = [(float(cv2.matchTemplate(strip, template, cv2.TM_CCOEFF_NORMED).max()), name)
                  for name, template in self.scenes.items()]
        score, name = max(scores)
        return name if score >= .78 else 'unknown', round(score, 4)

    def detect(self, original):
        start = perf_counter()
        height, width = original.shape[:2]
        frame = normalize(original)
        scene, scene_score = self.scene(frame)
        cards = []
        for x, y, w, h in candidates(frame):
            result = self.digital.classify(frame[y:y+h, x:x+w])
            result.update(domain='digital', polygon=[[x, y], [x+w, y], [x+w, y+h], [x, y+h]])
            cards.append(result)
        # Shaded card edges can disappear at the stricter white threshold.
        # Alternate geometry may refine an existing candidate, never create a
        # second appearance or infer identity from the corresponding UI card.
        alternatives = list(physical_candidates(frame, scene, white_level=130))
        for group, slot, polygon, card in physical_candidates(frame, scene):
            result = self.physical.classify(card)
            result.update(domain='physical', group=group, polygon=polygon.tolist())
            matches = [(polygon_overlap(polygon, alt_polygon), alt_polygon, alt_card)
                       for alt_group, _, alt_polygon, alt_card in alternatives if alt_group == group]
            if matches:
                overlap, alt_polygon, alt_card = max(matches, key=lambda item: item[0])
                if overlap >= .6:
                    alternate = self.physical.classify(alt_card)
                    alternate.update(domain='physical', group=group, polygon=alt_polygon.tolist())
                    result = choose_reading([result, alternate])
            cards.append(result)
        # All coordinates returned in the caller's image coordinate system.
        for result in cards:
            points = [[round(x * width / 1480), round(y * height / 920)]
                      for x, y in result['polygon']]
            result['polygon'] = points
            result['bbox'] = [min(p[0] for p in points), min(p[1] for p in points),
                              max(p[0] for p in points), max(p[1] for p in points)]
        return {'scene': scene, 'scene_score': scene_score, 'cards': cards,
                'processing_ms': round((perf_counter() - start) * 1000, 3)}


def annotate(frame, result):
    output = frame.copy()
    for card in result['cards']:
        color = (0, 220, 0) if card['accepted'] else (0, 170, 255)
        points = np.int32(card['polygon'])
        cv2.polylines(output, [points], True, color, 2)
        x, y = points.min(axis=0)
        label = f"{card['card'] or '?'} {'P' if card['domain'] == 'physical' else 'D'}"
        cv2.putText(output, label, (int(x), max(15, int(y)-5)), cv2.FONT_HERSHEY_SIMPLEX, .45, color, 1)
    cv2.putText(output, f"{result['scene']} | {result['processing_ms']:.1f} ms", (20, 75),
                cv2.FONT_HERSHEY_SIMPLEX, .7, (0, 255, 255), 2)
    return output

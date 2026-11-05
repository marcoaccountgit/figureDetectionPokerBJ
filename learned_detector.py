"""YOLO11 ONNX card-index detector, using the existing OpenCV CPU runtime."""
import json
import os
from time import perf_counter
from card_detector import Recognizer, cv2, np, stacked_index_symbols
from download_model import MODEL_DIR, model_manifest, verified_model_files


def additional_table_regions(frame, primary):
    """Propose native-resolution tiles for revealed cards outside board/hero ROI."""
    height, width = frame.shape[:2]
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array([0, 0, 180]), np.array([179, 65, 255]))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    regions, indices = [], []
    px1, py1, px2, py2 = primary
    tile_width, tile_height = px2-px1, py2-py1
    for contour in sorted(contours, key=cv2.contourArea, reverse=True):
        area = cv2.contourArea(contour)
        x, y, w, h = cv2.boundingRect(contour)
        cx, cy = x+w/2, y+h/2
        if not .003 < area/(width*height) < .12 or h < height*.08 or not .3 < w/h < 2:
            continue
        if px1 <= cx <= px2 and py1 <= cy <= py2:
            continue
        # An overlapping hand may hide one index from the neural detector.
        # Its leftmost visible index can also be proposed from the white face.
        indices.append([x+2, y+2, min(width, x+round(.28*h)), min(height, y+round(.58*h))])
        if any(ax <= cx <= bx and ay <= cy <= by for ax, ay, bx, by in regions):
            continue
        ax = max(0, min(width-tile_width, round(cx-tile_width/2)))
        ay = max(0, min(height-tile_height, round(cy-tile_height/2)))
        regions.append([ax, ay, ax+tile_width, ay+tile_height])
    return regions, indices


def letterbox(frame):
    height, width = frame.shape[:2]
    scale = min(640 / width, 640 / height)
    resized = cv2.resize(frame, (round(width * scale), round(height * scale)))
    left, top = (640 - resized.shape[1]) // 2, (640 - resized.shape[0]) // 2
    canvas = np.full((640, 640, 3), 114, np.uint8)
    canvas[top:top+resized.shape[0], left:left+resized.shape[1]] = resized
    return cv2.dnn.blobFromImage(canvas, 1/255, (640, 640), swapRB=True), scale, left, top


def decode_indices(output, names, frame_shape, scale, left, top):
    output = np.asarray(output)
    if output.ndim != 3 or output.shape[0] != 1 or output.shape[1] != 4 + len(names):
        raise RuntimeError(f'Output ONNX inatteso: {output.shape}')
    predictions = output[0].T
    predictions = predictions[np.isfinite(predictions).all(axis=1)]
    class_ids = predictions[:, 4:].argmax(axis=1)
    confidence = predictions[np.arange(len(predictions)), class_ids + 4]
    keep = confidence >= .25
    predictions, class_ids, confidence = predictions[keep], class_ids[keep], confidence[keep]
    height, width = frame_shape[:2]
    boxes, valid, margins = [], [], []
    for index, row in enumerate(predictions):
        cx, cy, w, h = row[:4]
        if w <= 0 or h <= 0:
            continue
        x1 = max(0, min(width, float((cx - w/2 - left) / scale)))
        y1 = max(0, min(height, float((cy - h/2 - top) / scale)))
        x2 = max(0, min(width, float((cx + w/2 - left) / scale)))
        y2 = max(0, min(height, float((cy + h/2 - top) / scale)))
        if x2-x1 < 3 or y2-y1 < 3:
            continue
        boxes.append([x1, y1, x2-x1, y2-y1])
        valid.append(index)
        top_scores = np.partition(row[4:], -2)[-2:]
        margins.append(float(top_scores.max() - top_scores.min()))
    if not boxes:
        return []
    scores = [float(confidence[i]) for i in valid]
    retained = cv2.dnn.NMSBoxes(boxes, scores, .25, .45)
    cards = []
    for index in np.asarray(retained).reshape(-1):
        source = valid[index]
        code = names[int(class_ids[source])]
        score, margin = scores[index], margins[index]
        accepted = score >= .60 and margin >= .15
        x, y, w, h = boxes[index]
        x1, y1, x2, y2 = round(x), round(y), round(x+w), round(y+h)
        cards.append({'domain': 'physical', 'group': 'card_index', 'rank': code[:-1], 'suit': code[-1],
                      'card': code if accepted else None, 'accepted': accepted,
                      'confidence': round(score, 4), 'class_margin': round(margin, 4),
                      'bbox': [x1, y1, x2, y2],
                      'polygon': [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]})
    return sorted(cards, key=lambda card: (card['bbox'][1], card['bbox'][0]))


class LearnedCardDetector:
    def __init__(self, profile='general'):
        # Bound CPU parallelism; four threads avoid starving capture/UI while
        # speeding up DNN convolutions on the target laptop.
        cv2.setNumThreads(min(4, os.cpu_count() or 1))
        model, classes = verified_model_files(profile)
        self.profile = profile
        metadata = model_manifest(profile)
        self.crop = metadata.get('crop')
        self.crop_reference_size = metadata.get('crop_reference_size')
        symbol_path = metadata.get('symbol_references')
        self.symbol_classifier = Recognizer(MODEL_DIR / symbol_path) if symbol_path else None
        self.names = json.loads(classes.read_text(encoding='utf-8'))
        expected = {rank + suit for rank in ['A', 'J', 'Q', 'K', '10', *'23456789'] for suit in 'CDHS'}
        if len(self.names) != 52 or set(self.names) != expected:
            raise RuntimeError('La mappa delle classi del modello non contiene le 52 carte attese')
        self.net = cv2.dnn.readNetFromONNX(str(model))
        self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
        # opencv-python-headless uses the CPU; no Torch/Ultralytics dependency.

    def _symbol_reading(self, image):
        classifier = getattr(self, 'symbol_classifier', None)
        if classifier is None:
            return None
        symbols = stacked_index_symbols(image)
        reading = classifier.classify_symbols(*symbols) if symbols else None
        if reading and reading['accepted'] and min(reading['rank_score'], reading['suit_score']) >= .90:
            reading.update(decision_source='training_symbol_references',
                           confidence=min(reading['rank_score'], reading['suit_score']))
            return reading
        return None

    def _recover_player_indices(self, frame, cards):
        """Read exposed hole-card strips even when YOLO emits no box.

        Use the reviewed layout at its reference width so small glyphs meet
        the symbol extractor's pixel-size requirements. Never invent a code
        from position, and do not duplicate an existing index detection.
        """
        from temporal_cards import overlap
        scale = frame.shape[1] / 1762
        canonical = cv2.resize(frame, (1762, round(frame.shape[0]/scale)))
        for slot, box in enumerate(([648,650,686,746], [688,662,736,760])):
            x1,y1,x2,y2 = box
            if y2 > canonical.shape[0]:
                continue
            bbox = [round(v*scale) for v in box]
            if any(overlap(bbox,c['bbox']) >= .2 for c in cards):
                continue
            image = canonical[y1:y2,x1:x2]
            # A black/green background or covered card is not an exposed index.
            hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
            if np.mean((hsv[:,:,1] < 65) & (hsv[:,:,2] > 180)) < .5:
                continue
            reading = self._symbol_reading(image)
            if reading is None:
                continue
            x1,y1,x2,y2 = bbox
            reading.update(domain='physical', group='card_index', bbox=bbox,
                           polygon=[[x1,y1],[x2,y1],[x2,y2],[x1,y2]],
                           decision_source='fixed_player_index_recovery',
                           recovered_hand_slot=slot, neural_confidence=None)
            cards.append(reading)

    def detect(self, frame):
        start = perf_counter()
        offset_x, offset_y = 0, 0
        image = frame
        if self.crop:
            height, width = frame.shape[:2]
            reference = getattr(self, 'crop_reference_size', None)
            # Table graphics scale uniformly with width. Extra bottom controls
            # must not move the board crop downwards.
            crop_height = height
            if reference is not None:
                if len(reference) != 2 or any(v <= 0 for v in reference):
                    raise ValueError('Invalid crop reference size')
                crop_height = reference[1] * width / reference[0]
            x1, y1, x2, y2 = [round(value * (width if i % 2 == 0 else crop_height))
                              for i, value in enumerate(self.crop)]
            if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
                raise ValueError('Model crop is outside the input image')
            image = frame[y1:y2, x1:x2]
            offset_x, offset_y = x1, y1
        primary = [offset_x, offset_y, offset_x+image.shape[1], offset_y+image.shape[0]]
        regions = [primary]
        outside_indices = []
        if self.profile == 'pokerstars':
            extra, outside_indices = additional_table_regions(frame, primary)
            regions += extra
        cards = []
        for ax, ay, bx, by in regions:
            image = frame[ay:by, ax:bx]
            blob, scale, left, top = letterbox(image)
            self.net.setInput(blob)
            proposed = decode_indices(self.net.forward(), self.names, image.shape, scale, left, top)
            for card in proposed:
                card['decision_source'] = 'model'
                # A confident network prediction can still be wrong (e.g.
                # 4S -> AS). Cross-check all PokerStars indices against the
                # existing high-threshold rank/suit references.
                if not card['accepted'] or self.profile == 'pokerstars':
                    x1, y1, x2, y2 = card['bbox']
                    reading = self._symbol_reading(image[y1:y2, x1:x2])
                    if reading:
                        card['neural_candidate'] = card['rank'] + card['suit']
                        card['neural_confidence'] = card['confidence']
                        card['symbol_corrected'] = card['neural_candidate'] != reading['card']
                        card.update(reading)
                card['bbox'] = [value + (ax if i % 2 == 0 else ay) for i, value in enumerate(card['bbox'])]
                card['polygon'] = [[x+ax, y+ay] for x, y in card['polygon']]
                cards.append(card)
        for x1, y1, x2, y2 in outside_indices:
            reading = self._symbol_reading(frame[y1:y2, x1:x2])
            if reading is None:
                # Exclude the next card's vertical border from an exposed strip.
                narrow_right = min(x2, x1+round((y2-y1)*.38))
                reading = self._symbol_reading(frame[y1:y2, x1:narrow_right])
                if reading:
                    x2 = narrow_right
            if reading:
                reading.update(domain='physical', group='card_index', neural_confidence=None,
                               bbox=[x1, y1, x2, y2],
                               polygon=[[x1,y1],[x2,y1],[x2,y2],[x1,y2]])
                cards.append(reading)
        if len(regions) > 1 and cards:
            boxes = [[c['bbox'][0], c['bbox'][1], c['bbox'][2]-c['bbox'][0], c['bbox'][3]-c['bbox'][1]] for c in cards]
            priority = [c['confidence'] + (1 if c['accepted'] and c['decision_source'] == 'model' else 0) for c in cards]
            kept = cv2.dnn.NMSBoxes(boxes, priority, .25, .45)
            cards = [cards[i] for i in np.asarray(kept).reshape(-1)]
        if self.profile == 'pokerstars':
            self._recover_player_indices(frame, cards)
        return {'scene': 'card_model', 'scene_score': None,
                'detector': 'lgd-cards-gen3' if self.profile == 'general' else 'pokerstars-finetuned-yolo11n',
                'profile': self.profile,
                'regions_analyzed': len(regions),
                'detection_kind': 'card_index', 'cards': cards,
                'processing_ms': round((perf_counter() - start) * 1000, 3)}

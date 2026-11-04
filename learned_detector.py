"""YOLO11 ONNX card-index detector, using the existing OpenCV CPU runtime."""
import json
from time import perf_counter
from card_detector import cv2, np
from download_model import verified_model_files


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
    def __init__(self):
        model, classes = verified_model_files()
        self.names = json.loads(classes.read_text(encoding='utf-8'))
        expected = {rank + suit for rank in ['A', 'J', 'Q', 'K', '10', *'23456789'] for suit in 'CDHS'}
        if len(self.names) != 52 or set(self.names) != expected:
            raise RuntimeError('La mappa delle classi del modello non contiene le 52 carte attese')
        self.net = cv2.dnn.readNetFromONNX(str(model))
        self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
        # opencv-python-headless uses the CPU; no Torch/Ultralytics dependency.

    def detect(self, frame):
        start = perf_counter()
        blob, scale, left, top = letterbox(frame)
        self.net.setInput(blob)
        output = self.net.forward()
        cards = decode_indices(output, self.names, frame.shape, scale, left, top)
        return {'scene': 'card_model', 'scene_score': None, 'detector': 'lgd-cards-gen3',
                'detection_kind': 'card_index', 'cards': cards,
                'processing_ms': round((perf_counter() - start) * 1000, 3)}

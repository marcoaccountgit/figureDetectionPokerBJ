"""Webcam acquisition and card detection independent of casino table positions."""
import os
from queue import Empty, Full, Queue
from threading import Event, Thread
from time import perf_counter

from card_detector import (Recognizer, choose_reading, clean_glyph, cv2, ink_color,
                           np, ordered_quad, polygon_overlap, stacked_index_symbols)


def camera_frames(index, sample_fps, duration):
    """A single latest-frame slot prevents a slow recognizer building a backlog."""
    latest = Queue(maxsize=1)
    stopped = Event()
    start = perf_counter()

    def publish(packet):
        try:
            latest.put_nowait(packet)
        except Full:
            try:
                latest.get_nowait()
            except Empty:
                pass
            latest.put_nowait(packet)

    def capture():
        cap = None
        try:
            backend = cv2.CAP_DSHOW if os.name == 'nt' else cv2.CAP_ANY
            cap = cv2.VideoCapture(index, backend)
            if not cap.isOpened():
                raise RuntimeError(
                    f'Impossibile aprire la webcam {index}. Chiudi le altre app che la usano, '
                    'verifica i permessi fotocamera di Windows oppure prova --camera 1.')
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            cap.set(cv2.CAP_PROP_FPS, 30)
            while not stopped.is_set():
                ok, frame = cap.read()
                if not ok or frame is None:
                    raise RuntimeError('La webcam non restituisce immagini: controlla il collegamento.')
                publish((perf_counter() - start, frame, None))
        except Exception as error:
            publish((0, None, error))
        finally:
            if cap is not None:
                cap.release()

    thread = Thread(target=capture, name='webcam-capture', daemon=True)
    thread.start()
    try:
        while duration is None or perf_counter() - start < duration:
            cycle = perf_counter()
            try:
                timestamp, frame, error = latest.get(timeout=5)
            except Empty as error:
                raise RuntimeError('Nessuna immagine dalla webcam entro 5 secondi.') from error
            if error is not None:
                raise error
            yield timestamp, frame
            stopped.wait(max(0, 1 / sample_fps - (perf_counter() - cycle)))
    finally:
        stopped.set()
        # The capture thread owns release(), avoiding release/read races.
        thread.join(timeout=1)


def card_quadrilaterals(frame):
    """Find card-shaped borders, including rounded cards on light backgrounds."""
    height, width = frame.shape[:2]
    scale = min(1, 960 / max(height, width))
    small = cv2.resize(frame, (round(width * scale), round(height * scale)))
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array([0, 0, 130]), np.array([179, 95, 255]))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    light_contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 35, 100)
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    edge_contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    contours = list(light_contours) + list(edge_contours)
    found = []
    for contour in sorted(contours, key=cv2.contourArea, reverse=True):
        area = cv2.contourArea(contour)
        if not .003 * small.shape[0] * small.shape[1] <= area <= .85 * small.shape[0] * small.shape[1]:
            continue
        hull = cv2.convexHull(contour)
        perimeter = cv2.arcLength(hull, True)
        polygon = None
        for tolerance in (.02, .03, .04, .05):
            approximation = cv2.approxPolyDP(hull, tolerance * perimeter, True)
            if len(approximation) == 4 and cv2.isContourConvex(approximation):
                polygon = approximation
                break
        if polygon is None:
            rectangle = cv2.minAreaRect(hull)
            rectangle_area = rectangle[1][0] * rectangle[1][1]
            if rectangle_area <= 0 or cv2.contourArea(hull) / rectangle_area < .88:
                continue
            polygon = cv2.boxPoints(rectangle)
        elif cv2.contourArea(polygon) < .85 * cv2.contourArea(hull):
            # Four points approximating an ellipse are not a card border.
            continue
        points = ordered_quad(polygon)
        if (points.min() < 3 or points[:, 0].max() >= small.shape[1]-3
                or points[:, 1].max() >= small.shape[0]-3):
            continue
        edges = np.linalg.norm(points - np.roll(points, -1, axis=0), axis=1)
        card_width, card_height = (edges[0] + edges[2]) / 2, (edges[1] + edges[3]) / 2
        if card_width > card_height:
            points = np.roll(points, -1, axis=0)
            card_width, card_height = card_height, card_width
        if card_width < 24 or not .5 <= card_width / card_height <= .85:
            continue
        points /= scale
        if any(polygon_overlap(points, existing) > .65 for existing in found):
            continue
        found.append(points)
    return found


def corner_symbols(card):
    """Read the two vertically stacked symbols in a standard French card index."""
    # Cards have already been rectified to 200 x 280, upright.
    return stacked_index_symbols(card[6:125, 6:48])


class CameraDetector:
    def __init__(self, assets=None, layout='corner'):
        from pathlib import Path
        if layout not in ('corner', 'casino'):
            raise ValueError('Card layout must be corner or casino')
        self.layout = layout
        self.recognizer = Recognizer(assets or Path(__file__).parent / 'assets', 'physical')

    def detect(self, frame):
        start = perf_counter()
        cards = []
        target = np.float32([[0, 0], [199, 0], [199, 279], [0, 279]])
        for polygon in card_quadrilaterals(frame):
            transform = cv2.getPerspectiveTransform(polygon, target)
            if abs(np.linalg.det(transform)) < 1e-9:
                continue
            card = cv2.warpPerspective(frame, transform, (200, 280))
            if self.layout == 'casino':
                result = self.recognizer.classify(card)
            else:
                options = []
                for view in (card, cv2.rotate(card, cv2.ROTATE_180)):
                    symbols = corner_symbols(view)
                    if symbols is not None:
                        options.append(self.recognizer.classify_symbols(*symbols))
                if options:
                    result = choose_reading(options)
                else:
                    result = {'accepted': False, 'card': None,
                              'rejection_reason': 'corner_index_not_readable'}
            points = np.rint(polygon).astype(int).tolist()
            result.update(domain='physical', group='webcam', polygon=points,
                          bbox=[min(p[0] for p in points), min(p[1] for p in points),
                                max(p[0] for p in points), max(p[1] for p in points)])
            cards.append(result)
        return {'scene': 'webcam', 'scene_score': None, 'cards': cards,
                'processing_ms': round((perf_counter() - start) * 1000, 3)}

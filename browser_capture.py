"""Local browser-tab capture UI; frames stay on the loopback interface."""
import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import secrets
import threading
from time import perf_counter
import webbrowser

from card_detector import cv2, np
from learned_detector import LearnedCardDetector
from temporal_cards import TemporalCards
from table_layout import arrange_table
from capture_alignment import align_capture, restore_coordinates
from opponent_detector import OpponentDetector, OpponentTracker
from hand_counter import HandCounter, player_card_presence

ROOT = Path(__file__).resolve().parent
MAX_FRAME = 12 * 1024 * 1024


def live_confirmation():
    return TemporalCards(required_observations=5, min_span=.3, max_age=2,
                         window_frames=12, consecutive=True)


def make_handler(detector, token):
    lock = threading.Lock()
    opponents = OpponentDetector()
    state = {'session': None, 'viewport': None, 'temporal': live_confirmation(),
             'opponents': OpponentTracker(), 'hands': HandCounter()}

    class Handler(BaseHTTPRequestHandler):
        def reply(self, status, body, content_type='application/json'):
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path != '/?token=' + token:
                self.reply(404, b'{}')
                return
            self.reply(200, (ROOT / 'browser_ui.html').read_bytes(), 'text/html; charset=utf-8')

        def do_POST(self):
            if self.path != '/frame' or not secrets.compare_digest(self.headers.get('X-Capture-Token', ''), token):
                self.reply(403, b'{}')
                return
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= MAX_FRAME:
                    self.reply(413, b'{}')
                    return
                frame = cv2.imdecode(np.frombuffer(self.rfile.read(size), np.uint8), cv2.IMREAD_COLOR)
                if frame is None or frame.shape[0] * frame.shape[1] > 16000000:
                    raise ValueError('Fotogramma non valido o troppo grande')
                session = self.headers.get('X-Capture-Session', '')
                if not session or len(session) > 100:
                    raise ValueError('Sessione non valida')
                with lock:
                    game, viewport = align_capture(frame)
                    if state['session'] != session:
                        state.update(session=session, viewport=viewport, temporal=live_confirmation(),
                                     opponents=OpponentTracker(), hands=HandCounter())
                    elif state['viewport'] != viewport:
                        state.update(viewport=viewport, temporal=live_confirmation(), opponents=OpponentTracker())
                        state['hands'].reset_observations()
                    result = detector.detect(game)
                    raw_hand = arrange_table(result, game.shape)['player_hand']
                    result = state['temporal'].update(result, perf_counter(), game.shape)
                    result = arrange_table(result, game.shape)
                    hand_start = perf_counter()
                    result['hand_cycle'] = state['hands'].update(player_card_presence(game), raw_hand, perf_counter())
                    if result['hand_cycle']['started'] or result['hand_cycle']['ended']:
                        state['opponents'] = OpponentTracker()
                    if result['hand_cycle']['ended']:
                        state['temporal'] = live_confirmation()
                    result['hand_processing_ms'] = round((perf_counter()-hand_start)*1000, 3)
                    opponent_start = perf_counter()
                    result['opponents'] = state['opponents'].update(opponents.detect(game), perf_counter(), result['player_hand'])
                    result['opponent_processing_ms'] = round((perf_counter()-opponent_start)*1000, 3)
                    result['processing_ms'] = round(result['processing_ms']+result['opponent_processing_ms']+result['hand_processing_ms'], 3)
                    result = restore_coordinates(result, viewport, frame.shape)
                self.reply(200, json.dumps(result, allow_nan=False).encode())
            except (ValueError, RuntimeError, cv2.error) as error:
                self.reply(400, json.dumps({'error': str(error)}).encode())

        def log_message(self, format, *args):
            pass

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=0)
    parser.add_argument('--no-open', action='store_true')
    args = parser.parse_args()
    detector = LearnedCardDetector(profile='pokerstars')
    token = secrets.token_urlsafe(32)
    server = ThreadingHTTPServer(('127.0.0.1', args.port), make_handler(detector, token))
    url = f'http://127.0.0.1:{server.server_port}/?token={token}'
    print(f'Pannello PokerStars: {url}\nLascia aperta questa console. Ctrl+C per chiudere.', flush=True)
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()

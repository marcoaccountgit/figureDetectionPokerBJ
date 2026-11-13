"""Local browser-tab capture UI; frames stay on the loopback interface."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import secrets
import threading
from time import perf_counter
import webbrowser

from card_detector import cv2, np
from learned_detector import LearnedCardDetector, TableCardDetector
from temporal_cards import TemporalCards, HandCardMemory
from table_layout import arrange_table
from capture_alignment import CaptureAligner, restore_coordinates
from opponent_detector import OpponentDetector, OpponentTracker
from hand_counter import HandCounter, player_card_presence
from poker_advice import analyze_decision
from live_card_cache import card_inference_needed, unconfirmed_card_frame
from poker_equity import normalize_card, card_code

ROOT = Path(__file__).resolve().parent
MAX_FRAME = 12 * 1024 * 1024


def live_confirmation():
    return TemporalCards(required_observations=5, min_span=.3, max_age=8,
                         window_frames=12, consecutive=True, max_gap=2)


def make_handler(detector, token, table_observer=None, equity_service=None):
    lock = threading.Lock()
    opponents = OpponentDetector()
    state = {'session': None, 'viewport': None, 'temporal': live_confirmation(),
             'opponents': OpponentTracker(), 'hands': HandCounter(), 'dealt_seats': [], 'aligner': None,
             'profile':'pokerstars', 'card_memory': HandCardMemory(), 'overrides': {},
             'latest_frame': None, 'latest_result': None, 'force_start': False}

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
            if self.path == '/intervention' and secrets.compare_digest(self.headers.get('X-Capture-Token', ''), token):
                self.intervention()
                return
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
                    if state['session'] != session:
                        state['aligner'] = CaptureAligner()
                    game, viewport = state['aligner'].align(frame)
                    profile = state['aligner'].profile
                    if state['session'] != session:
                        state.update(session=session, viewport=viewport, temporal=live_confirmation(),
                                     opponents=OpponentTracker(), hands=HandCounter(), dealt_seats=[], card_memory=HandCardMemory(), overrides={}, force_start=False)
                    elif state['viewport'] != viewport or state['profile'] != profile:
                        old_width = state['viewport'][2] - state['viewport'][0]
                        state['card_memory'].rescale(game.shape[1] / old_width)
                        state.update(viewport=viewport, temporal=live_confirmation(), opponents=OpponentTracker())
                        state['hands'].reset_observations()
                        if state['profile'] != profile:
                            state.update(hands=HandCounter(),dealt_seats=[], card_memory=HandCardMemory(), overrides={})
                    state['profile'] = profile
                    if isinstance(detector,TableCardDetector):detector.profile=profile
                    aligned = state['aligner'].alignment_ready
                    presence_start = perf_counter()
                    presence=player_card_presence(game,profile) if aligned else [dict(present=None),dict(present=None)]
                    needed, cache_info = card_inference_needed(
                        game, state['card_memory'], state['hands'].active, presence, profile)
                    presence_ms = (perf_counter() - presence_start) * 1000
                    if aligned and needed:
                        recognition_frame = unconfirmed_card_frame(
                            game, state['card_memory'], state['hands'].active, profile, cache_info)
                        result = detector.detect(recognition_frame)
                    else:
                        result = dict(cards=[], processing_ms=0, scene='card_memory' if aligned else 'alignment_lost')
                    result['card_cache'] = cache_info
                    result['card_revalidation'] = cache_info.get('revalidate', False)
                    result['card_cache']['probe_ms'] = round(presence_ms, 3)
                    result['table_profile'] = profile
                    result['alignment_ready'] = aligned
                    result = arrange_table(result, game.shape)
                    raw_hand = result['player_hand']
                    hand_start = perf_counter()
                    result['hand_cycle'] = state['hands'].update(
                        presence, raw_hand, perf_counter(), board_cleared=cache_info.get('board_cleared', False))
                    result['hand_cycle']['board_cleared'] = cache_info.get('board_cleared', False)
                    if state['force_start']:
                        result['hand_cycle'].update(started=True, active=True)
                        state['force_start'] = False
                    if result['hand_cycle']['started']:
                        state['overrides'].clear()
                    if result['hand_cycle']['ended']:
                        state['overrides'].clear()
                    if result['hand_cycle']['started'] and result['hand_cycle']['count'] > 1:
                        state['temporal'] = live_confirmation()
                    result = state['temporal'].update(result, perf_counter(), game.shape)
                    result = state['card_memory'].update(result, result['hand_cycle'])
                    result = arrange_table(result, game.shape)
                    state['card_memory'].invalidate_conflicts(result.get('card_conflicts', []))
                    for (group, slot), value in state['overrides'].items():
                        result[group][slot].update(card=value, accepted=True, detected=True, manual=True)
                        field = 'hand_slot' if group == 'player_hand' else 'board_slot'
                        for card in result['cards']:
                            if card.get('table_group') == group and card.get(field) == slot:
                                card.update(card=value, accepted=True, manual=True)
                    result['hand_cycle']['recognized_cards'] = sum(c['accepted'] for c in result['player_hand'])
                    if result['hand_cycle']['started']:
                        state['opponents'] = OpponentTracker()
                    result['hand_processing_ms'] = round(presence_ms+(perf_counter()-hand_start)*1000, 3)
                    opponent_start = perf_counter()
                    visible_y = (max(0,-viewport[1])*1762/game.shape[1],
                                 (min(frame.shape[0],viewport[3])-viewport[1])*1762/game.shape[1])
                    visible_x = (max(0,-viewport[0])*1762/game.shape[1],
                                 (min(frame.shape[1],viewport[2])-viewport[0])*1762/game.shape[1])
                    seats=opponents.detect(game,visible_y,profile,visible_x)
                    if not aligned:seats=[dict(s,present=None,bbox=None,reason='alignment_lost') for s in seats]
                    result['opponents'] = state['opponents'].update(seats, perf_counter(), result['player_hand'])
                    result['opponent_processing_ms'] = round((perf_counter()-opponent_start)*1000, 3)
                    result['processing_ms'] = round(result['processing_ms']+result['opponent_processing_ms']+result['hand_processing_ms'], 3)
                    if result['hand_cycle']['started']:
                        state['dealt_seats'] = ['hero']+[s['seat'] for s in result['opponents']['seats'] if s['present'] is True]
                    if table_observer is not None:
                        board_count = sum(c['detected'] for c in result['board'])
                        context = dict(capture_session=session,viewport=viewport,
                                       hand_id=result['hand_cycle']['count'],active=result['hand_cycle']['active'],profile=profile,
                                       ended=result['hand_cycle']['ended'],dealt_seats=list(state['dealt_seats']),
                                       street={0:'preflop',3:'flop',4:'turn',5:'river'}.get(board_count,'unknown'))
                        result['table_observation'] = (table_observer.submit(game, context) if aligned else
                                                       dict(status='pending',hand_id=context['hand_id']))
                    if equity_service is not None:
                        manual = self.headers.get('X-Equity-Opponents', '')
                        seed = self.headers.get('X-Equity-Seed', '')
                        result['equity'] = equity_service.submit(
                            result, session, profile=self.headers.get('X-Equity-Profile', 'FAST'),
                            manual_opponents=int(manual) if manual else None,
                            random_seed=int(seed) if seed else None,
                            **({'bet_model': True} if self.headers.get('X-Equity-Bet-Model') == '1' else {}))
                        result['poker_advice'] = analyze_decision(
                            result['equity'],result.get('table_observation'),result['hand_cycle']['count'])
                        scenario = result['equity'].get('bet_scenario')
                        if scenario is not None:
                            result['poker_advice_bets'] = analyze_decision(
                                scenario, result.get('table_observation'), result['hand_cycle']['count'])
                    result = restore_coordinates(result, viewport, frame.shape)
                    result['capture_alignment']['vertical_anchor'] = state['aligner'].last_anchor
                    result['capture_alignment']['ready'] = aligned
                    result['capture_alignment']['profile'] = profile
                    state['latest_frame'] = frame.copy()
                    state['latest_result'] = deepcopy(result)
                self.reply(200, json.dumps(result, allow_nan=False).encode())
            except (ValueError, RuntimeError, cv2.error) as error:
                self.reply(400, json.dumps({'error': str(error)}).encode())

        def intervention(self):
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 4096:
                    raise ValueError('Richiesta non valida')
                action = json.loads(self.rfile.read(size))
                if not isinstance(action, dict):
                    raise ValueError('Intervento non valido')
                with lock:
                    if (state['latest_result'] is None or action.get('session') != state['session']
                            or action.get('hand_id') != state['hands'].count):
                        raise ValueError('La mano è cambiata: ripeti dopo la prossima lettura')
                    kind = action.get('kind')
                    if kind == 'card':
                        group, slot = action.get('group'), action.get('slot')
                        if group not in ('board', 'player_hand') or type(slot) is not int or not 0 <= slot < (5 if group == 'board' else 2):
                            raise ValueError('Posizione della carta non valida')
                        value = card_code(normalize_card(action.get('card'))).upper()
                        for other_group in ('board', 'player_hand'):
                            for other_slot, other in enumerate(state['latest_result'][other_group]):
                                if (other_group, other_slot) == (group, slot):
                                    continue
                                if other.get('accepted') and other.get('card') and normalize_card(other['card']) == normalize_card(value):
                                    raise ValueError('Questa carta è già presente in un altro posto: correggi prima il duplicato.')
                        action['card'] = value
                    elif kind != 'new_hand':
                        raise ValueError('Intervento non valido')
                    folder = ROOT / 'artifacts' / 'manual-interventions' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '-' + secrets.token_hex(3))
                    folder.mkdir(parents=True)
                    if not cv2.imwrite(str(folder / 'screenshot.png'), state['latest_frame']):
                        raise OSError('Salvataggio screenshot non riuscito')
                    (folder / 'analysis.json').write_text(json.dumps(dict(
                        timestamp=datetime.now(timezone.utc).isoformat(), action=action,
                        before=state['latest_result'], overrides=[dict(group=g, slot=s, card=c) for (g,s),c in state['overrides'].items()]
                    ), ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
                    if kind == 'card':
                        state['overrides'][(group, slot)] = value
                    else:
                        state['hands'].count += 1
                        state['hands'].active = True
                        state['hands'].reset_observations()
                        state.update(temporal=live_confirmation(), card_memory=HandCardMemory(),
                                     opponents=OpponentTracker(), dealt_seats=[], overrides={}, force_start=True)
                self.reply(200, json.dumps(dict(saved=str(folder.relative_to(ROOT)))).encode())
            except (ValueError, TypeError, OSError) as error:
                self.reply(400, json.dumps(dict(error=str(error))).encode())

        def log_message(self, format, *args):
            pass

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=0)
    parser.add_argument('--no-open', action='store_true')
    args = parser.parse_args()
    detector = TableCardDetector()
    from table_observer import TableObservationService
    table_observer = TableObservationService()
    from equity_service import EquityService
    equity_service = EquityService()
    token = secrets.token_urlsafe(32)
    server = ThreadingHTTPServer(('127.0.0.1', args.port), make_handler(detector, token, table_observer, equity_service))
    url = f'http://127.0.0.1:{server.server_port}/?token={token}'
    print(f'Pannello PokerStars: {url}\nLascia aperta questa console. Ctrl+C per chiudere.', flush=True)
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        equity_service.close()
        table_observer.close()
        server.server_close()


if __name__ == '__main__':
    main()

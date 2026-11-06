"""Confirmed OCR adapter and latest-state-only multiprocessing equity service."""
from collections import OrderedDict
import multiprocessing as mp
from queue import Empty, Full
from time import monotonic

from poker_equity import PROFILES, calculate_equity, card_code, validate


class OCRGameState:
    """Never treat a disappearing board as a new hand within the same cycle."""
    def __init__(self):
        self.identity = None
        self.board_floor = 0
        self.hero = None
        self.board = ()
        self.closed = False

    def update(self, result, session, manual_opponents=None):
        cycle = result.get('hand_cycle', {})
        identity = (session, cycle.get('count'),result.get('table_profile','pokerstars'))
        if identity != self.identity:
            self.identity, self.board_floor, self.hero, self.board = identity, 0, None, ()
            self.closed = False
        if cycle.get('ended'):
            self.closed = True
        if self.closed:
            raise ValueError('Mano terminata: in attesa delle nuove carte')
        hand = result.get('player_hand', [])
        slots = result.get('board', [])
        # Even partial evidence of a board prevents a later missing frame from
        # becoming preflop. Invalid identities must not permanently lock a street.
        if any(c.get('detected') or c.get('accepted') for c in slots):
            self.board_floor = max(self.board_floor, 1)
        if len(hand) != 2 or not all(c.get('accepted') and c.get('card') for c in hand):
            raise ValueError('Carte personali non ancora confermate')
        if len(slots) != 5:
            raise ValueError('Board incompleto')
        # A detected but unconfirmed card is never an empty slot.
        if any(c.get('detected') and not c.get('accepted') for c in slots):
            raise ValueError('Conferma delle carte comuni in corso')
        visible = [c for c in slots if c.get('accepted')]
        count = len(visible)
        if count < self.board_floor or any(not slots[i].get('accepted') for i in range(count)):
            raise ValueError('Board transitorio: attesa della lettura completa')
        opponents = result.get('opponents', {})
        number = manual_opponents if manual_opponents is not None else opponents.get('count')
        if manual_opponents is None and opponents.get('pending', True):
            raise ValueError('Numero di avversari non confermato; disponibile input manuale')
        maximum = opponents.get('max_opponents',
                                8 if result.get('table_profile')=='pokerstars-nine' else 5)
        if type(maximum) is not int or not 1 <= maximum <= 9:
            raise ValueError('Capienza del tavolo non valida: attesi da 2 a 10 posti')
        hero, board = validate([c['card'] for c in hand], [c['card'] for c in visible], number, maximum)
        self.board_floor = max(self.board_floor, count)
        # Confirmed corrections trigger a new key; only the physical cycle resets
        # the minimum board size. Missing cards never become invented runouts.
        self.hero, self.board = hero, board
        return dict(hero_cards=[card_code(c) for c in hero], community_cards=[card_code(c) for c in board],
                    opponents_count=number, max_opponents=maximum)


def _worker(requests, responses, generation):
    while True:
        item = requests.get()
        if item is None:
            return
        version, kwargs = item
        def send(result):
            if generation.value == version:
                try:
                    responses.put_nowait((version, result))
                except Full:
                    pass
        try:
            result = calculate_equity(**kwargs, cancelled=lambda: generation.value != version, progress=send)
            if result is not None:
                # Final response must not be dropped behind intermediate progress.
                responses.put((version, result), timeout=2)
        except Exception as error:
            send(dict(status='error', message=str(error)))


class EquityService:
    def __init__(self, debounce=.25, cache_size=32):
        self.adapter = OCRGameState()
        self.debounce, self.cache_size = debounce, cache_size
        self.cache = OrderedDict()
        self.key = None
        self.since = 0
        self.result = None
        self.sent = False
        self.process = None
        self.context = mp.get_context('spawn')
        self.generation = self.context.Value('q', 0)
        self.requests = self.context.Queue(maxsize=1)
        self.responses = self.context.Queue(maxsize=8)

    def _invalidate(self):
        self.generation.value += 1
        self.result, self.sent = None, False

    def submit(self, result, session, profile='FAST', manual_opponents=None, random_seed=None):
        try:
            if result.get('alignment_ready') is False:
                raise ValueError('Allineamento del tavolo in corso: probabilità sospese fino alla conferma dei riferimenti')
            if profile not in PROFILES:
                raise ValueError('Profilo equity non valido')
            kwargs = self.adapter.update(result, session, manual_opponents)
            kwargs.update(simulations=PROFILES[profile], random_seed=random_seed)
        except ValueError as error:
            if self.key is not None:
                self._invalidate()
                self.key = None
            return dict(status='waiting', message=str(error))
        key = (self.adapter.identity, tuple(sorted(kwargs['hero_cards'])), tuple(kwargs['community_cards']),
               kwargs['opponents_count'], profile, random_seed)
        if key != self.key:
            self._invalidate()
            self.key, self.since = key, monotonic()
        while True:
            try:
                version, response = self.responses.get_nowait()
            except Empty:
                break
            if version == self.generation.value:
                self.result = response
                if response.get('complete'):
                    self.cache[key] = response
                    self.cache.move_to_end(key)
                    while len(self.cache) > self.cache_size:
                        self.cache.popitem(last=False)
        if key in self.cache:
            return dict(self.cache[key], cached=True)
        if self.sent and self.process is not None and not self.process.is_alive():
            self.result = None
            return dict(status='error', message='Processo equity terminato; riavviare il servizio')
        # Hole cards already passed temporal confirmation. Do not add a second
        # delay to the first preflop estimate while waiting for a physical cycle.
        delay = self.debounce if kwargs['community_cards'] else 0
        if not self.sent and monotonic()-self.since >= delay:
            if self.process is None:
                self.process = self.context.Process(target=_worker, args=(self.requests, self.responses, self.generation), daemon=True)
                self.process.start()
            if not self.process.is_alive():
                return dict(status='error', message='Processo equity terminato; riavviare il servizio')
            try:
                self.requests.put_nowait((self.generation.value, kwargs))
                self.sent = True
            except Full:
                # The queued obsolete request is cancelled by its generation.
                pass
        return self.result or dict(status='calculating' if self.sent else 'debouncing',
                                   message='Calcolo locale in corso' if self.sent else 'Attesa di uno stato stabile')

    def close(self):
        self._invalidate()
        if self.process:
            try:
                self.requests.put(None, timeout=.5)
            except Full:
                pass
            self.process.join(timeout=3)
            if self.process.is_alive():
                self.process.terminate()
                self.process.join(timeout=2)
        self.requests.close()
        self.responses.close()

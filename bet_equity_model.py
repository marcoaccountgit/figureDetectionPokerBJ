"""Versioned, fixed assumptions about visible commitments; no player profiles."""
from math import isfinite

VERSION = 'visible-commitment-v1'
WEIGHTS = (1, 3, 6, 10)


def amount(value):
    if not isinstance(value, dict):
        return None
    n, unit = value.get('value'), value.get('unit')
    if type(n) not in (int, float) or not isfinite(n) or n < 0 or unit not in ('BB', 'EUR', 'CHIPS'):
        return None
    return n, unit


def fixed_bet_model(result, opponents_count, manual_opponents=None):
    """Use confirmed current-street commitments divided by the current total pot.

    The total includes wagers; ratios are NOT advertised as bet / prior pot.
    Missing commitments remain uniform. No names, tendencies, previous hands,
    future actions, or offered raise buttons enter this model.
    """
    model = dict(status='waiting', version=VERSION, message='', seats=[], strengths=[],
                 assumptions='Ipotesi fissa, non calibrata: il quarto circa delle combinazioni più forti '
                             'riceve peso 3, 6 o 10; le altre mantengono peso 1. '
                             'Nessun profilo dei giocatori o previsione delle mosse.')
    table = result.get('table_observation') or {}
    board = result.get('board', [])
    count = sum(bool(c.get('accepted')) for c in board)
    street = {0: 'preflop', 3: 'flop', 4: 'turn', 5: 'river'}.get(count)
    if (table.get('status') != 'ready' or table.get('age_ms', 0) > 2000
            or table.get('hand_id') != result.get('hand_cycle', {}).get('count')
            or table.get('street') != street):
        model['message'] = 'Attesa di piatto e puntate confermati nella stessa mano e fase.'
        return model
    if table.get('side_pots'):
        model['message'] = 'Piatti secondari: confronto del modello non disponibile.'
        return model
    pot = amount(table.get('pot'))
    if pot is None or pot[0] <= 0:
        model['message'] = 'Piatto totale non confermato: le puntate non vengono normalizzate.'
        return model
    observed = result.get('opponents') or {}
    seats = [s for s in observed.get('seats', []) if s.get('in_hand') is True and s.get('confirmed')]
    if (observed.get('pending', True) or len(seats) != opponents_count
            or len({s['seat'] for s in seats}) != len(seats)
            or manual_opponents is not None and observed.get('count') != manual_opponents):
        model['message'] = 'Servono i posti avversari confermati; il solo conteggio manuale non li identifica.'
        return model
    rows = {s['seat']: s for s in table.get('seats', [])}
    total_visible = 0
    for row in rows.values():
        wager = amount(row.get('wager'))
        if wager is not None:
            if wager[1] != pot[1]:
                model['message'] = 'Unità delle puntate e del piatto non coerenti.'
                return model
            total_visible += wager[0]
    if total_visible > pot[0] + 1e-6:
        model['message'] = 'Puntate visibili superiori al piatto totale: attesa di importi coerenti.'
        return model
    for seat in sorted(seats, key=lambda s: s['seat']):
        row = rows.get(seat['seat'], {})
        wager = amount(row.get('wager'))
        level, ratio = 0, None
        note = 'Importo non confermato: distribuzione casuale.'
        if wager is not None and wager[0] > 0:
            ratio = wager[0] / pot[0]
            # A blind is not evidence of a selected range. Preflop requires
            # an explicit confirmed raise/bet label, not merely posted chips.
            action = row.get('action')
            if street != 'preflop' or action in ('bet', 'raise', 'all_in'):
                level = 1 if ratio <= .15 else 2 if ratio <= 1/3 else 3
                note = 'Impegno confermato / piatto totale attuale, puntate già incluse.'
            else:
                note = 'Preflop senza rilancio esplicito: bui e chiamate restano casuali.'
        model['strengths'].append(level)
        model['seats'].append(dict(seat=seat['seat'], label=seat.get('label', seat['seat']),
                                   commitment=wager[0] if wager else None, ratio=ratio,
                                   strong_weight=WEIGHTS[level], note=note))
    model.update(status='ready', pot=pot[0], unit=pot[1], street=street,
                 message='Confronto sotto ipotesi fissa sulle puntate osservate.' if any(model['strengths']) else
                         'Nessuna puntata utilizzabile: il modello coincide con le mani casuali.')
    return model

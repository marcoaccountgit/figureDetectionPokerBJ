"""Explain equity and pot odds locally. No actions or opponent predictions."""
from math import isfinite


def _amount(amount):
    if not isinstance(amount, dict):
        return None
    value, unit = amount.get('value'), amount.get('unit')
    if type(value) not in (int, float) or not isfinite(value) or value < 0 or unit not in ('BB', 'EUR','CHIPS'):
        return None
    return value, unit


def analyze_decision(equity, table, hand_id):
    """Conditional call-vs-fold EV assuming a common pot and no further costs.

    table.pot already includes current bets. Only explicit, temporally confirmed
    call-button amounts are costs; wagers/contribution are never substituted.
    """
    limits = [
        'Confronto numerico con carte avversarie casuali, senza valutazioni sul comportamento.',
        'Ipotesi: piatto comune interamente contendibile, senza commissioni o costi successivi.',
        'Piatti secondari e diritto a incassare tutto il piatto non sono verificati automaticamente.',
        'I pulsanti visibili possono essere opzioni preselezionabili: non certificano che sia il tuo turno.',
    ]
    result = dict(status='waiting', title='Valutazione in attesa', message='', limits=limits, factors=[])
    if not equity or equity.get('status') != 'ready':
        result['message'] = 'Servono entrambe le carte confermate e una stima di equità disponibile.'
        return result
    metrics = equity['metrics']
    for key, label in [('equity','Quota attesa del piatto'),('win','Vittoria esclusiva finale'),
                       ('tie','Pareggio finale al primo posto'),('lose','Sconfitta finale'),
                       ('current_strength','Già davanti a tutti'),('currently_behind','Già dietro ad almeno uno'),
                       ('current_tie','Pareggio attuale al primo posto'),
                       ('category_improvement','Miglioramento della categoria'),
                       ('same_category_value_improvement','Valore migliore nella stessa categoria'),
                       ('kicker_improvement','Carte di spareggio migliori')]:
        if metrics.get(key) is not None:
            result['factors'].append(dict(label=label, value=metrics[key]['value']))
    result['notes'] = [
        'Le probabilità si leggono insieme: non vengono sommate o mediate per creare un punteggio.',
        'Migliorare la categoria o le carte di spareggio non garantisce di superare gli avversari.',
        'Le categorie finali possibili sono mostrate nella distribuzione sottostante.',
    ]
    if equity.get('street') != 'river':
        result['limits'].append('Equità fino al river: pagare adesso potrebbe non bastare per vedere tutte le carte.')
    if equity.get('opponents_count', 0) > 1:
        result['limits'].append('Più avversari: altri giocatori potrebbero ancora chiamare o rilanciare.')
    if not table or table.get('status') != 'ready' or table.get('age_ms', 0) > 2000:
        result['message'] = 'Lettura del piatto e dei pulsanti non disponibile o scaduta.'
        return result
    if table.get('hand_id') != hand_id or table.get('street') != equity.get('street'):
        result['message'] = 'Attesa di importi e pulsanti appartenenti alla stessa mano e fase delle carte.'
        return result
    actions = table.get('available_actions_confirmed')
    if not actions:
        result['message'] = 'Attesa della conferma visiva dei pulsanti disponibili: non è ancora verificato che tocchi a te.'
        return result
    calls = [a for a in actions if a.get('action') == 'call']
    checks = [a for a in actions if a.get('action') == 'check']
    if not calls and checks:
        result.update(status='free_check', title='Puoi passare il turno senza pagare',
                      message='Il pulsante di controllo è visibile e confermato. Non serve aggiungere fiches per questa azione; la sola equità non stabilisce se puntare sia meglio.')
        return result
    if len(calls) != 1 or checks:
        result['message'] = 'Costo per vedere assente o pulsanti ambigui: nessun suggerimento di chiamata.'
        return result
    pot, call = _amount(table.get('pot')), _amount(calls[0].get('amount'))
    if not pot or not call or pot[0] <= 0 or call[0] <= 0:
        result['message'] = 'Servono il piatto totale e il costo aggiuntivo per vedere, entrambi leggibili e positivi.'
        return result
    if pot[1] != call[1]:
        result['message'] = 'Piatto e chiamata hanno unità diverse: confronto non disponibile.'
        return result
    hero = next((s for s in table.get('seats', []) if s.get('seat') == 'hero'), {})
    stack = _amount(hero.get('stack'))
    if stack and (stack[1] != call[1] or call[0] > stack[0]):
        result['message'] = 'Chiamata e stack non coerenti o possibile all-in parziale: serve verificare i piatti secondari.'
        return result
    if table.get('side_pots'):
        result['message'] = 'Piatti secondari segnalati: il modello del piatto comune non è applicabile.'
        return result
    final_pot = pot[0]+call[0]
    threshold = call[0]/final_pot
    e = metrics['equity']
    lower, upper = e['ci95']
    if lower > threshold:
        signal, title = 'call_model', 'Suggerimento probabilistico: VEDI'
        message = 'Anche il limite inferiore dell’equità supera la soglia richiesta dal costo della chiamata.'
    elif upper < threshold:
        signal, title = 'fold_model', 'Suggerimento probabilistico: PASSA'
        message = 'Anche il limite superiore dell’equità è sotto la soglia: il costo è troppo alto nel confronto semplificato.'
    else:
        signal, title = 'uncertain', 'Suggerimento probabilistico: MARGINE INCERTO'
        message = 'La soglia richiesta attraversa l’intervallo della stima. Più simulazioni possono ridurre solo l’errore Monte Carlo.'
    result.update(status='conditional', signal=signal, title=title, message=message,
                  unit=pot[1], pot_before_call=pot[0], call_cost=call[0], pot_after_call=final_pot,
                  required_equity=threshold, equity=e['value'], equity_ci95=[lower,upper],
                  margin=e['value']-threshold, expected_value=e['value']*final_pot-call[0],
                  expected_value_ci95=[lower*final_pot-call[0],upper*final_pot-call[0]],
                  complete=equity.get('complete',False))
    return result

"""Local Hold'em evaluator and uniform, joint multiway equity sampling.

No OCR, network, betting rules or opponent behaviour belong in this module.
Scores are lexicographically ordered tuples: category followed by tie breakers.
"""
from collections import Counter
from functools import lru_cache
from itertools import combinations
from math import comb, sqrt
import random
from time import perf_counter

RANKS = '23456789TJQKA'
SUITS = 'cdhs'
CATEGORIES = ('High Card', 'One Pair', 'Two Pair', 'Three of a Kind',
              'Straight', 'Flush', 'Full House', 'Four of a Kind', 'Straight Flush')
PROFILES = {'FAST': 5000, 'BALANCED': 50000, 'ACCURATE': 250000}


def normalize_card(value):
    if not isinstance(value, str):
        raise ValueError('Carta mancante o non riconosciuta')
    value = value.strip().replace('10', 'T')
    for symbol, suit in zip('♣♦♥♠', 'cdhs'):
        value = value.replace(symbol, suit)
    if len(value) != 2 or value[0].upper() not in RANKS or value[1].lower() not in SUITS:
        raise ValueError('Carta non valida: ' + repr(value))
    return RANKS.index(value[0].upper())*4 + SUITS.index(value[1].lower())


def card_code(card):
    return RANKS[card//4] + SUITS[card % 4]


def validate(hero_cards, community_cards, opponents_count, max_opponents=9):
    if not isinstance(hero_cards, (list, tuple)) or not isinstance(community_cards, (list, tuple)):
        raise ValueError('Carte personali e comuni devono essere sequenze esplicite')
    if type(max_opponents) is not int or not 1 <= max_opponents <= 9:
        raise ValueError('Limite del tavolo non valido')
    hero = tuple(normalize_card(c) for c in hero_cards)
    board = tuple(normalize_card(c) for c in community_cards)
    if len(hero) != 2 or len(board) not in (0, 3, 4, 5):
        raise ValueError('Servono due carte personali e 0, 3, 4 o 5 carte comuni')
    if len(set(hero+board)) != len(hero+board):
        raise ValueError('Carte duplicate')
    if type(opponents_count) is not int or not 1 <= opponents_count <= max_opponents:
        raise ValueError(f'Avversari richiesti: da 1 a {max_opponents}')
    if 2*opponents_count + 5-len(board) > 52-len(hero+board):
        raise ValueError('Carte insufficienti nel mazzo')
    return hero, board


def _straight(ranks):
    mask = sum(1 << r for r in ranks)
    for high in range(14, 5-1, -1):
        target = 31 << (high-4)
        if mask & target == target:
            return high
    return 5 if mask & ((1 << 14) | 60) == ((1 << 14) | 60) else 0


def evaluate(cards):
    """Evaluate 5..7 distinct integer cards; larger tuple means stronger hand."""
    if not 5 <= len(cards) <= 7 or len(set(cards)) != len(cards) or any(type(c) is not int or not 0 <= c < 52 for c in cards):
        raise ValueError('Valutazione richiede da 5 a 7 carte distinte valide')
    counts = Counter(c//4+2 for c in cards)
    ranks = sorted(counts, reverse=True)
    suits = [[] for _ in range(4)]
    for c in cards:
        suits[c % 4].append(c//4+2)
    flush = next((sorted(s, reverse=True) for s in suits if len(s) >= 5), None)
    if flush:
        straight = _straight(flush)
        if straight:
            return (8, straight)
    quads = [r for r in ranks if counts[r] == 4]
    if quads:
        return (7, quads[0], next(r for r in ranks if r != quads[0]))
    trips = [r for r in ranks if counts[r] >= 3]
    if trips:
        pairs = [r for r in ranks if r != trips[0] and counts[r] >= 2]
        if pairs:
            return (6, trips[0], pairs[0])
    if flush:
        return (5, *flush[:5])
    straight = _straight(ranks)
    if straight:
        return (4, straight)
    if trips:
        return (3, trips[0], *[r for r in ranks if r != trips[0]][:2])
    pairs = [r for r in ranks if counts[r] >= 2]
    if len(pairs) >= 2:
        return (2, *pairs[:2], next(r for r in ranks if r not in pairs[:2]))
    if pairs:
        return (1, pairs[0], *[r for r in ranks if r != pairs[0]][:3])
    return (0, *ranks[:5])


def uncertainty(total, squares, n, exact=False):
    mean = total/n
    variance = max(0., (squares-total*total/n)/(n-1)) if n > 1 else 0.
    se = 0. if exact else sqrt(variance/n)
    return {'value': mean, 'standard_error': se,
            'ci95': [max(0., mean-1.96*se), min(1., mean+1.96*se)]}


def calculate_equity(hero_cards, community_cards, opponents_count, simulations=5000,
                     random_seed=None, exact_threshold=2000, max_opponents=9,
                     cancelled=None, progress=None, backend='auto'):
    """Return probabilities in [0,1]. Progress receives cumulative snapshots.

    Exact enumeration is used only below exact_threshold legal labelled deals.
    Cancellation is checked every 128 deals; cancelled calls return None.
    """
    start = perf_counter()
    hero, board = validate(hero_cards, community_cards, opponents_count, max_opponents)
    if type(simulations) is not int or not 2 <= simulations <= 1000000:
        raise ValueError('Simulazioni: da 2 a 1000000')
    if type(exact_threshold) is not int or exact_threshold < 0:
        raise ValueError('Soglia di enumerazione non valida')
    if random_seed is not None and type(random_seed) is not int:
        raise ValueError('Il seed deve essere un intero')
    if backend not in ('auto', 'python', 'rust'):
        raise ValueError('Motore equity non valido: auto, python o rust')
    library = None
    if backend != 'python':
        from native_equity import load_native
        library = load_native()
        if library is None and backend == 'rust':
            raise RuntimeError('Motore Rust non disponibile: eseguire python build_native_equity.py')
    deck = tuple(c for c in range(52) if c not in hero+board)
    missing = 5-len(board)
    deals = comb(len(deck), missing)
    for i in range(opponents_count):
        deals *= comb(len(deck)-missing-2*i, 2)
    exact = deals <= exact_threshold
    current = evaluate(hero+board) if board else None
    # The current board has only 1,326 possible opponent pairs. Flop/turn
    # simulations revisit them often; river simulations reuse final scores too.
    @lru_cache(maxsize=2048)
    def current_score(hand):
        return evaluate(hand+board)

    @lru_cache(maxsize=2048)
    def hero_score(runout):
        return evaluate(hero+board+runout)
    totals = Counter()
    squares = Counter()
    categories = Counter()
    n = 0
    backend_used = 'python'

    def snapshot():
        metrics = {key: uncertainty(totals[key], squares[key], n, exact)
                   for key in ('win', 'lose', 'tie', 'equity')}
        for key in ('current_strength', 'currently_behind', 'current_tie',
                    'category_improvement', 'same_category_value_improvement', 'kicker_improvement'):
            metrics[key] = uncertainty(totals[key], squares[key], n, exact) if current else None
        return dict(status='ready', method='exact' if exact else 'monte_carlo', backend=backend_used,
                    hero_cards=[card_code(c) for c in hero], community_cards=[card_code(c) for c in board],
                    street={0:'preflop',3:'flop',4:'turn',5:'river'}[len(board)],
                    opponents_count=opponents_count, current_category=CATEGORIES[current[0]] if current else None,
                    current_label=('Royal Flush' if current == (8,14) else CATEGORIES[current[0]]) if current else None,
                    metrics=metrics, categories={k: uncertainty(categories[i], categories[i], n, exact)
                                                for i,k in enumerate(CATEGORIES)},
                    simulations=n, requested_simulations=simulations, legal_deals=deals,
                    complete=exact or n == simulations, random_seed=random_seed,
                    processing_ms=round((perf_counter()-start)*1000, 2))

    if library is not None and not exact:
        from native_equity import METRICS, run_simulations
        backend_used = 'rust'

        def use_totals(values):
            nonlocal n
            n = values.n
            for i, key in enumerate(METRICS):
                totals[key], squares[key] = values.sums[i], values.squares[i]
            for i, value in enumerate(values.categories):
                categories[i] = value

        def native_progress(values):
            use_totals(values)
            if progress:
                progress(snapshot())

        output = run_simulations(library, hero, board, opponents_count, simulations,
                                 random_seed, cancelled, native_progress if progress else None)
        if output is None:
            return None
        use_totals(output)
        return snapshot()

    def enumerate_hands(remaining, hands=()):
        if len(hands) == opponents_count:
            yield hands
            return
        for pair in combinations(remaining, 2):
            yield from enumerate_hands(tuple(c for c in remaining if c not in pair), hands+(pair,))

    def exact_samples():
        for runout in combinations(deck, missing):
            remaining = tuple(c for c in deck if c not in runout)
            for hands in enumerate_hands(remaining):
                yield runout, hands

    rng = random.Random(random_seed)
    def random_samples():
        for _ in range(simulations):
            sample = rng.sample(deck, missing+2*opponents_count)
            yield tuple(sample[:missing]), tuple(tuple(sample[missing+2*i:missing+2*i+2]) for i in range(opponents_count))

    for runout, hands in exact_samples() if exact else random_samples():
        if n % 128 == 0 and cancelled and cancelled():
            return None
        final_board = board+runout
        final = hero_score(tuple(sorted(runout)))
        scores = ([evaluate(hand+final_board) for hand in hands] if missing else
                  [current_score(tuple(sorted(hand))) for hand in hands])
        best = max(scores)
        win, lose = final > best, final < best
        tie = not win and not lose
        share = 0. if lose else 1/(1+sum(score == final for score in scores))
        values = dict(win=win, lose=lose, tie=tie, equity=share)
        if current:
            current_scores = [current_score(tuple(sorted(hand))) for hand in hands] if missing else scores
            current_best = max(current_scores)
            values.update(current_strength=current > current_best, currently_behind=current < current_best,
                          current_tie=current == current_best, category_improvement=final[0] > current[0],
                          same_category_value_improvement=final[0] == current[0] and final > current)
            # A stricter subset: unchanged made combination, better kickers.
            core = {0: 2, 1: 2, 2: 3, 3: 2, 7: 2}.get(current[0])
            values['kicker_improvement'] = bool(core and final[:core] == current[:core] and final > current)
        for key, value in values.items():
            totals[key] += value
            squares[key] += value*value
        categories[final[0]] += 1
        n += 1
        if progress and not exact and n in (256, 1024, 5000, 10000, 25000, 50000, 100000, 150000, 200000) and n < simulations:
            progress(snapshot())
    return snapshot()

"""Small ctypes bridge to the optional single-threaded Rust equity kernel.

Build with `python build_native_equity.py`. Libraries are loaded from this
repository only; importing this module never compiles or downloads anything.
"""
import ctypes as ct
from functools import lru_cache
from pathlib import Path
import secrets
import sys

METRICS = ('win', 'lose', 'tie', 'equity', 'current_strength', 'currently_behind',
           'current_tie', 'category_improvement', 'same_category_value_improvement', 'kicker_improvement')
PROGRESS_SAMPLES = (256, 1024, 5000, 10000, 25000, 50000, 100000, 150000, 200000)


class Totals(ct.Structure):
    _fields_ = [('n', ct.c_uint64), ('sums', ct.c_double * 10),
                ('squares', ct.c_double * 10), ('categories', ct.c_uint64 * 9),
                ('threats_now', ct.c_uint64 * 9), ('threats_final', ct.c_uint64 * 9)]


CALLBACK = ct.CFUNCTYPE(ct.c_int, ct.POINTER(Totals))
BYTE_POINTER = ct.POINTER(ct.c_uint8)


def library_path():
    name = ('poker_equity_native_v3.dll' if sys.platform == 'win32' else
            'libpoker_equity_native_v3.dylib' if sys.platform == 'darwin' else
            'libpoker_equity_native_v3.so')
    return Path(__file__).resolve().parent / 'native' / 'equity' / 'target' / 'release' / name


@lru_cache(maxsize=1)
def load_native():
    try:
        library = ct.CDLL(str(library_path()))
        library.poker_equity_abi_version.argtypes = []
        library.poker_equity_abi_version.restype = ct.c_uint32
        if library.poker_equity_abi_version() != 3:
            return None
        library.poker_simulate.argtypes = [BYTE_POINTER, ct.c_size_t, ct.c_size_t,
                                          ct.c_uint64, ct.c_uint64, CALLBACK, ct.POINTER(Totals)]
        library.poker_simulate.restype = ct.c_int
        library.poker_simulate_bets.argtypes = [BYTE_POINTER, ct.c_size_t, ct.c_size_t,
                                               ct.c_uint64, ct.c_uint64, BYTE_POINTER,
                                               CALLBACK, ct.POINTER(Totals)]
        library.poker_simulate_bets.restype = ct.c_int
        library.poker_evaluate_many.argtypes = [BYTE_POINTER, ct.c_size_t, ct.c_size_t, ct.POINTER(ct.c_uint32)]
        library.poker_evaluate_many.restype = ct.c_int
        library.poker_score_deals.argtypes = [BYTE_POINTER, ct.c_size_t, ct.c_size_t,
                                             BYTE_POINTER, ct.c_size_t, ct.POINTER(Totals)]
        library.poker_score_deals.restype = ct.c_int
        return library
    except (OSError, AttributeError):
        return None


def run_simulations(library, hero, board, opponents, simulations, seed, cancelled, progress, strengths=None):
    known = (ct.c_uint8 * (len(hero) + len(board)))(*hero, *board)
    # Preserve all bits of arbitrary Python integer seeds by folding through
    # a stable digest. A missing seed gets a fresh OS-generated 64-bit value.
    if seed is None:
        seed = secrets.randbits(64)
    else:
        import hashlib
        seed = int.from_bytes(hashlib.blake2b(str(seed).encode('ascii'), digest_size=8).digest(), 'little')
    errors = []
    published = set()

    @CALLBACK
    def notify(pointer):
        try:
            if cancelled and cancelled():
                return 1
            totals = pointer.contents
            if progress and totals.n in PROGRESS_SAMPLES and totals.n < simulations and totals.n not in published:
                published.add(totals.n)
                progress(totals)
            return 0
        except BaseException as error:
            # Exceptions cannot cross a ctypes callback boundary. Cancel Rust
            # synchronously, then raise the original error back in Python.
            errors.append(error)
            return 1

    output = Totals()
    if strengths is None:
        code = library.poker_simulate(known, len(known), opponents, simulations, seed, notify, ct.byref(output))
    else:
        levels = (ct.c_uint8 * opponents)(*strengths)
        code = library.poker_simulate_bets(known, len(known), opponents, simulations, seed, levels, notify, ct.byref(output))
    if errors:
        raise errors[0]
    if code == 1:
        return None
    if code != 0:
        raise RuntimeError('Campionamento del modello non completato' if code == -2 else
                           'Parametri non validi per il motore equity Rust')
    return output


def evaluate_many(hands):
    """Packed exact scores for evaluator regression tests and diagnostics."""
    library = load_native()
    if library is None:
        raise RuntimeError('Motore Rust non compilato: eseguire python build_native_equity.py')
    if not hands:
        return []
    width = len(hands[0])
    if width not in (5, 6, 7) or any(len(h) != width or len(set(h)) != width or
            any(type(c) is not int or not 0 <= c < 52 for c in h) for h in hands):
        raise ValueError('Servono mani omogenee di 5, 6 o 7 carte distinte valide')
    data = (ct.c_uint8 * (len(hands) * width))(*(c for h in hands for c in h))
    output = (ct.c_uint32 * len(hands))()
    if library.poker_evaluate_many(data, width, len(hands), output) != 0:
        raise RuntimeError('Valutazione Rust non riuscita')
    return list(output)

//! Single-threaded Hold'em Monte Carlo kernel, exported through a versioned C ABI.
//! No network, Python runtime, external crates, or runtime table generation.
#[allow(dead_code)]
mod ranking;
use ranking::{rank_index, FLUSH_OFFSET, SIZES};

const TABLES: &[u8] = include_bytes!(concat!(env!("OUT_DIR"), "/scores.bin"));

fn lookup(index: usize) -> u32 {
    u32::from_le_bytes(TABLES[index * 4..index * 4 + 4].try_into().unwrap())
}

fn evaluate(cards: &[u8]) -> u32 {
    let mut counts = [0u8; 13];
    let mut suits = [0u16; 4];
    for &card in cards {
        counts[(card / 4) as usize] += 1;
        suits[(card % 4) as usize] |= 1 << (card / 4);
    }
    for mask in suits {
        if mask.count_ones() >= 5 {
            return lookup(FLUSH_OFFSET + mask as usize);
        }
    }
    let offset = match cards.len() {
        5 => 0,
        6 => SIZES[0],
        7 => SIZES[0] + SIZES[1],
        _ => unreachable!(),
    };
    lookup(offset + rank_index(&counts))
}

// xoshiro256++ with SplitMix64 initialization, public-domain algorithm by
// David Blackman and Sebastiano Vigna: https://prng.di.unimi.it/
struct Random([u64; 4]);
impl Random {
    fn new(mut seed: u64) -> Self {
        let mut state = [0; 4];
        for value in &mut state {
            seed = seed.wrapping_add(0x9e3779b97f4a7c15);
            let mut z = seed;
            z = (z ^ (z >> 30)).wrapping_mul(0xbf58476d1ce4e5b9);
            z = (z ^ (z >> 27)).wrapping_mul(0x94d049bb133111eb);
            *value = z ^ (z >> 31);
        }
        Self(state)
    }
    fn next(&mut self) -> u64 {
        let s = &mut self.0;
        let value = s[0].wrapping_add(s[3]).rotate_left(23).wrapping_add(s[0]);
        let t = s[1] << 17;
        s[2] ^= s[0];
        s[3] ^= s[1];
        s[1] ^= s[2];
        s[0] ^= s[3];
        s[2] ^= t;
        s[3] = s[3].rotate_left(45);
        value
    }
    fn below(&mut self, bound: usize) -> usize {
        // Reject the short tail before modulo: every legal index has exactly
        // the same probability, unlike a plain random_word % bound.
        let bound = bound as u64;
        let threshold = bound.wrapping_neg() % bound;
        loop {
            let word = self.next();
            if word >= threshold {
                return (word % bound) as usize;
            }
        }
    }
}

#[repr(C)]
#[derive(Default, Clone)]
pub struct Totals {
    pub n: u64,
    pub sums: [f64; 10],
    pub squares: [f64; 10],
    pub categories: [u64; 9],
}

fn valid(cards: &[u8]) -> bool {
    let mut seen = 0u64;
    for &card in cards {
        if card >= 52 || seen & (1u64 << card) != 0 {
            return false;
        }
        seen |= 1u64 << card;
    }
    true
}

#[no_mangle]
pub extern "C" fn poker_equity_abi_version() -> u32 {
    1
}

/// # Safety
/// Input points to `count * width` bytes, output to `count` u32 values.
#[no_mangle]
pub unsafe extern "C" fn poker_evaluate_many(
    input: *const u8,
    width: usize,
    count: usize,
    output: *mut u32,
) -> i32 {
    if input.is_null() || output.is_null() || !(5..=7).contains(&width) || count > 3_000_000 {
        return -1;
    }
    let cards = std::slice::from_raw_parts(input, count * width);
    let scores = std::slice::from_raw_parts_mut(output, count);
    for (hand, score) in cards.chunks_exact(width).zip(scores) {
        if !valid(hand) {
            return -1;
        }
        *score = evaluate(hand);
    }
    0
}

// Metric order matches native_equity.METRICS. All inputs are joint deals
// without replacement, including the runout and every opponent's two cards.
fn record(hero: &[u8], board: &[u8], sample: &[u8], opponents: usize, totals: &mut Totals) {
    let missing = 5 - board.len();
    let mut final_board = [0; 5];
    final_board[..board.len()].copy_from_slice(board);
    final_board[board.len()..].copy_from_slice(&sample[..missing]);
    let mut hand = [0; 7];
    hand[..2].copy_from_slice(hero);
    hand[2..].copy_from_slice(&final_board);
    let final_score = evaluate(&hand);
    let category = final_score >> 20;
    let current = if board.is_empty() {
        None
    } else {
        hand[2..2 + board.len()].copy_from_slice(board);
        Some(evaluate(&hand[..2 + board.len()]))
    };
    let (mut best, mut current_best, mut equals) = (0, 0, 0);
    for opponent in 0..opponents {
        let pair = &sample[missing + 2 * opponent..missing + 2 * opponent + 2];
        hand[..2].copy_from_slice(pair);
        let score = evaluate(&hand);
        best = best.max(score);
        if score == final_score {
            equals += 1;
        }
        if current.is_some() {
            let now = if missing == 0 {
                score
            } else {
                evaluate(&hand[..2 + board.len()])
            };
            current_best = current_best.max(now);
        }
    }
    let mut values = [0.; 10];
    values[0] = (final_score > best) as u8 as f64;
    values[1] = (final_score < best) as u8 as f64;
    values[2] = (final_score == best) as u8 as f64;
    values[3] = if final_score < best {
        0.
    } else {
        1. / (1 + equals) as f64
    };
    if let Some(now) = current {
        let current_category = now >> 20;
        values[4] = (now > current_best) as u8 as f64;
        values[5] = (now < current_best) as u8 as f64;
        values[6] = (now == current_best) as u8 as f64;
        values[7] = (category > current_category) as u8 as f64;
        values[8] = (category == current_category && final_score > now) as u8 as f64;
        let shift = match current_category {
            0 | 1 | 3 | 7 => 16,
            2 => 12,
            _ => 0,
        };
        values[9] =
            (shift != 0 && final_score >> shift == now >> shift && final_score > now) as u8 as f64;
    }
    for (i, value) in values.into_iter().enumerate() {
        totals.sums[i] += value;
        totals.squares[i] += value * value;
    }
    totals.categories[category as usize] += 1;
    totals.n += 1;
}

/// # Safety
/// Known points to `known_len` bytes (two hero cards followed by the board).
/// Output is writable for one Totals. Callback, when supplied, remains valid
/// throughout this synchronous call; return nonzero to cancel.
#[no_mangle]
pub unsafe extern "C" fn poker_simulate(
    known: *const u8,
    known_len: usize,
    opponents: usize,
    simulations: u64,
    seed: u64,
    callback: Option<extern "C" fn(*const Totals) -> i32>,
    output: *mut Totals,
) -> i32 {
    if known.is_null()
        || output.is_null()
        || ![2, 5, 6, 7].contains(&known_len)
        || !(1..=9).contains(&opponents)
        || !(2..=1_000_000).contains(&simulations)
    {
        return -1;
    }
    let known = std::slice::from_raw_parts(known, known_len);
    if !valid(known) {
        return -1;
    }
    let (hero, board) = known.split_at(2);
    let mut deck = [0u8; 52];
    let mut length = 0;
    for card in 0..52 {
        if !known.contains(&card) {
            deck[length] = card;
            length += 1;
        }
    }
    let wanted = 5 - board.len() + 2 * opponents;
    let mut random = Random::new(seed);
    let mut totals = Totals::default();
    let mut swaps = [0; 23];
    for _ in 0..simulations {
        if totals.n % 128 == 0
            || [5000, 10000, 25000, 50000, 100000, 150000, 200000].contains(&totals.n)
        {
            if let Some(notify) = callback {
                if notify(&totals) != 0 {
                    *output = totals;
                    return 1;
                }
            }
        }
        // Partial Fisher-Yates; restoring the swaps avoids rebuilding a deck.
        for (i, swap) in swaps.iter_mut().enumerate().take(wanted) {
            let j = i + random.below(length - i);
            *swap = j;
            deck.swap(i, j);
        }
        record(hero, board, &deck[..wanted], opponents, &mut totals);
        for i in (0..wanted).rev() {
            deck.swap(i, swaps[i]);
        }
    }
    *output = totals;
    0
}

/// Deterministic joint-deal entry point for cross-language regression tests.
/// # Safety
/// Known has known_len bytes; samples has count * (7-known_len+2*opponents).
/// Output is writable for one Totals.
#[no_mangle]
pub unsafe extern "C" fn poker_score_deals(
    known: *const u8,
    known_len: usize,
    opponents: usize,
    samples: *const u8,
    count: usize,
    output: *mut Totals,
) -> i32 {
    if known.is_null()
        || samples.is_null()
        || output.is_null()
        || ![2, 5, 6, 7].contains(&known_len)
        || !(1..=9).contains(&opponents)
        || count > 1_000_000
    {
        return -1;
    }
    let known = std::slice::from_raw_parts(known, known_len);
    if !valid(known) {
        return -1;
    }
    let width = 7 - known_len + 2 * opponents;
    let samples = std::slice::from_raw_parts(samples, count * width);
    let mut totals = Totals::default();
    for sample in samples.chunks_exact(width) {
        if !valid(sample) || sample.iter().any(|c| known.contains(c)) {
            return -1;
        }
        record(&known[..2], &known[2..], sample, opponents, &mut totals);
    }
    *output = totals;
    0
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn random_reference_vector() {
        let mut random = Random([1, 2, 3, 4]);
        assert_eq!(random.next(), 41943041);
        assert_eq!(random.next(), 58720359);
    }
    #[test]
    fn shared_royal_has_equal_equity() {
        let known = [0, 5, 35, 39, 43, 47, 51];
        let mut totals = Totals::default();
        let status = unsafe { poker_simulate(known.as_ptr(), 7, 8, 5000, 42, None, &mut totals) };
        assert_eq!(status, 0);
        assert_eq!(totals.sums[2], 5000.);
        assert!((totals.sums[3] / 5000. - 1. / 9.).abs() < 1e-12);
    }
}

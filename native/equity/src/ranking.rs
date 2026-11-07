// Exact, order-preserving scores. Category occupies the high nibble, followed
// by up to five rank nibbles, matching Python's lexicographic score tuples.
pub const SIZES: [usize; 3] = [6188, 18564, 50388];
pub const FLUSH_OFFSET: usize = SIZES[0] + SIZES[1] + SIZES[2];

pub const fn choose(n: usize, k: usize) -> usize {
    if k > n {
        return 0;
    }
    let mut value = 1;
    let mut i = 0;
    while i < k {
        value = value * (n - i) / (i + 1);
        i += 1;
    }
    value
}

// Combinatorial number system for multisets: transform sorted ranks r[i]
// into the strictly increasing sequence r[i]+i. No hash collisions or probes.
pub const fn hash_terms() -> [[usize; 7]; 13] {
    let mut terms = [[0; 7]; 13];
    let mut rank = 0;
    while rank < 13 {
        let mut i = 0;
        while i < 7 {
            terms[rank][i] = choose(rank + i, i + 1);
            i += 1;
        }
        rank += 1;
    }
    terms
}
const TERMS: [[usize; 7]; 13] = hash_terms();

pub fn rank_index(counts: &[u8; 13]) -> usize {
    let (mut index, mut ordinal) = (0, 0);
    for (rank, &count) in counts.iter().enumerate() {
        for _ in 0..count {
            index += TERMS[rank][ordinal];
            ordinal += 1;
        }
    }
    index
}

pub fn score(category: u32, ranks: &[u32]) -> u32 {
    let mut value = category << 20;
    for (i, &rank) in ranks.iter().enumerate() {
        value |= rank << (16 - 4 * i);
    }
    value
}

pub fn straight(mask: u16) -> u32 {
    for high in (4..13).rev() {
        if mask & (31 << (high - 4)) == 31 << (high - 4) {
            return high + 2;
        }
    }
    if mask & 0x100f == 0x100f {
        5
    } else {
        0
    }
}

// Used only to generate lookup tables at build time.
pub fn nonflush_score(counts: &[u8; 13]) -> u32 {
    let mut ranks = Vec::new();
    let mut pairs = Vec::new();
    let mut trips = Vec::new();
    let mut mask = 0;
    let mut quad = None;
    for r in (0..13).rev() {
        if counts[r] > 0 {
            ranks.push(r as u32 + 2);
            mask |= 1 << r;
        }
        if counts[r] >= 2 {
            pairs.push(r as u32 + 2);
        }
        if counts[r] >= 3 {
            trips.push(r as u32 + 2);
        }
        if counts[r] == 4 {
            quad = Some(r as u32 + 2);
        }
    }
    if let Some(q) = quad {
        return score(7, &[q, *ranks.iter().find(|&&r| r != q).unwrap()]);
    }
    if let Some(&t) = trips.first() {
        if let Some(&p) = pairs.iter().find(|&&p| p != t) {
            return score(6, &[t, p]);
        }
    }
    let high = straight(mask);
    if high != 0 {
        return score(4, &[high]);
    }
    if let Some(&t) = trips.first() {
        let kickers: Vec<_> = ranks.iter().copied().filter(|&r| r != t).take(2).collect();
        return score(3, &[t, kickers[0], kickers[1]]);
    }
    if pairs.len() >= 2 {
        let kicker = *ranks
            .iter()
            .find(|&&r| r != pairs[0] && r != pairs[1])
            .unwrap();
        return score(2, &[pairs[0], pairs[1], kicker]);
    }
    if let Some(&p) = pairs.first() {
        let mut values = vec![p];
        values.extend(ranks.iter().copied().filter(|&r| r != p).take(3));
        return score(1, &values);
    }
    score(0, &ranks[..5])
}

pub fn flush_score(mask: u16) -> u32 {
    if mask.count_ones() < 5 {
        return 0;
    }
    let high = straight(mask);
    if high != 0 {
        return score(8, &[high]);
    }
    let ranks: Vec<_> = (0..13)
        .rev()
        .filter(|&r| mask & (1 << r) != 0)
        .take(5)
        .map(|r| r + 2)
        .collect();
    score(5, &ranks)
}

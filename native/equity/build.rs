#[path = "src/ranking.rs"]
mod ranking;

fn fill(counts: &mut [u8; 13], rank: usize, remaining: usize, table: &mut [u32]) {
    if rank == 13 {
        if remaining == 0 {
            let index = ranking::rank_index(counts);
            assert_eq!(table[index], u32::MAX, "rank hash collision");
            table[index] = ranking::nonflush_score(counts);
        }
        return;
    }
    for count in 0..=remaining.min(4) {
        counts[rank] = count as u8;
        fill(counts, rank + 1, remaining - count, table);
    }
    counts[rank] = 0;
}

fn main() {
    println!("cargo:rerun-if-changed=src/ranking.rs");
    println!("cargo:rerun-if-changed=build.rs");
    let mut tables = Vec::new();
    for (i, size) in ranking::SIZES.into_iter().enumerate() {
        let mut table = vec![u32::MAX; size];
        fill(&mut [0; 13], 0, i + 5, &mut table);
        tables.extend(table);
    }
    assert_eq!(tables.len(), ranking::FLUSH_OFFSET);
    tables.extend((0..8192).map(ranking::flush_score));
    let bytes: Vec<_> = tables.into_iter().flat_map(u32::to_le_bytes).collect();
    let path = std::path::PathBuf::from(std::env::var_os("OUT_DIR").unwrap()).join("scores.bin");
    std::fs::write(path, bytes).unwrap();
}

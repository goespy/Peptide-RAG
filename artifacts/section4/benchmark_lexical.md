# Section 4 lexical benchmark

Recorded: `2026-08-13T18:21:47.156089+00:00`

Corpus SHA-256: `231E048971C34EF9203ED3BB20587DDE4C95141AC7EFD2746C85C078A844212C`
Qrels SHA-256: `B30E1B7868EFFB580155442917C2BB0105ECC00E13527A103F6325B6A2B32ED6`
Queries: 15
BM25: `k1=0.8`, `b=0.75`

| Operation | Samples | Median (ms) | p95 (ms) | Peak memory (bytes) |
|---|---:|---:|---:|---:|
| Cold build | 5 | 11503.597 | 11597.386 | 111491576 |
| Query | 15 x 100 | 2.490 | 7.743 | 162277 |

Timing uses `time.perf_counter`; peak allocations use `tracemalloc`. This report records observations only and defines no performance pass threshold.

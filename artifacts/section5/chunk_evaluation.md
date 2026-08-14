# Chunk Retrieval Evaluation

Development answerable QA cases only.

| Config | Lexical R@5 | Semantic R@5 | Avg context tokens |
|---|---:|---:|---:|
| 128_32 | 0.558 | 0.700 | 119.9 |
| 256_64 | 0.710 | 0.710 | 189.5 |
| 512_128 | 0.717 | 0.667 | 213.3 |

Selected chunk configuration: `256_64`.

| Alpha | Hybrid R@5 | Hybrid Evidence Hit@5 |
|---:|---:|---:|
| 0.25 | 0.710 | 0.800 |
| 0.50 | 0.810 | 0.900 |
| 0.75 | 0.780 | 0.900 |

Selected RRF alpha: `0.5`.

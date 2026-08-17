# Section 3 Retrieval Baseline

- Generated: `2026-08-13T18:05:53.944321+00:00`
- Corpus SHA-256: `231E048971C34EF9203ED3BB20587DDE4C95141AC7EFD2746C85C078A844212C`
- Qrels SHA-256: `B30E1B7868EFFB580155442917C2BB0105ECC00E13527A103F6325B6A2B32ED6`
- Qrels version: `2`
- Source revision: `6bc737334357787ea469f456405c054fe30f2611`
- Source worktree dirty: `false`
- Documents: `2000`
- Vocabulary terms: `19023`
- BM25: Lucene variant, `k1=1.2`, `b=0.75`

## BOOLEAN

### Aggregate

| Queries | MRR | Mean Precision@1 | Mean Precision@3 | Mean Precision@5 | Mean Precision@10 | Mean Recall@1 | Mean Recall@3 | Mean Recall@5 | Mean Recall@10 | Mean NDCG@1 | Mean NDCG@3 | Mean NDCG@5 | Mean NDCG@10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 15 | 0.967 | 0.933 | 0.622 | 0.507 | 0.253 | 0.220 | 0.428 | 0.570 | 0.570 | 0.933 | 0.725 | 0.716 | 0.716 |

### Per-query

| Query ID | Query | Relevant | Retrieved | Reciprocal Rank | Precision@1 | Precision@3 | Precision@5 | Precision@10 | Recall@1 | Recall@3 | Recall@5 | Recall@10 | NDCG@1 | NDCG@3 | NDCG@5 | NDCG@10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| q01 | BPC 157 liver necrosis rats | 3 | 6 | 1.000 | 1.000 | 0.667 | 0.600 | 0.300 | 0.333 | 0.667 | 1.000 | 1.000 | 1.000 | 0.649 | 0.889 | 0.889 |
| q02 | GHK Cu cognitive decline neurodegeneration | 5 | 1 | 1.000 | 1.000 | 0.333 | 0.200 | 0.100 | 0.200 | 0.200 | 0.200 | 0.200 | 1.000 | 0.469 | 0.372 | 0.372 |
| q03 | thymosin beta 4 backbone conformations | 4 | 1 | 1.000 | 1.000 | 0.333 | 0.200 | 0.100 | 0.250 | 0.250 | 0.250 | 0.250 | 1.000 | 0.469 | 0.390 | 0.390 |
| q04 | ipamorelin oral bioavailability growth hormone | 5 | 4 | 1.000 | 1.000 | 1.000 | 0.800 | 0.400 | 0.200 | 0.600 | 0.800 | 0.800 | 1.000 | 0.844 | 0.927 | 0.927 |
| q05 | tesamorelin HIV lipodystrophy clinical trials | 5 | 9 | 1.000 | 1.000 | 1.000 | 1.000 | 0.500 | 0.200 | 0.600 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| q06 | epitalon drosophila lifespan increase | 3 | 1 | 1.000 | 1.000 | 0.333 | 0.200 | 0.100 | 0.333 | 0.333 | 0.333 | 0.333 | 1.000 | 0.556 | 0.556 | 0.556 |
| q07 | MOTS c metabolic obesity insulin resistance | 5 | 14 | 1.000 | 1.000 | 1.000 | 1.000 | 0.500 | 0.200 | 0.600 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| q08 | PT 141 melanocortin sexual dysfunction | 5 | 9 | 1.000 | 1.000 | 1.000 | 1.000 | 0.500 | 0.200 | 0.600 | 1.000 | 1.000 | 1.000 | 0.803 | 0.940 | 0.940 |
| q09 | BPC 157 gastric duodenal lesions rats | 5 | 12 | 1.000 | 1.000 | 1.000 | 1.000 | 0.500 | 0.200 | 0.600 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| q10 | GHK Cu healing ACL reconstruction rat | 5 | 1 | 1.000 | 1.000 | 0.333 | 0.200 | 0.100 | 0.200 | 0.200 | 0.200 | 0.200 | 1.000 | 0.726 | 0.606 | 0.606 |
| q11 | TB 500 wound healing metabolites | 3 | 2 | 0.500 | 0.000 | 0.333 | 0.200 | 0.100 | 0.000 | 0.333 | 0.333 | 0.333 | 0.000 | 0.458 | 0.458 | 0.458 |
| q12 | ipamorelin growth hormone release receptor | 4 | 3 | 1.000 | 1.000 | 0.667 | 0.400 | 0.200 | 0.250 | 0.500 | 0.500 | 0.500 | 1.000 | 0.847 | 0.767 | 0.767 |
| q13 | tesamorelin HIV visceral adipose triglycerides safety | 5 | 2 | 1.000 | 1.000 | 0.667 | 0.400 | 0.200 | 0.200 | 0.400 | 0.400 | 0.400 | 1.000 | 0.765 | 0.679 | 0.679 |
| q14 | epitalon evening melatonin cortisol secretion | 3 | 1 | 1.000 | 1.000 | 0.333 | 0.200 | 0.100 | 0.333 | 0.333 | 0.333 | 0.333 | 1.000 | 0.556 | 0.556 | 0.556 |
| q15 | MOTS c mitochondrial polymorphism longevity | 5 | 1 | 1.000 | 1.000 | 0.333 | 0.200 | 0.100 | 0.200 | 0.200 | 0.200 | 0.200 | 1.000 | 0.726 | 0.606 | 0.606 |

## BM25

### Aggregate

| Queries | MRR | Mean Precision@1 | Mean Precision@3 | Mean Precision@5 | Mean Precision@10 | Mean Recall@1 | Mean Recall@3 | Mean Recall@5 | Mean Recall@10 | Mean NDCG@1 | Mean NDCG@3 | Mean NDCG@5 | Mean NDCG@10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 15 | 0.967 | 0.933 | 0.756 | 0.640 | 0.407 | 0.229 | 0.538 | 0.749 | 0.940 | 0.933 | 0.850 | 0.860 | 0.921 |

### Per-query

| Query ID | Query | Relevant | Retrieved | Reciprocal Rank | Precision@1 | Precision@3 | Precision@5 | Precision@10 | Recall@1 | Recall@3 | Recall@5 | Recall@10 | NDCG@1 | NDCG@3 | NDCG@5 | NDCG@10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| q01 | BPC 157 liver necrosis rats | 3 | 556 | 1.000 | 1.000 | 0.667 | 0.600 | 0.300 | 0.333 | 0.667 | 1.000 | 1.000 | 1.000 | 0.907 | 0.987 | 0.987 |
| q02 | GHK Cu cognitive decline neurodegeneration | 5 | 176 | 1.000 | 1.000 | 1.000 | 0.800 | 0.500 | 0.200 | 0.600 | 0.800 | 1.000 | 1.000 | 1.000 | 0.952 | 0.996 |
| q03 | thymosin beta 4 backbone conformations | 4 | 1179 | 1.000 | 1.000 | 1.000 | 0.800 | 0.400 | 0.250 | 0.750 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| q04 | ipamorelin oral bioavailability growth hormone | 5 | 518 | 1.000 | 1.000 | 1.000 | 1.000 | 0.500 | 0.200 | 0.600 | 1.000 | 1.000 | 1.000 | 0.844 | 0.981 | 0.981 |
| q05 | tesamorelin HIV lipodystrophy clinical trials | 5 | 399 | 1.000 | 1.000 | 1.000 | 1.000 | 0.500 | 0.200 | 0.600 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| q06 | epitalon drosophila lifespan increase | 3 | 303 | 1.000 | 1.000 | 1.000 | 0.600 | 0.300 | 0.333 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| q07 | MOTS c metabolic obesity insulin resistance | 5 | 549 | 1.000 | 1.000 | 1.000 | 0.800 | 0.500 | 0.200 | 0.600 | 0.800 | 1.000 | 1.000 | 1.000 | 0.869 | 0.971 |
| q08 | PT 141 melanocortin sexual dysfunction | 5 | 143 | 1.000 | 1.000 | 0.667 | 0.800 | 0.500 | 0.200 | 0.400 | 0.800 | 1.000 | 1.000 | 0.765 | 0.910 | 0.946 |
| q09 | BPC 157 gastric duodenal lesions rats | 5 | 435 | 0.500 | 0.000 | 0.333 | 0.400 | 0.400 | 0.000 | 0.200 | 0.400 | 0.800 | 0.000 | 0.117 | 0.310 | 0.535 |
| q10 | GHK Cu healing ACL reconstruction rat | 5 | 573 | 1.000 | 1.000 | 0.667 | 0.400 | 0.400 | 0.200 | 0.400 | 0.400 | 0.800 | 1.000 | 0.879 | 0.734 | 0.865 |
| q11 | TB 500 wound healing metabolites | 3 | 384 | 1.000 | 1.000 | 0.333 | 0.200 | 0.300 | 0.333 | 0.333 | 0.333 | 1.000 | 1.000 | 0.726 | 0.726 | 0.869 |
| q12 | ipamorelin growth hormone release receptor | 4 | 631 | 1.000 | 1.000 | 0.333 | 0.400 | 0.200 | 0.250 | 0.250 | 0.500 | 0.500 | 1.000 | 0.726 | 0.752 | 0.752 |
| q13 | tesamorelin HIV visceral adipose triglycerides safety | 5 | 188 | 1.000 | 1.000 | 1.000 | 0.600 | 0.500 | 0.200 | 0.600 | 0.600 | 1.000 | 1.000 | 1.000 | 0.887 | 0.978 |
| q14 | epitalon evening melatonin cortisol secretion | 3 | 186 | 1.000 | 1.000 | 0.667 | 0.600 | 0.300 | 0.333 | 0.667 | 1.000 | 1.000 | 1.000 | 0.907 | 0.987 | 0.987 |
| q15 | MOTS c mitochondrial polymorphism longevity | 5 | 432 | 1.000 | 1.000 | 0.667 | 0.600 | 0.500 | 0.200 | 0.400 | 0.600 | 1.000 | 1.000 | 0.879 | 0.812 | 0.943 |

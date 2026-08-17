# Section 4 One-Shot Lexical Holdout

The selected configuration was hash-frozen before this command accessed holdout queries.

- Source revision: `c53e584ae14219ff994dbb86919a28e54a044bd7`
- Holdout queries: `q09, q10, q11, q13, q15`
- Tuned configuration: `{"analysis": "baseline", "b": 0.75, "k1": 0.8, "proximity_boost": 0.0}`

## Untouched BM25 holdout

## Retrieval Metrics

### Aggregate

| Queries | MRR | Mean Precision@1 | Mean Precision@3 | Mean Precision@5 | Mean Precision@10 | Mean Recall@1 | Mean Recall@3 | Mean Recall@5 | Mean Recall@10 | Mean NDCG@1 | Mean NDCG@3 | Mean NDCG@5 | Mean NDCG@10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 5 | 0.900 | 0.800 | 0.600 | 0.440 | 0.420 | 0.187 | 0.387 | 0.467 | 0.920 | 0.800 | 0.720 | 0.694 | 0.838 |

### Per-query

| Query ID | Query | Relevant | Retrieved | Reciprocal Rank | Precision@1 | Precision@3 | Precision@5 | Precision@10 | Recall@1 | Recall@3 | Recall@5 | Recall@10 | NDCG@1 | NDCG@3 | NDCG@5 | NDCG@10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| q09 | BPC 157 gastric duodenal lesions rats | 5 | 435 | 0.500 | 0.000 | 0.333 | 0.400 | 0.400 | 0.000 | 0.200 | 0.400 | 0.800 | 0.000 | 0.117 | 0.310 | 0.535 |
| q10 | GHK Cu healing ACL reconstruction rat | 5 | 573 | 1.000 | 1.000 | 0.667 | 0.400 | 0.400 | 0.200 | 0.400 | 0.400 | 0.800 | 1.000 | 0.879 | 0.734 | 0.865 |
| q11 | TB 500 wound healing metabolites | 3 | 384 | 1.000 | 1.000 | 0.333 | 0.200 | 0.300 | 0.333 | 0.333 | 0.333 | 1.000 | 1.000 | 0.726 | 0.726 | 0.869 |
| q13 | tesamorelin HIV visceral adipose triglycerides safety | 5 | 188 | 1.000 | 1.000 | 1.000 | 0.600 | 0.500 | 0.200 | 0.600 | 0.600 | 1.000 | 1.000 | 1.000 | 0.887 | 0.978 |
| q15 | MOTS c mitochondrial polymorphism longevity | 5 | 432 | 1.000 | 1.000 | 0.667 | 0.600 | 0.500 | 0.200 | 0.400 | 0.600 | 1.000 | 1.000 | 0.879 | 0.812 | 0.943 |

## Tuned BM25 holdout

## Retrieval Metrics

### Aggregate

| Queries | MRR | Mean Precision@1 | Mean Precision@3 | Mean Precision@5 | Mean Precision@10 | Mean Recall@1 | Mean Recall@3 | Mean Recall@5 | Mean Recall@10 | Mean NDCG@1 | Mean NDCG@3 | Mean NDCG@5 | Mean NDCG@10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 5 | 0.900 | 0.800 | 0.600 | 0.480 | 0.420 | 0.187 | 0.387 | 0.507 | 0.920 | 0.800 | 0.714 | 0.708 | 0.841 |

### Per-query

| Query ID | Query | Relevant | Retrieved | Reciprocal Rank | Precision@1 | Precision@3 | Precision@5 | Precision@10 | Recall@1 | Recall@3 | Recall@5 | Recall@10 | NDCG@1 | NDCG@3 | NDCG@5 | NDCG@10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| q09 | BPC 157 gastric duodenal lesions rats | 5 | 435 | 0.500 | 0.000 | 0.333 | 0.400 | 0.400 | 0.000 | 0.200 | 0.400 | 0.800 | 0.000 | 0.117 | 0.310 | 0.535 |
| q10 | GHK Cu healing ACL reconstruction rat | 5 | 573 | 1.000 | 1.000 | 0.667 | 0.600 | 0.400 | 0.200 | 0.400 | 0.600 | 0.800 | 1.000 | 0.847 | 0.794 | 0.858 |
| q11 | TB 500 wound healing metabolites | 3 | 384 | 1.000 | 1.000 | 0.333 | 0.200 | 0.300 | 0.333 | 0.333 | 0.333 | 1.000 | 1.000 | 0.726 | 0.726 | 0.883 |
| q13 | tesamorelin HIV visceral adipose triglycerides safety | 5 | 188 | 1.000 | 1.000 | 1.000 | 0.600 | 0.500 | 0.200 | 0.600 | 0.600 | 1.000 | 1.000 | 1.000 | 0.887 | 0.978 |
| q15 | MOTS c mitochondrial polymorphism longevity | 5 | 432 | 1.000 | 1.000 | 0.667 | 0.600 | 0.500 | 0.200 | 0.400 | 0.600 | 1.000 | 1.000 | 0.879 | 0.821 | 0.952 |

## Tuned full-set descriptive metrics

## Retrieval Metrics

### Aggregate

| Queries | MRR | Mean Precision@1 | Mean Precision@3 | Mean Precision@5 | Mean Precision@10 | Mean Recall@1 | Mean Recall@3 | Mean Recall@5 | Mean Recall@10 | Mean NDCG@1 | Mean NDCG@3 | Mean NDCG@5 | Mean NDCG@10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 15 | 0.967 | 0.933 | 0.756 | 0.653 | 0.413 | 0.229 | 0.538 | 0.762 | 0.957 | 0.933 | 0.848 | 0.865 | 0.926 |

### Per-query

| Query ID | Query | Relevant | Retrieved | Reciprocal Rank | Precision@1 | Precision@3 | Precision@5 | Precision@10 | Recall@1 | Recall@3 | Recall@5 | Recall@10 | NDCG@1 | NDCG@3 | NDCG@5 | NDCG@10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| q01 | BPC 157 liver necrosis rats | 3 | 556 | 1.000 | 1.000 | 0.667 | 0.600 | 0.300 | 0.333 | 0.667 | 1.000 | 1.000 | 1.000 | 0.907 | 0.987 | 0.987 |
| q02 | GHK Cu cognitive decline neurodegeneration | 5 | 176 | 1.000 | 1.000 | 1.000 | 0.800 | 0.500 | 0.200 | 0.600 | 0.800 | 1.000 | 1.000 | 1.000 | 0.952 | 0.996 |
| q03 | thymosin beta 4 backbone conformations | 4 | 1179 | 1.000 | 1.000 | 1.000 | 0.800 | 0.400 | 0.250 | 0.750 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| q04 | ipamorelin oral bioavailability growth hormone | 5 | 518 | 1.000 | 1.000 | 1.000 | 1.000 | 0.500 | 0.200 | 0.600 | 1.000 | 1.000 | 1.000 | 0.844 | 0.981 | 0.981 |
| q05 | tesamorelin HIV lipodystrophy clinical trials | 5 | 399 | 1.000 | 1.000 | 1.000 | 1.000 | 0.500 | 0.200 | 0.600 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| q06 | epitalon drosophila lifespan increase | 3 | 303 | 1.000 | 1.000 | 1.000 | 0.600 | 0.300 | 0.333 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| q07 | MOTS c metabolic obesity insulin resistance | 5 | 549 | 1.000 | 1.000 | 1.000 | 0.800 | 0.500 | 0.200 | 0.600 | 0.800 | 1.000 | 1.000 | 1.000 | 0.869 | 0.967 |
| q08 | PT 141 melanocortin sexual dysfunction | 5 | 143 | 1.000 | 1.000 | 0.667 | 0.800 | 0.500 | 0.200 | 0.400 | 0.800 | 1.000 | 1.000 | 0.765 | 0.910 | 0.947 |
| q09 | BPC 157 gastric duodenal lesions rats | 5 | 435 | 0.500 | 0.000 | 0.333 | 0.400 | 0.400 | 0.000 | 0.200 | 0.400 | 0.800 | 0.000 | 0.117 | 0.310 | 0.535 |
| q10 | GHK Cu healing ACL reconstruction rat | 5 | 573 | 1.000 | 1.000 | 0.667 | 0.600 | 0.400 | 0.200 | 0.400 | 0.600 | 0.800 | 1.000 | 0.847 | 0.794 | 0.858 |
| q11 | TB 500 wound healing metabolites | 3 | 384 | 1.000 | 1.000 | 0.333 | 0.200 | 0.300 | 0.333 | 0.333 | 0.333 | 1.000 | 1.000 | 0.726 | 0.726 | 0.883 |
| q12 | ipamorelin growth hormone release receptor | 4 | 631 | 1.000 | 1.000 | 0.333 | 0.400 | 0.300 | 0.250 | 0.250 | 0.500 | 0.750 | 1.000 | 0.726 | 0.752 | 0.815 |
| q13 | tesamorelin HIV visceral adipose triglycerides safety | 5 | 188 | 1.000 | 1.000 | 1.000 | 0.600 | 0.500 | 0.200 | 0.600 | 0.600 | 1.000 | 1.000 | 1.000 | 0.887 | 0.978 |
| q14 | epitalon evening melatonin cortisol secretion | 3 | 186 | 1.000 | 1.000 | 0.667 | 0.600 | 0.300 | 0.333 | 0.667 | 1.000 | 1.000 | 1.000 | 0.907 | 0.987 | 0.987 |
| q15 | MOTS c mitochondrial polymorphism longevity | 5 | 432 | 1.000 | 1.000 | 0.667 | 0.600 | 0.500 | 0.200 | 0.400 | 0.600 | 1.000 | 1.000 | 0.879 | 0.821 | 0.952 |

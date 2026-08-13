# Section 4 Lexical Development Experiments

Holdout queries were not searched or evaluated.

## Selected configuration

```json
{
  "analyzer": "baseline",
  "k1": 0.8,
  "b": 0.75,
  "proximity_boost": 0.0,
  "bm25_config": {
    "k1": 0.8,
    "b": 0.75,
    "proximity_boost": 0.0
  }
}
```

## Parameter Grid

| Analyzer | k1 | b | Proximity | Status | NDCG@10 | Recall@10 | MRR |
| --- | ---: | ---: | ---: | --- | ---: | ---: | ---: |
| baseline | 0.8 | 0.0 | 0.0 | evaluated | 0.9513 | 0.9750 | 1.0000 |
| baseline | 0.8 | 0.5 | 0.0 | evaluated | 0.9646 | 0.9500 | 1.0000 |
| baseline | 0.8 | 0.75 | 0.0 | evaluated | 0.9681 | 0.9750 | 1.0000 |
| baseline | 0.8 | 1.0 | 0.0 | evaluated | 0.9545 | 0.9550 | 1.0000 |
| baseline | 1.2 | 0.0 | 0.0 | evaluated | 0.9492 | 0.9750 | 1.0000 |
| baseline | 1.2 | 0.5 | 0.0 | evaluated | 0.9603 | 0.9300 | 1.0000 |
| baseline | 1.2 | 0.75 | 0.0 | evaluated | 0.9620 | 0.9500 | 1.0000 |
| baseline | 1.2 | 1.0 | 0.0 | evaluated | 0.9557 | 0.9550 | 1.0000 |
| baseline | 1.6 | 0.0 | 0.0 | evaluated | 0.9462 | 0.9750 | 1.0000 |
| baseline | 1.6 | 0.5 | 0.0 | evaluated | 0.9555 | 0.9300 | 1.0000 |
| baseline | 1.6 | 0.75 | 0.0 | evaluated | 0.9602 | 0.9500 | 1.0000 |
| baseline | 1.6 | 1.0 | 0.0 | evaluated | 0.9394 | 0.8967 | 1.0000 |
| baseline | 2.0 | 0.0 | 0.0 | evaluated | 0.9290 | 0.9550 | 1.0000 |
| baseline | 2.0 | 0.5 | 0.0 | evaluated | 0.9503 | 0.9300 | 1.0000 |
| baseline | 2.0 | 0.75 | 0.0 | evaluated | 0.9560 | 0.9300 | 1.0000 |
| baseline | 2.0 | 1.0 | 0.0 | evaluated | 0.9272 | 0.8967 | 1.0000 |

## Analyzers

| Analyzer | k1 | b | Proximity | Status | NDCG@10 | Recall@10 | MRR |
| --- | ---: | ---: | ---: | --- | ---: | ---: | ---: |
| baseline | 0.8 | 0.75 | 0.0 | evaluated | 0.9681 | 0.9750 | 1.0000 |
| greek | 0.8 | 0.75 | 0.0 | evaluated | 0.9681 | 0.9750 | 1.0000 |
| stopwords | 0.8 | 0.75 | 0.0 | evaluated | 0.9617 | 0.9500 | 1.0000 |
| greek_stopwords | 0.8 | 0.75 | 0.0 | evaluated | 0.9617 | 0.9500 | 1.0000 |

## Proximity

| Analyzer | k1 | b | Proximity | Status | NDCG@10 | Recall@10 | MRR |
| --- | ---: | ---: | ---: | --- | ---: | ---: | ---: |
| baseline | 0.8 | 0.75 | 0.0 | evaluated | 0.9681 | 0.9750 | 1.0000 |
| baseline | 0.8 | 0.75 | 0.1 | evaluated | 0.9519 | 0.9300 | 1.0000 |
| baseline | 0.8 | 0.75 | 0.25 | evaluated | 0.9506 | 0.9300 | 1.0000 |
| baseline | 0.8 | 0.75 | 0.5 | evaluated | 0.9481 | 0.9300 | 1.0000 |

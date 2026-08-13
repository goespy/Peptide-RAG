# Section 4 Claude Methodology Review

## Scope

Claude received only the public experiment protocol and aggregate development/
holdout outcomes. It did not access repository files, corpus text, qrels, or
secrets. This was a methodology review, not a source-code audit.

## Verdict

`CHANGES_REQUIRED`

Claude identified three concerns:

1. Development gains weakened substantially on holdout, and NDCG@3 declined.
2. The clearest holdout gain was Recall@5, so the tuning favors evidence breadth
   more than the very top of the ranked list.
3. The observed improvement may be too small to justify claiming a generally
   superior lexical configuration.

## Project response

The findings are accepted as limitations. The configuration will not be
changed after seeing the holdout because doing so would turn the holdout into a
second development set. Section 4 therefore keeps the pre-frozen
`baseline/k1=0.8/b=0.75/no-proximity` configuration and describes it as a
modest tradeoff:

- Holdout Recall@5: `+0.040`.
- Holdout NDCG@5: `+0.014`.
- Holdout NDCG@10: `+0.003`.
- Holdout NDCG@3: `-0.006`.

The recall gain is relevant to the next RAG stage, where missing evidence is a
critical failure, but it does not erase the shallow-ranking regression. Both
the untouched default and tuned configuration remain reported.

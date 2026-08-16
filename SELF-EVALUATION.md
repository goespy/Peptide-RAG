# Self-Evaluation

## Requirement evidence matrix

| Assignment requirement | Reproducible evidence | Current state |
| --- | --- | --- |
| Frozen real corpus and judgments | `python run_project.py`; `data/corpus.jsonl`; `data/qrels_v2.json` | Pass |
| Positional inverted index and Boolean retrieval | `tests/test_index.py`; `tests/test_boolean.py`; offline runner | Pass |
| BM25 and full IR metrics | `tests/test_bm25.py`; `tests/test_metrics.py`; `artifacts/section3/baseline.json` | Pass |
| Reference BM25 differential | `tests/test_bm25_differential.py` with development dependency `bm25s` | Pass |
| Measured tuning and untouched holdout | `artifacts/section4/development_experiments.json`; `artifacts/section4/holdout.json` | Pass |
| Property, deletion, robustness, performance | index/BM25 tests; `artifacts/section4/benchmark_lexical.json` | Pass |
| QA oracle and evidence spans | `QA-REVIEW.md`; `data/qa.json`; `scripts/freeze_qa.py` | Pass: 20 owner-approved cases |
| Lexical/semantic/hybrid chunk metrics | `artifacts/section5/chunk_evaluation.json`; `scripts/evaluate_chunks.py` | Pass on development split; hybrid Recall@5 0.810 |
| Grounded answers, citations, refusal | `src/generation.py`; versioned generator diagnostics | Contract passes; GPT v2.5 measured 10/10 answers, 3/3 refusals, and 13/13 structure |
| Generator selection and judge validation | `data/rag_generator_v2_5_judge_summary.json`; `artifacts/section5/generator_v2_5_judge_config.json`; blind worksheet | Judge-v2 measured 0.900 answered-only faithfulness; owner labels pending; holdout untouched |
| Independent implementation review | `artifacts/section6/claude_opus_review.md` | Opus re-review passed after fixes |
| Generator-v2.5 independent review | `artifacts/section5/claude_generator_v2_5_review.md`; `artifacts/section5/claude_generator_v2_5_judge_review.md` | Opus passed the prompt-only experiment and corrected judge-v2 evidence chain before paid calls |
| Public deployment | `app.py`; `railway.json`; `DEPLOYMENT.md` | Local shell and Railway packaging implemented; project/domain/secrets/deploy pending |
| Cost report | `COST-REPORT.md` | Embedding, bake-off, and later GPT costs measured where exposed; Railway/projections pending |
| Demo and social evidence | `DEMO-SCRIPT.md`; `SOCIAL-POST.md` | Draft only |

## Complete, reproducible evidence

- Core corpus integrity, positional index construction, Boolean retrieval, and BM25 retrieval are checked by `python run_project.py` without network access.
- The runner recomputes the current Boolean/BM25 evaluation from the frozen corpus, qrels, split, lexical configuration, and committed baseline evidence. It prints the measured metrics from that run rather than copying values into this report.
- Reference-BM25 differential and lexical tests run under `python -m unittest discover -s tests` in CI.
- Section 5 chunk manifests are validated when committed; their absence or invalid optional RAG assets is reported transparently and does not hide core-search results.
- A malformed committed RAG artifact makes the offline release command exit nonzero; an artifact that does not yet exist remains an explicit `TBD` gate.

## Pending human validation

- `data/qa.json` is owner-approved and frozen. The remaining human gate is the ten-output judge-validation worksheet.
- Development retrieval, generator, and judge-v2 results are reported with their denominators. GPT-OSS remains provisional pending owner validation; no holdout faithfulness claim is made.

## Pending credentials / deployment

- Claude development judging is complete. The final holdout still requires owner-validation passage, configured provider credentials, and a separately approved paid-run budget.
- Deployment is not represented as complete. See [DEPLOYMENT.md](DEPLOYMENT.md) for the explicit release gates.

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
| QA oracle and evidence spans | `QA-REVIEW.md`; `scripts/freeze_qa.py` | Blocked on owner approval |
| Lexical/semantic/hybrid chunk metrics | `scripts/evaluate_chunks.py` | Not run; no approved QA/cache |
| Grounded answers, citations, refusal | `src/generation.py`; unit tests | Contract passes; live evaluation pending |
| Three-model bake-off and judge validation | bake-off/validation scripts | Not run |
| Public deployment | `app.py`; `DEPLOYMENT.md` | Local shell implemented; Railway pending |
| Cost report | `COST-REPORT.md` | Formula frozen; actual prices/usage TBD |
| Demo and social evidence | `DEMO-SCRIPT.md`; `SOCIAL-POST.md` | Draft only |

## Complete, reproducible evidence

- Core corpus integrity, positional index construction, Boolean retrieval, and BM25 retrieval are checked by `python run_project.py` without network access.
- The runner recomputes the current Boolean/BM25 evaluation from the frozen corpus, qrels, split, lexical configuration, and committed baseline evidence. It prints the measured metrics from that run rather than copying values into this report.
- Reference-BM25 differential and lexical tests run under `python -m unittest discover -s tests` in CI.
- Section 5 chunk manifests are validated when committed; their absence or invalid optional RAG assets is reported transparently and does not hide core-search results.
- A malformed committed RAG artifact makes the offline release command exit nonzero; an artifact that does not yet exist remains an explicit `TBD` gate.

## Pending human approval

- `data/qa.json` is not committed as an approved QA set. Evidence-span review, answerability labels, and faithfulness/refusal labels remain pending human approval.
- No completed semantic, hybrid, citation, refusal, or faithfulness score is claimed until those approved artifacts and their evaluation outputs are committed.

## Pending credentials / deployment

- Embedding and generation evaluation requires configured provider credentials and an approved paid-run budget.
- Deployment is not represented as complete. See [DEPLOYMENT.md](DEPLOYMENT.md) for the explicit release gates.

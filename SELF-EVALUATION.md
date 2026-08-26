# Self-Evaluation

## Capability evidence matrix

| Project capability | Reproducible evidence | Current state |
| --- | --- | --- |
| Completed Pre-Search Phases 1–3 | `Presearch.md`; `Post-Stack Refinement.md`; `tests/test_presearch_docs.py` | Pass: all 16 checklist topics documented; initial decisions distinguished from later measurements |
| Frozen real corpus and judgments | `python run_project.py`; `data/corpus.jsonl`; `data/qrels_v2.json` | Pass |
| Positional inverted index and Boolean retrieval | `tests/test_index.py`; `tests/test_boolean.py`; offline runner | Pass |
| BM25 and full IR metrics | `tests/test_bm25.py`; `tests/test_metrics.py`; `artifacts/section3/baseline.json` | Pass |
| Reference BM25 differential | `tests/test_bm25_differential.py` with development dependency `bm25s` | Pass |
| Measured tuning and untouched holdout | `artifacts/section4/development_experiments.json`; `artifacts/section4/holdout.json` | Pass |
| Property, deletion, robustness, performance | index/BM25 tests; `artifacts/section4/benchmark_lexical.json`; `artifacts/section6/service_memory.json`; Railway live snapshot | Pass locally; early Railway hour: memory avg/current/max 136.7066/348.1314/677.4262 MB (limit 1023.9974 MB); short-window evidence, not capacity proof |
| QA oracle and evidence spans | `QA-REVIEW.md`; `data/qa.json`; `scripts/freeze_qa.py` | Pass: 20 owner-approved cases |
| Lexical/semantic/hybrid chunk metrics | `artifacts/section5/chunk_evaluation.json`; `scripts/evaluate_chunks.py` | Pass on development split; hybrid Recall@5 0.810 |
| Grounded answers, citations, refusal | `src/generation.py`; `src/refusals.py`; `tests/test_refusals.py`; versioned generator diagnostics | Contract passes; GPT v2.5 measured 10/10 answers, 3/3 refusals, and 13/13 structure; public responses distinguish four safe refusal reasons while retaining evidence |
| Generator selection and judge validation | `data/rag_generator_v2_5_judge_summary.json`; `artifacts/section5/generator_v2_5_judge_config.json`; blind worksheet and Markdown renderer | Pass: owner blind validation 10/10 raw agreement (kappa undefined: no label variation); GPT-OSS accepted, Claude Sonnet 4.6 judge accepted |
| One-shot RAG holdout gate | `scripts/freeze_generator_selection.py`; `scripts/export_rag_holdout_contexts.py`; `scripts/run_rag_holdout.py`; focused tests | Pass: untouched holdout 5/5 answered, 2/2 correct refusals, 7/7 structural; all measured quality rates 1.0 |
| Independent implementation review | `artifacts/section6/claude_opus_review.md` | Opus re-review passed after fixes |
| Generator-v2.5 independent review | `artifacts/section5/claude_generator_v2_5_review.md`; `artifacts/section5/claude_generator_v2_5_judge_review.md` | Opus passed the prompt-only experiment and corrected judge-v2 evidence chain before paid calls |
| Final release audit | `artifacts/section6/claude_opus_release_review.md` | Pass: blind-safe Opus review resolved all High/Medium findings; final focused verdict `PASS` |
| Final documentation/evidence audit | `artifacts/section6/claude_opus_final_docs_review.md` | Initial Opus verdict `CHANGES_REQUIRED`; eight repository findings corrected; the owner subsequently reported completing credential rotation |
| Deployment smoke and owner handoff audit | `scripts/smoke_deployment.py`; `tests/test_smoke_deployment.py`; `artifacts/section6/deployment_smoke.json`; public UI captures | Pass: recorded deployed-runtime CI run 32071964692 passed 307 tests; current release passes 313 locally; offline runner, public smoke, and controlled rate-limit smoke (HTTP 429 exactly at probe 30) pass; `qa17` validates the model-originated refusal |
| Public deployment | `app.py`; `railway.json`; `DEPLOYMENT.md`; `artifacts/section6/railway_release_measurement.json`; service-memory artifact | Pass: https://peptide-rag-production.up.railway.app tracks `main`; the retained early Railway snapshot reported 0 5xx and p95 3 ms |
| Cost report | `COST-REPORT.md`; `artifacts/section6/cost_projection.json`; frozen provider catalog and usage ledgers | Pass for evaluation evidence; holdout cost $0.06478416 plus $0.0000027 context embedding; Railway early-window usage $0.0019362454475925924, not a monthly forecast |
| Demo and social evidence | `DEMO-SCRIPT.md`; `SOCIAL-POST.md`; `docs/architecture-overview.svg`; `artifacts/section6/search-results.jpg` | Release facts and draft complete; recording and publication remain owner actions |

## Complete, reproducible evidence

- Core corpus integrity, positional index construction, Boolean retrieval, and BM25 retrieval are checked by `python run_project.py` without network access.
- The runner recomputes the current Boolean/BM25 evaluation from the frozen corpus, qrels, split, lexical configuration, and committed baseline evidence. It prints the measured metrics from that run rather than copying values into this report.
- Reference-BM25 differential and lexical tests run under `python -m unittest discover -s tests` in CI.
- Section 5 chunk manifests are validated when committed; their absence or invalid optional RAG assets is reported transparently and does not hide core-search results.
- A malformed committed RAG artifact makes the offline release command exit nonzero; an artifact that does not yet exist remains an explicit `TBD` gate.
- The service-memory artifact is bound to the exact corpus, embedding cache, and service source; `python run_project.py` rejects hash or measurement drift.

## Completed human validation

- `data/qa.json` is owner-approved and frozen. The ten-output blind worksheet achieved 10/10 raw agreement; kappa is undefined because no labels varied.
- GPT-OSS is the accepted generator and Claude Sonnet 4.6 the accepted judge. The untouched holdout measured 1.0 faithfulness, relevancy, citation, correct-answer, and correct-refusal rates (5/5 answers, 2/2 refusals, 7/7 structure).
- The holdout bridge binds downstream artifacts by SHA-256, prohibits overwrite of one-shot contexts/results, and froze the final selection only after saved rows replayed and met thresholds.

## Production limitations and remaining owner actions

- Deployment is live. Railway has supplied only a short timestamped early measurement, not a monthly resource/billing forecast; the local sizing figure is also not a production measurement.
- The owner reported rotating the OpenRouter key after Railway CLI diagnostics unexpectedly echoed the former credential into private task output. No credential value is reproduced in this report or stored in the repository.
- Demo recording and social publication remain owner actions. See [DEPLOYMENT.md](DEPLOYMENT.md) for operational limitations.

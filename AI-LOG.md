# AI Development Log

> Submission summary. The chronological evidence, prompts, failures, costs, and review history are preserved in [`AI-LOG-DETAIL.md`](AI-LOG-DETAIL.md).

## Tools & Workflow

- **Codex** was the primary pair programmer and integrator. It read the assignment first, implemented the custom index/BM25/metrics/RAG code, delegated bounded modules after interfaces were frozen, ran tests, and maintained hash-bound artifacts.
- **Claude Code (Opus)** was the independent reviewer. Its read-only reviews found evaluation-design, concurrency, recovery, and artifact-integrity defects that green tests had missed. After evidence-backed fixes, the final release-hardening review returned `PASS`; the blind owner labels and untouched holdout data were excluded from its scope.
- **OpenRouter** supplied hosted embeddings, GPT-OSS generation, and a different-family Claude Sonnet judge for explicitly approved, cost-capped evaluations. Production code uses no prebuilt IR or metrics library; `bm25s` is differential-test-only.
- **Human owner** wrote/approved relevance and QA judgments, chose the generator family, approved every paid evaluation ceiling, and completed the blind judge-validation labels. AI review never substitutes for human oracle approval.

## MCP Usage

The Codex in-app Browser MCP exercised the local FastAPI app as a user: BM25 search, snippets, PubMed links, metrics, disclaimers, and retrieval-only fallback were checked with no browser-console error. MCPs do not build the index, compute metrics, label relevance, or call the production models.

## Effective Prompts

1. “Before doing anything, read RAG-ASSIGNMENT.md to understand our absolute constraints, deliverables, and the 'measured, not vibed' methodology.” This kept labels and red metrics ahead of ranking work.
2. “Every improvement is measured against versioned evaluation artifacts. Production retrieval and metrics calculations remain hand-built; a reference library is permitted only in differential tests.” This produced immutable baselines and an independent BM25 score oracle without contaminating production code.
3. “make a mix of general user oriented questions and the original more specific questions” This improved QA realism while preserving exact evidence spans and human approval.
4. “we dont need to cut any corners lets stay as methodical as we have been.” This reinforced frozen development/holdout gates instead of tuning against the final seven cases.
5. “once you finish have claude opus check your work” This established an independent review gate; Claude findings are reproduced and tested before acceptance.

## Code Analysis

Approximately **100% of source/test code was AI-generated or AI-edited** and **0% was directly hand-written by the owner**, based on the recorded session history rather than unavailable line-level provenance. The owner contribution was nevertheless essential: corpus/topic choices, 75 relevance grades, 20 QA approvals, evaluation policy, architecture decisions, and API-cost authorization were human decisions, not generated code.

## Strengths & Limitations

- AI was strong at translating a frozen contract into isolated modules, adversarial tests, reproducible artifacts, and fast corpus-wide differential checks.
- Delegated agents repeatedly produced plausible code that used the wrong test framework or passed import tests but failed direct CLI execution; primary integration and end-to-end commands caught those errors.
- Model output quality could not be improved by confidence or prompt style alone. Saved development evidence separated retrieval misses, refusal-policy errors, citation-validation errors, and token exhaustion.
- AI reviewers can also be confidently wrong. Findings were accepted only after reproducing them against complete source data or tests.

## Oracle Catches

- Valid JSONL hid three blank book titles; comparison with official EFetch XML exposed the missing `BookTitle` path.
- The optional BM25 differential initially appeared green only because `bm25s` was absent. Installing it exposed an incorrectly batched reference call; the corrected scorer now matches all 15 frozen queries within `1e-6`.
- Claude found a self-confirming judge worksheet and an offline release check that reported pass without comparing saved metrics. Blind/hash-bound labels and full replay comparisons replaced both.
- The production service expected the wrong final-generator status/hash fields and would have ignored the measured v2.5 prompt settings. A release-loader regression test now requires the accepted selection, retriever hash, prompt hash, and exact generation settings to agree before generation can activate.
- A release audit found that ranked scores existed in the API but were invisible in the web UI. The API now emits explicit ranks, the client renders stable rank/score metadata, and an in-app browser run verified the result users actually see.
- Opus's release audit also caught shared provider-call state, non-resumable paid holdout work, and a daily-cap concurrency race. Request-local state, atomic cost-reserved checkpoints, and a true concurrent regression test now guard those boundaries.
- Production smoke initially used `qa16`, a correct deterministic safety refusal that was inappropriate for testing a **model-originated** refusal. `qa17` then intermittently returned a valid initial model refusal followed by an unusable optional reconsideration. The final release preserves that failure metadata and tests the validated initial refusal/fail-closed behavior rather than changing prompt, retrieval, or the untouched holdout.
- A real, provider-free service check of the new refusal labels initially returned `service_unavailable` for “What dose should I take?” because provider availability was checked before the deterministic dosing rule. Moving the safety check ahead of provider setup made the public explanation stable even during provider outages; a regression test now locks that ordering.

## Final release evidence

- Public service: https://peptide-rag-production.up.railway.app (Railway project `cb2e8529-ebca-4a99-9f36-9811e5bdede1`, service `bcd52c1e-5128-40db-8823-77ff9180b42b`, deployment `37dcb82b-a1cd-4524-ae52-ecc5481c34c3`: `SUCCESS`).
- Railway tracks `main`; the retained deployment snapshot at `4c709558dd0796a416022eeebf7436259927e0de` and its 307-test CI run `32071964692` are historical evidence. The current release passes 313 tests locally, and the offline runner passes every gate.
- Blind owner validation achieved 10/10 raw agreement; kappa is undefined because the labels had no variation. GPT-OSS was accepted as generator and Claude Sonnet 4.6 as judge.
- The untouched seven-case QA holdout answered all 5 answerable cases, correctly refused both unanswerable cases, and met 7/7 structural checks. Measured faithfulness, relevancy, citation, correct-answer, and correct-refusal rates were all 1.0; p95 latency was 8,445.535 ms and model/judge cost was $0.06478416.
- Public smoke passed health, metrics, same-origin behavior, BM25, a grounded answer with two citations, and the model-originated `qa17` refusal. Controlled rate-limit smoke returned HTTP 429 exactly at probe 30. Live UI evidence is captured in `artifacts/section6/cited-answer.png` and `artifacts/section6/evidence-refusal.png`. During Railway diagnostics the CLI unexpectedly printed the former OpenRouter secret into private task output; the owner reported completing rotation, and no credential value is stored in repository evidence.

## Key Learnings

The oracle is part of the product, not paperwork. Green unit tests do not prove that optional references ran, CLI commands work, labels are independent, or deployment uses the evaluated configuration. Freezing interfaces made lower-cost delegation effective, while hash binding, blind human labels, negative-result retention, and a separate-model review kept fluent AI output from becoming unearned evidence.

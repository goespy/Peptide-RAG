# AI Development Log

> Submission summary. The chronological evidence, prompts, failures, costs, and review history are preserved in [`AI-LOG-DETAIL.md`](AI-LOG-DETAIL.md).

## Tools & Workflow

- **Codex** was the primary pair programmer and integrator. It read the assignment first, implemented the custom index/BM25/metrics/RAG code, delegated bounded modules after interfaces were frozen, ran tests, and maintained hash-bound artifacts.
- **Claude Code (Opus)** was the independent reviewer. Its read-only reviews found evaluation-design and artifact-integrity defects that green tests had missed. The final release audit is still pending because the subscription session limit had not reset at the latest attempt; it is not represented as a pass.
- **OpenRouter** supplied hosted embeddings, GPT-OSS generation, and a different-family Claude Sonnet judge for explicitly approved, cost-capped evaluations. Production code uses no prebuilt IR or metrics library; `bm25s` is differential-test-only.
- **Human owner** wrote/approved relevance and QA judgments, chose the generator family, and approved every paid evaluation ceiling. The remaining blind judge-validation labels are explicitly pending; AI review never substitutes for human oracle approval.

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

## Key Learnings

The oracle is part of the product, not paperwork. Green unit tests do not prove that optional references ran, CLI commands work, labels are independent, or deployment uses the evaluated configuration. Freezing interfaces made lower-cost delegation effective, while hash binding, blind human labels, negative-result retention, and a separate-model review kept fluent AI output from becoming unearned evidence.

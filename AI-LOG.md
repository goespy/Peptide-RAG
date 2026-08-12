# AI Development Log

> Living one-page record. Update this file when work happens; use measured artifacts, test output, and actual costs. Never backfill imagined successes or failures.

## Tools & Workflow

| Date | Tool | Work performed | Human verification |
|---|---|---|---|
| 2026-08-12 | Codex | Read the assignment; implemented the Day 1 corpus fetcher, offline tests, and foundation documentation; fetched and validated the live corpus. | Reviewed the repository, verified the 2,000-record corpus schema/hash, and ran 17 offline tests. |

Second required AI tool or integration: **TBD**.

## MCP Usage

No MCP integration has been used for project implementation yet. **TBD if one is used later.** Local filesystem and shell tools are not being relabeled as MCP usage.

## Effective Prompts

Preserve 3–5 prompts that produced useful, verifiable work.

1. **Foundation constraints:** The initial project prompt requiring the exact PubMed query, a from-scratch index/metrics approach, and the “measured, not vibed” ordering. Result: **fetcher and foundation docs; engine work remains pending**.
2. **TBD:** Paste the exact prompt and describe its verified result.
3. **TBD:** Paste the exact prompt and describe its verified result.

## Code Analysis

| Category | Current estimate | Basis |
|---|---:|---|
| AI-generated or AI-edited | TBD% | Recalculate from reviewed code before submission. |
| Hand-written or materially rewritten | TBD% | Do not count manual qrels as generated code. |

Estimates must reflect the final reviewed repository, not prompt volume.

## Strengths & Limitations

- **Observed strength:** Quickly converted detailed ingestion constraints into an executable script and focused offline tests.
- **Observed limitation:** The first test command assumed `python` was on `PATH`; verification required the workspace's bundled Python runtime and a project virtual environment.
- **TBD:** Add findings from indexing, Boolean retrieval, BM25, and RAG work only after those phases exist.

## Oracle Catches

- **2026-08-12 — PubMed book titles:** The first live corpus passed the JSONL schema checks but contained three blank titles. A targeted comparison with the official EFetch XML showed that these were `PubmedBookArticle` records whose titles were stored in `Book/BookTitle`, while the parser checked only `ArticleTitle`. The parser gained a `BookTitle` fallback and a regression test; the corpus was then regenerated and revalidated. This was a data-validation catch, before retrieval evaluation existed.
- Add later retrieval incidents when a qrels metric, differential oracle, property test, or robustness test exposes them. Include the failing evidence, correction, and changed metric/test result.

## Key Learnings

- Claims in documentation must follow evidence: the repository initially contained statements about corpus and BM25 work that had not occurred, so they were removed.
- Schema validity alone is insufficient for corpus QA; field-completeness checks exposed a valid XML variant that the original parser missed.
- Retrieval decisions are baselines until the same frozen judgment set measures them.
- **TBD:** Add concrete lessons from later oracle catches.

## AI Cost Tracking

| Provider/model | Input tokens | Output tokens | Calls | Cost |
|---|---:|---:|---:|---:|
| TBD | TBD | TBD | TBD | TBD |

Record actual development usage and assumptions for the required monthly 100/1K/10K/100K-user projection before final submission.

# AI Development Log

> Living one-page record. Update this file when work happens; use measured artifacts, test output, and actual costs. Never backfill imagined successes or failures.

## Tools & Workflow

| Date | Tool | Work performed | Human verification |
|---|---|---|---|
| 2026-08-12 | Codex | Read the assignment; implemented the Day 1 corpus fetcher, offline tests, and foundation documentation; fetched and validated the live corpus. | Reviewed the repository, verified the 2,000-record corpus schema/hash, and ran 17 offline tests. |
| 2026-08-12 | Codex + three GPT-5.6 Terra subagents | Implemented deterministic qrels-candidate selection, then delegated three isolated five-document batches for draft query wording. | Primary agent corrected three peptide-omitting drafts, validated every query term against its source, rendered an explicitly unapproved human-review packet, and ran 28 offline tests. |
| 2026-08-12 | Claude (Claude Code), independent second reviewer | Re-read all 15 draft `QRELS-REVIEW.md` entries against the frozen no-stemming tokenizer rule, checking that every analyzed query term is literally present in its source; grepped the full 2,000-record corpus for a topically better TB-500 candidate. | Found and corrected one real defect (q11); flagged and then retracted one false positive (q02) after re-reading the untruncated source. Both outcomes logged under Oracle Catches below. |
| 2026-08-12 | Codex + three GPT-5.6 Terra subagents | Froze shared interfaces, then delegated the positional index, Boolean parser, and dependency-free metrics module as isolated workstreams. | Codex integrated the modules, converted an undiscovered pytest-style test file to `unittest`, fixed Windows Unicode output, ran 52 tests, and reproduced the 15-query metrics report. |

Second required AI tool or integration: **Claude Code** (independent qrels review, distinct from the Codex/GPT-5.6 build agent — satisfies the "two tools" requirement and is a deliberate second-model check, not just a second interface).

## MCP Usage

No MCP integration has been used for project implementation yet. **TBD if one is used later.** Local filesystem and shell tools are not being relabeled as MCP usage.

## Effective Prompts

Preserve 3–5 prompts that produced useful, verifiable work.

1. **Foundation constraints:** The initial project prompt requiring the exact PubMed query, a from-scratch index/metrics approach, and the “measured, not vibed” ordering. Result: **fetcher and foundation docs; engine work remains pending**.
2. **Bounded qrels drafting:** “Read ONLY candidates q01-q05 from `data/qrels_candidates.json`. Do not search the rest of the corpus or use retrieval code. Draft a short 3–6 term information need whose analyzed terms occur in the source, and return JSON requiring human approval.” Result: five draft queries; the same prompt was applied to two disjoint five-document batches.
3. **Bounded engine modules:** “Implement only one named retrieval module and its tests against these frozen public interfaces; do not edit other files; use the Python standard library and no IR libraries.” Result: independently developed index, Boolean, and metrics modules that were then integration-tested by the primary agent.

## Code Analysis

| Category | Current estimate | Basis |
|---|---:|---|
| AI-generated or AI-edited | TBD% | Recalculate from reviewed code before submission. |
| Hand-written or materially rewritten | TBD% | Do not count manual qrels as generated code. |

Estimates must reflect the final reviewed repository, not prompt volume.

## Strengths & Limitations

- **Observed strength:** Quickly converted detailed ingestion constraints into an executable script and focused offline tests.
- **Observed limitation:** The first test command assumed `python` was on `PATH`; verification required the workspace's bundled Python runtime and a project virtual environment.
- **Observed limitation:** Mechanical delegates produced fluent queries but three omitted the peptide identity, so primary review added the peptide terms before validation.
- **Observed limitation:** The Boolean delegate wrote pytest-style functions even though the repository standard was `unittest`; they looked valid but were invisible to test discovery until integration review converted them.
- **TBD:** Add findings from indexing, Boolean retrieval, BM25, and RAG work only after those phases exist.

## Oracle Catches

- **2026-08-12 — PubMed book titles:** The first live corpus passed the JSONL schema checks but contained three blank titles. A targeted comparison with the official EFetch XML showed that these were `PubmedBookArticle` records whose titles were stored in `Book/BookTitle`, while the parser checked only `ArticleTitle`. The parser gained a `BookTitle` fallback and a regression test; the corpus was then regenerated and revalidated. This was a data-validation catch, before retrieval evaluation existed.
- **2026-08-12 — q11 topical mismatch (real catch, fixed):** The deterministic lowest-PMID selection rule (Architecture.md protocol step 3) picked PMID 1328127 for the TB-500 / Thymosin Beta-4 family — a 1990s swine placental-weight study that mentions thymosin beta 4 only as one of several assayed hormones. Every analyzed query term was technically present in the source, so schema/token validation alone would not have caught it; the defect is topical implausibility, not a tokenizer bug. Grepping the full corpus surfaced PMID 38382158, literally titled with "TB-500" and directly evaluating its wound-healing activity — the reason this peptide is in the corpus at all. `QRELS-REVIEW.md`, `data/qrels_draft.json`, and the human-review notes were updated to record the substitution and the reason; `data/qrels_candidates.json` (the deterministic output) was left unchanged as the audit trail. **Root cause:** "lowest PMID per family" systematically favors decades-old, generically-worded literature for any peptide name that was studied broadly before its current therapeutic notoriety — worth re-checking for other families before freezing qrels v1.
- **2026-08-12 — q02 false positive (retracted before it was logged):** The same review initially flagged q02 (`GHK Cu cognitive decline neurodegeneration`) as broken, reasoning that the source only contained "neurodegenerative," not "neurodegeneration," under the no-stemming pipeline. Re-reading the untruncated abstract in `data/qrels_candidates.json` showed the closing sentence — "...therapeutic agent against age-associated neurodegeneration and cognitive decline" — does contain the literal token. The claim was retracted before being written into this log or applied to the qrels files; q02 required no change. Recorded here specifically because it is a "confidently wrong, then self-caught" incident, and the assignment's own oracle-catch section exists to surface exactly that pattern rather than hide it.
- **2026-08-12 — red Boolean baseline:** The first frozen-qrels run measured mean Recall@1 of `0.933`. For q11, numeric PMID ordering returned PMID 23084823 (a doping-control paper) before relevant PMID 38382158 (the wound-healing study), producing Recall@1 `0.000` and Recall@3 `1.000`. The miss was kept as evidence that Boolean matching without ranking cannot reliably order relevant results.
- **2026-08-12 — Unicode CLI output:** Retrieval itself handled `β4`, but the Windows console crashed while printing a matching title because its legacy encoding could not encode Greek beta. A direct search smoke test caught the boundary failure; the CLI now configures UTF-8 output and a Unicode retrieval regression test prevents recurrence.
- Add later retrieval incidents when a qrels metric, differential oracle, property test, or robustness test exposes them. Include the failing evidence, correction, and changed metric/test result.

## Key Learnings

- Claims in documentation must follow evidence: the repository initially contained statements about corpus and BM25 work that had not occurred, so they were removed.
- Schema validity alone is insufficient for corpus QA; field-completeness checks exposed a valid XML variant that the original parser missed.
- Lower-cost delegation worked well after selection rules and output constraints were frozen; it did not remove the need for primary validation or human relevance judgment.
- Retrieval decisions are baselines until the same frozen judgment set measures them.
- A single AI agent drafting and reviewing its own qrels is the same failure mode as a student writing an easy quiz and grading it themselves; an independent second reviewer with no stake in the retrieval implementation caught a real defect a same-agent review plausibly would not have prioritized.
- Token-literal validation ("does this word appear in the source") is necessary but not sufficient — q11 passed that check and was still a bad judgment because the source was topically implausible as a real information need. Schema/token checks and human topical judgment are different failure modes and need different checks.
- Verify against the full untruncated source before writing a finding into a permanent log, even when the finding sounds correct — the q02 near-miss shows a truncated read produces confident, wrong conclusions exactly like the ones this log exists to catch.
- **TBD:** Add concrete lessons from later oracle catches.

## AI Cost Tracking

| Provider/model | Input tokens | Output tokens | Calls | Cost |
|---|---:|---:|---:|---:|
| TBD | TBD | TBD | TBD | TBD |

Record actual development usage and assumptions for the required monthly 100/1K/10K/100K-user projection before final submission.

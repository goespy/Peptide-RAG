# Claude Opus Independent Review

- Review date: 2026-08-13
- Reviewer: Claude Opus through Claude Code 2.1.229
- Scope: Sections 5–6 code, focused tests, architecture, and release contracts
- Excluded by instruction: PubMed corpus bodies and multi-megabyte chunk bodies
- Repository access: read-only

## Audit trail

The first repository-wide attempt reached the five-minute execution ceiling and returned no verdict, so it was not counted. A bounded audit then returned `CHANGES_REQUIRED` with three blocking findings:

1. The owner judge-validation worksheet displayed the judge verdict, anchoring the supposedly independent labels.
2. The LLM judge received the frozen answerability label while judging faithfulness, relevance, and citations.
3. `run_project.py` recomputed metrics but did not compare the complete results with saved evidence, and it did not load every frozen analyzer/BM25 field.

The audit also identified cache-model self-attestation, duplicate answer retrieval, short uncited numeric claims, a medical-refusal escape, live/offline structural-validation drift, an undocumented chunk tie-break, duplicate metric work, and an undocumented p95 estimator.

## Resolutions

- The worksheet now hides both judge verdicts and answerability. Validation reloads verdicts from the SHA-256-bound source outputs and rejects changed sample evidence or duplicate source rows.
- Answerability never enters the LLM prompt. Refusal correctness is computed deterministically in Python, and a call without an answerability label fails closed before HTTP.
- Saved output answerability is overwritten from the approved QA oracle before metric calculation.
- The release runner loads the frozen analyzer, `k1`, `b`, and proximity setting, then compares the complete recomputed Boolean and BM25 reports with the committed artifacts within `1e-9`. A deliberate saved-metric mutation now fails the release.
- The frozen embedding model must match the cache manifest; answer generation reuses the single displayed retrieval; the citation and medical-refusal edge cases are covered; live and replayed answers use the same structural validator; chunk ties and p95 are explicit.

## Re-review

Claude Opus returned:

```text
VERDICT: PASS
BLOCKING FINDINGS: None
```

Its four remaining non-blocking suggestions were also addressed: source-QA answerability replaces saved labels, answerability was removed from the blind worksheet, missing judge answerability fails closed, and live/offline structural-validity parity now uses one tested function.

## Verification after review

- `python -m unittest discover -v`: 184 tests passed.
- `python run_project.py`: frozen hashes, index, Section 4 provenance, complete Boolean report, complete tuned-BM25 report, and three chunk manifests passed.
- Owner-approved QA, paid evaluation, human judge labels, holdout, costs, and deployment remain legitimate external gates and are still reported as `TBD`.

# Claude Opus Review — Blind Owner Validation

- Review method: Claude Code subscription (`opus`), read-only static audits
- Scope: owner worksheet generation, Markdown rendering, offline release replay,
  and their focused tests
- Final verdict: **PASS**
- QA oracle, judged-output JSON, holdout artifacts, and secrets were excluded
  from the review scope.

## Findings and resolutions

Claude initially returned `CHANGES_REQUIRED` after finding that the worksheet
listed answered cases first and refusals last. Even without an explicit
answerability field, position therefore revealed the target. It also found that
raw QA IDs gave the oracle approver a direct lookup key. The worksheet now uses
deterministic hash-mixed ordering and opaque review IDs; raw QA IDs, model IDs,
acceptable answers, answerability targets, and automated verdicts are absent.

A second review found that validation required ten rows but did not require ten
unique expected IDs. Duplicating an easy row could have displaced a disagreeing
row while preserving the count. Both the standalone validator and offline
release runner now require exact one-time coverage of the frozen sample set.

A third review found that the standalone validator rejected unexpected packet
root fields, but the release runner did not apply the same check until labels
were complete. The runner now applies an exact root allowlist before examining
label state. Exact allowlists also cover sample items, answers, citations,
evidence passages, and owner-label objects.

The final narrow resolution review returned `PASS`. It confirmed that empty-label
worksheets fail immediately on any unexpected root field and that completed
refusal labels render `null` rather than appearing unlabeled as `TBD`.

## Accepted limitation

Opaque IDs provide procedural rather than cryptographic blinding because their
deterministic construction is public. The owner must review only the generated
Markdown packet and avoid the QA oracle or judged-output artifacts until labels
are frozen. Determinism is retained so the packet remains reproducible and
tamper-evident.

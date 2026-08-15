# Claude Opus Generator-v2.4 Review

Date: 2026-08-14
Scope: read-only review of the v2.4 generation state machine, diagnostic gate,
cost estimator, frozen config, and focused tests. The reviewer was explicitly
denied the QA set, retrieved contexts, corpus, and holdout artifacts.

## Initial verdict: `CHANGES_REQUIRED`

Opus found one release-blocking integration defect: a deliberate
`model_insufficient_evidence_after_reconsideration` outcome was not included in
the diagnostic summary's model-refusal set. A perfect v2.4 run would therefore
have been reported as `0/3` correct refusals and would never open the judge gate.

It also identified these missing protections:

1. No test distinguished a retained refusal after reconsideration from a
   failed-closed reconsideration.
2. No test proved the conservative estimator selected the longer of the repair
   and refusal-reconsideration payloads while multiplying retry attempts.
3. The config's `repair_attempts` value was recorded but not validated.

Opus independently confirmed that the reconsideration prompt was general and
contained no QA ID, expected answer, or question-specific hint; dosing requests
still failed before provider access; the branch allowed only one secondary
stage; input/output paths and hashes remained frozen; and holdout data was not
loaded.

## Resolution evidence

- The summary now counts
  `model_insufficient_evidence_after_reconsideration` as deliberate while still
  excluding `failed_closed_after_refusal_reconsideration`.
- Focused tests pin both outcomes and the paid-judge readiness gate.
- A cost test independently reconstructs both secondary payloads, proves that
  reconsideration is longer for the frozen configuration, verifies that the
  estimator selects it, and verifies the two retry-inclusive stages per case.
- Config validation now requires exactly one secondary/repair attempt.
- The focused suite passes 48 tests and the recomputed worst-case generator-only
  estimate is `$0.0115379`, beneath the frozen `$0.02` ceiling.

## Resolution-review status

`NOT COMPLETED` — the requested Opus resolution call was rejected because the
Claude subscription session limit had been reached. This is not represented as
a PASS. The prior findings are addressed by source inspection and the tests
above; a later Opus resolution review remains desirable before release.

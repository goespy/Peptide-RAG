# Claude Opus Generator-v2.5 Pre-run Review

Date: 2026-08-16

Scope: two read-only Claude Code subscription reviews using Opus. Both were
limited to the v2.5/v2.4 generator configs, generator/diagnostic code, the
fresh model-catalog snapshot, the prior judge-review memo, and focused tests.
Opus was explicitly denied QA, contexts, generator outputs, corpus, holdout,
`.env`, network, shell, and write tools.

## Initial verdict: `CHANGES_REQUIRED`

Opus found the v2.5 prompt itself to be a sound, general, non-oracle-leaking
remediation for unsupported scope generalization. It confirmed that the four
new rules contain no QA ID, PMID, peptide name, question text, or expected
answer and preserve the v2.4 medical-refusal and single-secondary-attempt
behavior.

The review nevertheless found seven pre-run wiring gaps:

1. Diagnostic defaults still targeted v2.4 and could overwrite its evidence
   when invoked with `--overwrite`.
2. The refreshed catalog was not exercised by the real validation functions in
   tests.
3. Only one of seven v2.5 parent hashes was pinned to its source file.
4. No test proved that the generation settings and every v2.4 prompt sentence
   remained unchanged.
5. The reviewed `$0.01184732` maximum was not frozen or runtime-checked.
6. One of the four prompt changes was omitted from the change log.
7. The live run needed explicit confirmation of catalog freshness, estimate,
   new output targets, and absence of `--overwrite`.

## Resolution verdict: `PASS`

After fixes, Opus verified:

- CLI defaults now target only the v2.5 config/output/summary and refreshed
  catalog; tests hash all four v2.4 generator/judge evidence files before and
  after the default estimate path.
- The real refreshed catalog passes candidate-family, availability,
  structured-output, context, price, judge-family, and selected-parameter
  validation.
- All seven `parent_*_sha256` fields are tested against their exact files and
  participate in the runtime overwrite blocklist.
- The v2.5 generation block is key-for-key equal to v2.4, every v2.4 prompt
  sentence remains, the four general additions are documented, and obvious QA
  leakage tokens are absent.
- `$0.01184732` is frozen as `reviewed_estimate_usd` and must exactly equal the
  runtime recomputation before estimate, offline, or live execution proceeds.
- The `$0.02` cap, zero-judge-call rule, medical preflight, one-secondary-stage
  state machine, fail-closed accounting, and atomic artifact writes remain
  enforced.

Opus reported no remaining pre-run blocker. It noted operationally that the
catalog must be refreshed and the config re-frozen together if the live run
occurs after its 24-hour freshness window; the approved run is being executed
within that window.

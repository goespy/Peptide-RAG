# Claude Opus Generator-v2 Review

Date: 2026-08-14
Review method: Claude Code subscription, `--model opus`, read-only tools
Scope excluded: secrets, `.env`, corpus/chunk bodies, embeddings, saved provider-output bodies, and holdout cases

## Audit trail

The initial broad high-effort review timed out after five minutes without a
verdict and is not counted as review evidence. A narrower Opus review returned
`CHANGES_REQUIRED` with five findings:

1. Make the stated `$0.04` generator-only ceiling explicit and test its gate.
2. Do not persist full raw model responses in diagnostic artifacts.
3. Do not count a technical fail-closed fallback as a deliberate refusal.
4. Ensure a repair sees a real prior body with its matching failure reason; do
   not fabricate an assistant response when no body was received.
5. State the finite hybrid rank window explicitly.

Codex reproduced and fixed all five findings. The focused regression suite
passed, the cache-only retrieval diagnostic was regenerated, and the maximum
generator-only estimate became `$0.03457764` with zero judge calls.

## Resolution verdict

`PASS` — Opus found no unresolved blocking findings.

Opus verified that:

- the hard cost gate executes before credential access or provider calls;
- diagnostic artifacts retain only raw-output SHA-256 and character counts;
- deliberate model refusal is distinct from preflight and technical failure;
- repair body/failure provenance is reset and paired per request stage;
- hybrid diagnostics record the 50-per-source RRF limit and 100-result union
  window; and
- the generator-only execution path never calls the judge.

## Non-blocking notes

- The conservative estimator does not include the invalid assistant body in a
  hypothetical repair input, but its assumption that every attempt consumes
  the full 800-token output ceiling provides substantially more cost slack.
- A preflight medical-policy refusal intentionally does not count as a model's
  correct unanswerable-case refusal. This is conservative and could prevent the
  diagnostic gate from passing if an oracle question itself triggers preflight.
- Opus did not inspect `src/judge.py`; zero judge calls were verified at the
  generator-only call sites and cost report.

No paid generator call occurred during either review.

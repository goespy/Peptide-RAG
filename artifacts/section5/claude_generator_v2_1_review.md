# Claude Opus Generator-v2.1 Review

Date: 2026-08-14
Review method: Claude Code subscription, `--model opus`, read-only `Read` and `Grep` tools
Scope excluded: secrets, `.env`, holdout cases, provider calls, paid judging, and file modification

## Audit trail

The first broad review timed out without a verdict and is not counted as
approval. A completed focused review identified two concerns:

1. The cost gate needed an explicit invariant proving that the conservative
   estimate itself could not exceed the frozen experiment cap.
2. The reviewer could not independently inspect QA16 because the oracle was
   outside its allowed file scope.

Codex added and tested the missing estimate-versus-cap invariant. Codex also
read the owner-approved development oracle directly and verified that QA16 is:

> What is the safest effective BPC-157 dose for healing a human tendon injury?

A first resolution attempt timed out without a verdict and is also not counted
as approval. A narrower resolution review then returned `PASS`.

## Resolution verdict

`PASS` — Opus found no release-blocking defect in the generator-v2.1 preflight.

Opus verified that:

- the conservative estimate must fit both the owner-entered budget and the
  frozen configuration cap before credentials or provider calls are accessed;
- QA16 is refused deterministically before HTTP, while questions about doses
  reported in studies, trials, or experiments remain eligible for evidence-
  grounded answers;
- visible citation markers are rebound to the exact supplied contexts rather
  than trusting model-declared PMID or chunk identities;
- `provider.require_parameters` is sent for structured-output compatibility;
- persisted diagnostics omit raw provider bodies and response messages;
- the generator-only path constructs no judge and does not access the holdout;
  and
- the v2.1 configuration binds the current model catalog and parent artifacts.

## Non-blocking notes

- The command must explicitly select
  `artifacts/section5/generator_v2_1_config.json` because the script's defaults
  preserve the parent-v2 paths.
- The frozen `repair_attempts` value equals the client's current one-repair
  default, but that value is not yet passed as a constructor argument. This does
  not understate the present cost bound; making the wiring explicit is a later
  maintainability improvement.

No paid provider call occurred during any review attempt.

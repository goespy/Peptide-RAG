# Claude Opus v2.4 Judge Audit

Date: 2026-08-16

Scope: read-only audit through the Claude Code subscription using Opus. The
review was limited to the v2.4 development generator/judge code, frozen
development contexts and outputs, judge summary, blind worksheet, and relevant
tests. Opus was explicitly denied `data/qa.json`, all holdout artifacts, the
corpus, `.env`, network, shell, and write tools.

## Verdict: `CHANGES_REQUIRED`

Opus confirmed that the recorded `11/13 = 0.846153846` all-row faithfulness
score is arithmetically correct and that neither the saved artifacts nor the
release report claim final acceptance. It also confirmed the exact input,
output, path, call-count, cost-cap, and generator-answer bindings that already
held. The holdout remained untouched.

The audit found these release blockers:

1. The owner-validation rule treated undefined kappa as automatic failure even
   when a dimension had constant labels and perfect raw agreement. With the
   current sample, relevance, citation correctness, and refusal correctness
   could never pass under any owner labeling.
2. Offline judge replay did not enforce `faithful == all(claim.supported)` and
   did not compare copied generator metadata with the hash-frozen source row.
   Judge usage and latency therefore needed stronger invariants.
3. The headline faithfulness denominator included three deterministic
   refusals. Answered-only faithfulness was `8/10 = 0.800` and must be reported
   beside the all-row score.
4. The blind worksheet exposed the oracle acceptable answer even though the
   owner should judge against the displayed question and evidence. It also
   treated deterministic refusal correctness as a model-judge agreement
   dimension.
5. The v2.4 worksheet was not yet validated by the one-command offline release
   chain.
6. `ready_for_owner_validation` meant only that the single candidate had 13
   complete verdicts; the name overstated the measured faithfulness result.

## Confirmed red cases

- **qa02:** The answer attaches “in humans” to both improved transplant success
  and increased follicle size. The displayed source supports the former human
  claim but does not give the latter a human population scope. Opus confirmed
  the judge's unsupported-claim verdict and noted that “potential for hair
  regrowth” was also not directly supported.
- **qa07:** The answer correctly reports two human observations, then converts
  them into a universal “no evidence” conclusion about human weight loss or
  metabolism. The displayed evidence does not state that conclusion, and
  another supplied passage reports metabolic/weight effects in mice. Opus
  confirmed the judge's unsupported-claim verdict.

The shared failure mode is unsupported scope generalization: applying a
population qualifier or absence-of-evidence conclusion more broadly than the
cited passage permits.

## Required remediation

- Make undefined-kappa dimensions explicitly inconclusive and use the frozen
  raw-agreement floor plus confusion matrix as the fallback required by the
  project plan.
- Enforce claim/faithfulness consistency and copied-metadata equality during
  offline replay; bind future raw judge responses by hash.
- Report answered-only and all-row faithfulness with explicit denominators.
- Remove oracle answers from the owner worksheet, and treat refusal correctness
  as a deterministic consistency check rather than an agreement dimension.
- Bind the current worksheet and report into `run_project.py`.
- For a later generator version, add only general rules: do not infer absence
  of evidence unless a passage states it, attach population qualifiers only to
  claims that carry that scope, and reconcile all relevant supplied passages.

No suggestion from this audit is treated as ground truth without local source
inspection, tests, and replay evidence.

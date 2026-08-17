# Claude Opus Final Documentation Review

- Date: 2026-08-17
- Reviewer: Claude Code 2.1.233, Opus, read/search-only tools
- Scope: final release documentation, deployment evidence JSON, release-evidence test, assignment coverage, and secret hygiene
- Initial verdict: `CHANGES_REQUIRED`

## Initial findings

1. Service-memory and startup measurements disagreed across `README.md`,
   `DEPLOYMENT.md`, and the hash-bound `service_memory.json` artifact.
2. `Project-Master-Plan.md` incorrectly said Gemma produced no usable answers,
   contradicting the retained 2/10 negative result.
3. The initial bake-off table's cost column did not disclose that each row
   combined generator and judge cost.
4. The master-plan introduction and Mermaid diagram still presented Sections
   3–6 as unfinished.
5. The OpenRouter credential exposed in private Railway CLI output still needs
   rotation; no credential value was found in the repository.
6. The master plan retained the original 400-token generation contract instead
   of the measured 800-token, locally derived citation, shared-secondary-attempt
   contract.
7. The cost report's 299-call subtotal omitted 123 known generator-v2 calls
   from the overall call count even though their cost remains unknown.
8. `AI-LOG.md` called a seven-case holdout a five-case holdout.
9. The Railway billing-period end was written as if the snapshot had been
   captured at that time; the measurement was actually captured earlier.

## Resolution status

Findings 1–4 and 6–9 were corrected against the saved artifacts. Finding 5 is
an operational owner action and remains open until a replacement OpenRouter key
is installed in Railway and the old key is revoked. A follow-up Opus verdict is
required after rotation and the final test run.

## Verified clean in the initial review

Claude independently reconciled the documented corpus and QA counts, cost
arithmetic, projection arithmetic, deployment identifiers, and the distinction
between the deployed 307-test runtime CI run and the final 308-test local
documentation/evidence suite. It also confirmed that demo and social
publication are honestly disclosed as owner actions and that no secret value
appears in the audited repository files.

The 308-test figure above is the state Claude reviewed. A subsequent
owner-requested refusal-explanation change added four tests; the current branch
passes 312 tests and requires a fresh follow-up Opus verdict before release.

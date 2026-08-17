# Claude Opus QA Review Attempt

Status: unavailable — no review verdict produced

Attempted: 2026-08-14 (America/New_York)

## Requested scope

Claude Opus was asked to perform a read-only independent audit of the approved
QA oracle, including evidence support, scientific scope, species and population
caveats, unanswerable labels, split integrity, and provenance. It was explicitly
instructed not to modify files and not to treat human approval as proof of
scientific correctness.

## Outcome

- Attempt 1 reached the local 120-second execution limit without returning any
  output.
- Attempt 2 used a narrower file scope and a 300-second bound. It ended after
  approximately 192 seconds with `API Error: Connection refused — a firewall
  or proxy may be blocking it`.
- Claude produced no findings and no `PASS` or `CHANGES_REQUIRED` verdict.

This artifact is evidence of an attempted review only. It must not be cited as
Claude approval. The audit should be retried when Claude connectivity is
available.

## Completed local verification

Independently of the unavailable Claude review:

- all 20 cases have explicit project-owner approval;
- the oracle contains 15 answerable and 5 unanswerable cases;
- exact evidence offsets and SHA-256 hashes validate against the frozen corpus;
- supporting PMIDs are disjoint between development and holdout;
- the five unanswerable cases have recorded multi-query corpus audits; and
- the full offline test suite passes.


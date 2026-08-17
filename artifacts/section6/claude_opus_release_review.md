# Claude Opus Release-Hardening Review

- Review date: 2026-08-16 EDT
- Reviewer: Claude Opus through the project owner's Claude subscription
- Mode: read-only; no OpenRouter calls and no repository edits
- Explicit exclusions: the QA oracle, blind owner worksheet, owner labels, and
  all untouched holdout contexts, outputs, summaries, and results

## Initial independent findings

Opus identified two release blockers: request state shared by concurrent
generation calls, and a one-shot holdout that persisted evidence only after all
seven cases. It also identified missing query-embedding and provider-concurrency
limits, shared embedding metadata, incomplete saved-cost revalidation, a runtime
gate that did not require the actual holdout evidence artifacts, and four small
robustness defects.

The implementation response added request-local metadata, per-thread production
HTTP sessions, locked aggregate usage, an application provider semaphore, daily
answer and query-embedding caps, visible lexical fallbacks, crash-safe holdout
checkpoints and resume, saved-cost revalidation, strict holdout artifact hash
binding, malformed-input guards, dynamic context-count messages, and correct
Windows last-error handling.

## Resolution review

The first resolution pass marked every original finding resolved. It then found
additional edge cases: the daily answer slot was reserved after a retrieval
await; shared sessions serialized all provider work; resume did not reserve
worst-case cost for repeated attempts; missing values could compare equal in the
release gate; failed embeddings did not reach cumulative accounting; and one
invalid numeric environment value could silently disable provider work.

Those were addressed by:

- reserving the answer slot before any await and testing two concurrent calls;
- using per-thread production sessions while serializing only explicitly
  injected shared sessions;
- freezing a conservative maximum cost per holdout case and atomically reserving
  it before every initial or resumed attempt;
- requiring syntactically valid SHA-256 values and a metrics object before
  release activation;
- counting failed embedding attempts while recording unknown token/cost values;
- failing startup on malformed, nonfinite, negative, or zero numeric controls;
- proving the lexical fallback never invokes the query embedder; and
- making `run_project.py` replay the saved attempt reservations.

The final narrowly scoped Opus check returned **PASS** with no remaining High or
Medium finding. Opus did not inspect blind labels or holdout evidence and did
not independently execute the complete suite. The primary agent's local
verification is recorded separately in the repository and CI.

## Deployment-smoke and owner-handoff delta

Opus later reviewed the uncommitted deployment-smoke automation and human
handoff documents under the same blindness exclusions. That audit did **not**
pass the first draft. It found that the refusal probe accepted provider outages
and budget failures as if they were a correct scientific refusal. It also found
that the same-origin probe omitted browser preflights, the earlier 302-test
`PASS` was blurred with later 305-test work, and the social draft reported the
all-query tuned score without the lexical-holdout qualification.

The response now:

- accepts only the exact standard evidence refusal from hybrid retrieval with
  no fallback or infrastructure-failure reason;
- exercises hostile-origin GET and JSON-POST preflights for both public POST
  endpoints and rejects permissive CORS headers;
- verifies NCBI attribution and the exact 30-requests/minute/IP boundary;
- closes internally created HTTP sessions and caps the explicit paid smoke at
  one development answerable plus one development unanswerable HTTP request;
- forbids untouched holdout questions in smoke/demo evidence;
- separates commit `8785c40` and its 302-test Opus pass from the later local
  305-test deployment-smoke tree; and
- reports the all-query `0.926` result as descriptive alongside the frozen
  lexical-holdout delta from `0.838` to `0.841`.

After those changes, the primary agent ran 305 tests, the complete offline
release replay, and the provider-call-free smoke against a real local Uvicorn
process. All passed. A narrow Opus resolution rerun immediately afterward hit
the subscription session limit, which reports a 2:20 AM ET reset. Therefore no
second Opus `PASS` is claimed in this addendum yet.

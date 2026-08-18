# Deployment and Release Evidence

## Released

The public service is live at https://peptide-rag-production.up.railway.app.

- Deployed `main` commit: `4c709558dd0796a416022eeebf7436259927e0de`
- Railway project/service/deployment: `cb2e8529-ebca-4a99-9f36-9811e5bdede1` / `bcd52c1e-5128-40db-8823-77ff9180b42b` / `37dcb82b-a1cd-4524-ae52-ecc5481c34c3` (`SUCCESS`)
- Deployed-runtime CI run `32071964692` (307 tests): pass; current release branch (312 local tests) and offline runner: pass
- Public smoke: pass for `/healthz`, metrics, same-origin behavior, BM25, a grounded answer with two citations, and the model-originated `qa17` refusal. Controlled rate-limit smoke returned HTTP 429 exactly at probe 30.

Live public-UI evidence is retained at `artifacts/section6/cited-answer.png` and `artifacts/section6/evidence-refusal.png`.

Owner blind validation completed with 10/10 raw agreement (kappa undefined because labels did not vary). GPT-OSS is the accepted generator and Claude Sonnet 4.6 the accepted judge. The untouched QA holdout answered 5/5 cases, correctly refused 2/2, and passed 7/7 structural checks; faithfulness, relevancy, citation, correct-answer, and correct-refusal measurements were each 1.0. p95 latency was 8,445.535 ms.

### Retained negative result

The initial production smoke used `qa16`; it was a correct deterministic safety refusal, but that made it inappropriate for a model-refusal test. `qa17` intermittently returned a valid initial model refusal then an unusable optional reconsideration. PR #8 retained the already-validated refusal and failure metadata without changing prompt, retrieval, or holdout evidence; final smoke then passed. The service's behavior remains fail-closed, with five evidence cards when model completion is unusable.

### Operational follow-up

Railway reported `$0.0019362454475925924` total usage for the billing period beginning 2026-08-14T23:31Z and scheduled to end 2026-08-17T23:59Z; the snapshot itself was captured at 2026-08-17T21:45Z, before the period ended. It comprised `$0.00017385344907407406` CPU, `$0.0017422829985185185` memory, and `$0.000020109` egress. One live hour reported CPU average/max `0.006207` / `0.1637622` vCPU (limit 2), memory average/current/max `136.7066` / `348.1314` / `677.4262` MB (limit `1023.9974` MB), 78 HTTP requests (62 2xx, 16 controlled 4xx CORS/rate-limit probes, 0 5xx), error rate 0, and p95 3 ms. There is no volume/disk usage. This is a short early window, not a monthly forecast. The refreshed local benchmark measured peak RSS of 278,568,960 bytes and startup of 3,582.723 ms; it remains a separate sizing signal. During Railway diagnostics, the CLI unexpectedly printed the OpenRouter secret into private task output. Rotate that key before closing the release; do not copy it into docs, logs, screenshots, or tickets.

## Complete locally

The repository supports a read-only offline release check:

```text
python run_project.py
```

It validates frozen core hashes, builds the index, runs Boolean and BM25
evaluation, and validates the approved QA set, chunk manifests, embedding
ledger, selected hybrid configuration, development contexts, versioned GPT
outputs, Claude judge evidence, and blind owner worksheet. Corruption exits
nonzero. The measured GPT-only v2.5 development run reached 10/10 answerable
cases, 3/3 correct refusals, and 13/13 structurally valid outputs. Judge-v2
measured `0.900` answered-only faithfulness before final owner validation and
the completed holdout gate.

## Historical pre-release procedure (completed)

The 20-case QA set and evidence spans are approved. GPT-only v2.5 passed its
10/10 answerable, 3/3 correct-refusal, and 13/13 structural gate, and the
different-family Claude judge-v2 run is complete. The historical human step was
to label the blinded 10-output worksheet and validate agreement before the
one-shot holdout. It is now complete: raw agreement was 10/10 (kappa undefined
because labels did not vary), and final artifacts retain the generator, judge,
worksheet, citation, usage, and negative-result evidence.

After the labels pass, the release sequence is intentionally gated:

```text
python scripts/freeze_generator_selection.py
python scripts/export_rag_holdout_contexts.py --cache artifacts/section5/embeddings_256_64.npz --max-cost-usd 0.01 --confirm-cost
python scripts/refresh_model_catalog.py --output artifacts/section5/holdout_model_catalog.json
python scripts/run_rag_holdout.py --estimate-only
python scripts/run_rag_holdout.py --live --max-cost-usd 0.50 --confirm-cost
python run_project.py
```

The context and holdout targets are one-shot artifacts and have no overwrite
path. The live holdout atomically checkpoints every completed generator+judge
pair to a hash-bound partial journal. After an interruption, inspect the error
and use the same live command with `--resume-partial`; already completed cases
are validated and skipped. Before every new or resumed case, the journal
reserves that case's conservative maximum generator+judge cost; a retry is
refused before any call if cumulative reservations would exceed the original
owner-approved cap. If all provider calls finish but finalization is
interrupted, use
`python scripts/run_rag_holdout.py --finalize-saved`; it validates the saved
rows and makes no provider request. This release completed the holdout freeze
and offline release check before Railway deployment.

At runtime, generation also fails closed unless the final holdout config,
accepted generator selection, frozen retriever, source v2.5 prompt hash, actual
holdout contexts, outputs, and passing summary all hash-match. Deployment
therefore cannot silently replace the measured evidence, prompt, token cap,
citation mode, reasoning settings, or refusal-reconsideration behavior with
application defaults.

## Production configuration and limitations

Set `OPENROUTER_API_KEY` only in the deployment environment. The repository
uses `railway.json` and pins Python 3.11; the deployed Railway project, domain,
and service are recorded above. Railway config-as-code overrides dashboard
build/deploy settings. Rotate the deployed key following the CLI diagnostic
exposure noted above.

### Railway environment

- `OPENROUTER_API_KEY` -- required for query embeddings and grounded answers.
- `EMBEDDING_CACHE_PATH=artifacts/section5/embeddings_256_64.npz` -- selected cache matching the frozen RAG configuration.
- `DAILY_ANSWER_CAP=200` -- default single-process budget guard.
- `DAILY_EMBEDDING_CAP=5000` -- default paid query-embedding guard; exhaustion falls back visibly to BM25.
- `PROVIDER_CONCURRENCY_LIMIT=8` -- maximum simultaneous provider-bound requests.
- `PROVIDER_SLOT_TIMEOUT_SECONDS=0.1` -- maximum wait for a provider slot before a safe fallback.
- `TRUST_PROXY_HEADERS=true` -- required on Railway so rate limits use the forwarded client IP; leave false for direct local serving.

Synchronous retrieval/provider work is dispatched off the async event loop,
provider work is bounded by a semaphore, and answer/embedding budget slots are
reserved before provider awaits. The answer cap is checked before semantic
retrieval, so an exhausted answer budget cannot spend on an unnecessary query
embedding. This keeps health/local BM25 responsive and prevents concurrent
requests from overshooting single-process caps. Multiple Railway replicas would
still require shared external counters before the same claim could be made
across instances.

Planned start command:

```text
python -m uvicorn app:app --host 0.0.0.0 --port $PORT
```

The checked-in config uses Railpack, `/healthz`, a 120-second deployment
healthcheck, and an `ON_FAILURE` restart policy capped at ten retries. Railway
injects `PORT`; the application must listen on `0.0.0.0:$PORT`. The healthcheck
is a deployment-readiness gate, not continuous monitoring. See Railway's
[config-as-code reference](https://docs.railway.com/config-as-code/reference),
[public networking guide](https://docs.railway.com/public-networking), and
[healthcheck documentation](https://docs.railway.com/deployments/healthchecks).

Before release, configure Railway usage controls and optional sleeping, measure
actual memory with the selected embedding cache loaded, and keep hosting costs
separate from provider charges. Rollback means redeploying the last CI-tested
commit; if model/provider health or budget fails, unset the cache/key or lower
the daily cap so the application remains available in local BM25
retrieval-only mode.

The offline development measurement is reproducible with:

```text
python scripts/benchmark_service.py --overwrite
```

It observed `217,960,448` bytes RSS after initialization, a
`278,568,960`-byte peak, and `3,582.723 ms` startup with the selected cache,
2,000-document index, and zero provider calls. The machine ran Windows and
Python 3.12, so the artifact is a separate local sizing signal; the early
Railway/Python 3.11 measurement above is the production observation.

### Smoke-test checklist

Run the provider-call-free-by-default deployment probe first:

```text
python scripts/smoke_deployment.py --base-url https://YOUR-DOMAIN
```

After selecting one owner-approved **development** answerable question and one
development intentionally unanswerable question, the explicit paid smoke path
is below. Never use untouched holdout questions for smoke testing or the demo.
The smoke command verifies both supplied questions against the frozen approved
development split before sending a request, and a refusal passes only when the
generation client identifies it as a valid model refusal rather than a local
fail-close.

The command sends exactly two `/api/answer` HTTP requests; it does not enforce a
dollar cap, so verify the server-side daily/provider caps and the OpenRouter
account limit before confirming it.

```text
python scripts/smoke_deployment.py --base-url https://YOUR-DOMAIN --answer-query "..." --refusal-query "..." --confirm-paid
```

Add `--check-rate-limit` only in a controlled window; it deliberately sends up
to 35 additional BM25 requests to the deployed domain and requires the expected
30th probe to return HTTP 429. Wait at least 60 seconds after prior search
traffic, run this last, and expect the source IP's search route to remain
rate-limited for the rest of that one-minute window. The smoke report never
prints the supplied questions.

1. `/healthz` returns `{"status":"ok"}`.
2. BM25 search returns scored PubMed records and safe highlighted snippets.
3. Hybrid search uses the frozen cache; deleting or corrupting its identity must disable it.
4. One approved answer contains clickable, chunk-bound citations.
5. One approved development unanswerable question returns a model-originated
   `insufficient_evidence`, not a provider/parser fail-close.
6. Personalized/dosing advice is refused before generation.
7. The response exposes exactly one safe public category—medical safety,
   insufficient evidence, service unavailable, or budget limit—without raw
   provider details, and the UI still displays retrieved evidence.
7. Per-IP limits and the daily budget return retrieval evidence, not a generated fallback.
8. No raw query or server secret appears in application logs or browser code.

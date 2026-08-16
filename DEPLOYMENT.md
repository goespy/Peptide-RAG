# Deployment and Release Gates

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
measured `0.900` answered-only faithfulness, but holdout remains `TBD` until the
owner-validation gate passes.

## Pending human validation

The 20-case QA set and evidence spans are approved. GPT-only v2.5 passed its
10/10 answerable, 3/3 correct-refusal, and 13/13 structural gate, and the
different-family Claude judge-v2 run is complete. The remaining human step is
to label the blinded 10-output worksheet (seven answerable plus all three
unanswerable outputs), validate agreement, and only then run the untouched
seven-case holdout exactly once. Commit every reproducible generator, judge,
worksheet, citation, usage, and negative-result artifact.

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
path. If provider calls finish but summary finalization is interrupted, use
`python scripts/run_rag_holdout.py --finalize-saved`; it validates the saved
rows and makes no provider request. Railway deployment remains closed until the
holdout artifact is frozen and the offline release check passes.

At runtime, generation also fails closed unless the final holdout config,
accepted generator selection, frozen retriever, source v2.5 prompt hash, and
all generation settings agree. Deployment therefore cannot silently replace
the measured prompt, token cap, citation mode, reasoning settings, or refusal
reconsideration behavior with application defaults.

## Pending credentials and deployment

Set `OPENROUTER_API_KEY` only in the deployment environment after the RAG
release gates pass. The repository now includes `railway.json` and pins Python
3.11, but no Railway project, domain, secret, or paid deployment has been
created. Railway config-as-code overrides dashboard build/deploy settings, so
review the deployment details before activation.

### Planned Railway environment

- `OPENROUTER_API_KEY` -- required for query embeddings and grounded answers.
- `EMBEDDING_CACHE_PATH=artifacts/section5/embeddings_256_64.npz` -- selected cache matching the frozen RAG configuration.
- `DAILY_ANSWER_CAP=200` -- default single-process budget guard.
- `TRUST_PROXY_HEADERS=true` -- required on Railway so rate limits use the forwarded client IP; leave false for direct local serving.

Synchronous retrieval/provider work is dispatched off the async event loop,
and an answer-attempt budget slot is reserved before the provider await. This
prevents a slow request from freezing unrelated endpoints and prevents
concurrent requests from overshooting the single-process daily cap. Multiple
Railway replicas would still require a shared external counter before the same
claim could be made across instances.

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

It observed `216,748,032` bytes RSS after initialization and a
`278,310,912`-byte peak with the selected cache, 2,000-document index, and zero
provider calls. The machine ran Windows and Python 3.12, so the artifact is a
pre-deployment sizing signal only; Railway/Python 3.11 memory remains the
authoritative production measurement.

### Smoke-test checklist

1. `/healthz` returns `{"status":"ok"}`.
2. BM25 search returns scored PubMed records and safe highlighted snippets.
3. Hybrid search uses the frozen cache; deleting or corrupting its identity must disable it.
4. One approved answer contains clickable, chunk-bound citations.
5. One frozen unanswerable question returns `insufficient_evidence`.
6. Personalized/dosing advice is refused before generation.
7. Per-IP limits and the daily budget return retrieval evidence, not a generated fallback.
8. No raw query or server secret appears in application logs or browser code.

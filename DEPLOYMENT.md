# Deployment and Release Gates

## Complete locally

The repository supports a read-only offline release check:

```text
python run_project.py
```

It validates frozen core hashes, builds the index, runs Boolean and BM25
evaluation, and validates the approved QA set, chunk manifests, embedding
ledger, selected hybrid configuration, and development contexts. Corruption
exits nonzero. Generator acceptance, judge validation, and holdout gates remain
`TBD` until their evidence exists. The measured GPT-only v2.3 development run
reached 9/10 answerable cases, 3/3 correct refusals, and 13/13 structurally
valid outputs; it is preserved as a failed gate rather than promoted.

## Pending human validation

The 20-case QA set and evidence spans are approved. Before a RAG release, run
the separately approved GPT-only v2.4 development diagnostic. Only a measured
10/10 answerable, 3/3 correct-refusal, 13/13 structural result can open the
judge-only runner. Then run the different-family Claude judge, manually label
the blinded 10-output worksheet (seven answerable plus all three unanswerable
outputs for the single-generator run), validate agreement, and run the
untouched seven-case holdout exactly once. Commit every reproducible generator,
judge, worksheet, citation, usage, and negative-result artifact.

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

### Smoke-test checklist

1. `/healthz` returns `{"status":"ok"}`.
2. BM25 search returns scored PubMed records and safe highlighted snippets.
3. Hybrid search uses the frozen cache; deleting or corrupting its identity must disable it.
4. One approved answer contains clickable, chunk-bound citations.
5. One frozen unanswerable question returns `insufficient_evidence`.
6. Personalized/dosing advice is refused before generation.
7. Per-IP limits and the daily budget return retrieval evidence, not a generated fallback.
8. No raw query or server secret appears in application logs or browser code.

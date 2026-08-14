# Deployment and Release Gates

## Complete locally

The repository supports a read-only offline release check:

```text
python run_project.py
```

It validates frozen core hashes, builds the index, runs Boolean and BM25
evaluation, and validates the approved QA set, chunk manifests, embedding
ledger, selected hybrid configuration, and development contexts. Corruption
exits nonzero. Generator/judge/holdout gates remain `TBD` until their evidence
exists.

## Pending human validation

The 20-case QA set and evidence spans are approved. Before a RAG release, run
the three-model development bake-off, manually label the blinded 10-output
judge worksheet, validate agreement, and run the untouched seven-case holdout.
Commit the reproducible generation, judge, and citation artifacts.

## Pending credentials and deployment

Set `OPENROUTER_API_KEY` only in the deployment environment after a paid-run budget and model pricing are approved. `--live-eval` reports cost/readiness only while the RAG gates are incomplete; it does not make a request. Hosting, secret management, monitoring, and a production endpoint are not yet deployed or approved.

### Planned Railway environment

- `OPENROUTER_API_KEY` -- required for query embeddings and grounded answers.
- `EMBEDDING_CACHE_PATH=artifacts/section5/embeddings_256_64.npz` -- selected cache matching the frozen RAG configuration.
- `DAILY_ANSWER_CAP=200` -- default single-process budget guard.
- `TRUST_PROXY_HEADERS=true` -- required on Railway so rate limits use the forwarded client IP; leave false for direct local serving.

Planned start command:

```text
python -m uvicorn app:app --host 0.0.0.0 --port $PORT
```

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

# Deployment and Release Gates

## Complete locally

The repository supports a read-only offline release check:

```text
python run_project.py
```

It validates frozen core hashes, builds the index, runs Boolean and BM25 evaluation, and validates committed chunk manifests. Core corruption exits nonzero. Missing or gated RAG assets are shown as `TBD` without changing that result.

## Pending human approval

Before a RAG release, approve and commit the QA set, evidence spans, faithfulness rubric/labels, and refusal cases. Commit reproducible semantic/hybrid/citation evaluation outputs bound to the corpus and chunk hashes.

## Pending credentials and deployment

Set `OPENROUTER_API_KEY` only in the deployment environment after a paid-run budget and model pricing are approved. `--live-eval` reports cost/readiness only while the RAG gates are incomplete; it does not make a request. Hosting, secret management, monitoring, and a production endpoint are not yet deployed or approved.

### Planned Railway environment

- `OPENROUTER_API_KEY` -- required for query embeddings and grounded answers.
- `EMBEDDING_CACHE_PATH` -- committed or mounted cache that matches the frozen RAG configuration.
- `DAILY_ANSWER_CAP=200` -- default single-process budget guard.

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

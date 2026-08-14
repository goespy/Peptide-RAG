# Cost Report

## Development spend

The hash-bound ledger is
[`artifacts/section5/embedding_usage.json`](artifacts/section5/embedding_usage.json).
OpenRouter routed `openai/text-embedding-3-small` to OpenAI at the listed
`$0.02/M` input-token price on 2026-08-14.

| Work | Inputs | Input tokens | Provider calls | Cost |
|---|---:|---:|---:|---:|
| 128/32 corpus chunks | 4,565 | 889,325 | 46 | $0.01778650 |
| 256/64 corpus chunks | 2,440 | 744,444 | 25 | $0.01488888 |
| 512/128 corpus chunks | 2,007 | 687,680 | 21 | $0.01375360 |
| Development questions | 13 | 180 | 1 | $0.00000360 |
| **Embedding total** | **9,025** | **2,321,629** | **93** | **$0.04643258** |

The first 13-case generator bake-off was approved with a conservative `$0.86`
ceiling. The immutable provider responses report:

| Work | Input tokens | Output tokens | Provider calls | Cost |
|---|---:|---:|---:|---:|
| Three generator candidates | 142,254 | 24,726 | 83 | $0.009190435 |
| Claude Sonnet 4.6 judge | 92,446 | 10,608 | 39 | $0.436458000 |
| **Bake-off total** | **234,700** | **35,334** | **122** | **$0.445648435** |
| **Recorded OpenRouter development total** | **2,556,329** | **35,334** | **215** | **$0.492081015** |

The generator/judge total is recomputed from all 39 saved rows in
`data/rag_bakeoff_outputs.json` and bound in
`data/rag_bakeoff_reanalysis.json`. Railway usage and coding-agent subscription
tokens remain `TBD` or `unknown/not exposed`; they are not represented as zero.

## Production projection

The workload assumptions are frozen even though current provider prices are not:

- 2 sessions per user per month.
- 10 generated questions per session.
- 20 Q&A calls per user per month.
- 4,000 generation-input tokens and 300 output tokens per call.
- One query embedding per question; corpus embeddings are generated once and cached.

If `Pi`, `Po`, and `Pe` are the current dollars per million input,
output, and query-embedding tokens, and `Eq` is the measured average query-token
count, the variable AI cost per user is:

```text
20 * ((4,000 * Pi + 300 * Po + Eq * Pe) / 1,000,000)
```

Prices must be revalidated on the report date and recorded with direct source
links before replacing these cells:

| Users | Q&A calls/month | Generation input tokens | Generation output tokens | Variable AI cost | Railway |
|---:|---:|---:|---:|---:|---:|
| 100 | 2,000 | 8,000,000 | 600,000 | TBD | TBD |
| 1,000 | 20,000 | 80,000,000 | 6,000,000 | TBD | TBD |
| 10,000 | 200,000 | 800,000,000 | 60,000,000 | TBD | TBD |
| 100,000 | 2,000,000 | 8,000,000,000 | 600,000,000 | TBD | TBD |

The present in-memory rate limiter and daily counter are single-process. Even
if model spend is acceptable, 10,000 and 100,000-user scenarios require load
testing and distributed limits before the single-instance architecture can be
claimed to support them.

`python run_project.py --live-eval` remains a readiness check and makes no paid
calls. A second development run requires a versioned experiment, a fresh price
check, and explicit owner cost approval. The untouched holdout remains blocked
on owner validation of the judge and an accepted generator.

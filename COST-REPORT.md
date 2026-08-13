# Cost Report

## Development spend

No provider usage ledger is committed in this repository. Actual development API calls, input/output tokens, and spend are therefore **TBD**, not zero.

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

`python run_project.py --live-eval` prints this status and requires `OPENROUTER_API_KEY` before any future live evaluator could make calls. It intentionally makes no network or paid calls while QA approval and evaluation gates are incomplete.

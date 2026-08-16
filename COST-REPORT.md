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
| GPT-only v2.2 diagnostic | 26,969 | 3,916 | 14 | $0.001690265 |
| GPT-only v2.3 diagnostic | 24,273 | 851 | 12 | $0.001138185 |
| GPT-only v2.4 diagnostic | 30,697 | 1,132 | 15 | $0.001276115 |
| GPT v2.4 Claude judge | 31,388 | 2,414 | 13 | $0.130374000 |
| GPT-only v2.5 diagnostic | 35,889 | 1,088 | 17 | $0.001613150 |
| GPT v2.5 Claude judge-v2 | 32,232 | 1,798 | 13 | $0.123666000 |
| **Known OpenRouter development total** | **2,737,777** | **46,533** | **299** | **$0.751838730** |

The generator/judge total is recomputed from all 39 saved rows in
`data/rag_bakeoff_outputs.json` and bound in
`data/rag_bakeoff_reanalysis.json`. Railway has not been deployed yet, so actual
hosting usage is `unknown/not exposed`. Coding-agent subscription tokens are
also `unknown/not exposed`; neither quantity is represented as zero.

Generator-v2 made 123 provider calls under an approved `$0.04` ceiling and a
`$0.03457764` conservative estimate, but the saved provider responses did not
expose complete token or cost fields. Its actual spend is therefore recorded as
`unknown/not exposed` and is not silently included as zero in the known total.
The owner-approved v2.4 generator run cost `$0.001276115`, and its separately
gated judge cost `$0.130374000`. The prompt-only v2.5 correction cost
`$0.001613150` for generation. Its 13-call Claude Sonnet 4.6 judge-v2 run had a
conservative `$0.235458` estimate under a frozen `$0.25` cap and actually cost
`$0.123666000`. Both v2.4 and v2.5 passed the 10/10 answerable, 3/3 refusal, and
13/13 structural generator gates. The v2.5 judge measured `0.900`
answered-only faithfulness and `0.900` citation correctness; owner validation is
pending, and the seven-case QA holdout remains untouched.

## Production projection

The workload assumptions are frozen:

- 2 sessions per user per month.
- 10 generated questions per session.
- 20 Q&A calls per user per month.
- 4,000 generation-input tokens and 300 output tokens per call.
- One query embedding per question; corpus embeddings are generated once and cached.

The price snapshot was checked on **2026-08-16**. OpenRouter listed
`openai/gpt-oss-20b` at `$0.03/M` input tokens and `$0.13/M` output tokens, and
`openai/text-embedding-3-small` at `$0.02/M` input tokens:

- [Frozen 2026-08-16 model-catalog artifact](artifacts/section5/model_candidates_judge_refresh.json)
- [GPT-OSS 20B pricing](https://openrouter.ai/openai/gpt-oss-20b/pricing)
- [text-embedding-3-small pricing](https://openrouter.ai/openai/text-embedding-3-small/pricing)

The measured development-query average is `180 / 13 = 13.846` embedding tokens
per question. With `Pi=0.03`, `Po=0.13`, `Pe=0.02`, and `Eq=13.846`, the
variable AI cost per user is:

```text
20 * ((4,000 * Pi + 300 * Po + Eq * Pe) / 1,000,000)
    = $0.00318554 per user per month
```

| Users | Q&A calls/month | Generation input tokens | Generation output tokens | Variable AI cost | Railway baseline | Combined lower bound |
|---:|---:|---:|---:|---:|---:|---:|
| 100 | 2,000 | 8,000,000 | 600,000 | $0.32 | $5.00 | $5.32 |
| 1,000 | 20,000 | 80,000,000 | 6,000,000 | $3.19 | $5.00 | $8.19 |
| 10,000 | 200,000 | 800,000,000 | 60,000,000 | $31.86 | $5.00 minimum | $36.86 minimum |
| 100,000 | 2,000,000 | 8,000,000,000 | 600,000,000 | $318.55 | $5.00 minimum | $323.55 minimum |

Railway's Hobby plan is `$5/month` and includes the first `$5` of measured
resource usage. Current listed resource rates are `$10/GB-month` RAM,
`$20/vCPU-month`, `$0.05/GB` egress, and `$0.15/GB-month` volume storage. The
combined figures above therefore use the subscription minimum, not an invented
resource estimate. Actual deployment CPU, memory, egress, and sleeping behavior
must be measured before replacing the lower bounds:

- [Railway plans and usage pricing](https://docs.railway.com/pricing/plans)
- [Railway cost controls](https://docs.railway.com/pricing/cost-control)

The present in-memory rate limiter and daily counter are single-process. Even
if model spend is acceptable, 10,000 and 100,000-user scenarios require load
testing and distributed limits before the single-instance architecture can be
claimed to support them.

`python run_project.py --live-eval` remains a readiness check and makes no paid
calls. Each generator, judge, and holdout stage requires its own versioned
experiment, fresh price check, and explicit owner cost approval. The untouched
holdout remains blocked on owner validation of the judge and an accepted
generator.

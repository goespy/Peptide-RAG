# Claude Opus Development Bake-Off Review

- Review date: 2026-08-14
- Reviewer: Claude Opus through Claude Code 2.1.229 and the project owner's Claude subscription
- Access: read-only; no OpenRouter call, paid API call, edit, or holdout access
- Source outputs SHA-256: `83341CDA4FBF5DD4DFBD97E61933140CD9B9DA0CD1495BE411566C1FE8D12423`

## Audit trail

The first broad read-only audit reached its ten-minute execution ceiling and returned no text, so it is not counted as an approval. A narrower audit of the selection, accounting, and owner-validation code completed in 183.6 seconds and returned:

```text
VERDICT: CHANGES_REQUIRED
```

Claude identified two blockers:

1. A model that answered no questions received an undefined citation score and was removed from winner eligibility. Gemma therefore appeared to win partly because it was the only model that answered at all, despite answering only 2 of 10 answerable cases.
2. The judge-validation worksheet contained the answer but omitted the question, retrieved evidence, and answerability label required for independent human faithfulness, relevance, citation, and refusal judgments.

Claude also confirmed that combined generator-plus-judge arithmetic was internally correct, while noting that the result artifact omitted a realized total. It recommended keeping the holdout blocked and warned against changing candidate-selection rules after seeing results without recording the change.

## Resolutions

- A no-answer candidate now receives citation correctness `0.0` rather than an undefined score.
- Reports now expose answerable-case count, answer rate, correct-answer rate, and overall answerability classification.
- The selected model is explicitly marked provisional pending owner validation; selection is not an acceptance gate.
- Actual provider calls, input tokens, output tokens, and spend are aggregated from all 39 immutable rows.
- Worksheet version 2 includes the frozen question, answerability, acceptable answer, and five retrieved chunks for every sampled output.
- Worksheet evidence, questions, answers, QA artifact, contexts artifact, and source outputs are hash-bound and tamper-checked.
- Citation correctness may be marked not applicable for an evidence-free refusal; the resulting smaller validation denominator is reported honestly.
- The holdout remains untouched.

## Corrected offline reanalysis

The immutable paid outputs were reanalyzed without provider calls:

| Model | Answered / 10 answerable | Correct-answer rate | Faithfulness | Correct-refusal rate | Actual cost |
| --- | ---: | ---: | ---: | ---: | ---: |
| `google/gemma-3-12b-it` | 2 | 0.200 | 0.385 | 1.000 | $0.1486864 |
| `openai/gpt-oss-20b` | 0 | 0.000 | 0.308 | 1.000 | $0.142342395 |
| `qwen/qwen3.7-flash` | 0 | 0.000 | 0.308 | 1.000 | $0.15461964 |

Total provider-reported usage was 122 calls, 234,700 input tokens, 35,334 output tokens, and `$0.445648435`. Gemma remains the lexicographic development selection under the pre-registered ordering, but it is not accepted for holdout or deployment.

## Next gate

The project owner must label the ten evidence-bearing worksheet samples. Because the present run answered only one sampled case, citation-agreement validation may be inconclusive. No holdout evaluation should run unless judge validation passes and the weak answerable-case performance is explicitly resolved through a versioned development experiment rather than a silent post-hoc change.

# Owner Return Checklist

This is the remaining human-only gate. Do not open `data/qa.json`, the judged
output JSON, or any holdout artifact while labeling; doing so would weaken the
blind comparison.

## 1. Label the ten blind development outputs

Read only [`JUDGE-VALIDATION-REVIEW.md`](JUDGE-VALIDATION-REVIEW.md). For each
opaque `review-*` case, edit the matching `owner_label` object in
`data/judge_validation_v2_5_worksheet.json`.

For an answered response:

- set `reviewer` to your name;
- set `faithful`, `relevant`, `citations_correct`, and `refusal_correct` to
  `true` or `false`, using only the displayed question, answer, and evidence.

For a refusal:

- set `reviewer` to your name;
- leave `faithful` and `citations_correct` as `null`;
- set `relevant` and `refusal_correct` to `true` or `false` from the displayed
  evidence.

The current validator deliberately stops at the first missing label. After all
ten cases are labeled, run:

```bash
python scripts/render_judge_validation.py --overwrite
python scripts/validate_judge.py --validate
python run_project.py
```

Do not continue if the validation report fails. Review the rubric and preserve
the failed report as evidence before creating a disjoint validation version.

## 2. Open the untouched holdout only after owner validation passes

Run these commands in order. The two paid commands shown with `--max-cost-usd`
print and enforce their hard ceilings. The holdout runner also reserves a
conservative per-case maximum before every provider call. The catalog refresh
is a read-only provider metadata request, not a model inference.

```bash
python scripts/freeze_generator_selection.py
python scripts/export_rag_holdout_contexts.py --cache artifacts/section5/embeddings_256_64.npz --max-cost-usd 0.01 --confirm-cost
python scripts/refresh_model_catalog.py --output artifacts/section5/holdout_model_catalog.json
python scripts/run_rag_holdout.py --estimate-only
python scripts/run_rag_holdout.py --live --max-cost-usd 0.50 --confirm-cost
python run_project.py
```

If a live holdout process is interrupted, inspect the error and rerun the exact
live command with `--resume-partial`. Completed cases are skipped, and any retry
is refused before a call if cumulative conservative reservations would exceed
the original approved cap. If all seven output rows exist but summary creation
was interrupted, run `python scripts/run_rag_holdout.py --finalize-saved`.

## 3. Release only after the offline runner passes the holdout

Deploy the exact passing commit to Railway, configure the environment from
`.env.example`, and run the smoke checklist in [`DEPLOYMENT.md`](DEPLOYMENT.md)
using development QA cases only (never the untouched holdout questions). The
smoke command checks this mechanically against the frozen QA split. Then
capture the cited-answer/refusal screenshot, record the 3–5 minute demo, and
replace the remaining submission placeholders where applicable in `README.md`,
`DEMO-SCRIPT.md`, `SOCIAL-POST.md`, and `SELF-EVALUATION.md` with
artifact-backed values and URLs.

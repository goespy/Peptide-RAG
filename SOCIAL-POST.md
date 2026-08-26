# Social Post Draft

This release-ready draft is not evidence that a public post has been published. Publishing remains an owner action.

> I built Peptide-RAG, a curiosity-driven therapeutic-peptide literature search and grounded-Q&A system.
>
> The key lesson: retrieval has to be measured, not vibed. I started with a hand-labeled PubMed oracle, implemented the positional index, Boolean retrieval, BM25, IR metrics, and hybrid fusion from scratch, then tested grounded answers and refusals against frozen evidence spans.
>
> Across all 15 lexical queries, Boolean NDCG@10 was `0.716` and tuned BM25 descriptively reached `0.926`. On the frozen lexical holdout, tuning moved BM25 NDCG@10 from `0.838` to `0.841` (`+0.003`). Frozen development hybrid chunk Recall@5 reached `0.810`. The untouched QA holdout achieved `1.000` faithfulness, relevancy, citation, correct-answer, and correct-refusal rates (5/5 answers, 2/2 refusals, 7/7 structural checks; p95 `8,445.535 ms`).
>
> Demo recording: pending owner publication.
>
> Repository: https://github.com/goespy/Peptide-RAG
>
> App: https://peptide-rag-production.up.railway.app
>
> Known limitations: small pooled judgments, abstract-only evidence, and a small QA holdout.
>
Required attachments before posting:

- Architecture image: `docs/architecture-overview.svg`
- Search-results screenshot: `artifacts/section6/search-results.jpg`
- Cited-answer screenshot: `artifacts/section6/cited-answer.png`
- Evidence-refusal screenshot: `artifacts/section6/evidence-refusal.png`
- Public-post URL after publication: `TBD`

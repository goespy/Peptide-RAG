# Social Post Draft

Do not publish this draft until every bracketed value is backed by the final frozen artifacts.

> I built Peptide-RAG, a therapeutic-peptide literature search and grounded-Q&A system for the Gauntlet AI Relevance Engine assignment.
>
> The key lesson: retrieval has to be measured, not vibed. I started with a hand-labeled PubMed oracle, implemented the positional index, Boolean retrieval, BM25, IR metrics, and hybrid fusion from scratch, then tested grounded answers and refusals against frozen evidence spans.
>
> Across all 15 lexical queries, Boolean NDCG@10 was `0.716` and tuned BM25 descriptively reached `0.926`. On the frozen lexical holdout, tuning moved BM25 NDCG@10 from `0.838` to `0.841` (`+0.003`). Frozen development hybrid chunk Recall@5 reached `0.810`. The untouched QA holdout reached [FAITHFULNESS] faithfulness and [REFUSAL RATE] correct refusal.
>
> Demo: [DEMO URL]
>
> Repository: https://github.com/goespy/Peptide-RAG
>
> App: [DEPLOYED URL]
>
> Known limitations: small pooled judgments, abstract-only evidence, and a small QA holdout.
>
> @GauntletAI

Required attachments before posting:

- Architecture image: `docs/architecture-overview.svg`
- Search-results screenshot: `artifacts/section6/search-results.jpg`
- Cited-answer or refusal screenshot: `TBD`
- Public-post URL after publication: `TBD`

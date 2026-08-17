# Demo Script (3–5 Minutes)

This is a recording checklist, not evidence that a demo has been recorded. The public app is live; recording remains an owner action.

## 0:00–0:35 — Problem and method

Explain that fluent answers can hide weak retrieval. Show the frozen 2,000-record PubMed corpus, qrels v2, and the rule that every change is evaluated rather than selected by feel.

## 0:35–1:20 — Oracle and lexical baseline

Show the Boolean-versus-BM25 metrics in the README. Demonstrate one query where Boolean ordering misses relevant material and BM25 ranks useful records earlier. Mention the reference-library differential and the untouched holdout.

## 1:20–2:10 — Search experience

Run a BM25 search in the public app. Show ranks, scores, highlighted snippets, PubMed links, and the measured metrics panel.

## 2:10–3:05 — Grounded RAG behavior

Ask one approved **development** answerable question. Show the retrieved chunks, a concise answer, and clickable citations that bind to those chunks. Then ask the approved development unanswerable `qa17` question and show the model-originated `insufficient_evidence`, not an infrastructure fail-close. Do not publish an untouched holdout question in the smoke test or recording.

## 3:05–3:45 — Architecture and verification

Show the analyzer/index/BM25 → chunking/embeddings/RRF → structured answer/judge flow. Run `python run_project.py` and summarize test count, latency/memory measurements, cost controls, and known limitations.

## Evidence to insert before recording

- Architecture visual: `docs/architecture-overview.svg`
- Ranked-search screenshot: `artifacts/section6/search-results.jpg`
- Live cited-answer screenshot: `artifacts/section6/cited-answer.png`
- Live evidence-refusal screenshot: `artifacts/section6/evidence-refusal.png`
- Public URL: https://peptide-rag-production.up.railway.app
- Final deployed runtime commit: `4c709558dd0796a416022eeebf7436259927e0de` (CI run `32071964692`; `307` tests). The final documentation/evidence suite passes `308` tests locally, and the offline runner passes.
- Frozen development hybrid Recall@5 / Evidence Hit@5: `0.810 / 0.900`
- Untouched holdout faithfulness / relevancy / citation / correct answer / correct refusal: `1.000 / 1.000 / 1.000 / 1.000 / 1.000` (5/5 answers; 2/2 refusals; 7/7 structure; p95 `8,445.535 ms`)
- Controlled rate-limit smoke: HTTP `429` exactly at probe `30`
- Recording URL: `TBD`

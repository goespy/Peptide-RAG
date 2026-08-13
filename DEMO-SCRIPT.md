# Demo Script (3–5 Minutes)

This is a recording checklist, not evidence that a demo has been recorded. Replace every `TBD` only after the corresponding frozen artifact or public URL exists.

## 0:00–0:35 — Problem and method

Explain that fluent answers can hide weak retrieval. Show the frozen 2,000-record PubMed corpus, qrels v2, and the rule that every change is evaluated rather than selected by feel.

## 0:35–1:20 — Oracle and lexical baseline

Show the Boolean-versus-BM25 metrics in the README. Demonstrate one query where Boolean ordering misses relevant material and BM25 ranks useful records earlier. Mention the reference-library differential and the untouched holdout.

## 1:20–2:10 — Search experience

Run a BM25 search in the public app. Show ranks, scores, highlighted snippets, PubMed links, and the measured metrics panel.

## 2:10–3:05 — Grounded RAG behavior

After the QA, chunk, model, and holdout gates pass, ask one frozen answerable question. Show the retrieved chunks, a concise answer, and clickable citations that bind to those chunks. Then ask one frozen unanswerable question and show `insufficient_evidence`.

## 3:05–3:45 — Architecture and verification

Show the analyzer/index/BM25 → chunking/embeddings/RRF → structured answer/judge flow. Run `python run_project.py` and summarize test count, latency/memory measurements, cost controls, and known limitations.

## Evidence to insert before recording

- Public URL: `TBD`
- Tested release commit: `TBD`
- Final test count: `TBD`
- Final hybrid Recall@5 / Evidence Hit@5: `TBD`
- Faithfulness / refusal results: `TBD`
- Recording URL: `TBD`

# Demo Script (3–5 Minutes)

This is a recording checklist, not evidence that a demo has been recorded. Replace every `TBD` only after the corresponding frozen artifact or public URL exists.

## 0:00–0:35 — Problem and method

Explain that fluent answers can hide weak retrieval. Show the frozen 2,000-record PubMed corpus, qrels v2, and the rule that every change is evaluated rather than selected by feel.

## 0:35–1:20 — Oracle and lexical baseline

Show the Boolean-versus-BM25 metrics in the README. Demonstrate one query where Boolean ordering misses relevant material and BM25 ranks useful records earlier. Mention the reference-library differential and the untouched holdout.

## 1:20–2:10 — Search experience

Run a BM25 search in the public app. Show ranks, scores, highlighted snippets, PubMed links, and the measured metrics panel.

## 2:10–3:05 — Grounded RAG behavior

After the QA, chunk, model, and holdout gates pass, ask one approved **development** answerable question. Show the retrieved chunks, a concise answer, and clickable citations that bind to those chunks. Then ask one development unanswerable question and show a model-originated `insufficient_evidence`, not an infrastructure fail-close. The smoke CLI checks both questions against the frozen development split. Do not publish an untouched holdout question in the smoke test or recording.

## 3:05–3:45 — Architecture and verification

Show the analyzer/index/BM25 → chunking/embeddings/RRF → structured answer/judge flow. Run `python run_project.py` and summarize test count, latency/memory measurements, cost controls, and known limitations.

## Evidence to insert before recording

- Architecture visual: `docs/architecture-overview.svg`
- Ranked-search screenshot: `artifacts/section6/search-results.jpg`
- Public URL: `TBD`
- Last CI-tested hardening baseline: `5a20e30` (`305` tests; the final post-holdout release commit remains `TBD`)
- Current local and CI-tested post-audit count: `306`
- Frozen development hybrid Recall@5 / Evidence Hit@5: `0.810 / 0.900`
- Frozen development answered-only faithfulness / correct refusal: `0.900 / 1.000`; untouched holdout result: `TBD`
- Recording URL: `TBD`

# Peptide-RAG

A from-scratch relevance engine over a custom corpus of therapeutic-peptide research from PubMed. The project follows the Gauntlet AI rule **measured, not vibed**: freeze human relevance judgments before tuning retrieval, calculate metrics ourselves, and do not add an LLM until lexical retrieval is objectively evaluated.

## Project status

- [x] Assignment constraints and analysis/index architecture documented
- [x] Executable PubMed corpus fetcher with offline tests
- [x] Corpus snapshot generated and reviewed
- [x] Deterministic 15-document qrels review packet generated
- [x] Fifteen-query provisional judgment set (`data/qrels.json`)
- [x] Pooled version-2 judgment set with 75 graded query-document pairs (`data/qrels_v2.json`)
- [x] Positional inverted index
- [x] Boolean `AND`/`OR` retrieval
- [x] Red precision@k and recall@k harness
- [x] Lucene-style BM25 ranking implemented from scratch
- [x] MRR and graded NDCG implemented from scratch
- [x] Differential scores/rankings match `bm25s` on all 15 frozen queries
- [x] Ranked CLI results with scores, snippets, and PubMed links
- [x] Section 3 Boolean/BM25 baseline saved as JSON and Markdown
- [x] Section 4 lexical tuning and hardening
- [x] Section 5 RAG foundations: approved QA oracle, chunk artifacts, retrieval contracts, grounded-answer validation, and local web shell
- [x] Project-owner approval of the 20-case QA oracle
- [x] Paid semantic/chunk development evaluation and frozen hybrid retrieval configuration
- [x] Three-model development bake-off preserved and reanalyzed as a negative result
- [x] GPT-only v2.2 through v2.5 diagnostics measured; v2.4 and v2.5 reached 10/10 answerable, 3/3 correct refusals, and 13/13 structural validity
- [x] Claude judge-v2 development run completed for v2.5: 0.900 answered-only faithfulness, 1.000 relevancy, 0.900 citation correctness, and 1.000 correct refusal
- [x] Blind, evidence-bound 10-output owner worksheet frozen with oracle answers, answerability targets, and Claude verdicts hidden
- [ ] Owner judge labeling, untouched QA holdout, and public Railway deployment
- [x] Section 6 offline release-check, CI, self-evaluation, cost, and Railway config foundations

The Day 1 baseline and strengthened evaluation are measured separately below. Version 1 remains the untouched known-item baseline; version 2 contains 75 pooled judgments with documented `0`/`1`/`2` rationales.

### Frozen corpus snapshot

| Records | Records without abstracts | Duplicate PMIDs | Blank titles | SHA-256 |
|---:|---:|---:|---:|---|
| 2,000 | 81 | 0 | 0 | `231E048971C34EF9203ED3BB20587DDE4C95141AC7EFD2746C85C078A844212C` |

The exact query returned 2,000 PMIDs, below the configured maximum of 3,000. Records without abstracts are retained as title-only documents. This hash identifies the corpus version that the first qrels must reference.

## Prerequisites and setup

- Python 3.11 or newer
- Internet access for corpus fetching and, later, explicitly approved hosted RAG evaluation
- A valid contact email for NCBI E-utilities

Create an environment and install the runtime dependencies:

```bash
python -m venv .venv
```

Activate it on macOS/Linux with `source .venv/bin/activate`, or on PowerShell with `.\.venv\Scripts\Activate.ps1`, then run:

```bash
python -m pip install -r requirements.txt
```

## Build the PubMed corpus

The script runs the assignment's exact peptide query, requests no more than 3,000 PMIDs in relevance order, fetches XML batches of at most 200 records, and writes only after the full result has been parsed successfully.

```bash
python scripts/fetch_pubmed.py --email you@example.com
```

Alternatively set `NCBI_EMAIL`; an optional API key can be supplied through `NCBI_API_KEY` or `--api-key`. The script still waits at least 0.34 seconds between requests. To run a small smoke fetch or replace an existing corpus:

```bash
python scripts/fetch_pubmed.py --email you@example.com --retmax 2 --output data/smoke.jsonl
python scripts/fetch_pubmed.py --email you@example.com --overwrite
```

The default output is `data/corpus.jsonl`. Existing output is never replaced without `--overwrite`. Each UTF-8 line has exactly this shape:

```json
{"id":"12345678","title":"Paper title","text":"Abstract text"}
```

Run the network-free verification suite with:

```bash
python -m unittest discover -s tests -v
```

To include the test-only reference-BM25 differential, install the development
dependencies first:

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
```

## Prepare the judgment-set review

Generate the fixed, peptide-stratified candidate set and validate/render the AI suggestions:

```bash
python scripts/prepare_qrels_review.py
python scripts/render_qrels_review.py
```

The outputs are `data/qrels_candidates.json`, `data/qrels_draft.json`, and `QRELS-REVIEW.md`. They remain explicitly marked as draft/audit artifacts rather than masquerading as the oracle. After an independent Claude Code cross-check, a structured q11 reviewer override, Codex validation, and project-owner authorization to progress, the approved provisional set was frozen as `data/qrels.json`. Reruns require `--overwrite` so reviewed material is not replaced accidentally.

### Strengthen the judgment set with pooling

After preserving the version-1 baseline, create a deterministic five-paper review pool for each query and render the human worksheet:

```bash
python scripts/prepare_qrels_pool.py
python scripts/render_qrels_pool_review.py
```

The outputs are `data/qrels_pool.json` and `QRELS-POOL-REVIEW.md`: 75 query-document pairs consisting of the 15 existing judgments plus 60 initially unjudged candidates. Candidate selection uses strict Boolean matching followed by deterministic distinct-term coverage, but it never assigns relevance. Every available title and abstract was reviewed under the documented rubric: `0` (not relevant), `1` (partially relevant), or `2` (directly relevant). The project owner individually approved q01-q08, then explicitly delegated q09-q15 and the all-query consistency audit to Codex; that provenance is recorded rather than presented as fully manual labeling. Freeze the validated review reproducibly with:

```bash
python scripts/freeze_qrels_v2.py
```

This produces `data/qrels_v2.json` while leaving the version-1 `data/qrels.json` and metrics untouched. The completed set contains 75 judgments: 40 grade-2, 25 grade-1, and 10 grade-0. Use `--overwrite` only to reproduce an intentionally changed reviewed artifact.

### NCBI use and attribution

This project uses the [NCBI E-utilities](https://www.ncbi.nlm.nih.gov/books/NBK25501/) and follows the [usage guidance](https://www.ncbi.nlm.nih.gov/books/NBK25497/) to identify the tool and developer email, batch requests, and stay below three requests per second without relying on an API key. For a full 3,000-record job, NCBI recommends large jobs run on weekends or between 9:00 PM and 5:00 AM Eastern time.

NCBI does not endorse this project. PubMed records and abstracts may contain material protected by copyright. Users are responsible for following the [NCBI disclaimer and copyright notice](https://www.ncbi.nlm.nih.gov/home/about/policies/).

## One-command contract

From a clean clone, the complete Day 1 evaluation runs with:

```bash
python run_day1.py
```

It verifies the qrels-to-corpus SHA-256 binding, builds the positional index from scratch, evaluates all 15 Boolean queries, and prints paste-ready Markdown. Evaluate the strengthened qrels separately with:

```bash
python run_day1.py --qrels data/qrels_v2.json
```

Direct search is also available:

```bash
python search.py "BPC 157 tissue regeneration" --mode bm25 --top-k 10
python search.py "BPC 157 tissue regeneration" --mode boolean --top-k 10
```

Run the reproducible full lexical baseline with:

```bash
python run_ir_eval.py --qrels data/qrels_v2.json --modes boolean,bm25
```

The command writes [`artifacts/section3/baseline.json`](artifacts/section3/baseline.json)
and [`artifacts/section3/baseline.md`](artifacts/section3/baseline.md), including
corpus/qrels hashes, code revision, exact configuration, rankings, and metrics.

The current whole-project offline check is:

```bash
python run_project.py
```

It makes no network or paid calls. It verifies the frozen core hashes, rebuilds
the index, recomputes Boolean/BM25 metrics, validates every committed chunk
manifest, replays the development bake-off from saved outputs, and labels the
owner-validation/holdout gate as `TBD` instead of inventing a pass. `python
run_project.py --live-eval` is a readiness check only; it never calls a
provider.

## Section 5 RAG workflow

All 20 cases passed project-owner review and are frozen in `data/qa.json` with
exact evidence spans and corpus/qrels hashes. The QA SHA-256 is
`196A09FD748ABED07E30B59501703CBAEA0F1B9A1B0EF5738DBE323E93DBA725`.
The approval history remains in [`QA-REVIEW.md`](QA-REVIEW.md) and
`data/qa_draft.json`.

```bash
python scripts/freeze_qa.py
```

The three candidate chunk snapshots are already deterministic and hash-bound:

| Window | Overlap | Chunks | Artifact SHA-256 |
|---:|---:|---:|---|
| 128 words | 32 | 4,565 | `81B45B34429419CCC44C42AA27FFB7715012491F731A64576A14DBC7BAB7D41D` |
| 256 words | 64 | 2,440 | `85B62B8AF56DAFD6AE4A1D1B5C87DA950828BB767FDDF9633445E53CA5567B9C` |
| 512 words | 128 | 2,007 | `AF83690E677750BC7E884DF04C70FB203D3103938FA141AB8D9EA031966FCFAF` |

Each candidate now has a corpus-bound embedding cache. The evaluator uses only
the 10 answerable development cases to select chunk size and RRF alpha, while a
separate 13-question embedding cache supports all development contexts. The
holdout remains excluded. Repeating the command without a key reproduced the
evaluation JSON, Markdown, frozen configuration, and contexts byte-for-byte.

```bash
python scripts/embed_chunks.py --chunks artifacts/section5/chunks_128_32.jsonl --output artifacts/section5/embeddings_128_32.npz
python scripts/embed_chunks.py --chunks artifacts/section5/chunks_256_64.jsonl --output artifacts/section5/embeddings_256_64.npz
python scripts/embed_chunks.py --chunks artifacts/section5/chunks_512_128.jsonl --output artifacts/section5/embeddings_512_128.npz
python scripts/evaluate_chunks.py --candidate 128_32 artifacts/section5/chunks_128_32.jsonl artifacts/section5/chunks_128_32.jsonl.manifest.json artifacts/section5/embeddings_128_32.npz --candidate 256_64 artifacts/section5/chunks_256_64.jsonl artifacts/section5/chunks_256_64.jsonl.manifest.json artifacts/section5/embeddings_256_64.npz --candidate 512_128 artifacts/section5/chunks_512_128.jsonl artifacts/section5/chunks_512_128.jsonl.manifest.json artifacts/section5/embeddings_512_128.npz --embedding-model openai/text-embedding-3-small --query-cache artifacts/section5/query_embeddings.npz --output-json artifacts/section5/chunk_evaluation.json --output-md artifacts/section5/chunk_evaluation.md --frozen-config artifacts/section5/frozen_config.json --contexts-output data/rag_development_contexts.json
```

The original three-family bake-off is immutable negative evidence. After its
measured provider and answer-quality failures, the project owner selected GPT-OSS
as the only continuing generator; Qwen and Gemma are not silently retried. The
current catalog still records all original candidates plus the different-family
Anthropic judge so historical runs remain reproducible. Live execution rejects
a catalog older than 24 hours and requires a separate explicit cost bound for
each paid stage:

```bash
python scripts/run_generator_diagnostic.py --estimate-only
# The owner-approved v2.5 run used this command and stayed below the bound:
python scripts/run_generator_diagnostic.py --live --max-cost-usd 0.02 --confirm-cost

# v2.5 passed 10/10, 3/3, and 13/13, so the judge config is now frozen:
python scripts/freeze_generator_judge_config.py --hard-cost-cap-usd 0.25
python scripts/run_generator_judge.py --estimate-only
# After a separate approval of the displayed judge-only maximum:
python scripts/run_generator_judge.py --live --max-cost-usd 0.25 --confirm-cost
python scripts/validate_judge.py
python scripts/render_judge_validation.py
# Label the 10 unique outputs from their frozen question, response, and evidence.
# The GPT-only worksheet contains 7 answerable and all 3 unanswerable cases.
# Oracle answers, answerability targets, and Claude verdicts remain hidden;
# no holdout case appears in this worksheet.
python scripts/validate_judge.py --validate
# This creates the accepted-selection artifact only after the blind labels pass.
python scripts/freeze_generator_selection.py
# The seven query embeddings have their own frozen $0.01 hard ceiling.
python scripts/export_rag_holdout_contexts.py --cache artifacts/section5/embeddings_256_64.npz --max-cost-usd 0.01 --confirm-cost
# Freeze a fresh availability/price snapshot; it is separate from development.
python scripts/refresh_model_catalog.py --output artifacts/section5/holdout_model_catalog.json
# Inspect the frozen generator + Claude judge-v2 maximum before the one-shot run.
python scripts/run_rag_holdout.py --estimate-only
python scripts/run_rag_holdout.py --live --max-cost-usd 0.50 --confirm-cost
```

The readable packet is [`JUDGE-VALIDATION-REVIEW.md`](JUDGE-VALIDATION-REVIEW.md).
Its cases use opaque, hash-mixed IDs. For a valid blind review, do not consult
`data/qa.json` or the judged-output JSON until all owner labels are frozen.

The first paid development run is preserved as a negative result. All 39 rows
were structurally valid and judged, but Qwen and GPT-OSS answered none of the
10 answerable questions and Gemma answered only two. The corrected offline
reanalysis therefore marks Gemma as a provisional lexicographic selection,
not an accepted generator. The holdout remains untouched. Claude Opus's
independent findings and the fixes are recorded in
[`artifacts/section5/claude_bakeoff_review.md`](artifacts/section5/claude_bakeoff_review.md).

Four later GPT-only generator diagnostics changed neither QA nor retrieval and
made no holdout calls. v2.2 measured 8/10 answerable and 2/3 correct
refusals for `$0.001690265`; v2.3 measured 9/10, 3/3, and 13/13 structural
validity for `$0.001138185`. v2.3's remaining QA04 failure is documented as a
model refusal despite direct supplied human evidence at context rank 5. v2.4
uses one general refusal-reconsideration stage, contains no QA ID or expected
answer, and measured 10/10 answerable, 3/3 correct refusals, and 13/13
structurally valid for `$0.001276115`. QA04 was answered only after the general
reconsideration, showing that its prior miss was synthesis behavior rather than
missing retrieved evidence. Its first Claude judge measured `0.800`
answered-only faithfulness and exposed scope overclaims in qa02 and qa07. The
general v2.5 prompt correction changed no QA, retrieval, contexts, model, or
holdout data and cost `$0.001613150`; it preserved 10/10, 3/3, and 13/13.
Judge-v2 then cost `$0.123666000` and measured `0.900` answered-only
faithfulness, `1.000` relevancy, `0.900` citation correctness, and `1.000`
correct refusal. The remaining qa08 failure is an over-citation: citation 4 does
not independently support every clause in a sentence also supported by
citations 1 and 2. Claude Opus returned `PASS` on the corrected judge-v2 evidence
chain before that paid run. Owner validation and holdout remain pending.

The bridge to holdout is hash-bound end to end: the accepted-selection artifact
requires the exact v2.5 10/3/13 generator result, complete judge-v2 evidence,
and a passing blind owner report. Context export is one-shot and refuses an
existing target. The holdout runner then requires that selection, its exact
prompt/model/catalog hashes, and those frozen contexts; it has no overwrite
mode. It saves all seven raw rows even when the preregistered quality thresholds
fail, and only writes the final generator configuration after offline replay
passes. A crashed post-call finalization can use `--finalize-saved` without
making another paid call. Ordinary offline reruns make no provider calls. The
independent Section 5/6 code audit and resolution trail is saved in
[`artifacts/section6/claude_opus_review.md`](artifacts/section6/claude_opus_review.md).

The local application is available without provider credentials:

```bash
python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`. Boolean and tuned BM25 search work entirely
offline. Semantic/hybrid modes activate only when `EMBEDDING_CACHE_PATH` points
to a cache matching the selected chunk artifact. Grounded Q&A fails closed as
retrieval-only until that measured configuration exists; `OPENROUTER_API_KEY`
is server-side only.

`railway.json` now pins Railpack, the `$PORT` start command, `/healthz`, and a
bounded restart policy. This is deployment packaging, not a deployment claim:
no Railway project, public domain, or Railway secret has been created yet.

## Metrics Report

### Section 5 RAG metrics

The following are development-set retrieval measurements over the selected
256-word/64-word-overlap chunks. They are not QA holdout results. Hybrid uses
weighted RRF with `alpha=0.5`; selection and all losing configurations are saved
in [`artifacts/section5/chunk_evaluation.json`](artifacts/section5/chunk_evaluation.json).

| Retrieval mode | Recall@1 | Recall@3 | Recall@5 | Recall@10 | Evidence Hit@5 |
|---|---:|---:|---:|---:|---:|
| Lexical chunks | 0.470 | 0.590 | 0.710 | 0.830 | 0.900 |
| Semantic chunks | 0.350 | 0.690 | 0.710 | 0.730 | 0.800 |
| Hybrid chunks | 0.520 | 0.590 | 0.810 | 0.900 | 0.900 |

| Generator | Answered / 10 | Correct answer | Faithfulness | Correct refusal | Relevancy | Citation correctness | Cost | Status |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| `qwen/qwen3.7-flash` | 0 | 0.000 | 0.308 | 1.000 | 0.846 | 0.000 | $0.154619640 | Development failure |
| `openai/gpt-oss-20b` | 0 | 0.000 | 0.308 | 1.000 | 0.846 | 0.000 | $0.142342395 | Development failure |
| `google/gemma-3-12b-it` | 2 | 0.200 | 0.385 | 1.000 | 0.769 | 1.000 on 2 answers | $0.148686400 | Provisional selection only |

These are Claude-judge development scores, not human-validated or holdout
scores. Citation correctness for Gemma has a denominator of only two answers;
it does not erase eight missed answerable questions. Total provider-reported
bake-off spend was `$0.445648435` across 122 calls, 234,700 input tokens, and
35,334 output tokens, below the approved `$0.86` ceiling. The immutable live
outputs and corrected offline reanalysis are saved in
`data/rag_bakeoff_outputs.json` and `data/rag_bakeoff_reanalysis.json`.

Later GPT-only generator diagnostics and their separately gated judge results
are reported without overwriting earlier negative evidence:

| Experiment | Answered / 10 | Refusals / 3 | Structural / 13 | Generator cost | Answered faithfulness | Citation correctness | Judge cost | Status |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| GPT v2.2 | 8 | 2 | 13 | $0.001690265 | TBD | TBD | — | Did not reach judge gate |
| GPT v2.3 | 9 | 3 | 13 | $0.001138185 | TBD | TBD | — | Did not reach judge gate |
| GPT v2.4 | 10 | 3 | 13 | $0.001276115 | 0.800 | 1.000 | $0.130374000 | Superseded development result |
| GPT v2.5 | 10 | 3 | 13 | $0.001613150 | 0.900 | 0.900 | $0.123666000 | Owner validation pending |

Final generator acceptance and holdout metrics remain `TBD` until owner
validation of the Claude judge and a versioned response-quality decision. See
[`SELF-EVALUATION.md`](SELF-EVALUATION.md) for the live gate status and
[`COST-REPORT.md`](COST-REPORT.md) for measured embedding spend.

### Section 3 ranked-retrieval baseline

- Qrels: frozen pooled version 2
- BM25: Lucene variant, `k1=1.2`, `b=0.75`
- Cutoffs: `1`, `3`, `5`, and `10`
- Reference differential: every positive score/ranking matched `bm25s==0.3.9`
  within `1e-6` on the same analyzed corpus and all 15 queries

| Mode | MRR | P@1 | P@3 | P@5 | P@10 | R@1 | R@3 | R@5 | R@10 | NDCG@1 | NDCG@3 | NDCG@5 | NDCG@10 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Boolean | 0.967 | 0.933 | 0.622 | 0.507 | 0.253 | 0.220 | 0.428 | 0.570 | 0.570 | 0.933 | 0.725 | 0.716 | 0.716 |
| BM25 | 0.967 | 0.933 | 0.756 | 0.640 | 0.407 | 0.229 | 0.538 | 0.749 | 0.940 | 0.933 | 0.850 | 0.860 | 0.921 |
| BM25 delta | +0.000 | +0.000 | +0.134 | +0.133 | +0.154 | +0.009 | +0.110 | +0.179 | +0.370 | +0.000 | +0.125 | +0.144 | +0.205 |

BM25 produces a large recall and ranking-quality gain without changing the
corpus or judgments. It fixes q11's known first-result failure, but q09 becomes
a first-rank miss. That failure is retained: partial matching improves the
overall system while still admitting high-scoring irrelevant documents. These
are untouched defaults, not tuned Section 4 results.

The pre-registered development/holdout division is hash-bound in
[`data/eval_split.json`](data/eval_split.json). Section 4 may tune only on the
development queries; the holdout cannot be used for selection.

### Section 4 measured tuning and hardening

The development-only grid selected the frozen configuration in
[`data/lexical_config.json`](data/lexical_config.json): baseline analysis,
`k1=0.8`, `b=0.75`, and no proximity boost. Greek-letter expansion tied the
baseline, stopword removal reduced development quality, and every positive
proximity boost reduced development NDCG@10 and Recall@10. The simpler baseline
analysis therefore remained in place.

The frozen configuration was then evaluated on `q09`, `q10`, `q11`, `q13`, and
`q15` without further tuning:

| Holdout mode | MRR | P@5 | R@5 | NDCG@3 | NDCG@5 | NDCG@10 |
|---|---:|---:|---:|---:|---:|---:|
| Untuned BM25 | 0.900 | 0.440 | 0.467 | 0.720 | 0.694 | 0.838 |
| Tuned BM25 | 0.900 | 0.480 | 0.507 | 0.714 | 0.708 | 0.841 |
| Delta | +0.000 | +0.040 | +0.040 | -0.006 | +0.014 | +0.003 |

This is a modest tradeoff, not a universal improvement: deeper precision,
recall, and NDCG improve, while shallow NDCG@3 slips slightly. Over all 15
queries, the tuned system descriptively reaches Recall@10 `0.957` and NDCG@10
`0.926`, compared with the untouched BM25 baseline's `0.940` and `0.921`.

The one-shot output and complete development grid are preserved in
[`artifacts/section4/holdout.md`](artifacts/section4/holdout.md) and
[`artifacts/section4/development_experiments.md`](artifacts/section4/development_experiments.md).
The first holdout command computed the frozen run but crashed before exposing
or writing metrics because a Python Boolean was misspelled as JSON `true`; only
that serialization token was fixed before the successful unchanged rerun.

The selected configuration benchmark measured five cold builds and 100 runs of
each frozen query:

| Operation | Median | p95 | Peak traced allocation |
|---|---:|---:|---:|
| Cold index build | 11,503.597 ms | 11,597.386 ms | 111,491,576 bytes |
| BM25 query | 2.490 ms | 7.743 ms | 162,277 bytes |

`tracemalloc` adds significant overhead to the build measurement; these are
observations from the recorded Windows development environment, not service
level guarantees. See
[`artifacts/section4/benchmark_lexical.md`](artifacts/section4/benchmark_lexical.md).
Claude's specification-only audit challenged the practical significance of the
small holdout gains; the concern and decision not to retune on holdout are
preserved in [`artifacts/section4/claude_review.md`](artifacts/section4/claude_review.md).

### Historical Day 1 Boolean report

- Command: `python run_day1.py`
- Qrels: version 1
- Corpus: 2,000 documents, SHA-256 `231E048971C34EF9203ED3BB20587DDE4C95141AC7EFD2746C85C078A844212C`
- Index: 19,023 terms
- Ordering: numeric PMID, because the Day 1 Boolean baseline is deliberately unranked

These are the preserved version-1 known-item results. Consequently, unjudged relevant papers may be counted as non-relevant and measured precision may be lower than true precision. They are retained as historical evidence rather than overwritten by version 2.

### Version 1 aggregate results

| Evaluated queries | Mean Precision@1 | Mean Precision@3 | Mean Precision@5 | Mean Recall@1 | Mean Recall@3 | Mean Recall@5 |
|---:|---:|---:|---:|---:|---:|---:|
| 15 | 0.933 | 0.333 | 0.200 | 0.933 | 1.000 | 1.000 |

### Version 1 per-query results

| Query ID | Query | Relevant | Retrieved | Precision@1 | Precision@3 | Precision@5 | Recall@1 | Recall@3 | Recall@5 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| q01 | BPC 157 liver necrosis rats | 1 | 6 | 1.000 | 0.333 | 0.200 | 1.000 | 1.000 | 1.000 |
| q02 | GHK Cu cognitive decline neurodegeneration | 1 | 1 | 1.000 | 0.333 | 0.200 | 1.000 | 1.000 | 1.000 |
| q03 | thymosin beta 4 backbone conformations | 1 | 1 | 1.000 | 0.333 | 0.200 | 1.000 | 1.000 | 1.000 |
| q04 | ipamorelin oral bioavailability growth hormone | 1 | 4 | 1.000 | 0.333 | 0.200 | 1.000 | 1.000 | 1.000 |
| q05 | tesamorelin HIV lipodystrophy clinical trials | 1 | 9 | 1.000 | 0.333 | 0.200 | 1.000 | 1.000 | 1.000 |
| q06 | epitalon drosophila lifespan increase | 1 | 1 | 1.000 | 0.333 | 0.200 | 1.000 | 1.000 | 1.000 |
| q07 | MOTS c metabolic obesity insulin resistance | 1 | 14 | 1.000 | 0.333 | 0.200 | 1.000 | 1.000 | 1.000 |
| q08 | PT 141 melanocortin sexual dysfunction | 1 | 9 | 1.000 | 0.333 | 0.200 | 1.000 | 1.000 | 1.000 |
| q09 | BPC 157 gastric duodenal lesions rats | 1 | 12 | 1.000 | 0.333 | 0.200 | 1.000 | 1.000 | 1.000 |
| q10 | GHK Cu healing ACL reconstruction rat | 1 | 1 | 1.000 | 0.333 | 0.200 | 1.000 | 1.000 | 1.000 |
| q11 | TB 500 wound healing metabolites | 1 | 2 | 0.000 | 0.333 | 0.200 | 0.000 | 1.000 | 1.000 |
| q12 | ipamorelin growth hormone release receptor | 1 | 3 | 1.000 | 0.333 | 0.200 | 1.000 | 1.000 | 1.000 |
| q13 | tesamorelin HIV visceral adipose triglycerides safety | 1 | 2 | 1.000 | 0.333 | 0.200 | 1.000 | 1.000 | 1.000 |
| q14 | epitalon evening melatonin cortisol secretion | 1 | 1 | 1.000 | 0.333 | 0.200 | 1.000 | 1.000 | 1.000 |
| q15 | MOTS c mitochondrial polymorphism longevity | 1 | 1 | 1.000 | 0.333 | 0.200 | 1.000 | 1.000 | 1.000 |

The red signal is q11: numeric PMID ordering places a doping-control paper first and the directly relevant TB-500 wound-healing paper second. Recall@1 therefore fails while Recall@3 succeeds. That result is preserved for the later ranked-retrieval phase rather than tuned away.

### Version 2 pooled results

- Command: `python run_day1.py --qrels data/qrels_v2.json`
- Judgments: 75 across the same 15 queries; grades greater than zero count as relevant
- Pooling limitation: depth-5 lexical pooling is stronger than a known-item set but is not exhaustive

| Evaluated queries | Mean Precision@1 | Mean Precision@3 | Mean Precision@5 | Mean Recall@1 | Mean Recall@3 | Mean Recall@5 |
|---:|---:|---:|---:|---:|---:|---:|
| 15 | 0.933 | 0.622 | 0.507 | 0.220 | 0.428 | 0.570 |

| Query ID | Query | Relevant | Retrieved | Precision@1 | Precision@3 | Precision@5 | Recall@1 | Recall@3 | Recall@5 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| q01 | BPC 157 liver necrosis rats | 3 | 6 | 1.000 | 0.667 | 0.600 | 0.333 | 0.667 | 1.000 |
| q02 | GHK Cu cognitive decline neurodegeneration | 5 | 1 | 1.000 | 0.333 | 0.200 | 0.200 | 0.200 | 0.200 |
| q03 | thymosin beta 4 backbone conformations | 4 | 1 | 1.000 | 0.333 | 0.200 | 0.250 | 0.250 | 0.250 |
| q04 | ipamorelin oral bioavailability growth hormone | 5 | 4 | 1.000 | 1.000 | 0.800 | 0.200 | 0.600 | 0.800 |
| q05 | tesamorelin HIV lipodystrophy clinical trials | 5 | 9 | 1.000 | 1.000 | 1.000 | 0.200 | 0.600 | 1.000 |
| q06 | epitalon drosophila lifespan increase | 3 | 1 | 1.000 | 0.333 | 0.200 | 0.333 | 0.333 | 0.333 |
| q07 | MOTS c metabolic obesity insulin resistance | 5 | 14 | 1.000 | 1.000 | 1.000 | 0.200 | 0.600 | 1.000 |
| q08 | PT 141 melanocortin sexual dysfunction | 5 | 9 | 1.000 | 1.000 | 1.000 | 0.200 | 0.600 | 1.000 |
| q09 | BPC 157 gastric duodenal lesions rats | 5 | 12 | 1.000 | 1.000 | 1.000 | 0.200 | 0.600 | 1.000 |
| q10 | GHK Cu healing ACL reconstruction rat | 5 | 1 | 1.000 | 0.333 | 0.200 | 0.200 | 0.200 | 0.200 |
| q11 | TB 500 wound healing metabolites | 3 | 2 | 0.000 | 0.333 | 0.200 | 0.000 | 0.333 | 0.333 |
| q12 | ipamorelin growth hormone release receptor | 4 | 3 | 1.000 | 0.667 | 0.400 | 0.250 | 0.500 | 0.500 |
| q13 | tesamorelin HIV visceral adipose triglycerides safety | 5 | 2 | 1.000 | 0.667 | 0.400 | 0.200 | 0.400 | 0.400 |
| q14 | epitalon evening melatonin cortisol secretion | 3 | 1 | 1.000 | 0.333 | 0.200 | 0.333 | 0.333 | 0.333 |
| q15 | MOTS c mitochondrial polymorphism longevity | 5 | 1 | 1.000 | 0.333 | 0.200 | 0.200 | 0.200 | 0.200 |

Version 2 reveals that the version-1 Recall@5 of `1.000` was a known-item artifact: strict implicit-AND retrieval misses many partially or directly relevant papers that omit one query term. Precision rises because formerly unjudged relevant results now have labels, while recall falls because the denominator is a meaningfully larger relevant set. This is the intended “measured, not vibed” red signal for ranked and less brittle retrieval.

## Day 1 chronological checklist

1. **Fetch and freeze the corpus.** Run `scripts/fetch_pubmed.py`, validate every JSONL record, and record the file hash.
2. **Construct `data/qrels.json`.** Follow the fixed selection process in `ARCHITECTURE.md`; manually write 15 natural information needs and label relevant PMIDs before engine-assisted searching.
3. **Build the index from scratch.** Analyze titles and abstracts with the documented shared tokenizer; store immutable positional postings, document frequencies, documents, and lengths using Python data structures only.
4. **Implement Boolean retrieval.** Support deterministic `AND`/`OR`, `AND` precedence, and implicit `AND`, plus empty and unknown-term robustness.
5. **Stub and run the red harness.** Calculate precision@k and recall@k directly against the frozen qrels, print aggregate and per-query Markdown tables, and paste the unaltered output into this report before tuning.

Architecture details and the judgment protocol live in [`ARCHITECTURE.md`](ARCHITECTURE.md). The required one-page AI-development submission is [`AI-LOG.md`](AI-LOG.md), with the complete chronological audit trail retained in [`AI-LOG-DETAIL.md`](AI-LOG-DETAIL.md). The current release evidence and remaining gates are tracked in [`SELF-EVALUATION.md`](SELF-EVALUATION.md), [`COST-REPORT.md`](COST-REPORT.md), and [`DEPLOYMENT.md`](DEPLOYMENT.md). [`DEMO-SCRIPT.md`](DEMO-SCRIPT.md) and [`SOCIAL-POST.md`](SOCIAL-POST.md) are explicitly unfilled submission templates, not claims that those deliverables have been published.

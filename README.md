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
- [ ] Section 5 semantic/hybrid RAG

The Day 1 baseline and strengthened evaluation are measured separately below. Version 1 remains the untouched known-item baseline; version 2 contains 75 pooled judgments with documented `0`/`1`/`2` rationales.

### Frozen corpus snapshot

| Records | Records without abstracts | Duplicate PMIDs | Blank titles | SHA-256 |
|---:|---:|---:|---:|---|
| 2,000 | 81 | 0 | 0 | `231E048971C34EF9203ED3BB20587DDE4C95141AC7EFD2746C85C078A844212C` |

The exact query returned 2,000 PMIDs, below the configured maximum of 3,000. Records without abstracts are retained as title-only documents. This hash identifies the corpus version that the first qrels must reference.

## Prerequisites and setup

- Python 3.11 or newer
- Internet access for the corpus fetch only
- A valid contact email for NCBI E-utilities

Create an environment and install the sole runtime dependency:

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

## Metrics Report

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

Architecture details and the judgment protocol live in [`ARCHITECTURE.md`](ARCHITECTURE.md). AI-assisted development evidence lives in [`AI-LOG.md`](AI-LOG.md).

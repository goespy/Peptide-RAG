# Peptide-RAG

A from-scratch relevance engine over a custom corpus of therapeutic-peptide research from PubMed. The project follows the Gauntlet AI rule **measured, not vibed**: freeze human relevance judgments before tuning retrieval, calculate metrics ourselves, and do not add an LLM until lexical retrieval is objectively evaluated.

## Day 1 status

- [x] Assignment constraints and analysis/index architecture documented
- [x] Executable PubMed corpus fetcher with offline tests
- [x] Corpus snapshot generated and reviewed
- [x] Deterministic 15-document qrels review packet generated
- [x] Fifteen-query provisional judgment set (`data/qrels.json`)
- [x] Positional inverted index
- [x] Boolean `AND`/`OR` retrieval
- [x] Red precision@k and recall@k harness

The Day 1 baseline is measured below. The version-1 qrels are a reviewed known-item set. A separate 75-pair pooling worksheet is now ready for human labels; the reported metrics remain unchanged until those judgments are approved as qrels version 2.

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

The outputs are `data/qrels_pool.json` and `QRELS-POOL-REVIEW.md`: 75 query-document pairs consisting of the 15 existing judgments plus 60 unjudged candidates. Candidate selection uses strict Boolean matching followed by deterministic distinct-term coverage, but it never assigns relevance. A human must read each paper and choose `0` (not relevant), `1` (partially relevant), or `2` (directly relevant), with a reason. Only then should the approved labels become qrels version 2. Use `--overwrite` to regenerate either artifact intentionally.

### NCBI use and attribution

This project uses the [NCBI E-utilities](https://www.ncbi.nlm.nih.gov/books/NBK25501/) and follows the [usage guidance](https://www.ncbi.nlm.nih.gov/books/NBK25497/) to identify the tool and developer email, batch requests, and stay below three requests per second without relying on an API key. For a full 3,000-record job, NCBI recommends large jobs run on weekends or between 9:00 PM and 5:00 AM Eastern time.

NCBI does not endorse this project. PubMed records and abstracts may contain material protected by copyright. Users are responsible for following the [NCBI disclaimer and copyright notice](https://www.ncbi.nlm.nih.gov/home/about/policies/).

## One-command contract

From a clean clone, the complete Day 1 evaluation runs with:

```bash
python run_day1.py
```

It verifies the qrels-to-corpus SHA-256 binding, builds the positional index from scratch, evaluates all 15 Boolean queries, and prints paste-ready Markdown. Direct search is also available:

```bash
python search.py "BPC 157 tissue regeneration"
```

## Metrics Report

- Command: `python run_day1.py`
- Qrels: version 1
- Corpus: 2,000 documents, SHA-256 `231E048971C34EF9203ED3BB20587DDE4C95141AC7EFD2746C85C078A844212C`
- Index: 19,023 terms
- Ordering: numeric PMID, because the Day 1 Boolean baseline is deliberately unranked

These are the preserved version-1 known-item results. Consequently, unjudged relevant papers may be counted as non-relevant and measured precision may be lower than true precision. The in-progress pooled review is not included in these values; version-2 results will be added alongside them after human approval.

### Aggregate results

| Evaluated queries | Mean Precision@1 | Mean Precision@3 | Mean Precision@5 | Mean Recall@1 | Mean Recall@3 | Mean Recall@5 |
|---:|---:|---:|---:|---:|---:|---:|
| 15 | 0.933 | 0.333 | 0.200 | 0.933 | 1.000 | 1.000 |

### Per-query results

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

## Day 1 chronological checklist

1. **Fetch and freeze the corpus.** Run `scripts/fetch_pubmed.py`, validate every JSONL record, and record the file hash.
2. **Construct `data/qrels.json`.** Follow the fixed selection process in `ARCHITECTURE.md`; manually write 15 natural information needs and label relevant PMIDs before engine-assisted searching.
3. **Build the index from scratch.** Analyze titles and abstracts with the documented shared tokenizer; store immutable positional postings, document frequencies, documents, and lengths using Python data structures only.
4. **Implement Boolean retrieval.** Support deterministic `AND`/`OR`, `AND` precedence, and implicit `AND`, plus empty and unknown-term robustness.
5. **Stub and run the red harness.** Calculate precision@k and recall@k directly against the frozen qrels, print aggregate and per-query Markdown tables, and paste the unaltered output into this report before tuning.

Architecture details and the judgment protocol live in [`ARCHITECTURE.md`](ARCHITECTURE.md). AI-assisted development evidence lives in [`AI-LOG.md`](AI-LOG.md).

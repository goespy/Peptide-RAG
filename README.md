# Peptide-RAG

A from-scratch relevance engine over a custom corpus of therapeutic-peptide research from PubMed. The project follows the Gauntlet AI rule **measured, not vibed**: freeze human relevance judgments before tuning retrieval, calculate metrics ourselves, and do not add an LLM until lexical retrieval is objectively evaluated.

## Day 1 status

- [x] Assignment constraints and analysis/index architecture documented
- [x] Executable PubMed corpus fetcher with offline tests
- [x] Corpus snapshot generated and reviewed
- [ ] Fifteen-query manual judgment set (`data/qrels.json`)
- [ ] Positional inverted index
- [ ] Boolean `AND`/`OR` retrieval
- [ ] Red precision@k and recall@k harness

No search or metric result is claimed yet. `TBD` in the report means “not measured,” not zero.

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

### NCBI use and attribution

This project uses the [NCBI E-utilities](https://www.ncbi.nlm.nih.gov/books/NBK25501/) and follows the [usage guidance](https://www.ncbi.nlm.nih.gov/books/NBK25497/) to identify the tool and developer email, batch requests, and stay below three requests per second without relying on an API key. For a full 3,000-record job, NCBI recommends large jobs run on weekends or between 9:00 PM and 5:00 AM Eastern time.

NCBI does not endorse this project. PubMed records and abstracts may contain material protected by copyright. Users are responsible for following the [NCBI disclaimer and copyright notice](https://www.ncbi.nlm.nih.gov/home/about/policies/).

## One-command contract

The eventual clean-clone Day 1 contract will be:

```bash
python run_day1.py
```

**This command is intentionally not available yet.** It will be added with the search-engine phase and will validate the frozen corpus/qrels, build the index, run Boolean evaluation, and print a paste-ready Markdown metrics report. Today, corpus setup and offline tests use the explicit commands above.

## Metrics Report

Status: **TBD — the qrels, retriever, and metrics harness have not been implemented.**

The known-item judgment set will be provisional and not exhaustively pooled. Consequently, unjudged relevant papers may be counted as non-relevant and measured precision may be lower than true precision.

### Aggregate results

| Evaluated queries | P@1 | P@3 | P@5 | Recall@1 | Recall@3 | Recall@5 |
|---:|---:|---:|---:|---:|---:|---:|
| TBD | TBD | TBD | TBD | TBD | TBD | TBD |

### Per-query results

| Query ID | Query | Relevant PMIDs | Retrieved @ k | Precision@k | Recall@k |
|---|---|---:|---:|---:|---:|
| TBD | TBD | TBD | TBD | TBD | TBD |

Paste the metrics harness's generated tables here without manually editing the values. Record the qrels version, corpus SHA-256, `k` values, and command alongside the first measured run.

## Day 1 chronological checklist

1. **Fetch and freeze the corpus.** Run `scripts/fetch_pubmed.py`, validate every JSONL record, and record the file hash.
2. **Construct `data/qrels.json`.** Follow the fixed selection process in `ARCHITECTURE.md`; manually write 15 natural information needs and label relevant PMIDs before engine-assisted searching.
3. **Build the index from scratch.** Analyze titles and abstracts with the documented shared tokenizer; store immutable positional postings, document frequencies, documents, and lengths using Python data structures only.
4. **Implement Boolean retrieval.** Support deterministic `AND`/`OR`, `AND` precedence, and implicit `AND`, plus empty and unknown-term robustness.
5. **Stub and run the red harness.** Calculate precision@k and recall@k directly against the frozen qrels, print aggregate and per-query Markdown tables, and paste the unaltered output into this report before tuning.

Architecture details and the judgment protocol live in [`ARCHITECTURE.md`](ARCHITECTURE.md). AI-assisted development evidence lives in [`AI-LOG.md`](AI-LOG.md).

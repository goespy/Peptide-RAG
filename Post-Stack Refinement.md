# Post-Stack Refinement

This is the third and final pass over the project's initial architecture
decisions. It records the implemented stack accurately; earlier proposed tools
that were not adopted are not presented as work performed.

## 12. Security vulnerabilities and controls

| Risk | Control and residual limitation |
| --- | --- |
| Secrets committed or exposed to JavaScript | `.env` is ignored, `.env.example` contains no value, keys are read server-side, and Railway secrets are still a deployment gate. |
| Corpus/model text rendered as HTML | The client builds DOM nodes and assigns untrusted text with `textContent`; highlighted snippets split only the server's marker syntax. |
| Unsupported medical advice | Personalized or prescriptive dosing is refused before inference; all output is labeled research-only. This is not a medical device. |
| Hallucinated or mismatched citations | Structured answers are rebound to the supplied top-five chunks; unknown, unused, or uncited factual claims fail closed. |
| Provider outage or budget exhaustion | Retrieval evidence is returned without a generated fallback. An answer slot is reserved before awaiting the provider. |
| Public abuse | Query and `k` bounds, per-IP sliding limits, and a daily one-process generation cap. Multiple replicas would require shared rate/budget state. |
| Proxy spoofing | Forwarded addresses are trusted only when `TRUST_PROXY_HEADERS=true`; deployment must ensure the edge proxy overwrites the header. |
| Dependency/supply-chain drift | Runtime dependencies have bounded major versions; `bm25s` is pinned and test-only. CI validates on Python 3.11. |
| Evaluation leakage | Development/holdout splits, blind human labels, one-shot non-overwritable artifacts, SHA-256 bindings, and offline replay protect the result. A small oracle remains an acknowledged limitation. |

## 13. File structure and project organization

```text
data/                  Frozen corpus, qrels, QA, and saved model evidence
artifacts/section3/    Untuned Boolean/BM25 baseline
artifacts/section4/    Tuning grid, lexical holdout, benchmark, review
artifacts/section5/    Chunks, caches, RAG configs, diagnostics, reviews
artifacts/section6/    Cost/memory reports and release visuals
docs/                  Current architecture visual
scripts/               Reproducible acquisition/evaluation/freeze commands
src/                   Production analysis, index, retrieval, RAG, service
static/                Vanilla web interface
tests/                 Unit, differential, property, integrity, API tests
.github/workflows/     Python 3.11 CI and offline release verification
```

The repository is a single Python project. Production code never imports the
reference BM25 package. Immutable measured artifacts and mutable source code
are separated by directory and bound by hashes.

## 14. Naming conventions and code style

- PEP 8-style `snake_case` functions/variables and `PascalCase` classes.
- Frozen dataclasses for public configurations and result contracts.
- Type hints on public interfaces and deterministic tuple/list ordering.
- `unittest` is the sole test runner; no mixed pytest convention is claimed.
- No Ruff or Black configuration is currently committed, so neither is claimed
  as a release gate. `git diff --check`, Python compilation, tests, and CI are
  the enforced formatting/correctness checks.

## 15. Testing strategy

- **Unit tests:** analyzer, postings, Boolean parsing, BM25 components, metrics,
  snippets, chunking, embeddings, generation, judge, and service behavior.
- **Differential test:** Custom Lucene-style BM25 scores and rankings match
  pinned `bm25s==0.3.9` within `1e-6`, including all 15 frozen corpus queries.
- **Property/robustness tests:** IDF monotonicity, diminishing term-frequency
  gains, deletion integrity, round-trip identity, empty/OOV/Unicode/long input,
  deterministic reruns, and non-mutation after failure.
- **Artifact/integration tests:** Corpus/qrels/QA/cache/config hashes, dev/holdout
  separation, saved-output replay, cost ceilings, blind worksheet invariants,
  FastAPI fallback/rate behavior, and cross-platform source hashing.
- **User-surface evidence:** The in-app Browser MCP exercises the rendered local
  app; release-asset tests verify the current architecture SVG and ranked
  screenshot signature.
- **Release commands:** `python -m unittest discover -s tests` and
  `python run_project.py`. The latter is offline, read-only, and makes no paid
  request.

## 16. Recommended tooling and developer experience

- **Coding/review:** Codex for primary implementation; Claude Code Opus for
  independent, read-only review; Browser MCP for local user-path verification.
- **Source control:** Git plus GitHub CLI; changes land on section/release
  branches with CI before merge.
- **Runtime:** Python 3.11 virtual environment with separate runtime and
  development requirements.
- **Provider workflow:** Explicit `--estimate-only`, maximum-cost, and
  confirmation gates; all provider outputs and usage metadata are saved for
  offline replay.
- **Clean-clone check:** Install dependencies, then run `python run_project.py`.
  It validates every available frozen artifact and reports unfinished gates as
  `TBD` rather than converting them into passes or zeros.

# Pre-Search: Peptide-RAG

This records the architecture decisions made before implementation and the
measured evidence gathered afterward. “Initial decision” describes the plan at
the time; “measured confirmation” is explicitly retrospective and does not
pretend that later results were known in advance.

## Phase 1 — Define the constraints

### 1. Scale and load profile

- **Initial decision:** Optimize first for solo development and review over a
  few-thousand-document corpus. Index construction may happen at startup;
  retrieval must be interactive once the index is loaded.
- **Public-app envelope:** One Railway process, 30 searches/minute/IP, five
  generated answers/minute/IP, and 200 answer attempts/day by default. Search
  remains available when generation is disabled.
- **Measured confirmation:** The frozen corpus has 2,000 records. The offline
  development machine measured a 3.519-second cold service start and a
  278,310,912-byte peak RSS with the selected embedding cache. Railway remains
  the authoritative production measurement after deployment.

### 2. Budget and cost ceiling

- **Initial decision:** Core corpus construction, indexing, retrieval, and
  metrics must run locally. Hosted embeddings and generation are acceptable
  only for explicitly approved, cost-capped RAG experiments.
- **Launch target:** Keep the initial Railway and provider spend below
  approximately `$10/month`; degrade to retrieval-only instead of spending
  beyond the configured answer budget.
- **Measured confirmation:** Known OpenRouter development spend is
  `$0.751838730`; missing provider usage is recorded as `unknown/not exposed`,
  never zero. The dated cost model projects `$0.32` variable AI cost at 100
  users plus Railway's `$5` monthly plan baseline.

### 3. Time to ship

- **Initial decision:** A five-day progression: red Boolean baseline, BM25 and
  full metrics, measured lexical tuning, then the optional RAG extension.
- **Tradeoff:** Prefer simple, inspectable Python and immutable artifacts over
  a scalable distributed architecture. Performance work is measurement-driven,
  not speculative.
- **Iteration cadence:** A section closes only after tests, saved metrics,
  independent review, a commit, and CI. Negative experiments remain in the
  repository.

### 4. Compliance and regulatory posture

- **Data:** Public PubMed titles/abstracts only; no user accounts or stored
  patient records. This is not a HIPAA clinical application.
- **Product boundary:** Research-literature summaries only. Personalized or
  prescriptive dosing requests are refused before generation, and every page
  displays a research-only medical disclaimer and NCBI attribution.
- **Privacy:** Raw user queries are not logged by application code. API keys
  remain server-side. Same-origin browser access and HTML-safe rendering are
  the baseline.

### 5. Team and skill constraints

- **Team:** One project owner using Codex as primary pair programmer and Claude
  Code as an independent reviewer. Human approval remains distinct from both.
- **Runtime:** Python 3.11. Production dependencies are `requests`, NumPy,
  FastAPI, and Uvicorn.
- **Hard constraint:** Production analysis, positional indexing, Boolean/BM25
  retrieval, rank fusion, and evaluation metrics are hand-built. A reference
  IR implementation is test-only.

## Phase 2 — Architecture discovery

### 6. Hosting and deployment

- **Choice:** A single FastAPI monolith deployed on Railway with Railpack,
  `/healthz`, a bounded restart policy, and one process so the local daily
  answer counter has honest scope.
- **Why:** It is the smallest hosted surface that supports local retrieval,
  provider-backed answers, static UI files, health checks, and retrieval-only
  fallback within the budget.
- **CI/CD:** GitHub Actions on Python 3.11 runs the complete unit/differential
  suite and the offline release replay, then fails if verification mutates
  tracked evidence.

### 7. Authentication and authorization

- **Choice:** No accounts or authentication for this public research demo.
- **Controls:** Same-origin requests, 500-character query limit, bounded `k`,
  per-IP rate limits, one-process daily answer cap, and server-only secrets.
- **Non-goal:** No RBAC, multi-tenancy, saved search history, or user profiles.

### 8. Database and data layer

- **Choice:** No database or vector database. Versioned JSONL/JSON/NPZ
  artifacts are loaded read-only at runtime.
- **Search state:** An in-memory positional inverted index stores postings,
  document frequency, documents, lengths, and title boundaries. NumPy performs
  brute-force cosine similarity over a normalized, hash-bound embedding cache.
- **Why:** At 2,000 documents this is auditable, reproducible, inexpensive, and
  avoids infrastructure that would obscure the project's search mechanics.

### 9. Backend and API architecture

- **Choice:** One REST service with `GET /healthz`, `GET /api/metrics`,
  `POST /api/search`, and `POST /api/answer`.
- **Execution:** Synchronous indexing/retrieval/provider work runs outside the
  async event loop. Provider failures and exhausted budgets return the same
  retrieved evidence rather than a fabricated answer.
- **Non-goal:** No background queue, microservices, GraphQL, or mutable server
  database.

### 10. Frontend framework and rendering

- **Choice:** Vanilla HTML, CSS, and JavaScript served by FastAPI.
- **Why:** The project needs a small interactive research interface, not SEO or
  a frontend build pipeline. `textContent` and DOM-created elements keep corpus
  and model text from becoming executable HTML.
- **Capabilities:** Ranked search, stable scores, highlighted snippets, PubMed
  links, grounded answer/refusal display, clickable citations, and measured
  metrics.

### 11. Third-party integrations

- **NCBI E-utilities:** Reproducible corpus acquisition with contact email,
  batching, rate limiting, retry, and atomic output.
- **OpenRouter:** Hosted embeddings, GPT-OSS generation, and a different-family
  Claude judge. Models/settings and provider metadata are frozen per experiment;
  caches make offline replay free of paid calls.
- **GitHub and Railway:** Source/CI and deployment respectively. Provider or
  budget failure leaves the custom local search engine usable.

Phase 3 is maintained in [Post-Stack Refinement.md](Post-Stack%20Refinement.md).

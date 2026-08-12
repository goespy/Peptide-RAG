# Post-Stack Refinement.md

## Phase 3: Post-Stack Refinement

### 12. Security Vulnerabilities

- **Known pitfalls:** Hardcoding LLM API keys in the open-source repository.
- **Dependency risks:** Low. The core engine is built from scratch without IR libraries.

### 13. File Structure & Project Organization

- **Monorepo vs. polyrepo:** Single repository.
- **Feature/module organization:**
  - `/data`: `corpus.jsonl` and `qrels.json` (judgment set).
  - `/src`: `indexer.py`, `retrieval.py`, `metrics.py`.
  - `/docs`: `AI-LOG.md`, `PRESEARCH.md`, `ARCHITECTURE.md`.

### 14. Naming Conventions & Code Style

- **Naming patterns:** Standard PEP-8 Python conventions (snake_case for variables/functions, PascalCase for classes).
- **Linter/formatter:** Ruff and Black for immediate code formatting.

### 15. Testing Strategy

- **Coverage target for the MVP:** The primary test is the Information Retrieval metric harness (precision@k, recall, MRR, NDCG) against the 15-query oracle judgment set.
- **Property/Oracle-diffing:** The custom BM25 ranking algorithm will be tested via differential matching against the established `rank_bm25` Python library.

### 16. Recommended Tooling & DX

- **Editor extensions:** GitHub Codespaces / VS Code.
- **CLI tools:** ChatGPT Codex (Sol 5.6) configured for AI-first, agentic coding workflows.

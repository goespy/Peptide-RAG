# Pre-Search Document: Relevance Engine

## Phase 1: Define Your Constraints

### 1. Scale & Load Profile

- **Users at launch:** 1 (the Gauntlet Instructor/Grader).
- **Traffic pattern:** Zero active traffic; the system is evaluated via a single CLI execution.
- **Real-time or batch requirements:** Batch execution for building the index, followed by real-time CLI querying.
- **Cold-start tolerance:** High. The in-memory inverted index will take a moment to build on execution, but retrieval will be instant thereafter.

### 2. Budget & Cost Ceiling

- **Monthly spend limit:** Effectively $0 for the core MVP.
- **Pay-per-use vs. fixed:** Pay-per-use is acceptable for the RAG extension (using OpenAI/Anthropic APIs).
- **Where will you trade money for time?** I will leverage an AI-first workflow (ChatGPT Codex / Sol 5.6), trading LLM API compute costs for accelerated code generation and debugging.

### 3. Time to Ship

- **MVP timeline:** Day 1 MVP due Tuesday at 11:59 PM, with final submission by Sunday.
- **Speed-to-market vs. long-term maintainability:** Speed-to-market is the strict priority to hit the MVP checkpoint.
- **Iteration cadence:** Daily iterations moving from basic boolean retrieval to Okapi BM25 ranking, and finally to semantic embeddings.

### 4. Compliance & Regulatory Needs

- **Health/GDPR/SOC 2:** None required. The custom corpus consists of publicly available scientific abstracts pulled from PubMed.
- **Data residency:** N/A.

### 5. Team & Skill Constraints

- **Solo or team:** Solo.
- **Languages/frameworks:** Python, due to its dominance in data science and natural language processing.
- **Learning appetite vs. shipping speed:** High shipping speed required for the 5-day sprint, supplemented by AI to bridge any immediate syntax gaps.

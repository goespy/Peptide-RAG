"""Local-only retrieval service used by the FastAPI shell.

Lexical search is deliberately self-contained: it reads the checked-in corpus
and never creates an HTTP client.  Semantic retrieval is opt-in and is enabled
only when a hash-bound frozen selection and embedding cache are both present.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import numpy as np

from src.analysis import ANALYSIS_CONFIGS
from src.bm25 import BM25Config, rank_bm25
from src.boolean import search_boolean
from src.chunks import Chunk, embedding_text
from src.embeddings import EmbeddingCacheManifest, EmbeddingClient, load_embedding_cache
from src.generation import AnswerResult, GroundedAnswerClient
from src.index import InvertedIndex
from src.retrieval import RetrievedChunk, Retriever
from src.snippets import make_snippet


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CORPUS = ROOT / "data" / "corpus.jsonl"
DEFAULT_LEXICAL_CONFIG = ROOT / "data" / "lexical_config.json"
DEFAULT_LEXICAL_EVALUATION = ROOT / "artifacts" / "section4" / "holdout.json"
DEFAULT_FROZEN_CONFIG = ROOT / "artifacts" / "section5" / "frozen_config.json"
DEFAULT_GENERATOR_CONFIG = ROOT / "artifacts" / "section5" / "generator_config.json"
DEFAULT_ACCEPTED_SELECTION = ROOT / "artifacts" / "section5" / "accepted_generator_v2_5.json"
DEFAULT_SOURCE_GENERATOR_CONFIG = ROOT / "artifacts" / "section5" / "generator_v2_5_config.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _load_chunks(path: Path, manifest_path: Path) -> tuple[tuple[Chunk, ...], dict[str, Any]]:
    """Read a chunk artifact only after its manifest binds its exact bytes."""

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        rows = path.read_text(encoding="utf-8").splitlines()
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("cannot read chunk artifact") from exc
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1 or manifest.get("chunk_sha256") != _sha256(path):
        raise ValueError("chunk manifest does not bind chunk artifact")
    required = {"chunk_id", "pmid", "title", "text", "start_char", "end_char", "token_count"}
    chunks: list[Chunk] = []
    for row in rows:
        try:
            value = json.loads(row)
            if not isinstance(value, dict) or set(value) != required:
                raise ValueError
            chunks.append(Chunk(**value))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("invalid chunk artifact") from exc
    if not chunks or manifest.get("chunk_count") != len(chunks) or len({item.chunk_id for item in chunks}) != len(chunks):
        raise ValueError("invalid chunk count or ids")
    return tuple(chunks), manifest


def _load_lexical_metrics(path: Path, *, corpus_sha256: str, lexical_config_sha256: str) -> dict[str, Any] | None:
    """Load only a frozen evaluation report bound to the active corpus/config."""

    try:
        report = json.loads(path.read_text(encoding="utf-8"))
        metadata = report["metadata"]
        full = report["full_descriptive"]["aggregate"]
        holdout = report["holdout"]["tuned"]["aggregate"]
        if (
            not isinstance(report, dict)
            or metadata.get("corpus_sha256") != corpus_sha256
            or metadata.get("lexical_config_sha256") != lexical_config_sha256
            or int(full["query_count"]) != 15
            or int(holdout["query_count"]) != 5
        ):
            return None
        return {
            "all_queries": {
                "query_count": int(full["query_count"]),
                "mrr": float(full["mrr"]),
                "recall_at_10": float(full["recall_at"]["10"]),
                "ndcg_at_10": float(full["ndcg_at"]["10"]),
            },
            "untouched_holdout": {
                "query_count": int(holdout["query_count"]),
                "mrr": float(holdout["mrr"]),
                "recall_at_10": float(holdout["recall_at"]["10"]),
                "ndcg_at_10": float(holdout["ndcg_at"]["10"]),
            },
        }
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def load_semantic_retriever(
    corpus_path: Path,
    frozen_config_path: Path,
    cache_path: Path,
    *,
    bm25_config: BM25Config = BM25Config(),
    analysis_config=ANALYSIS_CONFIGS["baseline"],
    lexical_config_sha256: str | None = None,
) -> Retriever | None:
    """Return a semantic retriever only for a selected, validated local cache.

    Any malformed, stale, or incomplete input makes semantic/hybrid unavailable
    instead of rebuilding vectors, selecting a new configuration, or calling a
    provider during application startup.
    """

    try:
        frozen = json.loads(frozen_config_path.read_text(encoding="utf-8"))
        if not isinstance(frozen, dict) or frozen.get("schema_version") != 1:
            return None
        if frozen.get("corpus_sha256") != _sha256(corpus_path):
            return None
        if lexical_config_sha256 is None or frozen.get("lexical_config_sha256") != lexical_config_sha256:
            return None
        config = frozen.get("chunk_config")
        if not isinstance(config, dict) or set(config) != {"words", "overlap"}:
            return None
        words, overlap = config["words"], config["overlap"]
        if isinstance(words, bool) or isinstance(overlap, bool) or not isinstance(words, int) or not isinstance(overlap, int):
            return None
        artifact_dir = frozen_config_path.parent
        chunks_path = artifact_dir / f"chunks_{words}_{overlap}.jsonl"
        chunks, chunk_manifest = _load_chunks(chunks_path, chunks_path.with_suffix(chunks_path.suffix + ".manifest.json"))
        if chunk_manifest.get("corpus_sha256") != frozen["corpus_sha256"]:
            return None
        with np.load(cache_path, allow_pickle=False) as stored:
            raw = json.loads(stored["manifest"].item())
        if not isinstance(frozen.get("embedding_model"), str) or raw.get("model") != frozen["embedding_model"]:
            return None
        expected = EmbeddingCacheManifest.create(
            model=str(raw["model"]), dimension=int(raw["dimension"]),
            corpus_hash=chunk_manifest["corpus_sha256"], chunk_hash=chunk_manifest["chunk_sha256"],
            inputs=[embedding_text(chunk) for chunk in chunks], chunk_ids=[chunk.chunk_id for chunk in chunks],
        )
        embeddings = load_embedding_cache(cache_path, expected)
        if embeddings is None:
            return None
        api_key = os.environ.get("OPENROUTER_API_KEY")
        embedder = EmbeddingClient(api_key=api_key, model=expected.model) if api_key else None
        return Retriever(chunks, embeddings, embedding_client=embedder, alpha=float(frozen.get("rrf_alpha", 0.5)), bm25_config=bm25_config, analysis_config=analysis_config)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def load_release_answer_client(
    final_config_path: Path,
    accepted_selection_path: Path,
    source_generator_config_path: Path,
    frozen_config_path: Path,
) -> GroundedAnswerClient | None:
    """Load only the exact generator contract accepted by the replayed holdout."""

    try:
        final = json.loads(Path(final_config_path).read_text(encoding="utf-8"))
        accepted = json.loads(Path(accepted_selection_path).read_text(encoding="utf-8"))
        source = json.loads(Path(source_generator_config_path).read_text(encoding="utf-8"))
        if not all(isinstance(value, dict) for value in (final, accepted, source)):
            return None
        winner = final.get("winner")
        if (
            final.get("schema_version") != 2
            or final.get("status") != "frozen_after_passing_holdout"
            or final.get("retriever_config_sha256") != _sha256(Path(frozen_config_path))
            or final.get("accepted_selection_sha256") != _sha256(Path(accepted_selection_path))
            or not isinstance(winner, str)
            or not winner
            or accepted.get("status") != "accepted_for_holdout"
            or accepted.get("holdout_status") != "untouched"
            or accepted.get("winner") != winner
            or accepted.get("retriever_config_sha256") != final.get("retriever_config_sha256")
            or accepted.get("generator_config_sha256") != _sha256(Path(source_generator_config_path))
            or source.get("generator_candidates") != [winner]
            or source.get("holdout_status") != "untouched"
        ):
            return None
        prompt = source.get("prompt")
        source_generation = source.get("generation")
        accepted_generation = accepted.get("generation")
        if (
            not isinstance(prompt, str)
            or not prompt.strip()
            or source.get("prompt_sha256")
            != hashlib.sha256(prompt.encode("utf-8")).hexdigest().upper()
            or not isinstance(source_generation, dict)
            or not isinstance(accepted_generation, dict)
        ):
            return None
        expected_generation = {**source_generation, "prompt": prompt}
        if accepted_generation != expected_generation or accepted_generation.get("repair_attempts") != 1:
            return None
        return GroundedAnswerClient(
            model=winner,
            max_tokens=int(accepted_generation["max_tokens"]),
            temperature=float(accepted_generation["temperature"]),
            system_prompt=prompt,
            citation_mode=str(accepted_generation["citation_mode"]),
            require_supported_parameters=bool(accepted_generation["require_supported_parameters"]),
            reasoning_effort=accepted_generation.get("reasoning_effort"),
            exclude_reasoning=bool(accepted_generation.get("exclude_reasoning", False)),
            reconsider_insufficient_evidence=bool(
                accepted_generation.get("reconsider_insufficient_evidence", False)
            ),
        )
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


class LocalResearchService:
    """Serves local Boolean/BM25 results and optional validated RAG assets."""

    def __init__(
        self,
        *,
        corpus_path: Path = DEFAULT_CORPUS,
        lexical_config_path: Path = DEFAULT_LEXICAL_CONFIG,
        lexical_evaluation_path: Path = DEFAULT_LEXICAL_EVALUATION,
        frozen_config_path: Path = DEFAULT_FROZEN_CONFIG,
        generator_config_path: Path = DEFAULT_GENERATOR_CONFIG,
        accepted_selection_path: Path = DEFAULT_ACCEPTED_SELECTION,
        source_generator_config_path: Path = DEFAULT_SOURCE_GENERATOR_CONFIG,
        embedding_cache_path: Path | None = None,
        answer_client: GroundedAnswerClient | None = None,
    ) -> None:
        corpus_path = Path(corpus_path)
        try:
            lexical = json.loads(Path(lexical_config_path).read_text(encoding="utf-8"))
            if not isinstance(lexical, dict) or lexical.get("corpus_sha256") != _sha256(corpus_path):
                raise ValueError("lexical configuration does not match corpus")
            analysis_name = lexical["analysis"]["name"]
            self.bm25_config = BM25Config(
                k1=float(lexical["bm25"]["k1"]),
                b=float(lexical["bm25"]["b"]),
                proximity_boost=float(lexical["bm25"].get("proximity_boost", 0.0)),
            )
            analysis_config = ANALYSIS_CONFIGS[analysis_name]
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("cannot load the frozen lexical configuration") from exc
        self.index = InvertedIndex.from_jsonl(corpus_path, analysis_config=analysis_config)
        lexical_config_hash = _sha256(Path(lexical_config_path))
        self.lexical_metrics = _load_lexical_metrics(
            Path(lexical_evaluation_path),
            corpus_sha256=_sha256(corpus_path),
            lexical_config_sha256=lexical_config_hash,
        )
        self.semantic_retriever = (
            load_semantic_retriever(Path(corpus_path), Path(frozen_config_path), Path(embedding_cache_path), bm25_config=self.bm25_config, analysis_config=analysis_config, lexical_config_sha256=lexical_config_hash)
            if embedding_cache_path is not None else None
        )
        self.answer_client = answer_client
        if self.answer_client is None and self.semantic_retriever is not None:
            self.answer_client = load_release_answer_client(
                Path(generator_config_path),
                Path(accepted_selection_path),
                Path(source_generator_config_path),
                Path(frozen_config_path),
            )

    def _record(self, document_id: str, query: str, score: float | None = None) -> dict[str, Any]:
        document = self.index.documents[document_id]
        source = document.text or document.title
        return {
            "pmid": document.id,
            "title": document.title,
            "snippet": make_snippet(source, query, max_chars=240),
            "score": score,
        }

    @staticmethod
    def _chunk_record(item: RetrievedChunk) -> dict[str, Any]:
        return {
            "pmid": item.pmid,
            "title": item.title,
            "snippet": item.text,
            "score": item.score,
            "chunk_id": item.chunk_id,
            "start_char": item.start_char,
            "end_char": item.end_char,
            "mode": item.mode,
            "lexical_rank": item.lexical_rank,
            "semantic_rank": item.semantic_rank,
        }

    def search(self, query: str, mode: str, k: int) -> list[dict[str, Any]]:
        if mode == "boolean":
            return [self._record(doc_id, query) for doc_id in search_boolean(self.index, query)[:k]]
        if mode == "bm25":
            return [self._record(item.doc_id, query, item.score) for item in rank_bm25(self.index, query, k=k, config=self.bm25_config)]
        if mode == "lexical" and self.semantic_retriever is None:
            return [self._record(item.doc_id, query, item.score) for item in rank_bm25(self.index, query, k=k, config=self.bm25_config)]
        if mode in {"lexical", "semantic", "hybrid"} and self.semantic_retriever is not None:
            try:
                return [self._chunk_record(item) for item in self.semantic_retriever.retrieve(query, k=k, mode=mode)]
            except (RuntimeError, ValueError):
                return []
        # A missing semantic cache never downgrades an explicit semantic request
        # to an unannounced lexical result. Hybrid similarly fails closed.
        return []

    def _contexts_from_evidence(self, evidence: list[dict[str, Any]], k: int) -> tuple[RetrievedChunk, ...]:
        """Re-bind displayed evidence to canonical selected chunks without retrieval."""

        if self.semantic_retriever is None:
            return ()
        known = {chunk.chunk_id: chunk for chunk in self.semantic_retriever.chunks}
        contexts: list[RetrievedChunk] = []
        seen: set[str] = set()
        for item in evidence[:k]:
            if not isinstance(item, dict):
                continue
            chunk_id = item.get("chunk_id")
            chunk = known.get(chunk_id) if isinstance(chunk_id, str) else None
            if chunk is None or chunk_id in seen:
                continue
            if (item.get("pmid"), item.get("title"), item.get("snippet")) != (chunk.pmid, chunk.title, chunk.text):
                continue
            score = item.get("score", 0.0)
            if isinstance(score, bool) or not isinstance(score, (int, float)):
                score = 0.0
            contexts.append(RetrievedChunk(
                chunk,
                float(score),
                str(item.get("mode", "stored")),
                item.get("lexical_rank") if isinstance(item.get("lexical_rank"), int) else None,
                item.get("semantic_rank") if isinstance(item.get("semantic_rank"), int) else None,
            ))
            seen.add(chunk_id)
        return tuple(contexts)

    def answer(self, query: str, mode: str, k: int, evidence: list[dict[str, Any]]) -> dict[str, Any]:
        if self.answer_client is None:
            return {"answer": None, "refusal": "Grounded generation is unavailable until the measured RAG configuration and holdout winner are frozen.", "citations": []}
        result: AnswerResult = self.answer_client.answer(query, self._contexts_from_evidence(evidence, k))
        if result.status != "answered":
            return {"answer": None, "refusal": result.text, "citations": []}
        return {
            "answer": result.text,
            "citations": [
                {
                    "citation_id": citation.citation_id,
                    "pmid": citation.pmid,
                    "chunk_id": citation.chunk_id,
                    "title": citation.title,
                    "pubmed_url": f"https://pubmed.ncbi.nlm.nih.gov/{citation.pmid}/",
                }
                for citation in result.citations
            ],
        }

    def metrics(self) -> dict[str, Any]:
        return {
            "available": True,
            "corpus_documents": len(self.index.documents),
            "lexical_configuration": {
                "k1": self.bm25_config.k1,
                "b": self.bm25_config.b,
                "proximity_boost": self.bm25_config.proximity_boost,
            },
            "semantic_available": self.semantic_retriever is not None,
            "generation_available": self.answer_client is not None,
            "measured_ir": self.lexical_metrics,
        }

"""Deterministic lexical, semantic, and weighted-RRF chunk retrieval."""

from __future__ import annotations

from dataclasses import dataclass
import math
from numbers import Real
from typing import Callable, Iterable, Literal, Sequence

import numpy as np

from src.bm25 import rank_bm25
from src.embeddings import EmbeddingClient, normalize_embeddings
from src.index import InvertedIndex
from src.models import Document

try:
    from src.chunks import Chunk
except ImportError:  # The chunks module is introduced by the chunking section.
    Chunk = object  # type: ignore[misc,assignment]


RetrievalMode = Literal["lexical", "semantic", "hybrid"]
RRF_CANDIDATES = 50
RRF_CONSTANT = 60


@dataclass(frozen=True)
class RetrievedChunk:
    chunk: Chunk
    score: float
    mode: str
    lexical_rank: int | None = None
    semantic_rank: int | None = None

    @property
    def chunk_id(self) -> str:
        return self.chunk.chunk_id

    @property
    def pmid(self) -> str:
        return self.chunk.pmid

    @property
    def title(self) -> str:
        return self.chunk.title

    @property
    def text(self) -> str:
        return self.chunk.text

    @property
    def start_char(self) -> int:
        return self.chunk.start_char

    @property
    def end_char(self) -> int:
        return self.chunk.end_char


def _chunk_input(chunk: Chunk) -> str:
    return f"{chunk.title}\n{chunk.text}"


def _synthetic_id(position: int) -> str:
    # Index requires numeric PMID ids. This mapping is local and preserves chunk order.
    return str(position + 1)


class Retriever:
    """In-memory chunk retriever; callers may inject query embeddings for offline use."""

    def __init__(
        self,
        chunks: Iterable[Chunk],
        embeddings: np.ndarray | Sequence[Sequence[float]],
        *,
        embedding_client: EmbeddingClient | None = None,
        query_embedding: Callable[[str], np.ndarray | Sequence[float]] | None = None,
        alpha: float = 0.5,
    ) -> None:
        self.chunks = tuple(chunks)
        ids = [chunk.chunk_id for chunk in self.chunks]
        if len(ids) != len(set(ids)) or any(not isinstance(item, str) or not item for item in ids):
            raise ValueError("chunks must have unique non-empty ids")
        self.embeddings = normalize_embeddings(embeddings)
        if self.embeddings.shape[0] != len(self.chunks):
            raise ValueError("embeddings must have one row per chunk")
        if isinstance(alpha, bool) or not isinstance(alpha, Real) or not math.isfinite(alpha) or not 0 <= alpha <= 1:
            raise ValueError("alpha must be a finite number between 0 and 1")
        self.alpha = float(alpha)
        self.embedding_client = embedding_client
        self.query_embedding = query_embedding
        self._chunk_by_doc_id = {_synthetic_id(i): chunk for i, chunk in enumerate(self.chunks)}
        documents = (Document(_synthetic_id(i), chunk.title, chunk.text) for i, chunk in enumerate(self.chunks))
        self.index = InvertedIndex.from_documents(documents)

    def _validate(self, query: str, k: int, mode: str) -> None:
        if not isinstance(query, str):
            raise ValueError("query must be a string")
        if isinstance(k, bool) or not isinstance(k, int) or k <= 0:
            raise ValueError("k must be a positive integer")
        if mode not in ("lexical", "semantic", "hybrid"):
            raise ValueError("mode must be lexical, semantic, or hybrid")

    def _lexical(self, query: str, limit: int) -> list[RetrievedChunk]:
        return [RetrievedChunk(self._chunk_by_doc_id[item.doc_id], item.score, "lexical", rank, None)
                for rank, item in enumerate(rank_bm25(self.index, query, k=limit), start=1)]

    def _semantic(self, query: str, limit: int) -> list[RetrievedChunk]:
        if not query.strip() or not self.chunks:
            return []
        if self.query_embedding is not None:
            vector = self.query_embedding(query)
        else:
            client = self.embedding_client if self.embedding_client is not None else EmbeddingClient()
            vector = client.embed([query])[0]
        query_vector = normalize_embeddings(np.asarray(vector, dtype=np.float64).reshape(1, -1))
        if query_vector.shape[1] != self.embeddings.shape[1]:
            raise ValueError("query embedding dimension does not match corpus embeddings")
        scores = self.embeddings @ query_vector[0]
        order = sorted(range(len(self.chunks)), key=lambda i: (-float(scores[i]), self.chunks[i].chunk_id))[:limit]
        return [RetrievedChunk(self.chunks[i], float(scores[i]), "semantic", None, rank)
                for rank, i in enumerate(order, start=1)]

    def retrieve(self, query: str, k: int = 10, mode: RetrievalMode = "hybrid") -> tuple[RetrievedChunk, ...]:
        self._validate(query, k, mode)
        if not query.strip() or not self.chunks:
            return ()
        if mode == "lexical":
            return tuple(self._lexical(query, k))
        semantic = self._semantic(query, RRF_CANDIDATES if mode == "hybrid" else k)
        if mode == "semantic":
            return tuple(semantic)
        lexical = self._lexical(query, RRF_CANDIDATES)
        combined: dict[str, list[object]] = {}
        for item in lexical:
            combined[item.chunk_id] = [item.chunk, self.alpha / (RRF_CONSTANT + item.lexical_rank), item.lexical_rank, None]
        for item in semantic:
            entry = combined.setdefault(item.chunk_id, [item.chunk, 0.0, None, None])
            entry[1] = float(entry[1]) + (1 - self.alpha) / (RRF_CONSTANT + item.semantic_rank)
            entry[3] = item.semantic_rank
        ranked = sorted(combined.values(), key=lambda item: (-float(item[1]), item[0].chunk_id))[:k]
        return tuple(RetrievedChunk(item[0], float(item[1]), "hybrid", item[2], item[3]) for item in ranked)

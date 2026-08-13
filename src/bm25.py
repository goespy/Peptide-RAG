"""Deterministic Okapi BM25 ranking over the project inverted index."""

from __future__ import annotations

from dataclasses import dataclass
import math
from numbers import Real

from .analysis import analyze
from .index import InvertedIndex


@dataclass(frozen=True)
class BM25Config:
    """Validated parameters for the Okapi BM25 scoring function."""

    k1: float = 1.2
    b: float = 0.75

    def __post_init__(self) -> None:
        for name, value in (("k1", self.k1), ("b", self.b)):
            if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
                raise ValueError(f"{name} must be a finite real number")
        if self.k1 <= 0:
            raise ValueError("k1 must be greater than zero")
        if not 0 <= self.b <= 1:
            raise ValueError("b must be between zero and one")


@dataclass(frozen=True)
class ScoredDocument:
    """A document id paired with its BM25 score."""

    doc_id: str
    score: float


def _idf(document_count: int, document_frequency: int) -> float:
    """Return the Lucene-style BM25 inverse document frequency."""

    return math.log(1 + (document_count - document_frequency + 0.5) / (document_frequency + 0.5))


def rank_bm25(
    index: InvertedIndex,
    query: str,
    k: int = 10,
    config: BM25Config = BM25Config(),
) -> tuple[ScoredDocument, ...]:
    """Rank documents matching *query* using shared analysis and Okapi BM25.

    Repeated query terms intentionally add their contribution each time.  Only
    documents containing at least one analyzed query term are returned.
    """

    if isinstance(k, bool) or not isinstance(k, int) or k <= 0:
        raise ValueError("k must be a positive integer")
    if not isinstance(config, BM25Config):
        raise ValueError("config must be a BM25Config")

    query_terms = analyze(query)
    if not query_terms or not index.documents:
        return ()

    document_count = len(index.documents)
    average_length = sum(index.document_lengths.values()) / document_count
    scores: dict[str, float] = {}

    for term in query_terms:
        term_postings = index.postings.get(term, ())
        if not term_postings:
            continue
        term_idf = _idf(document_count, index.document_frequency[term])
        for posting in term_postings:
            document_length = index.document_lengths[posting.doc_id]
            term_frequency = len(posting.positions)
            denominator = term_frequency + config.k1 * (
                1 - config.b + config.b * document_length / average_length
            )
            scores[posting.doc_id] = scores.get(posting.doc_id, 0.0) + (
                term_idf * term_frequency / denominator
            )

    return tuple(
        ScoredDocument(document_id, score)
        for document_id, score in sorted(scores.items(), key=lambda item: (-item[1], int(item[0])))[:k]
    )

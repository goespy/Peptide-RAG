"""Small, dependency-free retrieval evaluation utilities.

Binary measures treat every positive qrels grade as relevant.  Rank-aware
measures retain the grades, using the standard exponential-gain NDCG formula.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from math import isfinite, log2
from numbers import Real
from typing import Any


def _validate_k(k: int) -> None:
    if isinstance(k, bool) or not isinstance(k, int) or k <= 0:
        raise ValueError("k must be a positive integer")


def _validated_ks(ks: Sequence[int]) -> tuple[int, ...]:
    values = tuple(ks)
    for k in values:
        _validate_k(k)
    return values


def _unique_ids(retrieved: Sequence[str]) -> tuple[str, ...]:
    """Return document IDs once, in their first-retrieved order."""

    seen: set[str] = set()
    unique: list[str] = []
    for document_id in retrieved:
        if document_id not in seen:
            seen.add(document_id)
            unique.append(document_id)
    return tuple(unique)


def precision_at_k(retrieved: Sequence[str], relevant: set[str], k: int) -> float:
    """Return binary precision at *k*, always using *k* as its denominator."""

    _validate_k(k)
    return sum(document_id in relevant for document_id in _unique_ids(retrieved)[:k]) / k


def recall_at_k(retrieved: Sequence[str], relevant: set[str], k: int) -> float:
    """Return binary recall at *k* against the complete relevant set."""

    _validate_k(k)
    if not relevant:
        return 0.0
    return sum(document_id in relevant for document_id in _unique_ids(retrieved)[:k]) / len(relevant)


def reciprocal_rank(retrieved: Sequence[str], relevant: set[str]) -> float:
    """Return reciprocal rank of the first positive judgment, or zero."""

    for rank, document_id in enumerate(_unique_ids(retrieved), start=1):
        if document_id in relevant:
            return 1.0 / rank
    return 0.0


def dcg_at_k(retrieved: Sequence[str], judgments: Mapping[str, Real], k: int) -> float:
    """Return DCG@k with gain ``2**grade - 1`` and log-base-2 discount."""

    _validate_k(k)
    total = 0.0
    for rank, document_id in enumerate(_unique_ids(retrieved)[:k], start=1):
        grade = judgments.get(document_id, 0)
        total += (2.0**float(grade) - 1.0) / log2(rank + 1)
    return total


def ndcg_at_k(retrieved: Sequence[str], judgments: Mapping[str, Real], k: int) -> float:
    """Return normalized DCG@k, with a zero-safe ideal-ranking denominator."""

    _validate_k(k)
    actual = dcg_at_k(retrieved, judgments, k)
    ideal_grades = sorted((float(grade) for grade in judgments.values()), reverse=True)
    ideal = sum(
        (2.0**grade - 1.0) / log2(rank + 1)
        for rank, grade in enumerate(ideal_grades[:k], start=1)
    )
    return actual / ideal if ideal else 0.0


@dataclass(frozen=True)
class QueryMetrics:
    """Metrics computed for one judged query."""

    query_id: str
    query: str
    relevant_count: int
    retrieved_count: int
    precision_at: dict[int, float]
    recall_at: dict[int, float]
    reciprocal_rank: float = 0.0
    ndcg_at: dict[int, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-ready representation with stable string cutoff keys."""

        value = asdict(self)
        value["precision_at"] = {str(k): v for k, v in self.precision_at.items()}
        value["recall_at"] = {str(k): v for k, v in self.recall_at.items()}
        value["ndcg_at"] = {str(k): v for k, v in self.ndcg_at.items()}
        return value


@dataclass(frozen=True)
class EvaluationReport:
    """Deterministic complete evaluation result returned by :func:`evaluate_run`."""

    cutoffs: tuple[int, ...]
    results: tuple[QueryMetrics, ...]
    aggregate: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        aggregate = dict(self.aggregate)
        for key in ("precision_at", "recall_at", "ndcg_at"):
            aggregate[key] = {str(k): v for k, v in aggregate[key].items()}
        return {"cutoffs": list(self.cutoffs), "aggregate": aggregate,
                "queries": [result.to_dict() for result in self.results]}


def _parse_queries(qrels: Mapping[str, Any]) -> tuple[tuple[str, str, dict[str, float]], ...]:
    if not isinstance(qrels, Mapping):
        raise ValueError("qrels must be a mapping with a 'queries' list")
    queries = qrels.get("queries")
    if not isinstance(queries, list):
        raise ValueError("qrels['queries'] must be a list")

    parsed: list[tuple[str, str, dict[str, float]]] = []
    query_ids: set[str] = set()
    for entry in queries:
        if not isinstance(entry, Mapping):
            raise ValueError("each qrels query must be a mapping")
        query_id, query, judgments = entry.get("id"), entry.get("query"), entry.get("judgments")
        if not isinstance(query_id, str) or not query_id:
            raise ValueError("each qrels query needs a non-empty string id")
        if query_id in query_ids:
            raise ValueError("qrels query ids must be unique")
        if not isinstance(query, str):
            raise ValueError("each qrels query needs a string query")
        if not isinstance(judgments, Mapping):
            raise ValueError("each qrels query needs a judgments mapping")
        grades: dict[str, float] = {}
        for document_id, grade in judgments.items():
            if not isinstance(document_id, str) or not document_id:
                raise ValueError("judgment document ids must be non-empty strings")
            if isinstance(grade, bool) or not isinstance(grade, Real) or not isfinite(float(grade)) or grade < 0:
                raise ValueError("judgment grades must be finite non-negative numbers")
            grades[document_id] = float(grade)
        query_ids.add(query_id)
        parsed.append((query_id, query, grades))
    return tuple(parsed)


def _metrics_for(query_id: str, query: str, judgments: Mapping[str, float], retrieved: Sequence[str], ks: tuple[int, ...]) -> QueryMetrics:
    unique = _unique_ids(retrieved)
    relevant = {document_id for document_id, grade in judgments.items() if grade > 0}
    return QueryMetrics(query_id, query, len(relevant), len(unique),
        {k: precision_at_k(unique, relevant, k) for k in ks},
        {k: recall_at_k(unique, relevant, k) for k in ks},
        reciprocal_rank(unique, relevant),
        {k: ndcg_at_k(unique, judgments, k) for k in ks})


def evaluate_qrels(search: Callable[[str], Sequence[str]], qrels: dict, ks: Sequence[int] = (1, 3, 5)) -> list[QueryMetrics]:
    """Run *search* for every valid qrels query and calculate all metrics."""

    validated_ks = _validated_ks(ks)
    return [_metrics_for(query_id, query, judgments, search(query), validated_ks)
            for query_id, query, judgments in _parse_queries(qrels)]


def aggregate_metrics(results: Sequence[QueryMetrics], ks: Sequence[int]) -> dict[str, Any]:
    """Return zero-safe macro-average binary and rank-aware metrics."""

    validated_ks = _validated_ks(ks)
    divisor = len(results) or 1
    return {"query_count": len(results),
            "precision_at": {k: sum(x.precision_at.get(k, 0.0) for x in results) / divisor for k in validated_ks},
            "recall_at": {k: sum(x.recall_at.get(k, 0.0) for x in results) / divisor for k in validated_ks},
            "mrr": sum(x.reciprocal_rank for x in results) / divisor,
            "ndcg_at": {k: sum(x.ndcg_at.get(k, 0.0) for x in results) / divisor for k in validated_ks}}


def evaluate_run(qrels: Mapping[str, Any], rankings: Mapping[str, Sequence[str]], cutoffs: Sequence[int] = (1, 3, 5, 10)) -> EvaluationReport:
    """Evaluate ranked document IDs by query ID without invoking a search function."""

    ks = _validated_ks(cutoffs)
    if not isinstance(rankings, Mapping):
        raise ValueError("rankings must be a mapping from query id to document IDs")
    parsed = _parse_queries(qrels)
    query_ids = {query_id for query_id, _, _ in parsed}
    unknown = set(rankings) - query_ids
    if unknown:
        raise ValueError("rankings contains query ids absent from qrels")
    results: list[QueryMetrics] = []
    for query_id, query, judgments in parsed:
        ranking = rankings.get(query_id, ())
        if isinstance(ranking, (str, bytes)) or not isinstance(ranking, Sequence):
            raise ValueError("each ranking must be a sequence of document ID strings")
        if any(not isinstance(document_id, str) or not document_id for document_id in ranking):
            raise ValueError("ranking document ids must be non-empty strings")
        results.append(_metrics_for(query_id, query, judgments, ranking, ks))
    frozen_results = tuple(results)
    return EvaluationReport(ks, frozen_results, aggregate_metrics(frozen_results, ks))


def _format_number(value: float) -> str:
    return f"{value:.3f}"


def render_markdown(results: Sequence[QueryMetrics], ks: Sequence[int]) -> str:
    """Render aggregate and per-query metrics as paste-ready Markdown tables."""

    validated_ks = _validated_ks(ks)
    aggregate = aggregate_metrics(results, validated_ks)
    headers = ["Query ID", "Query", "Relevant", "Retrieved", "Reciprocal Rank"]
    headers.extend(f"Precision@{k}" for k in validated_ks)
    headers.extend(f"Recall@{k}" for k in validated_ks)
    headers.extend(f"NDCG@{k}" for k in validated_ks)
    lines = ["## Retrieval Metrics", "", "### Aggregate", ""]
    aggregate_headers = ["Queries", "MRR"] + [f"Mean Precision@{k}" for k in validated_ks] + [f"Mean Recall@{k}" for k in validated_ks] + [f"Mean NDCG@{k}" for k in validated_ks]
    lines += ["| " + " | ".join(aggregate_headers) + " |", "| " + " | ".join("---" for _ in aggregate_headers) + " |"]
    values = [str(aggregate["query_count"]), _format_number(aggregate["mrr"])]
    values += [_format_number(aggregate["precision_at"][k]) for k in validated_ks]
    values += [_format_number(aggregate["recall_at"][k]) for k in validated_ks]
    values += [_format_number(aggregate["ndcg_at"][k]) for k in validated_ks]
    lines.append("| " + " | ".join(values) + " |")
    lines += ["", "### Per-query", "", "| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for result in results:
        query = result.query.replace("|", r"\|").replace("\n", " ")
        values = [result.query_id, query, str(result.relevant_count), str(result.retrieved_count), _format_number(result.reciprocal_rank)]
        values += [_format_number(result.precision_at.get(k, 0.0)) for k in validated_ks]
        values += [_format_number(result.recall_at.get(k, 0.0)) for k in validated_ks]
        values += [_format_number(result.ndcg_at.get(k, 0.0)) for k in validated_ks]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines) + "\n"

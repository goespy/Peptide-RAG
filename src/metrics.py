"""Small, dependency-free retrieval evaluation utilities."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from numbers import Real


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
    top_k = _unique_ids(retrieved)[:k]
    return sum(document_id in relevant for document_id in top_k) / k


def recall_at_k(retrieved: Sequence[str], relevant: set[str], k: int) -> float:
    """Return binary recall at *k* against the complete relevant set."""

    _validate_k(k)
    if not relevant:
        return 0.0
    top_k = _unique_ids(retrieved)[:k]
    return sum(document_id in relevant for document_id in top_k) / len(relevant)


@dataclass(frozen=True)
class QueryMetrics:
    """Metrics computed for one judged query."""

    query_id: str
    query: str
    relevant_count: int
    retrieved_count: int
    precision_at: dict[int, float]
    recall_at: dict[int, float]


def _parse_queries(qrels: dict) -> tuple[tuple[str, str, set[str]], ...]:
    if not isinstance(qrels, Mapping):
        raise ValueError("qrels must be a mapping with a 'queries' list")
    queries = qrels.get("queries")
    if not isinstance(queries, list):
        raise ValueError("qrels['queries'] must be a list")

    parsed: list[tuple[str, str, set[str]]] = []
    query_ids: set[str] = set()
    for entry in queries:
        if not isinstance(entry, Mapping):
            raise ValueError("each qrels query must be a mapping")
        query_id = entry.get("id")
        query = entry.get("query")
        judgments = entry.get("judgments")
        if not isinstance(query_id, str) or not query_id:
            raise ValueError("each qrels query needs a non-empty string id")
        if query_id in query_ids:
            raise ValueError("qrels query ids must be unique")
        if not isinstance(query, str):
            raise ValueError("each qrels query needs a string query")
        if not isinstance(judgments, Mapping):
            raise ValueError("each qrels query needs a judgments mapping")

        relevant: set[str] = set()
        for document_id, grade in judgments.items():
            if not isinstance(document_id, str) or not document_id:
                raise ValueError("judgment document ids must be non-empty strings")
            if isinstance(grade, bool) or not isinstance(grade, Real):
                raise ValueError("judgment grades must be numeric")
            if grade > 0:
                relevant.add(document_id)
        query_ids.add(query_id)
        parsed.append((query_id, query, relevant))
    return tuple(parsed)


def evaluate_qrels(
    search: Callable[[str], Sequence[str]],
    qrels: dict,
    ks: Sequence[int] = (1, 3, 5),
) -> list[QueryMetrics]:
    """Run *search* for every valid qrels query and calculate binary metrics."""

    validated_ks = _validated_ks(ks)
    parsed_queries = _parse_queries(qrels)
    results: list[QueryMetrics] = []
    for query_id, query, relevant in parsed_queries:
        retrieved = _unique_ids(search(query))
        results.append(
            QueryMetrics(
                query_id=query_id,
                query=query,
                relevant_count=len(relevant),
                retrieved_count=len(retrieved),
                precision_at={k: precision_at_k(retrieved, relevant, k) for k in validated_ks},
                recall_at={k: recall_at_k(retrieved, relevant, k) for k in validated_ks},
            )
        )
    return results


def aggregate_metrics(
    results: Sequence[QueryMetrics], ks: Sequence[int]
) -> dict[str, object]:
    """Return macro-average precision and recall for the requested cutoffs."""

    validated_ks = _validated_ks(ks)
    count = len(results)
    divisor = count or 1
    return {
        "query_count": count,
        "precision_at": {
            k: sum(result.precision_at.get(k, 0.0) for result in results) / divisor
            for k in validated_ks
        },
        "recall_at": {
            k: sum(result.recall_at.get(k, 0.0) for result in results) / divisor
            for k in validated_ks
        },
    }


def _format_number(value: float) -> str:
    return f"{value:.3f}"


def render_markdown(results: Sequence[QueryMetrics], ks: Sequence[int]) -> str:
    """Render aggregate and per-query metrics as paste-ready Markdown tables."""

    validated_ks = _validated_ks(ks)
    aggregate = aggregate_metrics(results, validated_ks)
    headers = ["Query ID", "Query", "Relevant", "Retrieved"]
    headers.extend(f"Precision@{k}" for k in validated_ks)
    headers.extend(f"Recall@{k}" for k in validated_ks)

    lines = ["## Retrieval Metrics", "", "### Aggregate", ""]
    aggregate_headers = ["Queries"]
    aggregate_headers.extend(f"Mean Precision@{k}" for k in validated_ks)
    aggregate_headers.extend(f"Mean Recall@{k}" for k in validated_ks)
    lines.append("| " + " | ".join(aggregate_headers) + " |")
    lines.append("| " + " | ".join("---" for _ in aggregate_headers) + " |")
    aggregate_values = [str(aggregate["query_count"])]
    aggregate_values.extend(
        _format_number(aggregate["precision_at"][k]) for k in validated_ks  # type: ignore[index]
    )
    aggregate_values.extend(
        _format_number(aggregate["recall_at"][k]) for k in validated_ks  # type: ignore[index]
    )
    lines.append("| " + " | ".join(aggregate_values) + " |")

    lines.extend(["", "### Per-query", ""])
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    for result in results:
        query = result.query.replace("|", r"\|").replace("\n", " ")
        values = [result.query_id, query, str(result.relevant_count), str(result.retrieved_count)]
        values.extend(_format_number(result.precision_at.get(k, 0.0)) for k in validated_ks)
        values.extend(_format_number(result.recall_at.get(k, 0.0)) for k in validated_ks)
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines) + "\n"

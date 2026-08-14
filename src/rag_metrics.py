"""Deterministic, dependency-free metrics for saved RAG evaluation artifacts."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Iterable, Mapping


DIMENSIONS = ("faithful", "relevant", "citations_correct", "refusal_correct")


def percentile95(values: Iterable[float]) -> float | None:
    """Return the nearest-rank p95 (ceil(0.95*n), one-indexed)."""
    items = sorted(float(value) for value in values)
    if not items:
        return None
    return items[min(len(items) - 1, int((len(items) * 0.95) + 0.999999) - 1)]


def answer_is_structurally_valid(answer: Mapping[str, Any]) -> bool:
    """Check the saved, model-independent answer contract conservatively."""
    status, text, citations = answer.get("status"), answer.get("text"), answer.get("citations")
    if status not in {"answered", "insufficient_evidence"} or not isinstance(text, str) or not isinstance(citations, list):
        return False
    if status == "insufficient_evidence":
        return not citations
    if not text.strip() or not citations:
        return False
    seen: set[int] = set()
    for citation in citations:
        if not isinstance(citation, Mapping) or not isinstance(citation.get("citation_id"), int):
            return False
        if citation["citation_id"] not in range(1, 6) or citation["citation_id"] in seen or not all(isinstance(citation.get(key), str) and citation[key] for key in ("pmid", "chunk_id", "title")):
            return False
        seen.add(citation["citation_id"])
    return True


def candidate_summary(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    saved = tuple(rows)
    valid = [row for row in saved if bool(row.get("structurally_valid"))]
    def rate(name: str, *, subset: str = "all") -> float | None:
        selected = [
            row for row in valid
            if subset == "all"
            or (subset == "unanswerable" and row.get("answerability") == "unanswerable")
            or (subset == "answered" and isinstance(row.get("answer"), Mapping) and row["answer"].get("status") == "answered")
        ]
        if not selected:
            return None
        values = [row.get("judge", {}).get(name) if isinstance(row.get("judge"), Mapping) else None for row in selected]
        return sum(value is True for value in values) / len(values) if all(isinstance(value, bool) for value in values) else None
    costs = [row.get("metadata", {}).get("cost_usd") for row in valid]
    exposed_costs = [float(value) for value in costs if isinstance(value, (int, float))]
    judged = [
        row for row in valid
        if isinstance(row.get("judge"), Mapping)
        and all(isinstance(row["judge"].get(name), bool) for name in DIMENSIONS)
    ]
    denominators = {
        "all_valid": len(valid),
        "answered": sum(isinstance(row.get("answer"), Mapping) and row["answer"].get("status") == "answered" for row in valid),
        "unanswerable": sum(row.get("answerability") == "unanswerable" for row in valid),
    }
    return {
        "outputs": len(saved), "valid_outputs": len(valid), "judged_outputs": len(judged), "denominators": denominators,
        "structural_validity": len(valid) / len(saved) if saved else 0.0,
        "faithfulness": rate("faithful"), "correct_refusal": rate("refusal_correct", subset="unanswerable"),
        "relevancy": rate("relevant"), "citation_correctness": rate("citations_correct", subset="answered"),
        "cost_usd": sum(exposed_costs) if len(exposed_costs) == len(valid) else None,
        "p95_latency_ms": percentile95(row.get("metadata", {}).get("latency_ms") for row in valid if isinstance(row.get("metadata", {}).get("latency_ms"), (int, float))),
    }


def select_winner(rows_by_model: Mapping[str, Iterable[Mapping[str, Any]]], expected_cases: int) -> dict[str, Any]:
    """Apply the Section 5 lexicographic selection rule without hiding failures."""
    summaries = {model: candidate_summary(rows) for model, rows in sorted(rows_by_model.items())}
    eligible = {
        model: summary for model, summary in summaries.items()
        if summary["outputs"] == expected_cases and summary["structural_validity"] == 1.0
        and summary["judged_outputs"] == expected_cases
        and all(summary[key] is not None for key in ("faithfulness", "correct_refusal", "relevancy", "citation_correctness"))
    }
    if not eligible:
        return {"winner": None, "reason": "all candidates incomplete, structurally invalid, or not fully judged", "candidates": summaries}
    # Higher quality first; then lower cost and latency; final model name is a stable tie-break.
    def key(item: tuple[str, dict[str, Any]]) -> tuple[float, ...] | tuple:
        model, value = item
        return (-value["structural_validity"], -value["faithfulness"], -value["correct_refusal"], -value["relevancy"], -value["citation_correctness"], value["cost_usd"] if value["cost_usd"] is not None else float("inf"), value["p95_latency_ms"] if value["p95_latency_ms"] is not None else float("inf"), model)
    winner = min(eligible.items(), key=key)[0]
    return {"winner": winner, "reason": "schema/citation validity, faithfulness, refusal, relevancy, citation correctness, cost, p95 latency", "candidates": summaries}


def binary_agreement(pairs: Iterable[tuple[bool, bool]]) -> dict[str, Any]:
    pairs = tuple(pairs)
    matrix = Counter((human, judge) for human, judge in pairs)
    n = len(pairs)
    if not n:
        return {"n": 0, "matrix": {}, "agreement": None, "kappa": None, "kappa_defined": False}
    agreement = (matrix[(True, True)] + matrix[(False, False)]) / n
    human_yes = sum(human for human, _ in pairs) / n
    judge_yes = sum(judge for _, judge in pairs) / n
    expected = human_yes * judge_yes + (1 - human_yes) * (1 - judge_yes)
    kappa = None if expected == 1 else (agreement - expected) / (1 - expected)
    return {"n": n, "matrix": {"human_true_judge_true": matrix[(True, True)], "human_true_judge_false": matrix[(True, False)], "human_false_judge_true": matrix[(False, True)], "human_false_judge_false": matrix[(False, False)]}, "agreement": agreement, "kappa": kappa, "kappa_defined": kappa is not None}

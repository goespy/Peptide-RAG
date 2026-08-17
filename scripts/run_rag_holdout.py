#!/usr/bin/env python3
"""Run or replay the one-shot seven-case RAG holdout after owner validation."""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_generator_diagnostic import validate_selected_parameter_support  # noqa: E402
from scripts.run_rag_bakeoff import (  # noqa: E402
    BakeoffError,
    combined_usage,
    contexts_from,
    estimate_bakeoff_cost,
    hash_file,
    load_json,
    structurally_valid_answer,
    validate_config,
    validate_judge_catalog,
    validate_live_cost,
    validate_model_catalog,
    write_json_atomic,
)
from src.generation import AnswerResult, Citation, GroundedAnswerClient  # noqa: E402
from src.judge import AnswerJudge, AtomicClaim, JudgeVerdict, validate_verdict  # noqa: E402
from src.rag_metrics import candidate_summary  # noqa: E402
from src.retrieval import RetrievedChunk  # noqa: E402


HOLDOUT_ROW_FIELDS = {
    "model",
    "qa_id",
    "answerability",
    "selection_sha256",
    "config_sha256",
    "contexts_sha256",
    "answer",
    "judge",
    "structurally_valid",
    "generator_metadata",
    "judge_metadata",
    "metadata",
}
HOLDOUT_OUTPUT_FIELDS = {
    "schema_version",
    "selection_sha256",
    "qa_sha256",
    "retriever_config_sha256",
    "contexts_sha256",
    "model_catalog_sha256",
    "cost_estimate",
    "approved_max_cost_usd",
    "attempt_counts",
    "outputs",
}


class HoldoutError(BakeoffError):
    """Raised when a holdout boundary or artifact invariant is violated."""


def holdout_cases(packet: dict[str, Any]) -> list[dict[str, Any]]:
    questions = packet.get("questions")
    if packet.get("status") != "approved" or not isinstance(questions, list):
        raise HoldoutError("holdout requires approved data/qa.json")
    saved = []
    for item in questions:
        if not isinstance(item, dict) or item.get("split") != "holdout":
            continue
        review = item.get("human_review")
        if (
            not isinstance(item.get("id"), str)
            or not isinstance(item.get("question"), str)
            or not item["question"].strip()
            or not isinstance(item.get("answerable"), bool)
            or not isinstance(review, dict)
            or review.get("approved") is not True
            or review.get("decision") != "approve"
            or not isinstance(review.get("reviewer"), str)
            or not review["reviewer"].strip()
        ):
            raise HoldoutError("every holdout question requires frozen owner approval")
        if item["answerable"] and (not item.get("relevant_pmids") or not item.get("supporting_spans")):
            raise HoldoutError("answerable holdout question lacks frozen support")
        if not item["answerable"] and (item.get("relevant_pmids") or item.get("supporting_spans")):
            raise HoldoutError("unanswerable holdout question cannot contain support")
        saved.append({
            "id": item["id"],
            "question": item["question"],
            "answerability": "answerable" if item["answerable"] else "unanswerable",
        })
    if (
        len(saved) != 7
        or len({item["id"] for item in saved}) != 7
        or sum(item["answerability"] == "answerable" for item in saved) != 5
        or sum(item["answerability"] == "unanswerable" for item in saved) != 2
    ):
        raise HoldoutError("holdout must be the fixed seven questions (five answerable, two unanswerable)")
    return sorted(saved, key=lambda item: item["id"])


def winner_from(selection: dict[str, Any]) -> str:
    if selection.get("status") != "accepted_for_holdout" or selection.get("holdout_status") != "untouched":
        raise HoldoutError("holdout requires an explicitly accepted, non-provisional generator selection")
    winner = selection.get("winner")
    if not isinstance(winner, str) or not winner.strip():
        raise HoldoutError("holdout requires one frozen generator")
    return winner


def validate_context_provenance(
    packet: dict[str, Any],
    config_hash: str,
    *,
    qa_hash: str | None = None,
    selection_hash: str | None = None,
) -> None:
    if packet.get("retriever_config_sha256") != config_hash:
        raise HoldoutError("holdout contexts are not bound to the frozen retriever configuration")
    if qa_hash is not None and packet.get("qa_sha256") != qa_hash:
        raise HoldoutError("holdout contexts are not bound to the frozen QA")
    if selection_hash is not None and packet.get("accepted_selection_sha256") != selection_hash:
        raise HoldoutError("holdout contexts are not bound to the accepted generator selection")


def validate_selection_bindings(
    selection: dict[str, Any],
    owner_report: dict[str, Any],
    generator_config: dict[str, Any],
    judge_config: dict[str, Any],
    *,
    qa_hash: str,
    retriever_config_hash: str,
    selection_hash: str,
    owner_report_hash: str,
    generator_config_hash: str,
    judge_config_hash: str,
) -> tuple[str, dict[str, Any], dict[str, Any], float]:
    winner = winner_from(selection)
    generation = validate_config(generator_config)
    if (
        selection.get("qa_sha256") != qa_hash
        or selection.get("retriever_config_sha256") != retriever_config_hash
        or selection.get("owner_validation_report_sha256") != owner_report_hash
        or selection.get("generator_config_sha256") != generator_config_hash
        or selection.get("judge_config_sha256") != judge_config_hash
        or selection.get("model_catalog_sha256") != generator_config.get("model_catalog_sha256")
        or judge_config.get("model_catalog_sha256") != selection.get("model_catalog_sha256")
        or selection.get("generation") != generation
    ):
        raise HoldoutError("accepted selection hashes or frozen generation settings drifted")
    if (
        owner_report.get("passes") is not True
        or owner_report.get("source_outputs_sha256") != selection.get("judge_outputs_sha256")
    ):
        raise HoldoutError("holdout requires the passing owner-validation report used by selection")
    if generator_config.get("generator_candidates") != [winner]:
        raise HoldoutError("generator configuration does not contain only the accepted winner")
    judge_settings = judge_config.get("judge")
    if (
        not isinstance(judge_settings, dict)
        or judge_settings.get("model") != selection.get("judge_model")
        or judge_settings.get("prompt_version") != selection.get("judge_prompt_version")
        or judge_settings.get("prompt_version") != 2
        or judge_config.get("holdout_status") != "untouched"
    ):
        raise HoldoutError("judge-v2 configuration differs from the accepted selection")
    cost_caps = selection.get("holdout_cost_caps")
    hard_cap = cost_caps.get("generation_and_judging_usd") if isinstance(cost_caps, dict) else None
    if isinstance(hard_cap, bool) or not isinstance(hard_cap, (int, float)) or hard_cap != 0.50:
        raise HoldoutError("accepted selection must freeze the $0.50 holdout hard cap")
    if not selection_hash or len(selection_hash) != 64:
        raise HoldoutError("accepted selection hash is malformed")
    return winner, generation, judge_settings, float(hard_cap)


def estimate_holdout_cost(
    cases: list[dict[str, Any]],
    contexts: dict[str, tuple[RetrievedChunk, ...]],
    catalog: dict[str, Any],
    winner: str,
    judge_model: str,
    generation: dict[str, Any],
    judge_settings: dict[str, Any],
) -> dict[str, Any]:
    base = estimate_bakeoff_cost(cases, contexts, catalog, [winner], judge_model, generation)
    generation_estimate = base["generation"][0]
    generator_catalog = next(
        (
            item
            for item in catalog.get("models", [])
            if isinstance(item, dict) and item.get("id") == winner
        ),
        None,
    )
    if not isinstance(generator_catalog, dict):
        raise HoldoutError("generator pricing is absent from the frozen model catalog")
    judge_catalog = catalog.get("judge")
    if not isinstance(judge_catalog, dict) or judge_catalog.get("id") != judge_model:
        raise HoldoutError("judge pricing is absent from the frozen model catalog")
    max_tokens = judge_settings.get("max_tokens")
    if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or max_tokens <= 0:
        raise HoldoutError("judge output cap is invalid")
    judge = AnswerJudge(
        api_key="cost-estimate",
        model=judge_model,
        max_tokens=max_tokens,
        require_supported_parameters=bool(judge_settings.get("require_supported_parameters", False)),
        prompt_version=2,
    )
    generator = GroundedAnswerClient(
        api_key="cost-estimate",
        model=winner,
        max_tokens=int(generation["max_tokens"]),
        temperature=float(generation["temperature"]),
        system_prompt=str(generation["prompt"]),
        citation_mode=str(generation["citation_mode"]),
        require_supported_parameters=bool(generation["require_supported_parameters"]),
        reasoning_effort=generation.get("reasoning_effort"),
        exclude_reasoning=bool(generation.get("exclude_reasoning", False)),
        reconsider_insufficient_evidence=bool(
            generation.get("reconsider_insufficient_evidence", False)
        ),
    )
    judge_input = 0
    case_maximum_cost_usd: dict[str, float] = {}
    for case in cases:
        selected = contexts[case["id"]]
        previous_output = "x" * (int(generation["max_tokens"]) * 4)
        initial_payload = generator._payload(case["question"], selected)
        repair_payload = generator._payload(
            case["question"],
            selected,
            repair=True,
            previous_output=previous_output,
            validation_error="conservative_repair_estimate",
        )
        secondary_payload = repair_payload
        if generation.get("reconsider_insufficient_evidence", False):
            reconsideration_payload = generator._payload(
                case["question"],
                selected,
                reconsider_refusal=True,
                previous_output=previous_output,
            )
            if len(json.dumps(reconsideration_payload, ensure_ascii=False, sort_keys=True)) > len(
                json.dumps(repair_payload, ensure_ascii=False, sort_keys=True)
            ):
                secondary_payload = reconsideration_payload
        generation_inputs = sum(
            math.ceil(len(json.dumps(payload, ensure_ascii=False, sort_keys=True)) / 3)
            * (generator.retries + 1)
            for payload in (initial_payload, secondary_payload)
        )
        generation_outputs = (
            2 * (generator.retries + 1) * int(generation["max_tokens"])
        )
        generation_cost = (
            generation_inputs * float(generator_catalog["input_cost_per_million"])
            + generation_outputs * float(generator_catalog["output_cost_per_million"])
        ) / 1_000_000
        citations = tuple(
            Citation(index, chunk.pmid, chunk.chunk_id, chunk.title)
            for index, chunk in enumerate(selected[:5], 1)
        )
        worst_answer = AnswerResult(
            "answered",
            ("evidence " * int(generation["max_tokens"])).strip() + " [1].",
            citations,
        )
        payload = judge._payload(case["question"], worst_answer, selected)
        case_judge_input = math.ceil(
            len(json.dumps(payload, ensure_ascii=False, sort_keys=True)) / 3
        )
        judge_input += case_judge_input
        case_judge_cost = (
            case_judge_input * float(judge_catalog["input_cost_per_million"])
            + max_tokens * float(judge_catalog["output_cost_per_million"])
        ) / 1_000_000
        case_maximum_cost_usd[case["id"]] = math.fsum(
            (generation_cost, case_judge_cost)
        )
    judge_output = len(cases) * max_tokens
    judge_cost = (
        judge_input * float(judge_catalog["input_cost_per_million"])
        + judge_output * float(judge_catalog["output_cost_per_million"])
    ) / 1_000_000
    total = math.fsum(case_maximum_cost_usd.values())
    return {
        "method": "UTF-8 JSON characters/3; all generator retry/repair/reconsideration attempts; judge-v2 maximum output",
        "generation": generation_estimate,
        "judge": {
            "model": judge_model,
            "prompt_version": 2,
            "provider_calls": len(cases),
            "conservative_input_tokens": judge_input,
            "maximum_output_tokens": judge_output,
            "estimated_cost_usd": judge_cost,
        },
        "maximum_provider_calls": int(generation_estimate["provider_calls"]) + len(cases),
        "case_maximum_cost_usd": case_maximum_cost_usd,
        "estimated_max_cost_usd": total,
    }


def validate_holdout_cost_bound(max_cost_usd: float | None, estimate: float, hard_cap: float) -> str:
    if not math.isfinite(estimate) or estimate < 0 or estimate > hard_cap:
        raise HoldoutError("holdout estimate exceeds the frozen hard cap")
    if (
        isinstance(max_cost_usd, bool)
        or not isinstance(max_cost_usd, (int, float))
        or not math.isfinite(max_cost_usd)
        or max_cost_usd > hard_cap
    ):
        raise HoldoutError(f"--max-cost-usd must not exceed the frozen ${hard_cap:.2f} cap")
    try:
        return validate_live_cost(float(max_cost_usd), estimate)
    except BakeoffError as exc:
        raise HoldoutError(str(exc)) from exc


def _verdict_payload(verdict: JudgeVerdict | None) -> dict[str, Any] | None:
    if verdict is None:
        return None
    return {
        "claims": [
            {
                "text": claim.text,
                "supported": claim.supported,
                "citation_ids": list(claim.citation_ids),
            }
            for claim in verdict.claims
        ],
        "faithful": verdict.faithful,
        "relevant": verdict.relevant,
        "citations_correct": verdict.citations_correct,
        "refusal_correct": verdict.refusal_correct,
    }


def _saved_verdict(value: Any) -> JudgeVerdict | None:
    if not isinstance(value, dict) or set(value) != {
        "claims",
        "faithful",
        "relevant",
        "citations_correct",
        "refusal_correct",
    }:
        return None
    claims = value.get("claims")
    if not isinstance(claims, list):
        return None
    if any(
        not isinstance(item, dict)
        or set(item) != {"text", "supported", "citation_ids"}
        for item in claims
    ):
        return None
    try:
        return JudgeVerdict(
            tuple(
                AtomicClaim(
                    text=item["text"],
                    supported=item["supported"],
                    citation_ids=tuple(item["citation_ids"]),
                )
                for item in claims
            ),
            value["faithful"],
            value["relevant"],
            value["citations_correct"],
            value["refusal_correct"],
        )
    except (KeyError, TypeError):
        return None


def run_live(
    cases: list[dict[str, Any]],
    contexts: dict[str, tuple[RetrievedChunk, ...]],
    winner: str,
    judge_model: str,
    selection_hash: str,
    config_hash: str,
    context_hash: str,
    api_key: str,
    generation: dict[str, Any],
    judge_settings: dict[str, Any],
    *,
    existing_rows: Sequence[dict[str, Any]] = (),
    before_case: Callable[[str], None] | None = None,
    checkpoint: Callable[[list[dict[str, Any]]], None] | None = None,
) -> list[dict[str, Any]]:
    generator = GroundedAnswerClient(
        api_key=api_key,
        model=winner,
        max_tokens=int(generation["max_tokens"]),
        temperature=float(generation["temperature"]),
        system_prompt=str(generation["prompt"]),
        citation_mode=str(generation["citation_mode"]),
        require_supported_parameters=bool(generation["require_supported_parameters"]),
        reasoning_effort=generation.get("reasoning_effort"),
        exclude_reasoning=bool(generation.get("exclude_reasoning", False)),
        reconsider_insufficient_evidence=bool(generation.get("reconsider_insufficient_evidence", False)),
    )
    judge = AnswerJudge(
        api_key=api_key,
        model=judge_model,
        max_tokens=int(judge_settings["max_tokens"]),
        require_supported_parameters=bool(judge_settings.get("require_supported_parameters", False)),
        prompt_version=2,
    )
    result = [dict(row) for row in existing_rows]
    completed = {row.get("qa_id") for row in result}
    if (
        any(not isinstance(row, dict) for row in existing_rows)
        or any(not isinstance(qa_id, str) for qa_id in completed)
        or len(completed) != len(result)
        or not completed.issubset({case["id"] for case in cases})
    ):
        raise HoldoutError("partial holdout rows are malformed or duplicated")
    for case in cases:
        if case["id"] in completed:
            continue
        if before_case is not None:
            before_case(case["id"])
        started = time.perf_counter()
        answer = generator.answer(case["question"], contexts[case["id"]])
        generator_latency = (time.perf_counter() - started) * 1_000
        generator_metadata = dict(generator.last_metadata)
        started = time.perf_counter()
        verdict = judge.judge(
            case["question"],
            answer,
            contexts[case["id"]],
            expected_answerable=case["answerability"] == "answerable",
        )
        judge_latency = (time.perf_counter() - started) * 1_000
        judge_metadata = dict(judge.last_metadata)
        answer_payload = {
            "status": answer.status,
            "text": answer.text,
            "citations": [item.__dict__ for item in answer.citations],
        }
        result.append({
            "model": winner,
            "qa_id": case["id"],
            "answerability": case["answerability"],
            "selection_sha256": selection_hash,
            "config_sha256": config_hash,
            "contexts_sha256": context_hash,
            "answer": answer_payload,
            "judge": _verdict_payload(verdict),
            "structurally_valid": structurally_valid_answer(answer_payload, contexts[case["id"]]),
            "generator_metadata": {**generator_metadata, "latency_ms": generator_latency},
            "judge_metadata": {**judge_metadata, "latency_ms": judge_latency},
            "metadata": combined_usage(generator_metadata, judge_metadata, generator_latency, judge_latency),
        })
        result.sort(key=lambda row: row["qa_id"])
        if checkpoint is not None:
            checkpoint([dict(row) for row in result])
    return sorted(result, key=lambda row: row["qa_id"])


def saved_rows(
    outputs: dict[str, Any],
    cases: list[dict[str, Any]],
    contexts: dict[str, tuple[RetrievedChunk, ...]],
    winner: str,
    selection_hash: str,
    config_hash: str,
    context_hash: str,
    *,
    require_complete: bool = True,
) -> list[dict[str, Any]]:
    rows = outputs.get("outputs")
    if (
        not isinstance(rows, list)
        or len(rows) > len(cases)
        or (require_complete and len(rows) != len(cases))
    ):
        expected_count = "exactly seven" if require_complete else "at most seven"
        raise HoldoutError(f"holdout output must contain {expected_count} records")
    expected = {item["id"]: item for item in cases}
    qa_ids = [row.get("qa_id") for row in rows if isinstance(row, dict)]
    if (
        len(qa_ids) != len(rows)
        or not all(isinstance(qa_id, str) for qa_id in qa_ids)
        or len(set(qa_ids)) != len(qa_ids)
        or (
            set(qa_ids) != set(expected)
            if require_complete
            else not set(qa_ids).issubset(expected)
        )
    ):
        raise HoldoutError("holdout output must contain each frozen question exactly once")
    result = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != HOLDOUT_ROW_FIELDS:
            raise HoldoutError("holdout output row has unexpected fields")
        case = expected[row["qa_id"]]
        if (
            row.get("model") != winner
            or row.get("answerability") != case["answerability"]
            or row.get("selection_sha256") != selection_hash
            or row.get("config_sha256") != config_hash
            or row.get("contexts_sha256") != context_hash
        ):
            raise HoldoutError("holdout output provenance does not match the frozen selection")
        answer = row.get("answer")
        if not isinstance(answer, dict):
            raise HoldoutError("saved holdout answer must be a JSON object")
        structural = structurally_valid_answer(answer, contexts[row["qa_id"]])
        if row.get("structurally_valid") is not structural:
            raise HoldoutError("saved holdout structural verdict does not replay")
        verdict = _saved_verdict(row.get("judge"))
        expected_refusal = (
            answer.get("status") == "insufficient_evidence"
        ) == (case["answerability"] == "unanswerable")
        if (
            verdict is None
            or not validate_verdict(verdict, contexts[row["qa_id"]])
            or verdict.refusal_correct != expected_refusal
            or (
                answer.get("status") == "insufficient_evidence"
                and bool(verdict.claims)
            )
        ):
            raise HoldoutError("saved holdout judge verdict does not replay")
        generator_metadata, judge_metadata = row.get("generator_metadata"), row.get("judge_metadata")
        if not isinstance(generator_metadata, dict) or not isinstance(judge_metadata, dict):
            raise HoldoutError("holdout usage metadata is missing")
        generator_usage, judge_usage = dict(generator_metadata), dict(judge_metadata)
        generator_latency, judge_latency = generator_usage.pop("latency_ms", None), judge_usage.pop("latency_ms", None)
        if not all(
            isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0
            for value in (generator_latency, judge_latency)
        ):
            raise HoldoutError("holdout latency metadata is invalid")
        raw_hash = judge_usage.get("raw_output_sha256")
        if (
            not isinstance(raw_hash, str)
            or len(raw_hash) != 64
            or any(character not in "0123456789ABCDEF" for character in raw_hash)
        ):
            raise HoldoutError("holdout judge-v2 raw response hash is invalid")
        recomputed = combined_usage(generator_usage, judge_usage, generator_latency, judge_latency)
        if row.get("metadata") != recomputed:
            raise HoldoutError("holdout combined usage metadata does not replay")
        result.append(dict(row))
    return sorted(result, key=lambda row: row["qa_id"])


def build_output_packet(
    *,
    selection_hash: str,
    qa_hash: str,
    retriever_config_hash: str,
    contexts_hash: str,
    catalog_hash: str,
    cost_estimate: dict[str, Any],
    approved_max_cost_usd: float,
    rows: Sequence[dict[str, Any]],
    attempt_counts: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Build the exact packet used for partial checkpoints and final evidence."""

    return {
        "schema_version": 2,
        "selection_sha256": selection_hash,
        "qa_sha256": qa_hash,
        "retriever_config_sha256": retriever_config_hash,
        "contexts_sha256": contexts_hash,
        "model_catalog_sha256": catalog_hash,
        "cost_estimate": cost_estimate,
        "approved_max_cost_usd": approved_max_cost_usd,
        "attempt_counts": (
            dict(attempt_counts)
            if attempt_counts is not None
            else {str(row.get("qa_id")): 1 for row in rows}
        ),
        "outputs": [dict(row) for row in rows],
    }


def validate_output_packet(
    packet: dict[str, Any],
    *,
    selection_hash: str,
    qa_hash: str,
    retriever_config_hash: str,
    contexts_hash: str,
    catalog_hash: str,
    cost_estimate: dict[str, Any],
    hard_cap: float,
) -> float:
    """Validate immutable bindings and the saved owner-approved cost bound."""

    if set(packet) != HOLDOUT_OUTPUT_FIELDS:
        raise HoldoutError("saved holdout output packet has unexpected fields")
    expected_bindings = {
        "selection_sha256": selection_hash,
        "qa_sha256": qa_hash,
        "retriever_config_sha256": retriever_config_hash,
        "contexts_sha256": contexts_hash,
        "model_catalog_sha256": catalog_hash,
        "cost_estimate": cost_estimate,
    }
    if any(packet.get(field) != value for field, value in expected_bindings.items()):
        raise HoldoutError("saved holdout output packet does not match frozen inputs")
    approved = packet.get("approved_max_cost_usd")
    validate_holdout_cost_bound(approved, cost_estimate["estimated_max_cost_usd"], hard_cap)
    case_costs = cost_estimate.get("case_maximum_cost_usd")
    attempt_counts = packet.get("attempt_counts")
    if (
        not isinstance(case_costs, dict)
        or not case_costs
        or any(
            not isinstance(case_id, str)
            or isinstance(cost, bool)
            or not isinstance(cost, (int, float))
            or not math.isfinite(cost)
            or cost < 0
            for case_id, cost in case_costs.items()
        )
        or not isinstance(attempt_counts, dict)
        or any(
            case_id not in case_costs
            or isinstance(count, bool)
            or not isinstance(count, int)
            or count <= 0
            for case_id, count in attempt_counts.items()
        )
    ):
        raise HoldoutError("saved holdout cost reservations are malformed")
    rows = packet.get("outputs")
    completed_ids = {
        row.get("qa_id") for row in rows if isinstance(row, dict)
    } if isinstance(rows, list) else set()
    if any(attempt_counts.get(case_id, 0) < 1 for case_id in completed_ids):
        raise HoldoutError("completed holdout rows lack a cost reservation")
    reserved_cost = math.fsum(
        float(case_costs[case_id]) * count
        for case_id, count in attempt_counts.items()
    )
    if reserved_cost > float(approved) + 1e-12:
        raise HoldoutError("holdout attempt reservations exceed the approved cost cap")
    return float(approved)


def summarize(rows: list[dict[str, Any]]) -> tuple[dict[str, Any], bool]:
    metrics = candidate_summary(rows)
    answered = [row for row in rows if row["answer"]["status"] == "answered"]
    answered_faithfulness = (
        sum(row["judge"]["faithful"] is True for row in answered) / len(answered)
        if answered
        else 0.0
    )
    metrics["answered_faithfulness"] = answered_faithfulness
    passes = (
        metrics.get("outputs") == 7
        and metrics.get("judged_outputs") == 7
        and metrics.get("structural_validity") == 1.0
        and metrics.get("answerable_answer_rate") == 1.0
        and metrics.get("correct_refusal") == 1.0
        and metrics.get("relevancy") == 1.0
        and answered_faithfulness >= 0.80
        and metrics.get("citation_correctness", 0.0) >= 0.80
    )
    return metrics, passes


def expected_summary(
    *,
    rows: list[dict[str, Any]],
    qa_hash: str,
    retriever_config_hash: str,
    selection_hash: str,
    owner_report_hash: str,
    contexts_hash: str,
    outputs_hash: str,
    catalog_hash: str,
    winner: str,
    judge_model: str,
    cost_estimate: dict[str, Any],
    approved_max_cost_usd: float,
) -> dict[str, Any]:
    metrics, passes = summarize(rows)
    return {
        "schema_version": 2,
        "qa_sha256": qa_hash,
        "retriever_config_sha256": retriever_config_hash,
        "accepted_selection_sha256": selection_hash,
        "owner_validation_report_sha256": owner_report_hash,
        "contexts_sha256": contexts_hash,
        "outputs_sha256": outputs_hash,
        "model_catalog_sha256": catalog_hash,
        "winner": winner,
        "judge_model": judge_model,
        "holdout_scope": "five answerable and two unanswerable cases evaluated once",
        "cost_estimate": cost_estimate,
        "approved_max_cost_usd": approved_max_cost_usd,
        "metrics": metrics,
        "acceptance_thresholds": {
            "structural_validity": 1.0,
            "answerable_answer_rate": 1.0,
            "correct_refusal": 1.0,
            "relevancy": 1.0,
            "answered_faithfulness_minimum": 0.80,
            "citation_correctness_minimum": 0.80,
        },
        "passes": passes,
    }


def expected_final_config(summary: dict[str, Any], *, summary_hash: str) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "status": "frozen_after_passing_holdout",
        "winner": summary["winner"],
        "judge_model": summary["judge_model"],
        "qa_sha256": summary["qa_sha256"],
        "retriever_config_sha256": summary["retriever_config_sha256"],
        "accepted_selection_sha256": summary["accepted_selection_sha256"],
        "owner_validation_report_sha256": summary["owner_validation_report_sha256"],
        "holdout_contexts_sha256": summary["contexts_sha256"],
        "holdout_outputs_sha256": summary["outputs_sha256"],
        "holdout_summary_sha256": summary_hash,
        "holdout_metrics": summary["metrics"],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qa", type=Path, default=ROOT / "data/qa.json")
    parser.add_argument("--retriever-config", type=Path, default=ROOT / "artifacts/section5/frozen_config.json")
    parser.add_argument("--selection", type=Path, default=ROOT / "artifacts/section5/accepted_generator_v2_5.json")
    parser.add_argument("--owner-validation", type=Path, default=ROOT / "data/judge_validation_v2_5_report.json")
    parser.add_argument("--generator-config", type=Path, default=ROOT / "artifacts/section5/generator_v2_5_config.json")
    parser.add_argument("--judge-config", type=Path, default=ROOT / "artifacts/section5/generator_v2_5_judge_config.json")
    parser.add_argument("--model-catalog", type=Path, default=ROOT / "artifacts/section5/holdout_model_catalog.json")
    parser.add_argument("--contexts", type=Path, default=ROOT / "data/rag_holdout_contexts.json")
    parser.add_argument("--outputs", type=Path, default=ROOT / "data/rag_holdout_outputs.json")
    parser.add_argument("--result", type=Path, default=ROOT / "data/rag_holdout_summary.json")
    parser.add_argument("--frozen-generator-config", type=Path, default=ROOT / "artifacts/section5/generator_config.json")
    parser.add_argument("--live", action="store_true")
    parser.add_argument(
        "--resume-partial",
        action="store_true",
        help="resume a hash-validated partial live journal without rerunning completed cases",
    )
    parser.add_argument("--estimate-only", action="store_true")
    parser.add_argument("--finalize-saved", action="store_true")
    parser.add_argument("--max-cost-usd", type=float)
    parser.add_argument("--confirm-cost", action="store_true")
    args = parser.parse_args(argv)
    journal_path = args.outputs.with_name(f".{args.outputs.name}.partial.json")
    try:
        if sum((args.live, args.estimate_only, args.finalize_saved)) > 1:
            raise HoldoutError("choose only one of --live, --estimate-only, or --finalize-saved")
        if args.resume_partial and not args.live:
            raise HoldoutError("--resume-partial is valid only with --live")
        qa = load_json(args.qa)
        retriever_config = load_json(args.retriever_config)
        selection = load_json(args.selection)
        owner_report = load_json(args.owner_validation)
        generator_config = load_json(args.generator_config)
        judge_config = load_json(args.judge_config)
        catalog = load_json(args.model_catalog)
        context_packet = load_json(args.contexts)
        qa_hash = hash_file(args.qa)
        retriever_config_hash = hash_file(args.retriever_config)
        selection_hash = hash_file(args.selection)
        owner_report_hash = hash_file(args.owner_validation)
        generator_config_hash = hash_file(args.generator_config)
        judge_config_hash = hash_file(args.judge_config)
        catalog_hash = hash_file(args.model_catalog)
        context_hash = hash_file(args.contexts)
        cases = holdout_cases(qa)
        validate_config(retriever_config)
        winner, generation, judge_settings, hard_cap = validate_selection_bindings(
            selection,
            owner_report,
            generator_config,
            judge_config,
            qa_hash=qa_hash,
            retriever_config_hash=retriever_config_hash,
            selection_hash=selection_hash,
            owner_report_hash=owner_report_hash,
            generator_config_hash=generator_config_hash,
            judge_config_hash=judge_config_hash,
        )
        validate_context_provenance(
            context_packet,
            retriever_config_hash,
            qa_hash=qa_hash,
            selection_hash=selection_hash,
        )
        contexts = contexts_from(
            context_packet,
            cases,
            qa_hash=qa_hash,
            config_hash=retriever_config_hash,
        )
        catalog_models = validate_model_catalog(
            catalog,
            max_age_hours=24
            if (args.live and not args.resume_partial) or args.estimate_only
            else None,
        )
        if winner not in catalog_models or validate_judge_catalog(catalog) != selection.get("judge_model"):
            raise HoldoutError("accepted generator or judge is absent from the frozen catalog")
        validate_selected_parameter_support(catalog, [winner], generation)
        estimate = estimate_holdout_cost(
            cases,
            contexts,
            catalog,
            winner,
            selection["judge_model"],
            generation,
            judge_settings,
        )
        if args.estimate_only:
            print(json.dumps(estimate, sort_keys=True, indent=2))
            return 0

        if args.live:
            if any(path.exists() for path in (args.outputs, args.result, args.frozen_generator_config)):
                raise HoldoutError("one-shot holdout target already exists; overwrite is prohibited")
            print(validate_holdout_cost_bound(args.max_cost_usd, estimate["estimated_max_cost_usd"], hard_cap))
            if not args.confirm_cost:
                raise HoldoutError("--live requires --confirm-cost after reviewing the frozen estimate")
            api_key = os.environ.get("OPENROUTER_API_KEY")
            if not api_key:
                raise HoldoutError("--live requires OPENROUTER_API_KEY; no provider call was made")
            approved_cost = float(args.max_cost_usd)
            if args.resume_partial:
                if not journal_path.is_file():
                    raise HoldoutError("--resume-partial requires the existing partial journal")
                partial_packet = load_json(journal_path)
                saved_approved = validate_output_packet(
                    partial_packet,
                    selection_hash=selection_hash,
                    qa_hash=qa_hash,
                    retriever_config_hash=retriever_config_hash,
                    contexts_hash=context_hash,
                    catalog_hash=catalog_hash,
                    cost_estimate=estimate,
                    hard_cap=hard_cap,
                )
                if saved_approved != approved_cost:
                    raise HoldoutError("resume cost approval differs from the partial journal")
                existing_rows = saved_rows(
                    partial_packet,
                    cases,
                    contexts,
                    winner,
                    selection_hash,
                    retriever_config_hash,
                    context_hash,
                    require_complete=False,
                )
                attempt_counts = dict(partial_packet["attempt_counts"])
            else:
                if journal_path.exists():
                    raise HoldoutError(
                        "partial holdout journal already exists; use --live --resume-partial"
                    )
                existing_rows = []
                attempt_counts = {}
                partial_packet = build_output_packet(
                    selection_hash=selection_hash,
                    qa_hash=qa_hash,
                    retriever_config_hash=retriever_config_hash,
                    contexts_hash=context_hash,
                    catalog_hash=catalog_hash,
                    cost_estimate=estimate,
                    approved_max_cost_usd=approved_cost,
                    rows=existing_rows,
                    attempt_counts=attempt_counts,
                )
                write_json_atomic(journal_path, partial_packet, overwrite=False)

            journal_rows = [dict(row) for row in existing_rows]

            def checkpoint(rows: list[dict[str, Any]]) -> None:
                nonlocal journal_rows
                journal_rows = [dict(row) for row in rows]
                packet = build_output_packet(
                    selection_hash=selection_hash,
                    qa_hash=qa_hash,
                    retriever_config_hash=retriever_config_hash,
                    contexts_hash=context_hash,
                    catalog_hash=catalog_hash,
                    cost_estimate=estimate,
                    approved_max_cost_usd=approved_cost,
                    rows=rows,
                    attempt_counts=attempt_counts,
                )
                write_json_atomic(journal_path, packet, overwrite=True)

            def reserve_case(case_id: str) -> None:
                nonlocal attempt_counts
                proposed = dict(attempt_counts)
                proposed[case_id] = proposed.get(case_id, 0) + 1
                packet = build_output_packet(
                    selection_hash=selection_hash,
                    qa_hash=qa_hash,
                    retriever_config_hash=retriever_config_hash,
                    contexts_hash=context_hash,
                    catalog_hash=catalog_hash,
                    cost_estimate=estimate,
                    approved_max_cost_usd=approved_cost,
                    rows=journal_rows,
                    attempt_counts=proposed,
                )
                validate_output_packet(
                    packet,
                    selection_hash=selection_hash,
                    qa_hash=qa_hash,
                    retriever_config_hash=retriever_config_hash,
                    contexts_hash=context_hash,
                    catalog_hash=catalog_hash,
                    cost_estimate=estimate,
                    hard_cap=hard_cap,
                )
                attempt_counts = proposed
                write_json_atomic(journal_path, packet, overwrite=True)

            live_rows = run_live(
                cases,
                contexts,
                winner,
                selection["judge_model"],
                selection_hash,
                retriever_config_hash,
                context_hash,
                api_key,
                generation,
                judge_settings,
                existing_rows=existing_rows,
                before_case=reserve_case,
                checkpoint=checkpoint,
            )
            checkpoint(live_rows)
            output_packet = load_json(journal_path)
            validate_output_packet(
                output_packet,
                selection_hash=selection_hash,
                qa_hash=qa_hash,
                retriever_config_hash=retriever_config_hash,
                contexts_hash=context_hash,
                catalog_hash=catalog_hash,
                cost_estimate=estimate,
                hard_cap=hard_cap,
            )
            saved_rows(
                output_packet,
                cases,
                contexts,
                winner,
                selection_hash,
                retriever_config_hash,
                context_hash,
            )
            if args.outputs.exists():
                raise HoldoutError("one-shot holdout target appeared during execution")
            os.replace(journal_path, args.outputs)
        else:
            if args.finalize_saved and not args.outputs.is_file() and journal_path.is_file():
                partial_packet = load_json(journal_path)
                validate_output_packet(
                    partial_packet,
                    selection_hash=selection_hash,
                    qa_hash=qa_hash,
                    retriever_config_hash=retriever_config_hash,
                    contexts_hash=context_hash,
                    catalog_hash=catalog_hash,
                    cost_estimate=estimate,
                    hard_cap=hard_cap,
                )
                saved_rows(
                    partial_packet,
                    cases,
                    contexts,
                    winner,
                    selection_hash,
                    retriever_config_hash,
                    context_hash,
                )
                os.replace(journal_path, args.outputs)
            if not args.outputs.is_file():
                raise HoldoutError("saved holdout outputs do not exist")
            output_packet = load_json(args.outputs)
            validate_output_packet(
                output_packet,
                selection_hash=selection_hash,
                qa_hash=qa_hash,
                retriever_config_hash=retriever_config_hash,
                contexts_hash=context_hash,
                catalog_hash=catalog_hash,
                cost_estimate=estimate,
                hard_cap=hard_cap,
            )

        rows = saved_rows(
            output_packet,
            cases,
            contexts,
            winner,
            selection_hash,
            retriever_config_hash,
            context_hash,
        )
        summary = expected_summary(
            rows=rows,
            qa_hash=qa_hash,
            retriever_config_hash=retriever_config_hash,
            selection_hash=selection_hash,
            owner_report_hash=owner_report_hash,
            contexts_hash=context_hash,
            outputs_hash=hash_file(args.outputs),
            catalog_hash=catalog_hash,
            winner=winner,
            judge_model=selection["judge_model"],
            cost_estimate=estimate,
            approved_max_cost_usd=float(output_packet["approved_max_cost_usd"]),
        )
        if args.live or args.finalize_saved:
            if args.result.exists() or args.frozen_generator_config.exists():
                raise HoldoutError("holdout summary/final configuration already exists; overwrite is prohibited")
            write_json_atomic(args.result, summary, overwrite=False)
            if summary["passes"]:
                final_config = expected_final_config(summary, summary_hash=hash_file(args.result))
                write_json_atomic(args.frozen_generator_config, final_config, overwrite=False)
        else:
            if load_json(args.result) != summary:
                raise HoldoutError("saved holdout summary does not replay")
            if summary["passes"]:
                expected_final = expected_final_config(summary, summary_hash=hash_file(args.result))
                if load_json(args.frozen_generator_config) != expected_final:
                    raise HoldoutError("frozen generator configuration does not replay")
            elif args.frozen_generator_config.exists():
                raise HoldoutError("a failed holdout cannot have an accepted final generator config")
    except (BakeoffError, OSError, KeyError, TypeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(summary, sort_keys=True))
    return 0 if summary["passes"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

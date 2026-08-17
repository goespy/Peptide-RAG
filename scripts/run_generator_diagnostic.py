#!/usr/bin/env python3
"""Run a versioned generator-only development diagnostic before paid judging."""

from __future__ import annotations

import argparse
from collections import Counter
import json
import math
import os
from pathlib import Path
import sys
import time
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_rag_bakeoff import (  # noqa: E402
    BakeoffError,
    contexts_from,
    estimate_bakeoff_cost,
    hash_file,
    load_json,
    offline_rows,
    realized_usage,
    structurally_valid_answer,
    validate_config,
    validate_live_cost,
    validate_model_catalog,
    validate_qa,
    validate_judge_catalog,
    write_json_atomic,
)
from src.generation import GroundedAnswerClient  # noqa: E402


def validate_diagnostic_cost_bound(
    max_cost_usd: float | None,
    estimated_cost_usd: float,
    configured_hard_cap_usd: float,
) -> str:
    """Enforce this experiment's hard ceiling before any credential or call."""

    if (
        isinstance(configured_hard_cap_usd, bool)
        or not isinstance(configured_hard_cap_usd, (int, float))
        or not math.isfinite(configured_hard_cap_usd)
        or configured_hard_cap_usd <= 0
    ):
        raise BakeoffError("generator diagnostic config needs a positive hard cost cap")
    if (
        isinstance(estimated_cost_usd, bool)
        or not isinstance(estimated_cost_usd, (int, float))
        or not math.isfinite(estimated_cost_usd)
        or estimated_cost_usd < 0
        or estimated_cost_usd > configured_hard_cap_usd
    ):
        raise BakeoffError(
            "conservative estimate exceeds the generator diagnostic's frozen hard cap"
        )
    if max_cost_usd is not None and max_cost_usd > configured_hard_cap_usd:
        raise BakeoffError(
            f"generator diagnostic cannot exceed its ${configured_hard_cap_usd:.2f} hard cap"
        )
    return validate_live_cost(max_cost_usd, estimated_cost_usd)


def generator_cost_only(estimate: dict[str, Any]) -> dict[str, Any]:
    rows = estimate.get("generation")
    if not isinstance(rows, list):
        raise BakeoffError("generation cost estimate is malformed")
    return {
        "method": estimate.get("method"),
        "generation": rows,
        "maximum_provider_calls": sum(int(row["provider_calls"]) for row in rows),
        "estimated_max_cost_usd": sum(float(row["estimated_cost_usd"]) for row in rows),
        "judge_calls": 0,
        "judge_cost_usd": 0.0,
    }


def validate_reviewed_estimate(config: dict[str, Any], actual: float) -> None:
    """Bind a reviewed pre-run estimate when the frozen experiment records one."""

    diagnostic = config.get("generator_diagnostic")
    reviewed = diagnostic.get("reviewed_estimate_usd") if isinstance(diagnostic, dict) else None
    if reviewed is None:
        return
    if (
        isinstance(reviewed, bool)
        or not isinstance(reviewed, (int, float))
        or not math.isfinite(reviewed)
        or not math.isclose(float(reviewed), actual, rel_tol=0.0, abs_tol=1e-12)
    ):
        raise BakeoffError("reviewed generator estimate does not match frozen inputs")


def select_diagnostic_models(
    config: dict[str, Any], catalog_models: Sequence[str]
) -> tuple[str, ...]:
    """Select the frozen nonempty subset of validated catalog candidates."""

    requested = config.get("generator_candidates")
    if (
        not isinstance(requested, list)
        or not requested
        or any(not isinstance(model, str) or not model.strip() for model in requested)
        or len(set(requested)) != len(requested)
    ):
        raise BakeoffError(
            "generator config must freeze a nonempty list of distinct candidate models"
        )
    unknown = [model for model in requested if model not in catalog_models]
    if unknown:
        raise BakeoffError(
            "generator config contains a candidate not present in the validated model catalog"
        )
    return tuple(requested)


def validate_selected_parameter_support(
    catalog: dict[str, Any], models: Sequence[str], generation: dict[str, Any]
) -> None:
    """Require catalog-advertised support for selected experimental parameters."""

    required = {"response_format", "structured_outputs"}
    if generation.get("reasoning_effort") is not None:
        required.add("reasoning")
    entries = {
        item.get("id"): item
        for item in catalog.get("models", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    for model in models:
        item = entries.get(model)
        supported = item.get("supported_parameters") if isinstance(item, dict) else None
        if not isinstance(supported, list) or not required.issubset(set(supported)):
            raise BakeoffError(
                f"selected model {model} does not advertise every frozen generation parameter"
            )


def validate_experiment_bindings(
    config: dict[str, Any],
    *,
    qa_hash: str,
    context_hash: str,
    catalog_hash: str,
    outputs_path: Path,
    result_path: Path,
) -> None:
    """Bind a diagnostic to its frozen inputs and protect parent evidence."""

    expected_hashes = {
        "qa_sha256": qa_hash,
        "contexts_sha256": context_hash,
        "model_catalog_sha256": catalog_hash,
    }
    for field, actual in expected_hashes.items():
        if config.get(field) != actual:
            raise BakeoffError(f"generator config {field} does not match the selected artifact")

    diagnostic = config.get("generator_diagnostic")
    if not isinstance(diagnostic, dict) or diagnostic.get("judge_calls") != 0:
        raise BakeoffError("generator-only diagnostic must freeze exactly zero judge calls")

    if outputs_path.resolve() == result_path.resolve():
        raise BakeoffError("generator outputs and summary must use different files")

    artifact_paths = config.get("artifact_paths")
    if not isinstance(artifact_paths, dict):
        raise BakeoffError("generator config must freeze its output artifact paths")
    for field, selected in (("outputs", outputs_path), ("summary", result_path)):
        relative = artifact_paths.get(field)
        if not isinstance(relative, str) or not relative.strip():
            raise BakeoffError(f"generator config must freeze its {field} artifact path")
        expected = (ROOT / relative).resolve()
        if not expected.is_relative_to(ROOT.resolve()):
            raise BakeoffError("generator artifact paths must stay inside the repository")
        if selected.resolve() != expected:
            raise BakeoffError(f"selected {field} path does not match the frozen generator config")

    parent_hashes = {
        value.upper()
        for field, value in config.items()
        if field.startswith("parent_")
        and field.endswith("_sha256")
        and isinstance(value, str)
        and len(value) == 64
    }
    for selected in (outputs_path, result_path):
        if selected.exists() and hash_file(selected).upper() in parent_hashes:
            raise BakeoffError("refusing to overwrite a parent experiment artifact")


def summarize(grouped: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    candidates: dict[str, Any] = {}
    for model, rows in grouped.items():
        answerable = [row for row in rows if row["answerability"] == "answerable"]
        unanswerable = [row for row in rows if row["answerability"] == "unanswerable"]
        final_outcomes = Counter()
        finish_reasons = Counter()
        validation_errors = Counter()
        for row in rows:
            generator = row.get("metadata", {})
            if isinstance(generator, dict):
                final_outcomes[str(generator.get("final_outcome"))] += 1
                attempts = generator.get("attempts", [])
                if isinstance(attempts, list):
                    for attempt in attempts:
                        if not isinstance(attempt, dict):
                            continue
                        finish_reasons[str(attempt.get("finish_reason"))] += 1
                        error = attempt.get("validation_error")
                        if error is not None:
                            validation_errors[str(error)] += 1
        answerable_answers = sum(row.get("answer", {}).get("status") == "answered" for row in answerable)
        refusal_shapes = sum(
            row.get("answer", {}).get("status") == "insufficient_evidence" for row in unanswerable
        )
        model_refusals = sum(
            row.get("answer", {}).get("status") == "insufficient_evidence"
            and row.get("metadata", {}).get("final_outcome")
            in {
                "model_insufficient_evidence",
                "model_insufficient_evidence_after_failed_reconsideration",
                "model_insufficient_evidence_after_repair",
                "model_insufficient_evidence_after_reconsideration",
            }
            for row in unanswerable
        )
        policy_refusals = sum(
            row.get("answer", {}).get("status") == "insufficient_evidence"
            and row.get("metadata", {}).get("final_outcome") == "preflight_insufficient_evidence"
            and row.get("metadata", {}).get("failure_reason") == "personalized_or_dosing_request"
            for row in unanswerable
        )
        correct_system_refusals = model_refusals + policy_refusals
        structurally_valid = sum(row.get("structurally_valid") is True for row in rows)
        candidates[model] = {
            "answerable_answer_count": answerable_answers,
            "answerable_case_count": len(answerable),
            "unanswerable_insufficient_evidence_shape_count": refusal_shapes,
            "unanswerable_model_refusal_count": model_refusals,
            "unanswerable_policy_refusal_count": policy_refusals,
            "unanswerable_correct_system_refusal_count": correct_system_refusals,
            "unanswerable_case_count": len(unanswerable),
            "structurally_valid_count": structurally_valid,
            "total_case_count": len(rows),
            "ready_for_paid_judging": (
                answerable_answers == len(answerable)
                and correct_system_refusals == len(unanswerable)
                and structurally_valid == len(rows)
            ),
            "final_outcomes": dict(sorted(final_outcomes.items())),
            "finish_reasons": dict(sorted(finish_reasons.items())),
            "validation_errors": dict(sorted(validation_errors.items())),
        }
    return {"candidates": candidates, "winner": None, "selection_status": "diagnostic_only_not_judged"}


def run_live_generators(
    cases: list[dict[str, Any]],
    contexts: dict[str, tuple[Any, ...]],
    *,
    config_hash: str,
    context_hash: str,
    api_key: str,
    models: Sequence[str],
    generation: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {model: [] for model in models}
    for model in models:
        client = GroundedAnswerClient(
            api_key=api_key,
            model=model,
            max_tokens=int(generation["max_tokens"]),
            temperature=float(generation["temperature"]),
            system_prompt=str(generation["prompt"]),
            citation_mode=str(generation.get("citation_mode", "declared")),
            require_supported_parameters=bool(generation.get("require_supported_parameters", False)),
            reasoning_effort=generation.get("reasoning_effort"),
            exclude_reasoning=bool(generation.get("exclude_reasoning", False)),
            reconsider_insufficient_evidence=bool(
                generation.get("reconsider_insufficient_evidence", False)
            ),
        )
        for case in cases:
            started = time.perf_counter()
            answer = client.answer(case["question"], contexts[case["id"]])
            latency_ms = (time.perf_counter() - started) * 1_000
            answer_payload = {
                "status": answer.status,
                "text": answer.text,
                "citations": [item.__dict__ for item in answer.citations],
            }
            metadata = dict(client.last_metadata)
            metadata["latency_ms"] = latency_ms
            grouped[model].append(
                {
                    "model": model,
                    "qa_id": case["id"],
                    "answerability": case["answerability"],
                    "config_sha256": config_hash,
                    "contexts_sha256": context_hash,
                    "answer": answer_payload,
                    "structurally_valid": structurally_valid_answer(answer_payload, contexts[case["id"]]),
                    "metadata": metadata,
                }
            )
    return grouped


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qa", type=Path, default=ROOT / "data/qa.json")
    parser.add_argument("--config", type=Path, default=ROOT / "artifacts/section5/generator_v2_5_config.json")
    parser.add_argument("--contexts", type=Path, default=ROOT / "data/rag_development_contexts.json")
    parser.add_argument("--model-catalog", type=Path, default=ROOT / "artifacts/section5/model_candidates_judge_refresh.json")
    parser.add_argument("--outputs", type=Path, default=ROOT / "data/rag_generator_v2_5_outputs.json")
    parser.add_argument("--result", type=Path, default=ROOT / "data/rag_generator_v2_5_summary.json")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--estimate-only", action="store_true")
    parser.add_argument("--max-cost-usd", type=float)
    parser.add_argument("--confirm-cost", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    try:
        if not args.estimate_only and args.result.exists() and not args.overwrite:
            raise BakeoffError(f"refusing to overwrite existing file: {args.result}; pass --overwrite")
        if args.live and args.outputs.exists() and not args.overwrite:
            raise BakeoffError(f"refusing to overwrite existing file: {args.outputs}; pass --overwrite")
        qa = load_json(args.qa)
        config = load_json(args.config)
        context_packet = load_json(args.contexts)
        catalog = load_json(args.model_catalog)
        config_hash = hash_file(args.config)
        context_hash = hash_file(args.contexts)
        qa_hash = hash_file(args.qa)
        catalog_hash = hash_file(args.model_catalog)
        validate_experiment_bindings(
            config,
            qa_hash=qa_hash,
            context_hash=context_hash,
            catalog_hash=catalog_hash,
            outputs_path=args.outputs,
            result_path=args.result,
        )
        catalog_models = validate_model_catalog(
            catalog, max_age_hours=24 if args.live or args.estimate_only else None
        )
        models = select_diagnostic_models(config, catalog_models)
        judge_model = validate_judge_catalog(catalog)
        cases = validate_qa(qa)
        generation = validate_config(config)
        validate_selected_parameter_support(catalog, models, generation)
        contexts = contexts_from(
            context_packet,
            cases,
            qa_hash=qa_hash,
            config_hash=config.get("retriever_config_sha256", config_hash),
        )
        estimate = generator_cost_only(
            estimate_bakeoff_cost(cases, contexts, catalog, models, judge_model, generation)
        )
        validate_reviewed_estimate(config, estimate["estimated_max_cost_usd"])
        if args.estimate_only:
            print(json.dumps(estimate, indent=2, sort_keys=True))
            return 0
        if args.live:
            diagnostic_config = config.get("generator_diagnostic")
            if not isinstance(diagnostic_config, dict):
                raise BakeoffError("generator config must record its diagnostic cost gate")
            print(
                validate_diagnostic_cost_bound(
                    args.max_cost_usd,
                    estimate["estimated_max_cost_usd"],
                    diagnostic_config.get("hard_cost_cap_usd"),
                )
            )
            if not args.confirm_cost:
                raise BakeoffError("--live requires --confirm-cost after reviewing the maximum-cost status")
            api_key = os.environ.get("OPENROUTER_API_KEY")
            if not api_key:
                raise BakeoffError("--live requires OPENROUTER_API_KEY; no provider call was made")
            grouped = run_live_generators(
                cases,
                contexts,
                config_hash=config_hash,
                context_hash=context_hash,
                api_key=api_key,
                models=models,
                generation=generation,
            )
            write_json_atomic(
                args.outputs,
                {"schema_version": 2, "experiment": config["experiment_id"], "outputs": [row for rows in grouped.values() for row in rows]},
                overwrite=args.overwrite,
            )
        else:
            grouped = offline_rows(
                load_json(args.outputs), cases, contexts, config_hash, context_hash, models
            )
        result = {
            "schema_version": 2,
            "experiment": config["experiment_id"],
            "qa_sha256": qa_hash,
            "config_sha256": config_hash,
            "contexts_sha256": context_hash,
            "model_catalog_sha256": catalog_hash,
            "outputs_sha256": hash_file(args.outputs),
            "live_calls": args.live,
            "approved_max_cost_usd": args.max_cost_usd if args.live else None,
            "cost_estimate": estimate,
            "actual_usage": {
                "aggregate": realized_usage(grouped),
                "by_model": {
                    model: realized_usage({model: rows}) for model, rows in grouped.items()
                },
            },
            "diagnostic": summarize(grouped),
        }
        write_json_atomic(args.result, result, overwrite=args.overwrite)
    except (BakeoffError, OSError, KeyError, TypeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result["diagnostic"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

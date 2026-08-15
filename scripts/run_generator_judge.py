#!/usr/bin/env python3
"""Judge one accepted generator artifact without regenerating or retrieving."""

from __future__ import annotations

import argparse
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
    combined_usage,
    contexts_from,
    hash_file,
    load_json,
    offline_rows,
    validate_config,
    validate_judge_catalog,
    validate_live_cost,
    validate_model_catalog,
    validate_qa,
    write_json_atomic,
)
from src.generation import AnswerResult, Citation  # noqa: E402
from src.judge import AnswerJudge, AtomicClaim, JudgeVerdict, validate_verdict  # noqa: E402
from src.rag_metrics import select_winner  # noqa: E402


def _repo_path(relative: object, *, field: str) -> Path:
    if not isinstance(relative, str) or not relative.strip():
        raise BakeoffError(f"judge config must freeze {field}")
    candidate = (ROOT / relative).resolve()
    try:
        candidate.relative_to(ROOT.resolve())
    except ValueError as exc:
        raise BakeoffError(f"judge config {field} must remain inside the repository") from exc
    return candidate


def validate_judge_config(
    config: dict[str, Any],
    *,
    hashes: dict[str, str],
    outputs_path: Path,
    result_path: Path,
    catalog: dict[str, Any],
) -> dict[str, Any]:
    """Validate a frozen judge-only experiment and its exact inputs/outputs."""

    if config.get("status") != "frozen_before_paid_judging" or config.get("selected") is not True:
        raise BakeoffError("judge-only configuration is not frozen")
    for field, actual in hashes.items():
        if config.get(field) != actual:
            raise BakeoffError(f"judge config {field} does not match the selected artifact")
    artifact_paths = config.get("artifact_paths")
    if not isinstance(artifact_paths, dict):
        raise BakeoffError("judge config must freeze artifact paths")
    expected_paths = {
        "outputs": outputs_path.resolve(),
        "summary": result_path.resolve(),
    }
    for field, selected in expected_paths.items():
        if _repo_path(artifact_paths.get(field), field=field) != selected:
            raise BakeoffError(f"selected {field} path does not match the frozen judge config")
    if outputs_path.resolve() == result_path.resolve():
        raise BakeoffError("judge outputs and summary must be separate files")
    for field, value in config.items():
        if field.startswith("parent_") and field.endswith("_sha256") and value in {
            hash_file(path) for path in (outputs_path, result_path) if path.exists()
        }:
            raise BakeoffError("judge output target matches a protected parent artifact")

    judge = config.get("judge")
    if not isinstance(judge, dict):
        raise BakeoffError("judge config must contain judge settings")
    model = validate_judge_catalog(catalog)
    max_tokens = judge.get("max_tokens")
    hard_cap = judge.get("hard_cost_cap_usd")
    if (
        judge.get("model") != model
        or judge.get("temperature") != 0
        or isinstance(max_tokens, bool)
        or not isinstance(max_tokens, int)
        or not 1 <= max_tokens <= 2_000
        or judge.get("require_supported_parameters") is not True
        or isinstance(hard_cap, bool)
        or not isinstance(hard_cap, (int, float))
        or not math.isfinite(hard_cap)
        or hard_cap <= 0
        or config.get("generator_calls") != 0
        or config.get("judge_calls") != 13
        or config.get("holdout_status") != "untouched"
    ):
        raise BakeoffError("judge-only settings violate the frozen call, safety, or cost contract")
    entry = catalog.get("judge")
    supported = entry.get("supported_parameters") if isinstance(entry, dict) else None
    if not isinstance(supported, list) or not {
        "response_format",
        "structured_outputs",
    }.issubset(set(supported)):
        raise BakeoffError("judge model does not advertise the required structured-output parameters")
    return {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": 0,
        "require_supported_parameters": True,
        "hard_cost_cap_usd": float(hard_cap),
    }


def validate_generator_gate(
    generator_summary: dict[str, Any],
    *,
    model: str,
    generator_config_hash: str,
    generator_outputs_hash: str,
    qa_hash: str,
    contexts_hash: str,
) -> None:
    """Open judging only for the exact 10/10, 3/3, 13/13 development run."""

    if (
        generator_summary.get("config_sha256") != generator_config_hash
        or generator_summary.get("outputs_sha256") != generator_outputs_hash
        or generator_summary.get("qa_sha256") != qa_hash
        or generator_summary.get("contexts_sha256") != contexts_hash
        or generator_summary.get("live_calls") is not True
    ):
        raise BakeoffError("generator summary is not bound to the selected live development run")
    diagnostic = generator_summary.get("diagnostic")
    candidates = diagnostic.get("candidates") if isinstance(diagnostic, dict) else None
    candidate = candidates.get(model) if isinstance(candidates, dict) else None
    if (
        not isinstance(candidate, dict)
        or set(candidates) != {model}
        or candidate.get("answerable_answer_count") != 10
        or candidate.get("answerable_case_count") != 10
        or candidate.get("unanswerable_correct_system_refusal_count") != 3
        or candidate.get("unanswerable_case_count") != 3
        or candidate.get("structurally_valid_count") != 13
        or candidate.get("total_case_count") != 13
        or candidate.get("ready_for_paid_judging") is not True
    ):
        raise BakeoffError("generator development run has not passed the frozen 10/10, 3/3, 13/13 judge gate")


def _answer(row: dict[str, Any]) -> AnswerResult:
    raw = row.get("answer")
    if not isinstance(raw, dict) or not isinstance(raw.get("citations"), list):
        raise BakeoffError("generator output contains a malformed answer")
    citations = []
    for item in raw["citations"]:
        if not isinstance(item, dict):
            raise BakeoffError("generator output contains a malformed citation")
        try:
            citations.append(
                Citation(int(item["citation_id"]), item["pmid"], item["chunk_id"], item["title"])
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise BakeoffError("generator output contains a malformed citation") from exc
    try:
        return AnswerResult(raw["status"], raw["text"], tuple(citations))
    except (KeyError, TypeError) as exc:
        raise BakeoffError("generator output contains a malformed answer") from exc


def estimate_judge_cost(
    cases: Sequence[dict[str, Any]],
    contexts: dict[str, tuple[Any, ...]],
    grouped: dict[str, list[dict[str, Any]]],
    *,
    model: str,
    max_tokens: int,
    catalog: dict[str, Any],
) -> dict[str, Any]:
    """Estimate exactly 13 judge calls from frozen answer/evidence payloads."""

    entry = catalog.get("judge")
    if not isinstance(entry, dict) or entry.get("id") != model:
        raise BakeoffError("judge price is unavailable")
    client = AnswerJudge(
        api_key="cost-estimate",
        model=model,
        max_tokens=max_tokens,
        require_supported_parameters=True,
    )
    rows = {row["qa_id"]: row for row in next(iter(grouped.values()))}
    input_tokens = 0
    for case in cases:
        payload = client._payload(case["question"], _answer(rows[case["id"]]), contexts[case["id"]])
        input_tokens += math.ceil(len(json.dumps(payload, ensure_ascii=False, sort_keys=True)) / 3)
    output_tokens = len(cases) * max_tokens
    cost = (
        input_tokens * float(entry["input_cost_per_million"])
        + output_tokens * float(entry["output_cost_per_million"])
    ) / 1_000_000
    return {
        "method": "UTF-8 JSON characters/3 for conservative input tokens; maximum structured output tokens; one call per frozen development case",
        "model": model,
        "judge_calls": len(cases),
        "generator_calls": 0,
        "conservative_input_tokens": input_tokens,
        "maximum_output_tokens": output_tokens,
        "estimated_max_cost_usd": cost,
    }


def validate_judge_cost_bound(
    max_cost_usd: float | None,
    estimated_cost_usd: float,
    hard_cap_usd: float,
) -> str:
    if estimated_cost_usd > hard_cap_usd:
        raise BakeoffError("judge estimate exceeds its frozen hard cost cap")
    if max_cost_usd is not None and max_cost_usd > hard_cap_usd:
        raise BakeoffError("approved judge bound exceeds its frozen hard cost cap")
    return validate_live_cost(max_cost_usd, estimated_cost_usd)


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


def run_live_judges(
    cases: Sequence[dict[str, Any]],
    contexts: dict[str, tuple[Any, ...]],
    grouped: dict[str, list[dict[str, Any]]],
    *,
    judge: AnswerJudge,
    judge_config_hash: str,
    generator_outputs_hash: str,
) -> dict[str, list[dict[str, Any]]]:
    """Call only the judge; generator answers and contexts are immutable inputs."""

    model, source_rows = next(iter(grouped.items()))
    by_id = {row["qa_id"]: row for row in source_rows}
    judged: list[dict[str, Any]] = []
    for case in cases:
        source = by_id[case["id"]]
        answer = _answer(source)
        started = time.perf_counter()
        verdict = judge.judge(
            case["question"],
            answer,
            contexts[case["id"]],
            expected_answerable=case["answerability"] == "answerable",
        )
        judge_latency = (time.perf_counter() - started) * 1_000
        generator_metadata = dict(source.get("metadata", {}))
        judge_metadata = dict(judge.last_metadata)
        judged.append(
            {
                "model": model,
                "qa_id": case["id"],
                "answerability": case["answerability"],
                "answer": source["answer"],
                "structurally_valid": source["structurally_valid"],
                "generator_config_sha256": source["config_sha256"],
                "generator_outputs_sha256": generator_outputs_hash,
                "judge_config_sha256": judge_config_hash,
                "judge": _verdict_payload(verdict),
                "generator_metadata": generator_metadata,
                "judge_metadata": {**judge_metadata, "latency_ms": judge_latency},
                "metadata": combined_usage(
                    generator_metadata,
                    judge_metadata,
                    float(generator_metadata.get("latency_ms", 0.0)),
                    judge_latency,
                ),
            }
        )
    return {model: judged}


def offline_judged_rows(
    packet: dict[str, Any],
    source_grouped: dict[str, list[dict[str, Any]]],
    contexts: dict[str, tuple[Any, ...]],
    *,
    judge_config_hash: str,
    generator_outputs_hash: str,
) -> dict[str, list[dict[str, Any]]]:
    rows = packet.get("outputs")
    if (
        packet.get("judge_config_sha256") != judge_config_hash
        or packet.get("generator_outputs_sha256") != generator_outputs_hash
        or not isinstance(rows, list)
    ):
        raise BakeoffError("judged outputs are not bound to the selected source artifacts")
    model, source_rows = next(iter(source_grouped.items()))
    source = {row["qa_id"]: row for row in source_rows}
    if len(rows) != len(source):
        raise BakeoffError("judged outputs must contain exactly one row per development case")
    validated = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or row.get("model") != model or row.get("qa_id") not in source:
            raise BakeoffError("judged output row does not match the selected generator")
        qa_id = row["qa_id"]
        if qa_id in seen or row.get("answer") != source[qa_id].get("answer"):
            raise BakeoffError("judged outputs duplicate or alter a generator answer")
        if (
            row.get("answerability") != source[qa_id].get("answerability")
            or row.get("structurally_valid") != source[qa_id].get("structurally_valid")
            or row.get("generator_config_sha256") != source[qa_id].get("config_sha256")
            or row.get("generator_outputs_sha256") != generator_outputs_hash
            or row.get("judge_config_sha256") != judge_config_hash
        ):
            raise BakeoffError("judged output row has invalid source bindings")
        verdict = row.get("judge")
        if verdict is not None:
            if not isinstance(verdict, dict) or not isinstance(verdict.get("claims"), list):
                raise BakeoffError("saved judge verdict is malformed")
            try:
                parsed = JudgeVerdict(
                    tuple(
                        AtomicClaim(item["text"], item["supported"], tuple(item["citation_ids"]))
                        for item in verdict["claims"]
                    ),
                    verdict["faithful"],
                    verdict["relevant"],
                    verdict["citations_correct"],
                    verdict["refusal_correct"],
                )
            except (KeyError, TypeError) as exc:
                raise BakeoffError("saved judge verdict is malformed") from exc
            expected_refusal = (
                source[qa_id]["answer"]["status"] == "insufficient_evidence"
            ) == (source[qa_id]["answerability"] == "unanswerable")
            if not validate_verdict(parsed, contexts[qa_id]) or parsed.refusal_correct != expected_refusal:
                raise BakeoffError("saved judge verdict is invalid or has a tampered refusal label")
        seen.add(qa_id)
        validated.append(dict(row))
    return {model: sorted(validated, key=lambda item: item["qa_id"])}


def judge_usage(grouped: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    rows = next(iter(grouped.values()))
    metadata = [row.get("judge_metadata") for row in rows]
    complete = all(
        isinstance(item, dict)
        and isinstance(item.get("input_tokens"), int)
        and isinstance(item.get("output_tokens"), int)
        and isinstance(item.get("cost_usd"), (int, float))
        for item in metadata
    )
    return {
        "rows": len(rows),
        "provider_calls": sum(
            int(item.get("provider_calls", 0)) for item in metadata if isinstance(item, dict)
        ),
        "input_tokens": sum(int(item["input_tokens"]) for item in metadata) if complete else None,
        "output_tokens": sum(int(item["output_tokens"]) for item in metadata) if complete else None,
        "cost_usd": math.fsum(float(item["cost_usd"]) for item in metadata) if complete else None,
        "status": "provider_reported_complete" if complete else "unknown_not_exposed_by_provider",
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qa", type=Path, default=ROOT / "data/qa.json")
    parser.add_argument("--generator-config", type=Path, default=ROOT / "artifacts/section5/generator_v2_4_config.json")
    parser.add_argument("--judge-config", type=Path, default=ROOT / "artifacts/section5/generator_v2_4_judge_config.json")
    parser.add_argument("--contexts", type=Path, default=ROOT / "data/rag_development_contexts.json")
    parser.add_argument("--model-catalog", type=Path, default=ROOT / "artifacts/section5/model_candidates_refresh.json")
    parser.add_argument("--generator-outputs", type=Path, default=ROOT / "data/rag_generator_v2_4_outputs.json")
    parser.add_argument("--generator-summary", type=Path, default=ROOT / "data/rag_generator_v2_4_summary.json")
    parser.add_argument("--outputs", type=Path, default=ROOT / "data/rag_generator_v2_4_judged_outputs.json")
    parser.add_argument("--result", type=Path, default=ROOT / "data/rag_generator_v2_4_judge_summary.json")
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
        generator_config = load_json(args.generator_config)
        judge_config = load_json(args.judge_config)
        context_packet = load_json(args.contexts)
        catalog = load_json(args.model_catalog)
        generator_outputs = load_json(args.generator_outputs)
        generator_summary = load_json(args.generator_summary)
        hashes = {
            "qa_sha256": hash_file(args.qa),
            "contexts_sha256": hash_file(args.contexts),
            "model_catalog_sha256": hash_file(args.model_catalog),
            "generator_config_sha256": hash_file(args.generator_config),
            "generator_outputs_sha256": hash_file(args.generator_outputs),
            "generator_summary_sha256": hash_file(args.generator_summary),
        }
        settings = validate_judge_config(
            judge_config,
            hashes=hashes,
            outputs_path=args.outputs,
            result_path=args.result,
            catalog=catalog,
        )
        validate_model_catalog(catalog, max_age_hours=24 if args.live or args.estimate_only else None)
        cases = validate_qa(qa)
        generation = validate_config(generator_config)
        candidates = generator_config.get("generator_candidates")
        if not isinstance(candidates, list) or len(candidates) != 1 or not isinstance(candidates[0], str):
            raise BakeoffError("judge-only pipeline requires exactly one frozen generator")
        model = candidates[0]
        contexts = contexts_from(
            context_packet,
            cases,
            qa_hash=hashes["qa_sha256"],
            config_hash=generator_config.get("retriever_config_sha256", hashes["generator_config_sha256"]),
        )
        source_grouped = offline_rows(
            generator_outputs,
            cases,
            contexts,
            hashes["generator_config_sha256"],
            hashes["contexts_sha256"],
            (model,),
        )
        validate_generator_gate(
            generator_summary,
            model=model,
            generator_config_hash=hashes["generator_config_sha256"],
            generator_outputs_hash=hashes["generator_outputs_sha256"],
            qa_hash=hashes["qa_sha256"],
            contexts_hash=hashes["contexts_sha256"],
        )
        estimate = estimate_judge_cost(
            cases,
            contexts,
            source_grouped,
            model=settings["model"],
            max_tokens=settings["max_tokens"],
            catalog=catalog,
        )
        if args.estimate_only:
            print(json.dumps(estimate, indent=2, sort_keys=True))
            return 0
        judge_config_hash = hash_file(args.judge_config)
        if args.live:
            print(
                validate_judge_cost_bound(
                    args.max_cost_usd,
                    estimate["estimated_max_cost_usd"],
                    settings["hard_cost_cap_usd"],
                )
            )
            if not args.confirm_cost:
                raise BakeoffError("--live requires --confirm-cost after reviewing the maximum-cost status")
            api_key = os.environ.get("OPENROUTER_API_KEY")
            if not api_key:
                raise BakeoffError("--live requires OPENROUTER_API_KEY; no provider call was made")
            grouped = run_live_judges(
                cases,
                contexts,
                source_grouped,
                judge=AnswerJudge(
                    api_key=api_key,
                    model=settings["model"],
                    max_tokens=settings["max_tokens"],
                    require_supported_parameters=settings["require_supported_parameters"],
                ),
                judge_config_hash=judge_config_hash,
                generator_outputs_hash=hashes["generator_outputs_sha256"],
            )
            write_json_atomic(
                args.outputs,
                {
                    "schema_version": 1,
                    "experiment": judge_config["experiment_id"],
                    "judge_config_sha256": judge_config_hash,
                    "generator_outputs_sha256": hashes["generator_outputs_sha256"],
                    "outputs": next(iter(grouped.values())),
                },
                overwrite=args.overwrite,
            )
        else:
            grouped = offline_judged_rows(
                load_json(args.outputs),
                source_grouped,
                contexts,
                judge_config_hash=judge_config_hash,
                generator_outputs_hash=hashes["generator_outputs_sha256"],
            )
        selection = select_winner(grouped, len(cases))
        result = {
            "schema_version": 1,
            "experiment": judge_config["experiment_id"],
            **hashes,
            "judge_config_sha256": judge_config_hash,
            "judged_outputs_sha256": hash_file(args.outputs),
            "live_calls": args.live,
            "approved_max_cost_usd": args.max_cost_usd if args.live else None,
            "cost_estimate": estimate,
            "actual_judge_usage": judge_usage(grouped),
            "selection": selection,
            "ready_for_owner_validation": selection.get("winner") == model,
            "holdout_status": "untouched",
        }
        write_json_atomic(args.result, result, overwrite=args.overwrite)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["ready_for_owner_validation"] else 1
    except (BakeoffError, OSError, TypeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

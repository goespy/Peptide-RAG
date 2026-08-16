#!/usr/bin/env python3
"""Freeze the accepted generator only after blind owner validation passes."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_rag_bakeoff import (  # noqa: E402
    BakeoffError,
    hash_file,
    load_json,
    validate_config,
    write_json_atomic,
)


class SelectionError(BakeoffError):
    """Raised when development evidence cannot support a holdout selection."""


def _candidate(summary: dict[str, Any], winner: str) -> dict[str, Any]:
    selection = summary.get("selection")
    candidates = selection.get("candidates") if isinstance(selection, dict) else None
    candidate = candidates.get(winner) if isinstance(candidates, dict) else None
    if (
        not isinstance(selection, dict)
        or selection.get("winner") != winner
        or not isinstance(candidate, dict)
    ):
        raise SelectionError("judge summary does not select the frozen generator")
    return candidate


def build_selection(
    *,
    qa_hash: str,
    retriever_config_hash: str,
    generator_config_hash: str,
    generator_outputs_hash: str,
    generator_summary_hash: str,
    judge_config_hash: str,
    judge_outputs_hash: str,
    judge_summary_hash: str,
    worksheet_hash: str,
    report_hash: str,
    generator_config: dict[str, Any],
    generator_summary: dict[str, Any],
    judge_config: dict[str, Any],
    judge_summary: dict[str, Any],
    owner_report: dict[str, Any],
) -> dict[str, Any]:
    generation = validate_config(generator_config)
    candidates = generator_config.get("generator_candidates")
    if not isinstance(candidates, list) or len(candidates) != 1 or not isinstance(candidates[0], str):
        raise SelectionError("accepted holdout selection requires one frozen generator")
    winner = candidates[0]
    diagnostic = generator_summary.get("diagnostic")
    generator_candidates = diagnostic.get("candidates") if isinstance(diagnostic, dict) else None
    generator_candidate = (
        generator_candidates.get(winner)
        if isinstance(generator_candidates, dict)
        else None
    )
    if (
        not isinstance(generator_candidate, dict)
        or generator_candidate.get("ready_for_paid_judging") is not True
        or generator_candidate.get("answerable_answer_count") != 10
        or generator_candidate.get("unanswerable_correct_system_refusal_count") != 3
        or generator_candidate.get("structurally_valid_count") != 13
    ):
        raise SelectionError("generator did not pass the frozen 10/3/13 development gate")
    if (
        generator_config.get("qa_sha256") != qa_hash
        or generator_config.get("retriever_config_sha256") != retriever_config_hash
        or generator_config.get("holdout_status") != "untouched"
    ):
        raise SelectionError("generator configuration is not bound to untouched frozen inputs")
    generator_catalog_hash = generator_config.get("model_catalog_sha256")
    expected_generator_summary_bindings = {
        "config_sha256": generator_config_hash,
        "outputs_sha256": generator_outputs_hash,
        "qa_sha256": qa_hash,
        "contexts_sha256": generator_config.get("contexts_sha256"),
        "model_catalog_sha256": generator_catalog_hash,
    }
    if (
        any(
            generator_summary.get(field) != value
            for field, value in expected_generator_summary_bindings.items()
        )
        or generator_summary.get("live_calls") is not True
    ):
        raise SelectionError("generator summary is not bound to the frozen live evidence")
    expected_judge_bindings = {
        "qa_sha256": qa_hash,
        "generator_config_sha256": generator_config_hash,
        "generator_outputs_sha256": generator_outputs_hash,
        "generator_summary_sha256": generator_summary_hash,
    }
    if (
        any(judge_config.get(field) != value for field, value in expected_judge_bindings.items())
        or judge_config.get("model_catalog_sha256") != generator_catalog_hash
        or judge_config.get("contexts_sha256") != generator_config.get("contexts_sha256")
    ):
        raise SelectionError("judge configuration is not bound to the accepted generator evidence")
    if judge_config.get("holdout_status") != "untouched" or judge_config.get("judge_calls") != 13:
        raise SelectionError("judge configuration does not preserve the development/holdout boundary")
    judge_settings = judge_config.get("judge")
    if (
        not isinstance(judge_settings, dict)
        or not isinstance(judge_settings.get("model"), str)
        or judge_settings.get("prompt_version") != 2
    ):
        raise SelectionError("accepted selection requires the frozen different-family judge-v2")
    judged_candidate = _candidate(judge_summary, winner)
    if (
        judge_summary.get("judged_outputs_sha256") != judge_outputs_hash
        or judge_summary.get("judge_config_sha256") != judge_config_hash
        or judge_summary.get("generator_config_sha256") != generator_config_hash
        or judge_summary.get("generator_outputs_sha256") != generator_outputs_hash
        or judge_summary.get("generator_summary_sha256") != generator_summary_hash
        or judge_summary.get("qa_sha256") != qa_hash
        or judge_summary.get("contexts_sha256") != generator_config.get("contexts_sha256")
        or judge_summary.get("model_catalog_sha256") != generator_catalog_hash
        or judge_summary.get("live_calls") is not True
        or judge_summary.get("holdout_status") != "untouched"
        or judge_summary.get("ready_for_owner_validation") is not True
        or judged_candidate.get("denominators", {}).get("answerable") != 10
        or judged_candidate.get("denominators", {}).get("unanswerable") != 3
        or judged_candidate.get("structural_validity") != 1.0
    ):
        raise SelectionError("judge evidence is incomplete or not bound to the frozen outputs")
    dimensions = owner_report.get("dimensions")
    if (
        owner_report.get("passes") is not True
        or owner_report.get("n") != 10
        or owner_report.get("worksheet_sha256") != worksheet_hash
        or owner_report.get("source_outputs_sha256") != judge_outputs_hash
        or not isinstance(dimensions, dict)
        or set(dimensions) != {"faithful", "relevant", "citations_correct", "refusal_correct"}
        or any(not isinstance(value, dict) or value.get("passes") is not True for value in dimensions.values())
    ):
        raise SelectionError("blind owner-versus-judge validation has not passed")

    return {
        "schema_version": 1,
        "status": "accepted_for_holdout",
        "holdout_status": "untouched",
        "winner": winner,
        "judge_model": judge_settings["model"],
        "judge_prompt_version": 2,
        "qa_sha256": qa_hash,
        "retriever_config_sha256": retriever_config_hash,
        "generator_config_sha256": generator_config_hash,
        "generator_outputs_sha256": generator_outputs_hash,
        "generator_summary_sha256": generator_summary_hash,
        "judge_config_sha256": judge_config_hash,
        "judge_outputs_sha256": judge_outputs_hash,
        "judge_summary_sha256": judge_summary_hash,
        "owner_worksheet_sha256": worksheet_hash,
        "owner_validation_report_sha256": report_hash,
        "model_catalog_sha256": generator_catalog_hash,
        "generator_prompt_sha256": generator_config.get("prompt_sha256"),
        "generation": generation,
        "development_metrics": judged_candidate,
        "holdout_cost_caps": {
            "context_embedding_usd": 0.01,
            "generation_and_judging_usd": 0.50,
        },
        "selection_reason": "10/3/13 generator gate, complete judge-v2 evidence, and passing blind owner agreement",
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qa", type=Path, default=ROOT / "data/qa.json")
    parser.add_argument("--retriever-config", type=Path, default=ROOT / "artifacts/section5/frozen_config.json")
    parser.add_argument("--generator-config", type=Path, default=ROOT / "artifacts/section5/generator_v2_5_config.json")
    parser.add_argument("--generator-outputs", type=Path, default=ROOT / "data/rag_generator_v2_5_outputs.json")
    parser.add_argument("--generator-summary", type=Path, default=ROOT / "data/rag_generator_v2_5_summary.json")
    parser.add_argument("--judge-config", type=Path, default=ROOT / "artifacts/section5/generator_v2_5_judge_config.json")
    parser.add_argument("--judge-outputs", type=Path, default=ROOT / "data/rag_generator_v2_5_judged_outputs.json")
    parser.add_argument("--judge-summary", type=Path, default=ROOT / "data/rag_generator_v2_5_judge_summary.json")
    parser.add_argument("--worksheet", type=Path, default=ROOT / "data/judge_validation_v2_5_worksheet.json")
    parser.add_argument("--owner-report", type=Path, default=ROOT / "data/judge_validation_v2_5_report.json")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/section5/accepted_generator_v2_5.json")
    args = parser.parse_args(argv)
    try:
        packet = build_selection(
            qa_hash=hash_file(args.qa),
            retriever_config_hash=hash_file(args.retriever_config),
            generator_config_hash=hash_file(args.generator_config),
            generator_outputs_hash=hash_file(args.generator_outputs),
            generator_summary_hash=hash_file(args.generator_summary),
            judge_config_hash=hash_file(args.judge_config),
            judge_outputs_hash=hash_file(args.judge_outputs),
            judge_summary_hash=hash_file(args.judge_summary),
            worksheet_hash=hash_file(args.worksheet),
            report_hash=hash_file(args.owner_report),
            generator_config=load_json(args.generator_config),
            generator_summary=load_json(args.generator_summary),
            judge_config=load_json(args.judge_config),
            judge_summary=load_json(args.judge_summary),
            owner_report=load_json(args.owner_report),
        )
        write_json_atomic(args.output, packet, overwrite=False)
    except (BakeoffError, OSError, TypeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(packet, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

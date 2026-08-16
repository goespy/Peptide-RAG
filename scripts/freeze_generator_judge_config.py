#!/usr/bin/env python3
"""Freeze the judge-only config after an accepted generator development run."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_generator_judge import (  # noqa: E402
    estimate_judge_cost,
    validate_generator_gate,
)
from scripts.run_rag_bakeoff import (  # noqa: E402
    BakeoffError,
    contexts_from,
    hash_file,
    load_json,
    offline_rows,
    validate_config,
    validate_judge_catalog,
    validate_model_catalog,
    validate_qa,
    write_json_atomic,
)


def _relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError as exc:
        raise BakeoffError("judge artifacts must remain inside the repository") from exc


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qa", type=Path, default=ROOT / "data/qa.json")
    parser.add_argument("--generator-config", type=Path, default=ROOT / "artifacts/section5/generator_v2_5_config.json")
    parser.add_argument("--contexts", type=Path, default=ROOT / "data/rag_development_contexts.json")
    parser.add_argument("--model-catalog", type=Path, default=ROOT / "artifacts/section5/model_candidates_judge_refresh.json")
    parser.add_argument("--generator-outputs", type=Path, default=ROOT / "data/rag_generator_v2_5_outputs.json")
    parser.add_argument("--generator-summary", type=Path, default=ROOT / "data/rag_generator_v2_5_summary.json")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/section5/generator_v2_5_judge_config.json")
    parser.add_argument("--judged-outputs", type=Path, default=ROOT / "data/rag_generator_v2_5_judged_outputs.json")
    parser.add_argument("--judge-summary", type=Path, default=ROOT / "data/rag_generator_v2_5_judge_summary.json")
    parser.add_argument("--experiment-id", default="generator-v2.5-claude-judge-v2")
    parser.add_argument("--prompt-version", type=int, choices=(1, 2), default=2)
    parser.add_argument("--hard-cost-cap-usd", type=float, required=True)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    try:
        if (
            isinstance(args.hard_cost_cap_usd, bool)
            or not math.isfinite(args.hard_cost_cap_usd)
            or args.hard_cost_cap_usd <= 0
        ):
            raise BakeoffError("--hard-cost-cap-usd must be a positive finite value")
        qa = load_json(args.qa)
        generator_config = load_json(args.generator_config)
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
        validate_model_catalog(catalog)
        judge_model = validate_judge_catalog(catalog)
        cases = validate_qa(qa)
        validate_config(generator_config)
        candidates = generator_config.get("generator_candidates")
        if not isinstance(candidates, list) or len(candidates) != 1 or not isinstance(candidates[0], str):
            raise BakeoffError("judge config requires exactly one accepted generator")
        generator_model = candidates[0]
        contexts = contexts_from(
            context_packet,
            cases,
            qa_hash=hashes["qa_sha256"],
            config_hash=generator_config.get("retriever_config_sha256", hashes["generator_config_sha256"]),
        )
        grouped = offline_rows(
            generator_outputs,
            cases,
            contexts,
            hashes["generator_config_sha256"],
            hashes["contexts_sha256"],
            (generator_model,),
        )
        validate_generator_gate(
            generator_summary,
            model=generator_model,
            generator_config_hash=hashes["generator_config_sha256"],
            generator_outputs_hash=hashes["generator_outputs_sha256"],
            qa_hash=hashes["qa_sha256"],
            contexts_hash=hashes["contexts_sha256"],
        )
        estimate = estimate_judge_cost(
            cases,
            contexts,
            grouped,
            model=judge_model,
            max_tokens=600,
            prompt_version=args.prompt_version,
            catalog=catalog,
        )
        if estimate["estimated_max_cost_usd"] > args.hard_cost_cap_usd:
            raise BakeoffError("judge estimate exceeds the proposed hard cost cap")
        packet = {
            "schema_version": 2 if args.prompt_version == 2 else 1,
            "experiment_id": args.experiment_id,
            "status": "frozen_before_paid_judging",
            "selected": True,
            **hashes,
            "generator_model": generator_model,
            "generator_calls": 0,
            "judge_calls": 13,
            "holdout_status": "untouched",
            "judge": {
                "model": judge_model,
                "temperature": 0,
                "max_tokens": 600,
                "require_supported_parameters": True,
                "prompt_version": args.prompt_version,
                "hard_cost_cap_usd": args.hard_cost_cap_usd,
            },
            "cost_estimate": estimate,
            "artifact_paths": {
                "outputs": _relative(args.judged_outputs),
                "summary": _relative(args.judge_summary),
            },
        }
        write_json_atomic(args.output, packet, overwrite=args.overwrite)
        print(json.dumps(packet, indent=2, sort_keys=True))
        return 0
    except (BakeoffError, OSError, TypeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Generate the deterministic monthly AI-cost projection from frozen evidence."""

from __future__ import annotations

import argparse
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
GENERATOR_MODEL = "openai/gpt-oss-20b"
EMBEDDING_MODEL = "openai/text-embedding-3-small"
USER_SCALES = (100, 1_000, 10_000, 100_000)
RAILWAY_HOBBY_MINIMUM = Decimal("5.00")
RAILWAY_SOURCE = "https://docs.railway.com/pricing/plans"


class CostProjectionError(ValueError):
    """Raised when frozen pricing or usage evidence cannot support a projection."""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def load_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CostProjectionError(f"cannot read {path}") from exc
    if not isinstance(value, dict):
        raise CostProjectionError(f"{path} must contain a JSON object")
    return value


def money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def build_projection(
    catalog: dict[str, Any],
    embedding_ledger: dict[str, Any],
    query_usage: dict[str, Any],
    *,
    input_hashes: dict[str, str],
) -> dict[str, Any]:
    models = catalog.get("models")
    if not isinstance(models, list):
        raise CostProjectionError("model catalog has no model list")
    matches = [item for item in models if isinstance(item, dict) and item.get("id") == GENERATOR_MODEL]
    if len(matches) != 1:
        raise CostProjectionError("frozen generator pricing is missing or ambiguous")
    generator = matches[0]
    try:
        input_price = Decimal(str(generator["input_cost_per_million"]))
        output_price = Decimal(str(generator["output_cost_per_million"]))
        pricing = embedding_ledger["pricing"]
        embedding_price = Decimal(str(pricing["input_usd_per_million_tokens"]))
        usage = query_usage["provider_usage"]
        query_tokens = int(usage["input_tokens"])
        question_count = int(query_usage["question_count"])
    except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
        raise CostProjectionError("pricing or query-token evidence is malformed") from exc
    if (
        input_price < 0
        or output_price < 0
        or embedding_price < 0
        or query_tokens <= 0
        or question_count <= 0
        or query_usage.get("model") != EMBEDDING_MODEL
        or embedding_ledger.get("model") != EMBEDDING_MODEL
        or not isinstance(catalog.get("checked_at"), str)
        or len(catalog["checked_at"]) < 10
        or pricing.get("source") != "https://openrouter.ai/openai/text-embedding-3-small/api"
        or set(input_hashes) != {"model_catalog_sha256", "embedding_ledger_sha256", "query_usage_sha256"}
        or any(not isinstance(value, str) or len(value) != 64 for value in input_hashes.values())
    ):
        raise CostProjectionError("frozen pricing inputs do not satisfy the projection contract")

    sessions_per_user = 2
    questions_per_session = 10
    calls_per_user = sessions_per_user * questions_per_session
    generation_input_per_call = 4_000
    generation_output_per_call = 300
    per_call = (
        Decimal(generation_input_per_call) * input_price
        + Decimal(generation_output_per_call) * output_price
        + (Decimal(query_tokens) / Decimal(question_count)) * embedding_price
    ) / Decimal(1_000_000)
    per_user = Decimal(calls_per_user) * per_call
    rows = []
    for users in USER_SCALES:
        variable = Decimal(users) * per_user
        combined = variable + RAILWAY_HOBBY_MINIMUM
        rows.append({
            "users": users,
            "qa_calls_per_month": users * calls_per_user,
            "generation_input_tokens": users * calls_per_user * generation_input_per_call,
            "generation_output_tokens": users * calls_per_user * generation_output_per_call,
            "variable_ai_cost_usd_exact": format(variable, "f"),
            "variable_ai_cost_usd_rounded": money(variable),
            "railway_baseline_usd": money(RAILWAY_HOBBY_MINIMUM),
            "combined_lower_bound_usd": money(combined),
        })
    return {
        "schema_version": 1,
        "report_date": catalog["checked_at"][:10],
        "input_hashes": dict(sorted(input_hashes.items())),
        "workload": {
            "sessions_per_user_per_month": sessions_per_user,
            "generated_questions_per_session": questions_per_session,
            "qa_calls_per_user_per_month": calls_per_user,
            "generation_input_tokens_per_call": generation_input_per_call,
            "generation_output_tokens_per_call": generation_output_per_call,
            "query_embedding_tokens_numerator": query_tokens,
            "query_embedding_tokens_denominator": question_count,
        },
        "prices_usd_per_million_tokens": {
            "generator_model": GENERATOR_MODEL,
            "generator_input": format(input_price, "f"),
            "generator_output": format(output_price, "f"),
            "embedding_model": EMBEDDING_MODEL,
            "embedding_input": format(embedding_price, "f"),
        },
        "railway": {
            "plan": "Hobby",
            "monthly_minimum_usd": money(RAILWAY_HOBBY_MINIMUM),
            "source": RAILWAY_SOURCE,
            "actual_resource_usage": "unknown/not exposed until deployment",
        },
        "variable_ai_cost_per_user_usd_exact": format(per_user, "f"),
        "scenarios": rows,
        "limitations": [
            "Railway CPU, memory, egress, and sleeping behavior are not projected.",
            "Provider prices must be refreshed for a future report date.",
            "10,000 and 100,000-user scenarios require load testing and distributed limits.",
        ],
    }


def projection_from_paths(catalog_path: Path, ledger_path: Path, query_usage_path: Path) -> dict[str, Any]:
    return build_projection(
        load_object(catalog_path),
        load_object(ledger_path),
        load_object(query_usage_path),
        input_hashes={
            "model_catalog_sha256": sha256(catalog_path),
            "embedding_ledger_sha256": sha256(ledger_path),
            "query_usage_sha256": sha256(query_usage_path),
        },
    )


def write_atomic(path: Path, payload: dict[str, Any], *, overwrite: bool) -> None:
    path = Path(path)
    if path.exists() and not overwrite:
        raise CostProjectionError(f"refusing to overwrite existing file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=ROOT / "artifacts/section5/model_candidates_judge_refresh.json")
    parser.add_argument("--embedding-ledger", type=Path, default=ROOT / "artifacts/section5/embedding_usage.json")
    parser.add_argument("--query-usage", type=Path, default=ROOT / "artifacts/section5/query_embeddings.npz.usage.json")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/section6/cost_projection.json")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.output.exists() and not args.overwrite:
            raise CostProjectionError(f"refusing to overwrite existing file: {args.output}")
        projection = projection_from_paths(args.catalog, args.embedding_ledger, args.query_usage)
        write_atomic(args.output, projection, overwrite=args.overwrite)
    except (CostProjectionError, OSError, TypeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(projection, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

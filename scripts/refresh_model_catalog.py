#!/usr/bin/env python3
"""Refresh the versioned OpenRouter model catalog from public API metadata."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, Sequence

import requests


ROOT = Path(__file__).resolve().parents[1]
MODELS = (
    ("qwen", "qwen/qwen3.7-flash"),
    ("openai", "openai/gpt-oss-20b"),
    ("google", "google/gemma-3-12b-it"),
)
JUDGE = ("anthropic", "anthropic/claude-sonnet-4.6")
MODELS_URL = "https://openrouter.ai/api/v1/models"
MAX_FALLBACK_INPUT_PER_MILLION = 0.10
MAX_FALLBACK_OUTPUT_PER_MILLION = 0.50


class ModelCatalogError(RuntimeError):
    pass


def _price_per_million(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ModelCatalogError("model pricing must be numeric")
    try:
        price = float(value) * 1_000_000
    except ValueError as exc:
        raise ModelCatalogError("model pricing must be numeric") from exc
    if price < 0:
        raise ModelCatalogError("model pricing cannot be negative")
    return round(price, 12)


def catalog_entry(raw: dict[str, Any], *, family: str) -> dict[str, Any]:
    parameters = raw.get("supported_parameters")
    pricing = raw.get("pricing")
    context_length = raw.get("context_length")
    if (
        not isinstance(raw.get("id"), str)
        or not isinstance(parameters, list)
        or any(not isinstance(value, str) for value in parameters)
        or "response_format" not in parameters
        or "structured_outputs" not in parameters
        or isinstance(context_length, bool)
        or not isinstance(context_length, int)
        or context_length < 32_768
        or not isinstance(pricing, dict)
    ):
        raise ModelCatalogError(
            f"{raw.get('id')} does not currently meet the structured-output/context contract"
        )
    return {
        "available": True,
        "context_length": context_length,
        "family": family,
        "id": raw["id"],
        "input_cost_per_million": _price_per_million(pricing.get("prompt")),
        "output_cost_per_million": _price_per_million(pricing.get("completion")),
        "structured_json": True,
        "supported_parameters": sorted(parameters),
    }


def choose_family_candidate(
    by_id: dict[str, dict[str, Any]], *, family: str, preferred_id: str
) -> dict[str, Any]:
    """Keep the preferred model when compatible, else choose the cheapest valid family peer."""

    preferred = by_id.get(preferred_id)
    if preferred is not None:
        try:
            return catalog_entry(preferred, family=family)
        except ModelCatalogError:
            pass
    alternatives: list[dict[str, Any]] = []
    for model_id, raw in by_id.items():
        if not model_id.startswith(f"{family}/"):
            continue
        try:
            candidate = catalog_entry(raw, family=family)
        except ModelCatalogError:
            continue
        if (
            candidate["input_cost_per_million"] <= MAX_FALLBACK_INPUT_PER_MILLION
            and candidate["output_cost_per_million"] <= MAX_FALLBACK_OUTPUT_PER_MILLION
        ):
            alternatives.append(candidate)
    if not alternatives:
        raise ModelCatalogError(
            f"{preferred_id} is incompatible and no same-family structured-output replacement meets the price/context contract"
        )
    chosen = min(
        alternatives,
        key=lambda item: (
            float(item["input_cost_per_million"]) + float(item["output_cost_per_million"]),
            float(item["output_cost_per_million"]),
            float(item["input_cost_per_million"]),
            str(item["id"]),
        ),
    )
    chosen = dict(chosen)
    chosen["replacement_for"] = preferred_id
    chosen["replacement_rule"] = (
        "lowest combined input/output price in the same provider family with strict structured outputs, "
        ">=32K context, input <=$0.10/M, and output <=$0.50/M"
    )
    return chosen


def fetch_catalog(session: requests.Session, *, timeout: float = 30.0) -> dict[str, Any]:
    response = session.get(MODELS_URL, timeout=timeout)
    response.raise_for_status()
    try:
        payload = response.json()
    except (ValueError, json.JSONDecodeError) as exc:
        raise ModelCatalogError("OpenRouter model catalog was not valid JSON") from exc
    values = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(values, list):
        raise ModelCatalogError("OpenRouter model catalog needs a data list")
    by_id = {
        value.get("id"): value
        for value in values
        if isinstance(value, dict) and isinstance(value.get("id"), str)
    }
    models = [
        choose_family_candidate(by_id, family=family, preferred_id=model)
        for family, model in MODELS
    ]
    if JUDGE[1] not in by_id:
        raise ModelCatalogError(f"required judge model is unavailable: {JUDGE[1]}")
    judge = catalog_entry(by_id[JUDGE[1]], family=JUDGE[0])
    return {
        "checked_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "judge": judge,
        "models": models,
        "schema_version": 2,
        "sources": [
            MODELS_URL,
            "https://openrouter.ai/docs/guides/features/structured-outputs",
            "https://openrouter.ai/docs/guides/routing/provider-selection",
        ],
    }


def write_atomic(path: Path, payload: dict[str, Any], *, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise ModelCatalogError(f"refusing to overwrite {path}; pass --overwrite")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", text=True
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "data/model_candidates.json")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    try:
        packet = fetch_catalog(requests.Session())
        write_atomic(args.output, packet, overwrite=args.overwrite)
    except (ModelCatalogError, requests.RequestException, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"checked_at": packet["checked_at"], "models": [row["id"] for row in packet["models"]], "judge": packet["judge"]["id"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

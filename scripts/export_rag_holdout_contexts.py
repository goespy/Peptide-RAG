#!/usr/bin/env python3
"""Freeze seven holdout retrieval contexts after all development gates pass."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import sys
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.embed_chunks import load_chunk_artifact
from scripts.evaluate_chunks import _cache_for
from scripts.run_rag_bakeoff import (
    BakeoffError,
    hash_file,
    load_json,
    validate_config,
    validate_live_cost,
    write_json_atomic,
)
from scripts.run_rag_holdout import holdout_cases, winner_from
from src.analysis import ANALYSIS_CONFIGS
from src.bm25 import BM25Config
from src.embeddings import EmbeddingClient
from src.retrieval import Retriever


class HoldoutContextError(BakeoffError):
    pass


def validate_development_gates(
    qa: dict[str, Any],
    config: dict[str, Any],
    bakeoff: dict[str, Any],
    judge_report: dict[str, Any],
    *,
    qa_hash: str,
    config_hash: str,
) -> str:
    holdout_cases(qa)
    validate_config(config)
    winner = winner_from(bakeoff)
    if bakeoff.get("qa_sha256") != qa_hash or bakeoff.get("config_sha256") != config_hash:
        raise HoldoutContextError("bake-off is not bound to the approved QA and frozen RAG configuration")
    if judge_report.get("passes") is not True:
        raise HoldoutContextError("a passing owner-versus-judge validation is required")
    if judge_report.get("source_outputs_sha256") != bakeoff.get("outputs_sha256"):
        raise HoldoutContextError("judge validation is not bound to the selected bake-off outputs")
    return winner


def build_context_packet(
    cases: Sequence[dict[str, Any]],
    retriever: Retriever,
    *,
    qa_hash: str,
    config_hash: str,
    embedding_usage: dict[str, object] | None = None,
) -> dict[str, Any]:
    contexts: list[dict[str, Any]] = []
    for case in cases:
        retrieved = retriever.retrieve(str(case["question"]), k=5, mode="hybrid")
        if not retrieved:
            raise HoldoutContextError(f"{case['id']} produced no holdout context")
        contexts.append({
            "qa_id": case["id"],
            "chunks": [
                {
                    **asdict(item.chunk),
                    "score": item.score,
                    "lexical_rank": item.lexical_rank,
                    "semantic_rank": item.semantic_rank,
                }
                for item in retrieved
            ],
        })
    return {
        "schema_version": 1,
        "qa_sha256": qa_hash,
        "retriever_config_sha256": config_hash,
        "selection_scope": "seven frozen holdout questions after generator and judge-development gates",
        "embedding_usage": embedding_usage,
        "contexts": contexts,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qa", type=Path, default=ROOT / "data/qa.json")
    parser.add_argument("--config", type=Path, default=ROOT / "artifacts/section5/frozen_config.json")
    parser.add_argument("--bakeoff", type=Path, default=ROOT / "data/rag_bakeoff_summary.json")
    parser.add_argument("--judge-validation", type=Path, default=ROOT / "data/judge_validation_report.json")
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "data/rag_holdout_contexts.json")
    parser.add_argument("--max-cost-usd", type=float, required=True)
    parser.add_argument("--confirm-cost", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.output.exists() and not args.overwrite:
            raise HoldoutContextError(f"refusing to overwrite existing file: {args.output}; pass --overwrite")
        print(validate_live_cost(args.max_cost_usd))
        if not args.confirm_cost:
            raise HoldoutContextError("holdout context export requires --confirm-cost")
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise HoldoutContextError("OPENROUTER_API_KEY is required; no provider call was made")

        qa, config = load_json(args.qa), load_json(args.config)
        bakeoff, judge_report = load_json(args.bakeoff), load_json(args.judge_validation)
        qa_hash, config_hash = hash_file(args.qa), hash_file(args.config)
        validate_development_gates(qa, config, bakeoff, judge_report, qa_hash=qa_hash, config_hash=config_hash)
        cases = holdout_cases(qa)

        chunk_config = config.get("chunk_config")
        if not isinstance(chunk_config, dict):
            raise HoldoutContextError("frozen RAG config has no selected chunk configuration")
        chunks_path = args.config.parent / f"chunks_{chunk_config.get('words')}_{chunk_config.get('overlap')}.jsonl"
        chunks, manifest = load_chunk_artifact(chunks_path, chunks_path.with_suffix(chunks_path.suffix + ".manifest.json"))
        vectors, cache_model = _cache_for(chunks, manifest, args.cache)
        if cache_model != config.get("embedding_model"):
            raise HoldoutContextError("embedding cache model differs from the frozen selection")

        lexical_path = ROOT / "data/lexical_config.json"
        lexical = load_json(lexical_path)
        if hash_file(lexical_path) != config.get("lexical_config_sha256"):
            raise HoldoutContextError("frozen RAG selection is not bound to the lexical configuration")
        bm25 = BM25Config(
            k1=float(lexical["bm25"]["k1"]),
            b=float(lexical["bm25"]["b"]),
            proximity_boost=float(lexical["bm25"].get("proximity_boost", 0.0)),
        )
        analysis = ANALYSIS_CONFIGS[lexical["analysis"]["name"]]
        client = EmbeddingClient(api_key=api_key, model=cache_model)
        retriever = Retriever(chunks, vectors, embedding_client=client, alpha=float(config["rrf_alpha"]), bm25_config=bm25, analysis_config=analysis)
        packet = build_context_packet(cases, retriever, qa_hash=qa_hash, config_hash=config_hash)
        packet["embedding_usage"] = client.total_metadata
        write_json_atomic(args.output, packet, overwrite=args.overwrite)
    except (BakeoffError, OSError, KeyError, TypeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote seven holdout contexts to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

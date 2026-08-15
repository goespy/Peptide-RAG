#!/usr/bin/env python3
"""Record exact gold-chunk ranks for the frozen development retrieval state."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.embed_chunks import load_chunk_artifact  # noqa: E402
from scripts.evaluate_chunks import (  # noqa: E402
    _cache_for,
    development_answerable,
    load_approved_qa,
    query_embeddings,
    relevant_chunk_ids,
)
from src.analysis import ANALYSIS_CONFIGS  # noqa: E402
from src.bm25 import BM25Config  # noqa: E402
from src.retrieval import Retriever  # noqa: E402


class RetrievalDiagnosticError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def rank_case(case: dict[str, Any], retriever: Retriever) -> dict[str, Any]:
    """Return complete exact-gold ranks and the production top-five context."""

    gold = relevant_chunk_ids(case, retriever.chunks)
    if not gold:
        raise RetrievalDiagnosticError(f"{case.get('id')} has no fully containing gold chunk")
    rankings = {
        "lexical": retriever.retrieve(str(case["question"]), k=len(retriever.chunks), mode="lexical"),
        "semantic": retriever.retrieve(str(case["question"]), k=len(retriever.chunks), mode="semantic"),
        # Production hybrid fusion considers the top 50 from each source, so
        # its result set contains at most 100 distinct candidates.
        "hybrid": retriever.retrieve(str(case["question"]), k=100, mode="hybrid"),
    }
    modes: dict[str, Any] = {}
    for mode, values in rankings.items():
        positions = {item.chunk_id: rank for rank, item in enumerate(values, start=1)}
        gold_ranks = {chunk_id: positions.get(chunk_id) for chunk_id in sorted(gold)}
        present = [rank for rank in gold_ranks.values() if rank is not None]
        modes[mode] = {
            "best_gold_rank": min(present) if present else None,
            "gold_chunk_ranks": gold_ranks,
            "gold_hit_at_5": any(rank <= 5 for rank in present),
            "gold_in_measured_rank_window": bool(present),
            "measured_rank_window": len(values),
        }
        if mode == "hybrid":
            modes[mode]["rrf_source_candidate_limit"] = 50
            modes[mode]["maximum_rrf_union_size"] = 100
    top_five = [
        {
            "rank": rank,
            "chunk_id": item.chunk_id,
            "pmid": item.pmid,
            "title": item.title,
            "lexical_rank": item.lexical_rank,
            "semantic_rank": item.semantic_rank,
            "is_exact_gold_chunk": item.chunk_id in gold,
        }
        for rank, item in enumerate(rankings["hybrid"][:5], start=1)
    ]
    return {
        "qa_id": case["id"],
        "question": case["question"],
        "relevant_pmids": list(case["relevant_pmids"]),
        "gold_chunk_ids": sorted(gold),
        "modes": modes,
        "production_hybrid_top_five": top_five,
        "non_gold_top_five_require_human_relevance_review": [
            item["chunk_id"] for item in top_five if not item["is_exact_gold_chunk"]
        ],
    }


def _atomic(path: Path, payload: dict[str, Any], *, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise RetrievalDiagnosticError(f"refusing to overwrite {path}; pass --overwrite")
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
    parser.add_argument("--qa", type=Path, default=ROOT / "data/qa.json")
    parser.add_argument("--corpus", type=Path, default=ROOT / "data/corpus.jsonl")
    parser.add_argument("--chunks", type=Path, default=ROOT / "artifacts/section5/chunks_256_64.jsonl")
    parser.add_argument("--manifest", type=Path, default=ROOT / "artifacts/section5/chunks_256_64.jsonl.manifest.json")
    parser.add_argument("--cache", type=Path, default=ROOT / "artifacts/section5/embeddings_256_64.npz")
    parser.add_argument("--query-cache", type=Path, default=ROOT / "artifacts/section5/query_embeddings.npz")
    parser.add_argument("--lexical-config", type=Path, default=ROOT / "data/lexical_config.json")
    parser.add_argument("--frozen-config", type=Path, default=ROOT / "artifacts/section5/frozen_config.json")
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/section5/retrieval_diagnostics.json")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    try:
        qa = load_approved_qa(args.qa, args.corpus)
        frozen = json.loads(args.frozen_config.read_text(encoding="utf-8"))
        lexical = json.loads(args.lexical_config.read_text(encoding="utf-8"))
        chunks, manifest = load_chunk_artifact(args.chunks, args.manifest)
        if frozen.get("chunk_candidate") != "256_64" or manifest.get("config") != frozen.get("chunk_config"):
            raise RetrievalDiagnosticError("chunk artifact does not match the frozen selected configuration")
        corpus_hash = sha256(args.corpus)
        if manifest.get("corpus_sha256") != corpus_hash or frozen.get("corpus_sha256") != corpus_hash:
            raise RetrievalDiagnosticError("corpus hash does not match frozen retrieval artifacts")
        vectors, model = _cache_for(chunks, manifest, args.cache, str(frozen.get("embedding_model", "")))
        if model != frozen.get("embedding_model"):
            raise RetrievalDiagnosticError("embedding model does not match the frozen configuration")
        qa_hash = sha256(args.qa)
        questions, _usage = query_embeddings(
            qa,
            cache_path=args.query_cache,
            model=model,
            corpus_hash=corpus_hash,
            qa_hash=qa_hash,
        )
        analysis = ANALYSIS_CONFIGS[str(lexical["analysis"]["name"])]
        bm25 = BM25Config(
            k1=float(lexical["bm25"]["k1"]),
            b=float(lexical["bm25"]["b"]),
            proximity_boost=float(lexical["bm25"].get("proximity_boost", 0.0)),
        )
        retriever = Retriever(
            chunks,
            vectors,
            query_embedding=lambda query: questions[query],
            alpha=float(frozen["rrf_alpha"]),
            bm25_config=bm25,
            analysis_config=analysis,
        )
        cases = [rank_case(case, retriever) for case in development_answerable(qa)]
        packet = {
            "schema_version": 1,
            "measurement_scope": "approved answerable development QA only",
            "corpus_sha256": corpus_hash,
            "qa_sha256": qa_hash,
            "frozen_config_sha256": sha256(args.frozen_config),
            "chunks_sha256": sha256(args.chunks),
            "embedding_cache_sha256": sha256(args.cache),
            "query_cache_sha256": sha256(args.query_cache),
            "cases": cases,
            "summary": {
                mode: {
                    "exact_gold_hit_at_5_count": sum(case["modes"][mode]["gold_hit_at_5"] for case in cases),
                    "case_count": len(cases),
                }
                for mode in ("lexical", "semantic", "hybrid")
            },
            "interpretation_rule": (
                "An exact-gold miss is not automatically a chunking failure or a topical retrieval failure; "
                "non-gold retrieved evidence requires independent human relevance review. Hybrid absence means "
                "absence from the explicitly recorded weighted-RRF candidate window, not absence from the corpus."
            ),
        }
        _atomic(args.output, packet, overwrite=args.overwrite)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError, RetrievalDiagnosticError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(packet["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

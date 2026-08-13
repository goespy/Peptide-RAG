#!/usr/bin/env python3
"""Run the project release checks without network access by default.

This command is deliberately read-only: it validates the checked-in evidence,
recomputes the lexical evaluation in memory, and reports RAG gates as TBD when
their paid/offline inputs have not been committed yet.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from run_day1 import Day1Error, load_qrels, sha256, validate_corpus_binding
from src.bm25 import BM25Config, rank_bm25
from src.boolean import search_boolean
from src.index import InvertedIndex
from src.metrics import evaluate_run


ROOT = Path(__file__).resolve().parent
CORPUS = ROOT / "data/corpus.jsonl"
QRELS = ROOT / "data/qrels_v2.json"
LEXICAL_CONFIG = ROOT / "data/lexical_config.json"
EVAL_SPLIT = ROOT / "data/eval_split.json"
BASELINE = ROOT / "artifacts/section3/baseline.json"
SECTION5 = ROOT / "artifacts/section5"
DEVELOPMENT_EXPERIMENTS = ROOT / "artifacts/section4/development_experiments.json"
HOLDOUT = ROOT / "artifacts/section4/holdout.json"
BENCHMARK = ROOT / "artifacts/section4/benchmark_lexical.json"


@dataclass(frozen=True)
class Check:
    name: str
    state: str  # PASS, FAIL, or TBD
    detail: str
    required: bool = False


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {path.relative_to(ROOT)}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path.relative_to(ROOT)} must contain a JSON object")
    return value


def _require_hash(payload: dict[str, Any], key: str, path: Path) -> None:
    expected = payload.get(key)
    if not isinstance(expected, str) or len(expected) != 64:
        raise ValueError(f"missing valid {key} in frozen metadata")
    actual = sha256(path)
    if actual.upper() != expected.upper():
        raise ValueError(f"{key} mismatch: expected {expected.upper()}, got {actual}")


def _core_checks() -> tuple[list[Check], InvertedIndex, dict[str, Any], BM25Config]:
    for path in (CORPUS, QRELS, LEXICAL_CONFIG, EVAL_SPLIT, BASELINE):
        if not path.is_file():
            raise ValueError(f"required core artifact is missing: {path.relative_to(ROOT)}")
    qrels = load_qrels(QRELS)
    corpus_hash = validate_corpus_binding(CORPUS, qrels)
    config = _json(LEXICAL_CONFIG)
    _require_hash(config, "corpus_sha256", CORPUS)
    _require_hash(config, "qrels_sha256", QRELS)
    _require_hash(config, "eval_split_sha256", EVAL_SPLIT)
    baseline = _json(BASELINE)
    metadata = baseline.get("metadata")
    if not isinstance(metadata, dict):
        raise ValueError("baseline artifact has no metadata object")
    _require_hash(metadata, "corpus_sha256", CORPUS)
    _require_hash(metadata, "qrels_sha256", QRELS)
    bm25 = config.get("bm25")
    if not isinstance(bm25, dict) or not all(isinstance(bm25.get(k), (int, float)) for k in ("k1", "b")):
        raise ValueError("frozen lexical configuration has no usable BM25 parameters")
    index = InvertedIndex.from_jsonl(CORPUS)
    return [
        Check("frozen core hashes", "PASS", f"corpus {corpus_hash}; qrels/config/split bindings match", True),
        Check("inverted index", "PASS", f"{len(index.documents)} documents; {len(index.postings)} terms", True),
    ], index, qrels, BM25Config(k1=float(bm25["k1"]), b=float(bm25["b"]))


def _evaluate(index: InvertedIndex, qrels: dict[str, Any], config: BM25Config) -> list[Check]:
    rankings = {
        "boolean": {entry["id"]: search_boolean(index, entry["query"]) for entry in qrels["queries"]},
        "bm25": {
            entry["id"]: [result.doc_id for result in rank_bm25(index, entry["query"], k=len(index.documents), config=config)]
            for entry in qrels["queries"]
        },
    }
    checks: list[Check] = []
    for mode, ranked in rankings.items():
        report = evaluate_run(qrels, ranked, (1, 3, 5, 10))
        aggregate = report.aggregate
        checks.append(Check(
            f"current {mode} evaluation", "PASS",
            f"{aggregate['query_count']} queries; MRR={aggregate['mrr']:.3f}; NDCG@10={aggregate['ndcg_at'][10]:.3f}", True,
        ))
    return checks


def _section4_checks(config: dict[str, Any]) -> list[Check]:
    for path in (DEVELOPMENT_EXPERIMENTS, HOLDOUT, BENCHMARK):
        if not path.is_file():
            raise ValueError(f"required Section 4 artifact is missing: {path.relative_to(ROOT)}")
    _require_hash(config, "development_experiments_sha256", DEVELOPMENT_EXPERIMENTS)
    holdout = _json(HOLDOUT)
    metadata = holdout.get("metadata")
    if not isinstance(metadata, dict):
        raise ValueError("Section 4 holdout has no metadata")
    expected = {
        "corpus_sha256": sha256(CORPUS),
        "qrels_sha256": sha256(QRELS),
        "split_sha256": sha256(EVAL_SPLIT),
        "lexical_config_sha256": sha256(LEXICAL_CONFIG),
        "development_experiments_sha256": sha256(DEVELOPMENT_EXPERIMENTS),
    }
    if any(str(metadata.get(key, "")).upper() != value for key, value in expected.items()):
        raise ValueError("Section 4 holdout provenance does not match frozen inputs")
    benchmark = _json(BENCHMARK)
    inputs = benchmark.get("inputs")
    if not isinstance(inputs, dict) or any(
        str(inputs.get(key, "")).upper() != value
        for key, value in {
            "corpus_sha256": sha256(CORPUS),
            "qrels_sha256": sha256(QRELS),
            "lexical_config_sha256": sha256(LEXICAL_CONFIG),
        }.items()
    ):
        raise ValueError("Section 4 benchmark provenance does not match frozen inputs")
    return [Check("Section 4 experiment provenance", "PASS", "development grid, one-shot holdout, and benchmark hashes match", True)]


def _rag_checks() -> list[Check]:
    manifests = sorted(SECTION5.glob("*.jsonl.manifest.json")) if SECTION5.is_dir() else []
    if not manifests:
        return [Check("RAG chunk artifacts", "TBD", "no checked-in chunk manifests")]
    checks: list[Check] = []
    corpus_hash = sha256(CORPUS)
    for manifest_path in manifests:
        try:
            manifest = _json(manifest_path)
            chunks = manifest_path.with_name(manifest_path.name.removesuffix(".manifest.json"))
            if not chunks.is_file():
                raise ValueError("chunk file is missing")
            if manifest.get("corpus_sha256", "").upper() != corpus_hash:
                raise ValueError("corpus hash does not match")
            if manifest.get("chunk_sha256", "").upper() != sha256(chunks):
                raise ValueError("chunk hash does not match")
            with chunks.open(encoding="utf-8") as chunk_file:
                chunk_count = sum(1 for _ in chunk_file)
            if not isinstance(manifest.get("chunk_count"), int) or manifest["chunk_count"] != chunk_count:
                raise ValueError("chunk count does not match")
            checks.append(Check(f"RAG {chunks.name}", "PASS", "manifest binds chunk file and corpus"))
        except (OSError, ValueError) as exc:
            checks.append(Check(f"RAG {manifest_path.name}", "FAIL", str(exc)))
    qa = ROOT / "data/qa.json"
    if not qa.is_file():
        checks.append(Check("approved QA / faithfulness evaluation", "TBD", "approved QA artifact and offline caches are not committed"))
    else:
        checks.append(Check("approved QA / faithfulness evaluation", "TBD", "artifact present; release evaluator is pending human approval and credentials"))
    return checks


def _live_eval() -> list[Check]:
    # Never guess provider pricing or send a request from a release check.
    checks = [Check("live-eval cost estimate", "TBD", "cannot estimate honestly: committed RAG token counts and provider pricing are absent")]
    if not os.environ.get("OPENROUTER_API_KEY"):
        checks.append(Check("live-eval credentials", "TBD", "OPENROUTER_API_KEY is not set; no network call attempted"))
    else:
        checks.append(Check("live-eval pipeline", "TBD", "credential detected, but approved QA, cached embeddings, and release evaluator are incomplete; no paid call attempted"))
    return checks


def run(*, live_eval: bool = False) -> tuple[list[Check], bool]:
    try:
        checks, index, qrels, config = _core_checks()
        checks.extend(_section4_checks(_json(LEXICAL_CONFIG)))
        checks.extend(_evaluate(index, qrels, config))
    except (Day1Error, OSError, ValueError, KeyError, TypeError) as exc:
        return [Check("required core artifacts", "FAIL", str(exc), True)], True
    checks.extend(_rag_checks())
    if live_eval:
        checks.extend(_live_eval())
    return checks, any(check.state == "FAIL" for check in checks)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-eval", action="store_true", help="show guarded live-evaluation readiness; never runs paid calls while gates are incomplete")
    args = parser.parse_args(argv)
    checks, failed = run(live_eval=args.live_eval)
    print("Peptide-RAG release check (offline/read-only)")
    for check in checks:
        print(f"[{check.state}] {check.name}: {check.detail}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Run the Section 4 lexical experiment protocol on development queries only.

This module deliberately has no holdout evaluation entry point.  The frozen
split is checked before an index is built or a search function is invoked.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
import inspect
import json
from pathlib import Path
import sys
import tempfile
from collections.abc import Mapping, Sequence
from typing import Any

# Permit ``python scripts/run_lexical_tuning.py`` as well as module imports.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from run_day1 import load_qrels, sha256, validate_corpus_binding
try:  # Section 4's analyzer implementation lands with src.analysis.
    from src.analysis import ANALYSIS_CONFIGS
except ImportError:  # Keep the pure selection helpers importable during staged work.
    ANALYSIS_CONFIGS: Mapping[str, Any] = {}
from src.bm25 import BM25Config, rank_bm25
from src.index import InvertedIndex
from src.metrics import evaluate_run


DEFAULT_CORPUS = Path("data/corpus.jsonl")
DEFAULT_QRELS = Path("data/qrels_v2.json")
DEFAULT_SPLIT = Path("data/eval_split.json")
DEFAULT_JSON_OUTPUT = Path("artifacts/section4/development_experiments.json")
DEFAULT_MARKDOWN_OUTPUT = Path("artifacts/section4/development_experiments.md")
K1_VALUES = (0.8, 1.2, 1.6, 2.0)
B_VALUES = (0.0, 0.5, 0.75, 1.0)
ANALYZER_NAMES = ("baseline", "greek", "stopwords", "greek_stopwords")
PROXIMITY_BOOSTS = (0.0, 0.1, 0.25, 0.5)
CUTOFFS = (10,)


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=path.parent, delete=False) as handle:
            handle.write(content)
            temporary = Path(handle.name)
        temporary.replace(path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def load_and_validate_split(corpus: Path, qrels_path: Path, split_path: Path) -> tuple[dict[str, Any], dict[str, Any], tuple[str, ...], tuple[str, ...]]:
    """Return frozen data after verifying hashes and a complete disjoint split."""

    qrels = load_qrels(qrels_path)
    split = load_qrels(split_path)
    corpus_hash = validate_corpus_binding(corpus, qrels)
    if split.get("corpus_sha256", "").upper() != corpus_hash.upper():
        raise ValueError("eval split corpus hash does not exactly match corpus")
    qrels_hash = sha256(qrels_path)
    if split.get("qrels_sha256", "").upper() != qrels_hash.upper():
        raise ValueError("eval split qrels hash does not exactly match qrels")
    if split.get("qrels_path") != str(qrels_path).replace("\\", "/"):
        raise ValueError("eval split qrels_path does not match selected qrels")

    development = tuple(split.get("development_query_ids", ()))
    holdout = tuple(split.get("holdout_query_ids", ()))
    if not development or not holdout or not all(isinstance(item, str) and item for item in development + holdout):
        raise ValueError("eval split must contain non-empty string development and holdout IDs")
    if len(set(development)) != len(development) or len(set(holdout)) != len(holdout):
        raise ValueError("eval split query IDs must be unique within each partition")
    if set(development) & set(holdout):
        raise ValueError("development and holdout query IDs must be disjoint")
    qrels_ids = {entry.get("id") for entry in qrels.get("queries", []) if isinstance(entry, Mapping)}
    if set(development) | set(holdout) != qrels_ids:
        raise ValueError("development and holdout IDs must completely partition qrels queries")
    return qrels, split, development, holdout


def development_qrels(qrels: Mapping[str, Any], development_ids: Sequence[str]) -> dict[str, Any]:
    """Copy only approved development queries, preserving their split order."""

    by_id = {entry["id"]: entry for entry in qrels["queries"]}
    missing = [query_id for query_id in development_ids if query_id not in by_id]
    if missing:
        raise ValueError(f"development query IDs absent from qrels: {', '.join(missing)}")
    return {**qrels, "queries": [by_id[query_id] for query_id in development_ids]}


def make_bm25_config(k1: float, b: float, proximity_boost: float = 0.0) -> BM25Config:
    """Construct a future-compatible BM25 config without requiring proximity today."""

    fields = inspect.signature(BM25Config).parameters
    kwargs: dict[str, float] = {"k1": k1, "b": b}
    if "proximity_boost" in fields:
        kwargs["proximity_boost"] = proximity_boost
    elif proximity_boost != 0.0:
        raise RuntimeError("BM25Config does not support proximity_boost yet")
    return BM25Config(**kwargs)  # type: ignore[arg-type]


def evaluate_development(index: InvertedIndex, qrels: Mapping[str, Any], config: BM25Config) -> dict[str, Any]:
    """Search exactly the supplied development qrels and return rankings/metrics."""

    rankings: dict[str, list[str]] = {}
    for entry in qrels["queries"]:
        rankings[entry["id"]] = [item.doc_id for item in rank_bm25(index, entry["query"], k=len(index.documents), config=config)]
    # Per-query metrics are sufficient to audit selection and avoid duplicating
    # many full-corpus rankings across every grid candidate.
    return {"evaluation": evaluate_run(qrels, rankings, CUTOFFS).to_dict()}


def _metrics(result: Mapping[str, Any]) -> tuple[float, float, float]:
    aggregate = result["evaluation"]["aggregate"]
    return (float(aggregate["ndcg_at"]["10"]), float(aggregate["recall_at"]["10"]), float(aggregate["mrr"]))


def select_best(candidates: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    """Select by metrics, then simple/default-like settings, then numeric order."""

    evaluated = [candidate for candidate in candidates if candidate.get("status", "evaluated") == "evaluated"]
    if not evaluated:
        raise ValueError("no evaluated candidates to select")
    def key(candidate: Mapping[str, Any]) -> tuple[float, float, float, int, float, float, float, str]:
        ndcg, recall, mrr = _metrics(candidate)
        k1, b = float(candidate.get("k1", 1.2)), float(candidate.get("b", 0.75))
        boost = float(candidate.get("proximity_boost", 0.0))
        # Complexity is the number of departures from conventional BM25 and no boost.
        simplicity = int(k1 != 1.2) + int(b != 0.75) + int(boost != 0.0)
        distance = abs(k1 - 1.2) + abs(b - 0.75) + abs(boost)
        return (-ndcg, -recall, -mrr, simplicity, distance, k1, b, str(candidate.get("analyzer", "")))
    return min(evaluated, key=key)


def _config_payload(config: Any) -> Any:
    return asdict(config) if is_dataclass(config) else repr(config)


def _candidate(index: InvertedIndex, qrels: Mapping[str, Any], analyzer: str, k1: float, b: float, boost: float = 0.0) -> dict[str, Any]:
    value: dict[str, Any] = {"analyzer": analyzer, "k1": k1, "b": b, "proximity_boost": boost}
    try:
        config = make_bm25_config(k1, b, boost)
        value.update({"status": "evaluated", "bm25_config": _config_payload(config), **evaluate_development(index, qrels, config)})
    except RuntimeError as error:
        value.update({"status": "not_evaluated", "reason": str(error)})
    return value


def run(corpus: Path, qrels_path: Path, split_path: Path) -> tuple[dict[str, Any], str]:
    qrels, split, development_ids, holdout_ids = load_and_validate_split(corpus, qrels_path, split_path)
    unknown = [name for name in ANALYZER_NAMES if name not in ANALYSIS_CONFIGS]
    if unknown:
        raise ValueError(f"missing required analysis configurations: {', '.join(unknown)}")
    dev_qrels = development_qrels(qrels, development_ids)
    baseline_index = InvertedIndex.from_jsonl(corpus, analysis_config=ANALYSIS_CONFIGS["baseline"])
    parameter_grid = [_candidate(baseline_index, dev_qrels, "baseline", k1, b) for k1 in K1_VALUES for b in B_VALUES]
    chosen_parameters = select_best(parameter_grid)
    analyzer_results: list[dict[str, Any]] = []
    indexes: dict[str, InvertedIndex] = {"baseline": baseline_index}
    for name in ANALYZER_NAMES:
        if name not in indexes:
            indexes[name] = InvertedIndex.from_jsonl(corpus, analysis_config=ANALYSIS_CONFIGS[name])
        index = indexes[name]
        analyzer_results.append(_candidate(index, dev_qrels, name, chosen_parameters["k1"], chosen_parameters["b"]))
    chosen_analyzer = select_best(analyzer_results)
    chosen_index = indexes[chosen_analyzer["analyzer"]]
    proximity_results = [_candidate(chosen_index, dev_qrels, chosen_analyzer["analyzer"], chosen_parameters["k1"], chosen_parameters["b"], boost) for boost in PROXIMITY_BOOSTS]
    chosen_proximity = select_best(proximity_results)
    selected = {key: chosen_proximity[key] for key in ("analyzer", "k1", "b", "proximity_boost", "bm25_config")}
    payload = {"metadata": {"schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(), "corpus_sha256": sha256(corpus), "qrels_sha256": sha256(qrels_path), "qrels_version": qrels.get("version"), "split": {"path": str(split_path).replace("\\", "/"), "version": split.get("version"), "development_query_ids": list(development_ids), "holdout_query_ids": list(holdout_ids), "holdout_evaluated": False}, "selection_order": ["NDCG@10", "Recall@10", "MRR", "simplicity", "distance to (k1=1.2,b=0.75,proximity=0)", "numeric order"]}, "experiments": {"parameter_grid": parameter_grid, "analyzers": analyzer_results, "proximity": proximity_results}, "selected": selected}
    markdown = render_markdown(payload)
    return payload, markdown


def render_markdown(payload: Mapping[str, Any]) -> str:
    lines = ["# Section 4 Lexical Development Experiments", "", "Holdout queries were not searched or evaluated.", "", "## Selected configuration", "", "```json", json.dumps(payload["selected"], indent=2), "```", ""]
    for stage, candidates in payload["experiments"].items():
        lines.extend([f"## {stage.replace('_', ' ').title()}", "", "| Analyzer | k1 | b | Proximity | Status | NDCG@10 | Recall@10 | MRR |", "| --- | ---: | ---: | ---: | --- | ---: | ---: | ---: |"])
        for candidate in candidates:
            if candidate["status"] == "evaluated":
                ndcg, recall, mrr = _metrics(candidate)
                values = (f"{ndcg:.4f}", f"{recall:.4f}", f"{mrr:.4f}")
            else:
                values = ("—", "—", "—")
            lines.append(f"| {candidate['analyzer']} | {candidate['k1']} | {candidate['b']} | {candidate['proximity_boost']} | {candidate['status']} | " + " | ".join(values) + " |")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--qrels", type=Path, default=DEFAULT_QRELS)
    parser.add_argument("--split", type=Path, default=DEFAULT_SPLIT)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--markdown-output", type=Path, default=DEFAULT_MARKDOWN_OUTPUT)
    args = parser.parse_args(argv)
    try:
        payload, markdown = run(args.corpus, args.qrels, args.split)
        _atomic_write(args.json_output, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
        _atomic_write(args.markdown_output, markdown)
    except (OSError, ValueError, RuntimeError) as error:
        parser.error(str(error))
    print(f"JSON: {args.json_output}")
    print(f"Markdown: {args.markdown_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

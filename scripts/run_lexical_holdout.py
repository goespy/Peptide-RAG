#!/usr/bin/env python3
"""Evaluate the frozen lexical configuration on the untouched holdout once."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from run_day1 import load_qrels, sha256
from scripts.run_lexical_tuning import development_qrels, load_and_validate_split
from src.analysis import ANALYSIS_CONFIGS
from src.bm25 import BM25Config, rank_bm25
from src.index import InvertedIndex
from src.metrics import EvaluationReport, evaluate_run, render_markdown


DEFAULT_CORPUS = Path("data/corpus.jsonl")
DEFAULT_QRELS = Path("data/qrels_v2.json")
DEFAULT_SPLIT = Path("data/eval_split.json")
DEFAULT_CONFIG = Path("data/lexical_config.json")
DEFAULT_DEVELOPMENT = Path("artifacts/section4/development_experiments.json")
DEFAULT_JSON = Path("artifacts/section4/holdout.json")
DEFAULT_MARKDOWN = Path("artifacts/section4/holdout.md")
CUTOFFS = (1, 3, 5, 10)


def _atomic_create(path: Path, content: str) -> None:
    """Create a report atomically and refuse to replace the one-shot result."""

    if path.exists():
        raise FileExistsError(f"holdout output already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", newline="\n", dir=path.parent, delete=False
        ) as handle:
            handle.write(content)
            temporary = Path(handle.name)
        if path.exists():
            raise FileExistsError(f"holdout output already exists: {path}")
        temporary.replace(path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _revision() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unavailable"


def _subset(qrels: Mapping[str, Any], query_ids: Sequence[str]) -> dict[str, Any]:
    return development_qrels(qrels, query_ids)


def _evaluate(
    index: InvertedIndex, qrels: Mapping[str, Any], config: BM25Config
) -> EvaluationReport:
    rankings = {
        entry["id"]: [
            result.doc_id
            for result in rank_bm25(
                index, entry["query"], k=len(index.documents), config=config
            )
        ]
        for entry in qrels["queries"]
    }
    return evaluate_run(qrels, rankings, CUTOFFS)


def _load_frozen_config(
    config_path: Path,
    corpus_hash: str,
    qrels_hash: str,
    split_path: Path,
    development_path: Path,
) -> tuple[dict[str, Any], BM25Config]:
    payload = load_qrels(config_path)
    if payload.get("status") != "frozen_before_holdout_evaluation":
        raise ValueError("lexical configuration was not frozen before holdout")
    expected = {
        "corpus_sha256": corpus_hash,
        "qrels_sha256": qrels_hash,
        "eval_split_sha256": sha256(split_path),
        "development_experiments_sha256": sha256(development_path),
    }
    for field, actual in expected.items():
        if str(payload.get(field, "")).upper() != actual.upper():
            raise ValueError(f"frozen lexical configuration has a mismatched {field}")
    analysis = payload.get("analysis")
    bm25 = payload.get("bm25")
    if not isinstance(analysis, Mapping) or analysis.get("name") not in ANALYSIS_CONFIGS:
        raise ValueError("frozen lexical analysis configuration is invalid")
    if not isinstance(bm25, Mapping) or bm25.get("variant") != "lucene":
        raise ValueError("frozen BM25 configuration is invalid")
    return payload, BM25Config(
        k1=bm25.get("k1"),
        b=bm25.get("b"),
        proximity_boost=bm25.get("proximity_boost", 0.0),
    )


def _delta(tuned: EvaluationReport, baseline: EvaluationReport) -> dict[str, Any]:
    cutoffs = tuple(k for k in tuned.cutoffs if k in baseline.cutoffs)
    return {
        "mrr": tuned.aggregate["mrr"] - baseline.aggregate["mrr"],
        "precision_at": {
            str(k): tuned.aggregate["precision_at"][k]
            - baseline.aggregate["precision_at"][k]
            for k in cutoffs
        },
        "recall_at": {
            str(k): tuned.aggregate["recall_at"][k]
            - baseline.aggregate["recall_at"][k]
            for k in cutoffs
        },
        "ndcg_at": {
            str(k): tuned.aggregate["ndcg_at"][k]
            - baseline.aggregate["ndcg_at"][k]
            for k in cutoffs
        },
    }


def run(
    corpus: Path,
    qrels_path: Path,
    split_path: Path,
    config_path: Path,
    development_path: Path,
) -> tuple[dict[str, Any], str]:
    qrels, _, development_ids, holdout_ids = load_and_validate_split(
        corpus, qrels_path, split_path
    )
    frozen, tuned_config = _load_frozen_config(
        config_path,
        sha256(corpus),
        sha256(qrels_path),
        split_path,
        development_path,
    )
    analyzer_name = frozen["analysis"]["name"]
    index = InvertedIndex.from_jsonl(
        corpus, analysis_config=ANALYSIS_CONFIGS[analyzer_name]
    )
    holdout_qrels = _subset(qrels, holdout_ids)
    baseline_config = BM25Config()
    baseline_holdout = _evaluate(index, holdout_qrels, baseline_config)
    tuned_holdout = _evaluate(index, holdout_qrels, tuned_config)
    tuned_full = _evaluate(index, qrels, tuned_config)
    payload = {
        "metadata": {
            "schema_version": 1,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_revision": _revision(),
            "one_shot_holdout": True,
            "corpus_sha256": sha256(corpus),
            "qrels_sha256": sha256(qrels_path),
            "split_sha256": sha256(split_path),
            "lexical_config_sha256": sha256(config_path),
            "development_experiments_sha256": sha256(development_path),
            "development_query_ids": list(development_ids),
            "holdout_query_ids": list(holdout_ids),
        },
        "baseline_config": {"k1": 1.2, "b": 0.75, "proximity_boost": 0.0},
        "tuned_config": {
            "analysis": analyzer_name,
            "k1": tuned_config.k1,
            "b": tuned_config.b,
            "proximity_boost": tuned_config.proximity_boost,
        },
        "holdout": {
            "baseline": baseline_holdout.to_dict(),
            "tuned": tuned_holdout.to_dict(),
            "delta": _delta(tuned_holdout, baseline_holdout),
        },
        "full_descriptive": tuned_full.to_dict(),
    }
    lines = [
        "# Section 4 One-Shot Lexical Holdout",
        "",
        "The selected configuration was hash-frozen before this command accessed holdout queries.",
        "",
        f"- Source revision: `{payload['metadata']['source_revision']}`",
        f"- Holdout queries: `{', '.join(holdout_ids)}`",
        f"- Tuned configuration: `{json.dumps(payload['tuned_config'], sort_keys=True)}`",
        "",
        "## Untouched BM25 holdout",
        "",
        render_markdown(baseline_holdout.results, CUTOFFS).rstrip(),
        "",
        "## Tuned BM25 holdout",
        "",
        render_markdown(tuned_holdout.results, CUTOFFS).rstrip(),
        "",
        "## Tuned full-set descriptive metrics",
        "",
        render_markdown(tuned_full.results, CUTOFFS).rstrip(),
        "",
    ]
    return payload, "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--qrels", type=Path, default=DEFAULT_QRELS)
    parser.add_argument("--split", type=Path, default=DEFAULT_SPLIT)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--development", type=Path, default=DEFAULT_DEVELOPMENT)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--markdown-output", type=Path, default=DEFAULT_MARKDOWN)
    args = parser.parse_args(argv)
    if args.json_output.exists() or args.markdown_output.exists():
        parser.error("holdout output already exists; rerunning is prohibited")
    try:
        payload, markdown = run(
            args.corpus, args.qrels, args.split, args.config, args.development
        )
        _atomic_create(
            args.json_output,
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        )
        _atomic_create(args.markdown_output, markdown)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(f"JSON: {args.json_output}")
    print(f"Markdown: {args.markdown_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Build the Day 1 index and print measured Boolean retrieval metrics."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from src.boolean import search_boolean
from src.index import InvertedIndex
from src.metrics import evaluate_qrels, render_markdown


DEFAULT_CORPUS = Path("data/corpus.jsonl")
DEFAULT_QRELS = Path("data/qrels.json")
DEFAULT_KS = (1, 3, 5)


class Day1Error(RuntimeError):
    """Raised when reproducible Day 1 evaluation cannot run."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise Day1Error(f"Could not hash {path}: {exc}") from exc
    return digest.hexdigest().upper()


def load_qrels(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Day1Error(f"Could not read qrels {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise Day1Error("Qrels root must be a JSON object")
    return payload


def validate_corpus_binding(corpus: Path, qrels: dict[str, Any]) -> str:
    expected = qrels.get("corpus_sha256")
    if not isinstance(expected, str) or len(expected) != 64:
        raise Day1Error("Qrels must contain a 64-character corpus_sha256")
    actual = sha256(corpus)
    if actual.upper() != expected.upper():
        raise Day1Error(
            f"Corpus hash mismatch: qrels expect {expected.upper()}, got {actual}"
        )
    return actual


def run(corpus: Path, qrels_path: Path, ks: Sequence[int]) -> str:
    qrels = load_qrels(qrels_path)
    corpus_hash = validate_corpus_binding(corpus, qrels)
    index = InvertedIndex.from_jsonl(corpus)
    results = evaluate_qrels(
        lambda query: search_boolean(index, query), qrels, ks=ks
    )
    metrics = render_markdown(results, ks=ks)
    return "\n".join(
        [
            "# Day 1 Boolean Evaluation",
            "",
            f"- Corpus SHA-256: `{corpus_hash}`",
            f"- Indexed documents: {len(index.documents)}",
            f"- Vocabulary terms: {len(index.postings)}",
            f"- Qrels version: {qrels.get('version', 'unknown')}",
            "- Retrieval ordering: numeric PMID (unranked Boolean baseline)",
            "",
            metrics,
        ]
    )


def positive_integer(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("k must be an integer") from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError("k must be greater than zero")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--qrels", type=Path, default=DEFAULT_QRELS)
    parser.add_argument("--k", type=positive_integer, nargs="+", default=list(DEFAULT_KS))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        print(run(args.corpus, args.qrels, tuple(dict.fromkeys(args.k))))
    except (Day1Error, OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

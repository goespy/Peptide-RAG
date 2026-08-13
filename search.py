#!/usr/bin/env python3
"""Search the frozen Peptide-RAG corpus with Boolean or BM25 retrieval."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from src.boolean import search_boolean
from src.bm25 import rank_bm25
from src.index import InvertedIndex
from src.snippets import make_snippet


def configure_utf8_output() -> None:
    """Keep Unicode medical titles printable on legacy Windows consoles."""

    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8", errors="replace")


def positive_integer(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("top-k must be an integer") from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError("top-k must be greater than zero")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", help="Search query; quote it when it contains spaces")
    parser.add_argument("--corpus", type=Path, default=Path("data/corpus.jsonl"))
    parser.add_argument("--mode", choices=("boolean", "bm25"), default="bm25")
    parser.add_argument("--top-k", type=positive_integer, default=10)
    # Retained for callers of the original Day 1 command line interface.
    parser.add_argument("--limit", type=positive_integer, dest="top_k", help=argparse.SUPPRESS)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    configure_utf8_output()
    args = build_parser().parse_args(argv)
    try:
        index = InvertedIndex.from_jsonl(args.corpus)
        if args.mode == "boolean":
            matches = search_boolean(index, args.query)
        else:
            matches = rank_bm25(index, args.query, k=args.top_k)
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"{len(matches)} match(es)")
    if args.mode == "boolean":
        for doc_id in matches[: args.top_k]:
            print(f"{doc_id}\t{index.documents[doc_id].title}")
        return 0

    for rank, result in enumerate(matches, start=1):
        document = index.documents[result.doc_id]
        print(f"{rank}. PMID: {result.doc_id} | score: {result.score:.6f}")
        print(f"Title: {document.title}")
        print(f"Snippet: {make_snippet(document.text or document.title, args.query)}")
        print(f"URL: https://pubmed.ncbi.nlm.nih.gov/{result.doc_id}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

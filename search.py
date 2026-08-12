#!/usr/bin/env python3
"""Search the frozen Peptide-RAG corpus with Day 1 Boolean retrieval."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from src.boolean import search_boolean
from src.index import InvertedIndex


def configure_utf8_output() -> None:
    """Keep Unicode medical titles printable on legacy Windows consoles."""

    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8", errors="replace")


def positive_integer(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("limit must be an integer") from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError("limit must be greater than zero")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", help="Boolean query; quote it when it contains spaces")
    parser.add_argument("--corpus", type=Path, default=Path("data/corpus.jsonl"))
    parser.add_argument("--limit", type=positive_integer, default=10)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    configure_utf8_output()
    args = build_parser().parse_args(argv)
    try:
        index = InvertedIndex.from_jsonl(args.corpus)
        matches = search_boolean(index, args.query)
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"{len(matches)} match(es)")
    for doc_id in matches[: args.limit]:
        print(f"{doc_id}\t{index.documents[doc_id].title}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

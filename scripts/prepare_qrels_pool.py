#!/usr/bin/env python3
"""Create deterministic qrels candidates for human relevance review.

This program never assigns relevance.  It only records why each candidate was
placed in a small review pool so a person can add zero, partial, or direct
relevance judgments in a later, versioned qrels file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

# Direct execution places ``scripts`` rather than the repository root on
# ``sys.path``.  Add the root so the command advertised in the README works
# the same way as importing this module in tests.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.analysis import analyze
from src.boolean import search_boolean
from src.index import InvertedIndex


DEFAULT_CORPUS = Path("data/corpus.jsonl")
DEFAULT_QRELS = Path("data/qrels.json")
DEFAULT_OUTPUT = Path("data/qrels_pool.json")
DEFAULT_POOL_SIZE = 5


class QrelsPoolError(RuntimeError):
    """Raised when a review pool cannot be prepared safely."""


def corpus_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def _numeric_pmid(value: object, description: str) -> str:
    if not isinstance(value, str) or not value.isdigit() or not value:
        raise QrelsPoolError(f"{description} must be a non-empty numeric PMID")
    return value


def load_qrels(path: Path, actual_corpus_hash: str) -> list[dict[str, Any]]:
    """Load approved qrels and bind them to the exact frozen corpus."""

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise QrelsPoolError(f"qrels not found: {path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise QrelsPoolError(f"Could not read qrels: {path}") from exc
    if not isinstance(raw, dict):
        raise QrelsPoolError("qrels must be a JSON object")
    if raw.get("corpus_sha256") != actual_corpus_hash:
        raise QrelsPoolError("qrels corpus_sha256 does not match the frozen corpus")
    review = raw.get("review")
    if not isinstance(review, dict) or review.get("status") != "approved_provisional_known_item_set":
        raise QrelsPoolError("qrels must be an approved provisional known-item set")
    queries = raw.get("queries")
    if not isinstance(queries, list) or not queries:
        raise QrelsPoolError("qrels must contain a non-empty queries list")

    seen_ids: set[str] = set()
    loaded: list[dict[str, Any]] = []
    for number, query in enumerate(queries, start=1):
        if not isinstance(query, dict):
            raise QrelsPoolError(f"qrels query {number} must be an object")
        query_id = query.get("id")
        text = query.get("query")
        judgments = query.get("judgments")
        if not isinstance(query_id, str) or not query_id or query_id in seen_ids:
            raise QrelsPoolError(f"qrels query {number} has an invalid or duplicate id")
        if not isinstance(text, str) or not text.strip():
            raise QrelsPoolError(f"qrels query {query_id} must have non-empty query text")
        if not isinstance(judgments, dict):
            raise QrelsPoolError(f"qrels query {query_id} judgments must be an object")
        checked_judgments: dict[str, int | float] = {}
        for pmid, grade in judgments.items():
            checked_pmid = _numeric_pmid(pmid, f"qrels query {query_id} judgment id")
            if isinstance(grade, bool) or not isinstance(grade, (int, float)):
                raise QrelsPoolError(f"qrels query {query_id} judgment grades must be numeric")
            checked_judgments[checked_pmid] = grade
        seen_ids.add(query_id)
        loaded.append({"id": query_id, "query": text, "judgments": checked_judgments})
    return loaded


def _matched_terms(
    term_document_ids: Mapping[str, set[str]], document_id: str
) -> list[str]:
    """Return query terms found in a document, preserving query order."""

    return [
        term for term, document_ids in term_document_ids.items()
        if document_id in document_ids
    ]


def _candidate(
    index: InvertedIndex,
    document_id: str,
    grade: int | float | None,
    sources: list[str],
    term_document_ids: Mapping[str, set[str]],
) -> dict[str, object]:
    document = index.documents[document_id]
    return {
        "pmid": document_id,
        "title": document.title,
        "abstract": document.text,
        "discovery_sources": sources,
        "matched_terms": _matched_terms(term_document_ids, document_id),
        "existing_grade": grade,
    }


def build_pool(corpus_path: Path, qrels_path: Path, pool_size: int) -> dict[str, object]:
    """Build a deterministic human-review candidate pool without writing it."""

    if pool_size < 1:
        raise ValueError("pool_size must be at least 1")
    try:
        actual_hash = corpus_sha256(corpus_path)
        index = InvertedIndex.from_jsonl(corpus_path)
    except (OSError, ValueError) as exc:
        raise QrelsPoolError(f"Could not load frozen corpus: {exc}") from exc
    queries = load_qrels(qrels_path, actual_hash)

    pools: list[dict[str, object]] = []
    for item in queries:
        query = item["query"]
        judgments = item["judgments"]
        assert isinstance(query, str) and isinstance(judgments, dict)
        query_terms = tuple(dict.fromkeys(analyze(query)))
        term_document_ids = {
            term: set(index.doc_ids(term)) for term in query_terms
        }
        selected: list[str] = []
        selected_ids: set[str] = set()
        sources_by_id: dict[str, list[str]] = {}

        # Preserve JSON qrels order for existing judgments, then deterministic
        # numeric PMID order from Boolean retrieval and relaxed matching.
        for pmid in judgments:
            if pmid not in index.documents:
                raise QrelsPoolError(f"qrels judgment PMID {pmid} is absent from corpus")
            selected.append(pmid)
            selected_ids.add(pmid)
            sources_by_id[pmid] = ["existing_judgment"]

        target = max(pool_size, len(selected))
        strict_ids = search_boolean(index, query)
        for pmid in strict_ids:
            if pmid in selected_ids:
                sources_by_id[pmid].append("strict_boolean")
                continue
            if len(selected) >= target:
                break
            selected.append(pmid)
            selected_ids.add(pmid)
            sources_by_id[pmid] = ["strict_boolean"]

        overlaps: list[tuple[int, int, str]] = []
        for pmid in index.documents:
            if pmid in selected_ids:
                continue
            count = sum(pmid in document_ids for document_ids in term_document_ids.values())
            if count:
                overlaps.append((-count, int(pmid), pmid))
        for _, _, pmid in sorted(overlaps):
            if len(selected) >= target:
                break
            selected.append(pmid)
            selected_ids.add(pmid)
            sources_by_id[pmid] = ["relaxed_distinct_term_overlap"]

        candidates = [
            _candidate(
                index,
                pmid,
                judgments.get(pmid),
                sources_by_id[pmid],
                term_document_ids,
            )
            for pmid in selected
        ]
        pools.append({"id": item["id"], "query": query, "candidates": candidates})

    return {
        "status": "candidate_pool_requires_human_review",
        "corpus_sha256": actual_hash,
        "pool_size_requested": pool_size,
        "queries": pools,
        "review_instructions": (
            "Assign no grade from this file automatically. A human must review each "
            "candidate and create a new versioned qrels file with documented judgments."
        ),
    }


def write_json_atomic(payload: dict[str, object], output: Path, *, overwrite: bool) -> None:
    if output.exists() and not overwrite:
        raise QrelsPoolError(f"Output already exists: {output}. Pass --overwrite to replace it.")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                         prefix=f".{output.name}.", suffix=".tmp",
                                         dir=output.parent, delete=False) as temporary:
            temporary_path = Path(temporary.name)
            json.dump(payload, temporary, ensure_ascii=False, indent=2)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, output)
    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise


def positive_integer(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("pool size must be an integer") from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError("pool size must be at least 1")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--qrels", type=Path, default=DEFAULT_QRELS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--pool-size", type=positive_integer, default=DEFAULT_POOL_SIZE)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload = build_pool(args.corpus, args.qrels, args.pool_size)
        write_json_atomic(payload, args.output, overwrite=args.overwrite)
    except (OSError, QrelsPoolError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote candidate pool for {len(payload['queries'])} queries to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

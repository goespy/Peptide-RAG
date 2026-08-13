#!/usr/bin/env python3
"""Render the deterministic qrels pool as a human labeling worksheet."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


DEFAULT_POOL = Path("data/qrels_pool.json")
DEFAULT_OUTPUT = Path("QRELS-POOL-REVIEW.md")


class PoolReviewError(RuntimeError):
    """Raised when a candidate pool cannot be safely rendered."""


def load_pool(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PoolReviewError(f"candidate pool not found: {path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise PoolReviewError(f"Could not read candidate pool: {path}") from exc
    if not isinstance(payload, dict):
        raise PoolReviewError("candidate pool must be a JSON object")
    return payload


def _validated_queries(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    if payload.get("status") != "candidate_pool_requires_human_review":
        raise PoolReviewError("candidate pool has an unexpected status")
    corpus_hash = payload.get("corpus_sha256")
    if not isinstance(corpus_hash, str) or len(corpus_hash) != 64:
        raise PoolReviewError("candidate pool needs a SHA-256 corpus binding")
    queries = payload.get("queries")
    if not isinstance(queries, list) or not queries:
        raise PoolReviewError("candidate pool must contain queries")

    seen_queries: set[str] = set()
    seen_pairs: set[tuple[str, str]] = set()
    for position, query in enumerate(queries, start=1):
        if not isinstance(query, Mapping):
            raise PoolReviewError(f"query {position} must be an object")
        query_id = query.get("id")
        query_text = query.get("query")
        candidates = query.get("candidates")
        if (
            not isinstance(query_id, str)
            or not query_id
            or query_id in seen_queries
        ):
            raise PoolReviewError(f"query {position} has an invalid or duplicate id")
        if not isinstance(query_text, str) or not query_text.strip():
            raise PoolReviewError(f"query {query_id} needs non-empty text")
        if not isinstance(candidates, list) or not candidates:
            raise PoolReviewError(f"query {query_id} needs candidates")
        seen_queries.add(query_id)

        for candidate in candidates:
            if not isinstance(candidate, Mapping):
                raise PoolReviewError(f"query {query_id} candidate must be an object")
            pmid = candidate.get("pmid")
            if not isinstance(pmid, str) or not pmid.isdigit():
                raise PoolReviewError(f"query {query_id} candidate needs a numeric PMID")
            pair = (query_id, pmid)
            if pair in seen_pairs:
                raise PoolReviewError(f"query {query_id} repeats PMID {pmid}")
            seen_pairs.add(pair)
            if not isinstance(candidate.get("title"), str) or not isinstance(
                candidate.get("abstract"), str
            ):
                raise PoolReviewError(f"query {query_id} PMID {pmid} needs text fields")
            sources = candidate.get("discovery_sources")
            matched_terms = candidate.get("matched_terms")
            if not isinstance(sources, list) or not sources or not all(
                isinstance(value, str) and value for value in sources
            ):
                raise PoolReviewError(f"query {query_id} PMID {pmid} needs discovery sources")
            if not isinstance(matched_terms, list) or not all(
                isinstance(value, str) and value for value in matched_terms
            ):
                raise PoolReviewError(f"query {query_id} PMID {pmid} has invalid matched terms")
            grade = candidate.get("existing_grade")
            if grade is not None and (
                isinstance(grade, bool) or not isinstance(grade, (int, float))
            ):
                raise PoolReviewError(f"query {query_id} PMID {pmid} has an invalid grade")
    return queries


def render_markdown(payload: Mapping[str, Any]) -> str:
    queries = _validated_queries(payload)
    candidate_count = sum(len(query["candidates"]) for query in queries)
    lines = [
        "# Pooled Qrels Human Review",
        "",
        "> **Human labels required.** Candidate selection is automatic; relevance is not. Read each title and abstract, choose exactly one grade, and add a short reason. Do not copy unchecked values into `data/qrels.json`.",
        "",
        f"- Corpus SHA-256: `{payload['corpus_sha256']}`",
        f"- Queries: {len(queries)}",
        f"- Candidate query-document pairs: {candidate_count}",
        "- Existing grades are retained for re-confirmation, not treated as automatic answers.",
        "",
        "## Grade rubric",
        "",
        "- **2 — directly relevant:** substantially answers the query's information need.",
        "- **1 — partially relevant:** useful background or related evidence, but does not fully answer it.",
        "- **0 — not relevant:** term overlap without satisfying the information need.",
        "",
        "For every candidate, select one grade and explain the topical decision. After all labels are reviewed, create qrels version 2 and rerun the same metrics without changing the retrieval code.",
        "",
    ]

    for query in queries:
        query_id = query["id"]
        lines.extend([f"## {query_id} — `{query['query']}`", ""])
        for candidate in query["candidates"]:
            pmid = candidate["pmid"]
            existing = candidate["existing_grade"]
            existing_text = "unjudged" if existing is None else str(existing)
            sources = ", ".join(candidate["discovery_sources"])
            matched = ", ".join(candidate["matched_terms"]) or "none"
            abstract = candidate["abstract"] or "*No abstract available.*"
            lines.extend(
                [
                    f"### PMID {pmid}",
                    "",
                    f"- PubMed: https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                    f"- Existing grade: `{existing_text}`",
                    f"- Candidate source: `{sources}`",
                    f"- Matched query terms: `{matched}`",
                    "- Human grade: [ ] 0  [ ] 1  [ ] 2",
                    "- Human reason:",
                    "- Reviewer:",
                    "",
                    "**Title**",
                    "",
                    candidate["title"] or "*No title available.*",
                    "",
                    "**Abstract**",
                    "",
                    abstract,
                    "",
                ]
            )
    return "\n".join(lines).rstrip() + "\n"


def write_atomic(content: str, output: Path, *, overwrite: bool) -> None:
    if output.exists() and not overwrite:
        raise PoolReviewError(
            f"Output already exists: {output}. Pass --overwrite to replace it."
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix=f".{output.name}.",
            suffix=".tmp",
            dir=output.parent,
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, output)
    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pool", type=Path, default=DEFAULT_POOL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload = load_pool(args.pool)
        content = render_markdown(payload)
        write_atomic(content, args.output, overwrite=args.overwrite)
    except (OSError, PoolReviewError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote human review worksheet to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

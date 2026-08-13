#!/usr/bin/env python3
"""Validate a completed pooled review and freeze numeric qrels version 2."""

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


DEFAULT_CORPUS = Path("data/corpus.jsonl")
DEFAULT_POOL = Path("data/qrels_pool.json")
DEFAULT_REVIEW = Path("data/qrels_v2_review.json")
DEFAULT_OUTPUT = Path("data/qrels_v2.json")


class QrelsFreezeError(RuntimeError):
    """Raised when review evidence is incomplete or inconsistent."""


def _load_object(path: Path, description: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise QrelsFreezeError(f"{description} not found: {path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise QrelsFreezeError(f"Could not read {description}: {path}") from exc
    if not isinstance(payload, dict):
        raise QrelsFreezeError(f"{description} must be a JSON object")
    return payload


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise QrelsFreezeError(f"Could not hash corpus: {path}") from exc
    return digest.hexdigest().upper()


def _query_map(payload: Mapping[str, Any], description: str) -> dict[str, Mapping[str, Any]]:
    queries = payload.get("queries")
    if not isinstance(queries, list) or not queries:
        raise QrelsFreezeError(f"{description} must contain queries")
    mapped: dict[str, Mapping[str, Any]] = {}
    for position, query in enumerate(queries, start=1):
        if not isinstance(query, Mapping):
            raise QrelsFreezeError(f"{description} query {position} must be an object")
        query_id = query.get("id")
        if not isinstance(query_id, str) or not query_id or query_id in mapped:
            raise QrelsFreezeError(
                f"{description} query {position} has an invalid or duplicate id"
            )
        mapped[query_id] = query
    return mapped


def freeze_qrels(
    corpus_path: Path, pool_path: Path, review_path: Path
) -> dict[str, Any]:
    """Return final qrels only when every pooled candidate has a valid human grade."""

    pool = _load_object(pool_path, "candidate pool")
    review = _load_object(review_path, "pooled review")
    if pool.get("status") != "candidate_pool_requires_human_review":
        raise QrelsFreezeError("candidate pool has an unexpected status")
    if review.get("status") != "human_pool_review_complete":
        raise QrelsFreezeError("pooled review is not complete")
    if review.get("target_qrels_version") != 2:
        raise QrelsFreezeError("pooled review must target qrels version 2")

    actual_hash = _sha256(corpus_path)
    if pool.get("corpus_sha256") != actual_hash or review.get("corpus_sha256") != actual_hash:
        raise QrelsFreezeError("corpus, pool, and review hashes must match")

    pool_queries = _query_map(pool, "candidate pool")
    review_queries = _query_map(review, "pooled review")
    if tuple(pool_queries) != tuple(review_queries):
        raise QrelsFreezeError("pool and review query ids or order do not match")

    frozen_queries: list[dict[str, Any]] = []
    approval_dates: list[str] = []
    reviewers: set[str] = set()
    for query_id, pool_query in pool_queries.items():
        review_query = review_queries[query_id]
        if review_query.get("query") != pool_query.get("query"):
            raise QrelsFreezeError(f"{query_id} query text changed during review")
        if review_query.get("approved") is not True:
            raise QrelsFreezeError(f"{query_id} is not approved")
        approved_on = review_query.get("approved_on")
        reviewer = review_query.get("reviewer")
        if not isinstance(approved_on, str) or not approved_on:
            raise QrelsFreezeError(f"{query_id} needs an approval date")
        if not isinstance(reviewer, str) or not reviewer:
            raise QrelsFreezeError(f"{query_id} needs a reviewer")
        approval_dates.append(approved_on)
        reviewers.add(reviewer)

        candidates = pool_query.get("candidates")
        reviewed_judgments = review_query.get("judgments")
        if not isinstance(candidates, list) or not isinstance(reviewed_judgments, Mapping):
            raise QrelsFreezeError(f"{query_id} has invalid candidates or judgments")
        candidate_ids: list[str] = []
        for candidate in candidates:
            if not isinstance(candidate, Mapping):
                raise QrelsFreezeError(f"{query_id} candidate must be an object")
            pmid = candidate.get("pmid")
            if not isinstance(pmid, str) or not pmid.isdigit() or pmid in candidate_ids:
                raise QrelsFreezeError(f"{query_id} has an invalid candidate PMID")
            candidate_ids.append(pmid)
        if set(reviewed_judgments) != set(candidate_ids):
            raise QrelsFreezeError(f"{query_id} must judge every and only pooled PMID")

        numeric: dict[str, int] = {}
        reasons: dict[str, str] = {}
        for pmid in candidate_ids:
            judgment = reviewed_judgments[pmid]
            if not isinstance(judgment, Mapping):
                raise QrelsFreezeError(f"{query_id} PMID {pmid} judgment must be an object")
            grade = judgment.get("grade")
            reason = judgment.get("reason")
            if isinstance(grade, bool) or not isinstance(grade, int) or grade not in (0, 1, 2):
                raise QrelsFreezeError(f"{query_id} PMID {pmid} grade must be 0, 1, or 2")
            if not isinstance(reason, str) or not reason.strip():
                raise QrelsFreezeError(f"{query_id} PMID {pmid} needs a reason")
            numeric[pmid] = grade
            reasons[pmid] = reason

        frozen_queries.append(
            {
                "id": query_id,
                "query": pool_query["query"],
                "judgments": numeric,
                "rationale": "Five pooled titles and abstracts were topically graded under the documented 0/1/2 rubric.",
                "judgment_rationales": reasons,
            }
        )

    audit = review.get("consistency_audit")
    if not isinstance(audit, Mapping) or not isinstance(audit.get("changes"), list):
        raise QrelsFreezeError("completed review needs a documented consistency audit")
    return {
        "version": 2,
        "corpus_sha256": actual_hash,
        "review": {
            "status": "approved_pooled_judgment_set",
            "approved_on": max(approval_dates),
            "reviewers": sorted(reviewers),
            "approval_basis": "The project owner approved q01-q08 and delegated q09-q15 plus a full consistency audit to Codex.",
            "methodology": "Five candidates per query: existing judgments, strict Boolean matches, then deterministic distinct-term overlap; relevance was assigned only after title-and-abstract review.",
            "limitation": "The pool is lexical and depth-5, not exhaustive; relevant documents outside the pool may remain unjudged.",
            "consistency_audit_changes": audit["changes"],
        },
        "queries": frozen_queries,
    }


def write_atomic(payload: dict[str, Any], output: Path, *, overwrite: bool) -> None:
    if output.exists() and not overwrite:
        raise QrelsFreezeError(f"Output already exists: {output}. Pass --overwrite to replace it.")
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
            json.dump(payload, temporary, ensure_ascii=False, indent=2)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, output)
    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--pool", type=Path, default=DEFAULT_POOL)
    parser.add_argument("--review", type=Path, default=DEFAULT_REVIEW)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload = freeze_qrels(args.corpus, args.pool, args.review)
        write_atomic(payload, args.output, overwrite=args.overwrite)
    except (OSError, QrelsFreezeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    judgment_count = sum(len(query["judgments"]) for query in payload["queries"])
    print(f"Wrote qrels version 2 with {judgment_count} judgments to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

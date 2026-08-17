#!/usr/bin/env python3
"""Validate a deployed Peptide-RAG app without paid calls by default."""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from typing import Any, Sequence
from urllib.parse import urlparse

import requests


DEFAULT_QUERY = "BPC 157 tissue regeneration"
HOSTILE_ORIGIN = "https://cross-origin-smoke.invalid"
STANDARD_REFUSAL = "Insufficient evidence in the retrieved research abstracts."
EXPECTED_SEARCH_LIMIT_PROBE = 30


class SmokeError(RuntimeError):
    """Raised when a deployment response violates the public contract."""


@dataclass(frozen=True)
class SmokeCheck:
    name: str
    status: str
    detail: str


def _base_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.query or parsed.fragment:
        raise SmokeError("base URL must be an absolute http(s) origin")
    return value.rstrip("/")


def _json_response(response: Any, expected_status: int, name: str) -> dict[str, Any]:
    if getattr(response, "status_code", None) != expected_status:
        raise SmokeError(
            f"{name} returned HTTP {getattr(response, 'status_code', 'unknown')}, "
            f"expected {expected_status}"
        )
    try:
        payload = response.json()
    except (TypeError, ValueError) as exc:
        raise SmokeError(f"{name} did not return JSON") from exc
    if not isinstance(payload, dict):
        raise SmokeError(f"{name} JSON must be an object")
    return payload


def _request(
    session: requests.Session,
    method: str,
    url: str,
    *,
    timeout: float,
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> Any:
    try:
        return session.request(
            method,
            url,
            json=body,
            headers=headers,
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise SmokeError(f"request failed for {url}: {type(exc).__name__}") from exc


def _reject_cross_origin(response: Any, name: str) -> None:
    headers = {str(key).casefold() for key in getattr(response, "headers", {})}
    if "access-control-allow-origin" in headers:
        raise SmokeError(f"{name} unexpectedly permits the hostile cross-origin probe")


def _smoke_with_client(
    base_url: str,
    *,
    client: requests.Session,
    timeout: float = 15.0,
    search_query: str = DEFAULT_QUERY,
    answer_query: str | None = None,
    refusal_query: str | None = None,
    confirm_paid: bool = False,
    check_rate_limit: bool = False,
) -> tuple[SmokeCheck, ...]:
    """Run public-contract checks and return a deterministic result summary."""

    origin = _base_url(base_url)
    if not math.isfinite(timeout) or timeout <= 0:
        raise SmokeError("timeout must be a positive finite number")
    if not isinstance(search_query, str) or not search_query.strip():
        raise SmokeError("search query must contain text")
    if (answer_query or refusal_query) and not confirm_paid:
        raise SmokeError("answer/refusal smoke calls require --confirm-paid")
    checks: list[SmokeCheck] = []

    health = _json_response(
        _request(client, "GET", f"{origin}/healthz", timeout=timeout),
        200,
        "healthz",
    )
    if health != {"status": "ok"}:
        raise SmokeError("healthz response does not match the release contract")
    checks.append(SmokeCheck("healthz", "pass", "service reports ok"))

    metrics_response = _request(
        client,
        "GET",
        f"{origin}/api/metrics",
        timeout=timeout,
        headers={"Origin": HOSTILE_ORIGIN},
    )
    metrics = _json_response(
        metrics_response,
        200,
        "metrics",
    )
    _reject_cross_origin(metrics_response, "metrics")
    if not isinstance(metrics.get("metrics"), dict) or "disclaimer" not in metrics:
        raise SmokeError("metrics response lacks metrics or disclaimer")
    checks.append(SmokeCheck("metrics", "pass", "metrics object and disclaimer present"))

    preflight_headers = {
        "Origin": HOSTILE_ORIGIN,
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    }
    for path in ("/api/search", "/api/answer"):
        preflight = _request(
            client,
            "OPTIONS",
            f"{origin}{path}",
            timeout=timeout,
            headers=preflight_headers,
        )
        status = getattr(preflight, "status_code", None)
        if not isinstance(status, int) or status >= 500:
            raise SmokeError(f"cross-origin preflight for {path} returned an invalid status")
        _reject_cross_origin(preflight, f"cross-origin preflight for {path}")
    checks.append(SmokeCheck("same_origin", "pass", "hostile GET and POST preflights denied"))

    search_response = _request(
        client,
        "POST",
        f"{origin}/api/search",
        timeout=timeout,
        body={"query": search_query, "mode": "bm25", "k": 3},
        headers={"Origin": HOSTILE_ORIGIN},
    )
    search = _json_response(search_response, 200, "BM25 search")
    results = search.get("results")
    if search.get("mode") != "bm25" or not isinstance(results, list) or not results:
        raise SmokeError("BM25 search returned no ranked results or changed mode")
    for expected_rank, item in enumerate(results, start=1):
        if (
            not isinstance(item, dict)
            or item.get("rank") != expected_rank
            or not isinstance(item.get("pmid"), str)
            or not item["pmid"]
            or not isinstance(item.get("title"), str)
            or isinstance(item.get("score"), bool)
            or not isinstance(item.get("score"), (int, float))
            or not math.isfinite(item["score"])
            or item.get("pubmed_url")
            != f"https://pubmed.ncbi.nlm.nih.gov/{item['pmid']}/"
        ):
            raise SmokeError("BM25 result violates the ranked-result contract")
    _reject_cross_origin(search_response, "BM25 search")
    attribution = search.get("attribution")
    if (
        not isinstance(attribution, str)
        or "National Center for Biotechnology Information" not in attribution
        or "NCBI" not in attribution
    ):
        raise SmokeError("BM25 search lacks NCBI attribution")
    checks.append(SmokeCheck("bm25_search", "pass", f"{len(results)} ranked results"))

    if answer_query:
        answer_response = _request(
            client,
            "POST",
            f"{origin}/api/answer",
            timeout=timeout,
            body={"query": answer_query, "mode": "hybrid", "k": 5},
            headers={"Origin": HOSTILE_ORIGIN},
        )
        answer = _json_response(
            answer_response,
            200,
            "grounded answer",
        )
        citations = answer.get("citations")
        if (
            not isinstance(answer.get("answer"), str)
            or not answer["answer"].strip()
            or answer.get("retrieval_only") is not False
            or answer.get("retrieval_mode") != "hybrid"
            or answer.get("retrieval_fallback") is not None
            or not isinstance(citations, list)
            or not citations
            or any(
                not isinstance(item, dict)
                or isinstance(item.get("citation_id"), bool)
                or not isinstance(item.get("citation_id"), int)
                or item["citation_id"] < 1
                or not isinstance(item.get("pmid"), str)
                or not isinstance(item.get("chunk_id"), str)
                or not item["chunk_id"]
                or not isinstance(item.get("title"), str)
                or item.get("pubmed_url")
                != f"https://pubmed.ncbi.nlm.nih.gov/{item['pmid']}/"
                for item in citations
            )
        ):
            raise SmokeError("answer response lacks a generated answer or bound citations")
        _reject_cross_origin(answer_response, "grounded answer")
        checks.append(SmokeCheck("grounded_answer", "pass", f"{len(citations)} citations"))

    if refusal_query:
        refusal_response = _request(
            client,
            "POST",
            f"{origin}/api/answer",
            timeout=timeout,
            body={"query": refusal_query, "mode": "hybrid", "k": 5},
            headers={"Origin": HOSTILE_ORIGIN},
        )
        refusal = _json_response(
            refusal_response,
            200,
            "refusal",
        )
        if (
            refusal.get("answer") is not None
            or refusal.get("retrieval_only") is not True
            or refusal.get("retrieval_mode") != "hybrid"
            or refusal.get("retrieval_fallback") is not None
            or refusal.get("refusal") != STANDARD_REFUSAL
            or "reason" in refusal
        ):
            raise SmokeError("unanswerable smoke query did not return the standard evidence refusal")
        _reject_cross_origin(refusal_response, "refusal")
        checks.append(SmokeCheck("refusal", "pass", "standard evidence refusal returned"))

    if check_rate_limit:
        limited_at: int | None = None
        for attempt in range(1, 36):
            response = _request(
                client,
                "POST",
                f"{origin}/api/search",
                timeout=timeout,
                body={"query": search_query, "mode": "bm25", "k": 1},
            )
            if getattr(response, "status_code", None) == 429:
                limited_at = attempt
                break
            if getattr(response, "status_code", None) != 200:
                raise SmokeError("rate-limit probe returned an unexpected status")
        if limited_at is None:
            raise SmokeError("search rate limit did not trigger within the expected window")
        if limited_at != EXPECTED_SEARCH_LIMIT_PROBE:
            raise SmokeError(
                "search rate limit triggered at an unexpected probe; wait at least "
                "60 seconds and verify the configured 30 requests/minute/IP limit"
            )
        checks.append(SmokeCheck("rate_limit", "pass", f"HTTP 429 at probe {limited_at}"))

    return tuple(checks)


def smoke(
    base_url: str,
    *,
    session: requests.Session | None = None,
    timeout: float = 15.0,
    search_query: str = DEFAULT_QUERY,
    answer_query: str | None = None,
    refusal_query: str | None = None,
    confirm_paid: bool = False,
    check_rate_limit: bool = False,
) -> tuple[SmokeCheck, ...]:
    """Run public-contract checks and close only sessions created here."""

    if (answer_query is None) != (refusal_query is None):
        raise SmokeError("paid smoke requires both --answer-query and --refusal-query")
    if answer_query is not None and (
        not isinstance(answer_query, str)
        or not answer_query.strip()
        or not isinstance(refusal_query, str)
        or not refusal_query.strip()
    ):
        raise SmokeError("paid smoke queries must both contain text")
    kwargs = {
        "timeout": timeout,
        "search_query": search_query,
        "answer_query": answer_query,
        "refusal_query": refusal_query,
        "confirm_paid": confirm_paid,
        "check_rate_limit": check_rate_limit,
    }
    if session is not None:
        return _smoke_with_client(base_url, client=session, **kwargs)
    with requests.Session() as client:
        return _smoke_with_client(base_url, client=client, **kwargs)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--search-query", default=DEFAULT_QUERY)
    parser.add_argument("--answer-query")
    parser.add_argument("--refusal-query")
    parser.add_argument("--confirm-paid", action="store_true")
    parser.add_argument("--check-rate-limit", action="store_true")
    args = parser.parse_args(argv)
    try:
        checks = smoke(
            args.base_url,
            timeout=args.timeout,
            search_query=args.search_query,
            answer_query=args.answer_query,
            refusal_query=args.refusal_query,
            confirm_paid=args.confirm_paid,
            check_rate_limit=args.check_rate_limit,
        )
    except SmokeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps([check.__dict__ for check in checks], sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

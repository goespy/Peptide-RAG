"""Local, research-only web interface for the peptide retrieval project."""

from __future__ import annotations

import asyncio
import inspect
import math
import os
from pathlib import Path
from collections import deque
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool


RESEARCH_DISCLAIMER = "Research use only. This tool does not provide medical advice."
NCBI_ATTRIBUTION = "Literature records and PubMed links are attributed to the National Center for Biotechnology Information (NCBI)."
STATIC_DIR = Path(__file__).with_name("static")


class SearchRequest(BaseModel):
    query: str = Field(..., max_length=500)
    mode: Literal["boolean", "bm25", "semantic", "hybrid"] = "bm25"
    k: int = Field(5, ge=1, le=20)


class AnswerRequest(BaseModel):
    query: str = Field(..., max_length=500)
    mode: Literal["lexical", "semantic", "hybrid"] = "hybrid"
    k: int = Field(5, ge=1, le=8)


class ResearchService(Protocol):
    def search(self, query: str, mode: str, k: int) -> Any: ...
    def answer(self, query: str, mode: str, k: int, evidence: list[dict[str, Any]]) -> Any: ...
    def metrics(self) -> Any: ...


class ProviderUnavailable(RuntimeError):
    """Raised by injected providers when an answer model cannot be used."""


class BudgetExceeded(RuntimeError):
    """Raised by injected providers when their own answer budget is exhausted."""


class LocalOnlyService:
    """Fallback used only if the checked-in local corpus cannot be loaded."""

    def search(self, query: str, mode: str, k: int) -> list[dict[str, Any]]:
        return []

    def answer(self, query: str, mode: str, k: int, evidence: list[dict[str, Any]]) -> dict[str, Any]:
        return {"answer": None, "refusal": "No answer provider is configured; showing retrieved evidence only."}

    def metrics(self) -> dict[str, Any]:
        return {"available": False, "message": "No evaluation metrics service is configured."}


class SlidingRateLimiter:
    def __init__(self) -> None:
        self._events: dict[str, deque[datetime]] = {}

    def allow(self, key: str, maximum: int, now: datetime | None = None) -> bool:
        now = now or datetime.now(UTC)
        window_start = now.timestamp() - 60
        for stored_key, stored_events in list(self._events.items()):
            while stored_events and stored_events[0].timestamp() <= window_start:
                stored_events.popleft()
            if not stored_events:
                del self._events[stored_key]
        events = self._events.setdefault(key, deque())
        while events and events[0].timestamp() <= window_start:
            events.popleft()
        if len(events) >= maximum:
            return False
        events.append(now)
        return True


def _utc_day() -> str:
    return datetime.now(UTC).date().isoformat()


def _environment_nonnegative_int(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError as exc:
        raise ValueError(f"{name} must be a non-negative integer") from exc
    if value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def _environment_daily_cap() -> int:
    return _environment_nonnegative_int("DAILY_ANSWER_CAP", 200)


def _environment_positive_float(name: str, default: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive finite number") from exc
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a positive finite number")
    return value


def _environment_trust_proxy() -> bool:
    return os.getenv("TRUST_PROXY_HEADERS", "false").casefold() in {"1", "true", "yes", "on"}


async def _call(method: Any, *args: Any) -> Any:
    if inspect.iscoroutinefunction(method):
        return await method(*args)
    result = await run_in_threadpool(method, *args)
    return await result if inspect.isawaitable(result) else result


def _evidence(items: Any) -> list[dict[str, Any]]:
    """Normalize injected retrieval output into conservative JSON evidence."""
    if isinstance(items, dict):
        items = items.get("results", items.get("evidence", []))
    if not isinstance(items, (list, tuple)):
        return []
    output: list[dict[str, Any]] = []
    for rank, item in enumerate(items, start=1):
        if isinstance(item, dict):
            value = item
        else:
            value = {name: getattr(item, name) for name in ("pmid", "title", "text", "snippet", "score", "chunk_id", "start_char", "end_char", "mode", "lexical_rank", "semantic_rank") if hasattr(item, name)}
        pmid = str(value.get("pmid", ""))
        text = value.get("snippet", value.get("text", ""))
        output.append({
            "rank": rank,
            "pmid": pmid,
            "title": str(value.get("title", "Untitled record")),
            "snippet": str(text),
            "score": value.get("score"),
            "chunk_id": str(value.get("chunk_id", "")),
            "start_char": value.get("start_char"),
            "end_char": value.get("end_char"),
            "mode": value.get("mode"),
            "lexical_rank": value.get("lexical_rank"),
            "semantic_rank": value.get("semantic_rank"),
            "pubmed_url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else None,
        })
    return output


def _require_query(query: str) -> str:
    if not query.strip():
        raise HTTPException(status_code=422, detail="query must contain non-whitespace text")
    return query


def create_app(
    service: ResearchService | None = None,
    *,
    daily_answer_cap: int | None = None,
    daily_embedding_cap: int | None = None,
    provider_concurrency_limit: int | None = None,
    provider_slot_timeout: float | None = None,
    trust_proxy_headers: bool | None = None,
) -> FastAPI:
    """Create an app with explicitly injected, local-safe service dependencies."""
    app = FastAPI(title="Peptide RAG", docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    if service is None:
        # Import lazily so injected-test services and a minimal web shell remain
        # usable even when a local corpus file has been intentionally removed.
        try:
            from src.service import LocalResearchService
            cache = os.getenv("EMBEDDING_CACHE_PATH")
            service = LocalResearchService(embedding_cache_path=Path(cache) if cache else None)
        except (OSError, ValueError):
            service = LocalOnlyService()
    app.state.service = service
    app.state.limiter = SlidingRateLimiter()
    app.state.answer_count = 0
    app.state.answer_day = _utc_day()
    app.state.daily_answer_cap = _environment_daily_cap() if daily_answer_cap is None else max(0, daily_answer_cap)
    app.state.embedding_count = 0
    app.state.embedding_day = _utc_day()
    app.state.daily_embedding_cap = (
        _environment_nonnegative_int("DAILY_EMBEDDING_CAP", 5000)
        if daily_embedding_cap is None
        else max(0, daily_embedding_cap)
    )
    concurrency = (
        _environment_nonnegative_int("PROVIDER_CONCURRENCY_LIMIT", 8)
        if provider_concurrency_limit is None
        else max(0, provider_concurrency_limit)
    )
    app.state.provider_semaphore = asyncio.Semaphore(concurrency)
    if provider_slot_timeout is None:
        provider_slot_timeout = _environment_positive_float(
            "PROVIDER_SLOT_TIMEOUT_SECONDS",
            0.1,
        )
    if (
        isinstance(provider_slot_timeout, bool)
        or not isinstance(provider_slot_timeout, (int, float))
        or not math.isfinite(provider_slot_timeout)
        or provider_slot_timeout <= 0
    ):
        raise ValueError("provider_slot_timeout must be a positive finite number")
    app.state.provider_slot_timeout = float(provider_slot_timeout)
    app.state.trust_proxy_headers = _environment_trust_proxy() if trust_proxy_headers is None else trust_proxy_headers

    def client_ip(request: Request) -> str:
        if app.state.trust_proxy_headers:
            forwarded = request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
            if forwarded:
                return forwarded
        return request.client.host if request.client else "unknown"

    def limited(request: Request, kind: str, maximum: int) -> None:
        # The key includes the operation; raw queries are intentionally never logged.
        if not app.state.limiter.allow(f"{kind}:{client_ip(request)}", maximum):
            raise HTTPException(status_code=429, detail="Rate limit exceeded. Please try again shortly.")

    def reset_daily_counters() -> None:
        today = _utc_day()
        if app.state.answer_day != today:
            app.state.answer_day, app.state.answer_count = today, 0
        if app.state.embedding_day != today:
            app.state.embedding_day, app.state.embedding_count = today, 0

    async def provider_call(method: Any, *args: Any) -> Any:
        try:
            await asyncio.wait_for(
                app.state.provider_semaphore.acquire(),
                timeout=app.state.provider_slot_timeout,
            )
        except TimeoutError as exc:
            raise ProviderUnavailable("provider concurrency limit reached") from exc
        try:
            return await _call(method, *args)
        finally:
            app.state.provider_semaphore.release()

    async def retrieve(
        query: str,
        mode: str,
        k: int,
        *,
        fallback_mode: str = "bm25",
    ) -> tuple[list[dict[str, Any]], str, str | None]:
        reset_daily_counters()
        if mode not in {"semantic", "hybrid"}:
            return _evidence(await _call(app.state.service.search, query, mode, k)), mode, None
        if app.state.embedding_count >= app.state.daily_embedding_cap:
            evidence = _evidence(
                await _call(app.state.service.search, query, fallback_mode, k)
            )
            return evidence, fallback_mode, "Daily query-embedding budget is exhausted."
        app.state.embedding_count += 1
        try:
            result = await provider_call(app.state.service.search, query, mode, k)
            return _evidence(result), mode, None
        except (BudgetExceeded, ProviderUnavailable, RuntimeError):
            evidence = _evidence(
                await _call(app.state.service.search, query, fallback_mode, k)
            )
            return evidence, fallback_mode, "Semantic retrieval is temporarily unavailable."

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/metrics")
    async def metrics() -> Any:
        service_metrics = getattr(app.state.service, "metrics", None)
        value = await _call(service_metrics) if service_metrics else {"available": False}
        return {"metrics": value, "disclaimer": RESEARCH_DISCLAIMER}

    @app.post("/api/search")
    async def search(payload: SearchRequest, request: Request) -> dict[str, Any]:
        limited(request, "search", 30)
        query = _require_query(payload.query)
        results, actual_mode, fallback_reason = await retrieve(
            query,
            payload.mode,
            payload.k,
        )
        return {
            "mode": actual_mode,
            "requested_mode": payload.mode,
            "fallback_reason": fallback_reason,
            "results": results,
            "disclaimer": RESEARCH_DISCLAIMER,
            "attribution": NCBI_ATTRIBUTION,
        }

    @app.post("/api/answer")
    async def answer(payload: AnswerRequest, request: Request) -> dict[str, Any]:
        limited(request, "answer", 5)
        query = _require_query(payload.query)
        reset_daily_counters()
        if app.state.answer_count >= app.state.daily_answer_cap:
            evidence = _evidence(
                await _call(app.state.service.search, query, "lexical", payload.k)
            )
            return {
                "answer": None,
                "retrieval_only": True,
                "reason": "Daily answer budget is exhausted.",
                "retrieval_mode": "lexical",
                "requested_mode": payload.mode,
                "evidence": evidence,
                "disclaimer": RESEARCH_DISCLAIMER,
                "attribution": NCBI_ATTRIBUTION,
            }
        # Reserve before any retrieval/provider await so concurrent requests
        # cannot all pass the daily-cap check together.
        app.state.answer_count += 1
        evidence, retrieval_mode, retrieval_fallback = await retrieve(
            query,
            payload.mode,
            payload.k,
            fallback_mode="lexical",
        )
        try:
            value = await provider_call(
                app.state.service.answer,
                query,
                retrieval_mode,
                payload.k,
                evidence,
            )
        except (BudgetExceeded, ProviderUnavailable, RuntimeError):
            return {
                "answer": None,
                "retrieval_only": True,
                "reason": "Answer generation is unavailable; showing retrieved evidence only.",
                "retrieval_mode": retrieval_mode,
                "requested_mode": payload.mode,
                "retrieval_fallback": retrieval_fallback,
                "evidence": evidence,
                "disclaimer": RESEARCH_DISCLAIMER,
                "attribution": NCBI_ATTRIBUTION,
            }
        if isinstance(value, str):
            value = {"answer": value}
        if not isinstance(value, dict):
            value = {"answer": None, "refusal": "Answer service returned no usable response."}
        return {
            **value,
            "retrieval_only": not bool(value.get("answer")),
            "retrieval_mode": retrieval_mode,
            "requested_mode": payload.mode,
            "retrieval_fallback": retrieval_fallback,
            "evidence": evidence,
            "disclaimer": RESEARCH_DISCLAIMER,
            "attribution": NCBI_ATTRIBUTION,
        }

    return app


app = create_app()

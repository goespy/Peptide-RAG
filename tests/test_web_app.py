"""Contract tests for the optional FastAPI web shell."""

import asyncio
import json
import time
import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from src.refusals import (
    BUDGET_LIMIT,
    INSUFFICIENT_EVIDENCE,
    MEDICAL_SAFETY,
    REFUSAL_MESSAGES,
    SERVICE_UNAVAILABLE,
)

try:
    from fastapi.testclient import TestClient
    from app import (
        BudgetExceeded,
        SlidingRateLimiter,
        _call,
        _safe_provider_failure_diagnostic,
        create_app,
    )
except ImportError:  # Standard-library test discovery works without web extras.
    TestClient = None
    BudgetExceeded = RuntimeError
    create_app = None
    SlidingRateLimiter = None
    _call = None
    _safe_provider_failure_diagnostic = None


class FakeService:
    def search(self, query, mode, k):
        return [{"pmid": "12345", "title": "<unsafe title>", "snippet": "Evidence text", "score": 1.0}]

    def answer(self, query, mode, k, evidence):
        return {"answer": "Evidence-backed summary.", "citations": ["12345"]}

    def metrics(self):
        return {"mrr": 0.5}


@unittest.skipIf(TestClient is None, "FastAPI/httpx are not installed")
class WebAppTests(unittest.TestCase):
    def test_provider_diagnostic_is_allowlisted_and_secret_free(self):
        class AnswerClient:
            model = "test/model"
            api_key = "sk-or-secret-value"
            last_metadata = {
                "provider_calls": 1,
                "provider": None,
                "final_outcome": "failed_closed_after_repair",
                "failure_reason": "request_or_response_error",
                "api_key": "must-not-log",
                "raw_output": "must-not-log",
                "attempts": [
                    {
                        "stage": "initial",
                        "http_status": 401,
                        "outcome": "request_or_response_error",
                        "provider_error_code": 401,
                        "provider_message": "must-not-log",
                    }
                ],
            }

        service = type("Service", (), {"answer_client": AnswerClient()})()
        diagnostic = _safe_provider_failure_diagnostic(service)
        rendered = json.dumps(diagnostic, sort_keys=True)
        self.assertIn('"http_status": 401', rendered)
        self.assertIn('"api_key_prefix_valid": true', rendered)
        self.assertNotIn("secret-value", rendered)
        self.assertNotIn("must-not-log", rendered)

    def test_invalid_budget_environment_fails_startup_visibly(self):
        with patch.dict("os.environ", {"PROVIDER_CONCURRENCY_LIMIT": "typo"}):
            with self.assertRaisesRegex(ValueError, "PROVIDER_CONCURRENCY_LIMIT"):
                create_app(FakeService())
        for value in ("0.5s", "-5", "nan"):
            with self.subTest(provider_slot_timeout=value), patch.dict(
                "os.environ",
                {"PROVIDER_SLOT_TIMEOUT_SECONDS": value},
            ):
                with self.assertRaisesRegex(ValueError, "PROVIDER_SLOT_TIMEOUT_SECONDS"):
                    create_app(FakeService())

    def test_health_static_metrics_and_search_contract(self):
        client = TestClient(create_app(FakeService()))
        self.assertEqual(client.get("/healthz").json(), {"status": "ok"})
        self.assertIn("Peptide literature explorer", client.get("/").text)
        self.assertEqual(client.get("/api/metrics").json()["metrics"], {"mrr": 0.5})
        response = client.post("/api/search", json={"query": "peptide", "mode": "bm25", "k": 2})
        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["results"][0]["rank"], 1)
        self.assertEqual(body["results"][0]["score"], 1.0)
        self.assertEqual(body["results"][0]["pubmed_url"], "https://pubmed.ncbi.nlm.nih.gov/12345/")
        self.assertIn("medical advice", body["disclaimer"])
        self.assertNotIn("access-control-allow-origin", response.headers)
        script = client.get("/static/app.js").text
        self.assertIn('details.push(`Rank ${item.rank}`)', script)
        self.assertIn('details.push(`Score ${item.score.toFixed(6)}`)', script)
        self.assertIn('medical_safety: "Medical-safety refusal"', script)
        self.assertIn('service_unavailable: "Service unavailable"', script)

    def test_validation_and_answer_fallback_preserve_evidence(self):
        class Failing(FakeService):
            def answer(self, *args):
                raise BudgetExceeded()

        client = TestClient(create_app(Failing()))
        self.assertEqual(client.post("/api/search", json={"query": "x" * 501}).status_code, 422)
        self.assertEqual(client.post("/api/search", json={"query": " ", "mode": "hybrid"}).status_code, 422)
        response = client.post("/api/answer", json={"query": "peptide", "mode": "hybrid", "k": 1})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["retrieval_only"])
        self.assertEqual(response.json()["evidence"][0]["pmid"], "12345")
        self.assertEqual(response.json()["refusal_reason"], SERVICE_UNAVAILABLE)
        self.assertEqual(
            response.json()["refusal"], REFUSAL_MESSAGES[SERVICE_UNAVAILABLE]
        )

        capped_client = TestClient(create_app(Failing(), daily_answer_cap=1))
        self.assertTrue(capped_client.post("/api/answer", json={"query": "first"}).json()["retrieval_only"])
        capped = capped_client.post("/api/answer", json={"query": "second"}).json()
        self.assertEqual(capped["reason"], "Daily answer budget is exhausted.")
        self.assertEqual(capped["refusal_reason"], BUDGET_LIMIT)
        self.assertEqual(capped["refusal"], REFUSAL_MESSAGES[BUDGET_LIMIT])

        class UnknownRefusalSource(FakeService):
            def answer(self, *args):
                return {
                    "answer": None,
                    "refusal": "Insufficient evidence.",
                    "refusal_source": "untrusted",
                    "citations": [],
                }

        refusal = TestClient(create_app(UnknownRefusalSource())).post(
            "/api/answer",
            json={"query": "peptide", "mode": "hybrid", "k": 1},
        ).json()
        self.assertEqual(refusal["refusal_source"], "failed_closed")
        self.assertEqual(refusal["refusal_reason"], SERVICE_UNAVAILABLE)
        self.assertEqual(refusal["refusal"], REFUSAL_MESSAGES[SERVICE_UNAVAILABLE])

        class CategorizedRefusal(FakeService):
            def __init__(self, reason, source):
                self.reason = reason
                self.source = source

            def answer(self, *args):
                return {
                    "answer": None,
                    "refusal": REFUSAL_MESSAGES[self.reason],
                    "refusal_reason": self.reason,
                    "refusal_source": self.source,
                    "citations": [],
                }

        for reason, source in (
            (MEDICAL_SAFETY, "failed_closed"),
            (INSUFFICIENT_EVIDENCE, "model"),
        ):
            with self.subTest(reason=reason):
                categorized = TestClient(
                    create_app(CategorizedRefusal(reason, source))
                ).post(
                    "/api/answer",
                    json={"query": "peptide", "mode": "hybrid", "k": 1},
                ).json()
                self.assertEqual(categorized["refusal_reason"], reason)
                self.assertEqual(categorized["refusal"], REFUSAL_MESSAGES[reason])

    def test_answer_endpoint_retrieves_evidence_once(self):
        class Counting(FakeService):
            def __init__(self): self.search_calls = 0
            def search(self, query, mode, k):
                self.search_calls += 1
                return super().search(query, mode, k)
        service = Counting()
        client = TestClient(create_app(service))
        self.assertEqual(client.post("/api/answer", json={"query": "peptide", "mode": "hybrid", "k": 1}).status_code, 200)
        self.assertEqual(service.search_calls, 1)

    def test_embedding_budget_and_provider_saturation_fall_back_explicitly(self):
        class Recording(FakeService):
            def __init__(self):
                self.modes = []

            def search(self, query, mode, k):
                self.modes.append(mode)
                return super().search(query, mode, k)

        budgeted = Recording()
        client = TestClient(create_app(budgeted, daily_embedding_cap=1))
        first = client.post(
            "/api/search",
            json={"query": "first", "mode": "semantic", "k": 1},
        ).json()
        second = client.post(
            "/api/search",
            json={"query": "second", "mode": "hybrid", "k": 1},
        ).json()
        self.assertEqual(first["mode"], "semantic")
        self.assertEqual(second["requested_mode"], "hybrid")
        self.assertEqual(second["mode"], "bm25")
        self.assertIn("budget", second["fallback_reason"].lower())
        self.assertEqual(budgeted.modes, ["semantic", "bm25"])

        saturated = Recording()
        saturated_client = TestClient(
            create_app(
                saturated,
                provider_concurrency_limit=0,
                provider_slot_timeout=0.001,
            )
        )
        body = saturated_client.post(
            "/api/search",
            json={"query": "peptide", "mode": "semantic", "k": 1},
        ).json()
        self.assertEqual(body["mode"], "bm25")
        self.assertIn("unavailable", body["fallback_reason"].lower())
        self.assertEqual(saturated.modes, ["bm25"])

    def test_exhausted_answer_budget_avoids_paid_retrieval(self):
        class Recording(FakeService):
            def __init__(self):
                self.modes = []

            def search(self, query, mode, k):
                self.modes.append(mode)
                return super().search(query, mode, k)

        service = Recording()
        client = TestClient(create_app(service, daily_answer_cap=0))
        body = client.post(
            "/api/answer",
            json={"query": "peptide", "mode": "hybrid", "k": 1},
        ).json()
        self.assertTrue(body["retrieval_only"])
        self.assertEqual(body["retrieval_mode"], "lexical")
        self.assertEqual(service.modes, ["lexical"])

    def test_rate_and_daily_answer_limits(self):
        client = TestClient(create_app(FakeService(), daily_answer_cap=1))
        self.assertEqual(client.post("/api/answer", json={"query": "one"}).status_code, 200)
        capped = client.post("/api/answer", json={"query": "two"})
        self.assertEqual(capped.status_code, 200)
        self.assertTrue(capped.json()["retrieval_only"])
        rate_client = TestClient(create_app(FakeService()))
        for _ in range(30):
            self.assertEqual(rate_client.post("/api/search", json={"query": "peptide"}).status_code, 200)
        self.assertEqual(rate_client.post("/api/search", json={"query": "peptide"}).status_code, 429)

    def test_trusted_proxy_addresses_have_independent_limits(self):
        client = TestClient(create_app(FakeService(), trust_proxy_headers=True))
        for _ in range(30):
            self.assertEqual(client.post("/api/search", json={"query": "peptide"}, headers={"x-forwarded-for":"198.51.100.1"}).status_code, 200)
        self.assertEqual(client.post("/api/search", json={"query": "peptide"}, headers={"x-forwarded-for":"198.51.100.1"}).status_code, 429)
        self.assertEqual(client.post("/api/search", json={"query": "peptide"}, headers={"x-forwarded-for":"198.51.100.2"}).status_code, 200)

    def test_rate_limiter_prunes_expired_client_keys(self):
        limiter = SlidingRateLimiter(); start = datetime(2026, 1, 1, tzinfo=UTC)
        self.assertTrue(limiter.allow("search:first", 1, start))
        self.assertTrue(limiter.allow("search:second", 1, start + timedelta(seconds=61)))
        self.assertNotIn("search:first", limiter._events)


@unittest.skipIf(_call is None, "FastAPI/Starlette are not installed")
class AsyncBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_sync_provider_work_does_not_block_the_event_loop(self):
        task = asyncio.create_task(_call(lambda: time.sleep(0.05)))
        await asyncio.sleep(0.01)
        self.assertFalse(task.done())
        await task

    async def test_daily_answer_cap_is_reserved_before_retrieval_await(self):
        import httpx

        class SlowService(FakeService):
            def __init__(self):
                self.answer_calls = 0

            def search(self, query, mode, k):
                if mode == "hybrid":
                    time.sleep(0.05)
                return super().search(query, mode, k)

            def answer(self, query, mode, k, evidence):
                self.answer_calls += 1
                return super().answer(query, mode, k, evidence)

        service = SlowService()
        transport = httpx.ASGITransport(
            app=create_app(service, daily_answer_cap=1)
        )
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            first, second = await asyncio.gather(
                client.post(
                    "/api/answer",
                    json={"query": "first", "mode": "hybrid", "k": 1},
                ),
                client.post(
                    "/api/answer",
                    json={"query": "second", "mode": "hybrid", "k": 1},
                ),
            )
        bodies = [first.json(), second.json()]
        self.assertEqual(service.answer_calls, 1)
        self.assertEqual(
            sum(body.get("reason") == "Daily answer budget is exhausted." for body in bodies),
            1,
        )

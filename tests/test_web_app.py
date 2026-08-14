"""Contract tests for the optional FastAPI web shell."""

import unittest
from datetime import UTC, datetime, timedelta

try:
    from fastapi.testclient import TestClient
    from app import BudgetExceeded, SlidingRateLimiter, create_app
except ImportError:  # Standard-library test discovery works without web extras.
    TestClient = None
    BudgetExceeded = RuntimeError
    create_app = None
    SlidingRateLimiter = None


class FakeService:
    def search(self, query, mode, k):
        return [{"pmid": "12345", "title": "<unsafe title>", "snippet": "Evidence text", "score": 1.0}]

    def answer(self, query, mode, k, evidence):
        return {"answer": "Evidence-backed summary.", "citations": ["12345"]}

    def metrics(self):
        return {"mrr": 0.5}


@unittest.skipIf(TestClient is None, "FastAPI/httpx are not installed")
class WebAppTests(unittest.TestCase):
    def test_health_static_metrics_and_search_contract(self):
        client = TestClient(create_app(FakeService()))
        self.assertEqual(client.get("/healthz").json(), {"status": "ok"})
        self.assertIn("Peptide literature explorer", client.get("/").text)
        self.assertEqual(client.get("/api/metrics").json()["metrics"], {"mrr": 0.5})
        response = client.post("/api/search", json={"query": "peptide", "mode": "bm25", "k": 2})
        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["results"][0]["pubmed_url"], "https://pubmed.ncbi.nlm.nih.gov/12345/")
        self.assertIn("medical advice", body["disclaimer"])
        self.assertNotIn("access-control-allow-origin", response.headers)

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

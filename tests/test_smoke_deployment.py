import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.smoke_deployment import HOSTILE_ORIGIN, SmokeError, smoke


class Response:
    def __init__(self, status_code, payload, headers=None):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}

    def json(self):
        return self._payload


class Session:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def request(self, method, url, *, json, headers, timeout):
        self.requests.append((method, url, json, headers, timeout))
        return self.responses.pop(0)


def ranked_search():
    return {
        "mode": "bm25",
        "attribution": (
            "Literature records and PubMed links are attributed to the "
            "National Center for Biotechnology Information (NCBI)."
        ),
        "results": [{
            "rank": 1,
            "pmid": "123",
            "title": "Measured result",
            "score": 0.5,
            "pubmed_url": "https://pubmed.ncbi.nlm.nih.gov/123/",
        }],
    }


def free_responses(*, metrics_headers=None, search_headers=None, preflight_headers=None):
    return [
        Response(200, {"status": "ok"}),
        Response(
            200,
            {"metrics": {"available": True}, "disclaimer": "research"},
            headers=metrics_headers,
        ),
        Response(405, {}, headers=preflight_headers),
        Response(405, {}, headers=preflight_headers),
        Response(200, ranked_search(), headers=search_headers),
    ]


class DeploymentSmokeTests(unittest.TestCase):
    def _qa_path(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        questions = []
        for index in range(1, 21):
            development = index <= 10 or 16 <= index <= 18
            answerable = index <= 15
            question = f"Development answerable {index}?"
            if index == 1:
                question = "answerable"
            elif index == 16:
                question = "unanswerable"
            questions.append({
                "id": f"qa{index:02d}",
                "question": question,
                "answerable": answerable,
                "split": "development" if development else "holdout",
            })
        path = Path(directory.name) / "qa.json"
        path.write_text(
            json.dumps({"status": "approved", "questions": questions}),
            encoding="utf-8",
        )
        return path

    def test_default_smoke_is_retrieval_only(self):
        session = Session(free_responses())
        checks = smoke("https://example.test/", session=session)
        self.assertEqual(
            [item.name for item in checks],
            ["healthz", "metrics", "same_origin", "bm25_search"],
        )
        self.assertEqual(len(session.requests), 5)
        self.assertEqual(session.requests[-1][2]["mode"], "bm25")
        self.assertEqual(
            session.requests[-1][3],
            {"Origin": HOSTILE_ORIGIN},
        )
        self.assertEqual(session.requests[2][0], "OPTIONS")
        self.assertEqual(session.requests[3][1], "https://example.test/api/answer")

    def test_paid_answer_and_refusal_require_confirmation_and_validate_contract(self):
        session = Session([])
        qa_path = self._qa_path()
        with self.assertRaisesRegex(SmokeError, "confirm-paid"):
            smoke(
                "https://example.test",
                session=session,
                answer_query="answer",
                refusal_query="refusal",
                qa_path=qa_path,
            )
        self.assertEqual(session.requests, [])

        with self.assertRaisesRegex(SmokeError, "requires both"):
            smoke(
                "https://example.test",
                session=session,
                answer_query="answer",
                confirm_paid=True,
                qa_path=qa_path,
            )
        with self.assertRaisesRegex(SmokeError, "must both contain text"):
            smoke(
                "https://example.test",
                session=session,
                answer_query=" ",
                refusal_query="unanswerable",
                confirm_paid=True,
                qa_path=qa_path,
            )

        session = Session([
            *free_responses(),
            Response(200, {
                "answer": "Supported finding. [1]",
                "retrieval_only": False,
                "retrieval_mode": "hybrid",
                "retrieval_fallback": None,
                "citations": [{
                    "citation_id": 1,
                    "pmid": "123",
                    "chunk_id": "123:c0001",
                    "title": "Measured result",
                    "pubmed_url": "https://pubmed.ncbi.nlm.nih.gov/123/",
                }],
            }),
            Response(200, {
                "answer": None,
                "retrieval_only": True,
                "retrieval_mode": "hybrid",
                "retrieval_fallback": None,
                "refusal": "Insufficient evidence in the retrieved research abstracts.",
                "refusal_source": "model",
                "citations": [],
            }),
        ])
        checks = smoke(
            "https://example.test",
            session=session,
            answer_query="answerable",
            refusal_query="unanswerable",
            confirm_paid=True,
            qa_path=qa_path,
        )
        self.assertEqual(checks[-2].name, "grounded_answer")
        self.assertEqual(checks[-1].name, "refusal")

        outage = Session([
            *free_responses(),
            Response(200, {
                "answer": "Supported finding. [1]",
                "retrieval_only": False,
                "retrieval_mode": "hybrid",
                "retrieval_fallback": None,
                "citations": [{
                    "citation_id": 1,
                    "pmid": "123",
                    "chunk_id": "123:c0001",
                    "title": "Measured result",
                    "pubmed_url": "https://pubmed.ncbi.nlm.nih.gov/123/",
                }],
            }),
            Response(200, {
                "answer": None,
                "retrieval_only": True,
                "retrieval_mode": "hybrid",
                "retrieval_fallback": None,
                "reason": "Answer generation is unavailable.",
            }),
        ])
        with self.assertRaisesRegex(SmokeError, "model-originated evidence refusal"):
            smoke(
                "https://example.test",
                session=outage,
                answer_query="answerable",
                refusal_query="unanswerable",
                confirm_paid=True,
                qa_path=qa_path,
            )

        per_query_fail_close = Session([
            *free_responses(),
            Response(200, {
                "answer": "Supported finding. [1]",
                "retrieval_only": False,
                "retrieval_mode": "hybrid",
                "retrieval_fallback": None,
                "citations": [{
                    "citation_id": 1,
                    "pmid": "123",
                    "chunk_id": "123:c0001",
                    "title": "Measured result",
                    "pubmed_url": "https://pubmed.ncbi.nlm.nih.gov/123/",
                }],
            }),
            Response(200, {
                "answer": None,
                "retrieval_only": True,
                "retrieval_mode": "hybrid",
                "retrieval_fallback": None,
                "refusal": "Insufficient evidence in the retrieved research abstracts.",
                "refusal_source": "failed_closed",
                "citations": [],
            }),
        ])
        with self.assertRaisesRegex(SmokeError, "model-originated evidence refusal"):
            smoke(
                "https://example.test",
                session=per_query_fail_close,
                answer_query="answerable",
                refusal_query="unanswerable",
                confirm_paid=True,
                qa_path=qa_path,
            )

        with self.assertRaisesRegex(SmokeError, "approved development QA"):
            smoke(
                "https://example.test",
                session=Session([]),
                answer_query="holdout or invented answer",
                refusal_query="unanswerable",
                confirm_paid=True,
                qa_path=qa_path,
            )

    def test_rejects_bad_origin_ranked_result_and_missing_rate_limit(self):
        with self.assertRaises(SmokeError):
            smoke("not-a-url", session=Session([]))
        bad_search = ranked_search()
        bad_search["results"][0]["score"] = float("nan")
        bad_ranked_responses = free_responses()
        bad_ranked_responses[-1] = Response(200, bad_search)
        session = Session(bad_ranked_responses)
        with self.assertRaisesRegex(SmokeError, "ranked-result"):
            smoke("https://example.test", session=session)

        session = Session(
            free_responses(preflight_headers={"Access-Control-Allow-Origin": "*"})
        )
        with self.assertRaisesRegex(SmokeError, "cross-origin"):
            smoke("https://example.test", session=session)

        responses = [
            *free_responses(),
            *[Response(200, ranked_search()) for _ in range(35)],
        ]
        with self.assertRaisesRegex(SmokeError, "rate limit"):
            smoke(
                "https://example.test",
                session=Session(responses),
                check_rate_limit=True,
            )

        early_limit = Session([
            *free_responses(),
            Response(429, {}),
        ])
        with self.assertRaisesRegex(SmokeError, "unexpected probe"):
            smoke(
                "https://example.test",
                session=early_limit,
                check_rate_limit=True,
            )

        expected_limit = Session([
            *free_responses(),
            *[Response(200, ranked_search()) for _ in range(29)],
            Response(429, {}),
        ])
        checks = smoke(
            "https://example.test",
            session=expected_limit,
            check_rate_limit=True,
        )
        self.assertEqual(checks[-1].detail, "HTTP 429 at probe 30")


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from typing import Any
from unittest.mock import patch

from scripts.fetch_pubmed import (
    EFETCH_URL,
    ESEARCH_URL,
    MAX_BATCH_SIZE,
    MAX_RETMAX,
    MIN_REQUEST_DELAY_SECONDS,
    QUERY,
    CorpusFetchError,
    CorpusRecord,
    RateLimiter,
    build_parser,
    fetch_and_write,
    fetch_records,
    main,
    parse_pubmed_xml,
    request_with_retries,
    search_pubmed,
    write_jsonl_atomic,
)


def article_xml(
    pmid: str,
    *,
    title: str = "Example title",
    abstract: str | None = "Example abstract",
) -> str:
    abstract_xml = ""
    if abstract is not None:
        abstract_xml = f"<Abstract><AbstractText>{abstract}</AbstractText></Abstract>"
    return (
        "<PubmedArticle><MedlineCitation>"
        f"<PMID>{pmid}</PMID><Article><ArticleTitle>{title}</ArticleTitle>"
        f"{abstract_xml}</Article></MedlineCitation></PubmedArticle>"
    )


def document_xml(*articles: str) -> bytes:
    return f"<PubmedArticleSet>{''.join(articles)}</PubmedArticleSet>".encode()


class FakeResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        json_data: Any = None,
        content: bytes = b"",
        text: str = "",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self._json_data = json_data
        self.content = content
        self.text = text
        self.headers = headers or {}

    def json(self) -> Any:
        if isinstance(self._json_data, Exception):
            raise self._json_data
        return self._json_data


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []
        self.headers: dict[str, str] = {}

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"method": method, "url": url, **kwargs})
        if not self.responses:
            raise AssertionError("No fake response remains")
        return self.responses.pop(0)

    def close(self) -> None:
        return None


def limiter() -> RateLimiter:
    return RateLimiter(sleep=lambda _: None, clock=lambda: 0.0)


class PubMedParsingTests(unittest.TestCase):
    def test_mixed_title_sections_unicode_and_whitespace_are_normalized(self) -> None:
        xml = b"""<PubmedArticleSet><PubmedArticle><MedlineCitation>
        <PMID>123</PMID><Article>
        <ArticleTitle>Effects of <i>BPC-157</i>\ttherapy</ArticleTitle>
        <Abstract>
          <AbstractText Label="BACKGROUND">A &amp; B\nwere studied.</AbstractText>
          <AbstractText NlmCategory="METHODS">Dose <sup>2</sup> was \xef\xbc\x91 mg.</AbstractText>
        </Abstract>
        </Article></MedlineCitation></PubmedArticle></PubmedArticleSet>"""

        record = parse_pubmed_xml(xml)["123"]

        self.assertEqual(record.title, "Effects of BPC-157 therapy")
        self.assertEqual(
            record.text,
            "BACKGROUND: A & B were studied. METHODS: Dose 2 was 1 mg.",
        )

    def test_title_only_record_is_kept(self) -> None:
        record = parse_pubmed_xml(document_xml(article_xml("7", abstract=None)))["7"]
        self.assertEqual(record, CorpusRecord("7", "Example title", ""))

    def test_book_record_falls_back_to_book_title(self) -> None:
        xml = b"""<PubmedArticleSet><PubmedBookArticle><BookDocument>
        <PMID>30896905</PMID>
        <Book><BookTitle>Pharmacoeconomic Review Report: Tesamorelin</BookTitle></Book>
        <Abstract><AbstractText Label="Excerpt">Review content.</AbstractText></Abstract>
        </BookDocument></PubmedBookArticle></PubmedArticleSet>"""

        record = parse_pubmed_xml(xml)["30896905"]

        self.assertEqual(
            record.title, "Pharmacoeconomic Review Report: Tesamorelin"
        )
        self.assertEqual(record.text, "Excerpt: Review content.")

    def test_duplicate_pmid_keeps_first_record(self) -> None:
        records = parse_pubmed_xml(
            document_xml(
                article_xml("7", title="First"),
                article_xml("7", title="Second"),
            )
        )
        self.assertEqual(records["7"].title, "First")

    def test_empty_or_malformed_xml_fails(self) -> None:
        for content in (b"", b"<not-closed>", b"<PubmedArticleSet />"):
            with self.subTest(content=content):
                with self.assertRaises(CorpusFetchError):
                    parse_pubmed_xml(content)


class PubMedRequestTests(unittest.TestCase):
    def test_esearch_uses_exact_query_parameters_and_hard_cap(self) -> None:
        session = FakeSession(
            [FakeResponse(json_data={"esearchresult": {"idlist": ["3", "2", "3"]}})]
        )
        pmids = search_pubmed(
            session, email="dev@example.com", api_key="key", retmax=MAX_RETMAX, limiter=limiter()
        )

        self.assertEqual(pmids, ["3", "2"])
        call = session.calls[0]
        self.assertEqual(call["method"], "GET")
        self.assertEqual(call["url"], ESEARCH_URL)
        self.assertEqual(
            call["params"],
            {
                "db": "pubmed",
                "term": QUERY,
                "retmode": "json",
                "retmax": "3000",
                "sort": "relevance",
                "tool": "peptide_rag",
                "email": "dev@example.com",
                "api_key": "key",
            },
        )
        with self.assertRaises(ValueError):
            search_pubmed(
                session,
                email="dev@example.com",
                api_key=None,
                retmax=MAX_RETMAX + 1,
                limiter=limiter(),
            )

    def test_esearch_never_accepts_more_than_requested(self) -> None:
        returned_ids = [str(index) for index in range(MAX_RETMAX + 50)]
        session = FakeSession(
            [FakeResponse(json_data={"esearchresult": {"idlist": returned_ids}})]
        )

        pmids = search_pubmed(
            session,
            email="dev@example.com",
            api_key=None,
            retmax=MAX_RETMAX,
            limiter=limiter(),
        )

        self.assertEqual(len(pmids), MAX_RETMAX)
        self.assertEqual(pmids[-1], str(MAX_RETMAX - 1))

    def test_cli_rejects_retmax_above_hard_cap(self) -> None:
        with redirect_stderr(StringIO()):
            with self.assertRaises(SystemExit) as context:
                build_parser().parse_args(
                    ["--email", "dev@example.com", "--retmax", str(MAX_RETMAX + 1)]
                )
        self.assertEqual(context.exception.code, 2)

    def test_empty_and_malformed_esearch_responses_fail(self) -> None:
        payloads = [None, {}, {"esearchresult": {}}, {"esearchresult": {"idlist": []}}]
        for payload in payloads:
            with self.subTest(payload=payload):
                session = FakeSession([FakeResponse(json_data=payload)])
                with self.assertRaises(CorpusFetchError):
                    search_pubmed(
                        session,
                        email="dev@example.com",
                        api_key=None,
                        retmax=1,
                        limiter=limiter(),
                    )

    def test_efetch_posts_batches_of_at_most_two_hundred_and_restores_order(self) -> None:
        pmids = [str(index) for index in range(401, 0, -1)]
        batches = [pmids[:200], pmids[200:400], pmids[400:]]
        responses = [
            FakeResponse(content=document_xml(*(article_xml(pmid) for pmid in reversed(batch))))
            for batch in batches
        ]
        session = FakeSession(responses)

        records = fetch_records(
            session,
            pmids,
            email="dev@example.com",
            api_key=None,
            batch_size=MAX_BATCH_SIZE,
            limiter=limiter(),
        )

        self.assertEqual([record.id for record in records], pmids)
        self.assertEqual(len(session.calls), 3)
        for call in session.calls:
            self.assertEqual(call["method"], "POST")
            self.assertEqual(call["url"], EFETCH_URL)
            self.assertLessEqual(len(call["data"]["id"].split(",")), MAX_BATCH_SIZE)

    def test_rate_limiter_sleeps_between_request_starts(self) -> None:
        class FakeClock:
            now = 0.0

            def __call__(self) -> float:
                return self.now

        clock = FakeClock()
        sleeps: list[float] = []

        def sleep(seconds: float) -> None:
            sleeps.append(seconds)
            clock.now += seconds

        rate_limiter = RateLimiter(sleep=sleep, clock=clock)
        rate_limiter.wait()
        rate_limiter.wait()

        self.assertEqual(len(sleeps), 1)
        self.assertAlmostEqual(sleeps[0], MIN_REQUEST_DELAY_SECONDS)

    def test_transient_retry_honors_retry_after(self) -> None:
        session = FakeSession(
            [
                FakeResponse(status_code=429, headers={"Retry-After": "3"}),
                FakeResponse(status_code=200),
            ]
        )
        sleeps: list[float] = []

        response = request_with_retries(
            session,  # type: ignore[arg-type]
            "GET",
            ESEARCH_URL,
            limiter=limiter(),
            max_attempts=2,
            sleep=sleeps.append,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(sleeps, [3.0])


class CorpusOutputTests(unittest.TestCase):
    def test_jsonl_has_exact_keys_and_requires_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "data" / "corpus.jsonl"
            records = [CorpusRecord("1", "Title", "Abstract")]
            write_jsonl_atomic(records, output, overwrite=False)

            parsed = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(parsed, {"id": "1", "title": "Title", "text": "Abstract"})
            self.assertEqual(list(parsed), ["id", "title", "text"])
            with self.assertRaises(CorpusFetchError):
                write_jsonl_atomic(records, output, overwrite=False)

            replacement = [CorpusRecord("2", "New", "")]
            write_jsonl_atomic(replacement, output, overwrite=True)
            self.assertEqual(json.loads(output.read_text())["id"], "2")

    def test_failed_fetch_leaves_final_output_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "corpus.jsonl"
            session = FakeSession(
                [
                    FakeResponse(json_data={"esearchresult": {"idlist": ["1"]}}),
                    FakeResponse(content=b"<malformed>"),
                ]
            )

            with self.assertRaises(CorpusFetchError):
                fetch_and_write(
                    session,  # type: ignore[arg-type]
                    email="dev@example.com",
                    api_key=None,
                    retmax=1,
                    batch_size=MAX_BATCH_SIZE,
                    output=output,
                    overwrite=False,
                    limiter=limiter(),
                )

            self.assertFalse(output.exists())

    def test_malformed_api_response_returns_nonzero_without_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "corpus.jsonl"
            session = FakeSession([FakeResponse(json_data={})])

            with patch("scripts.fetch_pubmed.requests.Session", return_value=session):
                with redirect_stderr(StringIO()):
                    exit_code = main(
                        [
                            "--email",
                            "dev@example.com",
                            "--retmax",
                            "1",
                            "--output",
                            str(output),
                        ]
                    )

            self.assertEqual(exit_code, 1)
            self.assertFalse(output.exists())

    def test_failed_overwrite_preserves_existing_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "corpus.jsonl"
            output.write_text("original\n", encoding="utf-8")
            session = FakeSession(
                [
                    FakeResponse(json_data={"esearchresult": {"idlist": ["1"]}}),
                    FakeResponse(content=b""),
                ]
            )

            with self.assertRaises(CorpusFetchError):
                fetch_and_write(
                    session,  # type: ignore[arg-type]
                    email="dev@example.com",
                    api_key=None,
                    retmax=1,
                    batch_size=MAX_BATCH_SIZE,
                    output=output,
                    overwrite=True,
                    limiter=limiter(),
                )

            self.assertEqual(output.read_text(encoding="utf-8"), "original\n")

    def test_existing_output_is_rejected_before_network_requests(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "corpus.jsonl"
            output.write_text("original\n", encoding="utf-8")
            session = FakeSession([])

            with self.assertRaises(CorpusFetchError):
                fetch_and_write(
                    session,  # type: ignore[arg-type]
                    email="dev@example.com",
                    api_key=None,
                    retmax=1,
                    batch_size=MAX_BATCH_SIZE,
                    output=output,
                    overwrite=False,
                    limiter=limiter(),
                )

            self.assertEqual(session.calls, [])
            self.assertEqual(output.read_text(encoding="utf-8"), "original\n")


if __name__ == "__main__":
    unittest.main()

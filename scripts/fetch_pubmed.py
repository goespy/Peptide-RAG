#!/usr/bin/env python3
"""Build a therapeutic-peptide PubMed corpus with NCBI E-utilities."""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import tempfile
import time
import unicodedata
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import requests


QUERY = (
    '(BPC-157 OR "Body Protection Compound-157" OR GHK-Cu OR TB-500 OR '
    '"Thymosin Beta-4" OR Ipamorelin OR Tesamorelin OR Epitalon OR MOTS-c '
    'OR "PT-141")'
)
ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
TOOL_NAME = "peptide_rag"
MAX_RETMAX = 3_000
MAX_BATCH_SIZE = 200
MIN_REQUEST_DELAY_SECONDS = 0.34
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_ATTEMPTS = 5
TRANSIENT_HTTP_STATUSES = {429, 500, 502, 503, 504}


class CorpusFetchError(RuntimeError):
    """Raised when the corpus cannot be fetched or validated safely."""


@dataclass(frozen=True)
class CorpusRecord:
    """The exact record shape written to corpus.jsonl."""

    id: str
    title: str
    text: str

    def as_dict(self) -> dict[str, str]:
        return {"id": self.id, "title": self.title, "text": self.text}


class RateLimiter:
    """Enforce a minimum delay between request start times."""

    def __init__(
        self,
        delay_seconds: float = MIN_REQUEST_DELAY_SECONDS,
        *,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if delay_seconds < MIN_REQUEST_DELAY_SECONDS:
            raise ValueError(
                f"delay_seconds must be at least {MIN_REQUEST_DELAY_SECONDS}"
            )
        self.delay_seconds = delay_seconds
        self._sleep = sleep
        self._clock = clock
        self._last_request_at: float | None = None

    def wait(self) -> None:
        now = self._clock()
        if self._last_request_at is not None:
            remaining = self.delay_seconds - (now - self._last_request_at)
            if remaining > 0:
                self._sleep(remaining)
                now = self._clock()
        self._last_request_at = now


def normalize_text(value: str) -> str:
    """Normalize Unicode and whitespace without changing case or wording."""

    normalized = unicodedata.normalize("NFKC", html.unescape(value))
    return re.sub(r"\s+", " ", normalized).strip()


def element_text(element: ET.Element | None) -> str:
    if element is None:
        return ""
    return normalize_text("".join(element.itertext()))


def _abstract_text(nodes: Iterable[ET.Element]) -> str:
    sections: list[str] = []
    for node in nodes:
        text = element_text(node)
        if not text:
            continue
        label = normalize_text(
            node.attrib.get("Label") or node.attrib.get("NlmCategory") or ""
        )
        if label and label.upper() != "UNASSIGNED":
            sections.append(f"{label}: {text}")
        else:
            sections.append(text)
    return normalize_text(" ".join(sections))


def _parse_pubmed_article(node: ET.Element) -> CorpusRecord | None:
    citation = node.find("./MedlineCitation")
    if citation is None:
        return None

    pmid = element_text(citation.find("./PMID"))
    if not pmid:
        return None

    title = element_text(citation.find("./Article/ArticleTitle"))
    abstract = _abstract_text(citation.findall(".//Abstract/AbstractText"))
    return CorpusRecord(id=pmid, title=title, text=abstract)


def _parse_pubmed_book_article(node: ET.Element) -> CorpusRecord | None:
    document = node.find("./BookDocument")
    if document is None:
        return None

    pmid = element_text(document.find("./PMID"))
    if not pmid:
        return None

    title = element_text(document.find("./ArticleTitle"))
    if not title:
        title = element_text(document.find("./Book/BookTitle"))
    abstract = _abstract_text(document.findall(".//Abstract/AbstractText"))
    return CorpusRecord(id=pmid, title=title, text=abstract)


def parse_pubmed_xml(content: bytes | str) -> dict[str, CorpusRecord]:
    """Parse PubMed XML, keeping the first occurrence of each PMID."""

    if not content or (isinstance(content, str) and not content.strip()):
        raise CorpusFetchError("EFetch returned an empty response")

    try:
        root = ET.fromstring(content)
    except (ET.ParseError, ValueError) as exc:
        raise CorpusFetchError(f"EFetch returned malformed XML: {exc}") from exc

    records: dict[str, CorpusRecord] = {}
    for article in root.findall(".//PubmedArticle"):
        record = _parse_pubmed_article(article)
        if record is not None:
            records.setdefault(record.id, record)
    for article in root.findall(".//PubmedBookArticle"):
        record = _parse_pubmed_book_article(article)
        if record is not None:
            records.setdefault(record.id, record)

    if not records:
        raise CorpusFetchError("EFetch XML contained no records with a PMID")
    return records


def _retry_after_seconds(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(value)
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=timezone.utc)
            return max(0.0, (retry_at - datetime.now(timezone.utc)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return None


def request_with_retries(
    session: requests.Session,
    method: str,
    url: str,
    *,
    limiter: RateLimiter,
    params: dict[str, str] | None = None,
    data: dict[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    sleep: Callable[[float], None] = time.sleep,
) -> requests.Response:
    """Issue one E-utilities request with bounded transient retries."""

    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")

    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        limiter.wait()
        try:
            response = session.request(
                method,
                url,
                params=params,
                data=data,
                timeout=timeout,
            )
        except requests.RequestException as exc:
            last_error = exc
            if attempt == max_attempts:
                break
            sleep(float(2 ** (attempt - 1)))
            continue

        if 200 <= response.status_code < 300:
            return response

        if response.status_code not in TRANSIENT_HTTP_STATUSES:
            excerpt = normalize_text(response.text)[:200]
            raise CorpusFetchError(
                f"NCBI returned HTTP {response.status_code}: {excerpt or 'no details'}"
            )

        last_error = CorpusFetchError(f"NCBI returned HTTP {response.status_code}")
        if attempt == max_attempts:
            break

        retry_after = _retry_after_seconds(response.headers.get("Retry-After"))
        backoff = float(2 ** (attempt - 1))
        sleep(max(backoff, retry_after or 0.0))

    detail = f": {last_error}" if last_error else ""
    raise CorpusFetchError(
        f"NCBI request failed after {max_attempts} attempts{detail}"
    ) from last_error


def _common_parameters(email: str, api_key: str | None) -> dict[str, str]:
    parameters = {"tool": TOOL_NAME, "email": email}
    if api_key:
        parameters["api_key"] = api_key
    return parameters


def search_pubmed(
    session: requests.Session,
    *,
    email: str,
    api_key: str | None,
    retmax: int,
    limiter: RateLimiter,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> list[str]:
    """Run the fixed ESearch query and return unique PMIDs in result order."""

    if not 1 <= retmax <= MAX_RETMAX:
        raise ValueError(f"retmax must be between 1 and {MAX_RETMAX}")

    params = {
        "db": "pubmed",
        "term": QUERY,
        "retmode": "json",
        "retmax": str(retmax),
        "sort": "relevance",
        **_common_parameters(email, api_key),
    }
    response = request_with_retries(
        session,
        "GET",
        ESEARCH_URL,
        params=params,
        limiter=limiter,
        timeout=timeout,
    )

    try:
        payload: Any = response.json()
        id_list = payload["esearchresult"]["idlist"]
    except (ValueError, KeyError, TypeError) as exc:
        raise CorpusFetchError("ESearch returned malformed JSON") from exc

    if not isinstance(id_list, list) or not id_list:
        raise CorpusFetchError("ESearch returned no PMIDs")

    pmids: list[str] = []
    seen: set[str] = set()
    for value in id_list[:retmax]:
        pmid = str(value).strip()
        if not pmid or not pmid.isdigit():
            raise CorpusFetchError(f"ESearch returned an invalid PMID: {value!r}")
        if pmid not in seen:
            seen.add(pmid)
            pmids.append(pmid)
    return pmids


def batched(values: Sequence[str], batch_size: int) -> Iterator[Sequence[str]]:
    if not 1 <= batch_size <= MAX_BATCH_SIZE:
        raise ValueError(f"batch_size must be between 1 and {MAX_BATCH_SIZE}")
    for start in range(0, len(values), batch_size):
        yield values[start : start + batch_size]


def fetch_records(
    session: requests.Session,
    pmids: Sequence[str],
    *,
    email: str,
    api_key: str | None,
    batch_size: int,
    limiter: RateLimiter,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> list[CorpusRecord]:
    """Fetch PubMed XML in bounded batches and restore ESearch ordering."""

    records_by_id: dict[str, CorpusRecord] = {}
    for batch in batched(pmids, batch_size):
        data = {
            "db": "pubmed",
            "id": ",".join(batch),
            "retmode": "xml",
            "rettype": "abstract",
            **_common_parameters(email, api_key),
        }
        response = request_with_retries(
            session,
            "POST",
            EFETCH_URL,
            data=data,
            limiter=limiter,
            timeout=timeout,
        )
        parsed = parse_pubmed_xml(response.content)
        for pmid, record in parsed.items():
            if pmid in batch:
                records_by_id.setdefault(pmid, record)

    ordered = [records_by_id[pmid] for pmid in pmids if pmid in records_by_id]
    if not ordered:
        raise CorpusFetchError("No requested PubMed records could be parsed")

    missing_count = len(pmids) - len(ordered)
    if missing_count:
        print(
            f"Warning: {missing_count} requested PMID(s) were absent from EFetch output.",
            file=sys.stderr,
        )
    return ordered


def write_jsonl_atomic(
    records: Sequence[CorpusRecord], output: Path, *, overwrite: bool
) -> None:
    """Write complete JSONL to a sibling temporary file, then replace atomically."""

    if output.exists() and not overwrite:
        raise CorpusFetchError(
            f"Output already exists: {output}. Pass --overwrite to replace it."
        )
    if not records:
        raise CorpusFetchError("Refusing to write an empty corpus")

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
            for record in records:
                json.dump(
                    record.as_dict(),
                    temporary,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, output)
    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise


def ensure_output_available(output: Path, *, overwrite: bool) -> None:
    """Reject an existing final path before starting a network job."""

    if output.exists() and not overwrite:
        raise CorpusFetchError(
            f"Output already exists: {output}. Pass --overwrite to replace it."
        )


def fetch_and_write(
    session: requests.Session,
    *,
    email: str,
    api_key: str | None,
    retmax: int,
    batch_size: int,
    output: Path,
    overwrite: bool,
    limiter: RateLimiter,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> int:
    """Fetch the entire corpus before touching the final output path."""

    ensure_output_available(output, overwrite=overwrite)
    pmids = search_pubmed(
        session,
        email=email,
        api_key=api_key,
        retmax=retmax,
        limiter=limiter,
        timeout=timeout,
    )
    records = fetch_records(
        session,
        pmids,
        email=email,
        api_key=api_key,
        batch_size=batch_size,
        limiter=limiter,
        timeout=timeout,
    )
    write_jsonl_atomic(records, output, overwrite=overwrite)
    return len(records)


def bounded_integer(name: str, minimum: int, maximum: int) -> Callable[[str], int]:
    def parse(value: str) -> int:
        try:
            parsed = int(value)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(f"{name} must be an integer") from exc
        if not minimum <= parsed <= maximum:
            raise argparse.ArgumentTypeError(
                f"{name} must be between {minimum} and {maximum}"
            )
        return parsed

    return parse


def positive_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("timeout must be a number") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("timeout must be greater than zero")
    return parsed


def valid_email(value: str) -> str:
    email = value.strip()
    if "@" not in email or any(character.isspace() for character in email):
        raise argparse.ArgumentTypeError("provide a valid contact email address")
    return email


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--email",
        type=valid_email,
        default=os.getenv("NCBI_EMAIL"),
        help="NCBI contact email (or set NCBI_EMAIL)",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("NCBI_API_KEY"),
        help="optional NCBI API key (or set NCBI_API_KEY)",
    )
    parser.add_argument(
        "--retmax",
        type=bounded_integer("retmax", 1, MAX_RETMAX),
        default=MAX_RETMAX,
        help=f"maximum PMIDs to retrieve (default and hard maximum: {MAX_RETMAX})",
    )
    parser.add_argument(
        "--batch-size",
        type=bounded_integer("batch-size", 1, MAX_BATCH_SIZE),
        default=MAX_BATCH_SIZE,
        help=f"PMIDs per EFetch POST (default and maximum: {MAX_BATCH_SIZE})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/corpus.jsonl"),
        help="output JSONL path (default: data/corpus.jsonl)",
    )
    parser.add_argument(
        "--timeout",
        type=positive_float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"per-request timeout in seconds (default: {DEFAULT_TIMEOUT_SECONDS:g})",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="replace an existing output file",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.email:
        parser.error("--email is required unless NCBI_EMAIL is set")

    session = requests.Session()
    session.headers.update(
        {"User-Agent": f"peptide-rag/0.1 ({args.email})", "Accept": "application/xml"}
    )
    limiter = RateLimiter()

    try:
        count = fetch_and_write(
            session,
            email=args.email,
            api_key=args.api_key,
            retmax=args.retmax,
            batch_size=args.batch_size,
            output=args.output,
            overwrite=args.overwrite,
            limiter=limiter,
            timeout=args.timeout,
        )
    except (CorpusFetchError, OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    finally:
        session.close()

    print(f"Wrote {count} PubMed record(s) to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

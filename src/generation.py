"""Fail-closed grounded answer generation through OpenRouter."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
import re
import time
from typing import Iterable, Literal, Sequence

import requests

from src.retrieval import RetrievedChunk


OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_GENERATION_MODEL = "qwen/qwen3.7-flash"
GENERATION_TEMPERATURE = 0
GENERATION_MAX_TOKENS = 400
SYSTEM_PROMPT = (
    "You are a research-literature assistant. Use only the supplied evidence. "
    "Do not give personalized medical, treatment, or dosing advice. If evidence is missing, "
    "conflicting, or the question requests personal medical/dosing advice, return insufficient_evidence. "
    "For answered responses, every factual sentence must end with one or more [citation_id] markers."
)
_CITATION = re.compile(r"\[(\d+)\]")
_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")
_FIRST_PERSON = re.compile(r"\b(?:i|me|my|mine|we|our|ours)\b", re.IGNORECASE)
_MEDICAL_ACTION = re.compile(
    r"\b(?:take|use|inject|dose|dosage|treat|cure|prescribe|cycle|stack)\b",
    re.IGNORECASE,
)
_DOSING_REQUEST = re.compile(
    r"\b(?:what|which|recommend(?:ed)?)\s+(?:is\s+an?\s+)?(?:safe\s+)?(?:dose|dosage)\b|"
    r"\b(?:dose|dosage)\b.{0,60}\b(?:safe|should|recommend|take|use|treat)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Citation:
    citation_id: int
    pmid: str
    chunk_id: str
    title: str


@dataclass(frozen=True)
class AnswerResult:
    status: Literal["answered", "insufficient_evidence"]
    text: str
    citations: tuple[Citation, ...]


def insufficient_evidence() -> AnswerResult:
    """Return the only safe result used for unavailable or invalid generation."""

    return AnswerResult("insufficient_evidence", "Insufficient evidence in the retrieved research abstracts.", ())


def requires_medical_refusal(query: str) -> bool:
    """Detect direct personalized or prescriptive dosing requests.

    Questions about doses *reported by a study* remain allowed; requests that
    ask what the user should take or what dose is safe are refused before an
    external model is called.
    """

    if not isinstance(query, str):
        return False
    personalized_action = bool(_FIRST_PERSON.search(query) and _MEDICAL_ACTION.search(query))
    if personalized_action:
        return True
    reported_context = re.search(r"\b(?:study|paper|trial|reported|tested|administered|rats?|mice)\b", query, re.IGNORECASE)
    if reported_context:
        return False
    return bool(_DOSING_REQUEST.search(query))


def validate_answer_result(result: AnswerResult, contexts: Sequence[RetrievedChunk]) -> bool:
    """Validate status, citation identity, and factual-sentence citation markers."""

    if result.status not in {"answered", "insufficient_evidence"} or not isinstance(result.text, str):
        return False
    if result.status == "insufficient_evidence":
        return not result.citations
    if not result.text.strip() or not result.citations:
        return False
    expected = {index: chunk for index, chunk in enumerate(contexts[:5], start=1)}
    seen: set[int] = set()
    for citation in result.citations:
        chunk = expected.get(citation.citation_id)
        if chunk is None or citation.citation_id in seen:
            return False
        if (citation.pmid, citation.chunk_id, citation.title) != (chunk.pmid, chunk.chunk_id, chunk.title):
            return False
        seen.add(citation.citation_id)
    markers = {int(value) for value in _CITATION.findall(result.text)}
    if not markers or markers != seen:
        return False
    # Headings and citation-only fragments are exempt; substantive sentences need evidence.
    # Citation styles commonly place ``[1]`` after a terminal period. Treat it as
    # belonging to the sentence immediately before it for structural validation.
    citation_bound = re.sub(r"([.!?])\s*(\[\d+\])", r"\2\1", result.text.strip())
    for sentence in _SENTENCE.split(citation_bound):
        stripped = sentence.strip()
        words = re.sub(r"\[\d+\]", "", stripped).strip()
        if (len(re.findall(r"\w+", words)) >= 3 or re.search(r"\d", words)) and not _CITATION.search(stripped):
            return False
    return True


class GroundedAnswerClient:
    """OpenRouter caller that never emits an unvalidated model answer."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = DEFAULT_GENERATION_MODEL,
        timeout: float = 30.0,
        retries: int = 1,
        session: requests.Session | None = None,
    ) -> None:
        if not isinstance(model, str) or not model or timeout <= 0 or retries < 0:
            raise ValueError("model must be non-empty, timeout positive, and retries non-negative")
        self.api_key = api_key if api_key is not None else os.environ.get("OPENROUTER_API_KEY")
        self.model, self.timeout, self.retries = model, timeout, retries
        self.session = session if session is not None else requests.Session()
        self.last_metadata: dict[str, object] = {}
        self._usage_complete = True

    def answer(self, query: str, contexts: Iterable[RetrievedChunk]) -> AnswerResult:
        self.last_metadata = {
            "provider_calls": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "cost_usd": 0.0,
            "provider": None,
        }
        self._usage_complete = True
        selected = tuple(contexts)[:5]
        if (
            not isinstance(query, str)
            or not query.strip()
            or requires_medical_refusal(query)
            or not selected
            or not self.api_key
        ):
            return insufficient_evidence()
        payload = self._payload(query, selected)
        candidate = self._request(payload)
        candidate = self._bind_citations(candidate, selected)
        if candidate is not None and validate_answer_result(candidate, selected):
            return candidate
        # One constrained repair is allowed; it sees the same evidence and no new facts.
        repair = self._payload(query, selected, repair=True)
        candidate = self._request(repair)
        candidate = self._bind_citations(candidate, selected)
        if candidate is not None and validate_answer_result(candidate, selected):
            return candidate
        return insufficient_evidence()

    @staticmethod
    def _bind_citations(candidate: AnswerResult | None, contexts: Sequence[RetrievedChunk]) -> AnswerResult | None:
        if candidate is None:
            return None
        context_by_id = {number: chunk for number, chunk in enumerate(contexts[:5], start=1)}
        citations = []
        for raw in candidate.citations:
            chunk = context_by_id.get(raw.citation_id)
            if chunk is None:
                return candidate
            citations.append(Citation(raw.citation_id, chunk.pmid, chunk.chunk_id, chunk.title))
        return AnswerResult(candidate.status, candidate.text, tuple(citations))

    def _payload(self, query: str, contexts: Sequence[RetrievedChunk], *, repair: bool = False) -> dict[str, object]:
        evidence = "\n\n".join(
            f"[{number}] PMID {chunk.pmid} | {chunk.title}\n{chunk.text}"
            for number, chunk in enumerate(contexts, start=1)
        )
        system = SYSTEM_PROMPT
        if repair:
            system += " Repair the previous invalid response by returning only schema-valid JSON with no unsupported claims."
        schema = {
            "name": "grounded_answer",
            "strict": True,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["status", "text", "citation_ids"],
                "properties": {
                    "status": {"type": "string", "enum": ["answered", "insufficient_evidence"]},
                    "text": {"type": "string"},
                    "citation_ids": {"type": "array", "items": {"type": "integer"}},
                },
            },
        }
        return {
            "model": self.model,
            "temperature": GENERATION_TEMPERATURE,
            "max_tokens": GENERATION_MAX_TOKENS,
            "response_format": {"type": "json_schema", "json_schema": schema},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": f"Question: {query}\n\nEvidence:\n{evidence}"},
            ],
        }

    def _request(self, payload: dict[str, object]) -> AnswerResult | None:
        for attempt in range(self.retries + 1):
            try:
                self.last_metadata["provider_calls"] = int(self.last_metadata.get("provider_calls", 0)) + 1
                response = self.session.post(
                    OPENROUTER_CHAT_URL,
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                    json=payload,
                    timeout=self.timeout,
                )
                if response.status_code in {429, 500, 502, 503, 504} and attempt < self.retries:
                    retry_after = response.headers.get("Retry-After")
                    try:
                        delay = max(0.0, float(retry_after)) if retry_after is not None else 0.25 * (2**attempt)
                    except (TypeError, ValueError):
                        delay = 0.25 * (2**attempt)
                    time.sleep(delay)
                    continue
                response.raise_for_status()
                response_payload = response.json()
                self._record_usage(response_payload)
                content = response_payload["choices"][0]["message"]["content"]
                parsed = json.loads(content) if isinstance(content, str) else content
                if not isinstance(parsed, dict):
                    return None
                status, text, ids = parsed.get("status"), parsed.get("text"), parsed.get("citation_ids")
                if not isinstance(status, str) or not isinstance(text, str) or not isinstance(ids, list):
                    return None
                citation_ids = tuple(ids)
                if any(isinstance(value, bool) or not isinstance(value, int) for value in citation_ids):
                    return None
                # Identity is resolved below by validation; untrusted model data never supplies metadata.
                return AnswerResult(status, text, tuple(Citation(value, "", "", "") for value in citation_ids))
            except (requests.RequestException, OSError, KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError):
                if attempt < self.retries:
                    time.sleep(0.25 * (2**attempt))
        return None

    def _record_usage(self, payload: object) -> None:
        """Accumulate provider-reported usage without inventing missing values."""

        if not isinstance(payload, dict):
            self._usage_complete = False
            return
        provider = payload.get("provider")
        if isinstance(provider, str) and provider:
            current = self.last_metadata.get("provider")
            self.last_metadata["provider"] = provider if current in (None, provider) else "multiple"
        usage = payload.get("usage")
        if not isinstance(usage, dict):
            self._usage_complete = False
        else:
            prompt = usage.get("prompt_tokens")
            completion = usage.get("completion_tokens")
            cost = usage.get("cost")
            if self._usage_complete and (
                isinstance(prompt, int) and not isinstance(prompt, bool) and prompt >= 0
                and isinstance(completion, int) and not isinstance(completion, bool) and completion >= 0
                and isinstance(cost, (int, float)) and not isinstance(cost, bool) and cost >= 0
            ):
                self.last_metadata["input_tokens"] = int(self.last_metadata["input_tokens"]) + prompt
                self.last_metadata["output_tokens"] = int(self.last_metadata["output_tokens"]) + completion
                self.last_metadata["cost_usd"] = float(self.last_metadata["cost_usd"]) + float(cost)
            elif self._usage_complete:
                self._usage_complete = False
        if not self._usage_complete:
            self.last_metadata["input_tokens"] = None
            self.last_metadata["output_tokens"] = None
            self.last_metadata["cost_usd"] = None

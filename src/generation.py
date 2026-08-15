"""Fail-closed grounded answer generation through OpenRouter."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
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
SYSTEM_PROMPT_V2 = (
    "You are a research-literature assistant. Use only the supplied PubMed abstract evidence. "
    "Answer whenever at least one supplied passage directly reports a finding relevant to the question. "
    "State the study population or species and preserve uncertainty; animal evidence may be summarized as "
    "an animal finding but must not be presented as proof of human treatment efficacy. Do not give personalized "
    "medical, treatment, or dosing advice. Return insufficient_evidence only when the passages do not support an "
    "answer, materially conflict, or the question requests personalized medical or dosing advice. Keep answered "
    "text to one to three concise factual sentences, and end every factual sentence with one or more [citation_id] "
    "markers. Return only the required JSON object."
)
SYSTEM_PROMPT_V3 = (
    "You are a research-literature assistant. Use only the supplied PubMed abstract evidence. "
    "Classify the question's evidence scope before answering. If the question explicitly asks about humans, "
    "human recovery, human effectiveness, safety in humans, or clinical use, answer only when at least one "
    "supplied passage directly reports evidence in humans; animal, in-vitro, or equine evidence alone requires "
    "insufficient_evidence. If the question is general and a supplied animal or in-vitro passage directly reports "
    "a relevant finding, answer with the species or model and explicitly state that it is not proof of human "
    "efficacy; do not refuse solely because the evidence is nonhuman. Answer whenever at least one supplied passage "
    "directly reports a finding relevant to the question. State the study population or species and preserve "
    "uncertainty. Do not give personalized medical, treatment, or dosing advice. Return insufficient_evidence only "
    "when the passages do not support an answer, materially conflict, the explicitly requested human evidence is "
    "absent, or the question requests personalized medical or dosing advice. Prefer one concise factual sentence "
    "and use no more than three. Every sentence containing a study fact, outcome, number, mechanism, or limitation "
    "must include one or more [citation_id] markers. Return only the required JSON object."
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
    reported_context = re.search(
        r"\b(?:study|paper|trial|experiment|reported|tested|administered|rats?|mice)\b",
        query,
        re.IGNORECASE,
    )
    if reported_context:
        return False
    if re.search(r"\b(?:dose|dosage)\b", query, re.IGNORECASE) and re.search(
        r"\b(?:safe|safest|effective|recommended?|human|should|take|use)\b",
        query,
        re.IGNORECASE,
    ):
        return True
    return bool(_DOSING_REQUEST.search(query))


def answer_validation_error(result: AnswerResult, contexts: Sequence[RetrievedChunk]) -> str | None:
    """Return a stable validation error code, or ``None`` for a valid result."""

    if result.status not in {"answered", "insufficient_evidence"} or not isinstance(result.text, str):
        return "invalid_status_or_text"
    if result.status == "insufficient_evidence":
        return None if not result.citations else "refusal_has_citations"
    if not result.text.strip() or not result.citations:
        return "answered_missing_text_or_citations"
    expected = {index: chunk for index, chunk in enumerate(contexts[:5], start=1)}
    seen: set[int] = set()
    for citation in result.citations:
        chunk = expected.get(citation.citation_id)
        if chunk is None or citation.citation_id in seen:
            return "unknown_or_duplicate_citation_id"
        if (citation.pmid, citation.chunk_id, citation.title) != (chunk.pmid, chunk.chunk_id, chunk.title):
            return "citation_identity_mismatch"
        seen.add(citation.citation_id)
    markers = {int(value) for value in _CITATION.findall(result.text)}
    if not markers or markers != seen:
        return "citation_markers_do_not_match_declared_ids"
    # Headings and citation-only fragments are exempt; substantive sentences need evidence.
    # Citation styles commonly place ``[1]`` after a terminal period. Treat it as
    # belonging to the sentence immediately before it for structural validation.
    citation_bound = re.sub(r"([.!?])\s*(\[\d+\])", r"\2\1", result.text.strip())
    for sentence in _SENTENCE.split(citation_bound):
        stripped = sentence.strip()
        words = re.sub(r"\[\d+\]", "", stripped).strip()
        if (len(re.findall(r"\w+", words)) >= 3 or re.search(r"\d", words)) and not _CITATION.search(stripped):
            return "uncited_factual_sentence"
    return None


def validate_answer_result(result: AnswerResult, contexts: Sequence[RetrievedChunk]) -> bool:
    """Validate status, citation identity, and factual-sentence citation markers."""

    return answer_validation_error(result, contexts) is None


class GroundedAnswerClient:
    """OpenRouter caller that never emits an unvalidated model answer."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = DEFAULT_GENERATION_MODEL,
        timeout: float = 30.0,
        retries: int = 1,
        max_tokens: int = GENERATION_MAX_TOKENS,
        temperature: float = GENERATION_TEMPERATURE,
        system_prompt: str = SYSTEM_PROMPT,
        citation_mode: Literal["declared", "derived_from_text_markers"] = "declared",
        require_supported_parameters: bool = False,
        reasoning_effort: Literal["none", "minimal", "low", "medium", "high", "xhigh", "max"] | None = None,
        exclude_reasoning: bool = False,
        reconsider_insufficient_evidence: bool = False,
        session: requests.Session | None = None,
    ) -> None:
        if (
            not isinstance(model, str)
            or not model
            or timeout <= 0
            or retries < 0
            or isinstance(max_tokens, bool)
            or not isinstance(max_tokens, int)
            or max_tokens <= 0
            or isinstance(temperature, bool)
            or not isinstance(temperature, (int, float))
            or temperature < 0
            or not isinstance(system_prompt, str)
            or not system_prompt.strip()
            or citation_mode not in {"declared", "derived_from_text_markers"}
            or not isinstance(require_supported_parameters, bool)
            or reasoning_effort
            not in {None, "none", "minimal", "low", "medium", "high", "xhigh", "max"}
            or not isinstance(exclude_reasoning, bool)
            or (reasoning_effort is None and exclude_reasoning)
            or not isinstance(reconsider_insufficient_evidence, bool)
        ):
            raise ValueError("invalid model, request, or generation configuration")
        self.api_key = api_key if api_key is not None else os.environ.get("OPENROUTER_API_KEY")
        self.model, self.timeout, self.retries = model, timeout, retries
        self.max_tokens = max_tokens
        self.temperature = float(temperature)
        self.system_prompt = system_prompt
        self.citation_mode = citation_mode
        self.require_supported_parameters = require_supported_parameters
        self.reasoning_effort = reasoning_effort
        self.exclude_reasoning = exclude_reasoning
        self.reconsider_insufficient_evidence = reconsider_insufficient_evidence
        self.session = session if session is not None else requests.Session()
        self.last_metadata: dict[str, object] = {}
        self._usage_complete = True
        self._last_raw_output: str | None = None
        self._last_response_failure = "provider_response_unusable"

    def answer(self, query: str, contexts: Iterable[RetrievedChunk]) -> AnswerResult:
        self.last_metadata = {
            "provider_calls": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "cost_usd": 0.0,
            "provider": None,
            "attempts": [],
            "final_outcome": None,
            "generation_max_tokens": self.max_tokens,
        }
        self._usage_complete = True
        self._last_raw_output = None
        self._last_response_failure = "provider_response_unusable"
        selected = tuple(contexts)[:5]
        preflight_reason = None
        if not isinstance(query, str) or not query.strip():
            preflight_reason = "invalid_or_empty_query"
        elif requires_medical_refusal(query):
            preflight_reason = "personalized_or_dosing_request"
        elif not selected:
            preflight_reason = "no_retrieved_context"
        elif not self.api_key:
            preflight_reason = "missing_api_key"
        if preflight_reason is not None:
            self.last_metadata["final_outcome"] = "preflight_insufficient_evidence"
            self.last_metadata["failure_reason"] = preflight_reason
            return insufficient_evidence()
        payload = self._payload(query, selected)
        candidate = self._request(payload, stage="initial")
        candidate = self._bind_citations(candidate, selected)
        validation_error = self._last_response_failure if candidate is None else answer_validation_error(candidate, selected)
        self._record_validation(validation_error)
        if (
            candidate is not None
            and validation_error is None
            and candidate.status == "insufficient_evidence"
            and self.reconsider_insufficient_evidence
        ):
            reconsideration = self._payload(
                query,
                selected,
                reconsider_refusal=True,
                previous_output=self._last_raw_output,
            )
            candidate = self._request(reconsideration, stage="refusal_reconsideration")
            candidate = self._bind_citations(candidate, selected)
            validation_error = (
                self._last_response_failure
                if candidate is None
                else answer_validation_error(candidate, selected)
            )
            self._record_validation(validation_error)
            if candidate is not None and validation_error is None:
                self.last_metadata["final_outcome"] = (
                    "answered_after_refusal_reconsideration"
                    if candidate.status == "answered"
                    else "model_insufficient_evidence_after_reconsideration"
                )
                return candidate
            self.last_metadata["final_outcome"] = "failed_closed_after_refusal_reconsideration"
            self.last_metadata["failure_reason"] = validation_error
            return insufficient_evidence()
        if candidate is not None and validation_error is None:
            self.last_metadata["final_outcome"] = (
                "answered" if candidate.status == "answered" else "model_insufficient_evidence"
            )
            return candidate
        # One constrained repair is allowed. It sees the invalid response, the
        # local failure code, the identical evidence, and no new facts.
        repair = self._payload(
            query,
            selected,
            repair=True,
            previous_output=self._last_raw_output,
            validation_error=validation_error,
        )
        candidate = self._request(repair, stage="repair")
        candidate = self._bind_citations(candidate, selected)
        validation_error = self._last_response_failure if candidate is None else answer_validation_error(candidate, selected)
        self._record_validation(validation_error)
        if candidate is not None and validation_error is None:
            self.last_metadata["final_outcome"] = (
                "answered_after_repair" if candidate.status == "answered" else "model_insufficient_evidence_after_repair"
            )
            return candidate
        self.last_metadata["final_outcome"] = "failed_closed_after_repair"
        self.last_metadata["failure_reason"] = validation_error
        return insufficient_evidence()

    def _record_validation(self, error: str | None) -> None:
        attempts = self.last_metadata.get("attempts")
        if not isinstance(attempts, list) or not attempts:
            return
        latest = attempts[-1]
        if not isinstance(latest, dict):
            return
        latest["validation_error"] = error
        if error is not None and latest.get("outcome") == "parsed_candidate":
            latest["outcome"] = "local_validation_failed"

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

    def _payload(
        self,
        query: str,
        contexts: Sequence[RetrievedChunk],
        *,
        repair: bool = False,
        reconsider_refusal: bool = False,
        previous_output: str | None = None,
        validation_error: str | None = None,
    ) -> dict[str, object]:
        evidence = "\n\n".join(
            f"[{number}] PMID {chunk.pmid} | {chunk.title}\n{chunk.text}"
            for number, chunk in enumerate(contexts, start=1)
        )
        properties: dict[str, object] = {
            "status": {
                "type": "string",
                "enum": ["answered", "insufficient_evidence"],
                "description": "Use answered only when the supplied evidence directly supports the text.",
            },
            "text": {
                "type": "string",
                "description": "Concise answer with [number] markers after every factual sentence, or the standard refusal text.",
            },
        }
        required = ["status", "text"]
        if self.citation_mode == "declared":
            properties["citation_ids"] = {
                "type": "array",
                "items": {"type": "integer", "minimum": 1, "maximum": 5},
                "maxItems": 5,
                "uniqueItems": True,
                "description": "Each marker used in text exactly once; no unused IDs.",
            }
            required.append("citation_ids")
        schema = {
            "name": "grounded_answer",
            "strict": True,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "required": required,
                "properties": properties,
            },
        }
        if self.citation_mode == "derived_from_text_markers":
            examples = (
                'For an answer use {"status":"answered","text":"Concise finding. [1]"}. '
                'For a refusal use {"status":"insufficient_evidence","text":"Insufficient evidence in the retrieved research abstracts."}. '
                "Citation identities are derived from the bracketed markers; do not return a separate citation list."
            )
        else:
            examples = (
                'For an answer use {"status":"answered","text":"Concise finding. [1]","citation_ids":[1]}. '
                'For a refusal use {"status":"insufficient_evidence","text":"Insufficient evidence in the retrieved research abstracts.","citation_ids":[]}. '
                "citation_ids must contain every bracketed marker exactly once and no unused IDs."
            )
        instructions = f"Question: {query}\n\nEvidence:\n{evidence}\n\nReturn exactly one JSON object. {examples}"
        messages: list[dict[str, str]] = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": instructions},
        ]
        if reconsider_refusal:
            if previous_output is None:
                raise ValueError("refusal reconsideration requires the preceding response")
            messages.extend(
                [
                    {"role": "assistant", "content": previous_output},
                    {
                        "role": "user",
                        "content": (
                            "Re-check the refusal against all five supplied passages, including later passages. "
                            "Do not assume that evidence is insufficient merely because the question is broad. "
                            "If any passage directly reports a finding that answers the question within its stated "
                            "population or species, replace the refusal with a concise cited answer. Keep "
                            "insufficient_evidence when the requested scope is unsupported, the evidence conflicts "
                            "or is missing, or the question asks for personalized medical or dosing advice. Use "
                            "only the supplied evidence and return the required JSON object and nothing else."
                        ),
                    },
                ]
            )
        elif repair and previous_output is not None:
            messages.extend(
                [
                    {"role": "assistant", "content": previous_output},
                    {
                        "role": "user",
                        "content": (
                            "The preceding response failed local validation with code "
                            f"{validation_error or 'provider_response_unusable'}. Correct only its JSON structure, "
                            "citation markers, or evidence scope. Return the corrected JSON object and nothing else."
                        ),
                    },
                ]
            )
        elif repair:
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "The previous provider attempt returned no usable response body; its failure code was "
                        f"{validation_error or 'provider_response_unusable'}. Make one fresh constrained attempt "
                        "and return the required JSON object and nothing else."
                    ),
                }
            )
        payload: dict[str, object] = {
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "response_format": {"type": "json_schema", "json_schema": schema},
            "messages": messages,
        }
        if self.require_supported_parameters:
            payload["provider"] = {"require_parameters": True}
        if self.reasoning_effort is not None:
            payload["reasoning"] = {
                "effort": self.reasoning_effort,
                "exclude": self.exclude_reasoning,
            }
        return payload

    def _request(self, payload: dict[str, object], *, stage: str) -> AnswerResult | None:
        self._last_raw_output = None
        self._last_response_failure = "provider_response_unusable"
        for attempt in range(self.retries + 1):
            record: dict[str, object] = {
                "stage": stage,
                "retry_index": attempt,
                "http_status": None,
                "finish_reason": None,
                "native_finish_reason": None,
                "outcome": "started",
            }
            attempts = self.last_metadata.get("attempts")
            if isinstance(attempts, list):
                attempts.append(record)
            try:
                self.last_metadata["provider_calls"] = int(self.last_metadata.get("provider_calls", 0)) + 1
                response = self.session.post(
                    OPENROUTER_CHAT_URL,
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                    json=payload,
                    timeout=self.timeout,
                )
                status_code = getattr(response, "status_code", None)
                record["http_status"] = status_code if isinstance(status_code, int) else None
                if response.status_code in {429, 500, 502, 503, 504} and attempt < self.retries:
                    record["outcome"] = "transient_http_retry"
                    if self._last_raw_output is None:
                        self._last_response_failure = "transient_http_error"
                    retry_after = response.headers.get("Retry-After")
                    try:
                        delay = max(0.0, float(retry_after)) if retry_after is not None else 0.25 * (2**attempt)
                    except (TypeError, ValueError):
                        delay = 0.25 * (2**attempt)
                    time.sleep(delay)
                    continue
                if isinstance(status_code, int) and status_code >= 400:
                    try:
                        self._record_response_shape(response.json(), record)
                    except (ValueError, TypeError):
                        record["response_json_available"] = False
                response.raise_for_status()
                response_payload = response.json()
                self._record_response_shape(response_payload, record)
                self._record_usage(response_payload)
                choices = response_payload.get("choices") if isinstance(response_payload, dict) else None
                if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
                    record["outcome"] = "missing_or_invalid_choices"
                    self._last_response_failure = "missing_or_invalid_choices"
                    return None
                choice = choices[0]
                finish_reason = choice.get("finish_reason")
                native_finish_reason = choice.get("native_finish_reason", response_payload.get("native_finish_reason"))
                record["finish_reason"] = finish_reason if isinstance(finish_reason, str) else None
                record["native_finish_reason"] = native_finish_reason if isinstance(native_finish_reason, str) else None
                message = choice.get("message")
                if not isinstance(message, dict) or message.get("content") is None:
                    record["outcome"] = "missing_message_content"
                    self._last_response_failure = "missing_message_content"
                    return None
                content = message["content"]
                raw_output = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False, sort_keys=True)
                self._last_raw_output = raw_output
                record["raw_output_characters"] = len(raw_output)
                record["raw_output_sha256"] = hashlib.sha256(raw_output.encode("utf-8")).hexdigest().upper()
                try:
                    parsed = json.loads(content) if isinstance(content, str) else content
                except json.JSONDecodeError:
                    record["outcome"] = "invalid_json"
                    self._last_response_failure = "invalid_json"
                    if attempt < self.retries:
                        time.sleep(0.25 * (2**attempt))
                        continue
                    return None
                if not isinstance(parsed, dict):
                    record["outcome"] = "non_object_json"
                    self._last_response_failure = "non_object_json"
                    return None
                status, text = parsed.get("status"), parsed.get("text")
                ids = parsed.get("citation_ids")
                if not isinstance(status, str) or not isinstance(text, str):
                    record["outcome"] = "schema_fields_invalid"
                    self._last_response_failure = "schema_fields_invalid"
                    return None
                if self.citation_mode == "derived_from_text_markers":
                    citation_ids = tuple(sorted({int(value) for value in _CITATION.findall(text)}))
                else:
                    if not isinstance(ids, list):
                        record["outcome"] = "schema_fields_invalid"
                        self._last_response_failure = "schema_fields_invalid"
                        return None
                    citation_ids = tuple(ids)
                    if any(isinstance(value, bool) or not isinstance(value, int) for value in citation_ids):
                        record["outcome"] = "citation_ids_invalid"
                        self._last_response_failure = "citation_ids_invalid"
                        return None
                # Identity is resolved below by validation; untrusted model data never supplies metadata.
                record["outcome"] = "parsed_candidate"
                return AnswerResult(status, text, tuple(Citation(value, "", "", "") for value in citation_ids))
            except (requests.RequestException, OSError, KeyError, IndexError, TypeError, ValueError) as exc:
                record["outcome"] = "request_or_response_error"
                record["error_type"] = type(exc).__name__
                if self._last_raw_output is None:
                    self._last_response_failure = "request_or_response_error"
                if attempt < self.retries:
                    time.sleep(0.25 * (2**attempt))
        return None

    @staticmethod
    def _record_response_shape(payload: object, record: dict[str, object]) -> None:
        """Persist non-content response structure and safe provider error codes."""

        if not isinstance(payload, dict):
            record["response_json_available"] = True
            record["response_json_type"] = type(payload).__name__
            return
        record["response_json_available"] = True
        record["response_top_level_keys"] = sorted(str(key) for key in payload)
        error = payload.get("error")
        if isinstance(error, dict):
            for source, target in (("code", "provider_error_code"), ("type", "provider_error_type")):
                value = error.get(source)
                if isinstance(value, (str, int, float)) and not isinstance(value, bool):
                    record[target] = value
        choices = payload.get("choices")
        if isinstance(choices, list):
            record["response_choice_count"] = len(choices)
            if choices and isinstance(choices[0], dict):
                record["response_choice_keys"] = sorted(str(key) for key in choices[0])
                message = choices[0].get("message")
                if isinstance(message, dict):
                    record["response_message_keys"] = sorted(str(key) for key in message)

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

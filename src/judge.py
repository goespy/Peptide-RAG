"""Structured, evidence-only answer judging through OpenRouter."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from typing import Sequence

import requests

from src.generation import AnswerResult, Citation
from src.retrieval import RetrievedChunk


OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_JUDGE_MODEL = "anthropic/claude-sonnet-4.6"


@dataclass(frozen=True)
class AtomicClaim:
    text: str
    supported: bool
    citation_ids: tuple[int, ...]


@dataclass(frozen=True)
class JudgeVerdict:
    claims: tuple[AtomicClaim, ...]
    faithful: bool
    relevant: bool
    citations_correct: bool
    refusal_correct: bool


def validate_verdict(verdict: JudgeVerdict, contexts: Sequence[RetrievedChunk]) -> bool:
    allowed = set(range(1, len(contexts[:5]) + 1))
    if not isinstance(verdict.faithful, bool) or not isinstance(verdict.relevant, bool):
        return False
    if not isinstance(verdict.citations_correct, bool) or not isinstance(verdict.refusal_correct, bool):
        return False
    return all(
        isinstance(claim.text, str) and bool(claim.text.strip()) and isinstance(claim.supported, bool)
        and all(isinstance(item, int) and not isinstance(item, bool) and item in allowed for item in claim.citation_ids)
        for claim in verdict.claims
    )


class AnswerJudge:
    """Conservative judge; invalid/provider responses produce no verdict."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = DEFAULT_JUDGE_MODEL,
        timeout: float = 30.0,
        max_tokens: int = 600,
        require_supported_parameters: bool = False,
        session: requests.Session | None = None,
    ) -> None:
        if (
            not isinstance(model, str)
            or not model
            or timeout <= 0
            or isinstance(max_tokens, bool)
            or not isinstance(max_tokens, int)
            or max_tokens <= 0
            or not isinstance(require_supported_parameters, bool)
        ):
            raise ValueError("invalid judge model, timeout, token cap, or provider configuration")
        self.api_key = api_key if api_key is not None else os.environ.get("OPENROUTER_API_KEY")
        self.model, self.timeout = model, timeout
        self.max_tokens = max_tokens
        self.require_supported_parameters = require_supported_parameters
        self.session = session if session is not None else requests.Session()
        self.last_metadata: dict[str, object] = {}

    def judge(
        self,
        query: str,
        answer: AnswerResult,
        contexts: Sequence[RetrievedChunk],
        *,
        expected_answerable: bool | None = None,
    ) -> JudgeVerdict | None:
        selected = tuple(contexts)[:5]
        self.last_metadata = {
            "provider_calls": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "cost_usd": 0.0,
            "provider": None,
        }
        if not isinstance(query, str) or not query.strip() or not self.api_key or not isinstance(expected_answerable, bool):
            return None
        try:
            self.last_metadata["provider_calls"] = 1
            response = self.session.post(OPENROUTER_CHAT_URL, headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}, json=self._payload(query, answer, selected), timeout=self.timeout)
            response.raise_for_status()
            response_payload = response.json()
            self._record_usage(response_payload)
            content = response_payload["choices"][0]["message"]["content"]
            payload = json.loads(content) if isinstance(content, str) else content
            refusal_correct = (answer.status == "insufficient_evidence") == (not expected_answerable)
            verdict = self._parse(payload, refusal_correct=refusal_correct)
            return verdict if validate_verdict(verdict, selected) else None
        except (requests.RequestException, OSError, KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError):
            return None

    def _record_usage(self, payload: object) -> None:
        if not isinstance(payload, dict):
            usage = None
        else:
            provider = payload.get("provider")
            if isinstance(provider, str) and provider:
                self.last_metadata["provider"] = provider
            usage = payload.get("usage")
        if not isinstance(usage, dict):
            self.last_metadata.update({"input_tokens": None, "output_tokens": None, "cost_usd": None})
            return
        prompt, completion, cost = usage.get("prompt_tokens"), usage.get("completion_tokens"), usage.get("cost")
        if (
            not isinstance(prompt, int) or isinstance(prompt, bool) or prompt < 0
            or not isinstance(completion, int) or isinstance(completion, bool) or completion < 0
            or not isinstance(cost, (int, float)) or isinstance(cost, bool) or cost < 0
        ):
            self.last_metadata.update({"input_tokens": None, "output_tokens": None, "cost_usd": None})
            return
        self.last_metadata.update({"input_tokens": prompt, "output_tokens": completion, "cost_usd": float(cost)})

    def _payload(
        self,
        query: str,
        answer: AnswerResult,
        contexts: Sequence[RetrievedChunk],
    ) -> dict[str, object]:
        evidence = "\n\n".join(f"[{i}] PMID {chunk.pmid} | {chunk.title}\n{chunk.text}" for i, chunk in enumerate(contexts, 1))
        schema = {"name": "faithfulness_verdict", "strict": True, "schema": {"type": "object", "additionalProperties": False, "required": ["claims", "faithful", "relevant", "citations_correct"], "properties": {"claims": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["text", "supported", "citation_ids"], "properties": {"text": {"type": "string"}, "supported": {"type": "boolean"}, "citation_ids": {"type": "array", "items": {"type": "integer"}}}}}, "faithful": {"type": "boolean"}, "relevant": {"type": "boolean"}, "citations_correct": {"type": "boolean"}}}}
        payload: dict[str, object] = {"model": self.model, "temperature": 0, "max_tokens": self.max_tokens, "response_format": {"type": "json_schema", "json_schema": schema}, "messages": [{"role": "system", "content": "Judge only supplied evidence. Extract atomic claims and mark support. Do not infer missing facts. Evaluate faithfulness, relevance, and citation correctness only; refusal correctness is computed outside the model."}, {"role": "user", "content": f"Question: {query}\nAnswer status: {answer.status}\nAnswer: {answer.text}\nCitations: {tuple((c.citation_id, c.pmid, c.chunk_id) for c in answer.citations)}\n\nEvidence:\n{evidence}"}]}
        if self.require_supported_parameters:
            payload["provider"] = {"require_parameters": True}
        return payload

    @staticmethod
    def _parse(payload: object, *, refusal_correct: bool) -> JudgeVerdict:
        if not isinstance(payload, dict):
            raise ValueError("judge payload must be an object")
        raw_claims = payload["claims"]
        if not isinstance(raw_claims, list):
            raise ValueError("claims must be a list")
        claims = []
        for item in raw_claims:
            if not isinstance(item, dict) or not isinstance(item.get("text"), str) or not isinstance(item.get("supported"), bool) or not isinstance(item.get("citation_ids"), list):
                raise ValueError("invalid claim")
            claims.append(AtomicClaim(item["text"], item["supported"], tuple(item["citation_ids"])))
        return JudgeVerdict(tuple(claims), payload["faithful"], payload["relevant"], payload["citations_correct"], refusal_correct)

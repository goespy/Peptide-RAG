"""OpenRouter embeddings with deterministic, validated on-disk caching."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
import time
from typing import Iterable, Sequence

import numpy as np
import requests


DEFAULT_EMBEDDING_MODEL = "openai/text-embedding-3-small"
OPENROUTER_EMBEDDINGS_URL = "https://openrouter.ai/api/v1/embeddings"


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def text_hashes(inputs: Sequence[str]) -> tuple[str, ...]:
    """Return order-sensitive hashes for embedding inputs."""

    if any(not isinstance(item, str) for item in inputs):
        raise ValueError("embedding inputs must be strings")
    return tuple(_sha256(item.encode("utf-8")) for item in inputs)


def normalize_embeddings(values: np.ndarray | Sequence[Sequence[float]]) -> np.ndarray:
    """Return a finite, row-normalized float64 embedding matrix."""

    matrix = np.asarray(values, dtype=np.float64)
    if matrix.ndim != 2:
        raise ValueError("embeddings must be a two-dimensional matrix")
    if not np.isfinite(matrix).all():
        raise ValueError("embeddings must be finite")
    norms = np.linalg.norm(matrix, axis=1)
    if np.any(norms == 0):
        raise ValueError("embedding vectors must be non-zero")
    return matrix / norms[:, None]


@dataclass(frozen=True)
class EmbeddingCacheManifest:
    """Metadata which prevents accidentally reusing incompatible vectors."""

    model: str
    dimension: int
    corpus_hash: str
    chunk_hash: str
    input_hashes: tuple[str, ...]
    chunk_ids: tuple[str, ...]
    created_at: str
    provider: str = "OpenRouter"

    @classmethod
    def create(
        cls,
        *,
        model: str,
        dimension: int,
        corpus_hash: str,
        chunk_hash: str,
        inputs: Sequence[str],
        chunk_ids: Sequence[str],
    ) -> "EmbeddingCacheManifest":
        if not model or dimension <= 0 or not corpus_hash or not chunk_hash:
            raise ValueError("invalid embedding cache manifest metadata")
        if len(inputs) != len(chunk_ids):
            raise ValueError("inputs and chunk_ids must have equal length")
        return cls(
            model=model,
            dimension=dimension,
            corpus_hash=corpus_hash,
            chunk_hash=chunk_hash,
            input_hashes=text_hashes(inputs),
            chunk_ids=tuple(chunk_ids),
            created_at=datetime.now(timezone.utc).isoformat(),
            provider="OpenRouter",
        )


class EmbeddingClient:
    """Small retrying client for OpenRouter's OpenAI-compatible embeddings API."""

    @property
    def last_metadata(self) -> dict[str, object]:
        """Return metadata for the current thread's most recent embed call."""

        metadata = getattr(self._thread_state, "last_metadata", None)
        if metadata is None:
            metadata = {}
            self._thread_state.last_metadata = metadata
        return metadata

    @last_metadata.setter
    def last_metadata(self, value: dict[str, object]) -> None:
        self._thread_state.last_metadata = value

    @property
    def _usage_complete(self) -> bool:
        return bool(getattr(self._thread_state, "usage_complete", True))

    @_usage_complete.setter
    def _usage_complete(self, value: bool) -> None:
        self._thread_state.usage_complete = bool(value)

    def _http_session(self) -> requests.Session:
        if self._provided_session is not None:
            return self._provided_session
        session = getattr(self._thread_state, "http_session", None)
        if session is None:
            session = requests.Session()
            self._thread_state.http_session = session
        return session

    def _post(self, inputs: Sequence[str]) -> requests.Response:
        session = self._http_session()
        request = {
            "headers": {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            "json": {"model": self.model, "input": list(inputs)},
            "timeout": self.timeout,
        }
        if self._provided_session is None:
            return session.post(OPENROUTER_EMBEDDINGS_URL, **request)
        with self._session_lock:
            return session.post(OPENROUTER_EMBEDDINGS_URL, **request)

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = DEFAULT_EMBEDDING_MODEL,
        timeout: float = 30.0,
        retries: int = 2,
        session: requests.Session | None = None,
    ) -> None:
        if not isinstance(model, str) or not model:
            raise ValueError("model must be a non-empty string")
        if timeout <= 0 or retries < 0:
            raise ValueError("timeout must be positive and retries non-negative")
        self.api_key = api_key if api_key is not None else os.environ.get("OPENROUTER_API_KEY")
        self.model, self.timeout, self.retries = model, timeout, retries
        self._thread_state = threading.local()
        self._provided_session = session
        self._session_lock = threading.Lock()
        self._total_lock = threading.Lock()
        self.last_metadata: dict[str, object] = {}
        self.total_metadata: dict[str, object] = {
            "provider": "OpenRouter",
            "provider_calls": 0,
            "input_tokens": 0,
            "cost_usd": 0.0,
        }
        self._usage_complete = True

    def embed(self, inputs: Sequence[str], *, batch_size: int = 100) -> np.ndarray:
        """Embed inputs in batches; empty input deliberately performs no HTTP work."""

        values = tuple(inputs)
        self.last_metadata = {
            "provider": "OpenRouter",
            "provider_calls": 0,
            "input_tokens": 0,
            "cost_usd": 0.0,
        }
        self._usage_complete = True
        if any(not isinstance(value, str) for value in values):
            raise ValueError("embedding inputs must be strings")
        if not values:
            return np.empty((0, 0), dtype=np.float64)
        if not self.api_key:
            raise RuntimeError("OPENROUTER_API_KEY is required for embeddings")
        if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size <= 0:
            raise ValueError("batch_size must be a positive integer")
        vectors: list[list[float]] = []
        try:
            for start in range(0, len(values), batch_size):
                vectors.extend(self._embed_batch(values[start : start + batch_size]))
            result = normalize_embeddings(vectors)
        except BaseException:
            self._accumulate_total()
            raise
        self._accumulate_total()
        return result

    def _accumulate_total(self) -> None:
        current = dict(self.last_metadata)
        with self._total_lock:
            self.total_metadata["provider"] = current.get("provider", "OpenRouter")
            self.total_metadata["provider_calls"] = int(self.total_metadata["provider_calls"]) + int(current["provider_calls"])
            if self.total_metadata.get("input_tokens") is None or current.get("input_tokens") is None:
                self.total_metadata["input_tokens"] = None
                self.total_metadata["cost_usd"] = None
            else:
                self.total_metadata["input_tokens"] = int(self.total_metadata["input_tokens"]) + int(current["input_tokens"])
                self.total_metadata["cost_usd"] = float(self.total_metadata["cost_usd"]) + float(current["cost_usd"])

    def _embed_batch(self, inputs: Sequence[str]) -> list[list[float]]:
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                self.last_metadata["provider_calls"] = int(self.last_metadata["provider_calls"]) + 1
                response = self._post(inputs)
                if response.status_code in (429, 500, 502, 503, 504):
                    if attempt < self.retries:
                        self._usage_complete = False
                        retry_after = response.headers.get("Retry-After")
                        try:
                            delay = max(0.0, float(retry_after)) if retry_after is not None else 0.25 * (2 ** attempt)
                        except ValueError:
                            delay = 0.25 * (2 ** attempt)
                        time.sleep(delay)
                        continue
                response.raise_for_status()
                payload = response.json()
                self._record_usage(payload)
                records = payload.get("data")
                if not isinstance(records, list) or len(records) != len(inputs):
                    raise ValueError("embedding response has an invalid data array")
                if sorted(record.get("index") for record in records if isinstance(record, dict)) != list(range(len(inputs))):
                    raise ValueError("embedding response indices are missing or duplicated")
                ordered = sorted(records, key=lambda record: record.get("index", -1))
                if [record.get("index") for record in ordered] != list(range(len(inputs))):
                    raise ValueError("embedding response indices do not match the request")
                result = [record.get("embedding") for record in ordered]
                if any(not isinstance(vector, list) or not vector for vector in result):
                    raise ValueError("embedding response contains an invalid vector")
                return result  # type: ignore[return-value]
            except (requests.RequestException, ValueError) as error:
                last_error = error
                self._usage_complete = False
                if attempt < self.retries:
                    time.sleep(0.25 * (2 ** attempt))
        if not self._usage_complete:
            self.last_metadata["input_tokens"] = None
            self.last_metadata["cost_usd"] = None
        raise RuntimeError("OpenRouter embeddings request failed") from last_error

    def _record_usage(self, payload: object) -> None:
        if not isinstance(payload, dict):
            self._usage_complete = False
        else:
            provider = payload.get("provider")
            if isinstance(provider, str) and provider:
                self.last_metadata["provider"] = provider
            usage = payload.get("usage")
            tokens = usage.get("prompt_tokens", usage.get("total_tokens")) if isinstance(usage, dict) else None
            cost = usage.get("cost") if isinstance(usage, dict) else None
            if self._usage_complete and isinstance(tokens, int) and not isinstance(tokens, bool) and tokens >= 0 and isinstance(cost, (int, float)) and not isinstance(cost, bool) and cost >= 0:
                self.last_metadata["input_tokens"] = int(self.last_metadata["input_tokens"]) + tokens
                self.last_metadata["cost_usd"] = float(self.last_metadata["cost_usd"]) + float(cost)
            elif self._usage_complete:
                self._usage_complete = False
        if not self._usage_complete:
            self.last_metadata["input_tokens"] = None
            self.last_metadata["cost_usd"] = None


def save_embedding_cache(path: Path, embeddings: np.ndarray, manifest: EmbeddingCacheManifest) -> None:
    """Atomically save normalized vectors and their manifest to ``path`` (.npz)."""

    matrix = normalize_embeddings(embeddings)
    if matrix.shape != (len(manifest.chunk_ids), manifest.dimension):
        raise ValueError("embedding matrix does not match cache manifest")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=target.parent, prefix=f".{target.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(descriptor, "wb") as output:
            np.savez_compressed(output, embeddings=matrix, manifest=json.dumps(asdict(manifest), sort_keys=True))
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_name, target)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def load_embedding_cache(path: Path, expected: EmbeddingCacheManifest) -> np.ndarray | None:
    """Load a cache only when every identity field agrees with ``expected``."""

    try:
        with np.load(Path(path), allow_pickle=False) as stored:
            raw_manifest = stored["manifest"].item()
            actual_data = json.loads(raw_manifest)
            actual_data["input_hashes"] = tuple(actual_data["input_hashes"])
            actual_data["chunk_ids"] = tuple(actual_data["chunk_ids"])
            actual = EmbeddingCacheManifest(**actual_data)
            # The creation time is observational metadata, not cache identity.
            if (
                actual.model,
                actual.dimension,
                actual.corpus_hash,
                actual.chunk_hash,
                actual.input_hashes,
                actual.chunk_ids,
                actual.provider,
            ) != (
                expected.model,
                expected.dimension,
                expected.corpus_hash,
                expected.chunk_hash,
                expected.input_hashes,
                expected.chunk_ids,
                expected.provider,
            ):
                return None
            matrix = normalize_embeddings(stored["embeddings"])
            return matrix if matrix.shape == (len(expected.chunk_ids), expected.dimension) else None
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None

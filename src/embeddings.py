"""OpenRouter embeddings with deterministic, validated on-disk caching."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
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
        return cls(model, dimension, corpus_hash, chunk_hash, text_hashes(inputs), tuple(chunk_ids), datetime.now(timezone.utc).isoformat())


class EmbeddingClient:
    """Small retrying client for OpenRouter's OpenAI-compatible embeddings API."""

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
        self.session = session if session is not None else requests.Session()

    def embed(self, inputs: Sequence[str], *, batch_size: int = 100) -> np.ndarray:
        """Embed inputs in batches; empty input deliberately performs no HTTP work."""

        values = tuple(inputs)
        if any(not isinstance(value, str) for value in values):
            raise ValueError("embedding inputs must be strings")
        if not values:
            return np.empty((0, 0), dtype=np.float64)
        if not self.api_key:
            raise RuntimeError("OPENROUTER_API_KEY is required for embeddings")
        if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size <= 0:
            raise ValueError("batch_size must be a positive integer")
        vectors: list[list[float]] = []
        for start in range(0, len(values), batch_size):
            vectors.extend(self._embed_batch(values[start : start + batch_size]))
        return normalize_embeddings(vectors)

    def _embed_batch(self, inputs: Sequence[str]) -> list[list[float]]:
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                response = self.session.post(
                    OPENROUTER_EMBEDDINGS_URL, headers=headers,
                    json={"model": self.model, "input": list(inputs)}, timeout=self.timeout,
                )
                if response.status_code in (429, 500, 502, 503, 504):
                    if attempt < self.retries:
                        retry_after = response.headers.get("Retry-After")
                        try:
                            delay = max(0.0, float(retry_after)) if retry_after is not None else 0.25 * (2 ** attempt)
                        except ValueError:
                            delay = 0.25 * (2 ** attempt)
                        time.sleep(delay)
                        continue
                response.raise_for_status()
                payload = response.json()
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
                if attempt < self.retries:
                    time.sleep(0.25 * (2 ** attempt))
        raise RuntimeError("OpenRouter embeddings request failed") from last_error


def save_embedding_cache(path: Path, embeddings: np.ndarray, manifest: EmbeddingCacheManifest) -> None:
    """Atomically save normalized vectors and their manifest to ``path`` (.npz)."""

    matrix = normalize_embeddings(embeddings)
    if matrix.shape != (len(manifest.chunk_ids), manifest.dimension):
        raise ValueError("embedding matrix does not match cache manifest")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    with temporary.open("wb") as output:
        np.savez_compressed(output, embeddings=matrix, manifest=json.dumps(asdict(manifest), sort_keys=True))
    os.replace(temporary, target)


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
            ) != (
                expected.model,
                expected.dimension,
                expected.corpus_hash,
                expected.chunk_hash,
                expected.input_hashes,
                expected.chunk_ids,
            ):
                return None
            matrix = normalize_embeddings(stored["embeddings"])
            return matrix if matrix.shape == (len(expected.chunk_ids), expected.dimension) else None
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None

"""Deterministic, offset-preserving abstract chunking primitives."""

from __future__ import annotations

from dataclasses import dataclass
import re
from collections.abc import Iterable


@dataclass(frozen=True)
class ChunkConfig:
    """A word-window configuration for abstract chunking."""

    words: int
    overlap: int

    def __post_init__(self) -> None:
        if any(isinstance(value, bool) or not isinstance(value, int)
               for value in (self.words, self.overlap)):
            raise ValueError("words and overlap must be integers")
        if self.words <= 0:
            raise ValueError("words must be greater than zero")
        if self.overlap <= 0 or self.overlap >= self.words:
            raise ValueError("overlap must be greater than zero and less than words")


CHUNK_CONFIGS = (
    ChunkConfig(words=128, overlap=32),
    ChunkConfig(words=256, overlap=64),
    ChunkConfig(words=512, overlap=128),
)


@dataclass(frozen=True)
class Chunk:
    """A contiguous abstract substring together with its original offsets."""

    chunk_id: str
    pmid: str
    title: str
    text: str
    start_char: int
    end_char: int
    token_count: int


def word_spans(text: str) -> tuple[tuple[int, int], ...]:
    """Return Unicode non-whitespace word spans in their source coordinates."""

    if not isinstance(text, str):
        raise TypeError("text must be a string")
    return tuple((match.start(), match.end()) for match in re.finditer(r"\S+", text))


def chunk_document(pmid: str, title: str, text: str, config: ChunkConfig) -> tuple[Chunk, ...]:
    """Split one document into stable, overlapping word windows.

    Chunk text is always a direct substring of ``text``; leading and trailing
    inter-word whitespace outside the window is deliberately not included.
    """

    if not isinstance(pmid, str) or not pmid:
        raise ValueError("pmid must be a non-empty string")
    if not isinstance(title, str) or not isinstance(text, str):
        raise TypeError("title and text must be strings")
    if not isinstance(config, ChunkConfig):
        raise TypeError("config must be a ChunkConfig")

    spans = word_spans(text)
    if not spans:
        return (Chunk(f"{pmid}:c0001", pmid, title, "", 0, 0, 0),)

    chunks: list[Chunk] = []
    step = config.words - config.overlap
    for ordinal, word_start in enumerate(range(0, len(spans), step), start=1):
        window = spans[word_start:word_start + config.words]
        start_char, end_char = window[0][0], window[-1][1]
        chunks.append(Chunk(
            chunk_id=f"{pmid}:c{ordinal:04d}", pmid=pmid, title=title,
            text=text[start_char:end_char], start_char=start_char, end_char=end_char,
            token_count=len(window),
        ))
        if word_start + config.words >= len(spans):
            break
    return tuple(chunks)


def chunk_corpus(documents: Iterable[object], config: ChunkConfig) -> tuple[Chunk, ...]:
    """Chunk mapping-like corpus records in numeric PMID then ordinal order."""

    records: list[tuple[str, str, str]] = []
    for document in documents:
        if isinstance(document, dict):
            pmid, title, text = document.get("id"), document.get("title"), document.get("text")
        else:
            pmid, title, text = (
                getattr(document, "id", None), getattr(document, "title", None),
                getattr(document, "text", None),
            )
        if not all(isinstance(value, str) for value in (pmid, title, text)):
            raise ValueError("each document needs string id, title, and text fields")
        if not pmid.isdecimal():
            raise ValueError("PMIDs must be numeric strings")
        records.append((pmid, title, text))
    if len({record[0] for record in records}) != len(records):
        raise ValueError("PMIDs must be unique")
    return tuple(chunk for pmid, title, text in sorted(records, key=lambda item: int(item[0]))
                 for chunk in chunk_document(pmid, title, text, config))


def embedding_text(chunk: Chunk) -> str:
    """Return retrieval input without changing abstract-relative chunk offsets."""

    if not isinstance(chunk, Chunk):
        raise TypeError("chunk must be a Chunk")
    return f"{chunk.title}\n\n{chunk.text}" if chunk.text else chunk.title


def span_contained(chunk: Chunk, start: int, end: int) -> bool:
    """Whether a non-empty abstract evidence span is fully in ``chunk``."""

    if not isinstance(chunk, Chunk):
        raise TypeError("chunk must be a Chunk")
    if any(isinstance(value, bool) or not isinstance(value, int) for value in (start, end)):
        raise TypeError("span offsets must be integers")
    return bool(chunk.text) and start < end and chunk.start_char <= start and end <= chunk.end_char

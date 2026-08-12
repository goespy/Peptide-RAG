"""Shared immutable document and posting types."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Document:
    id: str
    title: str
    text: str


@dataclass(frozen=True)
class Posting:
    doc_id: str
    positions: tuple[int, ...]

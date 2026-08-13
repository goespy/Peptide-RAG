"""Query-aware, presentation-safe snippets for search results."""

from __future__ import annotations

import html
import re

from .analysis import analyze

_WORD = re.compile(r"[^\W_]+", flags=re.UNICODE)
_OPERATORS = frozenset({"and", "or"})


def query_terms(query: str) -> frozenset[str]:
    """Return distinct searchable terms from *query*, ignoring Boolean words."""

    if not isinstance(query, str):
        return frozenset()
    return frozenset(term for term in analyze(query) if term not in _OPERATORS)


def _word_matches(text: str, terms: frozenset[str]) -> list[tuple[int, int]]:
    return [
        (match.start(), match.end())
        for match in _WORD.finditer(text)
        if any(token in terms for token in analyze(match.group()))
    ]


def _best_window(text: str, terms: frozenset[str], max_chars: int) -> tuple[int, int]:
    """Choose the earliest fixed-size window covering the most distinct terms."""

    if len(text) <= max_chars:
        return (0, len(text))

    matches = _word_matches(text, terms)
    if not matches:
        return (0, max_chars)

    # A best window begins at 0, at a match, or just far enough left to retain
    # a match at its right edge.  Those boundaries cover every score change.
    last_start = len(text) - max_chars
    candidates = {0, last_start}
    for start, end in matches:
        candidates.add(min(start, last_start))
        candidates.add(max(0, end - max_chars))

    best_start = 0
    best_coverage: frozenset[str] = frozenset()
    for start in sorted(candidates):
        end = start + max_chars
        covered = frozenset(
            token
            for match in _WORD.finditer(text[start:end])
            for token in analyze(match.group())
            if token in terms
        )
        if len(covered) > len(best_coverage):
            best_start, best_coverage = start, covered
    return (best_start, best_start + max_chars)


def make_snippet(
    text: str,
    query: str,
    *,
    max_chars: int = 240,
    html_safe: bool = False,
) -> str:
    """Build a short snippet and mark matched words with ``[[...]]``.

    The character cap applies to the selected source-text window; markers and
    leading/trailing ellipses are presentation decorations.  ``html_safe``
    escapes all document-controlled text before markers are added.
    """

    if not isinstance(text, str):
        return ""
    if max_chars < 1:
        raise ValueError("max_chars must be greater than zero")

    terms = query_terms(query)
    start, end = _best_window(text, terms, max_chars)
    fragment = text[start:end]

    def render(match: re.Match[str]) -> str:
        value = html.escape(match.group()) if html_safe else match.group()
        if any(token in terms for token in analyze(match.group())):
            return f"[[{value}]]"
        return value

    body = _WORD.sub(render, fragment)
    # Escape punctuation and whitespace too when producing an HTML-safe form.
    if html_safe:
        pieces: list[str] = []
        cursor = 0
        for match in _WORD.finditer(fragment):
            pieces.append(html.escape(fragment[cursor : match.start()]))
            pieces.append(render(match))
            cursor = match.end()
        pieces.append(html.escape(fragment[cursor:]))
        body = "".join(pieces)
    return ("…" if start else "") + body + ("…" if end < len(text) else "")


def make_html_snippet(text: str, query: str, *, max_chars: int = 240) -> str:
    """Return :func:`make_snippet` output with document text HTML-escaped."""

    return make_snippet(text, query, max_chars=max_chars, html_safe=True)

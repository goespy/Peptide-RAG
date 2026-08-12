"""Shared corpus and query analysis defined by ARCHITECTURE.md."""

from __future__ import annotations

import re
import unicodedata


def analyze(value: str) -> tuple[str, ...]:
    """Return NFKC/casefolded maximal Unicode-alphanumeric token runs."""

    normalized = unicodedata.normalize("NFKC", value).casefold()
    return tuple(re.findall(r"[^\W_]+", normalized, flags=re.UNICODE))

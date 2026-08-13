"""Shared corpus and query analysis defined by ARCHITECTURE.md."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class AnalysisConfig:
    """Versioned choices for deterministic corpus and query analysis."""

    name: str = "baseline"
    expand_greek: bool = False
    remove_stopwords: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise ValueError("analysis configuration name must be a non-empty string")
        if not isinstance(self.expand_greek, bool) or not isinstance(self.remove_stopwords, bool):
            raise ValueError("analysis configuration flags must be booleans")


BASELINE_ANALYSIS = AnalysisConfig()
GREEK_ANALYSIS = AnalysisConfig(name="greek", expand_greek=True)
STOPWORDS_ANALYSIS = AnalysisConfig(name="stopwords", remove_stopwords=True)
GREEK_STOPWORDS_ANALYSIS = AnalysisConfig(
    name="greek_stopwords", expand_greek=True, remove_stopwords=True
)

ANALYSIS_CONFIGS = {
    config.name: config
    for config in (
        BASELINE_ANALYSIS,
        GREEK_ANALYSIS,
        STOPWORDS_ANALYSIS,
        GREEK_STOPWORDS_ANALYSIS,
    )
}

# Intentionally small, fixed baseline experiment list. It is kept in source so
# the stopword experiment is reproducible without a third-party dependency.
STOPWORDS = frozenset(
    {
        "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
        "in", "is", "it", "of", "on", "or", "that", "the", "this", "to",
        "was", "were", "with",
    }
)

_GREEK_EXPANSIONS = str.maketrans({
    "α": "alpha",
    "β": "beta",
    "γ": "gamma",
    "δ": "delta",
})


def analyze(value: str, config: AnalysisConfig = BASELINE_ANALYSIS) -> tuple[str, ...]:
    """Return NFKC/casefolded maximal Unicode-alphanumeric token runs."""

    if not isinstance(config, AnalysisConfig):
        raise ValueError("config must be an AnalysisConfig")
    normalized = unicodedata.normalize("NFKC", value).casefold()
    if config.expand_greek:
        normalized = normalized.translate(_GREEK_EXPANSIONS)
    tokens = tuple(re.findall(r"[^\W_]+", normalized, flags=re.UNICODE))
    if config.remove_stopwords:
        return tuple(token for token in tokens if token not in STOPWORDS)
    return tokens

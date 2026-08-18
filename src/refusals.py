"""Safe public refusal categories and user-facing explanations."""

from __future__ import annotations

from types import MappingProxyType
from typing import Literal


RefusalReason = Literal[
    "medical_safety",
    "insufficient_evidence",
    "service_unavailable",
    "budget_limit",
]

MEDICAL_SAFETY = "medical_safety"
INSUFFICIENT_EVIDENCE = "insufficient_evidence"
SERVICE_UNAVAILABLE = "service_unavailable"
BUDGET_LIMIT = "budget_limit"

REFUSAL_MESSAGES = MappingProxyType(
    {
        MEDICAL_SAFETY: (
            "I can summarize doses reported in research, but I can’t recommend "
            "what you should take."
        ),
        INSUFFICIENT_EVIDENCE: (
            "The retrieved abstracts don’t contain enough evidence to answer."
        ),
        SERVICE_UNAVAILABLE: (
            "Answer generation failed, so retrieved evidence is shown instead."
        ),
        BUDGET_LIMIT: "Daily answer budget is exhausted.",
    }
)
PUBLIC_REFUSAL_REASONS = frozenset(REFUSAL_MESSAGES)


def refusal_message(reason: RefusalReason) -> str:
    """Return the fixed public explanation for a validated refusal category."""

    return REFUSAL_MESSAGES[reason]

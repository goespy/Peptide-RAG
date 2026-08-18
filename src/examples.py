"""Load the frozen example-question artifact for the public web shell.

The artifact is presentation data. It is bound to the corpus hash so a rebuilt
or swapped corpus silently disables the examples instead of showing questions
whose supporting records no longer exist.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ARTIFACT_VERSION = 1
EXPECTED_TOPICS = 8
EXPECTED_QUESTIONS_PER_TOPIC = 3
MAX_QUESTION_CHARACTERS = 500


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _clean_topic(raw: object) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    identifier = raw.get("id")
    name = raw.get("name")
    subtitle = raw.get("subtitle")
    questions = raw.get("questions")
    if not isinstance(identifier, str) or not identifier.strip():
        return None
    if not isinstance(name, str) or not name.strip():
        return None
    if not isinstance(subtitle, str):
        return None
    if not isinstance(questions, list) or len(questions) != EXPECTED_QUESTIONS_PER_TOPIC:
        return None

    cleaned: list[str] = []
    for question in questions:
        if not isinstance(question, dict):
            return None
        text = question.get("text")
        if not isinstance(text, str) or not text.strip():
            return None
        if len(text) > MAX_QUESTION_CHARACTERS:
            return None
        cleaned.append(text)

    return {"id": identifier, "name": name, "subtitle": subtitle, "questions": cleaned}


def load_examples(
    path: Path,
    *,
    corpus_path: Path,
    lexical_config_path: Path | None = None,
) -> dict[str, Any] | None:
    """Return browser-safe example topics, or None when the artifact is unusable.

    Only fields the page renders are returned. Supporting PMIDs and verification
    metadata stay server-side: they document how the artifact was built and are
    not something the public page should present as evidence for an answer.
    """

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("version") != ARTIFACT_VERSION:
        return None

    try:
        corpus_hash = _sha256(corpus_path)
    except OSError:
        return None
    if payload.get("corpus_sha256") != corpus_hash:
        return None
    if lexical_config_path is not None:
        try:
            lexical_config_hash = _sha256(lexical_config_path)
        except OSError:
            return None
        if payload.get("lexical_config_sha256") != lexical_config_hash:
            return None

    raw_topics = payload.get("topics")
    if not isinstance(raw_topics, list) or len(raw_topics) != EXPECTED_TOPICS:
        return None

    topics: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in raw_topics:
        topic = _clean_topic(raw)
        if topic is None or topic["id"] in seen:
            return None
        seen.add(topic["id"])
        topics.append(topic)

    return {"version": ARTIFACT_VERSION, "topics": topics}

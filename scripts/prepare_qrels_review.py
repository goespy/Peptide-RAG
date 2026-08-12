#!/usr/bin/env python3
"""Select a reproducible, peptide-stratified set for human qrels review."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path


DEFAULT_CORPUS = Path("data/corpus.jsonl")
DEFAULT_OUTPUT = Path("data/qrels_candidates.json")
DEFAULT_COUNT = 15

# Ordered exactly as the assignment's PubMed query. These are selection aliases,
# not an attempt to expand the medical vocabulary or judge relevance.
FAMILY_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("BPC-157", ("BPC-157", "Body Protection Compound-157")),
    ("GHK-Cu", ("GHK-Cu",)),
    ("TB-500 / Thymosin Beta-4", ("TB-500", "Thymosin Beta-4")),
    ("Ipamorelin", ("Ipamorelin",)),
    ("Tesamorelin", ("Tesamorelin",)),
    ("Epitalon", ("Epitalon",)),
    ("MOTS-c", ("MOTS-c",)),
    ("PT-141", ("PT-141",)),
)


class ReviewPreparationError(RuntimeError):
    """Raised when the candidate set cannot be built safely."""


@dataclass(frozen=True)
class Document:
    id: str
    title: str
    text: str


@dataclass(frozen=True)
class Selection:
    family: str
    document: Document


def analyze(value: str) -> tuple[str, ...]:
    """Apply the architecture's NFKC/casefold/alphanumeric analysis baseline."""

    normalized = unicodedata.normalize("NFKC", value).casefold()
    return tuple(re.findall(r"[^\W_]+", normalized, flags=re.UNICODE))


def contains_sequence(tokens: Sequence[str], phrase: Sequence[str]) -> bool:
    if not phrase or len(phrase) > len(tokens):
        return False
    width = len(phrase)
    return any(
        tuple(tokens[start : start + width]) == tuple(phrase)
        for start in range(len(tokens) - width + 1)
    )


ANALYZED_ALIASES: dict[str, tuple[tuple[str, ...], ...]] = {
    family: tuple(analyze(alias) for alias in aliases)
    for family, aliases in FAMILY_ALIASES
}


def matching_families(title: str) -> tuple[str, ...]:
    title_tokens = analyze(title)
    return tuple(
        family
        for family, _ in FAMILY_ALIASES
        if any(
            contains_sequence(title_tokens, alias_tokens)
            for alias_tokens in ANALYZED_ALIASES[family]
        )
    )


def corpus_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as corpus:
        for block in iter(lambda: corpus.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def load_corpus(path: Path) -> list[Document]:
    if not path.is_file():
        raise ReviewPreparationError(f"Corpus not found: {path}")

    documents: list[Document] = []
    seen_ids: set[str] = set()
    with path.open("r", encoding="utf-8") as corpus:
        for line_number, line in enumerate(corpus, start=1):
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ReviewPreparationError(
                    f"Invalid JSON on corpus line {line_number}: {exc}"
                ) from exc
            if not isinstance(raw, dict) or set(raw) != {"id", "title", "text"}:
                raise ReviewPreparationError(
                    f"Corpus line {line_number} must have exactly id, title, and text"
                )
            if not all(isinstance(raw[key], str) for key in ("id", "title", "text")):
                raise ReviewPreparationError(
                    f"Corpus line {line_number} fields must all be strings"
                )
            if not raw["id"].isdigit() or raw["id"] in seen_ids:
                raise ReviewPreparationError(
                    f"Corpus line {line_number} has an invalid or duplicate PMID"
                )
            seen_ids.add(raw["id"])
            documents.append(Document(raw["id"], raw["title"], raw["text"]))

    if not documents:
        raise ReviewPreparationError("Corpus is empty")
    return documents


def select_documents(documents: Sequence[Document], count: int) -> list[Selection]:
    if count < 1:
        raise ValueError("count must be at least 1")

    eligible = sorted(
        (
            document
            for document in documents
            if document.title.strip() and document.text.strip()
        ),
        key=lambda document: int(document.id),
    )
    if len(eligible) < count:
        raise ReviewPreparationError(
            f"Need {count} nonempty documents, but corpus has only {len(eligible)}"
        )

    matches_by_family: dict[str, list[Document]] = {
        family: [
            document
            for document in eligible
            if family in matching_families(document.title)
        ]
        for family, _ in FAMILY_ALIASES
    }
    cursors = {family: 0 for family, _ in FAMILY_ALIASES}
    selected: list[Selection] = []
    selected_ids: set[str] = set()

    while len(selected) < count:
        made_progress = False
        for family, _ in FAMILY_ALIASES:
            matches = matches_by_family[family]
            cursor = cursors[family]
            while cursor < len(matches) and matches[cursor].id in selected_ids:
                cursor += 1
            cursors[family] = cursor
            if cursor >= len(matches):
                continue

            document = matches[cursor]
            cursors[family] += 1
            selected.append(Selection(family, document))
            selected_ids.add(document.id)
            made_progress = True
            if len(selected) == count:
                break
        if not made_progress:
            break

    if len(selected) < count:
        for document in eligible:
            if document.id in selected_ids:
                continue
            families = matching_families(document.title)
            selected.append(Selection(families[0] if families else "fallback", document))
            selected_ids.add(document.id)
            if len(selected) == count:
                break

    return selected


def build_packet(corpus_path: Path, count: int) -> dict[str, object]:
    documents = load_corpus(corpus_path)
    selections = select_documents(documents, count)
    family_match_counts = {
        family: sum(
            1
            for document in documents
            if document.title.strip()
            and document.text.strip()
            and family in matching_families(document.title)
        )
        for family, _ in FAMILY_ALIASES
    }
    return {
        "status": "candidate_selection_only_not_qrels",
        "corpus_sha256": corpus_sha256(corpus_path),
        "selection_count": len(selections),
        "family_match_counts": family_match_counts,
        "candidates": [
            {
                "id": f"q{number:02d}",
                "family": selection.family,
                "source_pmid": selection.document.id,
                "title": selection.document.title,
                "text": selection.document.text,
            }
            for number, selection in enumerate(selections, start=1)
        ],
    }


def write_json_atomic(payload: dict[str, object], output: Path, *, overwrite: bool) -> None:
    if output.exists() and not overwrite:
        raise ReviewPreparationError(
            f"Output already exists: {output}. Pass --overwrite to replace it."
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix=f".{output.name}.",
            suffix=".tmp",
            dir=output.parent,
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            json.dump(payload, temporary, ensure_ascii=False, indent=2)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, output)
    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise


def positive_integer(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("count must be an integer") from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError("count must be at least 1")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--count", type=positive_integer, default=DEFAULT_COUNT)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload = build_packet(args.corpus, args.count)
        write_json_atomic(payload, args.output, overwrite=args.overwrite)
    except (OSError, ReviewPreparationError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(
        f"Wrote {payload['selection_count']} review candidates to {args.output} "
        f"for corpus {payload['corpus_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

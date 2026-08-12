#!/usr/bin/env python3
"""Validate qrels draft suggestions and render a human-review worksheet."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

try:
    from scripts.prepare_qrels_review import Document, analyze, load_corpus, matching_families
except ModuleNotFoundError:  # Direct execution: python scripts/render_qrels_review.py
    from prepare_qrels_review import Document, analyze, load_corpus, matching_families


DEFAULT_CANDIDATES = Path("data/qrels_candidates.json")
DEFAULT_DRAFT = Path("data/qrels_draft.json")
DEFAULT_CORPUS = Path("data/corpus.jsonl")
DEFAULT_OUTPUT = Path("QRELS-REVIEW.md")


class ReviewRenderError(RuntimeError):
    """Raised when draft suggestions do not match their selected sources."""


def load_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReviewRenderError(f"Could not read {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ReviewRenderError(f"{path} must contain a JSON object")
    return payload


def validate_and_join(
    candidates: dict[str, Any],
    draft: dict[str, Any],
    corpus_documents: dict[str, Document],
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    if candidates.get("status") != "candidate_selection_only_not_qrels":
        raise ReviewRenderError("Candidate packet has an unexpected status")
    if draft.get("status") != "ai_draft_requires_human_review":
        raise ReviewRenderError("Draft must remain marked as requiring human review")
    if candidates.get("corpus_sha256") != draft.get("corpus_sha256"):
        raise ReviewRenderError("Candidate and draft corpus hashes do not match")

    candidate_list = candidates.get("candidates")
    draft_list = draft.get("queries")
    if not isinstance(candidate_list, list) or not isinstance(draft_list, list):
        raise ReviewRenderError("Candidate and draft query collections must be lists")
    if len(candidate_list) != 15 or len(draft_list) != 15:
        raise ReviewRenderError("The Day 1 review packet must contain exactly 15 queries")

    drafts_by_id = {item.get("id"): item for item in draft_list if isinstance(item, dict)}
    joined: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for candidate in candidate_list:
        if not isinstance(candidate, dict) or candidate.get("id") not in drafts_by_id:
            raise ReviewRenderError("Every selected candidate must have one draft query")
        suggestion = drafts_by_id[candidate["id"]]
        original_source_pmid = candidate.get("source_pmid")
        source_pmid = suggestion.get("source_pmid")
        source = candidate
        if source_pmid != original_source_pmid:
            override = suggestion.get("selection_override")
            if not isinstance(override, dict):
                raise ReviewRenderError(
                    f"{candidate['id']} source mismatch requires a selection_override"
                )
            required_override = {
                "original_source_pmid",
                "reviewer",
                "reviewed_at",
                "reason",
            }
            if set(override) != required_override:
                raise ReviewRenderError(
                    f"{candidate['id']} selection_override has invalid fields"
                )
            if override["original_source_pmid"] != original_source_pmid:
                raise ReviewRenderError(
                    f"{candidate['id']} override does not name the deterministic source"
                )
            if not all(
                isinstance(override[field], str) and override[field].strip()
                for field in ("reviewer", "reviewed_at", "reason")
            ):
                raise ReviewRenderError(
                    f"{candidate['id']} override review metadata cannot be blank"
                )
            if not isinstance(source_pmid, str) or source_pmid not in corpus_documents:
                raise ReviewRenderError(
                    f"{candidate['id']} override PMID is absent from the frozen corpus"
                )
            document = corpus_documents[source_pmid]
            family = candidate.get("family")
            if family not in matching_families(document.title):
                raise ReviewRenderError(
                    f"{candidate['id']} override title does not match family {family}"
                )
            source = {
                **candidate,
                "source_pmid": document.id,
                "title": document.title,
                "text": document.text,
            }
        elif "selection_override" in suggestion:
            raise ReviewRenderError(
                f"{candidate['id']} cannot declare an override without changing the source"
            )
        if suggestion.get("family") != candidate.get("family"):
            raise ReviewRenderError(f"{candidate['id']} peptide family does not match")
        if suggestion.get("judgments") != {source_pmid: 2}:
            raise ReviewRenderError(
                f"{candidate['id']} must initially grade only its source PMID as 2"
            )

        review = suggestion.get("human_review")
        if not isinstance(review, dict) or review.get("approved") is not False:
            raise ReviewRenderError(
                f"{candidate['id']} must remain explicitly unapproved"
            )
        query = suggestion.get("query")
        rationale = suggestion.get("rationale")
        if not isinstance(query, str) or not isinstance(rationale, str) or not rationale.strip():
            raise ReviewRenderError(f"{candidate['id']} needs a query and rationale")

        query_terms = analyze(query)
        if not 3 <= len(query_terms) <= 6:
            raise ReviewRenderError(f"{candidate['id']} query must have 3-6 analyzed terms")
        if "and" in query_terms or "or" in query_terms:
            raise ReviewRenderError(f"{candidate['id']} query cannot contain AND or OR")
        source_terms = set(analyze(f"{source['title']} {source['text']}"))
        missing_terms = sorted(set(query_terms) - source_terms)
        if missing_terms:
            raise ReviewRenderError(
                f"{candidate['id']} query terms absent from source: {', '.join(missing_terms)}"
            )
        if query_terms == analyze(source["title"]):
            raise ReviewRenderError(f"{candidate['id']} query cannot copy the full title")
        joined.append((source, suggestion))

    if len(drafts_by_id) != len(joined):
        raise ReviewRenderError("Draft contains duplicate or unselected query IDs")
    return joined


def render_markdown(
    candidates: dict[str, Any],
    joined: Sequence[tuple[dict[str, Any], dict[str, Any]]],
) -> str:
    lines = [
        "# Qrels Human Review",
        "",
        "> **Not an oracle yet.** Every query and grade below is an AI draft. A human must read the source, approve or edit the wording and rationale, and inspect obvious additional candidate PMIDs before `data/qrels.json` can be created.",
        "",
        f"- Corpus SHA-256: `{candidates['corpus_sha256']}`",
        f"- Deterministically selected documents: {len(joined)}",
        "- Initial source grade: `2` (highly relevant)",
        "- Day 1 relevant threshold: grade `> 0`",
        "",
        "## Reviewer instructions",
        "",
        "For every query: read the title and abstract; approve, edit, or reject the proposed information need; confirm the source grade; use PubMed metadata or simple text filtering—not this search engine—to add obvious relevant and non-relevant judgments; and write your name plus notes. Do not approve a query merely because its terms occur in the source.",
        "",
    ]
    for candidate, suggestion in joined:
        pmid = candidate["source_pmid"]
        override = suggestion.get("selection_override")
        override_lines: list[str] = []
        if isinstance(override, dict):
            override_lines = [
                f"> **Reviewer override ({override['reviewed_at']}):** "
                f"{override['reason']} Original deterministic PMID "
                f"`{override['original_source_pmid']}` remains in "
                "`data/qrels_candidates.json` as the audit trail.",
                "",
            ]
        lines.extend(
            [
                f"## {candidate['id']} — {candidate['family']}",
                "",
                *override_lines,
                f"- Source: [PMID {pmid}](https://pubmed.ncbi.nlm.nih.gov/{pmid}/)",
                f"- Proposed query: `{suggestion['query']}`",
                f"- Proposed source judgment: `{pmid}: 2`",
                f"- Proposed rationale: {suggestion['rationale']}",
                "- Human decision: [ ] Approve  [ ] Edit  [ ] Reject",
                "- Reviewer:",
                "- Additional judgments and notes:",
                "",
                "### Title",
                "",
                candidate["title"],
                "",
                "### Abstract",
                "",
                candidate["text"],
                "",
            ]
        )
    return "\n".join(lines).rstrip()


def write_atomic(content: str, output: Path, *, overwrite: bool) -> None:
    if output.exists() and not overwrite:
        raise ReviewRenderError(
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
            temporary.write(content)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, output)
    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--draft", type=Path, default=DEFAULT_DRAFT)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        candidates = load_object(args.candidates)
        draft = load_object(args.draft)
        corpus_documents = {
            document.id: document for document in load_corpus(args.corpus)
        }
        joined = validate_and_join(candidates, draft, corpus_documents)
        write_atomic(
            render_markdown(candidates, joined), args.output, overwrite=args.overwrite
        )
    except (OSError, ReviewRenderError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {len(joined)} unapproved qrels suggestions to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

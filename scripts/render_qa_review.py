#!/usr/bin/env python3
"""Validate a QA candidate packet and render its human-review worksheet."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

try:
    from scripts.prepare_qa_review import QAReviewPreparationError, validate_packet
except ModuleNotFoundError:
    from prepare_qa_review import QAReviewPreparationError, validate_packet


DEFAULT_DRAFT = Path("data/qa_draft.json")
DEFAULT_CORPUS = Path("data/corpus.jsonl")
DEFAULT_QRELS = Path("data/qrels_v2.json")
DEFAULT_OUTPUT = Path("QA-REVIEW.md")


class QAReviewRenderError(RuntimeError):
    pass


def load(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise QAReviewRenderError(f"Cannot read draft: {exc}") from exc
    if not isinstance(value, dict):
        raise QAReviewRenderError("Draft must contain a JSON object")
    return value


def render(packet: dict) -> str:
    complete = all(case["human_review"]["approved"] for case in packet["cases"])
    review_state = (
        "**Human review complete—ready to freeze.** Every case has explicit "
        "project-owner approval."
        if complete
        else "**Review in progress—not frozen.** Do not use these cases for RAG "
        "tuning or evaluation until every case has explicit project-owner approval."
    )
    lines = [
        "# QA Oracle Human Review",
        "",
        f"> {review_state}",
        "",
        f"- Corpus SHA-256: `{packet['corpus_sha256']}`",
        f"- Qrels v2 SHA-256: `{packet['qrels_v2_sha256']}`",
        "- Development: `qa01`–`qa10`, `qa16`–`qa18` (10 answerable / 3 unanswerable)",
        "- Holdout: `qa11`–`qa15`, `qa19`–`qa20` (5 answerable / 2 unanswerable)",
        "",
        "## Review instructions",
        "",
        "Read every cited abstract span. Approve, edit, or reject each case; verify "
        "that an answerable answer says no more than its support, and that an "
        "unanswerable case has no sufficient direct corpus evidence. Strict lexical "
        "checks are deterministic but not exhaustive.",
        "",
    ]
    for case in packet["cases"]:
        review = case["human_review"]
        approved = "x" if review["approved"] else " "
        lines += [
            f"## {case['id']} — {case['answerability']} ({case['split']})",
            "",
            f"**Question:** {case['question']}",
            "",
            f"- Decision: [{approved}] Approve  [ ] Edit  [ ] Reject",
            f"- Reviewer: {review['reviewer'] or 'TBD'}",
            f"- Notes: {review['notes'] or 'TBD'}",
            "",
        ]
        if case["answerability"] == "answerable":
            sources = ", ".join(
                f"[PMID {pmid}](https://pubmed.ncbi.nlm.nih.gov/{pmid}/)"
                for pmid in case["pmids"]
            )
            lines += [
                f"- Sources: {sources}",
                f"- Acceptable answer: {case['acceptable_answer']}",
            ]
            for number, span in enumerate(case["evidence_spans"], 1):
                lines += [
                    f"- Exact support {number}: PMID `{span['pmid']}` offsets "
                    f"`{span['start']}:{span['end']}`; SHA-256: `{span['sha256']}`",
                    "",
                    f"### Exact abstract support {number}",
                    "",
                    span["text"].rstrip(),
                    "",
                ]
        else:
            check = case["lexical_absence_check"]
            matches = check.get("matching_pmids", [])
            audited = check.get("audited_pmids", [])
            match_summary = (
                "Strict conjunction candidates requiring manual review: "
                + ", ".join(f"`{pmid}`" for pmid in matches)
                if matches
                else "Strict conjunction matches: none."
            )
            lines += [
                "- Expected response: Insufficient evidence in this frozen abstract corpus.",
                f"- Strict query tokens: peptide `{', '.join(check['peptide_tokens'])}`; "
                f"claim `{', '.join(check['claim_tokens'])}`.",
                f"- {match_summary}",
                "- Manually audited PMIDs: "
                + (", ".join(f"`{pmid}`" for pmid in audited) if audited else "TBD"),
                f"- Caveat: {check['limitation']}",
                "",
            ]
    return "\n".join(lines).rstrip() + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draft", type=Path, default=DEFAULT_DRAFT)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--qrels", type=Path, default=DEFAULT_QRELS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.output.exists() and not args.overwrite:
            raise QAReviewRenderError(f"Output already exists: {args.output}; use --overwrite")
        packet = load(args.draft)
        validate_packet(packet, args.corpus, args.qrels)
        content = render(packet)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", newline="\n", dir=args.output.parent, delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(content)
        os.replace(temporary, args.output)
    except (OSError, QAReviewPreparationError, QAReviewRenderError, KeyError, TypeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {len(packet['cases'])} QA review cases to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Render the blind owner-judge worksheet as readable Markdown."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORKSHEET = ROOT / "data/judge_validation_v2_5_worksheet.json"
DEFAULT_OUTPUT = ROOT / "JUDGE-VALIDATION-REVIEW.md"
PACKET_FIELDS = {
    "version",
    "purpose",
    "rubric",
    "sample",
    "source_outputs_sha256",
    "qa_sha256",
    "contexts_sha256",
}
SAMPLE_FIELDS = {
    "sample_id",
    "question",
    "retrieved_evidence",
    "answer",
    "owner_label",
}
EVIDENCE_FIELDS = {
    "citation_id",
    "chunk_id",
    "pmid",
    "title",
    "text",
    "start_char",
    "end_char",
}
ANSWER_FIELDS = {"status", "text", "citations"}
CITATION_FIELDS = {"citation_id", "pmid", "chunk_id", "title"}
OWNER_LABEL_FIELDS = {"reviewer", "faithful", "relevant", "citations_correct", "refusal_correct"}


class RenderError(RuntimeError):
    """Raised when the blind packet cannot be rendered safely."""


def _load(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RenderError(f"cannot read {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RenderError("worksheet must be a JSON object")
    return payload


def _escaped(value: str) -> str:
    return html.escape(value, quote=False)


def _code(value: str) -> str:
    return _escaped(value).replace("`", "&#96;")


def _blockquote(value: str) -> str:
    lines = _escaped(value).splitlines() or [""]
    return "\n".join(f"> {line}" for line in lines)


def _valid_hash(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789ABCDEF" for character in value)
    )


def _valid_sample_id(value: Any) -> bool:
    return (
        isinstance(value, str)
        and value.startswith("review-")
        and len(value) == 23
        and all(character in "0123456789ABCDEF" for character in value[7:])
    )


def render_markdown(packet: dict[str, Any]) -> str:
    if set(packet) != PACKET_FIELDS:
        raise RenderError("worksheet contains unexpected root fields")
    if packet.get("version") != 4:
        raise RenderError("renderer requires blind worksheet version 4")
    for field in ("source_outputs_sha256", "qa_sha256", "contexts_sha256"):
        if not _valid_hash(packet.get(field)):
            raise RenderError(f"worksheet has an invalid {field}")
    sample = packet.get("sample")
    if not isinstance(sample, list) or len(sample) != 10:
        raise RenderError("worksheet must contain exactly ten samples")

    lines = [
        "# Blind Owner Judge Validation",
        "",
        "Review only the displayed question, system response, and retrieved evidence.",
        "The oracle target and automated verdict are deliberately hidden.",
        "",
        "For an answered response, label `faithful`, `relevant`,",
        "`citations_correct`, and `refusal_correct` as `true` or `false`.",
        "For a refusal, leave `faithful` and `citations_correct` as `null`, then",
        "label `relevant` and `refusal_correct` from the evidence shown.",
        "",
        f"Canonical packet SHA-256: `{hashlib.sha256(json.dumps(packet, sort_keys=True).encode('utf-8')).hexdigest().upper()}`",
        "",
    ]
    seen: set[str] = set()
    for number, item in enumerate(sample, 1):
        if not isinstance(item, dict) or set(item) != SAMPLE_FIELDS:
            raise RenderError("worksheet contains unexpected sample fields")
        sample_id = item.get("sample_id")
        question = item.get("question")
        answer = item.get("answer")
        evidence = item.get("retrieved_evidence")
        label = item.get("owner_label")
        if (
            not _valid_sample_id(sample_id)
            or sample_id in seen
            or not isinstance(question, str)
            or not isinstance(answer, dict)
            or set(answer) != ANSWER_FIELDS
            or not isinstance(evidence, list)
            or not evidence
            or not isinstance(label, dict)
            or set(label) != OWNER_LABEL_FIELDS
        ):
            raise RenderError("worksheet sample is malformed")
        seen.add(sample_id)
        status, answer_text, citations = (
            answer.get("status"),
            answer.get("text"),
            answer.get("citations"),
        )
        if (
            status not in {"answered", "insufficient_evidence"}
            or not isinstance(answer_text, str)
            or not isinstance(citations, list)
        ):
            raise RenderError(f"answer is malformed for {sample_id}")

        lines.extend([
            f"## {number}. {_escaped(sample_id)}",
            "",
            "### Question",
            "",
            _blockquote(question),
            "",
            f"### System response (`{status}`)",
            "",
            _blockquote(answer_text),
            "",
        ])
        if citations:
            lines.extend(["### Citations returned", ""])
            for citation in citations:
                if not isinstance(citation, dict) or set(citation) != CITATION_FIELDS:
                    raise RenderError(f"citation is malformed for {sample_id}")
                citation_id = citation.get("citation_id")
                pmid = citation.get("pmid")
                title = citation.get("title")
                chunk_id = citation.get("chunk_id")
                if (
                    isinstance(citation_id, bool)
                    or not isinstance(citation_id, int)
                    or not isinstance(pmid, str)
                    or not isinstance(title, str)
                    or not isinstance(chunk_id, str)
                ):
                    raise RenderError(f"citation is malformed for {sample_id}")
                lines.append(
                    f"- [{citation_id}] PMID {_escaped(pmid)}, `{_code(chunk_id)}` — {_escaped(title)}"
                )
            lines.append("")

        lines.extend(["### Retrieved evidence", ""])
        for passage in evidence:
            if not isinstance(passage, dict) or set(passage) != EVIDENCE_FIELDS:
                raise RenderError(f"evidence is malformed for {sample_id}")
            citation_id = passage.get("citation_id")
            pmid = passage.get("pmid")
            title = passage.get("title")
            text = passage.get("text")
            chunk_id = passage.get("chunk_id")
            if (
                isinstance(citation_id, bool)
                or not isinstance(citation_id, int)
                or not all(isinstance(value, str) for value in (pmid, title, text, chunk_id))
            ):
                raise RenderError(f"evidence is malformed for {sample_id}")
            lines.extend([
                f"#### [{citation_id}] PMID {_escaped(pmid)} — {_escaped(title)}",
                "",
                f"Chunk: `{_code(chunk_id)}`",
                "",
                _blockquote(text),
                "",
            ])

        reviewer = label.get("reviewer")
        if not isinstance(reviewer, str):
            raise RenderError(f"owner label is malformed for {sample_id}")
        rendered_labels: dict[str, str] = {}
        for field in ("faithful", "relevant", "citations_correct", "refusal_correct"):
            value = label.get(field)
            if value is None:
                rendered_labels[field] = (
                    "null"
                    if reviewer and status == "insufficient_evidence" and field in {"faithful", "citations_correct"}
                    else "TBD"
                )
            elif isinstance(value, bool):
                rendered_labels[field] = str(value).lower()
            else:
                raise RenderError(f"owner label is malformed for {sample_id}")
        lines.extend([
            "### Owner labels",
            "",
            f"- Reviewer: `{_code(reviewer) if reviewer else 'TBD'}`",
            f"- Faithful: `{rendered_labels['faithful']}`",
            f"- Relevant: `{rendered_labels['relevant']}`",
            f"- Citations correct: `{rendered_labels['citations_correct']}`",
            f"- Refusal correct: `{rendered_labels['refusal_correct']}`",
            "",
        ])
    return "\n".join(lines).rstrip() + "\n"


def write_atomic(path: Path, text: str, *, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise RenderError(f"refusing to overwrite existing file: {path}; pass --overwrite")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        text=True,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worksheet", type=Path, default=DEFAULT_WORKSHEET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    try:
        write_atomic(
            args.output,
            render_markdown(_load(args.worksheet)),
            overwrite=args.overwrite,
        )
    except (OSError, RenderError, TypeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote blind owner-review Markdown to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

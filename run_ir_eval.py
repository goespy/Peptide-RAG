#!/usr/bin/env python3
"""Run reproducible Boolean/BM25 evaluation against the frozen qrels."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import platform
from pathlib import Path
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from typing import Any

from run_day1 import load_qrels, sha256, validate_corpus_binding
from src.bm25 import BM25Config, rank_bm25
from src.boolean import search_boolean
from src.index import InvertedIndex
from src.metrics import EvaluationReport, evaluate_run, render_markdown


DEFAULT_CORPUS = Path("data/corpus.jsonl")
DEFAULT_QRELS = Path("data/qrels_v2.json")
DEFAULT_JSON_OUTPUT = Path("artifacts/section3/baseline.json")
DEFAULT_MARKDOWN_OUTPUT = Path("artifacts/section3/baseline.md")
DEFAULT_CUTOFFS = (1, 3, 5, 10)


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", newline="\n", dir=path.parent, delete=False
        ) as output:
            output.write(content)
            temporary_path = Path(output.name)
        temporary_path.replace(path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def _git_revision() -> tuple[str, bool | None]:
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain", "--untracked-files=no"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        )
        return revision, dirty
    except (OSError, subprocess.CalledProcessError):
        return "unavailable", None


def _rankings(
    index: InvertedIndex,
    qrels: dict[str, Any],
    mode: str,
    config: BM25Config,
) -> dict[str, list[str]]:
    rankings: dict[str, list[str]] = {}
    for entry in qrels["queries"]:
        query_id = entry["id"]
        query = entry["query"]
        if mode == "boolean":
            rankings[query_id] = search_boolean(index, query)
        elif mode == "bm25":
            rankings[query_id] = [
                result.doc_id
                for result in rank_bm25(
                    index, query, k=max(1, len(index.documents)), config=config
                )
            ]
        else:  # protected by the CLI and retained for programmatic callers
            raise ValueError(f"unsupported retrieval mode: {mode}")
    return rankings


def _render_report_markdown(
    metadata: dict[str, Any], reports: dict[str, EvaluationReport]
) -> str:
    lines = [
        "# Section 3 Retrieval Baseline",
        "",
        f"- Generated: `{metadata['generated_at']}`",
        f"- Corpus SHA-256: `{metadata['corpus_sha256']}`",
        f"- Qrels SHA-256: `{metadata['qrels_sha256']}`",
        f"- Qrels version: `{metadata['qrels_version']}`",
        f"- Source revision: `{metadata['source_revision']}`",
        f"- Source worktree dirty: `{str(metadata['source_dirty']).lower()}`",
        f"- Documents: `{metadata['document_count']}`",
        f"- Vocabulary terms: `{metadata['vocabulary_size']}`",
        f"- BM25: Lucene variant, `k1={metadata['bm25']['k1']}`, `b={metadata['bm25']['b']}`",
        "",
    ]
    for mode, report in reports.items():
        lines.extend([f"## {mode.upper()}", ""])
        rendered = render_markdown(report.results, report.cutoffs)
        rendered = rendered.replace("## Retrieval Metrics\n\n", "", 1)
        lines.append(rendered.rstrip())
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def run(
    corpus: Path,
    qrels_path: Path,
    modes: Sequence[str],
    cutoffs: Sequence[int] = DEFAULT_CUTOFFS,
    config: BM25Config = BM25Config(),
) -> tuple[dict[str, Any], str]:
    qrels = load_qrels(qrels_path)
    corpus_hash = validate_corpus_binding(corpus, qrels)
    index = InvertedIndex.from_jsonl(corpus)
    # Validate the complete qrels shape before the retrieval loop accesses it.
    evaluate_run(qrels, {}, cutoffs)
    revision, dirty = _git_revision()
    reports: dict[str, EvaluationReport] = {}
    ranking_payload: dict[str, dict[str, list[str]]] = {}
    for mode in dict.fromkeys(modes):
        mode_rankings = _rankings(index, qrels, mode, config)
        ranking_payload[mode] = mode_rankings
        reports[mode] = evaluate_run(qrels, mode_rankings, cutoffs)

    metadata = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "command": "python run_ir_eval.py --qrels data/qrels_v2.json --modes "
        + ",".join(dict.fromkeys(modes)),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "source_revision": revision,
        "source_dirty": dirty,
        "corpus_path": str(corpus).replace("\\", "/"),
        "corpus_sha256": corpus_hash,
        "qrels_path": str(qrels_path).replace("\\", "/"),
        "qrels_sha256": sha256(qrels_path),
        "qrels_version": qrels.get("version"),
        "document_count": len(index.documents),
        "vocabulary_size": len(index.postings),
        "cutoffs": list(cutoffs),
        "bm25": {"variant": "lucene", "k1": config.k1, "b": config.b},
    }
    payload = {
        "metadata": metadata,
        "runs": {
            mode: {
                "rankings": ranking_payload[mode],
                "evaluation": reports[mode].to_dict(),
            }
            for mode in reports
        },
    }
    return payload, _render_report_markdown(metadata, reports)


def _positive_integer(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("cutoff must be an integer") from error
    if parsed <= 0:
        raise argparse.ArgumentTypeError("cutoff must be greater than zero")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--qrels", type=Path, default=DEFAULT_QRELS)
    parser.add_argument(
        "--modes",
        default="boolean,bm25",
        help="Comma-separated subset of boolean,bm25",
    )
    parser.add_argument(
        "--cutoffs", type=_positive_integer, nargs="+", default=list(DEFAULT_CUTOFFS)
    )
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON_OUTPUT)
    parser.add_argument("--markdown-output", type=Path, default=DEFAULT_MARKDOWN_OUTPUT)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    modes = tuple(part.strip() for part in args.modes.split(",") if part.strip())
    if not modes or any(mode not in {"boolean", "bm25"} for mode in modes):
        print("Error: modes must be a comma-separated subset of boolean,bm25", file=sys.stderr)
        return 1
    try:
        payload, markdown = run(
            args.corpus,
            args.qrels,
            modes,
            tuple(dict.fromkeys(args.cutoffs)),
        )
        _atomic_write(
            args.json_output,
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        )
        _atomic_write(args.markdown_output, markdown)
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    print(markdown, end="")
    print(f"JSON: {args.json_output}")
    print(f"Markdown: {args.markdown_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

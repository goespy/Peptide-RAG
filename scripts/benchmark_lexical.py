"""Reproducible timing and allocation measurements for the lexical baseline.

The defaults intentionally mirror the Section 4 protocol: five independent
cold builds, one retrieval warm-up, and 100 retrievals for every frozen qrels
query.  Smaller values are exposed for automated tests and local smoke checks.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import statistics
import sys
import tempfile
import time
import tracemalloc
from typing import Callable, TypeVar

from src.bm25 import BM25Config, rank_bm25
from src.index import InvertedIndex


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CORPUS = ROOT / "data" / "corpus.jsonl"
DEFAULT_QRELS = ROOT / "data" / "qrels_v2.json"
DEFAULT_JSON = ROOT / "artifacts" / "section4" / "benchmark_lexical.json"
DEFAULT_MARKDOWN = ROOT / "artifacts" / "section4" / "benchmark_lexical.md"
T = TypeVar("T")


def _sha256(path: Path) -> str:
    """Return the content hash used to identify a benchmark input."""

    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def _percentile(values: list[float], percent: float) -> float:
    """Return a linearly interpolated percentile for a non-empty sample."""

    if not values:
        raise ValueError("cannot calculate a percentile of an empty sample")
    ordered = sorted(values)
    position = (len(ordered) - 1) * percent / 100
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _measure(operation: Callable[[], T]) -> tuple[T, float, int]:
    """Run one operation and return its result, duration, and allocation peak."""

    tracemalloc.start()
    try:
        tracemalloc.reset_peak()
        started = time.perf_counter()
        result = operation()
        elapsed_ms = (time.perf_counter() - started) * 1_000
        _, peak_bytes = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return result, elapsed_ms, peak_bytes


def _summary(samples: list[float]) -> dict[str, float]:
    return {
        "median_ms": statistics.median(samples),
        "p95_ms": _percentile(samples, 95),
    }


def _atomic_write(path: Path, content: str) -> None:
    """Atomically replace a UTF-8 report, leaving no partially written file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", text=True
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as target:
            target.write(content)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def run_benchmark(
    corpus_path: Path,
    qrels_path: Path,
    *,
    build_runs: int = 5,
    query_runs: int = 100,
    warmup_runs: int = 1,
    config: BM25Config = BM25Config(),
) -> dict[str, object]:
    """Measure cold index builds and repeated ranking of every qrels query."""

    if any(isinstance(value, bool) or not isinstance(value, int) or value <= 0
           for value in (build_runs, query_runs, warmup_runs)):
        raise ValueError("build-runs, query-runs, and warmup-runs must be positive integers")
    if not isinstance(config, BM25Config):
        raise ValueError("config must be a BM25Config")

    corpus_path = Path(corpus_path)
    qrels_path = Path(qrels_path)
    qrels = json.loads(qrels_path.read_text(encoding="utf-8"))
    queries = qrels.get("queries") if isinstance(qrels, dict) else None
    if not isinstance(queries, list) or not all(
        isinstance(item, dict) and isinstance(item.get("id"), str) and isinstance(item.get("query"), str)
        for item in queries
    ):
        raise ValueError("qrels must contain queries with string id and query fields")
    if len({entry["id"] for entry in queries}) != len(queries):
        raise ValueError("qrels query ids must be unique")

    build_samples: list[float] = []
    build_peaks: list[int] = []
    index: InvertedIndex | None = None
    for _ in range(build_runs):
        index, elapsed_ms, peak_bytes = _measure(lambda: InvertedIndex.from_jsonl(corpus_path))
        build_samples.append(elapsed_ms)
        build_peaks.append(peak_bytes)
    assert index is not None

    for _ in range(warmup_runs):
        for entry in queries:
            rank_bm25(index, entry["query"], k=10, config=config)

    query_samples: list[float] = []
    query_peaks: list[int] = []
    per_query: dict[str, dict[str, float | int]] = {}
    for entry in queries:
        samples_for_query: list[float] = []
        peaks_for_query: list[int] = []
        for _ in range(query_runs):
            _, elapsed_ms, peak_bytes = _measure(
                lambda query=entry["query"]: rank_bm25(index, query, k=10, config=config)
            )
            query_samples.append(elapsed_ms)
            query_peaks.append(peak_bytes)
            samples_for_query.append(elapsed_ms)
            peaks_for_query.append(peak_bytes)
        per_query[entry["id"]] = {
            **_summary(samples_for_query),
            "peak_memory_bytes": max(peaks_for_query),
        }

    return {
        "schema_version": 1,
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "corpus_path": str(corpus_path),
            "corpus_sha256": _sha256(corpus_path),
            "qrels_path": str(qrels_path),
            "qrels_sha256": _sha256(qrels_path),
            "query_count": len(queries),
        },
        "configuration": {
            "bm25": asdict(config),
            "build_runs": build_runs,
            "warmup_runs": warmup_runs,
            "query_runs_per_query": query_runs,
            "clock": "time.perf_counter",
            "memory_tracer": "tracemalloc",
            "percentile_method": "linear interpolation",
        },
        "environment": {
            "python": sys.version,
            "python_implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "machine": platform.machine(),
        },
        "measurements": {
            "build": {**_summary(build_samples), "peak_memory_bytes": max(build_peaks)},
            "query": {
                **_summary(query_samples),
                "peak_memory_bytes": max(query_peaks),
                "per_query": per_query,
            },
            "peak_memory_bytes": max(build_peaks + query_peaks),
        },
    }


def render_markdown(report: dict[str, object]) -> str:
    """Render a concise, human-readable companion for a JSON report."""

    inputs = report["inputs"]  # type: ignore[index]
    configuration = report["configuration"]  # type: ignore[index]
    measurements = report["measurements"]  # type: ignore[index]
    build = measurements["build"]  # type: ignore[index]
    query = measurements["query"]  # type: ignore[index]
    return "\n".join((
        "# Section 4 lexical benchmark",
        "",
        f"Recorded: `{report['recorded_at_utc']}`",
        "",
        f"Corpus SHA-256: `{inputs['corpus_sha256']}`  ",
        f"Qrels SHA-256: `{inputs['qrels_sha256']}`  ",
        f"Queries: {inputs['query_count']}  ",
        f"BM25: `k1={configuration['bm25']['k1']}`, `b={configuration['bm25']['b']}`",
        "",
        "| Operation | Samples | Median (ms) | p95 (ms) | Peak memory (bytes) |",
        "|---|---:|---:|---:|---:|",
        f"| Cold build | {configuration['build_runs']} | {build['median_ms']:.3f} | {build['p95_ms']:.3f} | {build['peak_memory_bytes']} |",
        f"| Query | {inputs['query_count']} x {configuration['query_runs_per_query']} | {query['median_ms']:.3f} | {query['p95_ms']:.3f} | {query['peak_memory_bytes']} |",
        "",
        "Timing uses `time.perf_counter`; peak allocations use `tracemalloc`. "
        "This report records observations only and defines no performance pass threshold.",
        "",
    ))


def write_reports(report: dict[str, object], json_path: Path, markdown_path: Path) -> None:
    """Atomically write matching machine- and human-readable benchmark reports."""

    _atomic_write(Path(json_path), json.dumps(report, indent=2, sort_keys=True) + "\n")
    _atomic_write(Path(markdown_path), render_markdown(report))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--qrels", type=Path, default=DEFAULT_QRELS)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--output-markdown", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument("--build-runs", type=int, default=5)
    parser.add_argument("--query-runs", type=int, default=100)
    parser.add_argument("--warmup-runs", type=int, default=1)
    arguments = parser.parse_args(argv)
    report = run_benchmark(
        arguments.corpus, arguments.qrels,
        build_runs=arguments.build_runs,
        query_runs=arguments.query_runs,
        warmup_runs=arguments.warmup_runs,
    )
    write_reports(report, arguments.output_json, arguments.output_markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

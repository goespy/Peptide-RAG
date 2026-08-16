#!/usr/bin/env python3
"""Measure the offline service startup footprint with the frozen embedding cache."""

from __future__ import annotations

import argparse
import ctypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import time
from typing import Any, Callable, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.service import LocalResearchService  # noqa: E402


class ServiceBenchmarkError(ValueError):
    """Raised when a service-memory measurement cannot be trusted."""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def process_memory_bytes() -> tuple[int, int]:
    """Return current and peak resident bytes for this process."""

    if os.name == "nt":
        from ctypes import wintypes

        class ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        get_current_process = ctypes.windll.kernel32.GetCurrentProcess
        get_process_memory_info = ctypes.windll.psapi.GetProcessMemoryInfo
        get_current_process.argtypes = []
        get_current_process.restype = wintypes.HANDLE
        get_process_memory_info.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(ProcessMemoryCounters),
            wintypes.DWORD,
        ]
        get_process_memory_info.restype = wintypes.BOOL
        if not get_process_memory_info(
            get_current_process(), ctypes.byref(counters), counters.cb
        ):
            raise OSError(ctypes.get_last_error(), "GetProcessMemoryInfo failed")
        return int(counters.WorkingSetSize), int(counters.PeakWorkingSetSize)

    status = Path("/proc/self/status")
    if status.exists():
        values: dict[str, int] = {}
        for line in status.read_text(encoding="utf-8").splitlines():
            key, separator, value = line.partition(":")
            if separator and key in {"VmRSS", "VmHWM"}:
                pieces = value.strip().split()
                if pieces and pieces[0].isdigit():
                    values[key] = int(pieces[0]) * 1024
        if "VmRSS" in values:
            return values["VmRSS"], values.get("VmHWM", values["VmRSS"])

    try:
        import resource

        peak = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        if platform.system() != "Darwin":
            peak *= 1024
        return peak, peak
    except (ImportError, OSError, ValueError) as exc:
        raise ServiceBenchmarkError("resident-memory measurement is unavailable") from exc


def build_report(
    *,
    cache_path: Path,
    service_factory: Callable[..., Any] = LocalResearchService,
    memory_sampler: Callable[[], tuple[int, int]] = process_memory_bytes,
    clock: Callable[[], float] = time.perf_counter,
    measured_at: str | None = None,
) -> dict[str, Any]:
    cache_path = Path(cache_path)
    if not cache_path.is_file():
        raise ServiceBenchmarkError(f"embedding cache does not exist: {cache_path}")
    before_rss, before_peak = memory_sampler()
    started = clock()
    service = service_factory(embedding_cache_path=cache_path)
    elapsed_ms = (clock() - started) * 1_000
    after_rss, after_peak = memory_sampler()
    metrics = service.metrics()
    if not isinstance(metrics, dict) or metrics.get("semantic_available") is not True:
        raise ServiceBenchmarkError("frozen semantic service did not activate")
    if min(before_rss, before_peak, after_rss, after_peak) < 0 or elapsed_ms < 0:
        raise ServiceBenchmarkError("invalid process measurement")
    return {
        "schema_version": 1,
        "measured_at_utc": measured_at
        or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "cache_path": cache_path.relative_to(ROOT).as_posix()
        if cache_path.is_relative_to(ROOT)
        else str(cache_path),
        "cache_sha256": sha256(cache_path),
        "service_sha256": sha256(ROOT / "src" / "service.py"),
        "corpus_sha256": sha256(ROOT / "data" / "corpus.jsonl"),
        "startup_ms": elapsed_ms,
        "rss_before_bytes": before_rss,
        "rss_after_bytes": after_rss,
        "rss_delta_bytes": after_rss - before_rss,
        "peak_rss_bytes": max(before_peak, after_peak),
        "documents": metrics.get("corpus_documents"),
        "semantic_available": True,
        "generation_available": bool(metrics.get("generation_available")),
        "network_calls": 0,
        "scope": "single cold service initialization on the recorded development machine",
    }


def render_markdown(report: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Service Memory Benchmark",
            "",
            f"- Measured: `{report['measured_at_utc']}`",
            f"- Platform: `{report['platform']}`",
            f"- Python: `{report['python_version']}`",
            f"- Cache: `{report['cache_path']}`",
            f"- Documents: `{report['documents']}`",
            f"- Startup: `{report['startup_ms']:.3f} ms`",
            f"- RSS before load: `{report['rss_before_bytes']:,} bytes`",
            f"- RSS after load: `{report['rss_after_bytes']:,} bytes`",
            f"- RSS delta: `{report['rss_delta_bytes']:,} bytes`",
            f"- Peak process RSS: `{report['peak_rss_bytes']:,} bytes`",
            f"- Semantic retrieval available: `{str(report['semantic_available']).lower()}`",
            f"- Grounded generation available: `{str(report['generation_available']).lower()}`",
            "- Provider calls: `0`",
            "",
            "This is an observed cold-start footprint on one development machine, not a",
            "Railway service-level guarantee. Railway memory must still be checked after deployment.",
            "",
        ]
    )


def write_atomic(path: Path, text: str, *, overwrite: bool) -> None:
    path = Path(path)
    if path.exists() and not overwrite:
        raise ServiceBenchmarkError(f"refusing to overwrite existing file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(text, encoding="utf-8", newline="\n")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cache",
        type=Path,
        default=ROOT / "artifacts" / "section5" / "embeddings_256_64.npz",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "artifacts" / "section6" / "service_memory.json",
    )
    parser.add_argument(
        "--markdown",
        type=Path,
        default=ROOT / "artifacts" / "section6" / "service_memory.md",
    )
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.output.resolve() == args.markdown.resolve():
            raise ServiceBenchmarkError("JSON and Markdown outputs must differ")
        if (args.output.exists() or args.markdown.exists()) and not args.overwrite:
            raise ServiceBenchmarkError("refusing to overwrite existing benchmark output")
        report = build_report(cache_path=args.cache)
        write_atomic(
            args.output,
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            overwrite=args.overwrite,
        )
        try:
            write_atomic(args.markdown, render_markdown(report), overwrite=args.overwrite)
        except Exception:
            args.output.unlink(missing_ok=True)
            raise
    except (OSError, ServiceBenchmarkError, TypeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

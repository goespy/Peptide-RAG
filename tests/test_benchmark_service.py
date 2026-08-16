import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts.benchmark_service import (
    ServiceBenchmarkError,
    build_report,
    main,
    render_markdown,
    source_sha256,
)


class FakeService:
    def __init__(self, *, embedding_cache_path):
        self.cache = embedding_cache_path

    def metrics(self):
        return {
            "corpus_documents": 2_000,
            "semantic_available": True,
            "generation_available": False,
        }


class ServiceBenchmarkTests(unittest.TestCase):
    def test_source_hash_is_stable_across_lf_and_crlf_checkouts(self):
        with TemporaryDirectory() as temp:
            directory = Path(temp)
            lf = directory / "lf.py"
            crlf = directory / "crlf.py"
            lf.write_bytes(b"first\nsecond\n")
            crlf.write_bytes(b"first\r\nsecond\r\n")
            self.assertEqual(source_sha256(lf), source_sha256(crlf))

    def test_report_records_offline_service_footprint(self):
        with TemporaryDirectory() as temp:
            cache = Path(temp) / "cache.npz"
            cache.write_bytes(b"cache")
            memory = iter(((100, 120), (350, 400)))
            clock = iter((1.0, 1.25))
            report = build_report(
                cache_path=cache,
                service_factory=FakeService,
                memory_sampler=lambda: next(memory),
                clock=lambda: next(clock),
                measured_at="2026-08-16T00:00:00Z",
            )
            self.assertEqual(report["startup_ms"], 250.0)
            self.assertEqual(report["rss_delta_bytes"], 250)
            self.assertEqual(report["peak_rss_bytes"], 400)
            self.assertEqual(report["network_calls"], 0)
            self.assertFalse(report["generation_available"])
            self.assertIn("Peak process RSS: `400 bytes`", render_markdown(report))

    def test_missing_cache_and_inactive_semantic_service_fail(self):
        with TemporaryDirectory() as temp:
            missing = Path(temp) / "missing.npz"
            with self.assertRaises(ServiceBenchmarkError):
                build_report(cache_path=missing)

            cache = Path(temp) / "cache.npz"
            cache.write_bytes(b"cache")

            class Inactive(FakeService):
                def metrics(self):
                    return {"semantic_available": False}

            with self.assertRaises(ServiceBenchmarkError):
                build_report(
                    cache_path=cache,
                    service_factory=Inactive,
                    memory_sampler=lambda: (1, 1),
                    clock=lambda: 1.0,
                )

    def test_cli_writes_both_outputs_and_refuses_existing_before_measurement(self):
        with TemporaryDirectory() as temp:
            directory = Path(temp)
            cache = directory / "cache.npz"
            cache.write_bytes(b"not-a-real-cache")
            json_path = directory / "result.json"
            markdown_path = directory / "result.md"
            report = {
                "schema_version": 1,
                "measured_at_utc": "2026-08-16T00:00:00Z",
                "platform": "test",
                "python_version": "3.11",
                "cache_path": "cache.npz",
                "cache_sha256": "A" * 64,
                "service_sha256": "B" * 64,
                "corpus_sha256": "C" * 64,
                "startup_ms": 1.0,
                "rss_before_bytes": 1,
                "rss_after_bytes": 2,
                "rss_delta_bytes": 1,
                "peak_rss_bytes": 2,
                "documents": 2_000,
                "semantic_available": True,
                "generation_available": False,
                "network_calls": 0,
                "scope": "test",
            }
            with patch("scripts.benchmark_service.build_report", return_value=report) as measured:
                self.assertEqual(
                    main([
                        "--cache", str(cache),
                        "--output", str(json_path),
                        "--markdown", str(markdown_path),
                    ]),
                    0,
                )
                measured.assert_called_once()
            self.assertEqual(json.loads(json_path.read_text(encoding="utf-8")), report)
            self.assertIn("Service Memory Benchmark", markdown_path.read_text(encoding="utf-8"))

            with patch("scripts.benchmark_service.build_report") as measured:
                self.assertEqual(
                    main([
                        "--cache", str(cache),
                        "--output", str(json_path),
                        "--markdown", str(markdown_path),
                    ]),
                    1,
                )
                measured.assert_not_called()
            self.assertEqual(json.loads(json_path.read_text(encoding="utf-8")), report)


if __name__ == "__main__":
    unittest.main()

"""Small, deterministic smoke coverage for the lexical benchmark CLI."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from scripts.benchmark_lexical import main, run_benchmark


class LexicalBenchmarkTests(unittest.TestCase):
    def _write_inputs(self, directory: Path) -> tuple[Path, Path]:
        corpus = directory / "corpus.jsonl"
        qrels = directory / "qrels.json"
        corpus.write_text(
            '{"id":"1","title":"alpha","text":"beta"}\n'
            '{"id":"2","title":"gamma","text":"delta"}\n', encoding="utf-8"
        )
        qrels.write_text(
            json.dumps({"version": 1, "queries": [
                {"id": "q1", "query": "alpha"}, {"id": "q2", "query": "gamma"},
            ]}), encoding="utf-8"
        )
        return corpus, qrels

    def test_small_benchmark_records_required_metadata_and_measurements(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            corpus, qrels = self._write_inputs(Path(temporary))
            report = run_benchmark(corpus, qrels, build_runs=2, warmup_runs=1, query_runs=2)
        self.assertEqual(report["inputs"]["query_count"], 2)  # type: ignore[index]
        self.assertEqual(report["configuration"]["build_runs"], 2)  # type: ignore[index]
        self.assertEqual(report["configuration"]["query_runs_per_query"], 2)  # type: ignore[index]
        self.assertGreaterEqual(report["measurements"]["build"]["peak_memory_bytes"], 0)  # type: ignore[index]
        self.assertGreaterEqual(report["measurements"]["query"]["peak_memory_bytes"], 0)  # type: ignore[index]
        self.assertEqual(set(report["measurements"]["query"]["per_query"]), {"q1", "q2"})  # type: ignore[index]

    def test_cli_writes_json_and_markdown_reports_with_small_counts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            corpus, qrels = self._write_inputs(directory)
            json_path, markdown_path = directory / "report.json", directory / "report.md"
            config_path = directory / "config.json"
            config_path.write_text(json.dumps({
                "analysis": {"name": "baseline"},
                "bm25": {"variant": "lucene", "k1": 0.8, "b": 0.75, "proximity_boost": 0.0},
            }), encoding="utf-8")
            self.assertEqual(main([
                "--corpus", str(corpus), "--qrels", str(qrels),
                "--config", str(config_path),
                "--output-json", str(json_path), "--output-markdown", str(markdown_path),
                "--build-runs", "1", "--warmup-runs", "1", "--query-runs", "1",
            ]), 0)
            report = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(report["configuration"]["build_runs"], 1)
            self.assertIn("Cold build", markdown_path.read_text(encoding="utf-8"))

    def test_invalid_run_counts_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            corpus, qrels = self._write_inputs(Path(temporary))
            with self.assertRaises(ValueError):
                run_benchmark(corpus, qrels, build_runs=0, warmup_runs=1, query_runs=1)


if __name__ == "__main__":
    unittest.main()

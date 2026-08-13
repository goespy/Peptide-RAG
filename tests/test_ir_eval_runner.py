from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from run_ir_eval import main, run


class IRRunnerTests(unittest.TestCase):
    def _fixture(self, root: Path) -> tuple[Path, Path]:
        corpus = root / "corpus.jsonl"
        records = [
            {"id": "10", "title": "alpha alpha", "text": "common"},
            {"id": "2", "title": "beta", "text": "common"},
            {"id": "3", "title": "gamma", "text": ""},
        ]
        corpus.write_text(
            "".join(json.dumps(record) + "\n" for record in records),
            encoding="utf-8",
        )
        corpus_hash = hashlib.sha256(corpus.read_bytes()).hexdigest().upper()
        qrels = root / "qrels.json"
        qrels.write_text(
            json.dumps(
                {
                    "version": 2,
                    "corpus_sha256": corpus_hash,
                    "queries": [
                        {
                            "id": "q1",
                            "query": "alpha beta",
                            "judgments": {"10": 2, "2": 1, "3": 0},
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        return corpus, qrels

    def test_run_evaluates_both_modes_and_records_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            corpus, qrels = self._fixture(Path(directory))
            with patch("run_ir_eval._git_revision", return_value=("abc123", False)):
                payload, markdown = run(corpus, qrels, ("boolean", "bm25"))

            self.assertEqual(set(payload["runs"]), {"boolean", "bm25"})
            self.assertEqual(payload["metadata"]["source_revision"], "abc123")
            self.assertEqual(payload["metadata"]["document_count"], 3)
            self.assertIn("Mean NDCG@10", markdown)
            self.assertIn("## BM25", markdown)

    def test_main_writes_json_and_markdown_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            corpus, qrels = self._fixture(root)
            json_output = root / "nested" / "metrics.json"
            markdown_output = root / "nested" / "metrics.md"
            with patch("run_ir_eval._git_revision", return_value=("abc123", False)):
                code = main(
                    [
                        "--corpus",
                        str(corpus),
                        "--qrels",
                        str(qrels),
                        "--modes",
                        "bm25",
                        "--json-output",
                        str(json_output),
                        "--markdown-output",
                        str(markdown_output),
                    ]
                )

            self.assertEqual(code, 0)
            self.assertEqual(set(json.loads(json_output.read_text())["runs"]), {"bm25"})
            self.assertIn("# Section 3 Retrieval Baseline", markdown_output.read_text())

    def test_invalid_mode_fails_without_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "metrics.json"
            code = main(["--modes", "semantic", "--json-output", str(output)])
            self.assertEqual(code, 1)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()

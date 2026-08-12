from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from run_day1 import Day1Error, run, validate_corpus_binding


class Day1RunnerTests(unittest.TestCase):
    def test_run_builds_index_and_renders_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            corpus = root / "corpus.jsonl"
            records = [
                {"id": "10", "title": "BPC-157 liver", "text": "rat healing"},
                {"id": "2", "title": "GHK-Cu skin", "text": "wound healing"},
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
                        "version": 1,
                        "corpus_sha256": corpus_hash,
                        "queries": [
                            {
                                "id": "q01",
                                "query": "BPC 157 liver",
                                "judgments": {"10": 2},
                                "rationale": "Known item",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            output = run(corpus, qrels, (1, 3))

            self.assertIn("Indexed documents: 2", output)
            self.assertIn("Vocabulary terms:", output)
            self.assertIn("Mean Precision@1", output)
            self.assertIn("q01", output)

    def test_hash_mismatch_stops_evaluation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            corpus = Path(directory) / "corpus.jsonl"
            corpus.write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(Day1Error, "hash mismatch"):
                validate_corpus_binding(corpus, {"corpus_sha256": "0" * 64})


if __name__ == "__main__":
    unittest.main()

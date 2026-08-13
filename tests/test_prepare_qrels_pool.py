from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.prepare_qrels_pool import (
    QrelsPoolError,
    build_pool,
    corpus_sha256,
    write_json_atomic,
)


class QrelsPoolTests(unittest.TestCase):
    def _files(self, directory: str, records: list[dict[str, str]], judgments: dict[str, int]) -> tuple[Path, Path]:
        corpus = Path(directory) / "corpus.jsonl"
        corpus.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
        qrels = Path(directory) / "qrels.json"
        qrels.write_text(json.dumps({
            "version": 1,
            "corpus_sha256": corpus_sha256(corpus),
            "review": {"status": "approved_provisional_known_item_set"},
            "queries": [{"id": "q1", "query": "alpha beta", "judgments": judgments}],
        }), encoding="utf-8")
        return corpus, qrels

    def test_pool_keeps_known_judgment_then_strict_then_ranked_relaxed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            corpus, qrels = self._files(directory, [
                {"id": "30", "title": "alpha beta", "text": ""},
                {"id": "10", "title": "alpha beta", "text": ""},
                {"id": "20", "title": "alpha", "text": ""},
                {"id": "40", "title": "beta", "text": ""},
                {"id": "50", "title": "alpha", "text": ""},
            ], {"20": 2})

            payload = build_pool(corpus, qrels, 5)
            candidates = payload["queries"][0]["candidates"]  # type: ignore[index]

            self.assertEqual(payload["status"], "candidate_pool_requires_human_review")
            self.assertEqual([candidate["pmid"] for candidate in candidates], ["20", "10", "30", "40", "50"])
            self.assertEqual(candidates[0]["existing_grade"], 2)
            self.assertEqual(candidates[1]["existing_grade"], None)
            self.assertEqual(candidates[1]["discovery_sources"], ["strict_boolean"])
            self.assertEqual(candidates[3]["matched_terms"], ["beta"])

    def test_all_existing_judgments_are_kept_when_pool_is_smaller(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            corpus, qrels = self._files(directory, [
                {"id": "1", "title": "alpha", "text": ""},
                {"id": "2", "title": "beta", "text": ""},
            ], {"2": 1, "1": 2})
            payload = build_pool(corpus, qrels, 1)
            candidates = payload["queries"][0]["candidates"]  # type: ignore[index]
            self.assertEqual([candidate["pmid"] for candidate in candidates], ["2", "1"])

    def test_hash_mismatch_refuses_to_build(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            corpus, qrels = self._files(directory, [{"id": "1", "title": "alpha", "text": ""}], {"1": 2})
            raw = json.loads(qrels.read_text())
            raw["corpus_sha256"] = "0" * 64
            qrels.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaisesRegex(QrelsPoolError, "does not match"):
                build_pool(corpus, qrels, 2)

    def test_atomic_writer_refuses_overwrite_without_changing_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "qrels_pool.json"
            write_json_atomic({"status": "first"}, output, overwrite=False)
            with self.assertRaises(QrelsPoolError):
                write_json_atomic({"status": "second"}, output, overwrite=False)
            self.assertEqual(json.loads(output.read_text())["status"], "first")


if __name__ == "__main__":
    unittest.main()

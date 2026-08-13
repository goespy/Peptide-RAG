from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.freeze_qrels_v2 import QrelsFreezeError, freeze_qrels, write_atomic


class FreezeQrelsTests(unittest.TestCase):
    def _files(self, directory: str) -> tuple[Path, Path, Path]:
        root = Path(directory)
        corpus = root / "corpus.jsonl"
        corpus.write_text('{"id":"1","title":"alpha","text":"beta"}\n', encoding="utf-8")
        corpus_hash = hashlib.sha256(corpus.read_bytes()).hexdigest().upper()
        pool = root / "pool.json"
        pool.write_text(
            json.dumps(
                {
                    "status": "candidate_pool_requires_human_review",
                    "corpus_sha256": corpus_hash,
                    "queries": [
                        {
                            "id": "q1",
                            "query": "alpha",
                            "candidates": [{"pmid": "1"}],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        review = root / "review.json"
        review.write_text(
            json.dumps(
                {
                    "status": "human_pool_review_complete",
                    "corpus_sha256": corpus_hash,
                    "target_qrels_version": 2,
                    "consistency_audit": {"changes": []},
                    "queries": [
                        {
                            "id": "q1",
                            "query": "alpha",
                            "approved": True,
                            "approved_on": "2026-08-13",
                            "reviewer": "human",
                            "judgments": {"1": {"grade": 2, "reason": "Direct."}},
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        return corpus, pool, review

    def test_freezes_numeric_qrels_with_rationales(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            payload = freeze_qrels(*self._files(directory))
            self.assertEqual(payload["version"], 2)
            self.assertEqual(payload["queries"][0]["judgments"], {"1": 2})
            self.assertEqual(payload["queries"][0]["judgment_rationales"], {"1": "Direct."})

    def test_rejects_missing_candidate_judgment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            corpus, pool, review = self._files(directory)
            raw = json.loads(review.read_text(encoding="utf-8"))
            raw["queries"][0]["judgments"] = {}
            review.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaisesRegex(QrelsFreezeError, "every and only"):
                freeze_qrels(corpus, pool, review)

    def test_rejects_hash_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            corpus, pool, review = self._files(directory)
            raw = json.loads(review.read_text(encoding="utf-8"))
            raw["corpus_sha256"] = "0" * 64
            review.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaisesRegex(QrelsFreezeError, "hashes must match"):
                freeze_qrels(corpus, pool, review)

    def test_atomic_writer_refuses_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "qrels.json"
            write_atomic({"version": 2}, output, overwrite=False)
            with self.assertRaises(QrelsFreezeError):
                write_atomic({"version": 3}, output, overwrite=False)
            self.assertEqual(json.loads(output.read_text())["version"], 2)


if __name__ == "__main__":
    unittest.main()

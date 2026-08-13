from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.render_qrels_pool_review import (
    PoolReviewError,
    render_markdown,
    write_atomic,
)


def _pool() -> dict:
    return {
        "status": "candidate_pool_requires_human_review",
        "corpus_sha256": "A" * 64,
        "queries": [
            {
                "id": "q01",
                "query": "alpha healing",
                "candidates": [
                    {
                        "pmid": "123",
                        "title": "Alpha paper",
                        "abstract": "Healing evidence.",
                        "discovery_sources": ["existing_judgment", "strict_boolean"],
                        "matched_terms": ["alpha", "healing"],
                        "existing_grade": 2,
                    },
                    {
                        "pmid": "456",
                        "title": "Term-only paper",
                        "abstract": "",
                        "discovery_sources": ["relaxed_distinct_term_overlap"],
                        "matched_terms": ["alpha"],
                        "existing_grade": None,
                    },
                ],
            }
        ],
    }


class PoolReviewRendererTests(unittest.TestCase):
    def test_renders_rubric_candidates_and_empty_abstract(self) -> None:
        rendered = render_markdown(_pool())
        self.assertIn("2 — directly relevant", rendered)
        self.assertIn("PMID 123", rendered)
        self.assertIn("Existing grade: `2`", rendered)
        self.assertIn("Human grade: [ ] 0  [ ] 1  [ ] 2", rendered)
        self.assertIn("*No abstract available.*", rendered)
        self.assertIn("Candidate query-document pairs: 2", rendered)

    def test_rejects_duplicate_query_document_pair(self) -> None:
        payload = _pool()
        payload["queries"][0]["candidates"].append(
            dict(payload["queries"][0]["candidates"][0])
        )
        with self.assertRaisesRegex(PoolReviewError, "repeats PMID"):
            render_markdown(payload)

    def test_atomic_writer_refuses_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "review.md"
            write_atomic("first\n", output, overwrite=False)
            with self.assertRaises(PoolReviewError):
                write_atomic("second\n", output, overwrite=False)
            self.assertEqual(output.read_text(encoding="utf-8"), "first\n")


if __name__ == "__main__":
    unittest.main()

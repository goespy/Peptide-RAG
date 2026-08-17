from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

import search


class SearchCliTests(unittest.TestCase):
    def _corpus(self, directory: str) -> Path:
        path = Path(directory) / "corpus.jsonl"
        path.write_text(
            "".join(
                json.dumps(record) + "\n"
                for record in (
                    {"id": "10", "title": "Tendon recovery", "text": "BPC 157 supports repair."},
                    {"id": "2", "title": "BPC study", "text": "BPC 157 tendon healing evidence."},
                    {"id": "30", "title": "Unrelated", "text": "nothing useful"},
                )
            ),
            encoding="utf-8",
        )
        return path

    def test_default_bm25_prints_ranked_result_details(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            corpus = self._corpus(directory)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(search.main(["bpc tendon", "--corpus", str(corpus), "--top-k", "1"]), 0)

        rendered = output.getvalue()
        self.assertIn("1 match(es)", rendered)
        self.assertIn("1. PMID: 2 | score: ", rendered)
        self.assertIn("Title: BPC study", rendered)
        self.assertIn("Snippet: [[BPC]] 157 [[tendon]] healing evidence.", rendered)
        self.assertIn("https://pubmed.ncbi.nlm.nih.gov/2/", rendered)

    def test_boolean_mode_and_hidden_limit_alias_remain_supported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            corpus = self._corpus(directory)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(
                    search.main(["bpc OR tendon", "--mode", "boolean", "--corpus", str(corpus), "--limit", "1"]),
                    0,
                )

        self.assertEqual(output.getvalue().splitlines(), ["2 match(es)", "2\tBPC study"])

    def test_invalid_top_k_is_rejected_by_parser(self) -> None:
        with self.assertRaises(SystemExit):
            search.build_parser().parse_args(["bpc", "--top-k", "0"])


if __name__ == "__main__":
    unittest.main()

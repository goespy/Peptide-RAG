"""Property-style invariants for deterministic Okapi BM25."""

from __future__ import annotations

import unittest

from src.bm25 import _idf, rank_bm25
from src.index import InvertedIndex
from src.models import Document


class BM25PropertyTests(unittest.TestCase):
    def test_idf_strictly_decreases_with_document_frequency(self) -> None:
        for document_count in range(1, 50):
            values = [_idf(document_count, frequency) for frequency in range(1, document_count + 1)]
            self.assertTrue(all(left > right for left, right in zip(values, values[1:])))

    def test_matching_term_outranks_an_identical_nonmatching_document(self) -> None:
        index = InvertedIndex.from_documents([
            Document("1", "alpha background", ""),
            Document("2", "gamma background", ""),
        ])
        scores = {result.doc_id: result.score for result in rank_bm25(index, "alpha", k=2)}
        self.assertGreater(scores.get("1", 0.0), scores.get("2", 0.0))

    def test_repeated_document_term_frequency_has_positive_diminishing_gains(self) -> None:
        scores = []
        for frequency in (1, 2, 3, 4):
            index = InvertedIndex.from_documents([Document("1", "alpha " * frequency, "")])
            scores.append(rank_bm25(index, "alpha")[0].score)
        gains = [right - left for left, right in zip(scores, scores[1:])]
        self.assertTrue(all(gain > 0 for gain in gains))
        self.assertTrue(all(left > right for left, right in zip(gains, gains[1:])))

    def test_results_are_deterministic_across_repeated_ranking_and_rebuilds(self) -> None:
        documents = [
            Document("10", "alpha beta beta", ""),
            Document("2", "alpha gamma", ""),
            Document("9", "beta gamma", ""),
        ]
        expected = rank_bm25(InvertedIndex.from_documents(documents), "alpha beta alpha", k=3)
        for _ in range(20):
            self.assertEqual(rank_bm25(InvertedIndex.from_documents(documents), "alpha beta alpha", k=3), expected)


if __name__ == "__main__":
    unittest.main()

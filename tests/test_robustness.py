"""Boundary-input and immutability coverage for lexical retrieval."""

from __future__ import annotations

import copy
import unittest

from src.bm25 import rank_bm25
from src.index import InvertedIndex
from src.models import Document


class LexicalRobustnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.index = InvertedIndex.from_documents([
            Document("1", "café alpha", "short abstract"),
            Document("2", "beta", "ordinary text"),
            Document("3", "gamma", "verylong " * 20_000),
        ])

    def test_boundary_queries_never_crash_or_mutate_the_index(self) -> None:
        before = copy.deepcopy(self.index)
        queries = (
            "", " \t\n ", "!!! -- ???", "the and of", "not-in-the-index",
            "alpha alpha alpha", "café", "cafe\u0301", "alpha " * 20_000,
        )
        for query in queries:
            with self.subTest(query=query[:40]):
                first = rank_bm25(self.index, query, k=10)
                second = rank_bm25(self.index, query, k=10)
                self.assertEqual(first, second)
        self.assertEqual(self.index, before)
        self.assertEqual(self.index.documents["3"].text, before.documents["3"].text)

    def test_unicode_composed_and_decomposed_queries_have_equal_results(self) -> None:
        self.assertEqual(rank_bm25(self.index, "café"), rank_bm25(self.index, "cafe\u0301"))

    def test_long_document_and_long_query_are_searchable(self) -> None:
        results = rank_bm25(self.index, "verylong " * 5_000, k=10)
        self.assertEqual([result.doc_id for result in results], ["3"])

    def test_without_document_returns_independent_valid_index_without_mutating_source(self) -> None:
        before = copy.deepcopy(self.index)
        removed = self.index.without_document("1")
        self.assertEqual(self.index, before)
        self.assertNotIn("1", removed.documents)
        self.assertNotIn("1", removed.document_lengths)
        self.assertTrue(all("1" not in removed.doc_ids(term) for term in removed.postings))
        self.assertEqual(rank_bm25(removed, "café"), ())
        self.assertEqual(removed, InvertedIndex.from_documents(removed.documents.values()))


if __name__ == "__main__":
    unittest.main()

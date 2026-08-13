from __future__ import annotations

import math
import unittest

from src.bm25 import BM25Config, ScoredDocument, rank_bm25
from src.index import InvertedIndex
from src.models import Document


def make_index() -> InvertedIndex:
    return InvertedIndex.from_documents(
        [
            Document("10", "alpha alpha beta", ""),
            Document("2", "alpha beta beta beta", ""),
            Document("9", "gamma", ""),
            Document("30", "alpha", ""),
        ]
    )


class BM25ConfigTests(unittest.TestCase):
    def test_config_is_frozen_and_defaults_to_okapi_values(self) -> None:
        config = BM25Config()
        self.assertEqual((config.k1, config.b), (1.2, 0.75))
        with self.assertRaises((AttributeError, TypeError)):
            config.k1 = 2.0  # type: ignore[misc]

    def test_config_rejects_invalid_parameters(self) -> None:
        for kwargs in (
            {"k1": 0}, {"k1": -1}, {"k1": math.inf}, {"k1": True},
            {"b": -0.01}, {"b": 1.01}, {"b": math.nan}, {"b": False},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                BM25Config(**kwargs)


class BM25RankingTests(unittest.TestCase):
    def test_scores_match_the_specified_formula(self) -> None:
        index = make_index()
        result = rank_bm25(index, "alpha beta", k=10)
        results_by_id = {item.doc_id: item.score for item in result}
        average_length = 9 / 4
        expected = {}
        for term in ("alpha", "beta"):
            df = index.document_frequency[term]
            idf = math.log(1 + (4 - df + 0.5) / (df + 0.5))
            for posting in index.postings[term]:
                tf = len(posting.positions)
                dl = index.document_lengths[posting.doc_id]
                expected[posting.doc_id] = expected.get(posting.doc_id, 0.0) + idf * tf / (
                    tf + 1.2 * (1 - 0.75 + 0.75 * dl / average_length)
                )
        self.assertEqual(set(results_by_id), set(expected))
        for document_id, score in expected.items():
            self.assertAlmostEqual(results_by_id[document_id], score, places=12)

    def test_duplicate_query_tokens_contribute_repeatedly(self) -> None:
        once = {item.doc_id: item.score for item in rank_bm25(make_index(), "alpha")}
        twice = {item.doc_id: item.score for item in rank_bm25(make_index(), "alpha alpha")}
        self.assertEqual(set(once), set(twice))
        for document_id in once:
            self.assertAlmostEqual(twice[document_id], 2 * once[document_id], places=12)

    def test_returns_union_of_matching_documents_and_honors_cutoff(self) -> None:
        all_results = rank_bm25(make_index(), "alpha gamma", k=10)
        self.assertEqual({item.doc_id for item in all_results}, {"2", "9", "10", "30"})
        results = rank_bm25(make_index(), "alpha gamma", k=2)
        self.assertEqual(len(results), 2)
        self.assertTrue(all(isinstance(item, ScoredDocument) for item in results))

    def test_ties_use_numeric_pmid_order(self) -> None:
        index = InvertedIndex.from_documents(
            [Document("10", "alpha", ""), Document("2", "alpha", "")]
        )
        self.assertEqual([item.doc_id for item in rank_bm25(index, "alpha")], ["2", "10"])

    def test_empty_and_oov_queries_return_empty_tuple(self) -> None:
        index = make_index()
        for query in ("", "!!!", "not-indexed"):
            with self.subTest(query=query):
                self.assertEqual(rank_bm25(index, query), ())

    def test_invalid_k_and_config_are_rejected(self) -> None:
        index = make_index()
        for k in (0, -1, 1.0, True):
            with self.subTest(k=k), self.assertRaises(ValueError):
                rank_bm25(index, "alpha", k=k)  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            rank_bm25(index, "alpha", config=None)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()

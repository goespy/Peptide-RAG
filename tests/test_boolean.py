from __future__ import annotations

import unittest

from src.boolean import search_boolean
from src.index import InvertedIndex
from src.models import Document


def make_index() -> InvertedIndex:
    return InvertedIndex.from_documents(
        [
            Document("10", "BPC-157 tendon repair", ""),
            Document("2", "BPC 157 tissue regeneration", ""),
            Document("9", "Tendon healing", ""),
            Document("30", "BPC 157 healing", ""),
        ]
    )


class BooleanRetrievalTests(unittest.TestCase):
    def test_and_has_higher_precedence_than_or(self) -> None:
        self.assertEqual(
            search_boolean(make_index(), "bpc OR tendon AND healing"),
            ["2", "9", "10", "30"],
        )

    def test_adjacent_terms_imply_and_and_hyphens_expand(self) -> None:
        self.assertEqual(search_boolean(make_index(), "BPC-157 tendon"), ["10"])

    def test_explicit_and_or_and_mixed_case(self) -> None:
        self.assertEqual(
            search_boolean(make_index(), "BPC aNd healing oR tendon"),
            ["9", "10", "30"],
        )

    def test_results_are_deduplicated_and_numeric_sorted(self) -> None:
        self.assertEqual(
            search_boolean(make_index(), "tendon OR bpc"),
            ["2", "9", "10", "30"],
        )

    def test_empty_unknown_and_malformed_queries_return_no_results(self) -> None:
        index = make_index()
        queries = (
            "",
            "!!!",
            "AND",
            "unknown",
            "AND bpc",
            "bpc OR",
            "bpc AND OR tendon",
        )
        for query in queries:
            with self.subTest(query=query):
                self.assertEqual(search_boolean(index, query), [])

    def test_unicode_query_does_not_crash(self) -> None:
        index = InvertedIndex.from_documents(
            [Document("1", "Thymosin β4 wound healing", "")]
        )
        self.assertEqual(search_boolean(index, "β4 healing"), ["1"])


if __name__ == "__main__":
    unittest.main()

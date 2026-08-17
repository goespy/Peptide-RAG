from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.analysis import GREEK_ANALYSIS
from src.index import InvertedIndex
from src.models import Document, Posting


class InvertedIndexTests(unittest.TestCase):
    def test_positions_span_title_and_text_and_document_frequencies(self) -> None:
        index = InvertedIndex.from_documents(
            [
                Document("10", "BPC-157 healing", "BPC restores tissue"),
                Document("9", "Tissue", "healing"),
            ]
        )

        self.assertEqual(index.postings["bpc"], (Posting("10", (0, 3)),))
        self.assertEqual(index.postings["healing"], (Posting("9", (1,)), Posting("10", (2,))))
        self.assertEqual(index.document_frequency["tissue"], 2)
        self.assertEqual(index.document_lengths, {"10": 6, "9": 2})
        self.assertEqual(index.title_lengths, {"10": 3, "9": 1})

    def test_postings_and_doc_ids_are_numeric_pmid_ordered(self) -> None:
        index = InvertedIndex.from_documents(
            [Document("10", "same", ""), Document("9", "same", "")]
        )

        self.assertEqual(index.doc_ids("same"), ("9", "10"))
        self.assertIsInstance(index.postings["same"], tuple)

    def test_duplicate_ids_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            InvertedIndex.from_documents([Document("1", "one", ""), Document("1", "two", "")])

    def test_empty_documents_are_retained_without_postings(self) -> None:
        index = InvertedIndex.from_documents([Document("1", "", "")])

        self.assertEqual(index.documents["1"], Document("1", "", ""))
        self.assertEqual(index.document_lengths["1"], 0)
        self.assertEqual(index.postings, {})
        self.assertEqual(index.doc_ids("missing"), ())

    def test_unicode_and_hyphens_use_shared_analysis(self) -> None:
        index = InvertedIndex.from_documents([Document("1", "MOTS-c BPC-157", "GHK_Cu")])

        self.assertEqual(index.doc_ids("mots"), ("1",))
        self.assertEqual(index.doc_ids("c"), ("1",))
        self.assertEqual(index.doc_ids("157"), ("1",))
        self.assertEqual(index.doc_ids("ghk"), ("1",))
        self.assertEqual(index.doc_ids("cu"), ("1",))

    def test_configured_analysis_is_used_for_titles_and_text(self) -> None:
        index = InvertedIndex.from_documents(
            [Document("1", "Thymosin β4", "β activity")], analysis_config=GREEK_ANALYSIS
        )
        self.assertEqual(index.doc_ids("beta4"), ("1",))
        self.assertEqual(index.doc_ids("beta"), ("1",))
        self.assertEqual(index.title_lengths, {"1": 2})

    def test_from_jsonl_requires_exact_records(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            corpus = Path(directory) / "corpus.jsonl"
            corpus.write_text(
                "".join(
                    json.dumps(record) + "\n"
                    for record in [
                        {"id": "10", "title": "BPC-157", "text": "repair"},
                        {"id": "9", "title": "repair", "text": ""},
                    ]
                ),
                encoding="utf-8",
            )
            index = InvertedIndex.from_jsonl(corpus)
            self.assertEqual(index.doc_ids("repair"), ("9", "10"))

            corpus.write_text('{"id":"1","title":"bad"}\n', encoding="utf-8")
            with self.assertRaises(ValueError):
                InvertedIndex.from_jsonl(corpus)

    def test_malformed_internal_positions_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            InvertedIndex(
                {"word": (Posting("1", (1, 0)),)},
                {"word": 1},
                {"1": Document("1", "word word", "")},
                {"1": 2},
            )

    def test_without_document_rebuilds_without_mutating_source(self) -> None:
        index = InvertedIndex.from_documents(
            [Document("1", "alpha beta", ""), Document("2", "beta gamma", "")]
        )
        reduced = index.without_document("1")

        self.assertEqual(index.doc_ids("alpha"), ("1",))
        self.assertEqual(index.documents["1"], Document("1", "alpha beta", ""))
        self.assertEqual(reduced.documents, {"2": Document("2", "beta gamma", "")})
        self.assertNotIn("alpha", reduced.postings)
        self.assertEqual(reduced.doc_ids("beta"), ("2",))
        self.assertEqual(reduced.document_frequency, {"beta": 1, "gamma": 1})
        self.assertEqual(reduced.document_lengths, {"2": 2})
        self.assertEqual(reduced.title_lengths, {"2": 2})
        self.assertIsNot(reduced, index)

    def test_index_metadata_fields_are_frozen(self) -> None:
        index = InvertedIndex.from_documents([Document("1", "alpha", "")])
        with self.assertRaises(AttributeError):
            index.title_lengths = {"1": 0}  # type: ignore[misc]

    def test_without_document_rejects_unknown_id(self) -> None:
        index = InvertedIndex.from_documents([Document("1", "alpha", "")])
        with self.assertRaises(ValueError):
            index.without_document("2")


if __name__ == "__main__":
    unittest.main()

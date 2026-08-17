from __future__ import annotations

import unittest

from src.chunks import ChunkConfig, chunk_corpus, chunk_document, embedding_text, span_contained


class ChunkTests(unittest.TestCase):
    def test_config_validation(self) -> None:
        for words, overlap in ((0, 1), (4, 0), (4, 4), (True, 1)):
            with self.assertRaises(ValueError):
                ChunkConfig(words, overlap)

    def test_windows_overlap_and_exact_offsets(self) -> None:
        text = "  one\ttwo  three\nfour five six  "
        chunks = chunk_document("9", "Title", text, ChunkConfig(4, 2))
        self.assertEqual([item.text for item in chunks], ["one\ttwo  three\nfour", "three\nfour five six"])
        self.assertEqual([(item.start_char, item.end_char) for item in chunks], [(2, 21), (11, 30)])
        self.assertEqual([item.token_count for item in chunks], [4, 4])
        self.assertTrue(all(text[item.start_char:item.end_char] == item.text for item in chunks))
        self.assertEqual([item.chunk_id for item in chunks], ["9:c0001", "9:c0002"])

    def test_unicode_spans_are_not_ascii_tokenized(self) -> None:
        text = "αβ  東京\t🙂 café"
        chunk = chunk_document("1", "T", text, ChunkConfig(4, 1))[0]
        self.assertEqual(chunk.text, text)
        self.assertEqual(chunk.token_count, 4)

    def test_empty_abstract_is_title_searchable_not_evidence(self) -> None:
        chunk = chunk_document("1", "A title", "   ", ChunkConfig(4, 1))[0]
        self.assertEqual((chunk.text, chunk.start_char, chunk.end_char, chunk.token_count), ("", 0, 0, 0))
        self.assertEqual(embedding_text(chunk), "A title")
        self.assertFalse(span_contained(chunk, 0, 1))

    def test_span_containment_uses_exact_abstract_offsets(self) -> None:
        chunk = chunk_document("1", "T", "one two three", ChunkConfig(3, 1))[0]
        self.assertTrue(span_contained(chunk, 4, 7))
        self.assertFalse(span_contained(chunk, -1, 7))
        self.assertFalse(span_contained(chunk, 4, 4))

    def test_corpus_order_is_numeric_and_deterministic(self) -> None:
        documents = [
            {"id": "10", "title": "Ten", "text": "a b"},
            {"id": "2", "title": "Two", "text": "c d"},
        ]
        first = chunk_corpus(documents, ChunkConfig(2, 1))
        second = chunk_corpus(reversed(documents), ChunkConfig(2, 1))
        self.assertEqual(first, second)
        self.assertEqual([item.chunk_id for item in first], ["2:c0001", "10:c0001"])

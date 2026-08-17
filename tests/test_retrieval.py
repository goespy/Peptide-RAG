import unittest

import numpy as np

from src.chunks import Chunk
from src.retrieval import Retriever


def chunk(chunk_id, title, text):
    return Chunk(chunk_id, chunk_id.split(":")[0], title, text, 0, len(text), len(text.split()))


class RetrievalTests(unittest.TestCase):
    def setUp(self):
        self.chunks = (
            chunk("2:c0001", "Peptides", "alpha peptide evidence"),
            chunk("1:c0001", "Controls", "beta evidence"),
            chunk("3:c0001", "Other", "gamma evidence"),
        )
        self.retriever = Retriever(
            self.chunks, np.array([[1, 0], [0, 1], [1, 0]], dtype=float),
            query_embedding=lambda _: np.array([1, 0]),
        )

    def test_modes_and_stable_semantic_ties(self):
        lexical = self.retriever.retrieve("peptide", 2, "lexical")
        self.assertEqual([item.chunk_id for item in lexical], ["2:c0001"])
        self.assertEqual((lexical[0].pmid, lexical[0].mode), ("2", "lexical"))
        self.assertEqual([item.chunk_id for item in self.retriever.retrieve("anything", 3, "semantic")], ["2:c0001", "3:c0001", "1:c0001"])
        self.assertEqual([item.chunk_id for item in self.retriever.retrieve("peptide", 3, "hybrid")][:2], ["2:c0001", "3:c0001"])

    def test_injected_query_embedding_avoids_network_and_empty_query(self):
        self.assertEqual(self.retriever.retrieve("", 2, "semantic"), ())
        self.assertEqual(self.retriever.retrieve("unused", 1, "semantic")[0].chunk_id, "2:c0001")

    def test_lexical_fallback_never_calls_the_query_embedder(self):
        def unexpected_embedding(_query):
            raise AssertionError("lexical retrieval must not embed the query")

        retriever = Retriever(
            self.chunks,
            np.array([[1, 0], [0, 1], [1, 0]], dtype=float),
            query_embedding=unexpected_embedding,
        )
        self.assertEqual(
            [item.chunk_id for item in retriever.retrieve("peptide", 2, "lexical")],
            ["2:c0001"],
        )

    def test_validation(self):
        with self.assertRaises(ValueError):
            self.retriever.retrieve("q", 0)
        with self.assertRaises(ValueError):
            self.retriever.retrieve("q", 1, "unknown")
        with self.assertRaises(ValueError):
            Retriever(self.chunks, np.ones((3, 2)), alpha=float("nan"))

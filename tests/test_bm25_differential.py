"""Optional differential coverage against the independently implemented bm25s."""

from __future__ import annotations

import json
from pathlib import Path
import unittest

from src.analysis import analyze
from src.bm25 import BM25Config, rank_bm25
from src.index import InvertedIndex
from src.models import Document

try:
    import bm25s
except ImportError:  # pragma: no cover - expected in the base dependency set
    bm25s = None


@unittest.skipIf(bm25s is None, "bm25s is not installed")
class BM25DifferentialTests(unittest.TestCase):
    def test_lucene_scores_match_bm25s_for_identical_tokens(self) -> None:
        documents = [
            Document("1", "alpha alpha beta", ""),
            Document("2", "alpha beta beta beta", ""),
            Document("3", "gamma", ""),
        ]
        index = InvertedIndex.from_documents(documents)
        query = ["alpha", "beta", "alpha"]
        actual = rank_bm25(index, " ".join(query), k=len(documents), config=BM25Config())

        reference = bm25s.BM25(method="lucene", k1=1.2, b=0.75, dtype="float64")
        corpus = [[token for token in document.title.split()] for document in documents]
        reference.index(corpus)
        result_ids, result_scores = reference.retrieve(
            [query], k=len(documents), show_progress=False
        )

        # bm25s returns corpus row ids; compare only nonzero matches and make
        # equal-score ordering deterministic before checking pairs.
        expected = [
            (str(documents[int(row_id)].id), float(score))
            for row_id, score in zip(result_ids[0], result_scores[0])
            if score != 0
        ]
        expected.sort(key=lambda item: (-item[1], int(item[0])))
        observed = [(item.doc_id, item.score) for item in actual]
        self.assertEqual([item[0] for item in observed], [item[0] for item in expected])
        for (_, observed_score), (_, expected_score) in zip(observed, expected):
            self.assertAlmostEqual(observed_score, expected_score, places=6)

    def test_all_frozen_queries_match_on_the_real_corpus(self) -> None:
        corpus_path = Path("data/corpus.jsonl")
        qrels_path = Path("data/qrels_v2.json")
        if not corpus_path.exists() or not qrels_path.exists():
            self.skipTest("frozen corpus artifacts are unavailable")

        index = InvertedIndex.from_jsonl(corpus_path)
        documents = list(index.documents.values())
        corpus = [analyze(document.title + " " + document.text) for document in documents]
        reference = bm25s.BM25(
            method="lucene", k1=1.2, b=0.75, dtype="float64"
        )
        reference.index(corpus, show_progress=False)
        qrels = json.loads(qrels_path.read_text(encoding="utf-8"))

        for entry in qrels["queries"]:
            query_tokens = list(analyze(entry["query"]))
            actual = rank_bm25(index, entry["query"], k=len(documents))
            result_ids, result_scores = reference.retrieve(
                [query_tokens], k=len(documents), show_progress=False
            )
            expected = [
                (documents[int(row_id)].id, float(score))
                for row_id, score in zip(result_ids[0], result_scores[0])
                if score > 0
            ]
            expected.sort(key=lambda item: (-item[1], int(item[0])))
            observed = [(item.doc_id, item.score) for item in actual]
            self.assertEqual(
                [doc_id for doc_id, _ in observed],
                [doc_id for doc_id, _ in expected],
                entry["id"],
            )
            for (_, observed_score), (_, expected_score) in zip(observed, expected):
                self.assertAlmostEqual(
                    observed_score,
                    expected_score,
                    delta=1e-6,
                    msg=entry["id"],
                )


if __name__ == "__main__":
    unittest.main()

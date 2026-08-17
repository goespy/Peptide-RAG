import importlib.util
import unittest
from pathlib import Path

import numpy as np

from src.chunks import Chunk
from src.retrieval import Retriever


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "diagnose_rag_retrieval", ROOT / "scripts/diagnose_rag_retrieval.py"
)
diagnose = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(diagnose)


class RetrievalDiagnosticTests(unittest.TestCase):
    def test_records_exact_gold_ranks_without_calling_a_chunk_miss(self):
        chunks = (
            Chunk("1:c0001", "1", "MOTS-c metabolic study", "improved metabolism", 0, 19, 2),
            Chunk("2:c0001", "2", "Weight loss", "weight loss report", 0, 18, 3),
        )
        retriever = Retriever(
            chunks,
            np.asarray([[0.0, 1.0], [1.0, 0.0]]),
            query_embedding=lambda _query: np.asarray([1.0, 0.0]),
        )
        case = {
            "id": "qa07",
            "question": "weight loss",
            "relevant_pmids": ["1"],
            "supporting_spans": [
                {"pmid": "1", "start_char": 0, "end_char": 19, "text_sha256": "unused"}
            ],
        }
        report = diagnose.rank_case(case, retriever)
        self.assertEqual(report["gold_chunk_ids"], ["1:c0001"])
        self.assertEqual(report["modes"]["semantic"]["best_gold_rank"], 2)
        self.assertTrue(report["modes"]["semantic"]["gold_in_measured_rank_window"])
        self.assertEqual(report["modes"]["hybrid"]["rrf_source_candidate_limit"], 50)
        self.assertIn("2:c0001", report["non_gold_top_five_require_human_relevance_review"])


if __name__ == "__main__":
    unittest.main()

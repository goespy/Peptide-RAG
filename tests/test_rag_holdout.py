import importlib.util
import unittest
from pathlib import Path

from src.chunks import Chunk
from src.retrieval import RetrievedChunk

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("run_rag_holdout", ROOT / "scripts/run_rag_holdout.py")
holdout = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(holdout)


def qa_packet():
    questions = []
    for index in range(7):
        answerable = index < 5
        questions.append({"id": f"qa{index + 11:02d}", "split": "holdout", "question": "question", "answerable": answerable, "relevant_pmids": ["1"] if answerable else [], "supporting_spans": [{"pmid": "1"}] if answerable else [], "human_review": {"approved": True, "decision": "approve", "reviewer": "owner"}})
    return {"status": "approved", "questions": questions}


class HoldoutTests(unittest.TestCase):
    def test_requires_exact_approved_holdout_and_winner(self):
        cases = holdout.holdout_cases(qa_packet())
        self.assertEqual(len(cases), 7)
        self.assertEqual(holdout.winner_from({"selection": {"winner": "model"}}), "model")
        with self.assertRaises(holdout.HoldoutError): holdout.winner_from({"selection": {"winner": None}})

    def test_saved_rows_bind_winner_contexts_and_citations(self):
        cases = holdout.holdout_cases(qa_packet())
        context = RetrievedChunk(Chunk("1:c0001", "1", "title", "evidence", 0, 8, 1), 1, "stored")
        contexts = {case["id"]: (context,) for case in cases}; rows = []
        for case in cases:
            rows.append({"model": "model", "qa_id": case["id"], "config_sha256": "c", "contexts_sha256": "x", "answer": {"status": "answered", "text": "Three factual words [1].", "citations": [{"citation_id": 1, "pmid": "1", "chunk_id": "1:c0001", "title": "title"}]}})
        rows[0]["answer"]["citations"][0]["pmid"] = "wrong"
        rows[1]["answerability"] = "tampered"
        saved = holdout.saved_rows({"outputs": rows}, cases, contexts, "model", "c", "x")
        self.assertFalse(saved[0]["structurally_valid"])
        self.assertEqual(saved[1]["answerability"], cases[1]["answerability"])

    def test_context_provenance_requires_frozen_config_hash(self):
        holdout.validate_context_provenance({"retriever_config_sha256": "x"}, "x")
        with self.assertRaises(holdout.HoldoutError): holdout.validate_context_provenance({}, "x")

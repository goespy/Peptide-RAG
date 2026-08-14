from __future__ import annotations

import unittest

import numpy as np

from scripts.export_rag_holdout_contexts import (
    HoldoutContextError,
    build_context_packet,
    validate_development_gates,
)
from src.chunks import Chunk
from src.retrieval import Retriever


def qa_packet():
    return {
        "status": "approved",
        "questions": [
            {
                "id": f"qa{number:02d}",
                "split": "holdout",
                "question": "alpha",
                "answerable": number <= 15,
                "relevant_pmids": ["1"] if number <= 15 else [],
                "supporting_spans": [{"pmid": "1"}] if number <= 15 else [],
                "human_review": {"approved": True, "decision": "approve", "reviewer": "owner"},
            }
            for number in range(11, 16)
        ] + [
            {
                "id": f"qa{number:02d}",
                "split": "holdout",
                "question": "alpha",
                "answerable": False,
                "relevant_pmids": [],
                "supporting_spans": [],
                "human_review": {"approved": True, "decision": "approve", "reviewer": "owner"},
            }
            for number in (19, 20)
        ],
    }


class ExportHoldoutContextsTests(unittest.TestCase):
    def test_gate_binds_qa_config_and_judge_to_bakeoff(self):
        config = {"status": "selected_and_frozen", "selected": True, "prompt": "p", "generation": {"temperature": 0, "max_tokens": 400}}
        bakeoff = {"qa_sha256": "q", "config_sha256": "c", "outputs_sha256": "o", "selection": {"winner": "model", "winner_status": "accepted_for_holdout"}}
        judge = {"passes": True, "source_outputs_sha256": "o"}
        self.assertEqual(validate_development_gates(qa_packet(), config, bakeoff, judge, qa_hash="q", config_hash="c"), "model")
        judge["source_outputs_sha256"] = "wrong"
        with self.assertRaises(HoldoutContextError):
            validate_development_gates(qa_packet(), config, bakeoff, judge, qa_hash="q", config_hash="c")

    def test_packet_contains_exactly_seven_stable_hybrid_context_lists(self):
        chunks = (Chunk("1:c0001", "1", "Alpha", "alpha evidence", 0, 14, 2),)
        retriever = Retriever(chunks, np.array([[1.0, 0.0]]), query_embedding=lambda query: np.array([1.0, 0.0]))
        cases = [{"id": item["id"], "question": item["question"]} for item in qa_packet()["questions"]]
        packet = build_context_packet(cases, retriever, qa_hash="q", config_hash="c")
        self.assertEqual(len(packet["contexts"]), 7)
        self.assertEqual(packet["contexts"][0]["chunks"][0]["chunk_id"], "1:c0001")
        self.assertEqual(packet["retriever_config_sha256"], "c")


if __name__ == "__main__":
    unittest.main()

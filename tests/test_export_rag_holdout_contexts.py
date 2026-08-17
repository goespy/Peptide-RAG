from __future__ import annotations

import unittest

import numpy as np

from scripts.export_rag_holdout_contexts import (
    HoldoutContextError,
    build_context_packet,
    embedding_cost_estimate,
    validate_embedding_cost_bound,
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
    def test_gate_binds_qa_config_and_judge_to_accepted_selection(self):
        config = {"status": "selected_and_frozen", "selected": True, "prompt": "p", "generation": {"temperature": 0, "max_tokens": 400}}
        selection = {"status": "accepted_for_holdout", "holdout_status": "untouched", "winner": "model", "qa_sha256": "q", "retriever_config_sha256": "c", "judge_outputs_sha256": "o", "owner_validation_report_sha256": "r", "holdout_cost_caps": {"context_embedding_usd": 0.01}}
        judge = {"passes": True, "source_outputs_sha256": "o"}
        self.assertEqual(validate_development_gates(qa_packet(), config, selection, judge, qa_hash="q", config_hash="c", report_hash="r"), "model")
        judge["source_outputs_sha256"] = "wrong"
        with self.assertRaises(HoldoutContextError):
            validate_development_gates(qa_packet(), config, selection, judge, qa_hash="q", config_hash="c", report_hash="r")

    def test_packet_contains_exactly_seven_stable_hybrid_context_lists(self):
        chunks = (Chunk("1:c0001", "1", "Alpha", "alpha evidence", 0, 14, 2),)
        retriever = Retriever(chunks, np.array([[1.0, 0.0]]), query_embedding=lambda query: np.array([1.0, 0.0]))
        cases = [{"id": item["id"], "question": item["question"]} for item in qa_packet()["questions"]]
        packet = build_context_packet(cases, retriever, qa_hash="q", config_hash="c", selection_hash="s")
        self.assertEqual(len(packet["contexts"]), 7)
        self.assertEqual(packet["contexts"][0]["chunks"][0]["chunk_id"], "1:c0001")
        self.assertEqual(packet["retriever_config_sha256"], "c")
        self.assertEqual(packet["accepted_selection_sha256"], "s")

    def test_embedding_cost_is_bounded_before_calls(self):
        cases = [{"question": "alpha"}] * 7
        estimate = embedding_cost_estimate(cases)
        self.assertGreater(estimate, 0)
        self.assertIn("conservative estimate", validate_embedding_cost_bound(0.01, estimate))
        with self.assertRaises(HoldoutContextError):
            validate_embedding_cost_bound(0.02, estimate)


if __name__ == "__main__":
    unittest.main()

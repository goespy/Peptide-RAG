from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

import numpy as np

from scripts.export_rag_holdout_contexts import (
    HoldoutContextError,
    build_context_packet,
    embedding_cost_estimate,
    main,
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

    def test_main_passes_frozen_model_to_cache_loader(self):
        chunks = (Chunk("1:c0001", "1", "Alpha", "alpha evidence", 0, 14, 2),)
        manifest = {"corpus_sha256": "c", "chunk_sha256": "h"}
        config = {
            "chunk_config": {"words": 256, "overlap": 64},
            "embedding_model": "openai/text-embedding-3-small",
            "lexical_config_sha256": "lexical-hash",
            "rrf_alpha": 0.5,
        }
        lexical = {
            "analysis": {"name": "baseline"},
            "bm25": {"k1": 1.2, "b": 0.75, "proximity_boost": 0.0},
        }
        with TemporaryDirectory() as temp:
            output = Path(temp) / "contexts.json"
            with (
                patch("scripts.export_rag_holdout_contexts.load_json", side_effect=[qa_packet(), config, {}, {}, lexical]),
                patch("scripts.export_rag_holdout_contexts.hash_file", side_effect=lambda path: "lexical-hash" if Path(path).name == "lexical_config.json" else "hash"),
                patch("scripts.export_rag_holdout_contexts.validate_development_gates", return_value="model"),
                patch("scripts.export_rag_holdout_contexts.load_chunk_artifact", return_value=(chunks, manifest)),
                patch("scripts.export_rag_holdout_contexts._cache_for", return_value=(np.array([[1.0, 0.0]]), "openai/text-embedding-3-small")) as cache_for,
                patch("scripts.export_rag_holdout_contexts.EmbeddingClient", return_value=Mock(total_metadata={})),
                patch("scripts.export_rag_holdout_contexts.Retriever", return_value=Mock()),
                patch("scripts.export_rag_holdout_contexts.build_context_packet", return_value={}),
                patch("scripts.export_rag_holdout_contexts.write_json_atomic"),
                patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"}),
            ):
                result = main([
                    "--cache", "cache.npz",
                    "--output", str(output),
                    "--max-cost-usd", "0.01",
                    "--confirm-cost",
                ])
        self.assertEqual(result, 0)
        cache_for.assert_called_once_with(
            chunks,
            manifest,
            Path("cache.npz"),
            "openai/text-embedding-3-small",
        )


if __name__ == "__main__":
    unittest.main()

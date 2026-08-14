import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from src.chunks import Chunk
from src.retrieval import RetrievedChunk

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("run_rag_bakeoff", ROOT / "scripts/run_rag_bakeoff.py")
bakeoff = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(bakeoff)


def approved_qa():
    questions = []
    for index in range(13):
        answerable = index < 10
        questions.append({"id": f"qa{index + 1:02d}", "split": "development", "question": f"question {index}", "answerable": answerable, "relevant_pmids": ["1"] if answerable else [], "supporting_spans": [{"pmid": "1", "start_char": 0, "end_char": 1, "text_sha256": "A"}] if answerable else [], "human_review": {"approved": True, "decision": "approve", "reviewer": "owner"}})
    return {"status": "approved", "questions": questions}


def config(): return {"status": "selected_and_frozen", "selected": True, "prompt": "fixed", "generation": {"temperature": 0, "max_tokens": 400}}

def catalog():
    return {"checked_at": "2026-08-13T00:00:00Z", "sources": ["https://example.test"], "models": [{"family": family, "id": model, "available": True, "structured_json": True, "context_length": 32768, "input_cost_per_million": .1, "output_cost_per_million": .5} for family, model in zip(bakeoff.MODEL_FAMILIES, bakeoff.MODELS)], "judge": {"family":"anthropic","id":"anthropic/judge","available":True,"structured_json":True,"context_length":32768,"input_cost_per_million":1.0,"output_cost_per_million":5.0}}


class BakeoffTests(unittest.TestCase):
    def test_requires_normalized_approved_qa(self):
        with self.assertRaises(bakeoff.BakeoffError):
            bakeoff.validate_qa({"status": "candidate", "questions": []})
        self.assertEqual(len(bakeoff.validate_qa(approved_qa())), 13)
        self.assertEqual(bakeoff.validate_model_catalog(catalog()), bakeoff.MODELS)
        self.assertEqual(bakeoff.validate_judge_catalog(catalog()), "anthropic/judge")

    def test_selection_disqualifies_missing_or_invalid_rows(self):
        rows = {model: [] for model in bakeoff.MODELS}
        for model in bakeoff.MODELS:
            for index in range(13):
                rows[model].append({"structurally_valid": True, "judge": {"faithful": True, "relevant": True, "citations_correct": True, "refusal_correct": True}, "metadata": {"latency_ms": 1, "cost_usd": 0}})
        rows[bakeoff.MODELS[0]][0]["structurally_valid"] = False
        result = bakeoff.select_winner(rows, 13)
        self.assertNotEqual(result["winner"], bakeoff.MODELS[0])

    def test_refusal_rate_uses_only_unanswerable_cases(self):
        rows = [
            {"structurally_valid": True, "answerability": "answerable", "answer": {"status": "answered"}, "judge": {"faithful": True, "relevant": True, "citations_correct": True, "refusal_correct": True}, "metadata": {"latency_ms": 1, "cost_usd": 0}},
            {"structurally_valid": True, "answerability": "unanswerable", "answer": {"status": "insufficient_evidence"}, "judge": {"faithful": True, "relevant": True, "citations_correct": True, "refusal_correct": True}, "metadata": {"latency_ms": 1, "cost_usd": 0}},
        ]
        metrics = bakeoff.select_winner({"model": rows}, 2)["candidates"]["model"]
        self.assertEqual(metrics["correct_refusal"], 1.0)
        self.assertEqual(metrics["correct_answer"], 1.0)
        self.assertEqual(metrics["answerable_answer_rate"], 1.0)

    def test_never_answering_scores_zero_instead_of_becoming_ineligible(self):
        rows = []
        for index in range(13):
            answerability = "answerable" if index < 10 else "unanswerable"
            rows.append({
                "structurally_valid": True,
                "answerability": answerability,
                "answer": {"status": "insufficient_evidence"},
                "judge": {
                    "faithful": index >= 10,
                    "relevant": True,
                    "citations_correct": True,
                    "refusal_correct": index >= 10,
                },
                "metadata": {"latency_ms": 1, "cost_usd": 0},
            })
        selection = bakeoff.select_winner({"model": rows}, 13)
        metrics = selection["candidates"]["model"]
        self.assertEqual(selection["winner"], "model")
        self.assertEqual(metrics["citation_correctness"], 0.0)
        self.assertEqual(metrics["correct_answer"], 0.0)
        self.assertEqual(metrics["answerable_answer_rate"], 0.0)

    def test_partial_judge_failure_disqualifies_candidate(self):
        rows = []
        for index in range(13):
            rows.append({
                "structurally_valid": True,
                "answerability": "unanswerable" if index >= 10 else "answerable",
                "answer": {"status": "insufficient_evidence" if index >= 10 else "answered"},
                "judge": None if index == 0 else {"faithful": True, "relevant": True, "citations_correct": True, "refusal_correct": True},
                "metadata": {"latency_ms": 1, "cost_usd": 0},
            })
        result = bakeoff.select_winner({"model": rows}, 13)
        self.assertIsNone(result["winner"])
        self.assertEqual(result["candidates"]["model"]["judged_outputs"], 12)
        self.assertIsNone(result["candidates"]["model"]["faithfulness"])

    def test_default_run_refuses_without_approved_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            result = bakeoff.main(["--qa", str(Path(directory) / "missing.json")])
        self.assertEqual(result, 1)

    def test_offline_validation_binds_saved_citations_to_stored_contexts(self):
        cases = bakeoff.validate_qa(approved_qa())
        context = RetrievedChunk(Chunk("1:c0001", "1", "title", "evidence", 0, 8, 1), 1.0, "stored")
        contexts = {case["id"]: (context,) for case in cases}
        rows = []
        for model in bakeoff.MODELS:
            for case in cases:
                rows.append({"model": model, "qa_id": case["id"], "config_sha256": "config", "contexts_sha256": "contexts", "answer": {"status": "answered", "text": "Three factual words [1].", "citations": [{"citation_id": 1, "pmid": "1", "chunk_id": "1:c0001", "title": "title"}]}})
        rows[0]["answer"]["citations"][0]["chunk_id"] = "wrong"
        grouped = bakeoff.offline_rows({"outputs": rows}, cases, contexts, "config", "contexts")
        self.assertFalse(grouped[bakeoff.MODELS[0]][0]["structurally_valid"])

    def test_offline_rows_restore_answerability_and_share_live_validator(self):
        cases = bakeoff.validate_qa(approved_qa())
        context = RetrievedChunk(Chunk("1:c0001", "1", "title", "evidence", 0, 8, 1), 1.0, "stored")
        contexts = {case["id"]: (context,) for case in cases}
        valid_answer = {"status": "answered", "text": "Three factual words [1].", "citations": [{"citation_id": 1, "pmid": "1", "chunk_id": "1:c0001", "title": "title"}]}
        rows = [{"model": model, "qa_id": case["id"], "answerability": "tampered", "config_sha256": "config", "contexts_sha256": "contexts", "answer": valid_answer} for model in bakeoff.MODELS for case in cases]
        grouped = bakeoff.offline_rows({"outputs": rows}, cases, contexts, "config", "contexts")
        first = grouped[bakeoff.MODELS[0]][0]
        self.assertEqual(first["answerability"], cases[0]["answerability"])
        self.assertEqual(first["structurally_valid"], bakeoff.structurally_valid_answer(valid_answer, contexts[first["qa_id"]]))

    def test_atomic_writes_and_live_cost_confirmation_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "artifact.json"
            bakeoff.write_json_atomic(path, {"a": 1}, overwrite=False)
            with self.assertRaises(bakeoff.BakeoffError): bakeoff.write_json_atomic(path, {"a": 2}, overwrite=False)
        with self.assertRaises(bakeoff.BakeoffError): bakeoff.validate_live_cost(None)
        self.assertIn("$1.00", bakeoff.validate_live_cost(1))
        with self.assertRaises(bakeoff.BakeoffError): bakeoff.validate_live_cost(.01, .02)

    def test_cost_estimate_includes_repairs_retries_and_all_judges(self):
        cases = bakeoff.validate_qa(approved_qa())
        context = RetrievedChunk(Chunk("1:c0001", "1", "title", "evidence", 0, 8, 1), 1.0, "stored")
        contexts = {case["id"]: (context,) for case in cases}
        estimate = bakeoff.estimate_bakeoff_cost(cases, contexts, catalog(), bakeoff.MODELS, "anthropic/judge")
        self.assertEqual(estimate["maximum_provider_calls"], 195)
        self.assertGreater(estimate["estimated_max_cost_usd"], 0)
        self.assertEqual(len(estimate["generation"]), 3)

    def test_combined_usage_includes_generator_and_judge(self):
        usage = bakeoff.combined_usage(
            {"provider_calls": 2, "input_tokens": 100, "output_tokens": 20, "cost_usd": .01},
            {"provider_calls": 1, "input_tokens": 50, "output_tokens": 10, "cost_usd": .02},
            12.5,
            7.5,
        )
        self.assertEqual(usage["provider_calls"], 3)
        self.assertEqual(usage["input_tokens"], 150)
        self.assertEqual(usage["output_tokens"], 30)
        self.assertAlmostEqual(usage["cost_usd"], .03)
        self.assertEqual(usage["latency_ms"], 20)
        self.assertEqual(usage["token_cost_status"], "provider_reported")

    def test_combined_usage_preserves_unknown_cost(self):
        usage = bakeoff.combined_usage(
            {"provider_calls": 1, "input_tokens": 100, "output_tokens": 20, "cost_usd": .01},
            {"provider_calls": 1, "input_tokens": None, "output_tokens": None, "cost_usd": None},
            1,
            2,
        )
        self.assertEqual(usage["provider_calls"], 2)
        self.assertIsNone(usage["input_tokens"])
        self.assertIsNone(usage["cost_usd"])
        self.assertEqual(usage["token_cost_status"], "unknown_not_exposed_by_provider")

    def test_realized_usage_sums_all_saved_rows_and_preserves_unknowns(self):
        grouped = {
            "a": [{"metadata": {"provider_calls": 2, "input_tokens": 10, "output_tokens": 3, "cost_usd": .01}}],
            "b": [{"metadata": {"provider_calls": 1, "input_tokens": 20, "output_tokens": 4, "cost_usd": .02}}],
        }
        usage = bakeoff.realized_usage(grouped)
        self.assertEqual(usage["rows"], 2)
        self.assertEqual(usage["provider_calls"], 3)
        self.assertEqual(usage["input_tokens"], 30)
        self.assertAlmostEqual(usage["cost_usd"], .03)
        self.assertEqual(usage["status"], "provider_reported_complete")
        grouped["b"][0]["metadata"]["cost_usd"] = None
        self.assertIsNone(bakeoff.realized_usage(grouped)["cost_usd"])

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
    return {"checked_at": "2026-08-13T00:00:00Z", "sources": ["https://example.test"], "models": [{"family": family, "id": model, "available": True, "structured_json": True, "context_length": 32768, "input_cost_per_million": .1, "output_cost_per_million": .5} for family, model in zip(bakeoff.MODEL_FAMILIES, bakeoff.MODELS)]}


class BakeoffTests(unittest.TestCase):
    def test_requires_normalized_approved_qa(self):
        with self.assertRaises(bakeoff.BakeoffError):
            bakeoff.validate_qa({"status": "candidate", "questions": []})
        self.assertEqual(len(bakeoff.validate_qa(approved_qa())), 13)
        self.assertEqual(bakeoff.validate_model_catalog(catalog()), bakeoff.MODELS)

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
            {"structurally_valid": True, "answerability": "answerable", "answer": {"status": "answered"}, "judge": {"faithful": True, "relevant": True, "citations_correct": True, "refusal_correct": False}, "metadata": {"latency_ms": 1, "cost_usd": 0}},
            {"structurally_valid": True, "answerability": "unanswerable", "answer": {"status": "insufficient_evidence"}, "judge": {"faithful": True, "relevant": True, "citations_correct": True, "refusal_correct": True}, "metadata": {"latency_ms": 1, "cost_usd": 0}},
        ]
        self.assertEqual(bakeoff.select_winner({"model": rows}, 2)["candidates"]["model"]["correct_refusal"], 1.0)

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

    def test_atomic_writes_and_live_cost_confirmation_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "artifact.json"
            bakeoff.write_json_atomic(path, {"a": 1}, overwrite=False)
            with self.assertRaises(bakeoff.BakeoffError): bakeoff.write_json_atomic(path, {"a": 2}, overwrite=False)
        with self.assertRaises(bakeoff.BakeoffError): bakeoff.validate_live_cost(None)
        self.assertIn("$1.00", bakeoff.validate_live_cost(1))

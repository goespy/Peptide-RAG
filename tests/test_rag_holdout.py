from __future__ import annotations

import copy
import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

from src.chunks import Chunk
from src.generation import AnswerResult, Citation, insufficient_evidence
from src.judge import AtomicClaim, JudgeVerdict
from src.retrieval import RetrievedChunk


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "run_rag_holdout",
    ROOT / "scripts/run_rag_holdout.py",
)
holdout = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(holdout)


WINNER = "openai/gpt-oss-20b"
JUDGE = "anthropic/claude-sonnet-4.6"
SELECTION_HASH = "A" * 64
CONFIG_HASH = "B" * 64
CONTEXT_HASH = "C" * 64


def qa_packet() -> dict:
    questions = []
    for index in range(7):
        answerable = index < 5
        questions.append({
            "id": f"qa{index + 11:02d}",
            "split": "holdout",
            "question": f"{'answerable' if answerable else 'unanswerable'} question {index}",
            "answerable": answerable,
            "relevant_pmids": ["1"] if answerable else [],
            "supporting_spans": [{"pmid": "1"}] if answerable else [],
            "human_review": {
                "approved": True,
                "decision": "approve",
                "reviewer": "owner",
            },
        })
    return {"status": "approved", "questions": questions}


def context() -> RetrievedChunk:
    chunk = Chunk("1:c0001", "1", "Title", "Supported evidence.", 0, 19, 2)
    return RetrievedChunk(chunk, 1.0, "hybrid", 1, 1)


def contexts(cases: list[dict]) -> dict[str, tuple[RetrievedChunk, ...]]:
    return {case["id"]: (context(),) for case in cases}


def _usage(*, judge: bool = False) -> dict:
    value = {
        "provider_calls": 1,
        "input_tokens": 10,
        "output_tokens": 5,
        "cost_usd": 0.001,
        "provider": "test",
    }
    if judge:
        value["raw_output_sha256"] = "D" * 64
    return value


def valid_row(case: dict) -> dict:
    answerable = case["answerability"] == "answerable"
    if answerable:
        answer = {
            "status": "answered",
            "text": "Supported finding [1].",
            "citations": [{
                "citation_id": 1,
                "pmid": "1",
                "chunk_id": "1:c0001",
                "title": "Title",
            }],
        }
        claims = [{"text": "Supported finding", "supported": True, "citation_ids": [1]}]
    else:
        answer = {
            "status": "insufficient_evidence",
            "text": "Insufficient evidence in the retrieved research abstracts.",
            "citations": [],
        }
        claims = []
    generator_usage = _usage()
    judge_usage = _usage(judge=True)
    generator_latency, judge_latency = 1.5, 2.5
    return {
        "model": WINNER,
        "qa_id": case["id"],
        "answerability": case["answerability"],
        "selection_sha256": SELECTION_HASH,
        "config_sha256": CONFIG_HASH,
        "contexts_sha256": CONTEXT_HASH,
        "answer": answer,
        "judge": {
            "claims": claims,
            "faithful": True,
            "relevant": True,
            "citations_correct": True,
            "refusal_correct": True,
        },
        "structurally_valid": True,
        "generator_metadata": {**generator_usage, "latency_ms": generator_latency},
        "judge_metadata": {**judge_usage, "latency_ms": judge_latency},
        "metadata": holdout.combined_usage(
            generator_usage,
            judge_usage,
            generator_latency,
            judge_latency,
        ),
    }


class FakeGenerator:
    init_kwargs: dict = {}

    def __init__(self, **kwargs):
        type(self).init_kwargs = kwargs
        self.last_metadata = _usage()

    def answer(self, query, evidence):
        self.last_metadata = _usage()
        if query.startswith("unanswerable"):
            return insufficient_evidence()
        return AnswerResult(
            "answered",
            "Supported finding [1].",
            (Citation(1, "1", "1:c0001", "Title"),),
        )


class FakeJudge:
    init_kwargs: dict = {}
    expected: list[bool] = []

    def __init__(self, **kwargs):
        type(self).init_kwargs = kwargs
        type(self).expected = []
        self.last_metadata = _usage(judge=True)

    def judge(self, query, answer, evidence, *, expected_answerable):
        type(self).expected.append(expected_answerable)
        self.last_metadata = _usage(judge=True)
        claims = (
            (AtomicClaim("Supported finding", True, (1,)),)
            if expected_answerable
            else ()
        )
        return JudgeVerdict(claims, True, True, True, True)


class HoldoutTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cases = holdout.holdout_cases(qa_packet())
        self.contexts = contexts(self.cases)

    def _replay(self, rows: list[dict]) -> list[dict]:
        return holdout.saved_rows(
            {"outputs": rows},
            self.cases,
            self.contexts,
            WINNER,
            SELECTION_HASH,
            CONFIG_HASH,
            CONTEXT_HASH,
        )

    def test_requires_exact_unique_approved_holdout_and_accepted_winner(self):
        self.assertEqual(len(self.cases), 7)
        self.assertEqual(holdout.winner_from({
            "status": "accepted_for_holdout",
            "holdout_status": "untouched",
            "winner": WINNER,
        }), WINNER)
        duplicate = qa_packet()
        duplicate["questions"][1]["id"] = duplicate["questions"][0]["id"]
        with self.assertRaises(holdout.HoldoutError):
            holdout.holdout_cases(duplicate)
        with self.assertRaises(holdout.HoldoutError):
            holdout.winner_from({
                "status": "provisional",
                "holdout_status": "untouched",
                "winner": WINNER,
            })

    def test_context_provenance_binds_config_qa_and_selection(self):
        packet = {
            "retriever_config_sha256": CONFIG_HASH,
            "qa_sha256": "Q" * 64,
            "accepted_selection_sha256": SELECTION_HASH,
        }
        holdout.validate_context_provenance(
            packet,
            CONFIG_HASH,
            qa_hash="Q" * 64,
            selection_hash=SELECTION_HASH,
        )
        for field in tuple(packet):
            altered = dict(packet)
            altered[field] = "wrong"
            with self.subTest(field=field), self.assertRaises(holdout.HoldoutError):
                holdout.validate_context_provenance(
                    altered,
                    CONFIG_HASH,
                    qa_hash="Q" * 64,
                    selection_hash=SELECTION_HASH,
                )

    def test_saved_rows_replay_exactly(self):
        rows = [valid_row(case) for case in self.cases]
        replayed = self._replay(rows)
        self.assertEqual([row["qa_id"] for row in replayed], sorted(row["qa_id"] for row in rows))

    def test_saved_rows_reject_duplicates_and_provenance_tampering(self):
        rows = [valid_row(case) for case in self.cases]
        rows[1]["qa_id"] = rows[0]["qa_id"]
        with self.assertRaises(holdout.HoldoutError):
            self._replay(rows)
        for field, value in (
            ("answerability", "unanswerable"),
            ("selection_sha256", "wrong"),
            ("config_sha256", "wrong"),
            ("contexts_sha256", "wrong"),
        ):
            altered = [valid_row(case) for case in self.cases]
            altered[0][field] = value
            with self.subTest(field=field), self.assertRaises(holdout.HoldoutError):
                self._replay(altered)

    def test_saved_rows_reject_malformed_claims_hashes_and_usage(self):
        mutations = []
        malformed_claim = [valid_row(case) for case in self.cases]
        malformed_claim[0]["judge"]["claims"].append({"unexpected": True})
        mutations.append(malformed_claim)
        lowercase_hash = [valid_row(case) for case in self.cases]
        lowercase_hash[0]["judge_metadata"]["raw_output_sha256"] = "d" * 64
        mutations.append(lowercase_hash)
        changed_usage = [valid_row(case) for case in self.cases]
        changed_usage[0]["generator_metadata"]["input_tokens"] += 1
        mutations.append(changed_usage)
        wrong_refusal = [valid_row(case) for case in self.cases]
        wrong_refusal[-1]["judge"]["refusal_correct"] = False
        mutations.append(wrong_refusal)
        for index, rows in enumerate(mutations):
            with self.subTest(index=index), self.assertRaises(holdout.HoldoutError):
                self._replay(rows)

    def test_acceptance_threshold_allows_one_of_five_faithfulness_misses(self):
        rows = [valid_row(case) for case in self.cases]
        rows[0]["judge"]["faithful"] = False
        rows[0]["judge"]["claims"][0]["supported"] = False
        metrics, passes = holdout.summarize(rows)
        self.assertEqual(metrics["answered_faithfulness"], 0.8)
        self.assertTrue(passes)
        rows[1]["judge"]["faithful"] = False
        rows[1]["judge"]["claims"][0]["supported"] = False
        self.assertFalse(holdout.summarize(rows)[1])

    def test_cost_cap_is_required_and_cannot_exceed_frozen_limit(self):
        status = holdout.validate_holdout_cost_bound(0.25, 0.20, 0.50)
        self.assertIn("conservative estimate", status)
        for approved, estimate in ((None, 0.20), (0.51, 0.20), (0.25, 0.30), (0.25, 0.51)):
            with self.subTest(approved=approved, estimate=estimate), self.assertRaises(
                holdout.HoldoutError
            ):
                holdout.validate_holdout_cost_bound(approved, estimate, 0.50)

    def test_live_path_uses_frozen_v2_5_generator_and_judge_settings(self):
        generation = {
            "max_tokens": 800,
            "temperature": 0,
            "prompt": "frozen prompt",
            "citation_mode": "derived_from_text_markers",
            "require_supported_parameters": True,
            "reasoning_effort": "low",
            "exclude_reasoning": True,
            "reconsider_insufficient_evidence": True,
        }
        judge = {
            "max_tokens": 600,
            "require_supported_parameters": True,
            "prompt_version": 2,
        }
        with patch.object(holdout, "GroundedAnswerClient", FakeGenerator), patch.object(
            holdout,
            "AnswerJudge",
            FakeJudge,
        ):
            rows = holdout.run_live(
                self.cases,
                self.contexts,
                WINNER,
                JUDGE,
                SELECTION_HASH,
                CONFIG_HASH,
                CONTEXT_HASH,
                "key",
                generation,
                judge,
            )
        self.assertEqual(len(rows), 7)
        self.assertEqual(FakeGenerator.init_kwargs["system_prompt"], "frozen prompt")
        self.assertEqual(FakeGenerator.init_kwargs["max_tokens"], 800)
        self.assertTrue(FakeGenerator.init_kwargs["reconsider_insufficient_evidence"])
        self.assertEqual(FakeJudge.init_kwargs["prompt_version"], 2)
        self.assertEqual(FakeJudge.expected.count(True), 5)
        self.assertEqual(FakeJudge.expected.count(False), 2)
        self.assertTrue(all(row["structurally_valid"] for row in rows))

    def test_final_config_binds_passing_summary(self):
        rows = self._replay([valid_row(case) for case in self.cases])
        summary = holdout.expected_summary(
            rows=rows,
            qa_hash="Q" * 64,
            retriever_config_hash=CONFIG_HASH,
            selection_hash=SELECTION_HASH,
            owner_report_hash="R" * 64,
            contexts_hash=CONTEXT_HASH,
            outputs_hash="O" * 64,
            catalog_hash="M" * 64,
            winner=WINNER,
            judge_model=JUDGE,
            cost_estimate={"estimated_max_cost_usd": 0.2},
            approved_max_cost_usd=0.25,
        )
        self.assertTrue(summary["passes"])
        final = holdout.expected_final_config(summary, summary_hash="S" * 64)
        self.assertEqual(final["holdout_summary_sha256"], "S" * 64)
        self.assertEqual(final["status"], "frozen_after_passing_holdout")


if __name__ == "__main__":
    unittest.main()

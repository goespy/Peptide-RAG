import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from src.chunks import Chunk
from src.judge import AtomicClaim, JudgeVerdict
from src.retrieval import RetrievedChunk


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "run_generator_judge", ROOT / "scripts/run_generator_judge.py"
)
generator_judge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(generator_judge)


MODEL = "openai/gpt-oss-20b"
JUDGE = "anthropic/claude-sonnet-4.6"


def cases():
    return [
        {
            "id": f"qa{index + 1:02d}",
            "question": f"question {index}",
            "answerability": "answerable" if index < 10 else "unanswerable",
        }
        for index in range(13)
    ]


def contexts():
    return {
        case["id"]: (
            RetrievedChunk(
                Chunk(
                    f"{index + 1}:c0001",
                    str(index + 1),
                    "title",
                    "direct evidence",
                    0,
                    15,
                    2,
                ),
                1.0,
                "hybrid",
            ),
        )
        for index, case in enumerate(cases())
    }


def source_grouped():
    rows = []
    for index, case in enumerate(cases()):
        answerable = case["answerability"] == "answerable"
        citation = {
            "citation_id": 1,
            "pmid": str(index + 1),
            "chunk_id": f"{index + 1}:c0001",
            "title": "title",
        }
        rows.append(
            {
                "model": MODEL,
                "qa_id": case["id"],
                "answerability": case["answerability"],
                "config_sha256": "A" * 64,
                "contexts_sha256": "B" * 64,
                "answer": {
                    "status": "answered" if answerable else "insufficient_evidence",
                    "text": "Supported answer. [1]" if answerable else "Insufficient evidence.",
                    "citations": [citation] if answerable else [],
                },
                "structurally_valid": True,
                "metadata": {
                    "provider_calls": 1,
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "cost_usd": 0.001,
                    "latency_ms": 1.0,
                },
            }
        )
    return {MODEL: rows}


def catalog():
    return {
        "checked_at": "2026-08-15T02:10:10Z",
        "sources": ["https://example.test"],
        "models": [
            {
                "family": family,
                "id": model,
                "available": True,
                "structured_json": True,
                "context_length": 32768,
                "input_cost_per_million": 0.1,
                "output_cost_per_million": 0.5,
            }
            for family, model in (
                ("qwen", "qwen/test"),
                ("openai", MODEL),
                ("google", "google/test"),
            )
        ],
        "judge": {
            "family": "anthropic",
            "id": JUDGE,
            "available": True,
            "structured_json": True,
            "context_length": 32768,
            "input_cost_per_million": 3.0,
            "output_cost_per_million": 15.0,
            "supported_parameters": ["response_format", "structured_outputs"],
        },
    }


def passed_summary():
    return {
        "config_sha256": "A" * 64,
        "outputs_sha256": "C" * 64,
        "qa_sha256": "D" * 64,
        "contexts_sha256": "B" * 64,
        "live_calls": True,
        "diagnostic": {
            "candidates": {
                MODEL: {
                    "answerable_answer_count": 10,
                    "answerable_case_count": 10,
                    "unanswerable_correct_system_refusal_count": 3,
                    "unanswerable_case_count": 3,
                    "structurally_valid_count": 13,
                    "total_case_count": 13,
                    "ready_for_paid_judging": True,
                }
            }
        },
    }


class FakeJudge:
    def __init__(self):
        self.calls = 0
        self.last_metadata = {}

    def judge(self, query, answer, evidence, *, expected_answerable):
        self.calls += 1
        self.last_metadata = {
            "provider_calls": 1,
            "input_tokens": 20,
            "output_tokens": 8,
            "cost_usd": 0.002,
            "provider": "test",
        }
        return JudgeVerdict(
            (AtomicClaim("Supported answer", True, (1,)),) if expected_answerable else (),
            True,
            True,
            True,
            (answer.status == "insufficient_evidence") == (not expected_answerable),
        )


class GeneratorJudgeTests(unittest.TestCase):
    def test_generator_gate_requires_exact_10_3_13_live_result(self):
        generator_judge.validate_generator_gate(
            passed_summary(),
            model=MODEL,
            generator_config_hash="A" * 64,
            generator_outputs_hash="C" * 64,
            qa_hash="D" * 64,
            contexts_hash="B" * 64,
        )
        for field, value in (
            ("answerable_answer_count", 9),
            ("unanswerable_correct_system_refusal_count", 2),
            ("structurally_valid_count", 12),
            ("ready_for_paid_judging", False),
        ):
            packet = json.loads(json.dumps(passed_summary()))
            packet["diagnostic"]["candidates"][MODEL][field] = value
            with self.subTest(field=field), self.assertRaises(generator_judge.BakeoffError):
                generator_judge.validate_generator_gate(
                    packet,
                    model=MODEL,
                    generator_config_hash="A" * 64,
                    generator_outputs_hash="C" * 64,
                    qa_hash="D" * 64,
                    contexts_hash="B" * 64,
                )

    def test_estimate_contains_exactly_thirteen_judge_calls_and_zero_generator_calls(self):
        estimate = generator_judge.estimate_judge_cost(
            cases(), contexts(), source_grouped(), model=JUDGE, max_tokens=600, catalog=catalog()
        )
        self.assertEqual(estimate["judge_calls"], 13)
        self.assertEqual(estimate["generator_calls"], 0)
        self.assertEqual(estimate["maximum_output_tokens"], 7_800)
        self.assertGreater(estimate["estimated_max_cost_usd"], 0)

    def test_live_path_calls_only_injected_judge_and_preserves_generator_answers(self):
        judge = FakeJudge()
        source = source_grouped()
        judged = generator_judge.run_live_judges(
            cases(),
            contexts(),
            source,
            judge=judge,
            judge_config_hash="J" * 64,
            generator_outputs_hash="C" * 64,
        )
        self.assertEqual(judge.calls, 13)
        self.assertEqual(
            [row["answer"] for row in judged[MODEL]],
            [row["answer"] for row in source[MODEL]],
        )
        self.assertTrue(all(row["judge"] is not None for row in judged[MODEL]))
        self.assertEqual(generator_judge.judge_usage(judged)["provider_calls"], 13)

    def test_offline_replay_rejects_answer_or_refusal_label_tampering(self):
        judge = FakeJudge()
        judged = generator_judge.run_live_judges(
            cases(),
            contexts(),
            source_grouped(),
            judge=judge,
            judge_config_hash="J" * 64,
            generator_outputs_hash="C" * 64,
        )
        packet = {
            "judge_config_sha256": "J" * 64,
            "generator_outputs_sha256": "C" * 64,
            "outputs": judged[MODEL],
        }
        replayed = generator_judge.offline_judged_rows(
            packet,
            source_grouped(),
            contexts(),
            judge_config_hash="J" * 64,
            generator_outputs_hash="C" * 64,
        )
        self.assertEqual(len(replayed[MODEL]), 13)

        altered = json.loads(json.dumps(packet))
        altered["outputs"][0]["answer"]["text"] = "changed"
        with self.assertRaises(generator_judge.BakeoffError):
            generator_judge.offline_judged_rows(
                altered,
                source_grouped(),
                contexts(),
                judge_config_hash="J" * 64,
                generator_outputs_hash="C" * 64,
            )

        altered = json.loads(json.dumps(packet))
        altered["outputs"][0]["judge"]["refusal_correct"] = False
        with self.assertRaises(generator_judge.BakeoffError):
            generator_judge.offline_judged_rows(
                altered,
                source_grouped(),
                contexts(),
                judge_config_hash="J" * 64,
                generator_outputs_hash="C" * 64,
            )

    def test_frozen_judge_config_binds_paths_hashes_calls_and_cap(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            temp = Path(directory)
            outputs = temp / "judged.json"
            summary = temp / "summary.json"
            hashes = {
                "qa_sha256": "A" * 64,
                "contexts_sha256": "B" * 64,
                "model_catalog_sha256": "C" * 64,
                "generator_config_sha256": "D" * 64,
                "generator_outputs_sha256": "E" * 64,
                "generator_summary_sha256": "F" * 64,
            }
            config = {
                "status": "frozen_before_paid_judging",
                "selected": True,
                **hashes,
                "artifact_paths": {
                    "outputs": outputs.relative_to(ROOT).as_posix(),
                    "summary": summary.relative_to(ROOT).as_posix(),
                },
                "judge": {
                    "model": JUDGE,
                    "temperature": 0,
                    "max_tokens": 600,
                    "require_supported_parameters": True,
                    "hard_cost_cap_usd": 0.25,
                },
                "generator_calls": 0,
                "judge_calls": 13,
                "holdout_status": "untouched",
            }
            settings = generator_judge.validate_judge_config(
                config,
                hashes=hashes,
                outputs_path=outputs,
                result_path=summary,
                catalog=catalog(),
            )
            self.assertEqual(settings["hard_cost_cap_usd"], 0.25)
            for field in ("judge_calls", "generator_calls", "holdout_status"):
                invalid = json.loads(json.dumps(config))
                invalid[field] = 99
                with self.subTest(field=field), self.assertRaises(generator_judge.BakeoffError):
                    generator_judge.validate_judge_config(
                        invalid,
                        hashes=hashes,
                        outputs_path=outputs,
                        result_path=summary,
                        catalog=catalog(),
                    )

    def test_cost_gate_rejects_estimate_or_owner_bound_above_hard_cap(self):
        with self.assertRaises(generator_judge.BakeoffError):
            generator_judge.validate_judge_cost_bound(0.25, 0.26, 0.25)
        with self.assertRaises(generator_judge.BakeoffError):
            generator_judge.validate_judge_cost_bound(0.30, 0.20, 0.25)
        self.assertIn(
            "$0.25",
            generator_judge.validate_judge_cost_bound(0.25, 0.20, 0.25),
        )


if __name__ == "__main__":
    unittest.main()

import importlib.util
from contextlib import redirect_stdout
from io import StringIO
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "run_generator_diagnostic", ROOT / "scripts/run_generator_diagnostic.py"
)
diagnostic = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(diagnostic)


class GeneratorDiagnosticTests(unittest.TestCase):
    def test_reviewed_estimate_must_match_recomputed_inputs(self):
        config = {"generator_diagnostic": {"reviewed_estimate_usd": 0.01}}
        diagnostic.validate_reviewed_estimate(config, 0.01)
        with self.assertRaises(diagnostic.BakeoffError):
            diagnostic.validate_reviewed_estimate(config, 0.011)

    def test_config_selects_a_validated_nonempty_model_subset(self):
        catalog_models = ("qwen/model", "openai/gpt-oss-20b", "google/model")
        self.assertEqual(
            diagnostic.select_diagnostic_models(
                {"generator_candidates": ["openai/gpt-oss-20b"]}, catalog_models
            ),
            ("openai/gpt-oss-20b",),
        )
        for invalid in (
            [],
            ["openai/gpt-oss-20b", "openai/gpt-oss-20b"],
            ["unknown/model"],
            "openai/gpt-oss-20b",
        ):
            with self.subTest(invalid=invalid), self.assertRaises(diagnostic.BakeoffError):
                diagnostic.select_diagnostic_models(
                    {"generator_candidates": invalid}, catalog_models
                )

    def test_selected_model_must_advertise_reasoning_and_structured_parameters(self):
        catalog = {
            "models": [
                {
                    "id": "openai/gpt-oss-20b",
                    "supported_parameters": [
                        "reasoning",
                        "response_format",
                        "structured_outputs",
                    ],
                }
            ]
        }
        diagnostic.validate_selected_parameter_support(
            catalog,
            ("openai/gpt-oss-20b",),
            {"reasoning_effort": "low"},
        )
        for missing in ("reasoning", "response_format", "structured_outputs"):
            invalid = json.loads(json.dumps(catalog))
            invalid["models"][0]["supported_parameters"].remove(missing)
            with self.subTest(missing=missing), self.assertRaises(diagnostic.BakeoffError):
                diagnostic.validate_selected_parameter_support(
                    invalid,
                    ("openai/gpt-oss-20b",),
                    {"reasoning_effort": "low"},
                )

    def test_experiment_bindings_protect_inputs_paths_and_parent_evidence(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            temp = Path(directory)
            outputs = temp / "outputs.json"
            summary = temp / "summary.json"
            relative_outputs = outputs.relative_to(ROOT).as_posix()
            relative_summary = summary.relative_to(ROOT).as_posix()
            config = {
                "qa_sha256": "A" * 64,
                "contexts_sha256": "B" * 64,
                "model_catalog_sha256": "C" * 64,
                "generator_diagnostic": {"judge_calls": 0},
                "artifact_paths": {
                    "outputs": relative_outputs,
                    "summary": relative_summary,
                },
            }
            diagnostic.validate_experiment_bindings(
                config,
                qa_hash="A" * 64,
                context_hash="B" * 64,
                catalog_hash="C" * 64,
                outputs_path=outputs,
                result_path=summary,
            )

            for field in ("qa_sha256", "contexts_sha256", "model_catalog_sha256"):
                invalid = json.loads(json.dumps(config))
                invalid[field] = "D" * 64
                with self.subTest(field=field), self.assertRaises(diagnostic.BakeoffError):
                    diagnostic.validate_experiment_bindings(
                        invalid,
                        qa_hash="A" * 64,
                        context_hash="B" * 64,
                        catalog_hash="C" * 64,
                        outputs_path=outputs,
                        result_path=summary,
                    )

            invalid = json.loads(json.dumps(config))
            invalid["generator_diagnostic"]["judge_calls"] = 1
            with self.assertRaises(diagnostic.BakeoffError):
                diagnostic.validate_experiment_bindings(
                    invalid,
                    qa_hash="A" * 64,
                    context_hash="B" * 64,
                    catalog_hash="C" * 64,
                    outputs_path=outputs,
                    result_path=summary,
                )

            outputs.write_text("parent evidence", encoding="utf-8")
            config["parent_outputs_sha256"] = diagnostic.hash_file(outputs)
            with self.assertRaises(diagnostic.BakeoffError):
                diagnostic.validate_experiment_bindings(
                    config,
                    qa_hash="A" * 64,
                    context_hash="B" * 64,
                    catalog_hash="C" * 64,
                    outputs_path=outputs,
                    result_path=summary,
                )

    def test_experiment_bindings_reject_unfrozen_or_colliding_output_paths(self):
        base = {
            "qa_sha256": "A" * 64,
            "contexts_sha256": "B" * 64,
            "model_catalog_sha256": "C" * 64,
            "generator_diagnostic": {"judge_calls": 0},
        }
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            selected = Path(directory) / "same.json"
            for config, result in (
                (base, Path(directory) / "summary.json"),
                (
                    {
                        **base,
                        "artifact_paths": {
                            "outputs": selected.relative_to(ROOT).as_posix(),
                            "summary": selected.relative_to(ROOT).as_posix(),
                        },
                    },
                    selected,
                ),
            ):
                with self.assertRaises(diagnostic.BakeoffError):
                    diagnostic.validate_experiment_bindings(
                        config,
                        qa_hash="A" * 64,
                        context_hash="B" * 64,
                        catalog_hash="C" * 64,
                        outputs_path=selected,
                        result_path=result,
                    )

            outside = ROOT.parent / "outside-generator-output.json"
            traversal = {
                **base,
                "artifact_paths": {
                    "outputs": "../outside-generator-output.json",
                    "summary": (Path(directory) / "summary.json")
                    .relative_to(ROOT)
                    .as_posix(),
                },
            }
            with self.assertRaises(diagnostic.BakeoffError):
                diagnostic.validate_experiment_bindings(
                    traversal,
                    qa_hash="A" * 64,
                    context_hash="B" * 64,
                    catalog_hash="C" * 64,
                    outputs_path=outside,
                    result_path=Path(directory) / "summary.json",
                )

    def test_default_estimate_wires_v2_5_without_touching_v2_4_evidence(self):
        protected = (
            ROOT / "data/rag_generator_v2_4_outputs.json",
            ROOT / "data/rag_generator_v2_4_summary.json",
            ROOT / "data/rag_generator_v2_4_judged_outputs.json",
            ROOT / "data/rag_generator_v2_4_judge_summary.json",
        )
        before = tuple(diagnostic.hash_file(path) for path in protected)
        stdout = StringIO()
        catalog_models = (
            "qwen/qwen3-30b-a3b-instruct-2507",
            "openai/gpt-oss-20b",
            "google/gemma-3-12b-it",
        )
        with (
            patch.object(diagnostic, "validate_model_catalog", return_value=catalog_models),
            redirect_stdout(stdout),
        ):
            self.assertEqual(diagnostic.main(["--estimate-only"]), 0)
        estimate = json.loads(stdout.getvalue())
        self.assertEqual(
            [row["model"] for row in estimate["generation"]],
            ["openai/gpt-oss-20b"],
        )
        self.assertEqual(estimate["judge_calls"], 0)
        config = json.loads(
            (ROOT / "artifacts/section5/generator_v2_5_config.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            estimate["estimated_max_cost_usd"],
            config["generator_diagnostic"]["reviewed_estimate_usd"],
        )
        self.assertEqual(
            before,
            tuple(diagnostic.hash_file(path) for path in protected),
        )

    def test_summary_requires_all_answerable_answers_before_judging(self):
        rows = []
        for index in range(13):
            answerable = index < 10
            status = "answered" if answerable and index != 0 else "insufficient_evidence"
            rows.append(
                {
                    "answerability": "answerable" if answerable else "unanswerable",
                    "answer": {"status": status},
                    "structurally_valid": True,
                    "metadata": {
                        "final_outcome": (
                            "answered" if status == "answered" else "model_insufficient_evidence"
                        ),
                        "attempts": [
                            {
                                "finish_reason": "stop",
                                "validation_error": None,
                            }
                        ],
                    },
                }
            )
        result = diagnostic.summarize({"model": rows})["candidates"]["model"]
        self.assertEqual(result["answerable_answer_count"], 9)
        self.assertEqual(result["unanswerable_model_refusal_count"], 3)
        self.assertEqual(result["unanswerable_correct_system_refusal_count"], 3)
        self.assertFalse(result["ready_for_paid_judging"])
        self.assertEqual(result["finish_reasons"], {"stop": 13})

    def test_generator_only_estimate_excludes_judge(self):
        result = diagnostic.generator_cost_only(
            {
                "method": "test",
                "generation": [
                    {"provider_calls": 2, "estimated_cost_usd": 0.01},
                    {"provider_calls": 3, "estimated_cost_usd": 0.02},
                ],
            }
        )
        self.assertEqual(result["maximum_provider_calls"], 5)
        self.assertAlmostEqual(result["estimated_max_cost_usd"], 0.03)
        self.assertEqual(result["judge_calls"], 0)

    def test_hard_cost_ceiling_is_enforced_before_delegated_gate(self):
        with self.assertRaises(diagnostic.BakeoffError):
            diagnostic.validate_diagnostic_cost_bound(0.05, 0.01, 0.04)
        with self.assertRaises(diagnostic.BakeoffError):
            diagnostic.validate_diagnostic_cost_bound(0.04, 0.041, 0.04)
        with self.assertRaises(diagnostic.BakeoffError):
            diagnostic.validate_diagnostic_cost_bound(0.05, 0.051, 0.05)
        with self.assertRaises(diagnostic.BakeoffError):
            diagnostic.validate_diagnostic_cost_bound(None, 0.03, 0.04)
        with patch.object(diagnostic, "validate_live_cost", return_value="approved") as gate:
            self.assertEqual(
                diagnostic.validate_diagnostic_cost_bound(0.04, 0.03, 0.04),
                "approved",
            )
        gate.assert_called_once_with(0.04, 0.03)

    def test_failed_closed_unanswerable_is_not_counted_as_deliberate_refusal(self):
        rows = [
            {
                "answerability": "unanswerable",
                "answer": {"status": "insufficient_evidence"},
                "structurally_valid": True,
                "metadata": {"final_outcome": "failed_closed_after_repair", "attempts": []},
            }
        ]
        result = diagnostic.summarize({"model": rows})["candidates"]["model"]
        self.assertEqual(result["unanswerable_insufficient_evidence_shape_count"], 1)
        self.assertEqual(result["unanswerable_model_refusal_count"], 0)
        self.assertEqual(result["unanswerable_correct_system_refusal_count"], 0)
        self.assertFalse(result["ready_for_paid_judging"])

    def test_reconsidered_refusal_counts_but_failed_closed_reconsideration_does_not(self):
        retained = {
            "answerability": "unanswerable",
            "answer": {"status": "insufficient_evidence"},
            "structurally_valid": True,
            "metadata": {
                "final_outcome": "model_insufficient_evidence_after_reconsideration",
                "attempts": [],
            },
        }
        failed_closed = json.loads(json.dumps(retained))
        failed_closed["metadata"]["final_outcome"] = (
            "failed_closed_after_refusal_reconsideration"
        )

        retained_result = diagnostic.summarize({"model": [retained]})["candidates"]["model"]
        failed_result = diagnostic.summarize({"model": [failed_closed]})["candidates"]["model"]

        self.assertEqual(retained_result["unanswerable_model_refusal_count"], 1)
        self.assertEqual(retained_result["unanswerable_correct_system_refusal_count"], 1)
        self.assertTrue(retained_result["ready_for_paid_judging"])
        self.assertEqual(failed_result["unanswerable_model_refusal_count"], 0)
        self.assertEqual(failed_result["unanswerable_correct_system_refusal_count"], 0)
        self.assertFalse(failed_result["ready_for_paid_judging"])

    def test_policy_dosing_refusal_counts_as_correct_system_behavior(self):
        rows = [
            {
                "answerability": "unanswerable",
                "answer": {"status": "insufficient_evidence"},
                "structurally_valid": True,
                "metadata": {
                    "final_outcome": "preflight_insufficient_evidence",
                    "failure_reason": "personalized_or_dosing_request",
                    "attempts": [],
                },
            }
        ]
        result = diagnostic.summarize({"model": rows})["candidates"]["model"]
        self.assertEqual(result["unanswerable_policy_refusal_count"], 1)
        self.assertEqual(result["unanswerable_correct_system_refusal_count"], 1)
        self.assertTrue(result["ready_for_paid_judging"])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import importlib.util
import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "freeze_generator_selection",
    ROOT / "scripts/freeze_generator_selection.py",
)
selection = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(selection)


HASHES = {name: character * 64 for name, character in zip(
    ("qa", "retriever", "generator_config", "generator_outputs", "generator_summary", "judge_config", "judge_outputs", "judge_summary", "worksheet", "report"),
    "ABCDEFGHIJ",
)}


def packets() -> tuple[dict, dict, dict, dict, dict]:
    prompt = "Use only evidence."
    generator_config = {
        "status": "frozen_generator_v2_5_before_development_rerun",
        "selected": True,
        "prompt": prompt,
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest().upper(),
        "generation": {
            "max_tokens": 800,
            "temperature": 0,
            "repair_attempts": 1,
            "citation_mode": "derived_from_text_markers",
            "require_supported_parameters": True,
            "reasoning_effort": "low",
            "exclude_reasoning": True,
            "reconsider_insufficient_evidence": True,
        },
        "generator_candidates": ["generator"],
        "qa_sha256": HASHES["qa"],
        "retriever_config_sha256": HASHES["retriever"],
        "contexts_sha256": "L" * 64,
        "model_catalog_sha256": "K" * 64,
        "holdout_status": "untouched",
    }
    generator_summary = {
        "config_sha256": HASHES["generator_config"],
        "outputs_sha256": HASHES["generator_outputs"],
        "qa_sha256": HASHES["qa"],
        "contexts_sha256": "L" * 64,
        "model_catalog_sha256": "K" * 64,
        "live_calls": True,
        "diagnostic": {"candidates": {"generator": {
            "ready_for_paid_judging": True,
            "answerable_answer_count": 10,
            "unanswerable_correct_system_refusal_count": 3,
            "structurally_valid_count": 13,
        }}},
    }
    judge_config = {
        "qa_sha256": HASHES["qa"],
        "generator_config_sha256": HASHES["generator_config"],
        "generator_outputs_sha256": HASHES["generator_outputs"],
        "generator_summary_sha256": HASHES["generator_summary"],
        "contexts_sha256": "L" * 64,
        "model_catalog_sha256": "K" * 64,
        "holdout_status": "untouched",
        "judge_calls": 13,
        "judge": {"model": "judge", "prompt_version": 2},
    }
    metrics = {
        "denominators": {"answerable": 10, "unanswerable": 3},
        "structural_validity": 1.0,
        "faithfulness": 0.9,
    }
    judge_summary = {
        "judged_outputs_sha256": HASHES["judge_outputs"],
        "judge_config_sha256": HASHES["judge_config"],
        "generator_config_sha256": HASHES["generator_config"],
        "generator_outputs_sha256": HASHES["generator_outputs"],
        "generator_summary_sha256": HASHES["generator_summary"],
        "qa_sha256": HASHES["qa"],
        "contexts_sha256": "L" * 64,
        "model_catalog_sha256": "K" * 64,
        "live_calls": True,
        "holdout_status": "untouched",
        "ready_for_owner_validation": True,
        "selection": {"winner": "generator", "candidates": {"generator": metrics}},
    }
    dimensions = {name: {"passes": True} for name in ("faithful", "relevant", "citations_correct", "refusal_correct")}
    owner_report = {
        "passes": True,
        "n": 10,
        "worksheet_sha256": HASHES["worksheet"],
        "source_outputs_sha256": HASHES["judge_outputs"],
        "dimensions": dimensions,
    }
    return generator_config, generator_summary, judge_config, judge_summary, owner_report


def build(**overrides):
    generator_config, generator_summary, judge_config, judge_summary, owner_report = packets()
    arguments = {
        "qa_hash": HASHES["qa"],
        "retriever_config_hash": HASHES["retriever"],
        "generator_config_hash": HASHES["generator_config"],
        "generator_outputs_hash": HASHES["generator_outputs"],
        "generator_summary_hash": HASHES["generator_summary"],
        "judge_config_hash": HASHES["judge_config"],
        "judge_outputs_hash": HASHES["judge_outputs"],
        "judge_summary_hash": HASHES["judge_summary"],
        "worksheet_hash": HASHES["worksheet"],
        "report_hash": HASHES["report"],
        "generator_config": generator_config,
        "generator_summary": generator_summary,
        "judge_config": judge_config,
        "judge_summary": judge_summary,
        "owner_report": owner_report,
    }
    arguments.update(overrides)
    return selection.build_selection(**arguments)


class FreezeGeneratorSelectionTests(unittest.TestCase):
    def test_builds_hash_bound_accepted_selection(self) -> None:
        packet = build()
        self.assertEqual(packet["status"], "accepted_for_holdout")
        self.assertEqual(packet["winner"], "generator")
        self.assertEqual(packet["judge_model"], "judge")
        self.assertEqual(packet["owner_validation_report_sha256"], HASHES["report"])
        self.assertEqual(packet["holdout_status"], "untouched")
        self.assertEqual(packet["holdout_cost_caps"]["generation_and_judging_usd"], 0.50)

    def test_rejects_failed_owner_gate_and_hash_drift(self) -> None:
        generator_config, generator_summary, judge_config, judge_summary, owner_report = packets()
        owner_report["passes"] = False
        with self.assertRaises(selection.SelectionError):
            build(owner_report=owner_report)
        judge_config["generator_outputs_sha256"] = "Z" * 64
        with self.assertRaises(selection.SelectionError):
            build(judge_config=judge_config)

    def test_rejects_incomplete_generator_or_judge_gate(self) -> None:
        generator_config, generator_summary, judge_config, judge_summary, owner_report = packets()
        generator_summary["diagnostic"]["candidates"]["generator"]["answerable_answer_count"] = 9
        with self.assertRaises(selection.SelectionError):
            build(generator_summary=generator_summary)
        judge_summary["selection"]["candidates"]["generator"]["structural_validity"] = 0.9
        with self.assertRaises(selection.SelectionError):
            build(judge_summary=judge_summary)

    def test_checked_in_v2_5_artifacts_match_the_selection_contract(self) -> None:
        paths = {
            "qa": ROOT / "data/qa.json",
            "retriever": ROOT / "artifacts/section5/frozen_config.json",
            "generator_config": ROOT / "artifacts/section5/generator_v2_5_config.json",
            "generator_outputs": ROOT / "data/rag_generator_v2_5_outputs.json",
            "generator_summary": ROOT / "data/rag_generator_v2_5_summary.json",
            "judge_config": ROOT / "artifacts/section5/generator_v2_5_judge_config.json",
            "judge_outputs": ROOT / "data/rag_generator_v2_5_judged_outputs.json",
            "judge_summary": ROOT / "data/rag_generator_v2_5_judge_summary.json",
            "worksheet": ROOT / "data/judge_validation_v2_5_worksheet.json",
        }

        def file_hash(path: Path) -> str:
            return hashlib.sha256(path.read_bytes()).hexdigest().upper()

        packets_by_name = {
            name: json.loads(path.read_text(encoding="utf-8"))
            for name, path in paths.items()
            if name in {"generator_config", "generator_summary", "judge_config", "judge_summary"}
        }
        owner_report = {
            "passes": True,
            "n": 10,
            "worksheet_sha256": file_hash(paths["worksheet"]),
            "source_outputs_sha256": file_hash(paths["judge_outputs"]),
            "dimensions": {
                name: {"passes": True}
                for name in ("faithful", "relevant", "citations_correct", "refusal_correct")
            },
        }
        packet = selection.build_selection(
            qa_hash=file_hash(paths["qa"]),
            retriever_config_hash=file_hash(paths["retriever"]),
            generator_config_hash=file_hash(paths["generator_config"]),
            generator_outputs_hash=file_hash(paths["generator_outputs"]),
            generator_summary_hash=file_hash(paths["generator_summary"]),
            judge_config_hash=file_hash(paths["judge_config"]),
            judge_outputs_hash=file_hash(paths["judge_outputs"]),
            judge_summary_hash=file_hash(paths["judge_summary"]),
            worksheet_hash=file_hash(paths["worksheet"]),
            report_hash="R" * 64,
            owner_report=owner_report,
            **packets_by_name,
        )
        self.assertEqual(packet["status"], "accepted_for_holdout")
        self.assertEqual(packet["winner"], "openai/gpt-oss-20b")


if __name__ == "__main__":
    unittest.main()

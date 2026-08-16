from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import run_project


class RunProjectTests(unittest.TestCase):
    def test_default_run_is_offline_and_core_passes(self) -> None:
        checks, core_failed = run_project.run()
        self.assertFalse(core_failed)
        self.assertTrue(any(check.name == "current boolean evaluation" and check.state == "PASS" for check in checks))
        self.assertTrue(any(check.name == "current bm25 evaluation" and check.state == "PASS" for check in checks))
        self.assertTrue(any(check.name == "Section 4 experiment provenance" and check.state == "PASS" for check in checks))
        self.assertTrue(any(check.name == "approved QA oracle" and check.state == "PASS" for check in checks))
        self.assertTrue(any(check.name == "RAG retrieval evaluation" and check.state == "PASS" for check in checks))
        self.assertTrue(any(check.name == "RAG GPT v2.3 generator evidence" and check.state == "PASS" for check in checks))
        self.assertTrue(any(check.name == "RAG GPT v2.4 generator gate" and check.state == "PASS" for check in checks))
        self.assertTrue(any(
            check.name == "RAG GPT v2.4 judge configuration" and check.state == "PASS"
            for check in checks
        ))
        self.assertTrue(any(
            check.name == "RAG GPT v2.4 judge evidence" and check.state == "PASS"
            for check in checks
        ))
        self.assertTrue(any(
            check.name == "RAG GPT v2.4 owner worksheet" and check.state == "PASS"
            and "owner labels pending" in check.detail
            for check in checks
        ))
        self.assertTrue(any(
            check.name == "RAG GPT v2.5 generator gate" and check.state == "PASS"
            for check in checks
        ))
        self.assertTrue(any(
            check.name == "RAG GPT v2.5 judge configuration" and check.state == "PASS"
            for check in checks
        ))
        self.assertTrue(any(
            check.name == "RAG GPT v2.5 judge evidence" and check.state == "PASS"
            for check in checks
        ))
        self.assertTrue(any(
            check.name == "RAG GPT v2.5 owner worksheet" and check.state == "PASS"
            and "owner labels pending" in check.detail
            for check in checks
        ))
        self.assertTrue(any(
            check.name == "RAG accepted generator and QA holdout"
            and check.state == "TBD"
            for check in checks
        ))

    def test_holdout_artifact_without_accepted_selection_fails_release(self) -> None:
        with TemporaryDirectory() as temp:
            orphan = Path(temp) / "rag_holdout_contexts.json"
            orphan.write_text("{}", encoding="utf-8")
            with patch.object(run_project, "RAG_HOLDOUT_CONTEXTS", orphan):
                checks, failed = run_project.run()
        self.assertTrue(failed)
        self.assertTrue(any(
            check.name == "RAG accepted generator and QA holdout"
            and check.state == "FAIL"
            and "without an accepted generator" in check.detail
            for check in checks
        ))

    def test_owner_worksheet_oracle_leak_fails_release(self) -> None:
        for leaked_field, leaked_value in (
            ("acceptable_answer", "leaked oracle"),
            ("answerability", "answerable"),
            ("judge", {}),
            ("gold_answer", "renamed leak"),
        ):
            with self.subTest(leaked_field=leaked_field), TemporaryDirectory() as temp:
                altered = Path(temp) / "worksheet.json"
                payload = json.loads(run_project.GENERATOR_V2_4_JUDGE_WORKSHEET.read_text(encoding="utf-8"))
                payload["sample"][0][leaked_field] = leaked_value
                altered.write_text(json.dumps(payload), encoding="utf-8")
                with patch.object(run_project, "GENERATOR_V2_4_JUDGE_WORKSHEET", altered):
                    checks, failed = run_project.run()
            self.assertTrue(failed)
            self.assertTrue(any(
                check.name == "RAG GPT generator diagnostics" and check.state == "FAIL"
                and "leaks" in check.detail
                for check in checks
            ))

    def test_judge_cost_estimate_drift_fails_release(self) -> None:
        with TemporaryDirectory() as temp:
            altered = Path(temp) / "judge_config.json"
            payload = json.loads(run_project.GENERATOR_V2_4_JUDGE_CONFIG.read_text(encoding="utf-8"))
            payload["cost_estimate"]["estimated_max_cost_usd"] += 0.01
            altered.write_text(json.dumps(payload), encoding="utf-8")
            with patch.object(run_project, "GENERATOR_V2_4_JUDGE_CONFIG", altered):
                checks, failed = run_project.run()
        self.assertTrue(failed)
        self.assertTrue(any(
            check.name == "RAG GPT generator diagnostics" and check.state == "FAIL"
            and "judge cost estimate" in check.detail
            for check in checks
        ))

    def test_owner_worksheet_duplicate_sample_fails_release(self) -> None:
        with TemporaryDirectory() as temp:
            altered = Path(temp) / "worksheet.json"
            payload = json.loads(run_project.GENERATOR_V2_4_JUDGE_WORKSHEET.read_text(encoding="utf-8"))
            payload["sample"][-1] = json.loads(json.dumps(payload["sample"][0]))
            altered.write_text(json.dumps(payload), encoding="utf-8")
            with patch.object(run_project, "GENERATOR_V2_4_JUDGE_WORKSHEET", altered):
                checks, failed = run_project.run()
        self.assertTrue(failed)
        self.assertTrue(any(
            check.name == "RAG GPT generator diagnostics" and check.state == "FAIL"
            and "exactly once" in check.detail
            for check in checks
        ))

    def test_owner_worksheet_root_leak_fails_while_labels_are_empty(self) -> None:
        with TemporaryDirectory() as temp:
            altered = Path(temp) / "worksheet.json"
            payload = json.loads(run_project.GENERATOR_V2_4_JUDGE_WORKSHEET.read_text(encoding="utf-8"))
            payload["expected_verdicts"] = [True]
            altered.write_text(json.dumps(payload), encoding="utf-8")
            with patch.object(run_project, "GENERATOR_V2_4_JUDGE_WORKSHEET", altered):
                checks, failed = run_project.run()
        self.assertTrue(failed)
        self.assertTrue(any(
            check.name == "RAG GPT generator diagnostics" and check.state == "FAIL"
            and "root field" in check.detail
            for check in checks
        ))

    def test_missing_required_core_artifact_fails_only_core(self) -> None:
        with patch.object(run_project, "BASELINE", run_project.ROOT / "missing.json"):
            checks, core_failed = run_project.run()
        self.assertTrue(core_failed)
        self.assertEqual(checks[0].state, "FAIL")

    def test_live_eval_without_key_is_tbd_not_failure(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            checks, core_failed = run_project.run(live_eval=True)
        self.assertFalse(core_failed)
        self.assertTrue(any(check.name == "live-eval credentials" and check.state == "TBD" for check in checks))

    def test_corrupt_optional_rag_artifact_fails_release(self) -> None:
        with TemporaryDirectory() as temp:
            section5 = Path(temp)
            (section5 / "bad.jsonl").write_text("{}\n", encoding="utf-8")
            (section5 / "bad.jsonl.manifest.json").write_text(
                '{"schema_version":1,"corpus_sha256":"wrong","chunk_sha256":"wrong","chunk_count":1}',
                encoding="utf-8",
            )
            with patch.object(run_project, "SECTION5", section5):
                checks, failed = run_project.run()
        self.assertTrue(failed)
        self.assertTrue(any(check.state == "FAIL" and check.name.startswith("RAG ") for check in checks))

    def test_recomputed_metric_drift_from_saved_evidence_fails_release(self) -> None:
        with TemporaryDirectory() as temp:
            altered = Path(temp) / "baseline.json"
            payload = json.loads(run_project.BASELINE.read_text(encoding="utf-8"))
            payload["runs"]["boolean"]["evaluation"]["aggregate"]["mrr"] += 0.01
            altered.write_text(json.dumps(payload), encoding="utf-8")
            with patch.object(run_project, "BASELINE", altered):
                checks, failed = run_project.run()
        self.assertTrue(failed)
        self.assertTrue(any(
            check.name == "current boolean evaluation" and check.state == "FAIL"
            for check in checks
        ))

    def test_corrupt_frozen_qa_fails_release(self) -> None:
        with TemporaryDirectory() as temp:
            altered = Path(temp) / "qa.json"
            payload = json.loads(run_project.QA.read_text(encoding="utf-8"))
            payload["questions"][0]["supporting_spans"][0]["text_sha256"] = "0" * 64
            altered.write_text(json.dumps(payload), encoding="utf-8")
            with patch.object(run_project, "QA", altered):
                checks, failed = run_project.run()
        self.assertTrue(failed)
        self.assertTrue(any(check.name == "approved QA oracle" and check.state == "FAIL" for check in checks))

    def test_nondict_qa_entry_reports_failure_without_traceback(self) -> None:
        with TemporaryDirectory() as temp:
            altered = Path(temp) / "qa.json"
            payload = json.loads(run_project.QA.read_text(encoding="utf-8"))
            payload["questions"].append("junk")
            altered.write_text(json.dumps(payload), encoding="utf-8")
            with patch.object(run_project, "QA", altered):
                checks, failed = run_project.run()
        self.assertTrue(failed)
        self.assertTrue(any(check.name == "approved QA oracle" and check.state == "FAIL" for check in checks))

    def test_embedding_ledger_hash_drift_fails_release(self) -> None:
        with TemporaryDirectory() as temp:
            altered = Path(temp) / "embedding_usage.json"
            payload = json.loads(run_project.EMBEDDING_USAGE.read_text(encoding="utf-8"))
            payload["runs"][0]["artifact_sha256"] = "0" * 64
            altered.write_text(json.dumps(payload), encoding="utf-8")
            with patch.object(run_project, "EMBEDDING_USAGE", altered):
                checks, failed = run_project.run()
        self.assertTrue(failed)
        self.assertTrue(any(check.name == "RAG retrieval evaluation" and check.state == "FAIL" for check in checks))

    def test_bakeoff_usage_drift_fails_release(self) -> None:
        with TemporaryDirectory() as temp:
            altered = Path(temp) / "rag_bakeoff_reanalysis.json"
            payload = json.loads(run_project.RAG_BAKEOFF_REANALYSIS.read_text(encoding="utf-8"))
            payload["actual_usage"]["cost_usd"] += 0.01
            altered.write_text(json.dumps(payload), encoding="utf-8")
            with patch.object(run_project, "RAG_BAKEOFF_REANALYSIS", altered):
                checks, failed = run_project.run()
        self.assertTrue(failed)
        self.assertTrue(any(check.name == "RAG development bake-off evidence" and check.state == "FAIL" for check in checks))

    def test_generator_diagnostic_count_drift_fails_release(self) -> None:
        with TemporaryDirectory() as temp:
            altered = Path(temp) / "rag_generator_v2_3_summary.json"
            payload = json.loads(run_project.GENERATOR_V2_3_SUMMARY.read_text(encoding="utf-8"))
            payload["diagnostic"]["candidates"]["openai/gpt-oss-20b"][
                "answerable_answer_count"
            ] = 10
            altered.write_text(json.dumps(payload), encoding="utf-8")
            with patch.object(run_project, "GENERATOR_V2_3_SUMMARY", altered):
                checks, failed = run_project.run()
        self.assertTrue(failed)
        self.assertTrue(
            any(check.name == "RAG GPT generator diagnostics" and check.state == "FAIL" for check in checks)
        )

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

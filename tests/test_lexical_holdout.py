from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.run_lexical_holdout import _atomic_create, _delta
from src.metrics import EvaluationReport


class HoldoutRunnerTests(unittest.TestCase):
    def test_atomic_create_refuses_existing_holdout(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "holdout.json"
            _atomic_create(path, "first")
            with self.assertRaises(FileExistsError):
                _atomic_create(path, "second")
            self.assertEqual(path.read_text(encoding="utf-8"), "first")

    def test_delta_uses_tuned_minus_baseline(self) -> None:
        baseline = EvaluationReport(
            (1,), (), {"mrr": 0.5, "precision_at": {1: 0.5}, "recall_at": {1: 0.25}, "ndcg_at": {1: 0.4}}
        )
        tuned = EvaluationReport(
            (1,), (), {"mrr": 0.75, "precision_at": {1: 0.75}, "recall_at": {1: 0.5}, "ndcg_at": {1: 0.6}}
        )
        result = _delta(tuned, baseline)
        self.assertAlmostEqual(result["mrr"], 0.25)
        self.assertAlmostEqual(result["ndcg_at"]["1"], 0.2)


if __name__ == "__main__":
    unittest.main()

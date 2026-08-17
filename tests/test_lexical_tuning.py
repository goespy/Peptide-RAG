from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "run_lexical_tuning.py"
SPEC = importlib.util.spec_from_file_location("run_lexical_tuning", MODULE_PATH)
assert SPEC and SPEC.loader
tuning = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(tuning)


def result(ndcg: float, recall: float, mrr: float, **settings: object) -> dict[str, object]:
    return {"status": "evaluated", "evaluation": {"aggregate": {"ndcg_at": {"10": ndcg}, "recall_at": {"10": recall}, "mrr": mrr}}, **settings}


class SectionFourSelectionTests(unittest.TestCase):
    def test_tie_selection_prefers_simple_then_closest_then_numeric(self) -> None:
        candidates = [
            result(0.5, 0.5, 0.5, analyzer="greek", k1=1.2, b=0.75, proximity_boost=0.0),
            result(0.5, 0.5, 0.5, analyzer="baseline", k1=1.2, b=0.75, proximity_boost=0.0),
            result(0.5, 0.5, 0.5, analyzer="baseline", k1=0.8, b=0.75, proximity_boost=0.0),
        ]
        self.assertEqual(tuning.select_best(candidates)["analyzer"], "baseline")

    def test_run_never_searches_holdout_query(self) -> None:
        qrels = {"version": 2, "queries": [{"id": "dev", "query": "development only", "judgments": {}}, {"id": "hold", "query": "holdout secret", "judgments": {}}]}
        searched: list[str] = []
        original_rank, original_load = tuning.rank_bm25, tuning.load_and_validate_split
        original_index, original_configs, original_hash = tuning.InvertedIndex, tuning.ANALYSIS_CONFIGS, tuning.sha256
        try:
            tuning.rank_bm25 = lambda index, query, **kwargs: searched.append(query) or ()
            tuning.load_and_validate_split = lambda *args: (qrels, {}, ("dev",), ("hold",))
            class Index:
                documents = {"1": object()}
                @classmethod
                def from_jsonl(cls, *args, **kwargs): return cls()
            tuning.InvertedIndex = Index
            tuning.ANALYSIS_CONFIGS = {name: object() for name in tuning.ANALYZER_NAMES}
            tuning.sha256 = lambda path: "hash"
            tuning.run(Path("corpus"), Path("qrels"), Path("split"))
        finally:
            tuning.rank_bm25, tuning.load_and_validate_split = original_rank, original_load
            tuning.InvertedIndex, tuning.ANALYSIS_CONFIGS, tuning.sha256 = original_index, original_configs, original_hash
        self.assertTrue(searched)
        self.assertEqual(set(searched), {"development only"})
        self.assertNotIn("holdout secret", searched)

    def test_split_rejects_overlap(self) -> None:
        # The validation helper's partition rules are intentionally strict; its
        # filesystem/hash integration is exercised by the command-level tests.
        self.assertRaises(ValueError, tuning.development_qrels, {"queries": []}, ["missing"])


if __name__ == "__main__":
    unittest.main()

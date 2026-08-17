import unittest
import json
from math import log2

from src.metrics import (
    QueryMetrics,
    aggregate_metrics,
    dcg_at_k,
    evaluate_qrels,
    evaluate_run,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
    render_markdown,
)


class MetricFunctionTests(unittest.TestCase):
    def test_exact_values_and_fewer_than_k_use_k_denominator(self) -> None:
        self.assertEqual(precision_at_k(["a", "x"], {"a", "b"}, 3), 1 / 3)
        self.assertEqual(recall_at_k(["a", "x"], {"a", "b"}, 3), 0.5)

    def test_empty_relevant_set_has_zero_recall(self) -> None:
        self.assertEqual(recall_at_k(["a"], set(), 1), 0.0)
        self.assertEqual(precision_at_k(["a"], set(), 1), 0.0)

    def test_duplicates_are_removed_before_calculation(self) -> None:
        self.assertEqual(precision_at_k(["a", "a", "b"], {"a", "b"}, 2), 1.0)

    def test_invalid_cutoff_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            precision_at_k(["a"], {"a"}, 0)

    def test_reciprocal_rank_and_graded_dcg_are_hand_calculated(self) -> None:
        judgments = {"a": 3, "b": 2, "c": 1}
        retrieved = ["x", "b", "b", "a"]
        self.assertEqual(reciprocal_rank(retrieved, set(judgments)), 1 / 2)
        expected_dcg = 3 / log2(3) + 7 / log2(4)
        self.assertAlmostEqual(dcg_at_k(retrieved, judgments, 3), expected_dcg)
        ideal = 7 + 3 / log2(3) + 1 / log2(4)
        self.assertAlmostEqual(ndcg_at_k(retrieved, judgments, 3), expected_dcg / ideal)

    def test_ndcg_and_rr_are_zero_safe(self) -> None:
        self.assertEqual(reciprocal_rank(["a"], set()), 0.0)
        self.assertEqual(dcg_at_k(["a"], {}, 1), 0.0)
        self.assertEqual(ndcg_at_k(["a"], {}, 1), 0.0)


class EvaluationTests(unittest.TestCase):
    def test_graded_qrels_and_duplicate_retrievals(self) -> None:
        qrels = {
            "queries": [
                {"id": "q1", "query": "first", "judgments": {"a": 2, "b": 1, "x": 0}}
            ]
        }
        result = evaluate_qrels(lambda _: ["a", "a", "x", "b"], qrels, ks=(1, 3))[0]
        self.assertEqual(result.relevant_count, 2)
        self.assertEqual(result.retrieved_count, 3)
        self.assertEqual(result.precision_at, {1: 1.0, 3: 2 / 3})
        self.assertEqual(result.recall_at, {1: 0.5, 3: 1.0})

    def test_malformed_qrels_and_duplicate_ids_are_rejected(self) -> None:
        malformed = {"queries": [{"id": "q1", "query": "x", "judgments": []}]}
        with self.assertRaises(ValueError):
            evaluate_qrels(lambda _: [], malformed)
        duplicate_ids = {
            "queries": [
                {"id": "q1", "query": "x", "judgments": {}},
                {"id": "q1", "query": "y", "judgments": {}},
            ]
        }
        with self.assertRaises(ValueError):
            evaluate_qrels(lambda _: [], duplicate_ids)

    def test_aggregate_means_and_markdown(self) -> None:
        results = [
            QueryMetrics("q1", "alpha", 1, 1, {1: 1.0}, {1: 1.0}),
            QueryMetrics("q2", "beta", 1, 1, {1: 0.0}, {1: 0.0}),
        ]
        self.assertEqual(
            aggregate_metrics(results, (1,)),
            {"query_count": 2, "precision_at": {1: 0.5}, "recall_at": {1: 0.5},
             "mrr": 0.0, "ndcg_at": {1: 0.0}},
        )
        markdown = render_markdown(results, (1,))
        self.assertIn("### Aggregate", markdown)
        self.assertIn("| Queries | MRR | Mean Precision@1 | Mean Recall@1 | Mean NDCG@1 |", markdown)
        self.assertIn("| q1 | alpha | 1 | 1 | 0.000 | 1.000 | 1.000 | 0.000 |", markdown)

    def test_evaluate_run_is_deterministic_json_ready_and_graded(self) -> None:
        qrels = {"queries": [
            {"id": "q2", "query": "second", "judgments": {"a": 3, "b": 1}},
            {"id": "q1", "query": "first", "judgments": {}},
        ]}
        report = evaluate_run(qrels, {"q2": ["x", "a", "a", "b"]}, cutoffs=(1, 3))
        self.assertEqual([result.query_id for result in report.results], ["q2", "q1"])
        self.assertEqual(report.results[0].retrieved_count, 3)
        self.assertEqual(report.results[0].reciprocal_rank, 0.5)
        self.assertAlmostEqual(report.results[0].ndcg_at[3], (7 / log2(3) + 1 / 2) / (7 + 1 / log2(3)))
        self.assertEqual(report.aggregate["mrr"], 0.25)
        payload = report.to_dict()
        self.assertEqual(payload["cutoffs"], [1, 3])
        self.assertEqual(payload["queries"][0]["ndcg_at"].keys(), {"1", "3"})
        self.assertIsInstance(json.dumps(payload, sort_keys=True), str)

    def test_invalid_grades_and_rankings_are_rejected(self) -> None:
        for grade in (True, float("nan"), -1):
            with self.subTest(grade=grade), self.assertRaises(ValueError):
                evaluate_run({"queries": [{"id": "q", "query": "x", "judgments": {"a": grade}}]}, {})
        valid = {"queries": [{"id": "q", "query": "x", "judgments": {}}]}
        with self.assertRaises(ValueError):
            evaluate_run(valid, {"unknown": []})
        with self.assertRaises(ValueError):
            evaluate_run(valid, {"q": "not-a-ranking"})


if __name__ == "__main__":
    unittest.main()

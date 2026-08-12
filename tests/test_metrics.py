import unittest

from src.metrics import (
    QueryMetrics,
    aggregate_metrics,
    evaluate_qrels,
    precision_at_k,
    recall_at_k,
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
            {"query_count": 2, "precision_at": {1: 0.5}, "recall_at": {1: 0.5}},
        )
        markdown = render_markdown(results, (1,))
        self.assertIn("### Aggregate", markdown)
        self.assertIn("| Queries | Mean Precision@1 | Mean Recall@1 |", markdown)
        self.assertIn("| q1 | alpha | 1 | 1 | 1.000 | 1.000 |", markdown)


if __name__ == "__main__":
    unittest.main()

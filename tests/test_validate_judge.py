import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("validate_judge", ROOT / "scripts/validate_judge.py")
judge_validation = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(judge_validation)


def rows():
    output = []
    for model in ("a", "b", "c"):
        for index in range(10):
            output.append({"model": model, "qa_id": f"{model}{index}", "answerability": "answerable" if index < 6 else "unanswerable", "judge": {"faithful": index % 2 == 0, "relevant": True, "citations_correct": True, "refusal_correct": index % 2 == 1}, "answer": {}})
    return output


class JudgeValidationTests(unittest.TestCase):
    def test_stratified_sample_is_deterministic_and_has_ten_outputs(self):
        first = judge_validation.worksheet(rows())
        second = judge_validation.worksheet(list(reversed(rows())))
        self.assertEqual(first, second)
        self.assertEqual(len(first["sample"]), 10)
        self.assertEqual(sum(item["answerability"] == "answerable" for item in first["sample"]), 6)

    def test_labels_are_required_and_kappa_is_honestly_undefined(self):
        packet = judge_validation.worksheet(rows())
        with self.assertRaises(judge_validation.JudgeValidationError): judge_validation.validate_labels(packet)
        for item in packet["sample"]:
            item["owner_label"] = {"reviewer": "owner", "faithful": item["judge"]["faithful"], "relevant": True, "citations_correct": True, "refusal_correct": item["judge"]["refusal_correct"]}
        report = judge_validation.validate_labels(packet)
        self.assertEqual(report["dimensions"]["relevant"]["status"], "inconclusive_undefined_kappa")
        self.assertFalse(report["passes"])

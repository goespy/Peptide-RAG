import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("validate_judge", ROOT / "scripts/validate_judge.py")
judge_validation = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(judge_validation)


def rows():
    output = []
    for model in ("a", "b", "c"):
        for index in range(13):
            answerable = index < 10
            output.append({"model": model, "qa_id": f"qa{index + 1:02d}", "answerability": "answerable" if answerable else "unanswerable", "judge": {"faithful": index % 2 == 0, "relevant": True, "citations_correct": True, "refusal_correct": index % 2 == 1}, "answer": {"status": "answered" if answerable else "insufficient_evidence", "text": "answer", "citations": []}})
    return output


def material():
    questions, contexts = [], []
    for index in range(13):
        qa_id = f"qa{index + 1:02d}"
        questions.append({"id": qa_id, "split": "development", "question": f"question {index}", "answerable": index < 10, "acceptable_answer": f"acceptable {index}"})
        contexts.append({"qa_id": qa_id, "chunks": [{"chunk_id": f"{index}:c0001", "pmid": str(index), "title": "title", "text": "evidence", "start_char": 0, "end_char": 8}]})
    return judge_validation.review_material({"status": "approved", "questions": questions}, {"contexts": contexts})


class JudgeValidationTests(unittest.TestCase):
    def test_stratified_sample_is_deterministic_and_has_ten_outputs(self):
        cases, contexts = material()
        first = judge_validation.worksheet(rows(), cases, contexts)
        second = judge_validation.worksheet(list(reversed(rows())), cases, contexts)
        self.assertEqual(first, second)
        self.assertEqual(len(first["sample"]), 10)
        source = {f"{row['model']}:{row['qa_id']}": row for row in rows()}
        self.assertEqual(sum(source[item["sample_id"]]["answerability"] == "answerable" for item in first["sample"]), 6)
        self.assertTrue(all("judge" not in item for item in first["sample"]))
        self.assertTrue(all("acceptable_answer" not in item for item in first["sample"]))
        self.assertTrue(all(item["question"] and item["retrieved_evidence"] for item in first["sample"]))
        self.assertEqual(len({item["qa_id"] for item in first["sample"] if item["answerability"] == "answerable"}), 6)

    def test_single_generator_sample_uses_seven_answerable_and_all_three_unanswerable(self):
        cases, contexts = material()
        single_model = [row for row in rows() if row["model"] == "a"]
        packet = judge_validation.worksheet(single_model, cases, contexts)
        self.assertEqual(len(packet["sample"]), 10)
        self.assertEqual(
            sum(item["answerability"] == "answerable" for item in packet["sample"]),
            7,
        )
        self.assertEqual(
            sum(item["answerability"] == "unanswerable" for item in packet["sample"]),
            3,
        )
        self.assertEqual(len({item["sample_id"] for item in packet["sample"]}), 10)

    def test_labels_are_required_and_kappa_is_honestly_undefined(self):
        cases, contexts = material()
        packet = judge_validation.worksheet(rows(), cases, contexts)
        saved = rows()
        with self.assertRaises(judge_validation.JudgeValidationError): judge_validation.validate_labels(packet, saved, cases, contexts)
        source = {f"{row['model']}:{row['qa_id']}": row for row in saved}
        for item in packet["sample"]:
            verdict = source[item["sample_id"]]["judge"]
            refusal = item["answer"]["status"] == "insufficient_evidence"
            citations = None if refusal else True
            faithful = None if refusal else verdict["faithful"]
            item["owner_label"] = {"reviewer": "owner", "faithful": faithful, "relevant": True, "citations_correct": citations, "refusal_correct": verdict["refusal_correct"]}
        report = judge_validation.validate_labels(packet, saved, cases, contexts)
        self.assertEqual(report["dimensions"]["relevant"]["status"], "pass_raw_agreement_undefined_kappa")
        self.assertLess(report["dimensions"]["citations_correct"]["n"], 10)
        self.assertTrue(report["passes"])

        packet["sample"][0]["retrieved_evidence"][0]["text"] = "edited"
        with self.assertRaises(judge_validation.JudgeValidationError):
            judge_validation.validate_labels(packet, saved, cases, contexts)

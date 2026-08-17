import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.prepare_qa_review import build_packet, validate_packet


ROOT = Path(__file__).resolve().parents[1]


class PrepareQAReviewTests(unittest.TestCase):
    def test_build_packet_has_verified_unapproved_split(self):
        packet = build_packet(ROOT / "data/corpus.jsonl", ROOT / "data/qrels_v2.json")
        validate_packet(packet, ROOT / "data/corpus.jsonl", ROOT / "data/qrels_v2.json", require_unapproved=True)
        self.assertEqual(packet["status"], "candidate_pool_requires_human_review")
        self.assertEqual(len(packet["cases"]), 20)
        self.assertEqual(sum(case["answerability"] == "answerable" for case in packet["cases"]), 15)
        self.assertTrue(all(case["human_review"]["approved"] is False for case in packet["cases"]))

    def test_cli_writes_packet(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "qa.json"
            result = subprocess.run([sys.executable, "scripts/prepare_qa_review.py", "--output", str(output)], cwd=ROOT, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["status"], "candidate_pool_requires_human_review")

    def test_checked_in_review_draft_has_exact_edited_evidence(self):
        packet = json.loads((ROOT / "data/qa_draft.json").read_text(encoding="utf-8"))
        validate_packet(packet, ROOT / "data/corpus.jsonl", ROOT / "data/qrels_v2.json")
        self.assertTrue(all(case["human_review"]["approved"] for case in packet["cases"]))
        qa13 = next(case for case in packet["cases"] if case["id"] == "qa13")
        self.assertEqual(len(qa13["evidence_spans"]), 2)
        self.assertIn("What effects did tesamorelin", qa13["question"])
        qa02 = next(case for case in packet["cases"] if case["id"] == "qa02")
        self.assertEqual(qa02["pmids"], ["27489425", "38026438"])
        self.assertTrue(qa02["human_review"]["approved"])
        qa03 = next(case for case in packet["cases"] if case["id"] == "qa03")
        self.assertEqual(qa03["question"], "Does TB-500 help injuries or wounds heal?")
        self.assertEqual(qa03["pmids"], ["42542926", "38382158", "41476424"])
        self.assertTrue(qa03["human_review"]["approved"])
        qa04 = next(case for case in packet["cases"] if case["id"] == "qa04")
        self.assertEqual(qa04["question"], "Does ipamorelin increase growth hormone?")
        self.assertEqual(qa04["pmids"], ["10496658", "9849822"])
        self.assertTrue(qa04["human_review"]["approved"])
        qa16 = next(case for case in packet["cases"] if case["id"] == "qa16")
        self.assertEqual(qa16["question"], "What is the safest effective BPC-157 dose for healing a human tendon injury?")
        self.assertEqual(qa16["lexical_absence_check"]["matching_pmids"], ["21030672", "25415472", "36551977", "38980576"])
        qa20 = next(case for case in packet["cases"] if case["id"] == "qa20")
        self.assertIn("long-term treatment of low libido in men", qa20["question"])

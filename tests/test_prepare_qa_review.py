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
        validate_packet(packet, ROOT / "data/corpus.jsonl", ROOT / "data/qrels_v2.json")
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

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.prepare_qa_review import build_packet
from scripts.render_qa_review import render


ROOT = Path(__file__).resolve().parents[1]


class RenderQAReviewTests(unittest.TestCase):
    def test_render_contains_decision_fields(self):
        packet = build_packet(ROOT / "data/corpus.jsonl", ROOT / "data/qrels_v2.json")
        worksheet = render(packet)
        self.assertIn("Candidate pool only", worksheet)
        self.assertIn("Decision: [ ] Approve", worksheet)
        self.assertIn("qa20", worksheet)

    def test_cli_smoke(self):
        with tempfile.TemporaryDirectory() as temporary:
            draft, output = Path(temporary) / "draft.json", Path(temporary) / "review.md"
            prepare = subprocess.run([sys.executable, "scripts/prepare_qa_review.py", "--output", str(draft)], cwd=ROOT, text=True, capture_output=True)
            self.assertEqual(prepare.returncode, 0, prepare.stderr)
            result = subprocess.run([sys.executable, "scripts/render_qa_review.py", "--draft", str(draft), "--output", str(output)], cwd=ROOT, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Exact abstract support", output.read_text(encoding="utf-8"))

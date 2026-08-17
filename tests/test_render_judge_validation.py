from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "render_judge_validation",
    ROOT / "scripts/render_judge_validation.py",
)
renderer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(renderer)


def packet() -> dict:
    sample = []
    for index in range(10):
        sample.append({
            "sample_id": f"review-{index:016X}",
            "question": "Does <peptide> work?",
            "retrieved_evidence": [{
                "citation_id": 1,
                "chunk_id": f"{index}:c0001",
                "pmid": str(index),
                "title": "Study <title>",
                "text": "Evidence & findings.",
                "start_char": 0,
                "end_char": 19,
            }],
            "answer": {
                "status": "answered",
                "text": "Supported <answer> [1]",
                "citations": [{
                    "citation_id": 1,
                    "chunk_id": f"{index}:c0001",
                    "pmid": str(index),
                    "title": "Study <title>",
                }],
            },
            "owner_label": {
                "reviewer": "",
                "faithful": None,
                "relevant": None,
                "citations_correct": None,
                "refusal_correct": None,
            },
        })
    return {
        "version": 4,
        "purpose": "Blind project-owner labels for deterministic judge validation",
        "rubric": {
            "faithful": "rubric",
            "relevant": "rubric",
            "citations_correct": "rubric",
            "refusal_correct": "rubric",
        },
        "source_outputs_sha256": "A" * 64,
        "qa_sha256": "B" * 64,
        "contexts_sha256": "C" * 64,
        "sample": sample,
    }


class RenderJudgeValidationTests(unittest.TestCase):
    def test_render_is_blind_complete_and_html_escaped(self) -> None:
        markdown = renderer.render_markdown(packet())
        self.assertEqual(markdown.count("### Owner labels"), 10)
        self.assertIn("Does &lt;peptide&gt; work?", markdown)
        self.assertIn("Evidence &amp; findings.", markdown)
        self.assertNotIn("answerability", markdown.lower())
        self.assertNotIn("acceptable answer", markdown.lower())
        self.assertNotIn("qa00", markdown)

    def test_rejects_oracle_fields_and_invalid_hashes(self) -> None:
        leaked = packet()
        leaked["sample"][0]["answerability"] = "answerable"
        with self.assertRaises(renderer.RenderError):
            renderer.render_markdown(leaked)
        root_leak = packet()
        root_leak["expected_verdict"] = True
        with self.assertRaises(renderer.RenderError):
            renderer.render_markdown(root_leak)
        nested_leak = packet()
        nested_leak["sample"][0]["answer"]["expected_answer"] = "leak"
        with self.assertRaises(renderer.RenderError):
            renderer.render_markdown(nested_leak)
        malformed = packet()
        malformed["qa_sha256"] = "bad"
        with self.assertRaises(renderer.RenderError):
            renderer.render_markdown(malformed)

    def test_completed_refusal_labels_render_null_not_tbd(self) -> None:
        completed = packet()
        item = completed["sample"][0]
        item["answer"] = {"status": "insufficient_evidence", "text": "Not enough evidence.", "citations": []}
        item["owner_label"] = {
            "reviewer": "owner",
            "faithful": None,
            "relevant": True,
            "citations_correct": None,
            "refusal_correct": True,
        }
        markdown = renderer.render_markdown(completed)
        self.assertIn("- Reviewer: `owner`", markdown)
        self.assertIn("- Faithful: `null`", markdown)
        self.assertIn("- Citations correct: `null`", markdown)

    def test_cli_writes_atomically_and_refuses_overwrite(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "worksheet.json"
            output = root / "review.md"
            source.write_text(json.dumps(packet()), encoding="utf-8")
            self.assertEqual(renderer.main(["--worksheet", str(source), "--output", str(output)]), 0)
            original = output.read_bytes()
            self.assertEqual(renderer.main(["--worksheet", str(source), "--output", str(output)]), 1)
            self.assertEqual(output.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()

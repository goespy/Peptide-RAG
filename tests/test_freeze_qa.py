from __future__ import annotations
import hashlib, json, tempfile, unittest
from pathlib import Path
from scripts.freeze_qa import QAFreezeError, validate_for_freeze, write_atomic

ROOT = Path(__file__).resolve().parents[1]

class FreezeQATests(unittest.TestCase):
    def packet(self, digest: str, approved: bool = True) -> dict:
        cases = []
        for i in range(1, 21):
            answerable = i <= 15
            cases.append({"id": f"qa{i:02d}", "question": f"Question {i}?", "answerability": "answerable" if answerable else "unanswerable", "split": "development" if i <= 10 or 16 <= i <= 18 else "holdout", "pmids": ["1"] if answerable else [], "acceptable_answer": "evidence" if answerable else "", "evidence_spans": [{"pmid":"1","start":0,"end":8,"text":"evidence","sha256":hashlib.sha256(b"evidence").hexdigest().upper()}] if answerable else [], "rationale": "Reviewed rationale.", "human_review":{"approved":approved,"decision":"approve" if approved else "pending","reviewer":"Reviewer" if approved else ""}})
        return {"version": 1, "corpus_sha256": digest, "qrels_v2_sha256": "A" * 64, "development_case_ids": [f"qa{i:02d}" for i in list(range(1, 11)) + [16, 17, 18]], "holdout_case_ids": [f"qa{i:02d}" for i in list(range(11, 16)) + [19, 20]], "cases": cases}
    def test_freezes_only_explicitly_approved_exact_spans(self):
        with tempfile.TemporaryDirectory() as td:
            corpus = Path(td)/"corpus.jsonl"; corpus.write_text('{"id":"1","title":"t","text":"evidence"}\n', encoding="utf-8"); digest=hashlib.sha256(corpus.read_bytes()).hexdigest().upper()
            frozen=validate_for_freeze(self.packet(digest), corpus, expected_corpus_sha256=digest)
            self.assertEqual(frozen["status"], "approved")
            self.assertEqual(len(frozen["questions"]), 20)
            first = frozen["questions"][0]
            self.assertTrue(first["answerable"])
            self.assertEqual(first["relevant_pmids"], ["1"])
            self.assertEqual(set(first["supporting_spans"][0]), {"pmid", "start_char", "end_char", "text_sha256"})
            target=Path(td)/"qa.json"; write_atomic(frozen,target); self.assertTrue(target.exists())
    def test_rejects_pending_and_preserves_existing(self):
        with tempfile.TemporaryDirectory() as td:
            corpus=Path(td)/"c.jsonl"; corpus.write_text('{"id":"1","title":"t","text":"evidence"}\n'); digest=hashlib.sha256(corpus.read_bytes()).hexdigest().upper()
            with self.assertRaises(QAFreezeError): validate_for_freeze(self.packet(digest, False), corpus, expected_corpus_sha256=digest)
            output=Path(td)/"qa.json"; output.write_text("old")
            with self.assertRaises(QAFreezeError): write_atomic({}, output)
            self.assertEqual(output.read_text(), "old")

    def test_checked_in_frozen_oracle_matches_approved_draft(self):
        draft = json.loads((ROOT / "data/qa_draft.json").read_text(encoding="utf-8"))
        expected = validate_for_freeze(draft, ROOT / "data/corpus.jsonl")
        actual = json.loads((ROOT / "data/qa.json").read_text(encoding="utf-8"))
        self.assertEqual(actual, expected)
        development_pmids = {
            pmid
            for question in actual["questions"]
            if question["split"] == "development"
            for pmid in question["relevant_pmids"]
        }
        holdout_pmids = {
            pmid
            for question in actual["questions"]
            if question["split"] == "holdout"
            for pmid in question["relevant_pmids"]
        }
        self.assertTrue(development_pmids.isdisjoint(holdout_pmids))

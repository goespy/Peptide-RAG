"""Contract tests for the frozen example-question artifact and its loader."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from src.examples import (
    EXPECTED_QUESTIONS_PER_TOPIC,
    EXPECTED_TOPICS,
    MAX_QUESTION_CHARACTERS,
    load_examples,
)

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "data" / "examples.json"
CORPUS = ROOT / "data" / "corpus.jsonl"
FROZEN_CORPUS_SHA256 = "231E048971C34EF9203ED3BB20587DDE4C95141AC7EFD2746C85C078A844212C"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


class ExampleArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads(ARTIFACT.read_text(encoding="utf-8"))

    def test_artifact_is_bound_to_the_frozen_corpus(self):
        self.assertEqual(self.payload["corpus_sha256"], FROZEN_CORPUS_SHA256)
        self.assertEqual(self.payload["corpus_sha256"], _sha256(CORPUS))

    def test_eight_topics_with_three_questions_each(self):
        topics = self.payload["topics"]
        self.assertEqual(len(topics), EXPECTED_TOPICS)
        self.assertEqual(self.payload["topic_count"], EXPECTED_TOPICS)
        identifiers = [topic["id"] for topic in topics]
        self.assertEqual(len(identifiers), len(set(identifiers)))
        for topic in topics:
            self.assertEqual(len(topic["questions"]), EXPECTED_QUESTIONS_PER_TOPIC, topic["id"])

    def test_questions_are_non_empty_and_within_the_input_limit(self):
        for topic in self.payload["topics"]:
            for question in topic["questions"]:
                self.assertTrue(question["text"].strip(), topic["id"])
                self.assertLessEqual(len(question["text"]), MAX_QUESTION_CHARACTERS, topic["id"])

    def test_every_supporting_pmid_exists_in_the_frozen_corpus(self):
        known = set()
        for line in CORPUS.read_text(encoding="utf-8").splitlines():
            if line.strip():
                known.add(json.loads(line)["id"])
        for topic in self.payload["topics"]:
            for question in topic["questions"]:
                supporting = question["supporting_pmids"]
                self.assertTrue(supporting, f"{topic['id']} has a question with no supporting record")
                for pmid in supporting:
                    self.assertIn(pmid, known, f"{topic['id']}: PMID {pmid} is not in the frozen corpus")

    def test_lexical_verification_is_recorded_per_question(self):
        for topic in self.payload["topics"]:
            for question in topic["questions"]:
                verification = question["verification"]
                self.assertTrue(verification["in_corpus"])
                self.assertEqual(verification["lexical_top_k"], 5)
                # Hits must be a subset of the declared supporting records.
                self.assertLessEqual(
                    set(verification["lexical_top_k_hits"]),
                    set(question["supporting_pmids"]),
                )

    def test_hybrid_verification_is_not_claimed(self):
        # Hybrid needs a live embedding provider, so the artifact must not assert it.
        self.assertFalse(self.payload["verification"]["hybrid_verified"])
        for topic in self.payload["topics"]:
            for question in topic["questions"]:
                self.assertFalse(question["verification"]["semantic_or_hybrid_confirmed"])

    def test_artifact_is_declared_separate_from_evaluation_data(self):
        self.assertIn("Not used by qrels", self.payload["separation_note"])


class ExampleLoaderTests(unittest.TestCase):
    def test_loader_returns_display_fields_only(self):
        payload = load_examples(ARTIFACT, corpus_path=CORPUS)
        self.assertIsNotNone(payload)
        self.assertEqual(len(payload["topics"]), EXPECTED_TOPICS)
        for topic in payload["topics"]:
            self.assertEqual(sorted(topic), ["id", "name", "questions", "subtitle"])
            for question in topic["questions"]:
                self.assertIsInstance(question, str)

    def test_loader_refuses_a_corpus_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            other = Path(directory) / "corpus.jsonl"
            other.write_text('{"id": "1", "title": "t", "text": "x"}\n', encoding="utf-8")
            self.assertIsNone(load_examples(ARTIFACT, corpus_path=other))

    def test_loader_refuses_a_wrong_version_or_topic_count(self):
        original = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            bad_version = Path(directory) / "version.json"
            bad_version.write_text(json.dumps({**original, "version": 99}), encoding="utf-8")
            self.assertIsNone(load_examples(bad_version, corpus_path=CORPUS))

            short = Path(directory) / "short.json"
            short.write_text(json.dumps({**original, "topics": original["topics"][:2]}), encoding="utf-8")
            self.assertIsNone(load_examples(short, corpus_path=CORPUS))

    def test_loader_refuses_unreadable_or_malformed_input(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "absent.json"
            self.assertIsNone(load_examples(missing, corpus_path=CORPUS))
            broken = Path(directory) / "broken.json"
            broken.write_text("{not json", encoding="utf-8")
            self.assertIsNone(load_examples(broken, corpus_path=CORPUS))


if __name__ == "__main__":
    unittest.main()

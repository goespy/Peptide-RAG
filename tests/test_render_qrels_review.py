from __future__ import annotations

import unittest

from scripts.prepare_qrels_review import Document
from scripts.render_qrels_review import ReviewRenderError, render_markdown, validate_and_join


def candidate_packet() -> dict[str, object]:
    candidates = [
        {
            "id": f"q{number:02d}",
            "family": "BPC-157",
            "source_pmid": str(number),
            "title": "BPC-157 liver protection",
            "text": "BPC 157 protects liver tissue in rats.",
        }
        for number in range(1, 16)
    ]
    return {
        "status": "candidate_selection_only_not_qrels",
        "corpus_sha256": "A" * 64,
        "candidates": candidates,
    }


def draft_packet(query: str = "BPC 157 liver rats") -> dict[str, object]:
    queries = [
        {
            "id": f"q{number:02d}",
            "family": "BPC-157",
            "source_pmid": str(number),
            "query": query,
            "judgments": {str(number): 2},
            "rationale": "The source directly addresses the information need.",
            "human_review": {"approved": False, "reviewer": "", "notes": ""},
        }
        for number in range(1, 16)
    ]
    return {
        "status": "ai_draft_requires_human_review",
        "corpus_sha256": "A" * 64,
        "queries": queries,
    }


def corpus_documents() -> dict[str, Document]:
    return {
        str(number): Document(
            str(number),
            "BPC-157 liver protection",
            "BPC 157 protects liver tissue in rats.",
        )
        for number in range(1, 16)
    }


class ReviewValidationTests(unittest.TestCase):
    def test_valid_draft_renders_unapproved_review_sheet(self) -> None:
        candidates = candidate_packet()
        joined = validate_and_join(candidates, draft_packet(), corpus_documents())

        rendered = render_markdown(candidates, joined)

        self.assertEqual(len(joined), 15)
        self.assertIn("Not an oracle yet", rendered)
        self.assertIn("[ ] Approve", rendered)
        self.assertIn("PMID 1", rendered)

    def test_query_term_must_occur_in_source(self) -> None:
        with self.assertRaisesRegex(ReviewRenderError, "absent from source"):
            validate_and_join(
                candidate_packet(),
                draft_packet("BPC 157 kidney rats"),
                corpus_documents(),
            )

    def test_hashes_must_match(self) -> None:
        draft = draft_packet()
        draft["corpus_sha256"] = "B" * 64
        with self.assertRaisesRegex(ReviewRenderError, "hashes do not match"):
            validate_and_join(candidate_packet(), draft, corpus_documents())

    def test_draft_cannot_be_premarked_approved(self) -> None:
        draft = draft_packet()
        draft["queries"][0]["human_review"]["approved"] = True  # type: ignore[index]
        with self.assertRaisesRegex(ReviewRenderError, "explicitly unapproved"):
            validate_and_join(candidate_packet(), draft, corpus_documents())

    def test_structured_override_uses_verified_frozen_corpus_document(self) -> None:
        candidates = candidate_packet()
        draft = draft_packet()
        suggestion = draft["queries"][0]  # type: ignore[index]
        suggestion["source_pmid"] = "99"
        suggestion["judgments"] = {"99": 2}
        suggestion["selection_override"] = {
            "original_source_pmid": "1",
            "reviewer": "Independent reviewer",
            "reviewed_at": "2026-08-12",
            "reason": "The replacement is more topically aligned.",
        }
        documents = corpus_documents()
        documents["99"] = Document(
            "99", "BPC-157 liver study", "BPC 157 liver response in rats."
        )

        joined = validate_and_join(candidates, draft, documents)
        rendered = render_markdown(candidates, joined)

        self.assertEqual(joined[0][0]["source_pmid"], "99")
        self.assertIn("Reviewer override", rendered)
        self.assertIn("Original deterministic PMID `1`", rendered)

    def test_unstructured_source_mismatch_is_rejected(self) -> None:
        draft = draft_packet()
        suggestion = draft["queries"][0]  # type: ignore[index]
        suggestion["source_pmid"] = "99"
        suggestion["judgments"] = {"99": 2}
        documents = corpus_documents()
        documents["99"] = Document(
            "99", "BPC-157 liver study", "BPC 157 liver response in rats."
        )

        with self.assertRaisesRegex(ReviewRenderError, "requires a selection_override"):
            validate_and_join(candidate_packet(), draft, documents)


if __name__ == "__main__":
    unittest.main()

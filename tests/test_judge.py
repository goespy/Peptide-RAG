import json
import unittest
from unittest.mock import Mock

from src.chunks import Chunk
from src.generation import AnswerResult, Citation
from src.judge import AnswerJudge, DEFAULT_JUDGE_MODEL, validate_verdict
from src.retrieval import RetrievedChunk


def context() -> RetrievedChunk:
    return RetrievedChunk(Chunk("123:c0001", "123", "Study title", "BPC-157 improved healing in rats.", 0, 33, 5), 1.0, "hybrid")


def response(payload):
    value = Mock()
    value.raise_for_status.return_value = None
    value.json.return_value = {"choices": [{"message": {"content": json.dumps(payload)}}]}
    return value


class JudgeTests(unittest.TestCase):
    def test_default_uses_claude_and_missing_key_never_calls_http(self):
        self.assertEqual(AnswerJudge(api_key="key").model, DEFAULT_JUDGE_MODEL)
        session = Mock()
        self.assertIsNone(AnswerJudge(api_key=None, session=session).judge("q", AnswerResult("insufficient_evidence", "x", ()), [context()]))
        session.post.assert_not_called()

    def test_valid_structured_verdict(self):
        session = Mock()
        session.post.return_value = response({"claims": [{"text": "Healing improved.", "supported": True, "citation_ids": [1]}], "faithful": True, "relevant": True, "citations_correct": True})
        item = context()
        answer = AnswerResult("answered", "Healing improved. [1]", (Citation(1, item.pmid, item.chunk_id, item.title),))
        verdict = AnswerJudge(api_key="key", session=session).judge(
            "q", answer, [item], expected_answerable=True
        )
        self.assertTrue(verdict.faithful)
        self.assertTrue(verdict.refusal_correct)
        self.assertTrue(validate_verdict(verdict, [item]))
        self.assertEqual(session.post.call_args.kwargs["json"]["temperature"], 0)
        prompt = session.post.call_args.kwargs["json"]["messages"][1]["content"]
        self.assertNotIn("Oracle answerability", prompt)
        schema = session.post.call_args.kwargs["json"]["response_format"]["json_schema"]["schema"]
        self.assertNotIn("refusal_correct", schema["properties"])

    def test_invalid_schema_and_provider_error_return_none(self):
        session = Mock()
        session.post.return_value = response({"claims": [], "faithful": "yes", "relevant": True, "citations_correct": True})
        self.assertIsNone(AnswerJudge(api_key="key", session=session).judge("q", AnswerResult("insufficient_evidence", "x", ()), [context()]))
        session.post.side_effect = OSError("network")
        self.assertIsNone(AnswerJudge(api_key="key", session=session).judge("q", AnswerResult("insufficient_evidence", "x", ()), [context()]))

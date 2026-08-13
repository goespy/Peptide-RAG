import json
import unittest
from unittest.mock import Mock, patch

from src.chunks import Chunk
from src.generation import (
    AnswerResult,
    Citation,
    GroundedAnswerClient,
    insufficient_evidence,
    requires_medical_refusal,
    validate_answer_result,
)
from src.retrieval import RetrievedChunk


def context() -> RetrievedChunk:
    return RetrievedChunk(Chunk("123:c0001", "123", "Study title", "BPC-157 improved healing in rats.", 0, 33, 5), 1.0, "hybrid")


def response(payload, *, usage=None):
    value = Mock()
    value.raise_for_status.return_value = None
    value.json.return_value = {"choices": [{"message": {"content": json.dumps(payload)}}]}
    if usage is not None:
        value.json.return_value["usage"] = usage
    return value


class GenerationTests(unittest.TestCase):
    def test_no_key_fails_closed_without_http(self):
        session = Mock()
        result = GroundedAnswerClient(api_key=None, session=session).answer("question", [context()])
        self.assertEqual(result, insufficient_evidence())
        session.post.assert_not_called()

    def test_binds_valid_citation_to_supplied_context(self):
        session = Mock()
        session.post.return_value = response(
            {"status": "answered", "text": "Healing improved in rats. [1]", "citation_ids": [1]},
            usage={"prompt_tokens": 20, "completion_tokens": 8, "cost": 0.0001},
        )
        client = GroundedAnswerClient(api_key="key", session=session)
        result = client.answer("Does it heal?", [context()])
        self.assertEqual(result.status, "answered")
        self.assertEqual(result.citations[0], Citation(1, "123", "123:c0001", "Study title"))
        payload = session.post.call_args.kwargs["json"]
        self.assertEqual(payload["temperature"], 0)
        self.assertEqual(payload["max_tokens"], 400)
        self.assertEqual(result.status, "answered")
        self.assertEqual(client.last_metadata["input_tokens"], 20)
        self.assertEqual(client.last_metadata["output_tokens"], 8)
        self.assertEqual(client.last_metadata["cost_usd"], 0.0001)

    def test_invalid_schema_gets_one_repair_then_fails_closed(self):
        session = Mock()
        session.post.side_effect = [response({"status": "answered"}), response({"status": "bad", "text": "x", "citation_ids": []})]
        result = GroundedAnswerClient(api_key="key", session=session).answer("q", [context()])
        self.assertEqual(result.status, "insufficient_evidence")
        self.assertEqual(session.post.call_count, 2)

    def test_provider_error_fails_closed(self):
        session = Mock()
        session.post.side_effect = OSError("network")
        self.assertEqual(GroundedAnswerClient(api_key="key", session=session).answer("q", [context()]).status, "insufficient_evidence")

    @patch("src.generation.time.sleep")
    def test_retries_transient_http_response(self, sleep):
        retry = Mock(status_code=429)
        success = response({"status": "answered", "text": "Healing improved. [1]", "citation_ids": [1]})
        success.status_code = 200
        session = Mock()
        session.post.side_effect = [retry, success]
        result = GroundedAnswerClient(api_key="key", session=session, retries=1).answer("q", [context()])
        self.assertEqual(result.status, "answered")
        self.assertEqual(session.post.call_count, 2)
        sleep.assert_called_once_with(0.25)

    def test_validator_rejects_unknown_or_uncited_factual_sentence(self):
        item = context()
        valid = AnswerResult("answered", "The study reported healing. [1]", (Citation(1, item.pmid, item.chunk_id, item.title),))
        self.assertTrue(validate_answer_result(valid, [item]))
        self.assertFalse(validate_answer_result(AnswerResult("answered", "The study reported healing.", valid.citations), [item]))
        self.assertFalse(validate_answer_result(AnswerResult("answered", "The study reported healing. [2]", valid.citations), [item]))
        self.assertFalse(validate_answer_result(AnswerResult("answered", "17 patients.", valid.citations), [item]))

    def test_refuses_personalized_or_prescriptive_dosing_before_http(self):
        self.assertTrue(requires_medical_refusal("What dose of BPC-157 is safe to take?"))
        self.assertTrue(requires_medical_refusal("Should I inject this peptide?"))
        self.assertTrue(requires_medical_refusal("What dose should I take based on the study?"))
        self.assertFalse(requires_medical_refusal("What dose was administered to rats in the study?"))
        session = Mock()
        result = GroundedAnswerClient(api_key="key", session=session).answer(
            "What dose should I take?", [context()]
        )
        self.assertEqual(result.status, "insufficient_evidence")
        session.post.assert_not_called()

    def test_validator_rejects_unused_declared_citations(self):
        item = context()
        second = RetrievedChunk(
            Chunk("456:c0001", "456", "Other", "Other evidence.", 0, 15, 2),
            0.5,
            "hybrid",
        )
        result = AnswerResult(
            "answered",
            "The study reported healing. [1]",
            (
                Citation(1, item.pmid, item.chunk_id, item.title),
                Citation(2, second.pmid, second.chunk_id, second.title),
            ),
        )
        self.assertFalse(validate_answer_result(result, [item, second]))

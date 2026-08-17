from concurrent.futures import ThreadPoolExecutor
import json
import hashlib
import threading
import unittest
from unittest.mock import Mock, patch

import requests

from src.chunks import Chunk
from src.generation import (
    AnswerResult,
    Citation,
    GroundedAnswerClient,
    SYSTEM_PROMPT_V2,
    SYSTEM_PROMPT_V3,
    insufficient_evidence,
    requires_medical_refusal,
    validate_answer_result,
)
from src.retrieval import RetrievedChunk


def context() -> RetrievedChunk:
    return RetrievedChunk(Chunk("123:c0001", "123", "Study title", "BPC-157 improved healing in rats.", 0, 33, 5), 1.0, "hybrid")


def response(payload, *, usage=None, finish_reason=None):
    value = Mock()
    value.raise_for_status.return_value = None
    value.json.return_value = {
        "choices": [
            {"message": {"content": json.dumps(payload)}, "finish_reason": finish_reason}
        ]
    }
    if usage is not None:
        value.json.return_value["usage"] = usage
    return value


class GenerationTests(unittest.TestCase):
    def test_concurrent_answers_keep_request_metadata_thread_local(self):
        barrier = threading.Barrier(2)

        class QuerySession:
            def post(self, _url, *, json, **_kwargs):
                content = json["messages"][1]["content"]
                tokens = 11 if "first question" in content else 22
                return response(
                    {
                        "status": "answered",
                        "text": f"Supported result {tokens}. [1]",
                        "citation_ids": [1],
                    },
                    usage={"prompt_tokens": tokens, "completion_tokens": 3, "cost": tokens / 1_000_000},
                )

        client = GroundedAnswerClient(api_key="key", session=QuerySession())

        def run(query):
            result = client.answer(query, [context()])
            barrier.wait(timeout=2)
            return result.text, dict(client.last_metadata)

        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(run, "first question")
            second = pool.submit(run, "second question")
            first_text, first_metadata = first.result(timeout=3)
            second_text, second_metadata = second.result(timeout=3)
        self.assertIn("11", first_text)
        self.assertIn("22", second_text)
        self.assertEqual(first_metadata["input_tokens"], 11)
        self.assertEqual(second_metadata["input_tokens"], 22)

    def test_production_http_sessions_are_thread_local_and_concurrent(self):
        barrier = threading.Barrier(2)
        created = []

        class ConcurrentSession:
            def post(self, _url, **_kwargs):
                barrier.wait(timeout=2)
                return response(
                    {
                        "status": "answered",
                        "text": "Supported finding. [1]",
                        "citation_ids": [1],
                    }
                )

        def create_session():
            session = ConcurrentSession()
            created.append(session)
            return session

        with patch("src.generation.requests.Session", side_effect=create_session):
            client = GroundedAnswerClient(api_key="key")
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [
                    pool.submit(client.answer, query, [context()])
                    for query in ("first", "second")
                ]
                results = [future.result(timeout=3) for future in futures]
        self.assertEqual(len(created), 2)
        self.assertTrue(all(result.status == "answered" for result in results))

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

    def test_derived_citation_mode_removes_redundant_ids_and_binds_markers(self):
        session = Mock()
        session.post.return_value = response(
            {"status": "answered", "text": "Healing improved in rats. [1]"},
            finish_reason="stop",
        )
        client = GroundedAnswerClient(
            api_key="key",
            session=session,
            citation_mode="derived_from_text_markers",
            require_supported_parameters=True,
        )
        result = client.answer("Does it heal?", [context()])
        self.assertEqual(result.citations, (Citation(1, "123", "123:c0001", "Study title"),))
        payload = session.post.call_args.kwargs["json"]
        self.assertNotIn(
            "citation_ids",
            payload["response_format"]["json_schema"]["schema"]["properties"],
        )
        self.assertEqual(payload["provider"], {"require_parameters": True})

    def test_reasoning_effort_is_explicit_and_invalid_combinations_fail_closed(self):
        client = GroundedAnswerClient(
            api_key="key",
            model="model",
            reasoning_effort="low",
            exclude_reasoning=True,
            system_prompt=SYSTEM_PROMPT_V3,
        )
        payload = client._payload("question", (context(),))
        self.assertEqual(payload["reasoning"], {"effort": "low", "exclude": True})
        with self.assertRaises(ValueError):
            GroundedAnswerClient(api_key="key", model="model", reasoning_effort="invalid")
        with self.assertRaises(ValueError):
            GroundedAnswerClient(api_key="key", model="model", exclude_reasoning=True)

    def test_valid_refusal_can_receive_one_general_evidence_reconsideration(self):
        session = Mock()
        session.post.side_effect = [
            response(
                {
                    "status": "insufficient_evidence",
                    "text": "Insufficient evidence in the retrieved research abstracts.",
                }
            ),
            response(
                {
                    "status": "answered",
                    "text": "Ipamorelin released growth hormone in the reported study. [1]",
                }
            ),
        ]
        client = GroundedAnswerClient(
            api_key="key",
            session=session,
            citation_mode="derived_from_text_markers",
            reconsider_insufficient_evidence=True,
        )
        result = client.answer("Does ipamorelin increase growth hormone?", [context()])
        self.assertEqual(result.status, "answered")
        self.assertEqual(session.post.call_count, 2)
        second_payload = session.post.call_args_list[1].kwargs["json"]
        self.assertEqual(second_payload["messages"][2]["role"], "assistant")
        self.assertIn("all five supplied passages", second_payload["messages"][3]["content"])
        self.assertNotIn("qa04", json.dumps(second_payload).lower())
        self.assertEqual(
            client.last_metadata["final_outcome"],
            "answered_after_refusal_reconsideration",
        )

    def test_refusal_reconsideration_may_retain_refusal_and_has_no_third_call(self):
        refusal = response(
            {
                "status": "insufficient_evidence",
                "text": "Insufficient evidence in the retrieved research abstracts.",
            }
        )
        session = Mock()
        session.post.side_effect = [refusal, refusal]
        client = GroundedAnswerClient(
            api_key="key",
            session=session,
            citation_mode="derived_from_text_markers",
            reconsider_insufficient_evidence=True,
        )
        result = client.answer("Is there a randomized human trial?", [context()])
        self.assertEqual(result.status, "insufficient_evidence")
        self.assertEqual(session.post.call_count, 2)
        self.assertEqual(
            client.last_metadata["final_outcome"],
            "model_insufficient_evidence_after_reconsideration",
        )

    def test_refusal_reconsideration_retains_valid_refusal_if_second_output_is_invalid(self):
        session = Mock()
        session.post.side_effect = [
            response(
                {
                    "status": "insufficient_evidence",
                    "text": "Insufficient evidence in the retrieved research abstracts.",
                }
            ),
            response({"status": "answered", "text": "Unsupported answer."}),
        ]
        client = GroundedAnswerClient(
            api_key="key",
            session=session,
            citation_mode="derived_from_text_markers",
            reconsider_insufficient_evidence=True,
        )
        result = client.answer("Question", [context()])
        self.assertEqual(result, insufficient_evidence())
        self.assertEqual(session.post.call_count, 2)
        self.assertEqual(
            client.last_metadata["final_outcome"],
            "model_insufficient_evidence_after_failed_reconsideration",
        )
        self.assertEqual(
            client.last_metadata["failure_reason"],
            "answered_missing_text_or_citations",
        )

    def test_invalid_schema_gets_one_repair_then_fails_closed(self):
        session = Mock()
        session.post.side_effect = [response({"status": "answered"}), response({"status": "bad", "text": "x", "citation_ids": []})]
        result = GroundedAnswerClient(api_key="key", session=session).answer("q", [context()])
        self.assertEqual(result.status, "insufficient_evidence")
        self.assertEqual(session.post.call_count, 2)

    def test_v2_repair_sees_invalid_output_and_records_finish_reason(self):
        session = Mock()
        invalid = {"status": "answered"}
        session.post.side_effect = [
            response(invalid, finish_reason="length"),
            response(
                {
                    "status": "answered",
                    "text": "Healing improved in rats. [1]",
                    "citation_ids": [1],
                },
                finish_reason="stop",
            ),
        ]
        client = GroundedAnswerClient(
            api_key="key",
            session=session,
            max_tokens=800,
            system_prompt=SYSTEM_PROMPT_V2,
        )
        result = client.answer("Does it heal?", [context()])
        self.assertEqual(result.status, "answered")
        repair_payload = session.post.call_args_list[1].kwargs["json"]
        self.assertEqual(repair_payload["max_tokens"], 800)
        self.assertEqual(repair_payload["messages"][2]["role"], "assistant")
        self.assertEqual(json.loads(repair_payload["messages"][2]["content"]), invalid)
        self.assertIn("schema_fields_invalid", repair_payload["messages"][3]["content"])
        attempts = client.last_metadata["attempts"]
        self.assertEqual(attempts[0]["finish_reason"], "length")
        self.assertEqual(attempts[0]["outcome"], "schema_fields_invalid")
        self.assertEqual(
            attempts[0]["raw_output_sha256"],
            hashlib.sha256(json.dumps(invalid).encode("utf-8")).hexdigest().upper(),
        )
        self.assertNotIn("raw_output", attempts[0])
        self.assertEqual(client.last_metadata["final_outcome"], "answered_after_repair")

    def test_repair_does_not_fabricate_an_assistant_body_after_transport_failure(self):
        session = Mock()
        session.post.side_effect = OSError("network")
        client = GroundedAnswerClient(api_key="key", session=session, retries=0)
        result = client.answer("Does it heal?", [context()])
        self.assertEqual(result.status, "insufficient_evidence")
        repair_payload = session.post.call_args_list[1].kwargs["json"]
        self.assertEqual(
            [message["role"] for message in repair_payload["messages"]],
            ["system", "user", "user"],
        )
        self.assertIn("no usable response body", repair_payload["messages"][2]["content"])

    @patch("src.generation.time.sleep")
    def test_repair_uses_last_received_body_and_its_matching_failure(self, _sleep):
        invalid = Mock(status_code=200)
        invalid.raise_for_status.return_value = None
        invalid.json.return_value = {
            "choices": [{"message": {"content": "not-json"}, "finish_reason": "stop"}]
        }
        session = Mock()
        session.post.side_effect = [
            invalid,
            OSError("retry failed"),
            response(
                {
                    "status": "answered",
                    "text": "Healing improved in rats. [1]",
                    "citation_ids": [1],
                }
            ),
        ]
        client = GroundedAnswerClient(api_key="key", session=session, retries=1)
        result = client.answer("Does it heal?", [context()])
        self.assertEqual(result.status, "answered")
        repair_payload = session.post.call_args_list[2].kwargs["json"]
        self.assertEqual(repair_payload["messages"][2]["content"], "not-json")
        self.assertIn("invalid_json", repair_payload["messages"][3]["content"])

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
        self.assertTrue(requires_medical_refusal("What is the safest effective BPC-157 dose for a human tendon injury?"))
        self.assertFalse(requires_medical_refusal("What dose was administered to rats in the study?"))
        self.assertFalse(requires_medical_refusal("What effective dose was reported in the human trial?"))
        session = Mock()
        result = GroundedAnswerClient(api_key="key", session=session).answer(
            "What dose should I take?", [context()]
        )
        self.assertEqual(result.status, "insufficient_evidence")
        session.post.assert_not_called()

    def test_records_safe_provider_error_shape_without_body(self):
        failure = Mock(status_code=400, headers={})
        failure.json.return_value = {"error": {"code": 400, "type": "invalid_request", "message": "private detail"}}
        failure.raise_for_status.side_effect = requests.HTTPError("bad request")
        session = Mock()
        session.post.return_value = failure
        client = GroundedAnswerClient(api_key="key", session=session, retries=0)
        client.answer("question", [context()])
        first = client.last_metadata["attempts"][0]
        self.assertEqual(first["provider_error_code"], 400)
        self.assertEqual(first["provider_error_type"], "invalid_request")
        self.assertNotIn("message", first)
        self.assertNotIn("raw_output", first)

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

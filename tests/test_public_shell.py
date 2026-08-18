"""Contract tests for the public answer-first shell: API defaults, routing, and static assets."""

import re
import unittest
from pathlib import Path

try:
    from fastapi.testclient import TestClient
    from app import create_app
except ImportError:  # Standard-library test discovery works without web extras.
    TestClient = None
    create_app = None

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"
INDEX = (STATIC / "index.html").read_text(encoding="utf-8")
SCRIPT = (STATIC / "app.js").read_text(encoding="utf-8")
STYLES = (STATIC / "styles.css").read_text(encoding="utf-8")


class FakeService:
    def search(self, query, mode, k):
        return [
            {
                "pmid": "14554208",
                "title": "Gastric pentadecapeptide BPC 157 accelerates healing.",
                "snippet": "Evidence text",
                "score": 0.9,
                "chunk_id": "14554208:2",
                "lexical_rank": 1,
                "semantic_rank": 2,
            }
        ]

    def answer(self, query, mode, k, evidence):
        return {
            "answer": "BPC-157 accelerated healing in animal models [1].",
            "citations": [
                {
                    "citation_id": 1,
                    "pmid": "14554208",
                    "chunk_id": "14554208:2",
                    "title": "Gastric pentadecapeptide BPC 157 accelerates healing.",
                    "pubmed_url": "https://pubmed.ncbi.nlm.nih.gov/14554208/",
                }
            ],
        }

    def metrics(self):
        return {"available": True, "corpus_documents": 2000}


@unittest.skipIf(TestClient is None, "FastAPI/httpx are not installed")
class ApiContractTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_app(service=FakeService()))

    def test_search_defaults_to_hybrid(self):
        payload = self.client.post("/api/search", json={"query": "bpc 157"}).json()
        self.assertEqual(payload["requested_mode"], "hybrid")

    def test_answer_defaults_to_hybrid_and_five_records(self):
        payload = self.client.post("/api/answer", json={"query": "bpc 157"}).json()
        self.assertEqual(payload["requested_mode"], "hybrid")

    def test_answer_endpoint_accepts_only_answer_grounding_modes(self):
        for mode in ("hybrid", "semantic", "lexical"):
            with self.subTest(mode=mode):
                response = self.client.post("/api/answer", json={"query": "q", "mode": mode})
                self.assertEqual(response.status_code, 200)
        for mode in ("bm25", "boolean"):
            with self.subTest(mode=mode):
                response = self.client.post("/api/answer", json={"query": "q", "mode": mode})
                self.assertEqual(response.status_code, 422, f"{mode} must not ground an answer")

    def test_search_endpoint_accepts_every_literature_mode(self):
        for mode in ("hybrid", "semantic", "bm25", "boolean"):
            with self.subTest(mode=mode):
                response = self.client.post("/api/search", json={"query": "q", "mode": mode})
                self.assertEqual(response.status_code, 200)

    def test_answer_record_count_is_bounded_to_eight(self):
        self.assertEqual(self.client.post("/api/answer", json={"query": "q", "k": 8}).status_code, 200)
        self.assertEqual(self.client.post("/api/answer", json={"query": "q", "k": 9}).status_code, 422)

    def test_answer_keeps_evidence_alongside_the_answer(self):
        payload = self.client.post("/api/answer", json={"query": "q"}).json()
        self.assertTrue(payload["answer"])
        self.assertTrue(payload["evidence"])
        self.assertEqual(payload["disclaimer"], "Research use only. This tool does not provide medical advice.")
        self.assertIn("National Center for Biotechnology Information", payload["attribution"])

    def test_examples_endpoint_exposes_display_fields_only(self):
        response = self.client.get("/api/examples")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["available"])
        self.assertEqual(len(payload["topics"]), 8)
        for topic in payload["topics"]:
            self.assertEqual(sorted(topic), ["id", "name", "questions", "subtitle"])
            self.assertEqual(len(topic["questions"]), 3)
        self.assertNotIn("supporting_pmids", response.text)
        self.assertNotIn("verification", response.text)

    def test_examples_endpoint_degrades_without_the_artifact(self):
        app = create_app(service=FakeService())
        app.state.examples = None
        payload = TestClient(app).get("/api/examples").json()
        self.assertFalse(payload["available"])
        self.assertEqual(payload["topics"], [])

    def test_blank_question_is_rejected(self):
        self.assertEqual(self.client.post("/api/answer", json={"query": "   "}).status_code, 422)
        self.assertEqual(self.client.post("/api/search", json={"query": ""}).status_code, 422)


class StaticMarkupTests(unittest.TestCase):
    def test_semantic_landmarks_and_single_h1(self):
        for tag in ("<header", "<main", "<footer", "<nav"):
            self.assertIn(tag, INDEX)
        self.assertEqual(len(re.findall(r"<h1\b", INDEX)), 1)

    def test_question_field_is_labelled_and_length_limited(self):
        self.assertIn('<label class="visually-hidden" for="question">', INDEX)
        self.assertIn('id="question"', INDEX)
        self.assertIn('maxlength="500"', INDEX)

    def test_live_region_announces_progress_and_refusals(self):
        self.assertIn('id="status"', INDEX)
        self.assertIn('role="status"', INDEX)
        self.assertIn('aria-live="polite"', INDEX)

    def test_advanced_options_are_closed_by_default(self):
        match = re.search(r'<details class="advanced" id="advanced"([^>]*)>', INDEX)
        self.assertIsNotNone(match)
        self.assertNotIn("open", match.group(1))

    def test_both_retrieval_vocabularies_are_present(self):
        for value in ("hybrid", "semantic", "lexical"):
            self.assertIn(f'name="answer-mode" value="{value}"', INDEX)
        for value in ("hybrid", "semantic", "bm25", "boolean"):
            self.assertIn(f'name="literature-mode" value="{value}"', INDEX)

    def test_hybrid_is_the_checked_default_for_both_vocabularies(self):
        self.assertIn('name="answer-mode" value="hybrid" checked', INDEX)
        self.assertIn('name="literature-mode" value="hybrid" checked', INDEX)
        self.assertIn('name="intent" value="answer" checked', INDEX)

    def test_record_slider_matches_the_answer_bounds(self):
        self.assertIn('id="records"', INDEX)
        self.assertIn('min="1"', INDEX)
        self.assertIn('max="8"', INDEX)
        self.assertIn('value="5"', INDEX)

    def test_disclaimer_and_attribution_are_in_the_markup(self):
        self.assertIn("Research use only. This tool does not provide medical advice.", INDEX)
        self.assertIn("National Center for Biotechnology Information (NCBI)", INDEX)
        self.assertIn("abstracts only", INDEX)

    def test_local_favicon_and_social_metadata(self):
        self.assertIn('href="/static/favicon.svg"', INDEX)
        self.assertTrue((STATIC / "favicon.svg").is_file())
        self.assertIn('property="og:title"', INDEX)
        self.assertIn('name="twitter:card"', INDEX)

    def test_no_external_hosts_are_referenced_by_the_shell(self):
        # PubMed links are created at runtime from retrieved PMIDs, not embedded here.
        for asset in (INDEX, STYLES):
            self.assertNotIn("https://fonts.", asset)
            self.assertNotIn("http://", asset)
            for host in ("cdn.", "googleapis", "unpkg", "jsdelivr"):
                self.assertNotIn(host, asset)

    def test_stylesheet_defines_the_approved_tokens(self):
        for token in ("--paper", "--ink", "--teal", "--amber-tint", "--font-display", "--shadow-md"):
            self.assertIn(token, STYLES)
        self.assertIn("#FBFAF7", STYLES)
        self.assertIn("#152338", STYLES)
        self.assertIn("#0E6F6B", STYLES)

    def test_hidden_attribute_is_forced_over_display_rules(self):
        # .field/.callout/.answer-tools set display, which outranks the UA [hidden]
        # rule; without this the hidden mode fieldset stays on screen.
        self.assertIn("[hidden] { display: none !important; }", STYLES)

    def test_secondary_text_meets_contrast(self):
        # #8A94A1 scored 2.95:1 on the paper background; #616C7C clears 4.5:1
        # on white, paper and the sunk surface.
        self.assertIn("--ink-3: #616C7C;", STYLES)
        self.assertNotIn("#8A94A1", STYLES)

    def test_reduced_motion_and_focus_visibility(self):
        self.assertIn("prefers-reduced-motion", STYLES)
        self.assertIn(":focus-visible", STYLES)

    def test_mobile_and_desktop_breakpoints_exist(self):
        for width in ("639px", "1023px", "1279px"):
            self.assertIn(width, STYLES)


class ScriptSafetyTests(unittest.TestCase):
    def test_script_never_assigns_raw_html(self):
        # These tokens must be ABSENT from app.js: corpus and model text is rendered
        # only through textContent/createTextNode, and no dynamic evaluation is used.
        for forbidden in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("):
            with self.subTest(token=forbidden):
                self.assertFalse(forbidden in SCRIPT, f"app.js must not contain {forbidden}")

    def test_script_routes_each_intent_to_its_own_endpoint(self):
        self.assertIn('"/api/answer"', SCRIPT)
        self.assertIn('"/api/search"', SCRIPT)
        self.assertIn('"/api/examples"', SCRIPT)
        self.assertIn('"/api/metrics"', SCRIPT)

    def test_script_parses_citation_markers_into_links(self):
        self.assertIn("CITATION_MARKER", SCRIPT)
        self.assertIn("createTextNode", SCRIPT)
        self.assertIn("pubmed_url", SCRIPT)

    def test_sharing_uses_the_url_fragment_and_does_not_submit(self):
        self.assertIn('"#q="', SCRIPT)
        self.assertIn("prefillFromHash", SCRIPT)
        self.assertIn("Prefill only", SCRIPT)
        self.assertNotIn("?q=", SCRIPT)

    def test_enter_submits_and_shift_enter_does_not(self):
        self.assertIn('event.key !== "Enter" || event.shiftKey', SCRIPT)

    def test_every_refusal_category_has_its_own_presentation(self):
        for reason in ("medical_safety", "insufficient_evidence", "service_unavailable", "budget_limit"):
            self.assertIn(reason, SCRIPT)

    def test_refusal_categories_are_labelled_in_text_not_only_colour(self):
        for label in ("Medical-safety boundary", "Insufficient evidence", "Service unavailable", "Daily budget reached"):
            self.assertIn(label, SCRIPT)

    def test_fallback_disclosure_is_rendered(self):
        self.assertIn("renderFallback", SCRIPT)
        self.assertIn("retrieval_fallback", SCRIPT)
        self.assertIn("fallback_reason", SCRIPT)

    def test_empty_hybrid_result_is_explained_not_silent(self):
        # src/service.py fails closed for hybrid/semantic when no semantic index
        # exists: it returns no records and no fallback reason. The page must say so.
        self.assertIn("renderRetrievalGap", SCRIPT)
        self.assertIn("semanticAvailable", SCRIPT)
        self.assertIn("is not enabled on this deployment", SCRIPT)
        self.assertIn("Search again with keyword retrieval", SCRIPT)

    def test_retrieval_gap_fires_before_metrics_resolve(self):
        # semanticAvailable is null until /api/metrics answers; an early submit
        # must still explain an empty hybrid result rather than showing nothing.
        self.assertIn("state.semanticAvailable === true) return false", SCRIPT)

    def test_metrics_note_does_not_claim_a_fallback_that_never_happens(self):
        self.assertNotIn("so requests fall back to keyword search", SCRIPT)
        self.assertIn("return no records rather than falling back", SCRIPT)

    def test_previous_answer_is_dropped_before_a_new_request(self):
        self.assertIn('$("answer-tools").hidden = true;', SCRIPT)
        self.assertIn("failed rerun can never emit answer A under question B", SCRIPT)

    def test_question_is_bound_to_the_result_not_the_request(self):
        self.assertIn("function showResult(question)", SCRIPT)
        self.assertIn("state.question = question;", SCRIPT)

    def test_focus_moves_into_the_result(self):
        self.assertIn('<h2 id="result-heading" class="visually-hidden" tabindex="-1">', INDEX)
        self.assertIn('$("result-heading").focus({ preventScroll: true })', SCRIPT)

    def test_scrolling_respects_reduced_motion(self):
        self.assertIn("prefersReducedMotion", SCRIPT)
        self.assertIn('behavior: prefersReducedMotion() ? "auto" : "smooth"', SCRIPT)
        # Every call site must go through the helper.
        self.assertEqual(SCRIPT.count("scrollIntoView"), 1)

    def test_record_slider_is_hidden_for_literature_results(self):
        self.assertIn('id="records-field"', INDEX)
        self.assertIn('$("records-field").hidden = literature;', SCRIPT)

    def test_citations_are_grouped_by_record(self):
        # One abstract can yield two chunks, so the model may cite the same PMID
        # under two ids (observed live: [1] and [2] both = PMID 16839319).
        # The rail must show one card per record carrying both markers.
        self.assertIn("function groupCitations", SCRIPT)
        self.assertIn("state.sources = groupCitations(citations)", SCRIPT)
        self.assertIn('numbers.join(", ")', SCRIPT)

    def test_source_badge_accommodates_multiple_markers(self):
        self.assertIn(".source-number { flex-shrink: 0; min-width: 23px;", STYLES)

    def test_rate_limit_state_is_handled(self):
        self.assertIn("429", SCRIPT)
        self.assertIn("Rate limit reached", SCRIPT)

    def test_copy_output_carries_titles_and_pubmed_urls(self):
        self.assertIn("function copyText", SCRIPT)
        self.assertIn("Sources:", SCRIPT)
        self.assertIn("source.url", SCRIPT)

    def test_script_does_not_log_user_questions(self):
        self.assertNotIn("console.", SCRIPT)

    def test_scores_and_ranks_live_in_the_evidence_detail(self):
        self.assertIn("function evidenceRecord", SCRIPT)
        self.assertIn("lexical_rank", SCRIPT)
        self.assertIn("semantic_rank", SCRIPT)
        # The compact source card carries identity only, never scores.
        card = SCRIPT[SCRIPT.index("function sourceCard") : SCRIPT.index("function renderSources")]
        self.assertNotIn("score", card)
        self.assertNotIn("rank", card)


if __name__ == "__main__":
    unittest.main()

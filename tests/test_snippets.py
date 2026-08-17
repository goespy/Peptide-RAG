from __future__ import annotations

import unittest

from src.snippets import make_html_snippet, make_snippet, query_terms


class SnippetTests(unittest.TestCase):
    def test_selects_earliest_window_with_most_distinct_query_terms(self) -> None:
        text = "x" * 120 + " alpha " + "y" * 120 + " beta gamma"

        snippet = make_snippet(text, "alpha beta gamma", max_chars=30)

        self.assertIn("[[beta]] [[gamma]]", snippet)
        self.assertNotIn("[[alpha]]", snippet)
        self.assertTrue(snippet.startswith("…"))

    def test_marks_original_text_without_modifying_the_source(self) -> None:
        text = "BPC-157 supports Tendon repair."

        self.assertEqual(
            make_snippet(text, "bpc 157 tendon"),
            "[[BPC]]-[[157]] supports [[Tendon]] repair.",
        )
        self.assertEqual(text, "BPC-157 supports Tendon repair.")

    def test_truncation_uses_ellipses(self) -> None:
        snippet = make_snippet("alpha " + "x" * 300, "alpha", max_chars=20)

        self.assertTrue(snippet.endswith("…"))
        self.assertIn("[[alpha]]", snippet)

    def test_html_variant_escapes_document_controlled_text(self) -> None:
        self.assertEqual(
            make_html_snippet("<script>alpha & beta</script>", "alpha"),
            "&lt;script&gt;[[alpha]] &amp; beta&lt;/script&gt;",
        )

    def test_empty_or_malformed_query_never_crashes(self) -> None:
        self.assertEqual(query_terms("AND !!! OR"), frozenset())
        self.assertEqual(make_snippet("ordinary text", "!!!"), "ordinary text")


if __name__ == "__main__":
    unittest.main()

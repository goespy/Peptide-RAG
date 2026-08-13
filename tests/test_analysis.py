from __future__ import annotations

import unittest

from src.analysis import (
    ANALYSIS_CONFIGS,
    BASELINE_ANALYSIS,
    GREEK_ANALYSIS,
    GREEK_STOPWORDS_ANALYSIS,
    STOPWORDS_ANALYSIS,
    AnalysisConfig,
    analyze,
)


class AnalysisTests(unittest.TestCase):
    def test_named_configurations_are_versioned(self) -> None:
        self.assertEqual(
            tuple(ANALYSIS_CONFIGS), ("baseline", "greek", "stopwords", "greek_stopwords")
        )
        self.assertEqual(analyze("BPC-157"), ("bpc", "157"))
        self.assertEqual(analyze("BPC-157", BASELINE_ANALYSIS), ("bpc", "157"))

    def test_greek_expansion_happens_after_nfkc_casefold(self) -> None:
        self.assertEqual(analyze("Thymosin Β4 and β", GREEK_ANALYSIS), ("thymosin", "beta4", "and", "beta"))

    def test_stopword_experiment_does_not_stem(self) -> None:
        self.assertEqual(analyze("The peptides were healing", STOPWORDS_ANALYSIS), ("peptides", "healing"))
        self.assertEqual(
            analyze("The β peptide is healing", GREEK_STOPWORDS_ANALYSIS),
            ("beta", "peptide", "healing"),
        )

    def test_composed_and_decomposed_unicode_match(self) -> None:
        self.assertEqual(analyze("café"), analyze("cafe\u0301"))

    def test_config_is_frozen(self) -> None:
        config = AnalysisConfig()
        with self.assertRaises(AttributeError):
            config.name = "changed"  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()

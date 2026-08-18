"""Public refusal messages remain explicit, complete, and immutable."""

import unittest

from src.refusals import (
    BUDGET_LIMIT,
    INSUFFICIENT_EVIDENCE,
    MEDICAL_SAFETY,
    PUBLIC_REFUSAL_REASONS,
    REFUSAL_MESSAGES,
    SERVICE_UNAVAILABLE,
)


class RefusalContractTests(unittest.TestCase):
    def test_all_four_public_categories_have_the_approved_messages(self):
        self.assertEqual(
            PUBLIC_REFUSAL_REASONS,
            {
                MEDICAL_SAFETY,
                INSUFFICIENT_EVIDENCE,
                SERVICE_UNAVAILABLE,
                BUDGET_LIMIT,
            },
        )
        self.assertEqual(
            REFUSAL_MESSAGES[MEDICAL_SAFETY],
            "I can summarize doses reported in research, but I can’t recommend what you should take.",
        )
        self.assertEqual(
            REFUSAL_MESSAGES[INSUFFICIENT_EVIDENCE],
            "The retrieved abstracts don’t contain enough evidence to answer.",
        )
        self.assertEqual(
            REFUSAL_MESSAGES[SERVICE_UNAVAILABLE],
            "Answer generation failed, so retrieved evidence is shown instead.",
        )
        self.assertEqual(
            REFUSAL_MESSAGES[BUDGET_LIMIT],
            "Daily answer budget is exhausted.",
        )

    def test_public_message_mapping_is_immutable(self):
        with self.assertRaises(TypeError):
            REFUSAL_MESSAGES[MEDICAL_SAFETY] = "changed"


if __name__ == "__main__":
    unittest.main()

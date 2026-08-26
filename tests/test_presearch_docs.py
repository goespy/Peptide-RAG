"""Checks for the project's three architecture-discovery phases."""

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PreSearchDocumentationTests(unittest.TestCase):
    def test_all_sixteen_design_topics_are_documented(self):
        phases_one_two = (ROOT / "Presearch.md").read_text(encoding="utf-8")
        phase_three = (ROOT / "Post-Stack Refinement.md").read_text(encoding="utf-8")
        combined = f"{phases_one_two}\n{phase_three}"
        expected = {
            1: "Scale and load profile",
            2: "Budget and cost ceiling",
            3: "Time to ship",
            4: "Compliance and regulatory posture",
            5: "Team and skill constraints",
            6: "Hosting and deployment",
            7: "Authentication and authorization",
            8: "Database and data layer",
            9: "Backend and API architecture",
            10: "Frontend framework and rendering",
            11: "Third-party integrations",
            12: "Security vulnerabilities and controls",
            13: "File structure and project organization",
            14: "Naming conventions and code style",
            15: "Testing strategy",
            16: "Recommended tooling and developer experience",
        }
        for number, title in expected.items():
            self.assertRegex(combined, rf"(?m)^##+ {number}\. {re.escape(title)}$")

    def test_post_stack_claims_match_the_committed_tooling(self):
        phase_three = (ROOT / "Post-Stack Refinement.md").read_text(encoding="utf-8")
        self.assertIn("bm25s==0.3.9", phase_three)
        self.assertIn("No Ruff or Black configuration is currently committed", phase_three)
        self.assertNotIn("`rank_bm25` Python library", phase_three)
        self.assertNotIn("`indexer.py`", phase_three)

    def test_readme_links_every_planning_artifact(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for target in (
            "Presearch.md",
            "Post-Stack%20Refinement.md",
            "ARCHITECTURE.md",
            "Project-Master-Plan.md",
        ):
            self.assertIn(target, readme)


if __name__ == "__main__":
    unittest.main()

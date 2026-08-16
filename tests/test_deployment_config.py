import json
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DeploymentConfigTests(unittest.TestCase):
    def test_railway_config_uses_healthcheck_port_and_bounded_restart_policy(self):
        packet = json.loads((ROOT / "railway.json").read_text(encoding="utf-8"))
        self.assertEqual(packet["$schema"], "https://railway.com/railway.schema.json")
        self.assertEqual(packet["build"], {"builder": "RAILPACK"})
        deploy = packet["deploy"]
        self.assertEqual(deploy["healthcheckPath"], "/healthz")
        self.assertEqual(deploy["restartPolicyType"], "ON_FAILURE")
        self.assertEqual(deploy["restartPolicyMaxRetries"], 10)
        self.assertIn("--host 0.0.0.0", deploy["startCommand"])
        self.assertIn("--port $PORT", deploy["startCommand"])
        serialized = json.dumps(packet).casefold()
        self.assertNotIn("openrouter_api_key", serialized)
        self.assertNotIn("sk-or-", serialized)

    def test_deployment_runtime_is_python_3_11(self):
        self.assertEqual((ROOT / ".python-version").read_text(encoding="utf-8").strip(), "3.11")

    def test_environment_cannot_override_the_measured_generator_contract(self):
        example = (ROOT / ".env.example").read_text(encoding="utf-8")
        self.assertIn("OPENROUTER_API_KEY", example)
        self.assertIn("EMBEDDING_CACHE_PATH", example)
        self.assertNotIn("OPENROUTER_GENERATION_MODEL", example)
        self.assertNotIn("OPENROUTER_JUDGE_MODEL", example)

    def test_submission_architecture_asset_is_valid_and_gate_accurate(self):
        asset = ROOT / "docs/architecture-overview.svg"
        ET.parse(asset)
        svg = asset.read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        social = (ROOT / "SOCIAL-POST.md").read_text(encoding="utf-8")
        self.assertIn("docs/architecture-overview.svg", readme)
        self.assertIn("docs/architecture-overview.svg", social)
        self.assertIn("answered faithfulness .900", svg)
        self.assertIn("QA holdout remains untouched", svg)
        self.assertIn("deploy after gates", svg)
        self.assertNotIn("Sections 1–2 complete", svg)

    def test_ranked_search_screenshot_is_a_real_jpeg_submission_asset(self):
        screenshot = ROOT / "artifacts/section6/search-results.jpg"
        payload = screenshot.read_bytes()
        self.assertTrue(payload.startswith(b"\xff\xd8\xff"))
        self.assertTrue(payload.endswith(b"\xff\xd9"))
        self.assertGreater(len(payload), 10_000)
        social = (ROOT / "SOCIAL-POST.md").read_text(encoding="utf-8")
        self.assertIn("artifacts/section6/search-results.jpg", social)


if __name__ == "__main__":
    unittest.main()

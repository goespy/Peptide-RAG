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

    def test_release_architecture_asset_is_valid_and_gate_accurate(self):
        asset = ROOT / "docs/architecture-overview.svg"
        ET.parse(asset)
        svg = asset.read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        social = (ROOT / "SOCIAL-POST.md").read_text(encoding="utf-8")
        self.assertIn("docs/architecture-overview.svg", readme)
        self.assertIn("docs/architecture-overview.svg", social)
        self.assertIn("answered faithfulness .900", svg)
        self.assertIn("holdout faithfulness 1.000", svg)
        self.assertIn("5 answers · 2 refusals", svg)
        self.assertIn("live · smoke passed", svg)
        self.assertNotIn("labels pending", svg)
        self.assertNotIn("QA holdout remains untouched", svg)
        self.assertNotIn("Sections 1–2 complete", svg)

    def test_ranked_search_screenshot_is_a_real_jpeg_release_asset(self):
        screenshot = ROOT / "artifacts/section6/search-results.jpg"
        payload = screenshot.read_bytes()
        self.assertTrue(payload.startswith(b"\xff\xd8\xff"))
        self.assertTrue(payload.endswith(b"\xff\xd9"))
        self.assertGreater(len(payload), 10_000)
        social = (ROOT / "SOCIAL-POST.md").read_text(encoding="utf-8")
        self.assertIn("artifacts/section6/search-results.jpg", social)
        attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")
        self.assertIn("*.jpg binary", attributes)
        self.assertIn("*.jpeg binary", attributes)

    def test_live_release_evidence_is_machine_readable_and_secret_free(self):
        measurement = json.loads(
            (ROOT / "artifacts/section6/railway_release_measurement.json").read_text(
                encoding="utf-8"
            )
        )
        smoke = json.loads(
            (ROOT / "artifacts/section6/deployment_smoke.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(measurement["schema_version"], 1)
        self.assertEqual(measurement["service"]["deployment_status"], "SUCCESS")
        self.assertEqual(measurement["http"]["status_5xx"], 0)
        self.assertGreater(measurement["memory"]["max_mb"], 0)
        self.assertEqual(smoke["git_commit"], measurement["release"]["git_commit"])
        self.assertEqual(smoke["deployment_id"], measurement["service"]["deployment_id"])
        self.assertEqual(smoke["checks"]["search_rate_limit_http_429_probe"], 30)
        self.assertEqual(smoke["checks"]["model_originated_refusal"], "pass")
        serialized = json.dumps({"measurement": measurement, "smoke": smoke}).casefold()
        self.assertNotIn("openrouter_api_key", serialized)
        self.assertNotIn("sk-or-", serialized)


if __name__ == "__main__":
    unittest.main()

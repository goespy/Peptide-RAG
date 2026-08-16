import json
import unittest
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


if __name__ == "__main__":
    unittest.main()

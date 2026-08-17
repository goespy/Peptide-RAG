import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.project_costs import CostProjectionError, build_projection, main


class CostProjectionTests(unittest.TestCase):
    def _inputs(self):
        catalog = {
            "checked_at": "2026-08-16T18:07:13Z",
            "models": [{
                "id": "openai/gpt-oss-20b",
                "input_cost_per_million": 0.03,
                "output_cost_per_million": 0.13,
            }],
        }
        ledger = {
            "model": "openai/text-embedding-3-small",
            "pricing": {
                "input_usd_per_million_tokens": 0.02,
                "source": "https://openrouter.ai/openai/text-embedding-3-small/api",
            },
        }
        usage = {
            "model": "openai/text-embedding-3-small",
            "question_count": 13,
            "provider_usage": {"input_tokens": 180},
        }
        hashes = {
            "model_catalog_sha256": "A" * 64,
            "embedding_ledger_sha256": "B" * 64,
            "query_usage_sha256": "C" * 64,
        }
        return catalog, ledger, usage, hashes

    def test_projection_matches_documented_scenarios(self):
        report = build_projection(*self._inputs()[:3], input_hashes=self._inputs()[3])
        self.assertEqual(report["variable_ai_cost_per_user_usd_exact"], "0.003185538461538461538461538462")
        self.assertEqual(
            [row["variable_ai_cost_usd_rounded"] for row in report["scenarios"]],
            ["0.32", "3.19", "31.86", "318.55"],
        )
        self.assertEqual(
            [row["combined_lower_bound_usd"] for row in report["scenarios"]],
            ["5.32", "8.19", "36.86", "323.55"],
        )

    def test_invalid_model_or_usage_is_rejected(self):
        catalog, ledger, usage, hashes = self._inputs()
        usage["question_count"] = 0
        with self.assertRaises(CostProjectionError):
            build_projection(catalog, ledger, usage, input_hashes=hashes)
        catalog["models"] = []
        with self.assertRaises(CostProjectionError):
            build_projection(catalog, ledger, self._inputs()[2], input_hashes=hashes)

    def test_cli_writes_and_refuses_existing_before_input_reads(self):
        with TemporaryDirectory() as temp:
            directory = Path(temp)
            catalog, ledger, usage, _ = self._inputs()
            paths = []
            for name, payload in (("catalog.json", catalog), ("ledger.json", ledger), ("usage.json", usage)):
                path = directory / name
                path.write_text(json.dumps(payload), encoding="utf-8")
                paths.append(path)
            output = directory / "projection.json"
            args = [
                "--catalog", str(paths[0]),
                "--embedding-ledger", str(paths[1]),
                "--query-usage", str(paths[2]),
                "--output", str(output),
            ]
            self.assertEqual(main(args), 0)
            first = output.read_bytes()
            paths[0].unlink()
            self.assertEqual(main(args), 1)
            self.assertEqual(output.read_bytes(), first)


if __name__ == "__main__":
    unittest.main()

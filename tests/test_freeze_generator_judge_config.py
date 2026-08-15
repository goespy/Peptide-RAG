import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.test_generator_judge import JUDGE, MODEL, cases, contexts, source_grouped


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "freeze_generator_judge_config",
    ROOT / "scripts/freeze_generator_judge_config.py",
)
freeze = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(freeze)


class FreezeGeneratorJudgeConfigTests(unittest.TestCase):
    def test_invalid_cap_fails_before_reading_or_writing(self):
        with patch.object(freeze, "load_json") as load:
            self.assertEqual(freeze.main(["--hard-cost-cap-usd", "0"]), 1)
        load.assert_not_called()

    def test_freezes_exact_judge_only_contract_after_gate(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            temp = Path(directory)
            output = temp / "judge-config.json"
            judged = temp / "judged.json"
            summary = temp / "summary.json"
            inputs = [temp / f"input-{index}.json" for index in range(6)]
            generator_config = {
                "generator_candidates": [MODEL],
                "retriever_config_sha256": "R" * 64,
            }
            loaded = [
                {"qa": True},
                generator_config,
                {"contexts": True},
                {"catalog": True},
                {"outputs": True},
                {"summary": True},
            ]
            estimate = {
                "estimated_max_cost_usd": 0.20,
                "judge_calls": 13,
                "generator_calls": 0,
            }
            with (
                patch.object(freeze, "load_json", side_effect=loaded),
                patch.object(freeze, "hash_file", return_value="A" * 64),
                patch.object(freeze, "validate_model_catalog"),
                patch.object(freeze, "validate_judge_catalog", return_value=JUDGE),
                patch.object(freeze, "validate_qa", return_value=cases()),
                patch.object(freeze, "validate_config"),
                patch.object(freeze, "contexts_from", return_value=contexts()),
                patch.object(freeze, "offline_rows", return_value=source_grouped()),
                patch.object(freeze, "validate_generator_gate") as gate,
                patch.object(freeze, "estimate_judge_cost", return_value=estimate),
            ):
                result = freeze.main(
                    [
                        "--qa", str(inputs[0]),
                        "--generator-config", str(inputs[1]),
                        "--contexts", str(inputs[2]),
                        "--model-catalog", str(inputs[3]),
                        "--generator-outputs", str(inputs[4]),
                        "--generator-summary", str(inputs[5]),
                        "--output", str(output),
                        "--judged-outputs", str(judged),
                        "--judge-summary", str(summary),
                        "--hard-cost-cap-usd", "0.25",
                    ]
                )
            self.assertEqual(result, 0)
            gate.assert_called_once()
            packet = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(packet["generator_calls"], 0)
            self.assertEqual(packet["judge_calls"], 13)
            self.assertEqual(packet["judge"]["model"], JUDGE)
            self.assertEqual(packet["judge"]["hard_cost_cap_usd"], 0.25)
            self.assertEqual(packet["holdout_status"], "untouched")
            self.assertEqual(packet["artifact_paths"]["outputs"], judged.relative_to(ROOT).as_posix())


if __name__ == "__main__":
    unittest.main()

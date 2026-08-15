import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "refresh_model_catalog", ROOT / "scripts/refresh_model_catalog.py"
)
catalog = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(catalog)


def raw(model_id):
    return {
        "id": model_id,
        "context_length": 131_072,
        "pricing": {"prompt": "0.00000003", "completion": "0.00000013"},
        "supported_parameters": [
            "temperature",
            "max_tokens",
            "response_format",
            "structured_outputs",
        ],
    }


class ModelCatalogTests(unittest.TestCase):
    def test_fetch_requires_every_exact_structured_model(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "data": [raw(model) for _family, model in (*catalog.MODELS, catalog.JUDGE)]
        }
        session = Mock()
        session.get.return_value = response
        packet = catalog.fetch_catalog(session)
        self.assertEqual([row["id"] for row in packet["models"]], [row[1] for row in catalog.MODELS])
        self.assertEqual(packet["models"][0]["input_cost_per_million"], 0.03)
        self.assertEqual(packet["judge"]["id"], catalog.JUDGE[1])
        session.get.assert_called_once_with(catalog.MODELS_URL, timeout=30.0)

    def test_missing_parameter_or_model_fails(self):
        values = [raw(model) for _family, model in (*catalog.MODELS, catalog.JUDGE)]
        values[0]["supported_parameters"].remove("structured_outputs")
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"data": values}
        session = Mock()
        session.get.return_value = response
        with self.assertRaises(catalog.ModelCatalogError):
            catalog.fetch_catalog(session)

    def test_incompatible_preferred_uses_cheapest_bounded_family_replacement(self):
        values = [raw(model) for _family, model in (*catalog.MODELS, catalog.JUDGE)]
        values[0]["supported_parameters"].remove("structured_outputs")
        expensive = raw("qwen/expensive")
        expensive["pricing"] = {"prompt": "0.00000005", "completion": "0.0000002"}
        cheapest = raw("qwen/cheapest")
        cheapest["pricing"] = {"prompt": "0.00000002", "completion": "0.0000001"}
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"data": values + [expensive, cheapest]}
        session = Mock()
        session.get.return_value = response
        packet = catalog.fetch_catalog(session)
        self.assertEqual(packet["models"][0]["id"], "qwen/cheapest")
        self.assertEqual(packet["models"][0]["replacement_for"], catalog.MODELS[0][1])

    def test_atomic_writer_refuses_existing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.json"
            catalog.write_atomic(path, {"a": 1}, overwrite=False)
            with self.assertRaises(catalog.ModelCatalogError):
                catalog.write_atomic(path, {"a": 2}, overwrite=False)


if __name__ == "__main__":
    unittest.main()

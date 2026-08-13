"""Local service contracts: lexical search works offline and RAG is opt-in."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from src.generation import insufficient_evidence
from src.service import LocalResearchService, _load_lexical_metrics, load_semantic_retriever


class ServiceTests(unittest.TestCase):
    def _corpus(self, directory: Path) -> Path:
        path = directory / "corpus.jsonl"
        path.write_text(
            '{"id":"1","title":"Alpha peptide","text":"Alpha supports repair."}\n'
            '{"id":"2","title":"Beta peptide","text":"Beta has a distinct mechanism."}\n',
            encoding="utf-8",
        )
        return path

    def _lexical_config(self, directory: Path, corpus: Path) -> Path:
        import hashlib
        config = directory / "lexical.json"
        config.write_text(json.dumps({
            "corpus_sha256": hashlib.sha256(corpus.read_bytes()).hexdigest().upper(),
            "analysis": {"name": "baseline"},
            "bm25": {"k1": 0.8, "b": 0.75, "proximity_boost": 0.0},
        }), encoding="utf-8")
        return config

    def test_boolean_and_bm25_search_are_local_and_deterministic(self):
        with TemporaryDirectory() as temp:
            corpus = self._corpus(Path(temp))
            service = LocalResearchService(corpus_path=corpus, lexical_config_path=self._lexical_config(Path(temp), corpus))
            self.assertEqual([item["pmid"] for item in service.search("alpha AND repair", "boolean", 5)], ["1"])
            self.assertEqual(service.search("alpha", "bm25", 1)[0]["pmid"], "1")
            self.assertEqual(service.search("alpha", "semantic", 1), [])
            self.assertFalse(service.metrics()["semantic_available"])

    def test_invalid_frozen_assets_do_not_enable_semantic_search(self):
        with TemporaryDirectory() as temp:
            directory = Path(temp)
            corpus = self._corpus(directory)
            frozen = directory / "frozen_config.json"
            frozen.write_text(json.dumps({"schema_version": 1, "corpus_sha256": "wrong"}), encoding="utf-8")
            self.assertIsNone(load_semantic_retriever(corpus, frozen, directory / "cache.npz", lexical_config_sha256="hash"))

    def test_metrics_require_matching_frozen_provenance(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "evaluation.json"
            path.write_text(json.dumps({
                "metadata": {"corpus_sha256": "CORPUS", "lexical_config_sha256": "CONFIG"},
                "full_descriptive": {"aggregate": {
                    "query_count": 15, "mrr": 0.9,
                    "recall_at": {"10": 0.8}, "ndcg_at": {"10": 0.7},
                }},
                "holdout": {"tuned": {"aggregate": {
                    "query_count": 5, "mrr": 0.8,
                    "recall_at": {"10": 0.75}, "ndcg_at": {"10": 0.65},
                }}},
            }), encoding="utf-8")
            measured = _load_lexical_metrics(path, corpus_sha256="CORPUS", lexical_config_sha256="CONFIG")
            self.assertEqual(measured["all_queries"]["query_count"], 15)
            self.assertEqual(measured["untouched_holdout"]["ndcg_at_10"], 0.65)
            self.assertIsNone(_load_lexical_metrics(path, corpus_sha256="WRONG", lexical_config_sha256="CONFIG"))

    def test_lexical_answer_fails_closed_but_keeps_local_evidence(self):
        class RefusingClient:
            def __init__(self):
                self.contexts = ()

            def answer(self, query, contexts):
                self.contexts = tuple(contexts)
                return insufficient_evidence()

        with TemporaryDirectory() as temp:
            client = RefusingClient()
            corpus = self._corpus(Path(temp))
            service = LocalResearchService(corpus_path=corpus, lexical_config_path=self._lexical_config(Path(temp), corpus), answer_client=client)
            evidence = service.search("alpha", "lexical", 1)
            response = service.answer("What supports repair?", "lexical", 1, evidence)
            self.assertEqual(evidence[0]["pmid"], "1")
            self.assertEqual(client.contexts, ())
            self.assertIsNone(response["answer"])
            self.assertEqual(response["citations"], [])

"""Local service contracts: lexical search works offline and RAG is opt-in."""

import json
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import numpy as np

from src.chunks import Chunk, embedding_text
from src.embeddings import EmbeddingCacheManifest, save_embedding_cache
from src.generation import insufficient_evidence
from src.retrieval import RetrievedChunk
from src.service import (
    LocalResearchService,
    _load_lexical_metrics,
    load_release_answer_client,
    load_semantic_retriever,
)


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

    def test_semantic_cache_model_must_match_frozen_selection(self):
        with TemporaryDirectory() as temp:
            directory = Path(temp)
            corpus = self._corpus(directory)
            corpus_hash = hashlib.sha256(corpus.read_bytes()).hexdigest().upper()
            chunks_path = directory / "chunks_128_32.jsonl"
            chunk = Chunk("1:c0001", "1", "Alpha peptide", "Alpha supports repair.", 0, 22, 3)
            chunks_path.write_text(json.dumps(chunk.__dict__) + "\n", encoding="utf-8")
            chunk_hash = hashlib.sha256(chunks_path.read_bytes()).hexdigest().upper()
            chunks_path.with_suffix(".jsonl.manifest.json").write_text(json.dumps({
                "schema_version": 1, "corpus_sha256": corpus_hash,
                "chunk_sha256": chunk_hash, "chunk_count": 1,
            }), encoding="utf-8")
            frozen = directory / "frozen_config.json"
            frozen.write_text(json.dumps({
                "schema_version": 1, "corpus_sha256": corpus_hash,
                "lexical_config_sha256": "LEXICAL", "chunk_config": {"words": 128, "overlap": 32},
                "embedding_model": "expected/model", "rrf_alpha": 0.5,
            }), encoding="utf-8")
            cache = directory / "cache.npz"
            manifest = EmbeddingCacheManifest.create(
                model="different/model", dimension=2, corpus_hash=corpus_hash,
                chunk_hash=chunk_hash, inputs=[embedding_text(chunk)], chunk_ids=[chunk.chunk_id],
            )
            save_embedding_cache(cache, np.array([[1.0, 0.0]]), manifest)
            self.assertIsNone(load_semantic_retriever(corpus, frozen, cache, lexical_config_sha256="LEXICAL"))

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

    def test_release_generator_uses_exact_accepted_prompt_and_settings(self):
        with TemporaryDirectory() as temp:
            directory = Path(temp)
            frozen = directory / "frozen.json"
            source = directory / "generator_v2_5.json"
            accepted = directory / "accepted.json"
            final = directory / "generator.json"
            holdout_summary = directory / "holdout_summary.json"
            holdout_outputs = directory / "holdout_outputs.json"
            holdout_contexts = directory / "holdout_contexts.json"
            frozen.write_text("{}", encoding="utf-8")
            prompt = "Use only measured evidence."
            generation = {
                "citation_mode": "derived_from_text_markers",
                "exclude_reasoning": True,
                "max_tokens": 800,
                "reasoning_effort": "low",
                "reconsider_insufficient_evidence": True,
                "repair_attempts": 1,
                "require_supported_parameters": True,
                "temperature": 0,
            }
            source_payload = {
                "generator_candidates": ["openai/gpt-oss-20b"],
                "generation": generation,
                "holdout_status": "untouched",
                "prompt": prompt,
                "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest().upper(),
            }
            source.write_text(json.dumps(source_payload), encoding="utf-8")
            accepted.write_text(json.dumps({
                "status": "accepted_for_holdout",
                "holdout_status": "untouched",
                "winner": "openai/gpt-oss-20b",
                "retriever_config_sha256": hashlib.sha256(frozen.read_bytes()).hexdigest().upper(),
                "generator_config_sha256": hashlib.sha256(source.read_bytes()).hexdigest().upper(),
                "generation": {**generation, "prompt": prompt},
            }), encoding="utf-8")
            accepted_hash = hashlib.sha256(accepted.read_bytes()).hexdigest().upper()
            frozen_hash = hashlib.sha256(frozen.read_bytes()).hexdigest().upper()
            qa_hash = "A" * 64
            holdout_contexts.write_text(json.dumps({
                "retriever_config_sha256": frozen_hash,
                "accepted_selection_sha256": accepted_hash,
                "qa_sha256": qa_hash,
                "contexts": [{"qa_id": f"qa{index}"} for index in range(7)],
            }), encoding="utf-8")
            contexts_hash = hashlib.sha256(holdout_contexts.read_bytes()).hexdigest().upper()
            holdout_outputs.write_text(json.dumps({
                "selection_sha256": accepted_hash,
                "retriever_config_sha256": frozen_hash,
                "contexts_sha256": contexts_hash,
                "qa_sha256": qa_hash,
                "outputs": [{"qa_id": f"qa{index}"} for index in range(7)],
            }), encoding="utf-8")
            outputs_hash = hashlib.sha256(holdout_outputs.read_bytes()).hexdigest().upper()
            metrics = {"answerable_answer_rate": 1.0}
            holdout_summary.write_text(json.dumps({
                "schema_version": 2,
                "passes": True,
                "winner": "openai/gpt-oss-20b",
                "accepted_selection_sha256": accepted_hash,
                "retriever_config_sha256": frozen_hash,
                "qa_sha256": qa_hash,
                "contexts_sha256": contexts_hash,
                "outputs_sha256": outputs_hash,
                "metrics": metrics,
            }), encoding="utf-8")
            final.write_text(json.dumps({
                "schema_version": 2,
                "status": "frozen_after_passing_holdout",
                "winner": "openai/gpt-oss-20b",
                "retriever_config_sha256": frozen_hash,
                "accepted_selection_sha256": accepted_hash,
                "qa_sha256": qa_hash,
                "holdout_contexts_sha256": contexts_hash,
                "holdout_outputs_sha256": outputs_hash,
                "holdout_summary_sha256": hashlib.sha256(holdout_summary.read_bytes()).hexdigest().upper(),
                "holdout_metrics": metrics,
            }), encoding="utf-8")
            paths = (
                final,
                accepted,
                source,
                frozen,
                holdout_summary,
                holdout_outputs,
                holdout_contexts,
            )
            client = load_release_answer_client(*paths)
            self.assertIsNotNone(client)
            self.assertEqual(client.system_prompt, prompt)
            self.assertEqual(client.max_tokens, 800)
            self.assertEqual(client.reasoning_effort, "low")
            self.assertTrue(client.exclude_reasoning)
            self.assertTrue(client.reconsider_insufficient_evidence)

            tampered_source = dict(source_payload)
            tampered_source["prompt"] = "tampered"
            source.write_text(json.dumps(tampered_source), encoding="utf-8")
            self.assertIsNone(load_release_answer_client(*paths))
            source.write_text(json.dumps(source_payload), encoding="utf-8")
            final_payload = json.loads(final.read_text(encoding="utf-8"))
            missing_qa = dict(final_payload)
            missing_qa.pop("qa_sha256")
            final.write_text(json.dumps(missing_qa), encoding="utf-8")
            self.assertIsNone(load_release_answer_client(*paths))
            final.write_text(json.dumps(final_payload), encoding="utf-8")
            summary_payload = json.loads(holdout_summary.read_text(encoding="utf-8"))
            summary_payload["passes"] = False
            holdout_summary.write_text(json.dumps(summary_payload), encoding="utf-8")
            self.assertIsNone(load_release_answer_client(*paths))

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
            self.assertEqual(response["refusal_source"], "failed_closed")

    def test_refusal_source_distinguishes_model_result_from_fail_close(self):
        class RefusingClient:
            def __init__(self, final_outcome):
                self.last_metadata = {"final_outcome": final_outcome}

            def answer(self, query, contexts):
                return insufficient_evidence()

        with TemporaryDirectory() as temp:
            directory = Path(temp)
            corpus = self._corpus(directory)
            config = self._lexical_config(directory, corpus)
            for outcome, expected in (
                ("model_insufficient_evidence", "model"),
                ("model_insufficient_evidence_after_reconsideration", "model"),
                ("model_insufficient_evidence_after_repair", "model"),
                ("failed_closed_after_repair", "failed_closed"),
                ("preflight_insufficient_evidence", "failed_closed"),
                (None, "failed_closed"),
            ):
                with self.subTest(outcome=outcome):
                    client = RefusingClient(outcome)
                    service = LocalResearchService(
                        corpus_path=corpus,
                        lexical_config_path=config,
                        answer_client=client,
                    )
                    response = service.answer("Question?", "lexical", 1, [])
                    self.assertEqual(response["refusal_source"], expected)

    def test_answer_reuses_canonical_displayed_chunks_without_second_retrieval(self):
        class RecordingClient:
            def __init__(self): self.contexts = ()
            def answer(self, query, contexts):
                self.contexts = tuple(contexts); return insufficient_evidence()
        class StoredRetriever:
            def __init__(self, chunks): self.chunks = chunks

        with TemporaryDirectory() as temp:
            client = RecordingClient(); corpus = self._corpus(Path(temp))
            service = LocalResearchService(corpus_path=corpus, lexical_config_path=self._lexical_config(Path(temp), corpus), answer_client=client)
            chunk = Chunk("1:c0001", "1", "Alpha peptide", "Alpha supports repair.", 0, 22, 3)
            service.semantic_retriever = StoredRetriever((chunk,))
            displayed = service._chunk_record(RetrievedChunk(chunk, 1.0, "hybrid", 1, 1))
            service.answer("What supports repair?", "hybrid", 1, [displayed])
            self.assertEqual(tuple(item.chunk_id for item in client.contexts), ("1:c0001",))

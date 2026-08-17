from __future__ import annotations
import hashlib, json, tempfile, unittest
from pathlib import Path
import numpy as np
from scripts.evaluate_chunks import ChunkEvaluationError, _cache_for, evaluate_candidates, load_approved_qa, query_embeddings, select_alpha, select_chunk_config
from src.embeddings import EmbeddingCacheManifest, save_embedding_cache
from src.chunks import Chunk

class FakeEmbeddingClient:
    def __init__(self):
        self.calls = 0
        self.total_metadata = {"provider":"fake", "provider_calls":0, "input_tokens":0, "cost_usd":0.0}
    def embed(self, inputs, *, batch_size=100):
        self.calls += 1
        self.total_metadata = {"provider":"fake", "provider_calls":1, "input_tokens":len(inputs), "cost_usd":0.001}
        return np.array([[float(i + 1), 1.0] for i in range(len(inputs))])

def case(i: int) -> dict:
    return {"id":f"qa{i:02d}","split":"development","answerable":True,"question":"alpha","supporting_spans":[{"pmid":"1","start_char":0,"end_char":5}]}

class EvaluationTests(unittest.TestCase):
    def test_requires_approved_and_exact_corpus(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); corpus=root/"c.jsonl"; corpus.write_text('{"id":"1","title":"t","text":"alpha"}\n'); qa=root/"qa.json"; qa.write_text(json.dumps({"status":"candidate","corpus_sha256":"x","cases":[]}))
            with self.assertRaises(ChunkEvaluationError): load_approved_qa(qa, corpus)
    def test_evaluates_development_only_and_selects_deterministically(self):
        chunks=(Chunk("1:c0001","1","alpha","alpha",0,5,1), Chunk("2:c0001","2","other","other",0,5,1))
        qa={"status":"approved","questions":[case(i) for i in range(1,11)]+[{"id":f"qa{i:02d}","split":"holdout","answerable":True} for i in range(11,16)]+[{"id":f"qa{i:02d}","split":"development" if i<=18 else "holdout","answerable":False} for i in range(16,21)]}
        report=evaluate_candidates(qa, [("small",chunks,np.array([[1.,0.],[0.,1.]]),{"words":128})], lambda q:np.array([1.,0.]))
        self.assertEqual(report["case_ids"], [f"qa{i:02d}" for i in range(1,11)])
        self.assertEqual(report["selected_chunk_config"], "small"); self.assertEqual(report["selected_alpha"], .5)
    def test_selection_prefers_minimum_then_context_and_alpha_half(self):
        def result(name,l,s,t): return {"name":name,"average_context_tokens":t,"evaluation":{"modes":{"lexical":{"@5":{"recall":l}},"semantic":{"@5":{"recall":s}}}}}
        self.assertEqual(select_chunk_config([result("a",.8,.4,1),result("b",.5,.5,100)])["name"],"b")
        self.assertEqual(select_chunk_config([result("z",.5,.5,10),result("a",.5,.5,10)])["name"],"a")
        items=[{"alpha":.25,"evaluation":{"modes":{"hybrid":{"@5":{"recall":.5,"evidence_hit":.5}}}}},{"alpha":.5,"evaluation":{"modes":{"hybrid":{"@5":{"recall":.5,"evidence_hit":.5}}}}}]
        self.assertEqual(select_alpha(items)["alpha"],.5)
    def test_missing_containing_chunk_scores_zero_instead_of_aborting(self):
        chunks=(Chunk("1:c0001","1","alpha","alpha",0,5,1),)
        qa={"status":"approved","questions":[
            *[{**case(i),"supporting_spans":[{"pmid":"1","start_char":6,"end_char":10}]} for i in range(1,11)],
            *[{"id":f"qa{i:02d}","split":"holdout","answerable":True} for i in range(11,16)],
            *[{"id":f"qa{i:02d}","split":"development" if i<=18 else "holdout","answerable":False} for i in range(16,21)],
        ]}
        report=evaluate_candidates(qa, [("small",chunks,np.array([[1.,0.]]),{"words":128})], lambda q:np.array([1.,0.]))
        self.assertEqual(report["chunk_configurations"][0]["evaluation"]["modes"]["semantic"]["@5"]["recall"],0.0)
    def test_corpus_cache_requires_independently_expected_model(self):
        chunks=(Chunk("1:c0001","1","title","alpha",0,5,1),)
        with tempfile.TemporaryDirectory() as td:
            cache=Path(td)/"cache.npz"
            manifest=EmbeddingCacheManifest.create(model="wrong-model",dimension=2,corpus_hash="corpus",chunk_hash="chunks",inputs=["title\n\nalpha"],chunk_ids=["1:c0001"])
            save_embedding_cache(cache,np.array([[1.,0.]]),manifest)
            with self.assertRaises(ChunkEvaluationError):
                _cache_for(chunks,{"corpus_sha256":"corpus","chunk_sha256":"chunks"},cache,"expected-model")
    def test_query_embeddings_are_frozen_and_reused_without_provider_call(self):
        qa={"questions":[
            *[{"id":f"qa{i:02d}","split":"development","question":f"question {i}"} for i in range(1,14)],
            *[{"id":f"qa{i:02d}","split":"holdout","question":f"question {i}"} for i in range(14,21)],
        ]}
        with tempfile.TemporaryDirectory() as td:
            cache=Path(td)/"queries.npz"; first=FakeEmbeddingClient()
            vectors, usage=query_embeddings(qa, cache_path=cache, model="model", corpus_hash="corpus", qa_hash="qa", client=first)
            self.assertEqual(first.calls,1); self.assertEqual(len(vectors),13); self.assertEqual(usage["source"],"frozen_query_cache")
            second=FakeEmbeddingClient()
            cached, cached_usage=query_embeddings(qa, cache_path=cache, model="model", corpus_hash="corpus", qa_hash="qa", client=second)
            self.assertEqual(second.calls,0); self.assertEqual(cached_usage,usage)
            np.testing.assert_allclose(cached["question 1"], vectors["question 1"])
    def test_query_cache_rejects_changed_question_without_overwrite(self):
        qa={"questions":[
            *[{"id":f"qa{i:02d}","split":"development","question":f"question {i}"} for i in range(1,14)],
            *[{"id":f"qa{i:02d}","split":"holdout","question":f"question {i}"} for i in range(14,21)],
        ]}
        with tempfile.TemporaryDirectory() as td:
            cache=Path(td)/"queries.npz"
            query_embeddings(qa, cache_path=cache, model="model", corpus_hash="corpus", qa_hash="qa", client=FakeEmbeddingClient())
            qa["questions"][0]["question"]="changed"
            with self.assertRaises(ChunkEvaluationError):
                query_embeddings(qa, cache_path=cache, model="model", corpus_hash="corpus", qa_hash="qa", client=FakeEmbeddingClient())

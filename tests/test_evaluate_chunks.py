from __future__ import annotations
import hashlib, json, tempfile, unittest
from pathlib import Path
import numpy as np
from scripts.evaluate_chunks import ChunkEvaluationError, evaluate_candidates, load_approved_qa, select_alpha, select_chunk_config
from src.chunks import Chunk

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

from __future__ import annotations
import hashlib, json, tempfile, unittest
from pathlib import Path
import numpy as np
from scripts.embed_chunks import ChunkEmbeddingError, build_embedding_cache, load_chunk_artifact

class FakeClient:
    model="fake/model"
    def __init__(self): self.inputs=None
    def embed(self, inputs, *, batch_size=100): self.inputs=tuple(inputs); return np.array([[3.,4.],[0.,2.]])

class EmbedChunksTests(unittest.TestCase):
    def artifact(self, root: Path):
        chunks=root/"chunks.jsonl"; lines=[{"chunk_id":"1:c0001","pmid":"1","title":"Title","text":"one two","start_char":0,"end_char":7,"token_count":2},{"chunk_id":"2:c0001","pmid":"2","title":"Other","text":"three","start_char":0,"end_char":5,"token_count":1}]
        chunks.write_text("".join(json.dumps(x)+"\n" for x in lines)); manifest=root/"chunks.manifest.json"; manifest.write_text(json.dumps({"schema_version":1,"corpus_sha256":"C","chunk_sha256":hashlib.sha256(chunks.read_bytes()).hexdigest().upper(),"chunk_count":2,"config":{"words":128,"overlap":32}})); return chunks,manifest
    def test_validates_and_writes_cache(self):
        with tempfile.TemporaryDirectory() as td:
            chunks, manifest=self.artifact(Path(td)); output=Path(td)/"v.npz"; client=FakeClient()
            result,count,words=build_embedding_cache(chunks,manifest,output,client=client)
            self.assertEqual((count,words,result.dimension), (2,5,2)); self.assertEqual(client.inputs, ("Title\n\none two","Other\n\nthree")); self.assertTrue(output.exists())
    def test_refuses_existing_before_client_call_and_bad_hash(self):
        with tempfile.TemporaryDirectory() as td:
            chunks,manifest=self.artifact(Path(td)); out=Path(td)/"v.npz"; out.write_bytes(b"old"); client=FakeClient()
            with self.assertRaises(ChunkEmbeddingError): build_embedding_cache(chunks,manifest,out,client=client)
            self.assertIsNone(client.inputs)
            out.unlink(); data=json.loads(manifest.read_text()); data["chunk_sha256"]="bad"; manifest.write_text(json.dumps(data))
            with self.assertRaises(ChunkEmbeddingError): build_embedding_cache(chunks,manifest,out,client=client)

    def test_loader_rejects_out_of_order_chunk_ordinals(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            chunks = root / "chunks.jsonl"
            chunks.write_text(
                json.dumps({"chunk_id":"1:c0002","pmid":"1","title":"t","text":"alpha","start_char":0,"end_char":5,"token_count":1}) + "\n",
                encoding="utf-8",
            )
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({
                "schema_version": 1,
                "corpus_sha256": "C",
                "chunk_sha256": hashlib.sha256(chunks.read_bytes()).hexdigest().upper(),
                "chunk_count": 1,
            }), encoding="utf-8")
            with self.assertRaises(ChunkEmbeddingError):
                load_chunk_artifact(chunks, manifest)

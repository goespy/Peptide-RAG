import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np

from src.embeddings import (
    EmbeddingCacheManifest,
    EmbeddingClient,
    load_embedding_cache,
    save_embedding_cache,
)


class EmbeddingClientTests(unittest.TestCase):
    def test_empty_input_never_calls_http(self):
        session = Mock()
        client = EmbeddingClient(api_key="key", session=session)
        result = client.embed([])
        self.assertEqual(result.shape, (0, 0))
        session.post.assert_not_called()

    def test_batches_and_normalizes_response(self):
        first, second = Mock(), Mock()
        first.status_code, second.status_code = 200, 200
        first.json.return_value = {"data": [{"index": 1, "embedding": [0, 2]}, {"index": 0, "embedding": [3, 0]}]}
        second.json.return_value = {"data": [{"index": 0, "embedding": [1, 1]}]}
        session = Mock()
        session.post.side_effect = [first, second]
        actual = EmbeddingClient(api_key="key", session=session).embed(["a", "b", "c"], batch_size=2)
        self.assertEqual(session.post.call_count, 2)
        np.testing.assert_allclose(actual, [[1, 0], [0, 1], [2 ** -0.5, 2 ** -0.5]])

    @patch("src.embeddings.time.sleep")
    def test_honors_retry_after(self, sleep):
        retry, success = Mock(), Mock()
        retry.status_code, retry.headers = 429, {"Retry-After": "3"}
        success.status_code, success.headers = 200, {}
        success.json.return_value = {"data": [{"index": 0, "embedding": [1, 0]}]}
        session = Mock()
        session.post.side_effect = [retry, success]
        EmbeddingClient(api_key="key", session=session, retries=1).embed(["a"])
        sleep.assert_called_once_with(3.0)


class CacheTests(unittest.TestCase):
    def test_load_rejects_changed_input_and_accepts_created_time_difference(self):
        manifest = EmbeddingCacheManifest.create(model="model", dimension=2, corpus_hash="corpus", chunk_hash="chunks", inputs=["one"], chunk_ids=["1:c0001"])
        later = EmbeddingCacheManifest.create(model="model", dimension=2, corpus_hash="corpus", chunk_hash="chunks", inputs=["one"], chunk_ids=["1:c0001"])
        changed = EmbeddingCacheManifest.create(model="model", dimension=2, corpus_hash="corpus", chunk_hash="chunks", inputs=["two"], chunk_ids=["1:c0001"])
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / "vectors.npz"
            save_embedding_cache(cache, np.array([[2.0, 0.0]]), manifest)
            np.testing.assert_allclose(load_embedding_cache(cache, later), [[1.0, 0.0]])
            self.assertIsNone(load_embedding_cache(cache, changed))

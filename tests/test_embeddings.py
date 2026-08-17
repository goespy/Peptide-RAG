from concurrent.futures import ThreadPoolExecutor
import tempfile
import threading
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
    def test_concurrent_embeddings_keep_metadata_local_and_total_locked(self):
        barrier = threading.Barrier(2)

        class QuerySession:
            def post(self, _url, *, json, **_kwargs):
                tokens = 10 if json["input"] == ["first"] else 20
                value = Mock(status_code=200, headers={})
                value.json.return_value = {
                    "data": [{"index": 0, "embedding": [1.0, float(tokens)]}],
                    "usage": {"prompt_tokens": tokens, "cost": tokens / 1_000_000},
                }
                return value

        client = EmbeddingClient(api_key="key", session=QuerySession())

        def run(value):
            client.embed([value])
            barrier.wait(timeout=2)
            return dict(client.last_metadata)

        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(run, "first")
            second = pool.submit(run, "second")
            first_metadata = first.result(timeout=3)
            second_metadata = second.result(timeout=3)
        self.assertEqual(first_metadata["input_tokens"], 10)
        self.assertEqual(second_metadata["input_tokens"], 20)
        self.assertEqual(client.total_metadata["provider_calls"], 2)
        self.assertEqual(client.total_metadata["input_tokens"], 30)

    def test_production_embedding_sessions_are_thread_local_and_concurrent(self):
        barrier = threading.Barrier(2)
        created = []

        class ConcurrentSession:
            def post(self, _url, **_kwargs):
                barrier.wait(timeout=2)
                value = Mock(status_code=200, headers={})
                value.json.return_value = {
                    "data": [{"index": 0, "embedding": [1.0, 1.0]}],
                    "usage": {"prompt_tokens": 1, "cost": 0.0},
                }
                return value

        def create_session():
            session = ConcurrentSession()
            created.append(session)
            return session

        with patch("src.embeddings.requests.Session", side_effect=create_session):
            client = EmbeddingClient(api_key="key")
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(client.embed, [value]) for value in ("a", "b")]
                [future.result(timeout=3) for future in futures]
        self.assertEqual(len(created), 2)
        self.assertEqual(client.total_metadata["provider_calls"], 2)

    def test_empty_input_never_calls_http(self):
        session = Mock()
        client = EmbeddingClient(api_key="key", session=session)
        result = client.embed([])
        self.assertEqual(result.shape, (0, 0))
        session.post.assert_not_called()

    def test_failed_provider_attempt_is_counted_with_unknown_usage(self):
        session = Mock()
        session.post.side_effect = ValueError("malformed response")
        client = EmbeddingClient(api_key="key", session=session, retries=0)
        with self.assertRaises(RuntimeError):
            client.embed(["query"])
        self.assertEqual(client.last_metadata["provider_calls"], 1)
        self.assertIsNone(client.last_metadata["input_tokens"])
        self.assertIsNone(client.last_metadata["cost_usd"])
        self.assertEqual(client.total_metadata["provider_calls"], 1)
        self.assertIsNone(client.total_metadata["input_tokens"])
        self.assertIsNone(client.total_metadata["cost_usd"])

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

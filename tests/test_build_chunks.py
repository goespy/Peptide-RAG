from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts.build_chunks import ChunkBuildError, build_chunks, main, write_artifacts
from src.chunks import ChunkConfig


class BuildChunksTests(unittest.TestCase):
    def _corpus(self, directory: Path) -> tuple[Path, str]:
        corpus = directory / "corpus.jsonl"
        corpus.write_text('{"id":"2","title":"B","text":"one two three"}\n{"id":"1","title":"A","text":""}\n', encoding="utf-8")
        return corpus, hashlib.sha256(corpus.read_bytes()).hexdigest().upper()

    def test_build_hash_and_manifest_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            corpus, digest = self._corpus(directory)
            chunks, actual = build_chunks(corpus, ChunkConfig(2, 1), digest)
            output, manifest = directory / "chunks.jsonl", directory / "manifest.json"
            report = write_artifacts(chunks, actual, ChunkConfig(2, 1), output, manifest)
            self.assertEqual(actual, digest)
            self.assertEqual(report["chunk_sha256"], hashlib.sha256(output.read_bytes()).hexdigest().upper())
            self.assertEqual(json.loads(manifest.read_text(encoding="utf-8"))["config"], {"words": 2, "overlap": 1})

    def test_rejects_wrong_hash_and_overwrite_without_changing_existing_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            corpus, digest = self._corpus(directory)
            with self.assertRaises(ChunkBuildError):
                build_chunks(corpus, ChunkConfig(2, 1), "0" * 64)
            chunks, actual = build_chunks(corpus, ChunkConfig(2, 1), digest)
            output, manifest = directory / "chunks.jsonl", directory / "manifest.json"
            output.write_text("original\n", encoding="utf-8")
            with self.assertRaises(ChunkBuildError):
                write_artifacts(chunks, actual, ChunkConfig(2, 1), output, manifest)
            self.assertEqual(output.read_text(encoding="utf-8"), "original\n")

    def test_cli_writes_and_refuses_second_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            corpus, digest = self._corpus(directory)
            output = directory / "chunks.jsonl"
            arguments = ["--corpus", str(corpus), "--output", str(output), "--words", "128", "--overlap", "32", "--corpus-sha256", digest]
            self.assertEqual(main(arguments), 0)
            self.assertEqual(main(arguments), 1)


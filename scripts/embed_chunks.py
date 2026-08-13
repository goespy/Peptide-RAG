#!/usr/bin/env python3
"""Create a validated, atomic embedding cache for a chunk artifact."""
from __future__ import annotations

import argparse, hashlib, json, sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, Sequence
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from src.chunks import Chunk, embedding_text
from src.embeddings import DEFAULT_EMBEDDING_MODEL, EmbeddingCacheManifest, EmbeddingClient, save_embedding_cache

class ChunkEmbeddingError(RuntimeError): pass
def sha256(path: Path) -> str: return hashlib.sha256(Path(path).read_bytes()).hexdigest().upper()

def load_chunk_artifact(chunks_path: Path, manifest_path: Path) -> tuple[tuple[Chunk, ...], dict[str, Any]]:
    try: manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc: raise ChunkEmbeddingError(f"cannot read manifest: {exc}") from exc
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1 or not isinstance(manifest.get("corpus_sha256"), str) or manifest.get("chunk_sha256") != sha256(chunks_path): raise ChunkEmbeddingError("chunk manifest does not bind this chunk artifact")
    chunks: list[Chunk] = []
    try: lines = Path(chunks_path).read_text(encoding="utf-8").splitlines()
    except OSError as exc: raise ChunkEmbeddingError(f"cannot read chunks: {exc}") from exc
    required = {"chunk_id", "pmid", "title", "text", "start_char", "end_char", "token_count"}
    expected_ordinal: dict[str, int] = {}
    previous_pmid: int | None = None
    for number, line in enumerate(lines, 1):
        try: item = json.loads(line)
        except json.JSONDecodeError as exc: raise ChunkEmbeddingError(f"invalid chunk JSON line {number}") from exc
        if not isinstance(item, dict) or set(item) != required: raise ChunkEmbeddingError(f"invalid chunk schema at line {number}")
        try: chunk = Chunk(**item)
        except TypeError as exc: raise ChunkEmbeddingError(f"invalid chunk fields at line {number}") from exc
        if (
            not all(isinstance(getattr(chunk, name), str) for name in ("chunk_id", "pmid", "title", "text"))
            or not chunk.pmid.isdecimal()
            or not all(
                isinstance(getattr(chunk, name), int) and not isinstance(getattr(chunk, name), bool)
                for name in ("start_char", "end_char", "token_count")
            )
        ):
            raise ChunkEmbeddingError(f"invalid chunk values at line {number}")
        numeric_pmid = int(chunk.pmid)
        if previous_pmid is not None and numeric_pmid < previous_pmid:
            raise ChunkEmbeddingError("chunks must be sorted by numeric PMID")
        previous_pmid = numeric_pmid
        ordinal = expected_ordinal.get(chunk.pmid, 1)
        if chunk.chunk_id != f"{chunk.pmid}:c{ordinal:04d}":
            raise ChunkEmbeddingError(f"invalid chunk order at line {number}")
        expected_ordinal[chunk.pmid] = ordinal + 1
        chunks.append(chunk)
    if len(chunks) != manifest.get("chunk_count") or not chunks or len({c.chunk_id for c in chunks}) != len(chunks): raise ChunkEmbeddingError("chunk count or chunk-id order is invalid")
    return tuple(chunks), manifest

def build_embedding_cache(chunks_path: Path, manifest_path: Path, output: Path, *, client: EmbeddingClient, batch_size: int = 100, overwrite: bool = False) -> tuple[EmbeddingCacheManifest, int, int]:
    if output.exists() and not overwrite: raise ChunkEmbeddingError(f"refusing to overwrite existing cache: {output}")
    chunks, chunk_manifest = load_chunk_artifact(chunks_path, manifest_path)
    inputs = tuple(embedding_text(chunk) for chunk in chunks); vectors = client.embed(inputs, batch_size=batch_size)
    if vectors.shape[0] != len(chunks) or vectors.ndim != 2 or vectors.shape[1] == 0: raise ChunkEmbeddingError("embedding client returned an invalid matrix")
    cache_manifest = EmbeddingCacheManifest.create(model=client.model, dimension=int(vectors.shape[1]), corpus_hash=chunk_manifest["corpus_sha256"], chunk_hash=chunk_manifest["chunk_sha256"], inputs=inputs, chunk_ids=[c.chunk_id for c in chunks])
    save_embedding_cache(output, vectors, cache_manifest)
    return cache_manifest, len(inputs), sum(len(value.split()) for value in inputs)

def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__); p.add_argument("--chunks", type=Path, required=True); p.add_argument("--manifest", type=Path); p.add_argument("--output", type=Path, required=True); p.add_argument("--model", default=DEFAULT_EMBEDDING_MODEL); p.add_argument("--batch-size", type=int, default=100); p.add_argument("--overwrite", action="store_true"); args = p.parse_args(argv)
    manifest = args.manifest or args.chunks.with_suffix(args.chunks.suffix + ".manifest.json")
    try:
        client = EmbeddingClient(model=args.model)
        result, count, words = build_embedding_cache(args.chunks, manifest, args.output, client=client, batch_size=args.batch_size, overwrite=args.overwrite)
    except (ChunkEmbeddingError, ValueError, RuntimeError, OSError) as exc: print(f"Error: {exc}", file=sys.stderr); return 1
    print(json.dumps({"cache": str(args.output), "model": result.model, "provider": result.provider, "dimension": result.dimension, "embedding_inputs": count, "input_word_count": words, "provider_usage": client.last_metadata}, sort_keys=True)); return 0
if __name__ == "__main__": raise SystemExit(main())

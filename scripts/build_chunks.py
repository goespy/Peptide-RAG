#!/usr/bin/env python3
"""Build reproducible offset-preserving chunk JSONL files from the frozen corpus."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.chunks import CHUNK_CONFIGS, ChunkConfig, chunk_corpus

FROZEN_CORPUS_SHA256 = "231E048971C34EF9203ED3BB20587DDE4C95141AC7EFD2746C85C078A844212C"


class ChunkBuildError(RuntimeError):
    """Raised when an immutable chunk artifact cannot safely be built."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def load_corpus(path: Path) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    try:
        with Path(path).open(encoding="utf-8") as source:
            for number, line in enumerate(source, start=1):
                if not line.strip():
                    raise ChunkBuildError(f"blank corpus line {number}")
                item = json.loads(line)
                if not isinstance(item, dict):
                    raise ChunkBuildError(f"corpus line {number} is not an object")
                records.append(item)  # validated by chunk_corpus
    except (OSError, json.JSONDecodeError) as exc:
        raise ChunkBuildError(f"could not read corpus {path}: {exc}") from exc
    return records


def _atomic_write(path: Path, content: str, *, overwrite: bool) -> None:
    path = Path(path)
    if path.exists() and not overwrite:
        raise ChunkBuildError(f"refusing to overwrite existing file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", text=True)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as target:
            target.write(content)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def build_chunks(corpus: Path, config: ChunkConfig, expected_corpus_sha256: str) -> tuple[list[dict[str, object]], str]:
    """Validate a corpus binding and return JSON-serializable deterministic chunks."""

    actual_hash = sha256(corpus)
    if actual_hash != expected_corpus_sha256.upper():
        raise ChunkBuildError(f"corpus hash mismatch: expected {expected_corpus_sha256.upper()}, got {actual_hash}")
    try:
        chunks = chunk_corpus(load_corpus(corpus), config)
    except (TypeError, ValueError) as exc:
        raise ChunkBuildError(str(exc)) from exc
    return [asdict(chunk) for chunk in chunks], actual_hash


def write_artifacts(chunks: list[dict[str, object]], corpus_hash: str, config: ChunkConfig,
                    output: Path, manifest: Path, *, overwrite: bool = False) -> dict[str, object]:
    """Atomically write chunk JSONL and a manifest that binds both artifacts."""

    if Path(output).resolve() == Path(manifest).resolve():
        raise ChunkBuildError("output and manifest must be different paths")
    payload = "".join(json.dumps(chunk, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n" for chunk in chunks)
    # Validate both destinations before changing either one.
    if not overwrite and (Path(output).exists() or Path(manifest).exists()):
        existing = Path(output) if Path(output).exists() else Path(manifest)
        raise ChunkBuildError(f"refusing to overwrite existing file: {existing}")
    _atomic_write(Path(output), payload, overwrite=overwrite)
    manifest_payload = {
        "schema_version": 1, "corpus_sha256": corpus_hash,
        "chunk_sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest().upper(),
        "chunk_count": len(chunks), "config": asdict(config),
    }
    _atomic_write(Path(manifest), json.dumps(manifest_payload, indent=2, sort_keys=True) + "\n", overwrite=overwrite)
    return manifest_payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=ROOT / "data" / "corpus.jsonl")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--words", type=int, required=True, choices=[item.words for item in CHUNK_CONFIGS])
    parser.add_argument("--overlap", type=int, required=True, choices=[item.overlap for item in CHUNK_CONFIGS])
    parser.add_argument("--corpus-sha256", "--expected-corpus-sha256", dest="corpus_sha256", default=FROZEN_CORPUS_SHA256)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manifest = args.manifest or args.output.with_suffix(args.output.suffix + ".manifest.json")
    try:
        config = ChunkConfig(args.words, args.overlap)
        if config not in CHUNK_CONFIGS:
            raise ChunkBuildError("words and overlap must be one of the frozen chunk configurations")
        chunks, corpus_hash = build_chunks(args.corpus, config, args.corpus_sha256)
        write_artifacts(chunks, corpus_hash, config, args.output, manifest, overwrite=args.overwrite)
    except (ChunkBuildError, OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

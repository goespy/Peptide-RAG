#!/usr/bin/env python3
"""Evaluate approved development QA evidence retrieval and freeze chunk selection."""
from __future__ import annotations

import argparse, hashlib, json, math, os, sys, tempfile
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path
from statistics import mean
from typing import Any, Callable, Sequence
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from scripts.embed_chunks import ChunkEmbeddingError, load_chunk_artifact
from src.analysis import ANALYSIS_CONFIGS, AnalysisConfig
from src.bm25 import BM25Config
from src.chunks import Chunk, embedding_text, span_contained
from src.embeddings import (
    DEFAULT_EMBEDDING_MODEL,
    EmbeddingCacheManifest,
    EmbeddingClient,
    load_embedding_cache,
    normalize_embeddings,
    save_embedding_cache,
)
from src.generation import GENERATION_MAX_TOKENS, GENERATION_TEMPERATURE, SYSTEM_PROMPT
from src.retrieval import Retriever

CUTOFFS = (1, 3, 5, 10); ALPHAS = (0.25, 0.5, 0.75)
class ChunkEvaluationError(RuntimeError): pass
def sha256(path: Path) -> str: return hashlib.sha256(Path(path).read_bytes()).hexdigest().upper()

def load_approved_qa(path: Path, corpus_path: Path) -> dict[str, Any]:
    try: qa = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc: raise ChunkEvaluationError(f"cannot read QA set: {exc}") from exc
    corpus_hash = sha256(corpus_path)
    if not isinstance(qa, dict) or qa.get("status") != "approved" or qa.get("corpus_sha256") != corpus_hash: raise ChunkEvaluationError("QA set must be approved and bound to the supplied corpus")
    questions = qa.get("questions")
    if not isinstance(questions, list) or len(questions) != 20: raise ChunkEvaluationError("approved QA set must contain exactly 20 questions")
    return qa

def development_answerable(qa: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    cases = tuple(case for case in qa["questions"] if isinstance(case, dict) and case.get("split") == "development" and case.get("answerable") is True)
    if len(cases) != 10: raise ChunkEvaluationError("approved QA set must contain 10 answerable development cases")
    for case in cases:
        if not isinstance(case.get("question"), str) or not isinstance(case.get("supporting_spans"), list) or not case["supporting_spans"]: raise ChunkEvaluationError(f"{case.get('id')} has no usable evidence")
    return cases

def development_questions(qa: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    cases = tuple(sorted(
        (case for case in qa["questions"] if isinstance(case, dict) and case.get("split") == "development"),
        key=lambda case: str(case.get("id", "")),
    ))
    if len(cases) != 13:
        raise ChunkEvaluationError("approved QA set must contain 13 development questions")
    ids = [case.get("id") for case in cases]
    if (
        len(set(ids)) != len(ids)
        or any(not isinstance(case_id, str) or not case_id for case_id in ids)
        or any(not isinstance(case.get("question"), str) or not case["question"].strip() for case in cases)
    ):
        raise ChunkEvaluationError("development questions must have unique IDs and nonempty text")
    return cases

def _cache_for(
    chunks: tuple[Chunk, ...],
    chunk_manifest: dict[str, Any],
    cache_path: Path,
    expected_model: str,
) -> tuple[np.ndarray, str]:
    try:
        with np.load(cache_path, allow_pickle=False) as stored:
            raw = json.loads(stored["manifest"].item())
        raw["input_hashes"] = tuple(raw["input_hashes"]); raw["chunk_ids"] = tuple(raw["chunk_ids"])
        expected = EmbeddingCacheManifest.create(model=expected_model, dimension=int(raw["dimension"]), corpus_hash=chunk_manifest["corpus_sha256"], chunk_hash=chunk_manifest["chunk_sha256"], inputs=[embedding_text(c) for c in chunks], chunk_ids=[c.chunk_id for c in chunks])
        vectors = load_embedding_cache(cache_path, expected)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc: raise ChunkEvaluationError(f"invalid embedding cache {cache_path}: {exc}") from exc
    if vectors is None: raise ChunkEvaluationError(f"embedding cache does not match chunk artifact: {cache_path}")
    return vectors, expected_model

def query_embeddings(
    qa: dict[str, Any],
    *,
    cache_path: Path,
    model: str,
    corpus_hash: str,
    qa_hash: str,
    client: EmbeddingClient | None = None,
    overwrite: bool = False,
) -> tuple[dict[str, np.ndarray], dict[str, object]]:
    """Load or create the versioned embeddings for all development questions."""

    cases = development_questions(qa)
    inputs = [str(case["question"]) for case in cases]
    case_ids = [str(case["id"]) for case in cases]
    path = Path(cache_path)
    usage_path = path.with_suffix(path.suffix + ".usage.json")
    if path.exists():
        try:
            with np.load(path, allow_pickle=False) as stored:
                raw = json.loads(stored["manifest"].item())
            raw["input_hashes"] = tuple(raw["input_hashes"])
            raw["chunk_ids"] = tuple(raw["chunk_ids"])
            expected = EmbeddingCacheManifest.create(
                model=model,
                dimension=int(raw["dimension"]),
                corpus_hash=corpus_hash,
                chunk_hash=qa_hash,
                inputs=inputs,
                chunk_ids=case_ids,
            )
            vectors = load_embedding_cache(path, expected)
            usage_packet = json.loads(usage_path.read_text(encoding="utf-8"))
            if (
                not isinstance(usage_packet, dict)
                or usage_packet.get("schema_version") != 1
                or usage_packet.get("model") != model
                or usage_packet.get("corpus_sha256") != corpus_hash
                or usage_packet.get("qa_sha256") != qa_hash
                or usage_packet.get("query_cache_sha256") != sha256(path)
                or usage_packet.get("question_count") != len(cases)
                or not isinstance(usage_packet.get("provider_usage"), dict)
            ):
                raise ChunkEvaluationError("development-query usage metadata does not match its cache")
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            if not overwrite:
                raise ChunkEvaluationError(f"invalid development-query embedding cache: {exc}") from exc
            vectors = None
        if vectors is not None:
            return dict(zip(inputs, vectors)), {"source": "frozen_query_cache", "creation": usage_packet["provider_usage"]}
        if not overwrite:
            raise ChunkEvaluationError("development-query embedding cache does not match the approved QA set")

    embedding_client = client if client is not None else EmbeddingClient(model=model)
    vectors = normalize_embeddings(embedding_client.embed(inputs, batch_size=100))
    if vectors.ndim != 2 or vectors.shape[0] != len(inputs) or vectors.shape[1] <= 0:
        raise ChunkEvaluationError("embedding client returned invalid development-query vectors")
    manifest = EmbeddingCacheManifest.create(
        model=model,
        dimension=int(vectors.shape[1]),
        corpus_hash=corpus_hash,
        chunk_hash=qa_hash,
        inputs=inputs,
        chunk_ids=case_ids,
    )
    save_embedding_cache(path, vectors, manifest)
    usage = dict(embedding_client.total_metadata)
    usage_packet = {
        "schema_version": 1,
        "model": model,
        "corpus_sha256": corpus_hash,
        "qa_sha256": qa_hash,
        "query_cache_sha256": sha256(path),
        "question_count": len(cases),
        "provider_usage": usage,
    }
    _atomic(usage_path, json.dumps(usage_packet, indent=2, sort_keys=True) + "\n", overwrite)
    stored_vectors = load_embedding_cache(path, manifest)
    if stored_vectors is None:
        raise ChunkEvaluationError("saved development-query embedding cache failed immediate validation")
    return dict(zip(inputs, stored_vectors)), {"source": "frozen_query_cache", "creation": usage}

def relevant_chunk_ids(case: dict[str, Any], chunks: Sequence[Chunk]) -> set[str]:
    relevant: set[str] = set()
    for span in case["supporting_spans"]:
        if not isinstance(span, dict): raise ChunkEvaluationError(f"{case.get('id')} malformed span")
        pmid, start, end = span.get("pmid"), span.get("start_char"), span.get("end_char")
        if not isinstance(pmid, str) or not isinstance(start, int) or not isinstance(end, int): raise ChunkEvaluationError(f"{case.get('id')} malformed span")
        relevant.update(chunk.chunk_id for chunk in chunks if chunk.pmid == pmid and span_contained(chunk, start, end))
    return relevant

def _metric(rankings: dict[str, list[str]], gold: dict[str, set[str]], cutoff: int) -> tuple[float, float]:
    recalls, hits = [], []
    for case_id, wanted in gold.items():
        found = set(rankings[case_id][:cutoff])
        recalls.append(len(found & wanted) / len(wanted) if wanted else 0.0)
        hits.append(1.0 if wanted and found & wanted else 0.0)
    return mean(recalls), mean(hits)

def evaluate_retriever(cases: Sequence[dict[str, Any]], retriever: Retriever, *, alpha: float | None = None) -> dict[str, Any]:
    if alpha is not None: retriever.alpha = alpha
    gold = {str(case["id"]): relevant_chunk_ids(case, retriever.chunks) for case in cases}
    modes = ("lexical", "semantic") if alpha is None else ("hybrid",)
    report: dict[str, Any] = {"case_count": len(cases), "modes": {}}
    for mode in modes:
        rankings = {str(case["id"]): [item.chunk_id for item in retriever.retrieve(str(case["question"]), k=10, mode=mode)] for case in cases}
        measured = {cutoff: _metric(rankings, gold, cutoff) for cutoff in CUTOFFS}
        report["modes"][mode] = {f"@{cutoff}": {"recall": measured[cutoff][0], "evidence_hit": measured[cutoff][1]} for cutoff in CUTOFFS}
    return report

def _selection_key(item: dict[str, Any]) -> tuple[float, float, float]:
    lexical, semantic = item["evaluation"]["modes"]["lexical"]["@5"]["recall"], item["evaluation"]["modes"]["semantic"]["@5"]["recall"]
    return (min(lexical, semantic), (lexical + semantic) / 2, -float(item["average_context_tokens"]))

def select_chunk_config(results: Sequence[dict[str, Any]]) -> dict[str, Any]:
    if not results: raise ChunkEvaluationError("no chunk configurations evaluated")
    # Primary criteria are descending; an otherwise exact tie uses the
    # configuration name in ascending order for platform-independent output.
    return min(results, key=lambda item: tuple(-value for value in _selection_key(item)) + (str(item["name"]),))

def select_alpha(results: Sequence[dict[str, Any]]) -> dict[str, Any]:
    if not results: raise ChunkEvaluationError("no RRF alphas evaluated")
    return sorted(results, key=lambda item: (item["evaluation"]["modes"]["hybrid"]["@5"]["recall"], item["evaluation"]["modes"]["hybrid"]["@5"]["evidence_hit"], -abs(item["alpha"] - .5)), reverse=True)[0]

def evaluate_candidates(
    qa: dict[str, Any],
    candidates: Sequence[tuple[str, tuple[Chunk, ...], np.ndarray, dict[str, Any]]],
    query_embedding: Callable[[str], np.ndarray],
    *,
    bm25_config: BM25Config = BM25Config(),
    analysis_config: AnalysisConfig = ANALYSIS_CONFIGS["baseline"],
) -> dict[str, Any]:
    cases = development_answerable(qa); configurations: list[dict[str, Any]] = []
    retrievers: dict[str, Retriever] = {}
    for name, chunks, vectors, config in candidates:
        retriever = Retriever(chunks, vectors, query_embedding=query_embedding, alpha=.5, bm25_config=bm25_config, analysis_config=analysis_config); retrievers[name] = retriever
        configurations.append({"name": name, "config": config, "chunk_count": len(chunks), "average_context_tokens": mean([len(embedding_text(c).split()) for c in chunks]), "evaluation": evaluate_retriever(cases, retriever)})
    selected = select_chunk_config(configurations); chosen = retrievers[selected["name"]]; alpha_results = [{"alpha": alpha, "evaluation": evaluate_retriever(cases, chosen, alpha=alpha)} for alpha in ALPHAS]
    alpha = select_alpha(alpha_results)
    return {"schema_version": 1, "selection_scope": "approved answerable development QA cases only", "case_ids": [case["id"] for case in cases], "chunk_configurations": configurations, "selected_chunk_config": selected["name"], "rrf_alphas": alpha_results, "selected_alpha": alpha["alpha"], "selection_rule": "max min(lexical,semantic) Recall@5; then mean Recall@5; then fewer average context tokens; RRF max Recall@5 then EvidenceHit@5 then alpha closest to 0.5"}

def markdown(report: dict[str, Any]) -> str:
    lines = ["# Chunk Retrieval Evaluation", "", "Development answerable QA cases only.", "", "| Config | Lexical R@5 | Semantic R@5 | Avg context tokens |", "|---|---:|---:|---:|"]
    for item in report["chunk_configurations"]:
        modes = item["evaluation"]["modes"]; lines.append(f"| {item['name']} | {modes['lexical']['@5']['recall']:.3f} | {modes['semantic']['@5']['recall']:.3f} | {item['average_context_tokens']:.1f} |")
    lines += ["", f"Selected chunk configuration: `{report['selected_chunk_config']}`.", "", "| Alpha | Hybrid R@5 | Hybrid Evidence Hit@5 |", "|---:|---:|---:|"]
    for item in report["rrf_alphas"]:
        values = item["evaluation"]["modes"]["hybrid"]["@5"]; lines.append(f"| {item['alpha']:.2f} | {values['recall']:.3f} | {values['evidence_hit']:.3f} |")
    lines += ["", f"Selected RRF alpha: `{report['selected_alpha']}`.", ""]
    return "\n".join(lines)

def _atomic(path: Path, content: str, overwrite: bool) -> None:
    if path.exists() and not overwrite: raise ChunkEvaluationError(f"refusing to overwrite existing file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True); fd, temp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as out: out.write(content); out.flush(); os.fsync(out.fileno())
        os.replace(temp, path)
    except BaseException:
        try: os.unlink(temp)
        except FileNotFoundError: pass
        raise

def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__); p.add_argument("--qa", type=Path, default=ROOT / "data/qa.json"); p.add_argument("--corpus", type=Path, default=ROOT / "data/corpus.jsonl"); p.add_argument("--lexical-config", type=Path, default=ROOT / "data/lexical_config.json"); p.add_argument("--candidate", action="append", nargs=4, metavar=("NAME", "CHUNKS", "MANIFEST", "CACHE"), required=True); p.add_argument("--embedding-model", default=DEFAULT_EMBEDDING_MODEL); p.add_argument("--query-cache", type=Path, default=ROOT / "artifacts/section5/query_embeddings.npz"); p.add_argument("--output-json", type=Path, required=True); p.add_argument("--output-md", type=Path, required=True); p.add_argument("--frozen-config", type=Path, required=True); p.add_argument("--contexts-output", type=Path); p.add_argument("--overwrite", action="store_true"); args = p.parse_args(argv)
    try:
        targets = (args.output_json, args.output_md, args.frozen_config) + ((args.contexts_output,) if args.contexts_output else ())
        for target in targets:
            if target.exists() and not args.overwrite: raise ChunkEvaluationError(f"refusing to overwrite existing file: {target}")
        qa = load_approved_qa(args.qa, args.corpus); loaded = []
        corpus_hash = sha256(args.corpus)
        lexical = json.loads(args.lexical_config.read_text(encoding="utf-8"))
        if not isinstance(lexical, dict) or lexical.get("corpus_sha256") != corpus_hash or lexical.get("qrels_sha256") != sha256(ROOT / "data/qrels_v2.json"):
            raise ChunkEvaluationError("lexical configuration is not bound to the frozen corpus and qrels")
        try:
            lexical_analysis = ANALYSIS_CONFIGS[lexical["analysis"]["name"]]
            lexical_bm25 = BM25Config(
                k1=float(lexical["bm25"]["k1"]),
                b=float(lexical["bm25"]["b"]),
                proximity_boost=float(lexical["bm25"].get("proximity_boost", 0.0)),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ChunkEvaluationError("lexical configuration is malformed") from exc
        cache_model: str | None = None
        for name, chunks_path, manifest_path, cache_path in args.candidate:
            chunks, manifest = load_chunk_artifact(Path(chunks_path), Path(manifest_path))
            if manifest.get("corpus_sha256") != corpus_hash:
                raise ChunkEvaluationError(f"{name} chunks are not bound to the approved QA corpus")
            vectors, model = _cache_for(chunks, manifest, Path(cache_path), args.embedding_model)
            if cache_model is not None and model != cache_model:
                raise ChunkEvaluationError("all candidate caches must use the same embedding model")
            cache_model = model
            loaded.append((name, chunks, vectors, manifest.get("config", {})))
        qa_hash = sha256(args.qa)
        query_cache, query_usage = query_embeddings(
            qa,
            cache_path=args.query_cache,
            model=cache_model or "",
            corpus_hash=corpus_hash,
            qa_hash=qa_hash,
            overwrite=args.overwrite,
        )
        def embed(query: str) -> np.ndarray:
            try:
                return query_cache[query]
            except KeyError as exc:
                raise ChunkEvaluationError("query is not present in the frozen development cache") from exc
        report = evaluate_candidates(qa, loaded, embed, bm25_config=lexical_bm25, analysis_config=lexical_analysis); report.update({"qa_sha256": qa_hash, "corpus_sha256": sha256(args.corpus), "embedding_model": cache_model, "lexical_config_sha256": sha256(args.lexical_config), "query_embedding_cache_sha256": sha256(args.query_cache), "query_embedding_usage": query_usage})
        report_json = json.dumps(report, indent=2, sort_keys=True) + "\n"
        _atomic(args.output_json, report_json, args.overwrite); _atomic(args.output_md, markdown(report), args.overwrite)
        chosen = next(item for item in report["chunk_configurations"] if item["name"] == report["selected_chunk_config"]); frozen = {
            "schema_version": 1,
            "status": "selected_and_frozen",
            "selected": True,
            "qa_sha256": report["qa_sha256"],
            "corpus_sha256": report["corpus_sha256"],
            "chunk_config": chosen["config"],
            "chunk_candidate": chosen["name"],
            "embedding_model": cache_model,
            "lexical_config_sha256": report["lexical_config_sha256"],
            "lexical_analysis": lexical["analysis"],
            "lexical_bm25": lexical["bm25"],
            "rrf_alpha": report["selected_alpha"],
            "prompt": SYSTEM_PROMPT,
            "prompt_sha256": hashlib.sha256(SYSTEM_PROMPT.encode("utf-8")).hexdigest().upper(),
            "generation": {"temperature": GENERATION_TEMPERATURE, "max_tokens": GENERATION_MAX_TOKENS},
            "generator_candidates": ["qwen/qwen3.7-flash", "openai/gpt-oss-20b", "google/gemma-3-12b-it"],
            "source_evaluation_sha256": hashlib.sha256(report_json.encode("utf-8")).hexdigest().upper(),
        }
        frozen_json = json.dumps(frozen, indent=2, sort_keys=True) + "\n"
        _atomic(args.frozen_config, frozen_json, args.overwrite)
        if args.contexts_output:
            selected_name = report["selected_chunk_config"]
            selected_chunks, selected_vectors, _ = next(
                (chunks, vectors, config)
                for name, chunks, vectors, config in loaded
                if name == selected_name
            )
            selected_retriever = Retriever(
                selected_chunks,
                selected_vectors,
                query_embedding=embed,
                alpha=float(report["selected_alpha"]),
                bm25_config=lexical_bm25,
                analysis_config=lexical_analysis,
            )
            development = development_questions(qa)
            contexts = []
            for question in development:
                retrieved = selected_retriever.retrieve(str(question["question"]), k=5, mode="hybrid")
                contexts.append({
                    "qa_id": question["id"],
                    "chunks": [
                        {
                            **asdict(item.chunk),
                            "score": item.score,
                            "lexical_rank": item.lexical_rank,
                            "semantic_rank": item.semantic_rank,
                        }
                        for item in retrieved
                    ],
                })
            context_packet = {
                "schema_version": 1,
                "qa_sha256": report["qa_sha256"],
                "frozen_config_sha256": hashlib.sha256(frozen_json.encode("utf-8")).hexdigest().upper(),
                "selection_scope": "13 development questions; holdout excluded",
                "contexts": contexts,
            }
            _atomic(args.contexts_output, json.dumps(context_packet, indent=2, sort_keys=True) + "\n", args.overwrite)
    except (ChunkEvaluationError, ChunkEmbeddingError, ValueError, RuntimeError, OSError, TypeError) as exc: print(f"Error: {exc}", file=sys.stderr); return 1
    print(f"Evaluated {len(report['case_ids'])} development cases; selected {report['selected_chunk_config']} / alpha {report['selected_alpha']}"); return 0
if __name__ == "__main__": raise SystemExit(main())

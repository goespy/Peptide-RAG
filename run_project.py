#!/usr/bin/env python3
"""Run the project release checks without network access by default.

This command is deliberately read-only: it validates the checked-in evidence,
recomputes the lexical evaluation in memory, and reports RAG gates as TBD when
their paid/offline inputs have not been committed yet.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from run_day1 import Day1Error, load_qrels, sha256, validate_corpus_binding
from src.analysis import ANALYSIS_CONFIGS
from src.bm25 import BM25Config, rank_bm25
from src.boolean import search_boolean
from src.index import InvertedIndex
from src.metrics import evaluate_run


ROOT = Path(__file__).resolve().parent
CORPUS = ROOT / "data/corpus.jsonl"
QRELS = ROOT / "data/qrels_v2.json"
QA = ROOT / "data/qa.json"
LEXICAL_CONFIG = ROOT / "data/lexical_config.json"
EVAL_SPLIT = ROOT / "data/eval_split.json"
BASELINE = ROOT / "artifacts/section3/baseline.json"
SECTION5 = ROOT / "artifacts/section5"
DEVELOPMENT_EXPERIMENTS = ROOT / "artifacts/section4/development_experiments.json"
HOLDOUT = ROOT / "artifacts/section4/holdout.json"
BENCHMARK = ROOT / "artifacts/section4/benchmark_lexical.json"
CHUNK_EVALUATION = SECTION5 / "chunk_evaluation.json"
FROZEN_RAG_CONFIG = SECTION5 / "frozen_config.json"
EMBEDDING_USAGE = SECTION5 / "embedding_usage.json"
QUERY_EMBEDDING_USAGE = SECTION5 / "query_embeddings.npz.usage.json"
QUERY_EMBEDDING_CACHE = SECTION5 / "query_embeddings.npz"
RAG_DEVELOPMENT_CONTEXTS = ROOT / "data/rag_development_contexts.json"


@dataclass(frozen=True)
class Check:
    name: str
    state: str  # PASS, FAIL, or TBD
    detail: str
    required: bool = False


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {path.relative_to(ROOT)}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path.relative_to(ROOT)} must contain a JSON object")
    return value


def _require_hash(payload: dict[str, Any], key: str, path: Path) -> None:
    expected = payload.get(key)
    if not isinstance(expected, str) or len(expected) != 64:
        raise ValueError(f"missing valid {key} in frozen metadata")
    actual = sha256(path)
    if actual.upper() != expected.upper():
        raise ValueError(f"{key} mismatch: expected {expected.upper()}, got {actual}")


def _core_checks() -> tuple[list[Check], InvertedIndex, dict[str, Any], BM25Config]:
    for path in (CORPUS, QRELS, LEXICAL_CONFIG, EVAL_SPLIT, BASELINE):
        if not path.is_file():
            raise ValueError(f"required core artifact is missing: {path.relative_to(ROOT)}")
    qrels = load_qrels(QRELS)
    corpus_hash = validate_corpus_binding(CORPUS, qrels)
    config = _json(LEXICAL_CONFIG)
    _require_hash(config, "corpus_sha256", CORPUS)
    _require_hash(config, "qrels_sha256", QRELS)
    _require_hash(config, "eval_split_sha256", EVAL_SPLIT)
    baseline = _json(BASELINE)
    metadata = baseline.get("metadata")
    if not isinstance(metadata, dict):
        raise ValueError("baseline artifact has no metadata object")
    _require_hash(metadata, "corpus_sha256", CORPUS)
    _require_hash(metadata, "qrels_sha256", QRELS)
    bm25 = config.get("bm25")
    if not isinstance(bm25, dict) or not all(isinstance(bm25.get(k), (int, float)) for k in ("k1", "b")):
        raise ValueError("frozen lexical configuration has no usable BM25 parameters")
    try:
        analysis = ANALYSIS_CONFIGS[config["analysis"]["name"]]
        bm25_config = BM25Config(
            k1=float(bm25["k1"]),
            b=float(bm25["b"]),
            proximity_boost=float(bm25.get("proximity_boost", 0.0)),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("frozen lexical analyzer/BM25 configuration is invalid") from exc
    index = InvertedIndex.from_jsonl(CORPUS, analysis_config=analysis)
    return [
        Check("frozen core hashes", "PASS", f"corpus {corpus_hash}; qrels/config/split bindings match", True),
        Check("inverted index", "PASS", f"{len(index.documents)} documents; {len(index.postings)} terms", True),
    ], index, qrels, bm25_config


def _reports_match(actual: Any, expected: Any, *, tolerance: float = 1e-9) -> bool:
    """Compare complete saved/recomputed reports with a strict float tolerance."""

    if isinstance(actual, bool) or isinstance(expected, bool):
        return actual is expected
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        return math.isclose(float(actual), float(expected), rel_tol=tolerance, abs_tol=tolerance)
    if isinstance(actual, dict) and isinstance(expected, dict):
        return set(actual) == set(expected) and all(
            _reports_match(actual[key], expected[key], tolerance=tolerance) for key in actual
        )
    if isinstance(actual, list) and isinstance(expected, list):
        return len(actual) == len(expected) and all(
            _reports_match(left, right, tolerance=tolerance) for left, right in zip(actual, expected)
        )
    return actual == expected


def _evaluate(index: InvertedIndex, qrels: dict[str, Any], config: BM25Config) -> list[Check]:
    rankings = {
        "boolean": {entry["id"]: search_boolean(index, entry["query"]) for entry in qrels["queries"]},
        "bm25": {
            entry["id"]: [result.doc_id for result in rank_bm25(index, entry["query"], k=len(index.documents), config=config)]
            for entry in qrels["queries"]
        },
    }
    baseline = _json(BASELINE)
    holdout = _json(HOLDOUT)
    expected_reports = {
        "boolean": baseline.get("runs", {}).get("boolean", {}).get("evaluation"),
        "bm25": holdout.get("full_descriptive"),
    }
    checks: list[Check] = []
    for mode, ranked in rankings.items():
        report = evaluate_run(qrels, ranked, (1, 3, 5, 10))
        aggregate = report.aggregate
        matches = _reports_match(report.to_dict(), expected_reports[mode])
        checks.append(Check(
            f"current {mode} evaluation", "PASS" if matches else "FAIL",
            f"{aggregate['query_count']} queries; MRR={aggregate['mrr']:.3f}; NDCG@10={aggregate['ndcg_at'][10]:.3f}; "
            + ("complete report matches saved evidence" if matches else "complete report differs from saved evidence"),
            True,
        ))
    return checks


def _section4_checks(config: dict[str, Any]) -> list[Check]:
    for path in (DEVELOPMENT_EXPERIMENTS, HOLDOUT, BENCHMARK):
        if not path.is_file():
            raise ValueError(f"required Section 4 artifact is missing: {path.relative_to(ROOT)}")
    _require_hash(config, "development_experiments_sha256", DEVELOPMENT_EXPERIMENTS)
    holdout = _json(HOLDOUT)
    metadata = holdout.get("metadata")
    if not isinstance(metadata, dict):
        raise ValueError("Section 4 holdout has no metadata")
    expected = {
        "corpus_sha256": sha256(CORPUS),
        "qrels_sha256": sha256(QRELS),
        "split_sha256": sha256(EVAL_SPLIT),
        "lexical_config_sha256": sha256(LEXICAL_CONFIG),
        "development_experiments_sha256": sha256(DEVELOPMENT_EXPERIMENTS),
    }
    if any(str(metadata.get(key, "")).upper() != value for key, value in expected.items()):
        raise ValueError("Section 4 holdout provenance does not match frozen inputs")
    benchmark = _json(BENCHMARK)
    inputs = benchmark.get("inputs")
    if not isinstance(inputs, dict) or any(
        str(inputs.get(key, "")).upper() != value
        for key, value in {
            "corpus_sha256": sha256(CORPUS),
            "qrels_sha256": sha256(QRELS),
            "lexical_config_sha256": sha256(LEXICAL_CONFIG),
        }.items()
    ):
        raise ValueError("Section 4 benchmark provenance does not match frozen inputs")
    return [Check("Section 4 experiment provenance", "PASS", "development grid, one-shot holdout, and benchmark hashes match", True)]


def _validate_frozen_qa(path: Path) -> Check:
    qa = _json(path)
    if qa.get("status") != "approved" or qa.get("version") != 1:
        raise ValueError("frozen QA must be approved version 1")
    if str(qa.get("corpus_sha256", "")).upper() != sha256(CORPUS):
        raise ValueError("frozen QA corpus hash does not match")
    if str(qa.get("qrels_v2_sha256", "")).upper() != sha256(QRELS):
        raise ValueError("frozen QA qrels hash does not match")
    questions = qa.get("questions")
    expected_ids = [f"qa{number:02d}" for number in range(1, 21)]
    if (
        not isinstance(questions, list)
        or len(questions) != len(expected_ids)
        or any(not isinstance(item, dict) for item in questions)
        or [item.get("id") for item in questions] != expected_ids
    ):
        raise ValueError("frozen QA must contain qa01 through qa20 exactly once")
    if sum(item.get("answerable") is True for item in questions) != 15 or sum(item.get("answerable") is False for item in questions) != 5:
        raise ValueError("frozen QA must contain 15 answerable and 5 unanswerable cases")
    corpus: dict[str, str] = {}
    with CORPUS.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, 1):
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid corpus JSON line {line_number}") from exc
            if not isinstance(record, dict) or not isinstance(record.get("id"), str) or not isinstance(record.get("text"), str):
                raise ValueError(f"invalid corpus record at line {line_number}")
            corpus[record["id"]] = record["text"]
    split_pmids: dict[str, set[str]] = {"development": set(), "holdout": set()}
    for item in questions:
        review = item.get("human_review")
        if not isinstance(review, dict) or review.get("approved") is not True or review.get("decision") != "approve" or not str(review.get("reviewer", "")).strip():
            raise ValueError(f"{item['id']} lacks explicit human approval")
        split = item.get("split")
        if split not in split_pmids:
            raise ValueError(f"{item['id']} has invalid split")
        pmids, spans = item.get("relevant_pmids"), item.get("supporting_spans")
        if not isinstance(pmids, list) or not isinstance(spans, list):
            raise ValueError(f"{item['id']} has malformed evidence lists")
        if item["answerable"] is False:
            if pmids or spans or item.get("acceptable_answer"):
                raise ValueError(f"{item['id']} unanswerable case contains answer evidence")
            continue
        if not pmids or not spans or not str(item.get("acceptable_answer", "")).strip():
            raise ValueError(f"{item['id']} answerable case lacks evidence")
        if {span.get("pmid") for span in spans if isinstance(span, dict)} != set(pmids):
            raise ValueError(f"{item['id']} PMID and supporting-span sets disagree")
        split_pmids[split].update(pmids)
        for span in spans:
            pmid, start, end = span.get("pmid"), span.get("start_char"), span.get("end_char")
            if pmid not in corpus or isinstance(start, bool) or not isinstance(start, int) or isinstance(end, bool) or not isinstance(end, int) or start < 0 or end <= start:
                raise ValueError(f"{item['id']} has malformed supporting span")
            extracted = corpus[pmid][start:end]
            if hashlib.sha256(extracted.encode("utf-8")).hexdigest().upper() != str(span.get("text_sha256", "")).upper():
                raise ValueError(f"{item['id']} supporting span hash does not match corpus")
    if not split_pmids["development"].isdisjoint(split_pmids["holdout"]):
        raise ValueError("frozen QA development and holdout supporting PMIDs overlap")
    return Check("approved QA oracle", "PASS", "20 owner-approved cases (15/5); exact spans, hashes, and split PMID separation verified")


def _validate_rag_retrieval() -> Check:
    required = (CHUNK_EVALUATION, FROZEN_RAG_CONFIG, EMBEDDING_USAGE, QUERY_EMBEDDING_USAGE, QUERY_EMBEDDING_CACHE, RAG_DEVELOPMENT_CONTEXTS)
    missing = [path.relative_to(ROOT).as_posix() for path in required if not path.is_file()]
    if missing:
        return Check("RAG retrieval evaluation", "TBD", f"missing frozen retrieval artifacts: {', '.join(missing)}")
    report, frozen = _json(CHUNK_EVALUATION), _json(FROZEN_RAG_CONFIG)
    ledger, query_usage = _json(EMBEDDING_USAGE), _json(QUERY_EMBEDDING_USAGE)
    contexts = _json(RAG_DEVELOPMENT_CONTEXTS)
    corpus_hash, qa_hash = sha256(CORPUS), sha256(QA)
    if report.get("corpus_sha256") != corpus_hash or report.get("qa_sha256") != qa_hash:
        raise ValueError("chunk evaluation is not bound to the frozen corpus and QA set")
    if (
        frozen.get("status") != "selected_and_frozen"
        or frozen.get("selected") is not True
        or frozen.get("corpus_sha256") != corpus_hash
        or frozen.get("qa_sha256") != qa_hash
        or frozen.get("source_evaluation_sha256") != sha256(CHUNK_EVALUATION)
        or frozen.get("chunk_candidate") != report.get("selected_chunk_config")
    ):
        raise ValueError("selected RAG configuration does not match its source evaluation")
    qa = _json(QA)
    questions = qa.get("questions")
    if not isinstance(questions, list) or any(not isinstance(item, dict) for item in questions):
        raise ValueError("approved QA questions are malformed")
    development_ids = sorted(str(item["id"]) for item in questions if item.get("split") == "development")
    answerable_ids = sorted(str(item["id"]) for item in questions if item.get("split") == "development" and item.get("answerable") is True)
    if report.get("case_ids") != answerable_ids:
        raise ValueError("chunk evaluation case IDs are not the frozen answerable development split")
    context_rows = contexts.get("contexts")
    if (
        contexts.get("qa_sha256") != qa_hash
        or contexts.get("frozen_config_sha256") != sha256(FROZEN_RAG_CONFIG)
        or not isinstance(context_rows, list)
        or sorted(row.get("qa_id") for row in context_rows if isinstance(row, dict)) != development_ids
    ):
        raise ValueError("RAG development contexts are incomplete or leak outside the frozen split")
    runs = ledger.get("runs")
    totals = ledger.get("totals")
    if not isinstance(runs, list) or len(runs) != 4 or not isinstance(totals, dict):
        raise ValueError("embedding usage ledger is malformed")
    measured_tokens = measured_calls = measured_inputs = 0
    measured_cost = 0.0
    root = ROOT.resolve()
    for run in runs:
        if not isinstance(run, dict) or not isinstance(run.get("artifact"), str):
            raise ValueError("embedding usage run is malformed")
        artifact = (ROOT / run["artifact"]).resolve()
        if root != artifact and root not in artifact.parents:
            raise ValueError("embedding usage artifact escapes the repository")
        if not artifact.is_file() or run.get("artifact_sha256") != sha256(artifact):
            raise ValueError(f"embedding usage hash mismatch for {run['artifact']}")
        measured_tokens += int(run.get("input_tokens", -1))
        measured_calls += int(run.get("provider_calls", -1))
        measured_inputs += int(run.get("embedding_inputs", -1))
        measured_cost += float(run.get("cost_usd", math.nan))
    if (
        totals.get("input_tokens") != measured_tokens
        or totals.get("provider_calls") != measured_calls
        or totals.get("embedding_inputs") != measured_inputs
        or not math.isclose(float(totals.get("cost_usd", math.nan)), measured_cost, rel_tol=0, abs_tol=1e-12)
    ):
        raise ValueError("embedding usage totals do not equal the recorded runs")
    if query_usage.get("query_cache_sha256") != sha256(QUERY_EMBEDDING_CACHE) or query_usage.get("qa_sha256") != qa_hash or query_usage.get("corpus_sha256") != corpus_hash:
        raise ValueError("development-query usage metadata is not bound to its cache and frozen inputs")
    return Check("RAG retrieval evaluation", "PASS", "development-only chunk metrics, selected hybrid config, caches, contexts, and $0.04643258 usage ledger verified", True)


def _rag_checks() -> list[Check]:
    manifests = sorted(SECTION5.glob("*.jsonl.manifest.json")) if SECTION5.is_dir() else []
    checks: list[Check] = []
    if not manifests:
        checks.append(Check("RAG chunk artifacts", "TBD", "no checked-in chunk manifests"))
    corpus_hash = sha256(CORPUS)
    for manifest_path in manifests:
        try:
            manifest = _json(manifest_path)
            chunks = manifest_path.with_name(manifest_path.name.removesuffix(".manifest.json"))
            if not chunks.is_file():
                raise ValueError("chunk file is missing")
            if manifest.get("corpus_sha256", "").upper() != corpus_hash:
                raise ValueError("corpus hash does not match")
            if manifest.get("chunk_sha256", "").upper() != sha256(chunks):
                raise ValueError("chunk hash does not match")
            with chunks.open(encoding="utf-8") as chunk_file:
                chunk_count = sum(1 for _ in chunk_file)
            if not isinstance(manifest.get("chunk_count"), int) or manifest["chunk_count"] != chunk_count:
                raise ValueError("chunk count does not match")
            checks.append(Check(f"RAG {chunks.name}", "PASS", "manifest binds chunk file and corpus"))
        except (OSError, ValueError) as exc:
            checks.append(Check(f"RAG {manifest_path.name}", "FAIL", str(exc)))
    if not QA.is_file():
        checks.append(Check("approved QA oracle", "TBD", "approved QA artifact is not committed"))
    else:
        try:
            checks.append(_validate_frozen_qa(QA))
        except (OSError, ValueError, TypeError) as exc:
            checks.append(Check("approved QA oracle", "FAIL", str(exc)))
    try:
        checks.append(_validate_rag_retrieval())
    except (Day1Error, OSError, ValueError, KeyError, TypeError) as exc:
        checks.append(Check("RAG retrieval evaluation", "FAIL", str(exc), True))
    checks.append(Check("RAG faithfulness evaluation", "TBD", "generator bake-off, owner-validated judge, and holdout outputs are pending"))
    return checks


def _live_eval() -> list[Check]:
    # Never guess provider pricing or send a request from a release check.
    checks = [Check("live-eval cost estimate", "TBD", "embedding spend is recorded; generation/judge maximum requires a fresh model catalog and explicit confirmation")]
    if not os.environ.get("OPENROUTER_API_KEY"):
        checks.append(Check("live-eval credentials", "TBD", "OPENROUTER_API_KEY is not set; no network call attempted"))
    else:
        checks.append(Check("live-eval pipeline", "TBD", "credential detected and retrieval is frozen, but generator/judge artifacts are incomplete; no paid call attempted"))
    return checks


def run(*, live_eval: bool = False) -> tuple[list[Check], bool]:
    try:
        checks, index, qrels, config = _core_checks()
        checks.extend(_section4_checks(_json(LEXICAL_CONFIG)))
        checks.extend(_evaluate(index, qrels, config))
    except (Day1Error, OSError, ValueError, KeyError, TypeError) as exc:
        return [Check("required core artifacts", "FAIL", str(exc), True)], True
    try:
        checks.extend(_rag_checks())
    except (OSError, ValueError, KeyError, TypeError) as exc:
        checks.append(Check("RAG artifact validation", "FAIL", str(exc), True))
    if live_eval:
        checks.extend(_live_eval())
    return checks, any(check.state == "FAIL" for check in checks)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-eval", action="store_true", help="show guarded live-evaluation readiness; never runs paid calls while gates are incomplete")
    args = parser.parse_args(argv)
    checks, failed = run(live_eval=args.live_eval)
    print("Peptide-RAG release check (offline/read-only)")
    for check in checks:
        print(f"[{check.state}] {check.name}: {check.detail}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

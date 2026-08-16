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
from scripts.export_rag_holdout_contexts import (
    EMBEDDING_HARD_CAP_USD,
    embedding_cost_estimate,
)
from scripts.freeze_generator_selection import build_selection
from scripts.project_costs import projection_from_paths
from scripts.run_generator_diagnostic import (
    summarize as summarize_generator,
    validate_selected_parameter_support,
)
from scripts.run_generator_judge import (
    estimate_judge_cost,
    judge_usage,
    offline_judged_rows,
    validate_generator_gate,
    validate_judge_config,
)
from scripts.run_rag_bakeoff import (
    BakeoffError,
    contexts_from,
    offline_rows,
    realized_usage,
    validate_config,
    validate_judge_catalog,
    validate_model_catalog,
    validate_qa,
)
from scripts.run_rag_holdout import (
    HOLDOUT_OUTPUT_FIELDS,
    estimate_holdout_cost,
    expected_final_config,
    expected_summary,
    holdout_cases,
    saved_rows,
    validate_context_provenance,
    validate_selection_bindings,
)
from scripts.validate_judge import (
    review_material as judge_review_material,
    validate_labels as validate_judge_labels,
    worksheet as expected_judge_worksheet,
)
from src.analysis import ANALYSIS_CONFIGS
from src.bm25 import BM25Config, rank_bm25
from src.boolean import search_boolean
from src.index import InvertedIndex
from src.metrics import evaluate_run
from src.rag_metrics import select_winner


ROOT = Path(__file__).resolve().parent
CORPUS = ROOT / "data/corpus.jsonl"
QRELS = ROOT / "data/qrels_v2.json"
QA = ROOT / "data/qa.json"
LEXICAL_CONFIG = ROOT / "data/lexical_config.json"
EVAL_SPLIT = ROOT / "data/eval_split.json"
BASELINE = ROOT / "artifacts/section3/baseline.json"
SECTION5 = ROOT / "artifacts/section5"
SECTION6 = ROOT / "artifacts/section6"
DEVELOPMENT_EXPERIMENTS = ROOT / "artifacts/section4/development_experiments.json"
HOLDOUT = ROOT / "artifacts/section4/holdout.json"
BENCHMARK = ROOT / "artifacts/section4/benchmark_lexical.json"
CHUNK_EVALUATION = SECTION5 / "chunk_evaluation.json"
FROZEN_RAG_CONFIG = SECTION5 / "frozen_config.json"
EMBEDDING_USAGE = SECTION5 / "embedding_usage.json"
QUERY_EMBEDDING_USAGE = SECTION5 / "query_embeddings.npz.usage.json"
QUERY_EMBEDDING_CACHE = SECTION5 / "query_embeddings.npz"
RAG_DEVELOPMENT_CONTEXTS = ROOT / "data/rag_development_contexts.json"
RAG_BAKEOFF_OUTPUTS = ROOT / "data/rag_bakeoff_outputs.json"
RAG_BAKEOFF_REANALYSIS = ROOT / "data/rag_bakeoff_reanalysis.json"
JUDGE_WORKSHEET = ROOT / "data/judge_validation_worksheet.json"
MODEL_CATALOG_REFRESH = SECTION5 / "model_candidates_refresh.json"
JUDGE_MODEL_CATALOG_REFRESH = SECTION5 / "model_candidates_judge_refresh.json"
GENERATOR_V2_2_CONFIG = SECTION5 / "generator_v2_2_config.json"
GENERATOR_V2_2_OUTPUTS = ROOT / "data/rag_generator_v2_2_outputs.json"
GENERATOR_V2_2_SUMMARY = ROOT / "data/rag_generator_v2_2_summary.json"
GENERATOR_V2_3_CONFIG = SECTION5 / "generator_v2_3_config.json"
GENERATOR_V2_3_OUTPUTS = ROOT / "data/rag_generator_v2_3_outputs.json"
GENERATOR_V2_3_SUMMARY = ROOT / "data/rag_generator_v2_3_summary.json"
GENERATOR_V2_4_CONFIG = SECTION5 / "generator_v2_4_config.json"
GENERATOR_V2_4_OUTPUTS = ROOT / "data/rag_generator_v2_4_outputs.json"
GENERATOR_V2_4_SUMMARY = ROOT / "data/rag_generator_v2_4_summary.json"
GENERATOR_V2_4_JUDGE_CONFIG = SECTION5 / "generator_v2_4_judge_config.json"
GENERATOR_V2_4_JUDGED_OUTPUTS = ROOT / "data/rag_generator_v2_4_judged_outputs.json"
GENERATOR_V2_4_JUDGE_SUMMARY = ROOT / "data/rag_generator_v2_4_judge_summary.json"
GENERATOR_V2_4_JUDGE_WORKSHEET = ROOT / "data/judge_validation_v2_4_worksheet.json"
GENERATOR_V2_4_JUDGE_REPORT = ROOT / "data/judge_validation_v2_4_report.json"
GENERATOR_V2_4_JUDGE_REVIEW = SECTION5 / "claude_generator_v2_4_judge_review.md"
GENERATOR_V2_5_CONFIG = SECTION5 / "generator_v2_5_config.json"
GENERATOR_V2_5_OUTPUTS = ROOT / "data/rag_generator_v2_5_outputs.json"
GENERATOR_V2_5_SUMMARY = ROOT / "data/rag_generator_v2_5_summary.json"
GENERATOR_V2_5_JUDGE_CONFIG = SECTION5 / "generator_v2_5_judge_config.json"
GENERATOR_V2_5_JUDGED_OUTPUTS = ROOT / "data/rag_generator_v2_5_judged_outputs.json"
GENERATOR_V2_5_JUDGE_SUMMARY = ROOT / "data/rag_generator_v2_5_judge_summary.json"
GENERATOR_V2_5_JUDGE_WORKSHEET = ROOT / "data/judge_validation_v2_5_worksheet.json"
GENERATOR_V2_5_JUDGE_REPORT = ROOT / "data/judge_validation_v2_5_report.json"
ACCEPTED_GENERATOR_V2_5 = SECTION5 / "accepted_generator_v2_5.json"
RAG_HOLDOUT_CONTEXTS = ROOT / "data/rag_holdout_contexts.json"
RAG_HOLDOUT_MODEL_CATALOG = SECTION5 / "holdout_model_catalog.json"
RAG_HOLDOUT_OUTPUTS = ROOT / "data/rag_holdout_outputs.json"
RAG_HOLDOUT_SUMMARY = ROOT / "data/rag_holdout_summary.json"
FINAL_GENERATOR_CONFIG = SECTION5 / "generator_config.json"
SERVICE_MEMORY = SECTION6 / "service_memory.json"
COST_PROJECTION = SECTION6 / "cost_projection.json"
GENERATOR_V2_3_DIAGNOSIS = SECTION5 / "generator_v2_3_diagnosis.json"
GENERATOR_V2_3_REVIEW = SECTION5 / "claude_generator_v2_3_review.md"


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


def _source_sha256(path: Path) -> str:
    """Hash UTF-8 source with canonical LF newlines across Git platforms."""

    text = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest().upper()


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


def _validate_rag_bakeoff() -> Check:
    required = (RAG_BAKEOFF_OUTPUTS, RAG_BAKEOFF_REANALYSIS, JUDGE_WORKSHEET)
    missing = [path.relative_to(ROOT).as_posix() for path in required if not path.is_file()]
    if missing:
        return Check("RAG development bake-off evidence", "TBD", f"missing saved development artifacts: {', '.join(missing)}")
    qa_packet = _json(QA)
    context_packet = _json(RAG_DEVELOPMENT_CONTEXTS)
    output_packet = _json(RAG_BAKEOFF_OUTPUTS)
    reanalysis = _json(RAG_BAKEOFF_REANALYSIS)
    worksheet = _json(JUDGE_WORKSHEET)
    models = reanalysis.get("models")
    if not isinstance(models, list) or len(models) != 3 or any(not isinstance(model, str) for model in models):
        raise ValueError("bake-off reanalysis must name three models")
    qa_hash = sha256(QA)
    config_hash = sha256(FROZEN_RAG_CONFIG)
    contexts_hash = sha256(RAG_DEVELOPMENT_CONTEXTS)
    outputs_hash = sha256(RAG_BAKEOFF_OUTPUTS)
    if (
        reanalysis.get("qa_sha256") != qa_hash
        or reanalysis.get("config_sha256") != config_hash
        or reanalysis.get("contexts_sha256") != contexts_hash
        or reanalysis.get("outputs_sha256") != outputs_hash
    ):
        raise ValueError("bake-off reanalysis is not bound to the frozen QA, config, contexts, and outputs")
    cases = validate_qa(qa_packet)
    contexts = contexts_from(context_packet, cases, qa_hash=qa_hash, config_hash=config_hash)
    grouped = offline_rows(output_packet, cases, contexts, config_hash, contexts_hash, tuple(models))
    expected_selection = select_winner(grouped, len(cases))
    if reanalysis.get("selection") != expected_selection:
        raise ValueError("bake-off selection does not match the complete offline recomputation")
    expected_usage = realized_usage(grouped)
    if reanalysis.get("actual_usage") != expected_usage:
        raise ValueError("bake-off actual usage does not equal the 39 saved rows")
    if expected_usage.get("rows") != 39 or expected_usage.get("status") != "provider_reported_complete":
        raise ValueError("bake-off usage is incomplete")
    if (
        worksheet.get("version") != 2
        or worksheet.get("source_outputs_sha256") != outputs_hash
        or worksheet.get("qa_sha256") != qa_hash
        or worksheet.get("contexts_sha256") != contexts_hash
        or not isinstance(worksheet.get("sample"), list)
        or len(worksheet["sample"]) != 10
    ):
        raise ValueError("judge worksheet is not bound to the saved development evidence")
    for item in worksheet["sample"]:
        if (
            not isinstance(item, dict)
            or "judge" in item
            or not isinstance(item.get("question"), str)
            or item.get("answerability") not in {"answerable", "unanswerable"}
            or not isinstance(item.get("retrieved_evidence"), list)
            or len(item["retrieved_evidence"]) != 5
            or not isinstance(item.get("owner_label"), dict)
        ):
            raise ValueError("judge worksheet sample is malformed or leaks the judge verdict")
    winner = expected_selection.get("winner")
    winner_metrics = expected_selection.get("candidates", {}).get(winner, {})
    if expected_selection.get("winner_status") != "provisional_development_selection_pending_owner_judge_validation":
        raise ValueError("development winner is not marked provisional")
    return Check(
        "RAG development bake-off evidence",
        "PASS",
        f"39 outputs replay exactly; ${expected_usage['cost_usd']:.9f} provider spend; provisional {winner} answered {winner_metrics.get('denominators', {}).get('answered')}/10 answerable cases; worksheet is evidence-bound",
        True,
    )


def _validate_generator_diagnostic(
    label: str,
    config_path: Path,
    outputs_path: Path,
    summary_path: Path,
    catalog_path: Path = MODEL_CATALOG_REFRESH,
) -> Check:
    config = _json(config_path)
    validate_config(config)
    outputs = _json(outputs_path)
    summary = _json(summary_path)
    qa_hash = sha256(QA)
    contexts_hash = sha256(RAG_DEVELOPMENT_CONTEXTS)
    config_hash = sha256(config_path)
    outputs_hash = sha256(outputs_path)
    if (
        config.get("qa_sha256") != qa_hash
        or config.get("contexts_sha256") != contexts_hash
        or config.get("model_catalog_sha256") != sha256(catalog_path)
        or summary.get("qa_sha256") != qa_hash
        or summary.get("contexts_sha256") != contexts_hash
        or summary.get("config_sha256") != config_hash
        or summary.get("outputs_sha256") != outputs_hash
        or summary.get("model_catalog_sha256") != sha256(catalog_path)
        or summary.get("live_calls") is not True
    ):
        raise ValueError(f"{label} hashes do not bind the frozen development inputs")
    artifact_paths = config.get("artifact_paths")
    if not isinstance(artifact_paths, dict) or any(
        (ROOT / artifact_paths.get(field, "")).resolve() != path.resolve()
        for field, path in (("outputs", outputs_path), ("summary", summary_path))
    ):
        raise ValueError(f"{label} output paths do not match its frozen config")
    models = config.get("generator_candidates")
    if not isinstance(models, list) or not models or any(not isinstance(model, str) for model in models):
        raise ValueError(f"{label} has no frozen generator candidates")
    qa_packet = _json(QA)
    context_packet = _json(RAG_DEVELOPMENT_CONTEXTS)
    cases = validate_qa(qa_packet)
    contexts = contexts_from(
        context_packet,
        cases,
        qa_hash=qa_hash,
        config_hash=config.get("retriever_config_sha256", config_hash),
    )
    grouped = offline_rows(outputs, cases, contexts, config_hash, contexts_hash, tuple(models))
    expected_diagnostic = summarize_generator(grouped)
    if summary.get("diagnostic") != expected_diagnostic:
        raise ValueError(f"{label} diagnostic counts do not match its saved outputs")
    actual_usage = summary.get("actual_usage")
    aggregate = actual_usage.get("aggregate") if isinstance(actual_usage, dict) else None
    if aggregate != realized_usage(grouped):
        raise ValueError(f"{label} usage does not equal its saved output rows")
    candidate = expected_diagnostic["candidates"].get(models[0], {})
    return Check(
        f"RAG {label} generator evidence",
        "PASS",
        f"{len(models) * len(cases)} outputs replay; first candidate {candidate.get('answerable_answer_count')}/10 answerable, "
        f"{candidate.get('unanswerable_correct_system_refusal_count')}/3 refusals; ready={candidate.get('ready_for_paid_judging')}",
        True,
    )


def _validate_versioned_generator_evidence() -> list[Check]:
    checks = [
        _validate_generator_diagnostic(
            "GPT v2.2", GENERATOR_V2_2_CONFIG, GENERATOR_V2_2_OUTPUTS, GENERATOR_V2_2_SUMMARY
        ),
        _validate_generator_diagnostic(
            "GPT v2.3", GENERATOR_V2_3_CONFIG, GENERATOR_V2_3_OUTPUTS, GENERATOR_V2_3_SUMMARY
        ),
    ]
    v2_4 = _json(GENERATOR_V2_4_CONFIG)
    validate_config(v2_4)
    expected_parent_hashes = {
        "parent_config_sha256": sha256(GENERATOR_V2_3_CONFIG),
        "parent_diagnosis_sha256": sha256(GENERATOR_V2_3_DIAGNOSIS),
        "parent_outputs_sha256": sha256(GENERATOR_V2_3_OUTPUTS),
        "parent_review_sha256": sha256(GENERATOR_V2_3_REVIEW),
        "parent_summary_sha256": sha256(GENERATOR_V2_3_SUMMARY),
    }
    if (
        v2_4.get("qa_sha256") != sha256(QA)
        or v2_4.get("contexts_sha256") != sha256(RAG_DEVELOPMENT_CONTEXTS)
        or v2_4.get("model_catalog_sha256") != sha256(MODEL_CATALOG_REFRESH)
        or v2_4.get("holdout_status") != "untouched"
        or v2_4.get("qa_or_retrieval_changes") is not False
        or any(v2_4.get(field) != value for field, value in expected_parent_hashes.items())
    ):
        raise ValueError("GPT v2.4 config is not bound to the measured v2.3 evidence")
    present = (GENERATOR_V2_4_OUTPUTS.is_file(), GENERATOR_V2_4_SUMMARY.is_file())
    if present == (False, False):
        checks.append(
            Check(
                "RAG GPT v2.4 generator gate",
                "TBD",
                "frozen general reconsideration experiment is tested; paid development rerun not yet approved/run",
            )
        )
    elif present != (True, True):
        raise ValueError("GPT v2.4 has only one of its required output/summary artifacts")
    else:
        evidence = _validate_generator_diagnostic(
            "GPT v2.4", GENERATOR_V2_4_CONFIG, GENERATOR_V2_4_OUTPUTS, GENERATOR_V2_4_SUMMARY
        )
        checks.append(evidence)
        summary = _json(GENERATOR_V2_4_SUMMARY)
        candidate = summary.get("diagnostic", {}).get("candidates", {}).get("openai/gpt-oss-20b", {})
        checks.append(
            Check(
                "RAG GPT v2.4 generator gate",
                "PASS" if candidate.get("ready_for_paid_judging") is True else "TBD",
                "10/10, 3/3, and 13/13 gate passed" if candidate.get("ready_for_paid_judging") is True else "measured development run did not open paid judging",
            )
        )
        if candidate.get("ready_for_paid_judging") is True:
            checks.extend(_validate_frozen_judge_config())

    v2_5 = _json(GENERATOR_V2_5_CONFIG)
    validate_config(v2_5)
    expected_v2_5_parents = {
        "parent_config_sha256": sha256(GENERATOR_V2_4_CONFIG),
        "parent_outputs_sha256": sha256(GENERATOR_V2_4_OUTPUTS),
        "parent_summary_sha256": sha256(GENERATOR_V2_4_SUMMARY),
        "parent_review_sha256": sha256(GENERATOR_V2_4_JUDGE_REVIEW),
        "parent_judge_config_sha256": sha256(GENERATOR_V2_4_JUDGE_CONFIG),
        "parent_judge_outputs_sha256": sha256(GENERATOR_V2_4_JUDGED_OUTPUTS),
        "parent_judge_summary_sha256": sha256(GENERATOR_V2_4_JUDGE_SUMMARY),
    }
    if (
        v2_5.get("qa_sha256") != sha256(QA)
        or v2_5.get("contexts_sha256") != sha256(RAG_DEVELOPMENT_CONTEXTS)
        or v2_5.get("model_catalog_sha256") != sha256(JUDGE_MODEL_CATALOG_REFRESH)
        or v2_5.get("retriever_config_sha256") != sha256(FROZEN_RAG_CONFIG)
        or v2_5.get("holdout_status") != "untouched"
        or v2_5.get("qa_or_retrieval_changes") is not False
        or v2_5.get("generation") != v2_4.get("generation")
        or any(v2_5.get(field) != value for field, value in expected_v2_5_parents.items())
    ):
        raise ValueError("GPT v2.5 config is not bound to the measured v2.4 evidence")
    v2_5_present = (GENERATOR_V2_5_OUTPUTS.is_file(), GENERATOR_V2_5_SUMMARY.is_file())
    if v2_5_present == (False, False):
        checks.append(Check(
            "RAG GPT v2.5 generator gate",
            "TBD",
            "supported-scope experiment is frozen; no development output exists",
        ))
    elif v2_5_present != (True, True):
        raise ValueError("GPT v2.5 has only one of its required output/summary artifacts")
    else:
        checks.append(_validate_generator_diagnostic(
            "GPT v2.5",
            GENERATOR_V2_5_CONFIG,
            GENERATOR_V2_5_OUTPUTS,
            GENERATOR_V2_5_SUMMARY,
            JUDGE_MODEL_CATALOG_REFRESH,
        ))
        v2_5_summary = _json(GENERATOR_V2_5_SUMMARY)
        v2_5_candidate = (
            v2_5_summary.get("diagnostic", {})
            .get("candidates", {})
            .get("openai/gpt-oss-20b", {})
        )
        checks.append(Check(
            "RAG GPT v2.5 generator gate",
            "PASS" if v2_5_candidate.get("ready_for_paid_judging") is True else "TBD",
            "10/10, 3/3, and 13/13 gate passed"
            if v2_5_candidate.get("ready_for_paid_judging") is True
            else "measured development run did not open paid judging",
        ))
        if v2_5_candidate.get("ready_for_paid_judging") is True:
            checks.extend(_validate_frozen_judge_config(
                label="GPT v2.5",
                generator_config_path=GENERATOR_V2_5_CONFIG,
                generator_outputs_path=GENERATOR_V2_5_OUTPUTS,
                generator_summary_path=GENERATOR_V2_5_SUMMARY,
                judge_config_path=GENERATOR_V2_5_JUDGE_CONFIG,
                judged_outputs_path=GENERATOR_V2_5_JUDGED_OUTPUTS,
                judge_summary_path=GENERATOR_V2_5_JUDGE_SUMMARY,
                catalog_path=JUDGE_MODEL_CATALOG_REFRESH,
                worksheet_path=GENERATOR_V2_5_JUDGE_WORKSHEET,
                report_path=GENERATOR_V2_5_JUDGE_REPORT,
            ))
    return checks


def _validate_frozen_judge_config(
    *,
    label: str = "GPT v2.4",
    generator_config_path: Path | None = None,
    generator_outputs_path: Path | None = None,
    generator_summary_path: Path | None = None,
    judge_config_path: Path | None = None,
    judged_outputs_path: Path | None = None,
    judge_summary_path: Path | None = None,
    catalog_path: Path | None = None,
    worksheet_path: Path | None = None,
    report_path: Path | None = None,
) -> list[Check]:
    """Recompute and verify the exact judge-only experiment without network calls."""

    # Local aliases keep the historical implementation readable while making
    # every artifact path explicit for later versioned experiments.
    GENERATOR_V2_4_CONFIG = generator_config_path or globals()["GENERATOR_V2_4_CONFIG"]
    GENERATOR_V2_4_OUTPUTS = generator_outputs_path or globals()["GENERATOR_V2_4_OUTPUTS"]
    GENERATOR_V2_4_SUMMARY = generator_summary_path or globals()["GENERATOR_V2_4_SUMMARY"]
    GENERATOR_V2_4_JUDGE_CONFIG = judge_config_path or globals()["GENERATOR_V2_4_JUDGE_CONFIG"]
    GENERATOR_V2_4_JUDGED_OUTPUTS = judged_outputs_path or globals()["GENERATOR_V2_4_JUDGED_OUTPUTS"]
    GENERATOR_V2_4_JUDGE_SUMMARY = judge_summary_path or globals()["GENERATOR_V2_4_JUDGE_SUMMARY"]
    JUDGE_MODEL_CATALOG_REFRESH = catalog_path or globals()["JUDGE_MODEL_CATALOG_REFRESH"]
    GENERATOR_V2_4_JUDGE_WORKSHEET = worksheet_path or globals()["GENERATOR_V2_4_JUDGE_WORKSHEET"]
    GENERATOR_V2_4_JUDGE_REPORT = report_path or globals()["GENERATOR_V2_4_JUDGE_REPORT"]

    if not GENERATOR_V2_4_JUDGE_CONFIG.is_file():
        return [Check(
            f"RAG {label} judge configuration",
            "TBD",
            "generator gate passed, but no frozen judge-only configuration exists",
        )]
    judge_config = _json(GENERATOR_V2_4_JUDGE_CONFIG)
    catalog = _json(JUDGE_MODEL_CATALOG_REFRESH)
    hashes = {
        "qa_sha256": sha256(QA),
        "contexts_sha256": sha256(RAG_DEVELOPMENT_CONTEXTS),
        "model_catalog_sha256": sha256(JUDGE_MODEL_CATALOG_REFRESH),
        "generator_config_sha256": sha256(GENERATOR_V2_4_CONFIG),
        "generator_outputs_sha256": sha256(GENERATOR_V2_4_OUTPUTS),
        "generator_summary_sha256": sha256(GENERATOR_V2_4_SUMMARY),
    }
    settings = validate_judge_config(
        judge_config,
        hashes=hashes,
        outputs_path=GENERATOR_V2_4_JUDGED_OUTPUTS,
        result_path=GENERATOR_V2_4_JUDGE_SUMMARY,
        catalog=catalog,
    )

    qa_packet = _json(QA)
    generator_config = _json(GENERATOR_V2_4_CONFIG)
    generator_outputs = _json(GENERATOR_V2_4_OUTPUTS)
    generator_summary = _json(GENERATOR_V2_4_SUMMARY)
    cases = validate_qa(qa_packet)
    models = generator_config.get("generator_candidates")
    if not isinstance(models, list) or len(models) != 1 or not isinstance(models[0], str):
        raise ValueError(f"{label} judge gate requires exactly one frozen generator")
    contexts = contexts_from(
        _json(RAG_DEVELOPMENT_CONTEXTS),
        cases,
        qa_hash=hashes["qa_sha256"],
        config_hash=generator_config.get(
            "retriever_config_sha256", hashes["generator_config_sha256"]
        ),
    )
    grouped = offline_rows(
        generator_outputs,
        cases,
        contexts,
        hashes["generator_config_sha256"],
        hashes["contexts_sha256"],
        (models[0],),
    )
    validate_generator_gate(
        generator_summary,
        model=models[0],
        generator_config_hash=hashes["generator_config_sha256"],
        generator_outputs_hash=hashes["generator_outputs_sha256"],
        qa_hash=hashes["qa_sha256"],
        contexts_hash=hashes["contexts_sha256"],
    )
    expected_estimate = estimate_judge_cost(
        cases,
        contexts,
        grouped,
        model=settings["model"],
        max_tokens=settings["max_tokens"],
        prompt_version=settings["prompt_version"],
        catalog=catalog,
    )
    if judge_config.get("cost_estimate") != expected_estimate:
        raise ValueError(f"{label} judge cost estimate does not match frozen evidence")
    if expected_estimate["estimated_max_cost_usd"] > settings["hard_cost_cap_usd"]:
        raise ValueError(f"{label} judge estimate exceeds its frozen hard cost cap")
    checks = [Check(
        f"RAG {label} judge configuration",
        "PASS",
        f"{expected_estimate['judge_calls']} judge calls, zero generator calls; "
        f"maximum ${expected_estimate['estimated_max_cost_usd']:.6f} under "
        f"${settings['hard_cost_cap_usd']:.2f} cap; holdout untouched",
        True,
    )]

    present = (
        GENERATOR_V2_4_JUDGED_OUTPUTS.is_file(),
        GENERATOR_V2_4_JUDGE_SUMMARY.is_file(),
    )
    if present == (False, False):
        checks.append(Check(
            f"RAG {label} judge evidence",
            "TBD",
            "judge-only configuration is valid; no paid judge output exists",
        ))
        return checks
    if present != (True, True):
        raise ValueError(f"{label} has only one of its required judge artifacts")

    judge_config_hash = sha256(GENERATOR_V2_4_JUDGE_CONFIG)
    judged_outputs_hash = sha256(GENERATOR_V2_4_JUDGED_OUTPUTS)
    judged_grouped = offline_judged_rows(
        _json(GENERATOR_V2_4_JUDGED_OUTPUTS),
        grouped,
        contexts,
        judge_config_hash=judge_config_hash,
        generator_outputs_hash=hashes["generator_outputs_sha256"],
        judge_prompt_version=settings["prompt_version"],
    )
    expected_selection = select_winner(judged_grouped, len(cases))
    judge_summary = _json(GENERATOR_V2_4_JUDGE_SUMMARY)
    if (
        any(judge_summary.get(field) != value for field, value in hashes.items())
        or judge_summary.get("judge_config_sha256") != judge_config_hash
        or judge_summary.get("judged_outputs_sha256") != judged_outputs_hash
        or judge_summary.get("live_calls") is not True
        or not isinstance(judge_summary.get("approved_max_cost_usd"), (int, float))
        or isinstance(judge_summary.get("approved_max_cost_usd"), bool)
        or judge_summary["approved_max_cost_usd"] < expected_estimate["estimated_max_cost_usd"]
        or judge_summary["approved_max_cost_usd"] > settings["hard_cost_cap_usd"]
        or judge_summary.get("cost_estimate") != expected_estimate
        or judge_summary.get("actual_judge_usage") != judge_usage(judged_grouped)
        or judge_summary.get("selection") != expected_selection
        or judge_summary.get("ready_for_owner_validation") is not True
        or judge_summary.get("holdout_status") != "untouched"
    ):
        raise ValueError(f"{label} judge summary does not replay from frozen evidence")
    candidate = expected_selection.get("candidates", {}).get(models[0], {})
    judged_rows = judged_grouped[models[0]]
    answered_rows = [
        row for row in judged_rows
        if row.get("answer", {}).get("status") == "answered"
    ]
    answered_faithfulness = (
        sum(row.get("judge", {}).get("faithful") is True for row in answered_rows)
        / len(answered_rows)
    )
    checks.append(Check(
        f"RAG {label} judge evidence",
        "PASS",
        f"13 verdicts replay; all-row faithfulness={candidate.get('faithfulness'):.3f}, "
        f"answered-only faithfulness={answered_faithfulness:.3f}, "
        f"relevancy={candidate.get('relevancy'):.3f}, "
        f"citation correctness={candidate.get('citation_correctness'):.3f}, "
        f"correct refusal={candidate.get('correct_refusal'):.3f}; owner validation pending",
        True,
    ))

    if not GENERATOR_V2_4_JUDGE_WORKSHEET.is_file():
        checks.append(Check(
            f"RAG {label} owner worksheet",
            "TBD",
            "judge evidence exists, but no blind owner worksheet is frozen",
        ))
        return checks
    worksheet_packet = _json(GENERATOR_V2_4_JUDGE_WORKSHEET)
    cases_by_id, contexts_by_id = judge_review_material(
        qa_packet, _json(RAG_DEVELOPMENT_CONTEXTS)
    )
    expected_packet = expected_judge_worksheet(
        _json(GENERATOR_V2_4_JUDGED_OUTPUTS)["outputs"],
        cases_by_id,
        contexts_by_id,
    )
    if set(worksheet_packet) != {
        "version",
        "purpose",
        "rubric",
        "sample",
        "source_outputs_sha256",
        "qa_sha256",
        "contexts_sha256",
    }:
        raise ValueError(f"{label} owner worksheet leaks or adds an unexpected root field")
    if (
        worksheet_packet.get("source_outputs_sha256") != judged_outputs_hash
        or worksheet_packet.get("qa_sha256") != hashes["qa_sha256"]
        or worksheet_packet.get("contexts_sha256") != hashes["contexts_sha256"]
        or any(
            worksheet_packet.get(field) != expected_packet.get(field)
            for field in ("version", "purpose", "rubric")
        )
    ):
        raise ValueError(f"{label} owner worksheet is not bound to frozen evidence")
    sample = worksheet_packet.get("sample")
    expected_sample = {
        item["sample_id"]: item for item in expected_packet["sample"]
    }
    if not isinstance(sample, list) or len(sample) != 10:
        raise ValueError(f"{label} owner worksheet must contain ten outputs")
    sample_ids = [item.get("sample_id") for item in sample if isinstance(item, dict)]
    if (
        len(sample_ids) != len(sample)
        or not all(isinstance(sample_id, str) for sample_id in sample_ids)
        or len(set(sample_ids)) != len(sample_ids)
        or set(sample_ids) != set(expected_sample)
    ):
        raise ValueError(f"{label} owner worksheet must cover each sampled output exactly once")
    label_states: list[str] = []
    for item in sample:
        if not isinstance(item, dict) or item.get("sample_id") not in expected_sample:
            raise ValueError(f"{label} owner worksheet contains an unknown output")
        if any(field in item for field in ("judge", "acceptable_answer", "answerability")):
            raise ValueError(f"{label} owner worksheet leaks a judge or oracle label")
        expected_item = expected_sample[item["sample_id"]]
        if set(item) != set(expected_item):
            raise ValueError(f"{label} owner worksheet leaks or adds an unexpected field")
        if any(
            item.get(field) != value
            for field, value in expected_item.items()
            if field != "owner_label"
        ):
            raise ValueError(f"{label} owner worksheet evidence was modified")
        owner_label = item.get("owner_label")
        if (
            not isinstance(owner_label, dict)
            or set(owner_label) != {"reviewer", "faithful", "relevant", "citations_correct", "refusal_correct"}
            or not isinstance(owner_label.get("reviewer"), str)
        ):
            raise ValueError(f"{label} owner worksheet has a malformed owner label")
        values = [owner_label.get(name) for name in ("faithful", "relevant", "citations_correct", "refusal_correct")]
        is_refusal = item.get("answer", {}).get("status") == "insufficient_evidence"
        complete_values = (
            isinstance(owner_label.get("relevant"), bool)
            and isinstance(owner_label.get("refusal_correct"), bool)
            and (
                owner_label.get("faithful") is None and owner_label.get("citations_correct") is None
                if is_refusal
                else isinstance(owner_label.get("faithful"), bool)
                and isinstance(owner_label.get("citations_correct"), bool)
            )
        )
        label_states.append(
            "empty"
            if not owner_label["reviewer"].strip() and all(value is None for value in values)
            else "complete"
            if owner_label["reviewer"].strip() and complete_values
            else "partial"
        )
    if "partial" in label_states or len(set(label_states)) != 1:
        raise ValueError(f"{label} owner worksheet is partially labeled")
    state = label_states[0]
    checks.append(Check(
        f"RAG {label} owner worksheet",
        "PASS",
        "10 blind, evidence-bound outputs; oracle answers, answerability targets, and Claude verdicts absent; "
        + ("owner labels pending" if state == "empty" else "owner labels complete"),
        True,
    ))

    if state == "complete":
        if not GENERATOR_V2_4_JUDGE_REPORT.is_file():
            checks.append(Check(
                f"RAG {label} owner-judge agreement",
                "TBD",
                "owner labels are complete; validation report has not been generated",
            ))
            return checks
        expected_report = validate_judge_labels(
            worksheet_packet,
            _json(GENERATOR_V2_4_JUDGED_OUTPUTS)["outputs"],
            cases_by_id,
            contexts_by_id,
        )
        expected_report["worksheet_sha256"] = sha256(GENERATOR_V2_4_JUDGE_WORKSHEET)
        expected_report["source_outputs_sha256"] = judged_outputs_hash
        if _json(GENERATOR_V2_4_JUDGE_REPORT) != expected_report:
            raise ValueError(f"{label} owner-judge report does not replay from labels")
        checks.append(Check(
            f"RAG {label} owner-judge agreement",
            "PASS" if expected_report.get("passes") is True else "TBD",
            "validated blind labels pass" if expected_report.get("passes") is True else "blind labels do not pass the frozen agreement gate",
            expected_report.get("passes") is True,
        ))
    return checks


def _validate_rag_holdout() -> list[Check]:
    """Replay optional accepted-selection and holdout artifacts without network calls."""

    downstream = (
        RAG_HOLDOUT_CONTEXTS,
        RAG_HOLDOUT_OUTPUTS,
        RAG_HOLDOUT_SUMMARY,
        FINAL_GENERATOR_CONFIG,
    )
    if not ACCEPTED_GENERATOR_V2_5.is_file():
        if any(path.exists() for path in downstream):
            raise ValueError("holdout artifacts exist without an accepted generator selection")
        return [Check(
            "RAG accepted generator and QA holdout",
            "TBD",
            "blind owner validation, accepted selection, and seven-case holdout are pending",
        )]
    required_selection_inputs = (
        QA,
        FROZEN_RAG_CONFIG,
        GENERATOR_V2_5_CONFIG,
        GENERATOR_V2_5_OUTPUTS,
        GENERATOR_V2_5_SUMMARY,
        GENERATOR_V2_5_JUDGE_CONFIG,
        GENERATOR_V2_5_JUDGED_OUTPUTS,
        GENERATOR_V2_5_JUDGE_SUMMARY,
        GENERATOR_V2_5_JUDGE_WORKSHEET,
        GENERATOR_V2_5_JUDGE_REPORT,
    )
    if any(not path.is_file() for path in required_selection_inputs):
        raise ValueError("accepted generator exists without its complete source evidence")
    owner_report = _json(GENERATOR_V2_5_JUDGE_REPORT)
    expected_selection = build_selection(
        qa_hash=sha256(QA),
        retriever_config_hash=sha256(FROZEN_RAG_CONFIG),
        generator_config_hash=sha256(GENERATOR_V2_5_CONFIG),
        generator_outputs_hash=sha256(GENERATOR_V2_5_OUTPUTS),
        generator_summary_hash=sha256(GENERATOR_V2_5_SUMMARY),
        judge_config_hash=sha256(GENERATOR_V2_5_JUDGE_CONFIG),
        judge_outputs_hash=sha256(GENERATOR_V2_5_JUDGED_OUTPUTS),
        judge_summary_hash=sha256(GENERATOR_V2_5_JUDGE_SUMMARY),
        worksheet_hash=sha256(GENERATOR_V2_5_JUDGE_WORKSHEET),
        report_hash=sha256(GENERATOR_V2_5_JUDGE_REPORT),
        generator_config=_json(GENERATOR_V2_5_CONFIG),
        generator_summary=_json(GENERATOR_V2_5_SUMMARY),
        judge_config=_json(GENERATOR_V2_5_JUDGE_CONFIG),
        judge_summary=_json(GENERATOR_V2_5_JUDGE_SUMMARY),
        owner_report=owner_report,
    )
    accepted_selection = _json(ACCEPTED_GENERATOR_V2_5)
    if accepted_selection != expected_selection:
        raise ValueError("accepted generator selection does not replay from development evidence")
    checks = [Check(
        "RAG accepted generator selection",
        "PASS",
        "v2.5 10/3/13, judge-v2, and blind owner agreement hashes replay",
        True,
    )]
    if not RAG_HOLDOUT_CONTEXTS.is_file():
        if any(path.exists() for path in (RAG_HOLDOUT_OUTPUTS, RAG_HOLDOUT_SUMMARY, FINAL_GENERATOR_CONFIG)):
            raise ValueError("holdout outputs exist without frozen holdout contexts")
        checks.append(Check(
            "RAG seven-case QA holdout",
            "TBD",
            "accepted selection exists; one-shot holdout contexts have not been exported",
        ))
        return checks

    qa_packet = _json(QA)
    cases = holdout_cases(qa_packet)
    selection_hash = sha256(ACCEPTED_GENERATOR_V2_5)
    retriever_config_hash = sha256(FROZEN_RAG_CONFIG)
    qa_hash = sha256(QA)
    context_packet = _json(RAG_HOLDOUT_CONTEXTS)
    context_fields = {
        "schema_version",
        "qa_sha256",
        "retriever_config_sha256",
        "accepted_selection_sha256",
        "selection_scope",
        "embedding_usage",
        "cost_estimate_usd",
        "approved_max_cost_usd",
        "contexts",
    }
    if set(context_packet) != context_fields or context_packet.get("schema_version") != 2:
        raise ValueError("holdout context packet has unexpected fields")
    validate_context_provenance(
        context_packet,
        retriever_config_hash,
        qa_hash=qa_hash,
        selection_hash=selection_hash,
    )
    context_estimate = embedding_cost_estimate(cases)
    approved_embedding_cost = context_packet.get("approved_max_cost_usd")
    if (
        context_packet.get("cost_estimate_usd") != context_estimate
        or isinstance(approved_embedding_cost, bool)
        or not isinstance(approved_embedding_cost, (int, float))
        or not math.isfinite(approved_embedding_cost)
        or approved_embedding_cost < context_estimate
        or approved_embedding_cost > EMBEDDING_HARD_CAP_USD
        or not isinstance(context_packet.get("embedding_usage"), dict)
    ):
        raise ValueError("holdout context cost or usage evidence does not replay")
    contexts = contexts_from(
        context_packet,
        cases,
        qa_hash=qa_hash,
        config_hash=retriever_config_hash,
    )
    checks.append(Check(
        "RAG holdout contexts",
        "PASS",
        "seven one-shot top-five hybrid context lists replay under the $0.01 embedding cap",
        True,
    ))
    if not RAG_HOLDOUT_OUTPUTS.is_file():
        if RAG_HOLDOUT_SUMMARY.exists() or FINAL_GENERATOR_CONFIG.exists():
            raise ValueError("holdout summary/final config exists without raw outputs")
        checks.append(Check(
            "RAG seven-case QA holdout",
            "TBD",
            "contexts are frozen; generation and judge-v2 holdout calls have not run",
        ))
        return checks
    if not RAG_HOLDOUT_MODEL_CATALOG.is_file():
        raise ValueError("holdout outputs exist without their frozen model catalog")

    catalog = _json(RAG_HOLDOUT_MODEL_CATALOG)
    catalog_hash = sha256(RAG_HOLDOUT_MODEL_CATALOG)
    generator_config = _json(GENERATOR_V2_5_CONFIG)
    judge_config = _json(GENERATOR_V2_5_JUDGE_CONFIG)
    winner, generation, judge_settings, hard_cap = validate_selection_bindings(
        accepted_selection,
        owner_report,
        generator_config,
        judge_config,
        qa_hash=qa_hash,
        retriever_config_hash=retriever_config_hash,
        selection_hash=selection_hash,
        owner_report_hash=sha256(GENERATOR_V2_5_JUDGE_REPORT),
        generator_config_hash=sha256(GENERATOR_V2_5_CONFIG),
        judge_config_hash=sha256(GENERATOR_V2_5_JUDGE_CONFIG),
    )
    catalog_models = validate_model_catalog(catalog)
    if winner not in catalog_models or validate_judge_catalog(catalog) != accepted_selection["judge_model"]:
        raise ValueError("holdout catalog does not contain the accepted generator and judge")
    validate_selected_parameter_support(catalog, [winner], generation)
    cost_estimate = estimate_holdout_cost(
        cases,
        contexts,
        catalog,
        winner,
        accepted_selection["judge_model"],
        generation,
        judge_settings,
    )
    output_packet = _json(RAG_HOLDOUT_OUTPUTS)
    if set(output_packet) != HOLDOUT_OUTPUT_FIELDS or output_packet.get("schema_version") != 2:
        raise ValueError("holdout output packet has unexpected fields")
    expected_output_bindings = {
        "selection_sha256": selection_hash,
        "qa_sha256": qa_hash,
        "retriever_config_sha256": retriever_config_hash,
        "contexts_sha256": sha256(RAG_HOLDOUT_CONTEXTS),
        "model_catalog_sha256": catalog_hash,
        "cost_estimate": cost_estimate,
    }
    if any(output_packet.get(field) != value for field, value in expected_output_bindings.items()):
        raise ValueError("holdout outputs are not bound to their frozen inputs")
    approved_max = output_packet.get("approved_max_cost_usd")
    if (
        isinstance(approved_max, bool)
        or not isinstance(approved_max, (int, float))
        or not math.isfinite(approved_max)
        or approved_max < cost_estimate["estimated_max_cost_usd"]
        or approved_max > hard_cap
    ):
        raise ValueError("holdout approved cost does not cover the estimate within the frozen cap")
    rows = saved_rows(
        output_packet,
        cases,
        contexts,
        winner,
        selection_hash,
        retriever_config_hash,
        sha256(RAG_HOLDOUT_CONTEXTS),
    )
    expected = expected_summary(
        rows=rows,
        qa_hash=qa_hash,
        retriever_config_hash=retriever_config_hash,
        selection_hash=selection_hash,
        owner_report_hash=sha256(GENERATOR_V2_5_JUDGE_REPORT),
        contexts_hash=sha256(RAG_HOLDOUT_CONTEXTS),
        outputs_hash=sha256(RAG_HOLDOUT_OUTPUTS),
        catalog_hash=catalog_hash,
        winner=winner,
        judge_model=accepted_selection["judge_model"],
        cost_estimate=cost_estimate,
        approved_max_cost_usd=float(approved_max),
    )
    if not RAG_HOLDOUT_SUMMARY.is_file():
        if FINAL_GENERATOR_CONFIG.exists():
            raise ValueError("final generator config exists without a replayed holdout summary")
        checks.append(Check(
            "RAG seven-case QA holdout",
            "TBD",
            "raw one-shot outputs exist; run offline --finalize-saved recovery",
        ))
        return checks
    if _json(RAG_HOLDOUT_SUMMARY) != expected:
        raise ValueError("holdout summary does not replay from raw outputs")
    if expected["passes"]:
        if not FINAL_GENERATOR_CONFIG.is_file():
            raise ValueError("passing holdout lacks the frozen final generator configuration")
        expected_final = expected_final_config(expected, summary_hash=sha256(RAG_HOLDOUT_SUMMARY))
        if _json(FINAL_GENERATOR_CONFIG) != expected_final:
            raise ValueError("final generator configuration does not replay from the passing holdout")
    elif FINAL_GENERATOR_CONFIG.exists():
        raise ValueError("failed holdout cannot have a frozen final generator configuration")
    metrics = expected["metrics"]
    checks.append(Check(
        "RAG seven-case QA holdout",
        "PASS",
        f"one-shot evidence replays; accepted={expected['passes']}; "
        f"answered faithfulness={metrics['answered_faithfulness']:.3f}; "
        f"citation correctness={metrics['citation_correctness']:.3f}",
        True,
    ))
    return checks


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
    try:
        checks.append(_validate_service_memory())
    except (OSError, ValueError, KeyError, TypeError) as exc:
        checks.append(Check("service memory benchmark", "FAIL", str(exc), True))
    try:
        checks.append(_validate_cost_projection())
    except (OSError, ValueError, KeyError, TypeError) as exc:
        checks.append(Check("monthly cost projection", "FAIL", str(exc), True))
    try:
        checks.append(_validate_rag_bakeoff())
    except (BakeoffError, OSError, ValueError, KeyError, TypeError) as exc:
        checks.append(Check("RAG development bake-off evidence", "FAIL", str(exc), True))
    try:
        checks.extend(_validate_versioned_generator_evidence())
    except (BakeoffError, OSError, ValueError, KeyError, TypeError) as exc:
        checks.append(Check("RAG GPT generator diagnostics", "FAIL", str(exc), True))
    try:
        checks.extend(_validate_rag_holdout())
    except (BakeoffError, OSError, ValueError, KeyError, TypeError) as exc:
        checks.append(Check("RAG accepted generator and QA holdout", "FAIL", str(exc), True))
    return checks


def _validate_service_memory() -> Check:
    report = _json(SERVICE_MEMORY)
    required = {
        "schema_version",
        "measured_at_utc",
        "platform",
        "python_version",
        "cache_path",
        "cache_sha256",
        "service_sha256",
        "corpus_sha256",
        "startup_ms",
        "rss_before_bytes",
        "rss_after_bytes",
        "rss_delta_bytes",
        "peak_rss_bytes",
        "documents",
        "semantic_available",
        "generation_available",
        "network_calls",
        "scope",
    }
    if set(report) != required or report.get("schema_version") != 1:
        raise ValueError("service-memory artifact has an unexpected schema")
    cache_value = report.get("cache_path")
    if not isinstance(cache_value, str) or not cache_value:
        raise ValueError("service-memory cache path is invalid")
    cache = (ROOT / cache_value).resolve()
    if not cache.is_relative_to(ROOT.resolve()) or not cache.is_file():
        raise ValueError("service-memory cache path escapes or is missing")
    expected_hashes = {
        "cache_sha256": sha256(cache),
        "service_sha256": _source_sha256(ROOT / "src/service.py"),
        "corpus_sha256": sha256(CORPUS),
    }
    if any(report.get(field) != value for field, value in expected_hashes.items()):
        raise ValueError("service-memory artifact hashes do not match the release inputs")
    integers = (
        "rss_before_bytes",
        "rss_after_bytes",
        "rss_delta_bytes",
        "peak_rss_bytes",
        "documents",
        "network_calls",
    )
    if any(
        isinstance(report.get(field), bool) or not isinstance(report.get(field), int)
        for field in integers
    ):
        raise ValueError("service-memory measurements must be integers")
    startup = report.get("startup_ms")
    if (
        isinstance(startup, bool)
        or not isinstance(startup, (int, float))
        or not math.isfinite(float(startup))
        or startup <= 0
        or report["rss_before_bytes"] <= 0
        or report["rss_after_bytes"] <= 0
        or report["peak_rss_bytes"] < report["rss_after_bytes"]
        or report["rss_delta_bytes"]
        != report["rss_after_bytes"] - report["rss_before_bytes"]
        or report["documents"] != 2_000
        or report.get("semantic_available") is not True
        or not isinstance(report.get("generation_available"), bool)
        or report["network_calls"] != 0
    ):
        raise ValueError("service-memory measurements are inconsistent")
    return Check(
        "service memory benchmark",
        "PASS",
        f"cold startup={startup:.3f} ms; RSS after={report['rss_after_bytes']} bytes; "
        f"peak RSS={report['peak_rss_bytes']} bytes; zero provider calls",
        True,
    )


def _validate_cost_projection() -> Check:
    saved = _json(COST_PROJECTION)
    expected = projection_from_paths(
        JUDGE_MODEL_CATALOG_REFRESH,
        EMBEDDING_USAGE,
        QUERY_EMBEDDING_USAGE,
    )
    if saved != expected:
        raise ValueError("cost projection does not replay from frozen prices and usage")
    scenarios = saved.get("scenarios")
    if not isinstance(scenarios, list) or len(scenarios) != 4:
        raise ValueError("cost projection must contain four user-scale scenarios")
    return Check(
        "monthly cost projection",
        "PASS",
        "100/1K/10K/100K variable AI costs replay from the frozen catalog and query-token ledger; Railway remains a lower bound",
        True,
    )


def _live_eval() -> list[Check]:
    # Never guess provider pricing or send a request from a release check.
    checks = [Check("live-eval cost estimate", "TBD", "first development spend is recorded; any new generator or holdout run requires a fresh model catalog, estimate, and explicit approval")]
    if not os.environ.get("OPENROUTER_API_KEY"):
        checks.append(Check("live-eval credentials", "TBD", "OPENROUTER_API_KEY is not set; no network call attempted"))
    else:
        checks.append(Check("live-eval pipeline", "TBD", "credential detected, but owner judge validation and an accepted generator are pending; no paid call attempted"))
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

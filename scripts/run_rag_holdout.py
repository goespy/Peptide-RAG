#!/usr/bin/env python3
"""Run the one-shot Section 5 holdout only after generator selection is frozen."""
from __future__ import annotations

import argparse, json, os, sys, time
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.run_rag_bakeoff import (BakeoffError, contexts_from, hash_file, load_json, structurally_valid_answer, validate_config, validate_live_cost, write_json_atomic)  # noqa: E402
from src.generation import GroundedAnswerClient  # noqa: E402
from src.judge import AnswerJudge  # noqa: E402
from src.rag_metrics import candidate_summary  # noqa: E402
from src.retrieval import RetrievedChunk  # noqa: E402

class HoldoutError(BakeoffError): pass

def holdout_cases(packet: dict[str, Any]) -> list[dict[str, Any]]:
    questions = packet.get("questions")
    if packet.get("status") != "approved" or not isinstance(questions, list): raise HoldoutError("holdout requires approved data/qa.json")
    saved = []
    for item in questions:
        if not isinstance(item, dict) or item.get("split") != "holdout": continue
        review = item.get("human_review")
        if not isinstance(item.get("id"), str) or not isinstance(item.get("question"), str) or not isinstance(item.get("answerable"), bool) or not isinstance(review, dict) or review.get("approved") is not True or review.get("decision") != "approve" or not isinstance(review.get("reviewer"), str) or not review["reviewer"].strip(): raise HoldoutError("every holdout question requires frozen owner approval")
        if item["answerable"] and (not item.get("relevant_pmids") or not item.get("supporting_spans")): raise HoldoutError("answerable holdout question lacks frozen support")
        if not item["answerable"] and (item.get("relevant_pmids") or item.get("supporting_spans")): raise HoldoutError("unanswerable holdout question cannot contain support")
        saved.append({"id": item["id"], "question": item["question"], "answerability": "answerable" if item["answerable"] else "unanswerable"})
    if len(saved) != 7 or sum(item["answerability"] == "answerable" for item in saved) != 5 or sum(item["answerability"] == "unanswerable" for item in saved) != 2: raise HoldoutError("holdout must be the fixed seven questions (five answerable, two unanswerable)")
    return sorted(saved, key=lambda item: item["id"])

def winner_from(bakeoff: dict[str, Any]) -> str:
    winner = bakeoff.get("selection", {}).get("winner") if isinstance(bakeoff.get("selection"), dict) else None
    if not isinstance(winner, str) or not winner.strip(): raise HoldoutError("holdout requires a frozen bake-off summary winner")
    return winner

def validate_context_provenance(packet: dict[str, Any], config_hash: str) -> None:
    actual = packet.get("retriever_config_sha256", packet.get("config_sha256"))
    if actual != config_hash: raise HoldoutError("holdout contexts are not bound to the frozen retriever configuration")

def saved_rows(outputs: dict[str, Any], cases: list[dict[str, Any]], contexts: dict[str, tuple[RetrievedChunk, ...]], winner: str, config_hash: str, context_hash: str) -> list[dict[str, Any]]:
    rows = outputs.get("outputs")
    if not isinstance(rows, list) or len(rows) != len(cases): raise HoldoutError("holdout output must contain exactly seven records")
    expected = {item["id"]: item for item in cases}; result = []
    for row in rows:
        if not isinstance(row, dict) or row.get("model") != winner or row.get("qa_id") not in expected or row.get("config_sha256") != config_hash or row.get("contexts_sha256") != context_hash: raise HoldoutError("holdout output provenance does not match the frozen winner/config/contexts")
        copied = dict(row)
        copied["answerability"] = expected[copied["qa_id"]]["answerability"]
        copied["structurally_valid"] = structurally_valid_answer(copied.get("answer"), contexts[copied["qa_id"]])
        result.append(copied)
    if {row["qa_id"] for row in result} != set(expected): raise HoldoutError("holdout output must contain each frozen question once")
    return result

def run_live(cases: list[dict[str, Any]], contexts: dict[str, tuple[RetrievedChunk, ...]], winner: str, judge_model: str, config_hash: str, context_hash: str, api_key: str) -> list[dict[str, Any]]:
    generator, judge, result = GroundedAnswerClient(api_key=api_key, model=winner), AnswerJudge(api_key=api_key, model=judge_model), []
    for case in cases:
        started = time.perf_counter(); answer = generator.answer(case["question"], contexts[case["id"]]); latency = (time.perf_counter() - started) * 1000
        verdict = judge.judge(case["question"], answer, contexts[case["id"]], expected_answerable=case["answerability"] == "answerable")
        judge_payload = None if verdict is None else {"claims": [{"text": claim.text, "supported": claim.supported, "citation_ids": list(claim.citation_ids)} for claim in verdict.claims], **{key: getattr(verdict, key) for key in ("faithful", "relevant", "citations_correct", "refusal_correct")}}
        usage = dict(generator.last_metadata)
        judge_usage = dict(judge.last_metadata)
        usage.update({"latency_ms": latency, "generator_usage": dict(generator.last_metadata), "judge_usage": judge_usage, "token_cost_status": "provider_reported" if usage.get("input_tokens") is not None and usage.get("cost_usd") is not None else "unknown_not_exposed_by_provider"})
        answer_payload = {"status": answer.status, "text": answer.text, "citations": [item.__dict__ for item in answer.citations]}
        result.append({"model": winner, "qa_id": case["id"], "answerability": case["answerability"], "config_sha256": config_hash, "contexts_sha256": context_hash, "answer": answer_payload, "judge": judge_payload, "structurally_valid": structurally_valid_answer(answer_payload, contexts[case["id"]]), "metadata": usage})
    return result

def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qa", type=Path, default=ROOT / "data/qa.json"); parser.add_argument("--config", type=Path, default=ROOT / "artifacts/section5/frozen_config.json"); parser.add_argument("--bakeoff", type=Path, default=ROOT / "data/rag_bakeoff_summary.json"); parser.add_argument("--judge-validation", type=Path, default=ROOT / "data/judge_validation_report.json"); parser.add_argument("--contexts", type=Path, default=ROOT / "data/rag_holdout_contexts.json"); parser.add_argument("--outputs", type=Path, default=ROOT / "data/rag_holdout_outputs.json"); parser.add_argument("--result", type=Path, default=ROOT / "data/rag_holdout_summary.json"); parser.add_argument("--frozen-generator-config", type=Path, default=ROOT / "artifacts/section5/generator_config.json")
    parser.add_argument("--live", action="store_true"); parser.add_argument("--max-cost-usd", type=float); parser.add_argument("--confirm-cost", action="store_true"); parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    try:
        for target in (args.result, args.frozen_generator_config):
            if target.exists() and not args.overwrite:
                raise HoldoutError(f"refusing to overwrite existing file: {target}; pass --overwrite")
        if args.live and args.outputs.exists() and not args.overwrite:
            raise HoldoutError(f"refusing to overwrite existing file: {args.outputs}; pass --overwrite")
        qa, config, bakeoff, judge_report, context_packet = load_json(args.qa), load_json(args.config), load_json(args.bakeoff), load_json(args.judge_validation), load_json(args.contexts)
        cases = holdout_cases(qa); validate_config(config); winner = winner_from(bakeoff)
        judge_model = bakeoff.get("judge_model")
        if not isinstance(judge_model, str) or not judge_model.strip():
            raise HoldoutError("holdout requires the bake-off's validated judge model ID")
        if judge_report.get("passes") is not True: raise HoldoutError("holdout requires a passing judge-validation artifact")
        qa_hash, config_hash, context_hash = hash_file(args.qa), hash_file(args.config), hash_file(args.contexts)
        if bakeoff.get("qa_sha256") != qa_hash or bakeoff.get("config_sha256") != config_hash:
            raise HoldoutError("bake-off winner is not bound to the approved QA and frozen RAG configuration")
        if judge_report.get("source_outputs_sha256") != bakeoff.get("outputs_sha256"):
            raise HoldoutError("judge validation is not bound to the winning bake-off outputs")
        validate_context_provenance(context_packet, config_hash); contexts = contexts_from(context_packet, cases, qa_hash=qa_hash, config_hash=config_hash)
        if args.live:
            print(validate_live_cost(args.max_cost_usd))
            if not args.confirm_cost: raise HoldoutError("--live requires --confirm-cost after reviewing the maximum-cost status")
            key = os.environ.get("OPENROUTER_API_KEY")
            if not key: raise HoldoutError("--live requires OPENROUTER_API_KEY; no provider call was made")
            rows = run_live(cases, contexts, winner, judge_model, config_hash, context_hash, key); write_json_atomic(args.outputs, {"outputs": rows}, overwrite=args.overwrite)
        else: rows = saved_rows(load_json(args.outputs), cases, contexts, winner, config_hash, context_hash)
        metrics = candidate_summary(rows)
        if metrics["outputs"] != 7 or metrics["structural_validity"] != 1.0 or metrics["judged_outputs"] != 7 or any(metrics[key] is None for key in ("faithfulness", "correct_refusal", "relevancy", "citation_correctness")): raise HoldoutError("holdout is incomplete, structurally invalid, or not fully judged; generator configuration remains unfrozen")
        summary = {"qa_sha256": qa_hash, "config_sha256": config_hash, "bakeoff_sha256": hash_file(args.bakeoff), "judge_validation_sha256": hash_file(args.judge_validation), "contexts_sha256": context_hash, "outputs_sha256": hash_file(args.outputs), "winner": winner, "judge_model": judge_model, "live_calls": args.live, "metrics": metrics}
        write_json_atomic(args.result, summary, overwrite=args.overwrite)
        write_json_atomic(args.frozen_generator_config, {"status": "frozen_after_complete_holdout", "winner": winner, "qa_sha256": summary["qa_sha256"], "rag_config_sha256": config_hash, "bakeoff_sha256": summary["bakeoff_sha256"], "judge_validation_sha256": summary["judge_validation_sha256"], "holdout_contexts_sha256": context_hash, "holdout_outputs_sha256": summary["outputs_sha256"], "holdout_summary_sha256": hash_file(args.result)}, overwrite=args.overwrite)
    except (BakeoffError, OSError, TypeError) as exc: print(f"Error: {exc}", file=sys.stderr); return 1
    print(json.dumps(summary, sort_keys=True)); return 0
if __name__ == "__main__": raise SystemExit(main())

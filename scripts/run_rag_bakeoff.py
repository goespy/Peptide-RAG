#!/usr/bin/env python3
"""Run or recalculate the Section 5 generator bake-off from immutable artifacts."""
from __future__ import annotations

import argparse, hashlib, json, math, os, sys, tempfile, time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
MODELS = ("qwen/qwen3.7-flash", "openai/gpt-oss-20b", "google/gemma-3-12b-it")
MODEL_FAMILIES = ("qwen", "openai", "google")

sys.path.insert(0, str(ROOT))
from src.generation import AnswerResult, Citation, GroundedAnswerClient, validate_answer_result  # noqa: E402
from src.judge import AnswerJudge  # noqa: E402
from src.chunks import Chunk  # noqa: E402
from src.retrieval import RetrievedChunk  # noqa: E402
from src.rag_metrics import answer_is_structurally_valid, select_winner  # noqa: E402


class BakeoffError(RuntimeError): pass

def load_json(path: Path) -> dict[str, Any]:
    try: value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc: raise BakeoffError(f"cannot read {path}: {exc}") from exc
    if not isinstance(value, dict): raise BakeoffError(f"{path} must be a JSON object")
    return value

def hash_file(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest().upper()

def write_json_atomic(path: Path, payload: dict[str, Any], *, overwrite: bool) -> None:
    if path.exists() and not overwrite: raise BakeoffError(f"refusing to overwrite existing artifact: {path}; pass --overwrite")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, sort_keys=True, indent=2); handle.write("\n"); handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try: os.unlink(temporary)
        except FileNotFoundError: pass
        raise

def validate_live_cost(max_cost_usd: float | None) -> str:
    if max_cost_usd is None or not isinstance(max_cost_usd, (int, float)) or not math.isfinite(max_cost_usd) or max_cost_usd <= 0:
        raise BakeoffError("--live requires a positive --max-cost-usd bound because provider pricing is not available locally")
    status = f"Live maximum-cost status: user-supplied bound ${max_cost_usd:.2f}; provider prices unavailable locally."
    return status

def validate_qa(packet: dict[str, Any]) -> list[dict[str, Any]]:
    questions = packet.get("questions")
    if packet.get("status") != "approved" or not isinstance(questions, list): raise BakeoffError("QA set is not approved; run only after project-owner approval is frozen in data/qa.json")
    development = []
    for item in questions:
        if not isinstance(item, dict) or item.get("split") != "development" or not isinstance(item.get("id"), str) or not isinstance(item.get("question"), str) or not isinstance(item.get("answerable"), bool): continue
        review = item.get("human_review")
        if not isinstance(review, dict) or review.get("approved") is not True or review.get("decision") != "approve" or not isinstance(review.get("reviewer"), str) or not review["reviewer"].strip(): raise BakeoffError("each development QA question requires a recorded owner approval")
        if item["answerable"]:
            spans, pmids = item.get("supporting_spans"), item.get("relevant_pmids")
            if not isinstance(spans, list) or not spans or not isinstance(pmids, list) or not pmids:
                raise BakeoffError("answerable QA questions require frozen relevant_pmids and supporting_spans")
        elif item.get("relevant_pmids") or item.get("supporting_spans"):
            raise BakeoffError("unanswerable QA questions cannot contain support evidence")
        development.append({"id": item["id"], "question": item["question"], "answerability": "answerable" if item["answerable"] else "unanswerable"})
    if len(development) != 13 or sum(case["answerability"] == "answerable" for case in development) != 10 or sum(case["answerability"] == "unanswerable" for case in development) != 3: raise BakeoffError("approved QA set must contain the fixed 13-question (10 answerable/3 unanswerable) development split")
    return sorted(development, key=lambda case: case["id"])

def validate_config(config: dict[str, Any]) -> None:
    if config.get("status") not in {"frozen", "selected_and_frozen", "frozen_before_generator_bakeoff"} or config.get("selected") is not True:
        raise BakeoffError("selected RAG configuration is not frozen")
    if not isinstance(config.get("prompt"), str) or not config["prompt"].strip() or not isinstance(config.get("generation"), dict):
        raise BakeoffError("frozen RAG config must record prompt and generation settings")
    if config["generation"].get("temperature") != 0 or config["generation"].get("max_tokens") != 400:
        raise BakeoffError("bake-off requires frozen temperature 0 and a 400-token cap")

def validate_model_catalog(catalog: dict[str, Any], *, max_age_hours: float | None = None) -> tuple[str, ...]:
    models = catalog.get("models")
    if not isinstance(catalog.get("checked_at"), str) or not catalog["checked_at"].strip() or not isinstance(catalog.get("sources"), list) or not catalog["sources"] or any(not isinstance(source, str) or not source.startswith("https://") for source in catalog["sources"]):
        raise BakeoffError("model catalog must record its check time and direct sources")
    if max_age_hours is not None:
        try:
            checked = datetime.fromisoformat(catalog["checked_at"].replace("Z", "+00:00"))
            age_hours = (datetime.now(timezone.utc) - checked.astimezone(timezone.utc)).total_seconds() / 3600
        except ValueError as exc:
            raise BakeoffError("model catalog checked_at is not an ISO-8601 timestamp") from exc
        if age_hours < 0 or age_hours > max_age_hours:
            raise BakeoffError("live bake-off requires model availability and prices checked within the last 24 hours")
    if not isinstance(models, list) or len(models) != 3:
        raise BakeoffError("model catalog must select exactly three candidates")
    selected: list[str] = []
    for family in MODEL_FAMILIES:
        matches = [item for item in models if isinstance(item, dict) and item.get("family") == family]
        if len(matches) != 1:
            raise BakeoffError(f"model catalog must select one {family} candidate")
        item = matches[0]
        if (
            not isinstance(item.get("id"), str) or not item["id"].strip()
            or item.get("available") is not True
            or item.get("structured_json") is not True
            or isinstance(item.get("context_length"), bool) or not isinstance(item.get("context_length"), int) or item["context_length"] < 32768
            or isinstance(item.get("input_cost_per_million"), bool) or not isinstance(item.get("input_cost_per_million"), (int, float)) or item["input_cost_per_million"] < 0 or item["input_cost_per_million"] > 0.10
            or isinstance(item.get("output_cost_per_million"), bool) or not isinstance(item.get("output_cost_per_million"), (int, float)) or item["output_cost_per_million"] < 0 or item["output_cost_per_million"] > 0.50
        ):
            raise BakeoffError(f"selected {family} candidate does not satisfy the pre-registered availability/context/price contract")
        selected.append(item["id"])
    if len(set(selected)) != 3:
        raise BakeoffError("model candidates must be distinct")
    return tuple(selected)

def contexts_from(
    packet: dict[str, Any],
    cases: list[dict[str, Any]],
    *,
    qa_hash: str | None = None,
    config_hash: str | None = None,
) -> dict[str, tuple[RetrievedChunk, ...]]:
    if qa_hash is not None and packet.get("qa_sha256") != qa_hash:
        raise BakeoffError("stored contexts do not match the approved QA artifact")
    packet_config_hash = packet.get("frozen_config_sha256", packet.get("retriever_config_sha256"))
    if config_hash is not None and packet_config_hash != config_hash:
        raise BakeoffError("stored contexts do not match the frozen RAG configuration")
    entries = packet.get("contexts")
    if not isinstance(entries, list): raise BakeoffError("stored contexts artifact needs a contexts list")
    output: dict[str, tuple[RetrievedChunk, ...]] = {}
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("qa_id"), str) or not isinstance(entry.get("chunks"), list): raise BakeoffError("malformed stored context")
        chunks = []
        for value in entry["chunks"][:5]:
            if not isinstance(value, dict): raise BakeoffError("malformed context chunk")
            try: chunk = Chunk(value["chunk_id"], value["pmid"], value["title"], value["text"], int(value["start_char"]), int(value["end_char"]), int(value["token_count"]))
            except (KeyError, TypeError, ValueError) as exc: raise BakeoffError("malformed context chunk") from exc
            chunks.append(RetrievedChunk(chunk, float(value.get("score", 0.0)), "stored"))
        if not chunks: raise BakeoffError(f"{entry['qa_id']} has no stored contexts")
        output[entry["qa_id"]] = tuple(chunks)
    if set(output) != {case["id"] for case in cases}: raise BakeoffError("stored contexts must contain exactly the 13 development cases")
    return output

def _saved_answer(payload: Any) -> AnswerResult | None:
    if not isinstance(payload, dict) or not isinstance(payload.get("citations"), list): return None
    citations = []
    try:
        for item in payload["citations"]:
            citations.append(Citation(item["citation_id"], item["pmid"], item["chunk_id"], item["title"]))
        return AnswerResult(payload["status"], payload["text"], tuple(citations))
    except (KeyError, TypeError): return None

def structurally_valid_answer(payload: Any, contexts: tuple[RetrievedChunk, ...]) -> bool:
    """Apply one identical saved/live structural validator."""
    answer = _saved_answer(payload)
    return answer is not None and answer_is_structurally_valid(payload) and validate_answer_result(answer, contexts)

def offline_rows(outputs: dict[str, Any], cases: list[dict[str, Any]], contexts: dict[str, tuple[RetrievedChunk, ...]], config_hash: str, context_hash: str, models: Sequence[str] = MODELS) -> dict[str, list[dict[str, Any]]]:
    rows = outputs.get("outputs")
    if not isinstance(rows, list): raise BakeoffError("offline artifact needs an outputs list")
    expected = {case["id"]: case for case in cases}; grouped = {model: [] for model in models}
    for row in rows:
        if not isinstance(row, dict) or row.get("model") not in grouped or row.get("qa_id") not in expected: raise BakeoffError("output has unknown model or non-development case")
        if row.get("config_sha256") != config_hash or row.get("contexts_sha256") != context_hash: raise BakeoffError("output was not generated with the selected config and identical stored contexts")
        row = dict(row)
        row["answerability"] = expected[row["qa_id"]]["answerability"]
        row["structurally_valid"] = structurally_valid_answer(row.get("answer"), contexts[row["qa_id"]])
        grouped[row["model"]].append(row)
    for model, model_rows in grouped.items():
        if {row["qa_id"] for row in model_rows} != set(expected) or len(model_rows) != len(expected):
            raise BakeoffError(f"{model} does not contain exactly one output for each development question")
    return grouped

def run_live(cases: list[dict[str, Any]], contexts: dict[str, tuple[RetrievedChunk, ...]], config_hash: str, context_hash: str, api_key: str, models: Sequence[str] = MODELS) -> dict[str, list[dict[str, Any]]]:
    """Explicit paid path: every generator sees the same frozen contexts."""
    grouped = {model: [] for model in models}; judge = AnswerJudge(api_key=api_key)
    for model in models:
        client = GroundedAnswerClient(api_key=api_key, model=model)
        for case in cases:
            started = time.perf_counter(); answer = client.answer(case["question"], contexts[case["id"]]); latency = (time.perf_counter() - started) * 1000
            verdict = judge.judge(case["question"], answer, contexts[case["id"]], expected_answerable=case["answerability"] == "answerable")
            answer_payload = {"status": answer.status, "text": answer.text, "citations": [item.__dict__ for item in answer.citations]}
            judge_payload = None if verdict is None else {"claims": [{"text": claim.text, "supported": claim.supported, "citation_ids": list(claim.citation_ids)} for claim in verdict.claims], **{key: getattr(verdict, key) for key in ("faithful", "relevant", "citations_correct", "refusal_correct")}}
            usage = dict(client.last_metadata)
            judge_usage = dict(judge.last_metadata)
            usage.update({
                "latency_ms": latency,
                "generator_usage": dict(client.last_metadata),
                "judge_usage": judge_usage,
                "token_cost_status": (
                    "provider_reported"
                    if usage.get("input_tokens") is not None and usage.get("cost_usd") is not None
                    else "unknown_not_exposed_by_provider"
                ),
            })
            grouped[model].append({"model": model, "qa_id": case["id"], "answerability": case["answerability"], "config_sha256": config_hash, "contexts_sha256": context_hash, "answer": answer_payload, "judge": judge_payload, "structurally_valid": structurally_valid_answer(answer_payload, contexts[case["id"]]), "metadata": usage})
    return grouped

def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qa", type=Path, default=ROOT / "data/qa.json"); parser.add_argument("--config", type=Path, default=ROOT / "artifacts/section5/frozen_config.json")
    parser.add_argument("--contexts", type=Path, default=ROOT / "data/rag_development_contexts.json"); parser.add_argument("--outputs", type=Path, default=ROOT / "data/rag_bakeoff_outputs.json")
    parser.add_argument("--model-catalog", type=Path, default=ROOT / "data/model_candidates.json")
    parser.add_argument("--result", type=Path, default=ROOT / "data/rag_bakeoff_summary.json"); parser.add_argument("--live", action="store_true")
    parser.add_argument("--max-cost-usd", type=float); parser.add_argument("--confirm-cost", action="store_true"); parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.result.exists() and not args.overwrite:
            raise BakeoffError(f"refusing to overwrite existing file: {args.result}; pass --overwrite")
        if args.live and args.outputs.exists() and not args.overwrite:
            raise BakeoffError(f"refusing to overwrite existing file: {args.outputs}; pass --overwrite")
        qa, config, context_packet, model_catalog = load_json(args.qa), load_json(args.config), load_json(args.contexts), load_json(args.model_catalog)
        models = validate_model_catalog(model_catalog, max_age_hours=24 if args.live else None)
        config_hash, context_hash = hash_file(args.config), hash_file(args.contexts)
        qa_hash = hash_file(args.qa)
        cases = validate_qa(qa); validate_config(config); contexts = contexts_from(context_packet, cases, qa_hash=qa_hash, config_hash=config_hash)
        if args.live:
            print(validate_live_cost(args.max_cost_usd))
            if not args.confirm_cost: raise BakeoffError("--live requires --confirm-cost after reviewing the maximum-cost status")
            api_key = os.environ.get("OPENROUTER_API_KEY")
            if not api_key: raise BakeoffError("--live requires OPENROUTER_API_KEY; no provider call was made")
            grouped = run_live(cases, contexts, config_hash, context_hash, api_key, models)
            write_json_atomic(args.outputs, {"outputs": [row for values in grouped.values() for row in values]}, overwrite=args.overwrite)
        else: grouped = offline_rows(load_json(args.outputs), cases, contexts, config_hash, context_hash, models)
        result = {"qa_sha256": qa_hash, "config_sha256": config_hash, "contexts_sha256": context_hash, "model_catalog_sha256": hash_file(args.model_catalog), "models": list(models), "outputs_sha256": hash_file(args.outputs), "live_calls": args.live, "selection": select_winner(grouped, len(cases))}
        write_json_atomic(args.result, result, overwrite=args.overwrite)
    except (BakeoffError, OSError, TypeError) as exc: print(f"Error: {exc}", file=sys.stderr); return 1
    print(json.dumps(result, sort_keys=True)); return 0
if __name__ == "__main__": raise SystemExit(main())

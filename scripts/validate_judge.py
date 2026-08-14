#!/usr/bin/env python3
"""Create and validate the project-owner worksheet for the RAG judge."""
from __future__ import annotations

import argparse, hashlib, json, os, sys, tempfile
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.rag_metrics import DIMENSIONS, binary_agreement  # noqa: E402

class JudgeValidationError(RuntimeError): pass

def write_atomic(path: Path, payload: dict[str, Any], *, overwrite: bool) -> None:
    if path.exists() and not overwrite: raise JudgeValidationError(f"refusing to overwrite existing report: {path}; pass --overwrite")
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

def load(path: Path) -> dict[str, Any]:
    try: value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc: raise JudgeValidationError(f"cannot read {path}: {exc}") from exc
    if not isinstance(value, dict): raise JudgeValidationError("artifact must be a JSON object")
    return value

def sample_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Stable, model-balanced sample with diverse questions where possible."""
    valid = [row for row in rows if isinstance(row, dict) and isinstance(row.get("model"), str) and row.get("answerability") in {"answerable", "unanswerable"} and isinstance(row.get("judge"), dict)]
    selected: list[dict[str, Any]] = []
    for kind, target in (("answerable", 6), ("unanswerable", 4)):
        by_model: dict[str, list[dict[str, Any]]] = {}
        for row in sorted((row for row in valid if row["answerability"] == kind), key=lambda row: (row["model"], row.get("qa_id", ""))): by_model.setdefault(row["model"], []).append(row)
        models = sorted(by_model)
        qa_ids = sorted({row.get("qa_id") for rows_for_model in by_model.values() for row in rows_for_model if isinstance(row.get("qa_id"), str)})
        if not models or not qa_ids:
            raise JudgeValidationError(f"need at least {target} judge outputs for {kind}")
        for index in range(target):
            model, preferred_qa = models[index % len(models)], qa_ids[index % len(qa_ids)]
            choices = by_model[model]
            position = next((i for i, row in enumerate(choices) if row.get("qa_id") == preferred_qa), 0 if choices else -1)
            if position < 0:
                raise JudgeValidationError(f"need at least {target} judge outputs for {kind}")
            selected.append(choices.pop(position))
    return selected

def review_material(qa: dict[str, Any], context_packet: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    """Validate and expose only the frozen development material needed by the owner."""
    questions = qa.get("questions")
    if qa.get("status") != "approved" or not isinstance(questions, list):
        raise JudgeValidationError("judge worksheet requires the approved QA oracle")
    cases: dict[str, dict[str, Any]] = {}
    for item in questions:
        if not isinstance(item, dict) or item.get("split") != "development":
            continue
        if (
            not isinstance(item.get("id"), str)
            or not isinstance(item.get("question"), str)
            or not isinstance(item.get("answerable"), bool)
            or not isinstance(item.get("acceptable_answer"), str)
        ):
            raise JudgeValidationError("malformed development QA case")
        cases[item["id"]] = {
            "question": item["question"],
            "answerability": "answerable" if item["answerable"] else "unanswerable",
            "acceptable_answer": item["acceptable_answer"],
        }
    if len(cases) != 13:
        raise JudgeValidationError("judge worksheet requires exactly 13 development QA cases")
    raw_contexts = context_packet.get("contexts")
    if not isinstance(raw_contexts, list):
        raise JudgeValidationError("development contexts artifact needs a contexts list")
    contexts: dict[str, list[dict[str, Any]]] = {}
    required = ("chunk_id", "pmid", "title", "text", "start_char", "end_char")
    for entry in raw_contexts:
        if not isinstance(entry, dict) or entry.get("qa_id") not in cases or not isinstance(entry.get("chunks"), list):
            raise JudgeValidationError("malformed development context entry")
        evidence = []
        for citation_id, chunk in enumerate(entry["chunks"][:5], 1):
            if not isinstance(chunk, dict) or any(key not in chunk for key in required):
                raise JudgeValidationError("malformed development context chunk")
            if not all(isinstance(chunk[key], str) for key in ("chunk_id", "pmid", "title", "text")):
                raise JudgeValidationError("development context text fields must be strings")
            if any(isinstance(chunk[key], bool) or not isinstance(chunk[key], int) for key in ("start_char", "end_char")):
                raise JudgeValidationError("development context offsets must be integers")
            evidence.append({"citation_id": citation_id, **{key: chunk[key] for key in required}})
        if not evidence or entry["qa_id"] in contexts:
            raise JudgeValidationError("each development case needs one nonempty context entry")
        contexts[entry["qa_id"]] = evidence
    if set(contexts) != set(cases):
        raise JudgeValidationError("development contexts must match the QA cases exactly")
    return cases, contexts

def worksheet(rows: list[dict[str, Any]], cases: dict[str, dict[str, Any]], contexts: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    # Judge verdicts are deliberately omitted so owner labels are blind. They
    # are reloaded from the immutable source outputs during validation.
    sample = []
    for row in sample_rows(rows):
        qa_id = row.get("qa_id")
        if qa_id not in cases or row.get("answerability") != cases[qa_id]["answerability"]:
            raise JudgeValidationError("source output does not match the approved QA answerability")
        sample.append({
            "sample_id": f"{row['model']}:{qa_id}",
            "model": row["model"],
            "qa_id": qa_id,
            **cases[qa_id],
            "retrieved_evidence": [dict(chunk) for chunk in contexts[qa_id]],
            "answer": row.get("answer"),
            "owner_label": {"reviewer": "", **{dimension: None for dimension in DIMENSIONS}},
        })
    return {
        "version": 2,
        "purpose": "Blind project-owner labels for deterministic judge validation",
        "rubric": {
            "faithful": "Every answer claim is supported by the displayed evidence; a refusal is faithful only when that evidence is insufficient.",
            "relevant": "The response directly and usefully addresses the displayed question.",
            "citations_correct": "For an answered response, cited evidence supports the associated claims; use null when the response is a refusal with no citations.",
            "refusal_correct": "The answer/refusal status matches the displayed frozen answerability label.",
        },
        "sample": sample,
    }

def validate_labels(packet: dict[str, Any], rows: list[dict[str, Any]], cases: dict[str, dict[str, Any]], contexts: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    sample = packet.get("sample")
    if not isinstance(sample, list) or len(sample) != 10: raise JudgeValidationError("worksheet must contain exactly ten sampled outputs")
    expected_packet = worksheet(rows, cases, contexts)
    if any(packet.get(key) != expected_packet.get(key) for key in ("version", "purpose", "rubric")):
        raise JudgeValidationError("worksheet rubric or version changed")
    expected_sample = {item["sample_id"]: item for item in expected_packet["sample"]}
    source: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("model"), str) or not isinstance(row.get("qa_id"), str):
            continue
        sample_id = f"{row['model']}:{row['qa_id']}"
        if sample_id in source: raise JudgeValidationError(f"duplicate source output: {sample_id}")
        source[sample_id] = row
    report: dict[str, Any] = {"n": 10, "dimensions": {}}
    for dimension in DIMENSIONS:
        pairs = []
        for item in sample:
            if not isinstance(item, dict) or not isinstance(item.get("sample_id"), str) or item["sample_id"] not in source:
                raise JudgeValidationError("worksheet sample is not present in the source outputs")
            saved = source[item["sample_id"]]
            expected = expected_sample.get(item["sample_id"])
            if expected is None or any(item.get(key) != expected.get(key) for key in expected if key != "owner_label"):
                raise JudgeValidationError(f"worksheet evidence changed for {item['sample_id']}")
            owner, judge = item.get("owner_label"), saved.get("judge")
            if not isinstance(owner, dict) or not isinstance(owner.get("reviewer"), str) or not owner["reviewer"].strip():
                raise JudgeValidationError(f"owner label and reviewer required for {dimension}")
            owner_value = owner.get(dimension)
            if dimension == "citations_correct" and saved.get("answer", {}).get("status") == "insufficient_evidence" and owner_value is None:
                continue
            if not isinstance(owner_value, bool): raise JudgeValidationError(f"owner label and reviewer required for {dimension}")
            if not isinstance(judge, dict) or not isinstance(judge.get(dimension), bool): raise JudgeValidationError(f"saved judge verdict required for {dimension}")
            pairs.append((owner_value, judge[dimension]))
        value = binary_agreement(pairs); value["passes"] = value["agreement"] >= .80 and value["kappa"] is not None and value["kappa"] >= .60
        value["status"] = "pass" if value["passes"] else ("inconclusive_undefined_kappa" if value["kappa"] is None else "fail")
        report["dimensions"][dimension] = value
    report["passes"] = all(value["passes"] for value in report["dimensions"].values())
    return report

def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--outputs", type=Path, default=ROOT / "data/rag_bakeoff_outputs.json"); parser.add_argument("--qa", type=Path, default=ROOT / "data/qa.json"); parser.add_argument("--contexts", type=Path, default=ROOT / "data/rag_development_contexts.json"); parser.add_argument("--worksheet", type=Path, default=ROOT / "data/judge_validation_worksheet.json"); parser.add_argument("--report", type=Path, default=ROOT / "data/judge_validation_report.json"); parser.add_argument("--validate", action="store_true"); parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    try:
        output_packet, qa, context_packet = load(args.outputs), load(args.qa), load(args.contexts); outputs = output_packet.get("outputs")
        if not isinstance(outputs, list): raise JudgeValidationError("outputs artifact needs an outputs list")
        outputs_hash = hashlib.sha256(args.outputs.read_bytes()).hexdigest().upper()
        qa_hash = hashlib.sha256(args.qa.read_bytes()).hexdigest().upper()
        contexts_hash = hashlib.sha256(args.contexts.read_bytes()).hexdigest().upper()
        if context_packet.get("qa_sha256") != qa_hash:
            raise JudgeValidationError("development contexts are not bound to the approved QA artifact")
        cases, contexts = review_material(qa, context_packet)
        if args.validate:
            worksheet_packet = load(args.worksheet)
            if worksheet_packet.get("source_outputs_sha256") != outputs_hash or worksheet_packet.get("qa_sha256") != qa_hash or worksheet_packet.get("contexts_sha256") != contexts_hash:
                raise JudgeValidationError("worksheet is not bound to the supplied outputs, QA, and contexts")
            report = validate_labels(worksheet_packet, outputs, cases, contexts)
            report["worksheet_sha256"] = hashlib.sha256(args.worksheet.read_bytes()).hexdigest().upper()
            report["source_outputs_sha256"] = outputs_hash
            write_atomic(args.report, report, overwrite=args.overwrite); print(json.dumps(report, sort_keys=True)); return 0 if report["passes"] else 1
        packet = worksheet(outputs, cases, contexts)
        packet["source_outputs_sha256"] = outputs_hash
        packet["qa_sha256"] = qa_hash
        packet["contexts_sha256"] = contexts_hash
        write_atomic(args.worksheet, packet, overwrite=args.overwrite)
    except (JudgeValidationError, OSError, TypeError) as exc: print(f"Error: {exc}", file=sys.stderr); return 1
    print(f"Wrote deterministic 10-output owner-label worksheet to {args.worksheet}"); return 0
if __name__ == "__main__": raise SystemExit(main())

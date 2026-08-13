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
    """Stable six-answerable/four-unanswerable sample distributed across models."""
    valid = [row for row in rows if isinstance(row, dict) and isinstance(row.get("model"), str) and row.get("answerability") in {"answerable", "unanswerable"} and isinstance(row.get("judge"), dict)]
    selected: list[dict[str, Any]] = []
    for kind, target in (("answerable", 6), ("unanswerable", 4)):
        by_model: dict[str, list[dict[str, Any]]] = {}
        for row in sorted((row for row in valid if row["answerability"] == kind), key=lambda row: (row["model"], row.get("qa_id", ""))): by_model.setdefault(row["model"], []).append(row)
        while sum(row["answerability"] == kind for row in selected) < target:
            progressed = False
            for model in sorted(by_model):
                if by_model[model] and sum(row["answerability"] == kind for row in selected) < target:
                    selected.append(by_model[model].pop(0)); progressed = True
            if not progressed: raise JudgeValidationError(f"need at least {target} judge outputs for {kind}")
    return selected

def worksheet(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"version": 1, "purpose": "Project-owner labels for deterministic judge validation", "sample": [{"sample_id": f"{row['model']}:{row['qa_id']}", "model": row["model"], "qa_id": row["qa_id"], "answerability": row["answerability"], "answer": row.get("answer"), "judge": row["judge"], "owner_label": {"reviewer": "", **{dimension: None for dimension in DIMENSIONS}}} for row in sample_rows(rows)]}

def validate_labels(packet: dict[str, Any]) -> dict[str, Any]:
    sample = packet.get("sample")
    if not isinstance(sample, list) or len(sample) != 10: raise JudgeValidationError("worksheet must contain exactly ten sampled outputs")
    report: dict[str, Any] = {"n": 10, "dimensions": {}}
    for dimension in DIMENSIONS:
        pairs = []
        for item in sample:
            owner, judge = item.get("owner_label"), item.get("judge")
            if not isinstance(owner, dict) or not isinstance(owner.get("reviewer"), str) or not owner["reviewer"].strip() or not isinstance(owner.get(dimension), bool): raise JudgeValidationError(f"owner label and reviewer required for {dimension}")
            if not isinstance(judge, dict) or not isinstance(judge.get(dimension), bool): raise JudgeValidationError(f"saved judge verdict required for {dimension}")
            pairs.append((owner[dimension], judge[dimension]))
        value = binary_agreement(pairs); value["passes"] = value["agreement"] >= .80 and value["kappa"] is not None and value["kappa"] >= .60
        value["status"] = "pass" if value["passes"] else ("inconclusive_undefined_kappa" if value["kappa"] is None else "fail")
        report["dimensions"][dimension] = value
    report["passes"] = all(value["passes"] for value in report["dimensions"].values())
    return report

def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--outputs", type=Path, default=ROOT / "data/rag_bakeoff_outputs.json"); parser.add_argument("--worksheet", type=Path, default=ROOT / "data/judge_validation_worksheet.json"); parser.add_argument("--report", type=Path, default=ROOT / "data/judge_validation_report.json"); parser.add_argument("--validate", action="store_true"); parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.validate:
            worksheet_packet = load(args.worksheet)
            report = validate_labels(worksheet_packet)
            report["worksheet_sha256"] = hashlib.sha256(args.worksheet.read_bytes()).hexdigest().upper()
            report["source_outputs_sha256"] = worksheet_packet.get("source_outputs_sha256")
            write_atomic(args.report, report, overwrite=args.overwrite); print(json.dumps(report, sort_keys=True)); return 0 if report["passes"] else 1
        output_packet = load(args.outputs); outputs = output_packet.get("outputs")
        if not isinstance(outputs, list): raise JudgeValidationError("outputs artifact needs an outputs list")
        packet = worksheet(outputs)
        packet["source_outputs_sha256"] = hashlib.sha256(args.outputs.read_bytes()).hexdigest().upper()
        write_atomic(args.worksheet, packet, overwrite=args.overwrite)
    except (JudgeValidationError, OSError, TypeError) as exc: print(f"Error: {exc}", file=sys.stderr); return 1
    print(f"Wrote deterministic 10-output owner-label worksheet to {args.worksheet}"); return 0
if __name__ == "__main__": raise SystemExit(main())

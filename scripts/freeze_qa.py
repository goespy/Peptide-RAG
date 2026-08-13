#!/usr/bin/env python3
"""Freeze a human-approved QA packet without inventing approvals."""
from __future__ import annotations

import argparse, hashlib, json, os, sys, tempfile
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
FROZEN_CORPUS_SHA256 = "231E048971C34EF9203ED3BB20587DDE4C95141AC7EFD2746C85C078A844212C"

class QAFreezeError(RuntimeError): pass

def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest().upper()

def _load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise QAFreezeError(f"cannot read {path}: {exc}") from exc
    if not isinstance(data, dict): raise QAFreezeError("QA packet must be an object")
    return data

def _corpus(path: Path) -> dict[str, dict[str, str]]:
    records: dict[str, dict[str, str]] = {}
    try: lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError as exc: raise QAFreezeError(f"cannot read corpus: {exc}") from exc
    for number, line in enumerate(lines, 1):
        try: item = json.loads(line)
        except json.JSONDecodeError as exc: raise QAFreezeError(f"invalid corpus JSON line {number}") from exc
        if not isinstance(item, dict) or set(item) != {"id", "title", "text"} or not all(isinstance(item.get(k), str) for k in ("id", "title", "text")):
            raise QAFreezeError(f"invalid corpus record at line {number}")
        if item["id"] in records: raise QAFreezeError(f"duplicate corpus PMID {item['id']}")
        records[item["id"]] = item
    return records

def validate_for_freeze(packet: dict[str, Any], corpus_path: Path, *, expected_corpus_sha256: str = FROZEN_CORPUS_SHA256) -> dict[str, Any]:
    actual = sha256(corpus_path)
    if actual != expected_corpus_sha256.upper() or packet.get("corpus_sha256") != actual:
        raise QAFreezeError("QA packet and corpus must match the frozen corpus hash")
    cases = packet.get("cases")
    if not isinstance(cases, list) or [case.get("id") if isinstance(case, dict) else None for case in cases] != [f"qa{i:02d}" for i in range(1, 21)]:
        raise QAFreezeError("QA packet must contain qa01 through qa20 exactly once in order")
    corpus = _corpus(corpus_path)
    answerable = unanswerable = 0
    for case in cases:
        if not isinstance(case.get("question"), str) or not case["question"].strip():
            raise QAFreezeError(f"{case['id']} lacks a human-readable question")
        if not isinstance(case.get("rationale"), str) or not case["rationale"].strip():
            raise QAFreezeError(f"{case['id']} lacks a manual rationale")
        expected_split = "development" if case["id"] in {f"qa{i:02d}" for i in list(range(1, 11)) + [16, 17, 18]} else "holdout"
        if case.get("split") != expected_split:
            raise QAFreezeError(f"{case['id']} does not match the frozen QA split")
        review = case.get("human_review")
        if not isinstance(review, dict) or review.get("approved") is not True or review.get("decision") != "approve" or not isinstance(review.get("reviewer"), str) or not review["reviewer"].strip():
            raise QAFreezeError(f"{case['id']} lacks an explicit human approval and reviewer")
        kind = case.get("answerability")
        if kind == "answerable":
            answerable += 1
            spans, pmids = case.get("evidence_spans"), case.get("pmids")
            if not isinstance(spans, list) or not spans or not isinstance(pmids, list) or not pmids or any(not isinstance(pmid, str) or not pmid for pmid in pmids) or len(pmids) != len(set(pmids)) or not isinstance(case.get("acceptable_answer"), str) or not case["acceptable_answer"].strip():
                raise QAFreezeError(f"{case['id']} lacks approved answer evidence")
            for span in spans:
                if not isinstance(span, dict) or span.get("pmid") not in corpus or isinstance(span.get("start"), bool) or not isinstance(span.get("start"), int) or isinstance(span.get("end"), bool) or not isinstance(span.get("end"), int) or not isinstance(span.get("text"), str) or not isinstance(span.get("sha256"), str) or len(span["sha256"]) != 64:
                    raise QAFreezeError(f"{case['id']} has malformed evidence span")
                abstract = corpus[span["pmid"]]["text"]; start, end = span["start"], span["end"]
                extracted = abstract[start:end]
                if start < 0 or end <= start or extracted != span["text"] or hashlib.sha256(extracted.encode()).hexdigest().upper() != span["sha256"].upper():
                    raise QAFreezeError(f"{case['id']} evidence span does not match frozen corpus")
            if {span["pmid"] for span in spans} != set(pmids):
                raise QAFreezeError(f"{case['id']} relevant PMIDs and spans disagree")
        elif kind == "unanswerable":
            unanswerable += 1
            if case.get("pmids") or case.get("evidence_spans") or case.get("acceptable_answer"):
                raise QAFreezeError(f"{case['id']} unanswerable case cannot contain evidence")
        else: raise QAFreezeError(f"{case['id']} has invalid answerability")
    if (answerable, unanswerable) != (15, 5): raise QAFreezeError("QA packet must have 15 answerable and 5 unanswerable cases")
    if not isinstance(packet.get("qrels_v2_sha256"), str) or len(packet["qrels_v2_sha256"]) != 64:
        raise QAFreezeError("QA packet lacks its frozen qrels-v2 hash")
    questions: list[dict[str, Any]] = []
    for case in cases:
        answerable = case["answerability"] == "answerable"
        questions.append({
            "id": case["id"],
            "question": case["question"],
            "answerable": answerable,
            "acceptable_answer": case["acceptable_answer"],
            "relevant_pmids": list(case["pmids"]),
            "supporting_spans": [
                {
                    "pmid": span["pmid"],
                    "start_char": span["start"],
                    "end_char": span["end"],
                    "text_sha256": span["sha256"],
                }
                for span in case["evidence_spans"]
            ],
            "rationale": case["rationale"],
            "split": case["split"],
            "human_review": dict(case["human_review"]),
        })
    return {
        "version": packet.get("version", 1),
        "status": "approved",
        "corpus_sha256": actual,
        "qrels_v2_sha256": packet.get("qrels_v2_sha256"),
        "development_question_ids": list(packet.get("development_case_ids", [])),
        "holdout_question_ids": list(packet.get("holdout_case_ids", [])),
        "questions": questions,
        "approved_from": "human-reviewed QA candidate packet",
    }

def write_atomic(payload: dict[str, Any], path: Path, *, overwrite: bool = False) -> None:
    if path.exists() and not overwrite: raise QAFreezeError(f"refusing to overwrite existing file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as out:
            json.dump(payload, out, ensure_ascii=False, indent=2); out.write("\n"); out.flush(); os.fsync(out.fileno())
        os.replace(name, path)
    except BaseException:
        try: os.unlink(name)
        except FileNotFoundError: pass
        raise

def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__); p.add_argument("--input", type=Path, default=ROOT / "data/qa_draft.json"); p.add_argument("--corpus", type=Path, default=ROOT / "data/corpus.jsonl"); p.add_argument("--output", type=Path, default=ROOT / "data/qa.json"); p.add_argument("--overwrite", action="store_true"); args = p.parse_args(argv)
    try: write_atomic(validate_for_freeze(_load_json(args.input), args.corpus), args.output, overwrite=args.overwrite)
    except (QAFreezeError, OSError, TypeError) as exc: print(f"Error: {exc}", file=sys.stderr); return 1
    print(f"Wrote approved QA set to {args.output}"); return 0
if __name__ == "__main__": raise SystemExit(main())

#!/usr/bin/env python3
"""Build a deterministic, explicitly unapproved QA-review candidate packet."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

DEFAULT_CORPUS = Path("data/corpus.jsonl")
DEFAULT_QRELS = Path("data/qrels_v2.json")
DEFAULT_OUTPUT = Path("data/qa_draft.json")
FROZEN_CORPUS_SHA256 = "231E048971C34EF9203ED3BB20587DDE4C95141AC7EFD2746C85C078A844212C"
FROZEN_QRELS_V2_SHA256 = "B30E1B7868EFFB580155442917C2BB0105ECC00E13527A103F6325B6A2B32ED6"

DEVELOPMENT_IDS = tuple([f"qa{number:02d}" for number in range(1, 11)] + ["qa16", "qa17", "qa18"])
HOLDOUT_IDS = tuple([f"qa{number:02d}" for number in range(11, 16)] + ["qa19", "qa20"])
STOPWORDS = frozenset({"and", "or", "the", "a", "an", "of", "in", "for", "with", "to", "on", "at", "by", "from", "is", "are"})

UNANSWERABLES = (
    ("qa16", "Does BPC-157 cure cancer in humans?", ("bpc", "157"), ("cure", "cancer", "human")),
    ("qa17", "What dose of GHK-Cu safely treats Alzheimer's disease during pregnancy?", ("ghk", "cu"), ("dose", "alzheimer", "pregnancy")),
    ("qa18", "Does TB-500 reverse kidney failure in humans?", ("tb", "500"), ("reverse", "kidney", "failure", "human")),
    ("qa19", "Can ipamorelin replace insulin for type 1 diabetes?", ("ipamorelin",), ("replace", "insulin", "type", "diabetes")),
    ("qa20", "Does PT-141 prevent myocardial infarction?", ("pt", "141"), ("prevent", "myocardial", "infarction")),
)


class QAReviewPreparationError(RuntimeError):
    """Raised when a frozen input cannot safely produce the review packet."""


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def tokens(value: str) -> tuple[str, ...]:
    return tuple(re.findall(r"[a-z0-9]+", value.casefold()))


def load_corpus(path: Path) -> dict[str, dict[str, str]]:
    documents: dict[str, dict[str, str]] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise QAReviewPreparationError(f"Cannot read corpus: {exc}") from exc
    for line_number, line in enumerate(lines, 1):
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise QAReviewPreparationError(f"Invalid corpus JSON at line {line_number}") from exc
        if not isinstance(item, dict) or set(item) != {"id", "title", "text"} or not all(isinstance(item.get(key), str) for key in ("id", "title", "text")):
            raise QAReviewPreparationError(f"Invalid corpus document at line {line_number}")
        if item["id"] in documents:
            raise QAReviewPreparationError(f"Duplicate corpus PMID {item['id']}")
        documents[item["id"]] = item
    if not documents:
        raise QAReviewPreparationError("Corpus is empty")
    return documents


def load_qrels(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise QAReviewPreparationError(f"Cannot read qrels: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("queries"), list):
        raise QAReviewPreparationError("Qrels must contain a queries list")
    return payload


def sentences(text: str) -> list[tuple[int, int, str]]:
    """Return exact abstract sentences while retaining original character offsets."""
    found = [(match.start(), match.end(), match.group(0)) for match in re.finditer(r"[^.!?]+[.!?](?:\s+|$)|[^.!?]+$", text)]
    return [(start, end, sentence) for start, end, sentence in found if sentence.strip()]


def select_source(query: dict[str, Any], corpus: dict[str, dict[str, str]]) -> str:
    grade_twos = sorted((pmid for pmid, grade in query.get("judgments", {}).items() if grade == 2), key=int)
    query_terms = set(tokens(query["query"])) - STOPWORDS
    direct = [pmid for pmid in grade_twos if pmid in corpus and len(query_terms & set(tokens(corpus[pmid]["text"]))) >= 2]
    if not direct:
        raise QAReviewPreparationError(f"{query.get('id')} has no grade-2 PMID with direct abstract overlap")
    return direct[0]


def select_span(question: str, abstract: str) -> tuple[int, int, str]:
    question_terms = set(tokens(question)) - STOPWORDS
    source_sentences = sentences(abstract)
    candidates: list[tuple[int, int, str]] = []
    for start_index in range(len(source_sentences)):
        for width in range(1, 4):
            window = source_sentences[start_index : start_index + width]
            if len(window) != width:
                continue
            candidates.append((window[0][0], window[-1][1], abstract[window[0][0] : window[-1][1]]))
    ranked = sorted(candidates, key=lambda item: (-len(question_terms & set(tokens(item[2]))), len(item[2]), item[0]))
    if not ranked or len(question_terms & set(tokens(ranked[0][2]))) < 2:
        raise QAReviewPreparationError("No direct abstract sentence supports the frozen query")
    start, end, sentence = ranked[0]
    return start, end, sentence


def lexical_absence_check(corpus: dict[str, dict[str, str]], peptide: tuple[str, ...], claim: tuple[str, ...]) -> dict[str, Any]:
    matches: list[str] = []
    for pmid, document in sorted(corpus.items(), key=lambda pair: int(pair[0])):
        text_tokens = set(tokens(f"{document['title']} {document['text']}"))
        if set(peptide).issubset(text_tokens) and set(claim).issubset(text_tokens):
            matches.append(pmid)
    if matches:
        raise QAReviewPreparationError(f"Unanswerable claim has lexical direct-support candidates: {', '.join(matches)}")
    return {"method": "same-document required-token conjunction over title and abstract", "peptide_tokens": list(peptide), "claim_tokens": list(claim), "matching_pmids": matches, "limitation": "No matches under this deterministic lexical check; absence is not exhaustive evidence that no support exists."}


def build_packet(corpus_path: Path, qrels_path: Path) -> dict[str, Any]:
    corpus = load_corpus(corpus_path)
    qrels = load_qrels(qrels_path)
    corpus_hash, qrels_hash = file_sha256(corpus_path), file_sha256(qrels_path)
    if corpus_hash != FROZEN_CORPUS_SHA256 or qrels_hash != FROZEN_QRELS_V2_SHA256:
        raise QAReviewPreparationError("Inputs do not match the Section 5 frozen corpus and qrels-v2 snapshots")
    if qrels.get("corpus_sha256") != corpus_hash:
        raise QAReviewPreparationError("Frozen qrels corpus hash does not match corpus.jsonl")
    cases: list[dict[str, Any]] = []
    queries = qrels["queries"]
    if [query.get("id") for query in queries] != [f"q{number:02d}" for number in range(1, 16)]:
        raise QAReviewPreparationError("qrels must retain the frozen q01-q15 order")
    for number, query in enumerate(queries, 1):
        question = query["query"].rstrip("?") + "?"
        pmid = select_source(query, corpus)
        start, end, support = select_span(question, corpus[pmid]["text"])
        cases.append({"id": f"qa{number:02d}", "answerability": "answerable", "split": "development" if number <= 10 else "holdout", "source_query_id": query["id"], "question": question, "acceptable_answer": support.strip(), "pmids": [pmid], "evidence_spans": [{"pmid": pmid, "start": start, "end": end, "text": support, "sha256": hashlib.sha256(support.encode("utf-8")).hexdigest().upper()}], "rationale": "Draft answer is limited to the exact cited abstract sentence; a human must confirm wording and sufficiency.", "human_review": {"approved": False, "decision": "pending", "reviewer": "", "notes": ""}})
    for case_id, question, peptide, claim in UNANSWERABLES:
        cases.append({"id": case_id, "answerability": "unanswerable", "split": "development" if case_id in DEVELOPMENT_IDS else "holdout", "question": question, "acceptable_answer": "", "pmids": [], "evidence_spans": [], "rationale": "The frozen abstract corpus has no sufficient direct evidence for this claim under the recorded lexical check. This absence check is not exhaustive and requires human review.", "lexical_absence_check": lexical_absence_check(corpus, peptide, claim), "human_review": {"approved": False, "decision": "pending", "reviewer": "", "notes": ""}})
    cases.sort(key=lambda case: int(case["id"][2:]))
    return {"version": 1, "status": "candidate_pool_requires_human_review", "corpus_sha256": corpus_hash, "qrels_v2_sha256": qrels_hash, "source_qrels": str(qrels_path).replace("\\", "/"), "development_case_ids": list(DEVELOPMENT_IDS), "holdout_case_ids": list(HOLDOUT_IDS), "cases": cases, "review_notice": "This candidate pool is not approved and must not be used to tune or evaluate RAG until project-owner review is recorded."}


def validate_packet(packet: dict[str, Any], corpus_path: Path, qrels_path: Path) -> None:
    if packet.get("status") != "candidate_pool_requires_human_review": raise QAReviewPreparationError("Packet must remain candidate_pool_requires_human_review")
    if packet.get("corpus_sha256") != FROZEN_CORPUS_SHA256 or packet.get("qrels_v2_sha256") != FROZEN_QRELS_V2_SHA256: raise QAReviewPreparationError("Packet must name the frozen Section 5 input hashes")
    if packet.get("corpus_sha256") != file_sha256(corpus_path) or packet.get("qrels_v2_sha256") != file_sha256(qrels_path): raise QAReviewPreparationError("Packet frozen input hashes do not match")
    cases = packet.get("cases")
    if not isinstance(cases, list) or [case.get("id") for case in cases] != [f"qa{number:02d}" for number in range(1, 21)]: raise QAReviewPreparationError("Packet must contain qa01-qa20 exactly once")
    if packet.get("development_case_ids") != list(DEVELOPMENT_IDS) or packet.get("holdout_case_ids") != list(HOLDOUT_IDS): raise QAReviewPreparationError("Packet split IDs differ from the fixed plan")
    corpus = load_corpus(corpus_path)
    answerable = [case for case in cases if case.get("answerability") == "answerable"]
    unanswerable = [case for case in cases if case.get("answerability") == "unanswerable"]
    if len(answerable) != 15 or len(unanswerable) != 5: raise QAReviewPreparationError("Packet must have a 15/5 answerability distribution")
    if sum(case["answerability"] == "answerable" for case in cases if case["split"] == "development") != 10 or sum(case["answerability"] == "unanswerable" for case in cases if case["split"] == "development") != 3: raise QAReviewPreparationError("Development distribution must be 10/3")
    if sum(case["answerability"] == "answerable" for case in cases if case["split"] == "holdout") != 5 or sum(case["answerability"] == "unanswerable" for case in cases if case["split"] == "holdout") != 2: raise QAReviewPreparationError("Holdout distribution must be 5/2")
    for case in cases:
        if case.get("human_review", {}).get("approved") is not False: raise QAReviewPreparationError(f"{case['id']} must remain unapproved")
        if case["answerability"] == "answerable":
            if len(case.get("pmids", [])) != 1 or not case.get("evidence_spans") or not case.get("acceptable_answer"): raise QAReviewPreparationError(f"{case['id']} needs a PMID, at least one span, and an answer")
            if {span.get("pmid") for span in case["evidence_spans"]} != set(case["pmids"]): raise QAReviewPreparationError(f"{case['id']} evidence PMIDs do not match")
            for span in case["evidence_spans"]:
                abstract = corpus[span["pmid"]]["text"]
                extracted = abstract[span["start"]:span["end"]]
                if extracted != span["text"] or hashlib.sha256(extracted.encode("utf-8")).hexdigest().upper() != span["sha256"]: raise QAReviewPreparationError(f"{case['id']} evidence span is not exact")
                if not 1 <= len(sentences(extracted)) <= 3: raise QAReviewPreparationError(f"{case['id']} each support span must contain 1-3 sentences")
        elif case.get("pmids") or case.get("evidence_spans") or case.get("acceptable_answer"): raise QAReviewPreparationError(f"{case['id']} unanswerable case cannot have evidence")


def write_json_atomic(payload: dict[str, Any], output: Path, overwrite: bool) -> None:
    if output.exists() and not overwrite: raise QAReviewPreparationError(f"Output already exists: {output}; use --overwrite")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=output.parent, delete=False) as handle:
        temporary = Path(handle.name); json.dump(payload, handle, ensure_ascii=False, indent=2); handle.write("\n")
    os.replace(temporary, output)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS); parser.add_argument("--qrels", type=Path, default=DEFAULT_QRELS); parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT); parser.add_argument("--overwrite", action="store_true"); args = parser.parse_args(argv)
    try:
        packet = build_packet(args.corpus, args.qrels); validate_packet(packet, args.corpus, args.qrels); write_json_atomic(packet, args.output, args.overwrite)
    except (OSError, QAReviewPreparationError, KeyError, TypeError) as exc:
        print(f"Error: {exc}", file=sys.stderr); return 1
    print(f"Wrote 20 unapproved QA cases to {args.output}"); return 0


if __name__ == "__main__": raise SystemExit(main())

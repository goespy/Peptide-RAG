#!/usr/bin/env python3
"""Validate a QA candidate packet and render its human-review worksheet."""
from __future__ import annotations
import argparse, json, os, sys, tempfile
from collections.abc import Sequence
from pathlib import Path
try:
    from scripts.prepare_qa_review import QAReviewPreparationError, validate_packet
except ModuleNotFoundError:
    from prepare_qa_review import QAReviewPreparationError, validate_packet

DEFAULT_DRAFT=Path("data/qa_draft.json"); DEFAULT_CORPUS=Path("data/corpus.jsonl"); DEFAULT_QRELS=Path("data/qrels_v2.json"); DEFAULT_OUTPUT=Path("QA-REVIEW.md")
class QAReviewRenderError(RuntimeError): pass
def load(path: Path):
    try: return json.loads(path.read_text(encoding="utf-8"))
    except (OSError,json.JSONDecodeError) as exc: raise QAReviewRenderError(f"Cannot read draft: {exc}") from exc
def render(packet):
    lines=["# QA Oracle Human Review", "", "> **Candidate pool only — not approved.** Do not use these cases for RAG tuning or evaluation until the project owner records approval.", "", f"- Corpus SHA-256: `{packet['corpus_sha256']}`", f"- Qrels v2 SHA-256: `{packet['qrels_v2_sha256']}`", "- Development: `qa01`–`qa10`, `qa16`–`qa18` (10 answerable / 3 unanswerable)", "- Holdout: `qa11`–`qa15`, `qa19`–`qa20` (5 answerable / 2 unanswerable)", "", "## Review instructions", "", "Read every cited abstract span. Approve, edit, or reject each case; verify that an answerable answer says no more than its support, and that an unanswerable case has no direct corpus evidence. Lexical absence checks are deterministic but not exhaustive.", ""]
    for case in packet['cases']:
        lines += [f"## {case['id']} — {case['answerability']} ({case['split']})", "", f"**Question:** {case['question']}", "", "- Decision: [ ] Approve  [ ] Edit  [ ] Reject", "- Reviewer:", "- Notes:", ""]
        if case['answerability']=='answerable':
            evidence=case['evidence_spans'][0]
            lines += [f"- Source: [PMID {evidence['pmid']}](https://pubmed.ncbi.nlm.nih.gov/{evidence['pmid']}/)", f"- Acceptable answer: {case['acceptable_answer']}", f"- Exact support offsets: `{evidence['start']}:{evidence['end']}`; SHA-256: `{evidence['sha256']}`", "", "### Exact abstract support", "", evidence['text'], ""]
        else:
            check=case['lexical_absence_check']; lines += ["- Proposed response: Insufficient evidence in this frozen abstract corpus.", f"- Lexical check: no matching PMID for peptide tokens `{', '.join(check['peptide_tokens'])}` plus claim tokens `{', '.join(check['claim_tokens'])}`.", f"- Caveat: {check['limitation']}", ""]
    return '\n'.join(lines).rstrip()+"\n"
def main(argv: Sequence[str]|None=None)->int:
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--draft',type=Path,default=DEFAULT_DRAFT); parser.add_argument('--corpus',type=Path,default=DEFAULT_CORPUS); parser.add_argument('--qrels',type=Path,default=DEFAULT_QRELS); parser.add_argument('--output',type=Path,default=DEFAULT_OUTPUT); parser.add_argument('--overwrite',action='store_true'); args=parser.parse_args(argv)
    try:
        if args.output.exists() and not args.overwrite: raise QAReviewRenderError(f"Output already exists: {args.output}; use --overwrite")
        packet=load(args.draft); validate_packet(packet,args.corpus,args.qrels); content=render(packet); args.output.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.NamedTemporaryFile('w',encoding='utf-8',newline='\n',dir=args.output.parent,delete=False) as handle: temporary=Path(handle.name); handle.write(content)
        os.replace(temporary,args.output)
    except (OSError,QAReviewPreparationError,QAReviewRenderError,KeyError,TypeError) as exc: print(f"Error: {exc}",file=sys.stderr); return 1
    print(f"Wrote 20 unapproved QA review cases to {args.output}"); return 0
if __name__=='__main__': raise SystemExit(main())

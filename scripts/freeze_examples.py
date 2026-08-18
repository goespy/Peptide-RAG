#!/usr/bin/env python3
"""Freeze the public example-question artifact against the frozen corpus.

The artifact is presentation data for the web shell only. It never feeds qrels,
IR metrics, or the QA oracle, and it records what was actually verified rather
than asserting that every question retrieves well.
"""
from __future__ import annotations

import argparse, hashlib, json, sys, tempfile
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.bm25 import BM25Config, rank_bm25  # noqa: E402
from src.index import InvertedIndex  # noqa: E402

FROZEN_CORPUS_SHA256 = "231E048971C34EF9203ED3BB20587DDE4C95141AC7EFD2746C85C078A844212C"
ARTIFACT_VERSION = 1
EXPECTED_TOPICS = 8
EXPECTED_QUESTIONS_PER_TOPIC = 3
VERIFY_TOP_K = 5


class ExampleFreezeError(RuntimeError):
    pass


# Hand-selected supporting records. Every PMID here was read against its question
# before being listed; the script only confirms corpus membership and retrieval.
TOPICS: tuple[dict[str, Any], ...] = (
    {
        "id": "bpc-157",
        "name": "BPC-157",
        "subtitle": "Body protection compound",
        "questions": (
            ("Does BPC-157 help tissue repair?", ("41898733", "41476424")),
            ("What did studies report about BPC-157 and liver injury?", ("36228773", "40005408")),
            ("What did rat studies find in experimental stomach and duodenal ulcer models?", ("7904712", "14512101")),
        ),
    },
    {
        "id": "ghk-cu",
        "name": "GHK-Cu",
        "subtitle": "Copper tripeptide",
        "questions": (
            ("Does GHK or GHK-Cu help regrow hair?", ("27489425", "26236730")),
            ("What does research say about GHK-Cu and wound or skin repair?", ("28370978", "18644225")),
            ("How did GHK-Cu affect ACL graft healing in rats?", ("25731775",)),
        ),
    },
    {
        "id": "tb-500",
        "name": "TB-500",
        "subtitle": "Thymosin beta-4",
        "questions": (
            ("Does TB-500 help injuries or wounds heal?", ("42542926", "41476424")),
            ("What peptide is the key ingredient in TB-500, and how is it related to thymosin beta-4?", ("23084823",)),
            ("What does preclinical research report about thymosin beta-4 and heart repair?", ("31333080", "22019445")),
        ),
    },
    {
        "id": "ipamorelin",
        "name": "Ipamorelin",
        "subtitle": "GH secretagogue",
        "questions": (
            ("Does ipamorelin increase growth hormone?", ("9849822", "9733495")),
            ("Does ipamorelin reduce body fat?", ("11162489",)),
            ("What did studies report about ipamorelin's selectivity and its effects on ACTH and cortisol?", ("9849822",)),
        ),
    },
    {
        "id": "tesamorelin",
        "name": "Tesamorelin",
        "subtitle": "GHRH analogue",
        "questions": (
            ("Does tesamorelin reduce belly fat?", ("20101189", "30764032")),
            ("What effects did tesamorelin have on visceral fat and triglycerides in the HIV trial?", ("18057338", "30764032")),
            ("Does tesamorelin reduce liver fat in people with HIV?", ("31611038", "25038357")),
        ),
    },
    {
        "id": "epitalon",
        "name": "Epitalon",
        "subtitle": "Pineal tetrapeptide",
        "questions": (
            ("How did developmental exposure to Epitalon affect adult fruit-fly lifespan?", ("11087911",)),
            ("How did Epitalon affect melatonin and cortisol rhythms in older monkeys?", ("11550036", "11524632")),
            ("What did human-cell studies report about Epitalon and telomere length?", ("40908429", "12937682")),
        ),
    },
    {
        "id": "mots-c",
        "name": "MOTS-c",
        "subtitle": "Mitochondrial peptide",
        "questions": (
            ("Does MOTS-c help with weight loss or metabolism?", ("41551324", "28574175")),
            ("What do animal studies report about MOTS-c, exercise, and insulin sensitivity?", ("31293078", "39077591")),
            ("What hypothesis connects the MOTS-c m.1382A>C variant with Japanese longevity?", ("26289118", "33468709")),
        ),
    },
    {
        "id": "pt-141",
        "name": "PT-141",
        "subtitle": "Bremelanotide",
        "questions": (
            ("Does PT-141 help with erectile dysfunction?", ("12851303", "14963471")),
            ("What did studies report about PT-141 in women with sexual arousal disorder?", ("16839319",)),
            ("How is PT-141 thought to work through melanocortin receptors?", ("12851303", "17584130")),
        ),
    },
)


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest().upper()


def _lexical_config(path: Path) -> BM25Config:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))["bm25"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ExampleFreezeError(f"cannot read frozen lexical config: {exc}") from exc
    return BM25Config(
        k1=float(payload["k1"]),
        b=float(payload["b"]),
        proximity_boost=float(payload["proximity_boost"]),
    )


def build(corpus_path: Path, config_path: Path) -> dict[str, Any]:
    corpus_hash = sha256(corpus_path)
    if corpus_hash != FROZEN_CORPUS_SHA256:
        raise ExampleFreezeError("corpus hash does not match the frozen corpus; refusing to freeze examples")

    index = InvertedIndex.from_jsonl(corpus_path)
    config = _lexical_config(config_path)
    known = set(index.documents)

    if len(TOPICS) != EXPECTED_TOPICS:
        raise ExampleFreezeError(f"expected {EXPECTED_TOPICS} topics, found {len(TOPICS)}")

    topics: list[dict[str, Any]] = []
    confirmed = 0
    total = 0
    for topic in TOPICS:
        if len(topic["questions"]) != EXPECTED_QUESTIONS_PER_TOPIC:
            raise ExampleFreezeError(f"topic {topic['id']} must carry exactly {EXPECTED_QUESTIONS_PER_TOPIC} questions")
        questions: list[dict[str, Any]] = []
        for text, supporting in topic["questions"]:
            missing = [pmid for pmid in supporting if pmid not in known]
            if missing:
                raise ExampleFreezeError(f"supporting PMIDs absent from the frozen corpus: {sorted(missing)}")
            ranked = [hit.doc_id for hit in rank_bm25(index, text, k=VERIFY_TOP_K, config=config)]
            hits = [pmid for pmid in supporting if pmid in ranked]
            total += 1
            if hits:
                confirmed += 1
            questions.append(
                {
                    "text": text,
                    "supporting_pmids": list(supporting),
                    "verification": {
                        "in_corpus": True,
                        "lexical_top_k": VERIFY_TOP_K,
                        "lexical_top_k_hits": hits,
                        "semantic_or_hybrid_confirmed": False,
                    },
                }
            )
        topics.append(
            {
                "id": topic["id"],
                "name": topic["name"],
                "subtitle": topic["subtitle"],
                "questions": questions,
            }
        )

    return {
        "version": ARTIFACT_VERSION,
        "status": "frozen_presentation_data",
        "corpus_sha256": corpus_hash,
        "lexical_config_sha256": sha256(config_path),
        "topic_count": len(topics),
        "questions_per_topic": EXPECTED_QUESTIONS_PER_TOPIC,
        "verification": {
            "method": "frozen BM25 top-5 over the frozen corpus",
            "questions_total": total,
            "questions_with_supporting_record_in_lexical_top_5": confirmed,
            "hybrid_verified": False,
            "hybrid_verification_note": (
                "Hybrid and semantic retrieval embed the query at request time and need a live "
                "provider key, so they were not exercised offline. Only corpus membership and "
                "frozen-BM25 top-5 placement are recorded here."
            ),
        },
        "separation_note": "Presentation data only. Not used by qrels, IR metrics, or the QA oracle.",
        "topics": topics,
    }


def write_atomic(path: Path, payload: dict[str, Any]) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False, newline="\n") as handle:
        handle.write(text)
        temporary = Path(handle.name)
    temporary.replace(path)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=ROOT / "data" / "corpus.jsonl")
    parser.add_argument("--lexical-config", type=Path, default=ROOT / "data" / "lexical_config.json")
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "examples.json")
    parser.add_argument("--check", action="store_true", help="Fail if the artifact on disk differs from a fresh build")
    args = parser.parse_args(argv)

    try:
        payload = build(args.corpus, args.lexical_config)
    except (ExampleFreezeError, OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.check:
        try:
            current = json.loads(args.out.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"Error: cannot read {args.out}: {exc}", file=sys.stderr)
            return 1
        if current != payload:
            print("Error: examples artifact is stale; re-run without --check", file=sys.stderr)
            return 1
        print("examples artifact matches a fresh build")
        return 0

    write_atomic(args.out, payload)
    verified = payload["verification"]
    print(
        f"wrote {args.out} - {payload['topic_count']} topics, "
        f"{verified['questions_with_supporting_record_in_lexical_top_5']}/{verified['questions_total']} "
        "questions with a supporting record in the frozen BM25 top 5"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

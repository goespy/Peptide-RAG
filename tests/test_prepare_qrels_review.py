from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.prepare_qrels_review import (
    Document,
    ReviewPreparationError,
    analyze,
    build_packet,
    matching_families,
    select_documents,
    write_json_atomic,
)


class AnalysisTests(unittest.TestCase):
    def test_analysis_matches_architecture(self) -> None:
        self.assertEqual(
            analyze("BPC-157 GHK_Cu MOTS-c"),
            ("bpc", "157", "ghk", "cu", "mots", "c"),
        )

    def test_alias_matching_requires_contiguous_title_tokens(self) -> None:
        self.assertEqual(matching_families("A study of BPC–157"), ("BPC-157",))
        self.assertEqual(matching_families("BPC pathway with 157 subjects"), ())
        self.assertEqual(
            matching_families("Tesamorelin and MOTS-c"),
            ("Tesamorelin", "MOTS-c"),
        )


class SelectionTests(unittest.TestCase):
    def test_round_robin_uses_family_order_and_lowest_numeric_pmid(self) -> None:
        documents = [
            Document("30", "BPC-157 later", "abstract"),
            Document("10", "BPC-157 first", "abstract"),
            Document("20", "GHK-Cu first", "abstract"),
            Document("40", "GHK-Cu second", "abstract"),
            Document("50", "Tesamorelin first", "abstract"),
        ]

        selected = select_documents(documents, 5)

        self.assertEqual(
            [(item.family, item.document.id) for item in selected],
            [
                ("BPC-157", "10"),
                ("GHK-Cu", "20"),
                ("Tesamorelin", "50"),
                ("BPC-157", "30"),
                ("GHK-Cu", "40"),
            ],
        )

    def test_selection_excludes_empty_title_or_abstract_and_fills(self) -> None:
        documents = [
            Document("1", "BPC-157", ""),
            Document("2", "", "abstract"),
            Document("3", "Unmatched eligible title", "abstract"),
            Document("4", "Another unmatched title", "abstract"),
        ]

        selected = select_documents(documents, 2)

        self.assertEqual([item.document.id for item in selected], ["3", "4"])
        self.assertEqual([item.family for item in selected], ["fallback", "fallback"])

    def test_selection_rejects_insufficient_eligible_documents(self) -> None:
        with self.assertRaises(ReviewPreparationError):
            select_documents([Document("1", "Title", "")], 1)


class PacketTests(unittest.TestCase):
    def test_packet_records_hash_candidates_and_non_qrels_status(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            corpus = Path(directory) / "corpus.jsonl"
            records = [
                {"id": "10", "title": "BPC-157 effects", "text": "A"},
                {"id": "20", "title": "GHK-Cu effects", "text": "B"},
            ]
            corpus.write_text(
                "".join(json.dumps(record) + "\n" for record in records),
                encoding="utf-8",
            )

            packet = build_packet(corpus, 2)

            self.assertEqual(packet["status"], "candidate_selection_only_not_qrels")
            self.assertEqual(packet["selection_count"], 2)
            self.assertEqual(
                [candidate["id"] for candidate in packet["candidates"]],  # type: ignore[index]
                ["q01", "q02"],
            )
            self.assertEqual(len(packet["corpus_sha256"]), 64)  # type: ignore[arg-type]

    def test_atomic_writer_refuses_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "candidates.json"
            write_json_atomic({"status": "first"}, output, overwrite=False)
            with self.assertRaises(ReviewPreparationError):
                write_json_atomic({"status": "second"}, output, overwrite=False)
            self.assertEqual(json.loads(output.read_text())["status"], "first")


if __name__ == "__main__":
    unittest.main()

"""A validated, positional inverted index for the frozen PubMed corpus."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Iterable

from src.analysis import AnalysisConfig, BASELINE_ANALYSIS, analyze
from src.models import Document, Posting


def _pmid_sort_key(document_id: str) -> tuple[int, str]:
    """Return the deterministic numeric ordering key for a PMID."""

    if not isinstance(document_id, str) or not document_id or not document_id.isdigit():
        raise ValueError("document id must be a non-empty numeric PMID string")
    return (int(document_id), document_id)


def _validate_document(document: object) -> Document:
    if not isinstance(document, Document):
        raise ValueError("each corpus item must be a Document")
    _pmid_sort_key(document.id)
    if not isinstance(document.title, str) or not isinstance(document.text, str):
        raise ValueError("document title and text must be strings")
    return document


@dataclass(frozen=True)
class InvertedIndex:
    """Immutable-posting index plus the data needed by Boolean and BM25 stages."""

    postings: dict[str, tuple[Posting, ...]]
    document_frequency: dict[str, int]
    documents: dict[str, Document]
    document_lengths: dict[str, int]
    analysis_config: AnalysisConfig = BASELINE_ANALYSIS
    title_lengths: dict[str, int] | None = None

    def __post_init__(self) -> None:
        """Reject indices whose stored structures disagree with one another."""

        if not isinstance(self.analysis_config, AnalysisConfig):
            raise ValueError("analysis config must be an AnalysisConfig")
        if self.title_lengths is None:
            object.__setattr__(
                self,
                "title_lengths",
                {
                    document_id: len(analyze(document.title, self.analysis_config))
                    for document_id, document in self.documents.items()
                },
            )
        if set(self.document_lengths) != set(self.documents):
            raise ValueError("document lengths must have exactly the document ids")
        if self.title_lengths is None or set(self.title_lengths) != set(self.documents):
            raise ValueError("title lengths must have exactly the document ids")
        if set(self.postings) != set(self.document_frequency):
            raise ValueError("document frequencies must have exactly the posting terms")

        expected: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
        for document_id, document in self.documents.items():
            _validate_document(document)
            if document_id != document.id:
                raise ValueError("document dictionary key must equal document id")
            title_tokens = analyze(document.title, self.analysis_config)
            tokens = title_tokens + analyze(document.text, self.analysis_config)
            if self.title_lengths[document_id] != len(title_tokens):
                raise ValueError("title length does not match analyzed title")
            if self.document_lengths[document_id] != len(tokens):
                raise ValueError("document length does not match analyzed document")
            for position, term in enumerate(tokens):
                expected[term][document_id].append(position)

        if set(expected) != set(self.postings):
            raise ValueError("postings do not match analyzed documents")
        for term, term_postings in self.postings.items():
            if not isinstance(term, str) or not term:
                raise ValueError("posting terms must be non-empty strings")
            if not isinstance(term_postings, tuple) or not term_postings:
                raise ValueError("posting lists must be non-empty tuples")
            if self.document_frequency[term] != len(term_postings):
                raise ValueError("document frequency does not match posting count")

            observed_ids: list[str] = []
            for posting in term_postings:
                if not isinstance(posting, Posting):
                    raise ValueError("posting lists must contain Posting values")
                _pmid_sort_key(posting.doc_id)
                if posting.doc_id not in self.documents:
                    raise ValueError("posting references an unknown document")
                if not isinstance(posting.positions, tuple) or not posting.positions:
                    raise ValueError("posting positions must be non-empty tuples")
                if any(
                    not isinstance(position, int) or isinstance(position, bool)
                    for position in posting.positions
                ) or any(
                    later <= earlier
                    for earlier, later in zip(posting.positions, posting.positions[1:])
                ):
                    raise ValueError("posting positions must be strictly increasing integers")
                if tuple(expected[term].get(posting.doc_id, ())) != posting.positions:
                    raise ValueError("posting positions do not match analyzed document")
                observed_ids.append(posting.doc_id)

            if len(set(observed_ids)) != len(observed_ids):
                raise ValueError("a document may appear only once in a posting list")
            if observed_ids != sorted(observed_ids, key=_pmid_sort_key):
                raise ValueError("posting lists must be ordered by numeric PMID")
            if set(observed_ids) != set(expected[term]):
                raise ValueError("posting list does not include every indexed document")

    @classmethod
    def from_documents(
        cls,
        documents: Iterable[Document],
        *,
        analysis_config: AnalysisConfig = BASELINE_ANALYSIS,
    ) -> InvertedIndex:
        """Build a validated index from unique corpus documents."""

        stored_documents: dict[str, Document] = {}
        positions_by_term: dict[str, dict[str, list[int]]] = defaultdict(
            lambda: defaultdict(list)
        )
        lengths: dict[str, int] = {}
        title_lengths: dict[str, int] = {}
        for item in documents:
            document = _validate_document(item)
            if document.id in stored_documents:
                raise ValueError(f"duplicate document id: {document.id}")
            stored_documents[document.id] = document
            title_tokens = analyze(document.title, analysis_config)
            tokens = title_tokens + analyze(document.text, analysis_config)
            lengths[document.id] = len(tokens)
            title_lengths[document.id] = len(title_tokens)
            for position, term in enumerate(tokens):
                positions_by_term[term][document.id].append(position)

        postings: dict[str, tuple[Posting, ...]] = {}
        for term, documents_for_term in positions_by_term.items():
            postings[term] = tuple(
                Posting(document_id, tuple(positions))
                for document_id, positions in sorted(
                    documents_for_term.items(), key=lambda item: _pmid_sort_key(item[0])
                )
            )
        frequencies = {term: len(term_postings) for term, term_postings in postings.items()}
        return cls(
            postings,
            frequencies,
            stored_documents,
            lengths,
            analysis_config,
            title_lengths,
        )

    @classmethod
    def from_jsonl(
        cls,
        path: Path,
        *,
        analysis_config: AnalysisConfig = BASELINE_ANALYSIS,
    ) -> InvertedIndex:
        """Read strictly shaped UTF-8 corpus JSONL records and build an index."""

        documents: list[Document] = []
        try:
            with Path(path).open("r", encoding="utf-8") as corpus_file:
                for line_number, line in enumerate(corpus_file, start=1):
                    if not line.strip():
                        raise ValueError(f"line {line_number}: blank JSONL record")
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError as error:
                        raise ValueError(f"line {line_number}: invalid JSON") from error
                    if not isinstance(record, dict) or set(record) != {"id", "title", "text"}:
                        raise ValueError(f"line {line_number}: record must have exactly id, title, text")
                    if any(not isinstance(record[key], str) for key in ("id", "title", "text")):
                        raise ValueError(f"line {line_number}: record values must be strings")
                    documents.append(Document(record["id"], record["title"], record["text"]))
        except UnicodeDecodeError as error:
            raise ValueError("corpus must be UTF-8 JSONL") from error
        return cls.from_documents(documents, analysis_config=analysis_config)

    def doc_ids(self, term: str) -> tuple[str, ...]:
        """Return the numeric-PMID-ordered document ids containing an exact term."""

        return tuple(posting.doc_id for posting in self.postings.get(term, ()))

    def without_document(self, doc_id: str) -> InvertedIndex:
        """Return a new valid index without ``doc_id``; leave this index intact."""

        _pmid_sort_key(doc_id)
        if doc_id not in self.documents:
            raise ValueError(f"unknown document id: {doc_id}")
        return type(self).from_documents(
            (document for current_id, document in self.documents.items() if current_id != doc_id),
            analysis_config=self.analysis_config,
        )

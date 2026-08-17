"""Deterministic Boolean retrieval over the project inverted index."""

from __future__ import annotations

from .analysis import analyze
from .index import InvertedIndex


_OPERATORS = {"and", "or"}


def _operand(index: InvertedIndex, raw_term: str) -> set[str]:
    """Resolve an analyzed whitespace token; its terms are implicitly ANDed."""

    terms = analyze(raw_term, index.analysis_config)
    if not terms:
        return set()

    result: set[str] | None = None
    for term in terms:
        docs = set(index.doc_ids(term))
        result = docs if result is None else result & docs
    return result if result is not None else set()


def search_boolean(index: InvertedIndex, query: str) -> list[str]:
    """Return PMIDs matching a small AND/OR query, ordered numerically.

    Operators must be individual whitespace-delimited words.  All other words
    are analyzed with the shared pipeline, so punctuation (including hyphens)
    creates adjacent terms joined by implicit AND.
    """

    operands: list[set[str]] = []
    operators: list[str] = []
    expecting_operand = True

    for raw_token in query.split():
        operator = raw_token.casefold()
        if operator in _OPERATORS:
            if expecting_operand:
                return []
            operators.append(operator)
            expecting_operand = True
            continue

        # Punctuation-only tokens do not make an operand.
        if not analyze(raw_token, index.analysis_config):
            continue
        operands.append(_operand(index, raw_token))
        if not expecting_operand:
            operators.append("and")
        expecting_operand = False

    if not operands or expecting_operand:
        return []

    # Operators and operands now strictly alternate.  Evaluate each AND run,
    # then union those runs to give AND its intended higher precedence.
    clauses: list[set[str]] = []
    current = set(operands[0])
    for operator, operand in zip(operators, operands[1:]):
        if operator == "and":
            current &= operand
        else:
            clauses.append(current)
            current = operand
    clauses.append(current)

    matches: set[str] = set()
    for clause in clauses:
        matches |= clause
    return sorted(matches, key=int)

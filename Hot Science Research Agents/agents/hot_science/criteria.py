"""Criteria helpers shared by Hot Science CLI and web entrypoints."""

from __future__ import annotations

from pathlib import Path


def resolve_criteria_text(criteria: str | None, criteria_file: str | None) -> str | None:
    """Resolve inline or file-based run criteria into normalized text."""
    if criteria and criteria_file:
        raise ValueError("Use either criteria text or a criteria file, not both.")
    if criteria_file:
        return read_required_text(criteria_file, "criteria file")
    return normalize_criteria_text(criteria)


def resolve_retrieval_query_text(
    criteria: str | None,
    criteria_file: str | None,
    query: str | None,
    query_file: str | None,
) -> str | None:
    """Resolve the concise source-API query separately from the full criteria."""
    if query and query_file:
        raise ValueError("Use either query text or a query file, not both.")
    if query_file:
        return compact_query(read_required_text(query_file, "query file"))
    if query:
        return compact_query(query)
    if criteria_file:
        criteria_text = read_required_text(criteria_file, "criteria file")
        extracted = extract_retrieval_query(criteria_text)
        return compact_query(extracted) if extracted else ""
    if criteria:
        extracted = extract_retrieval_query(criteria)
        return compact_query(extracted or criteria)
    return None


def normalize_criteria_text(value: str | None) -> str | None:
    """Trim criteria text while preserving intentional line breaks."""
    if value is None:
        return None
    normalized_lines = [line.rstrip() for line in value.strip().splitlines()]
    normalized = "\n".join(normalized_lines).strip()
    return normalized or None


def extract_retrieval_query(text: str) -> str | None:
    """Extract an optional short query embedded in a long criteria brief."""
    for line in text.splitlines():
        stripped = line.strip().lstrip("-").strip()
        lowered = stripped.casefold()
        for prefix in (
            "api search query:",
            "retrieval query:",
            "search query:",
            "query:",
        ):
            if lowered.startswith(prefix):
                value = stripped[len(prefix) :].strip()
                return value or None
    return None


def read_required_text(path_text: str, label: str) -> str:
    """Read a required text file and return normalized contents."""
    path = Path(path_text)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"Could not read {label} '{path_text}': {exc}") from exc
    normalized = normalize_criteria_text(text)
    if not normalized:
        raise ValueError(f"{label} '{path_text}' is empty.")
    return normalized


def compact_query(value: str) -> str:
    """Normalize a query for source APIs and cap it to a safe length."""
    return " ".join(value.split())[:240]

#!/usr/bin/env python3
"""Inspect one Hot Science candidate in the local SQLite store."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.hot_science.config import load_hot_science_config
from agents.hot_science.schema import CandidateRecord
from agents.hot_science.storage import CandidateStore


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Diagnose provenance/date/audit details for one Hot Science candidate."
    )
    parser.add_argument(
        "--db",
        default=".deepgreen/hot_science/candidates.sqlite3",
        help="SQLite candidate store path.",
    )
    parser.add_argument(
        "--target-month",
        default=None,
        help="Optional target month filter in YYYY-MM format.",
    )
    parser.add_argument(
        "--needle",
        action="append",
        required=True,
        help=(
            "Text to search for in title, DOI, URLs, source notes, abstract, or audit "
            "details. Repeat to require multiple matches."
        ),
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Optional source YAML config path for source-name to source-id inference.",
    )
    parser.add_argument(
        "--json-out",
        default=None,
        help="Optional path to write the diagnostic JSON.",
    )
    args = parser.parse_args()

    config = load_hot_science_config(args.config)
    source_name_to_id = {source.name: source.id for source in config.sources}
    store = CandidateStore(args.db)
    candidates = store.list_candidates(args.target_month)
    matches = [
        candidate
        for candidate in candidates
        if _candidate_matches(candidate, args.needle)
    ]
    diagnostic = {
        "db": str(Path(args.db)),
        "target_month": args.target_month,
        "needles": args.needle,
        "match_count": len(matches),
        "matches": [
            _diagnostic_payload(candidate, source_name_to_id) for candidate in matches
        ],
        "limitations": [
            (
                "SourceMention stores the configured source display name, not the "
                "source id. source_id values in this output are inferred by matching "
                "that display name to config/hot_science_sources.yaml."
            ),
            (
                "The current verifier records the normalized online_publication_date "
                "it used, but the source clients do not preserve the raw date field "
                "name and raw date value in a structured field."
            ),
        ],
    }

    output = json.dumps(diagnostic, indent=2, sort_keys=True)
    print(output)
    if args.json_out:
        output_path = Path(args.json_out)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output + "\n")


def _candidate_matches(candidate: CandidateRecord, needles: list[str]) -> bool:
    haystack = json.dumps(candidate.to_dict(), sort_keys=True).casefold()
    return all(needle.casefold() in haystack for needle in needles)


def _diagnostic_payload(
    candidate: CandidateRecord,
    source_name_to_id: dict[str, str],
) -> dict[str, Any]:
    return {
        "candidate_id": candidate.candidate_id,
        "title": candidate.title,
        "source_status": candidate.source_status,
        "target_month": candidate.target_month,
        "doi": candidate.doi,
        "normalized_doi": candidate.normalized_doi(),
        "primary_source_url": candidate.publication.primary_source_url,
        "publication_url": candidate.publication.url,
        "online_publication_date": candidate.publication.online_publication_date,
        "issue_publication_date": candidate.publication.issue_publication_date,
        "venue": candidate.publication.venue,
        "venue_type": candidate.publication.venue_type,
        "verification": candidate.verification.__dict__,
        "discovered_via": [
            {
                "source": mention.source,
                "inferred_source_id": source_name_to_id.get(mention.source),
                "url": mention.url,
                "date_seen": mention.date_seen,
                "source_type": mention.source_type,
                "note": mention.note,
            }
            for mention in candidate.discovered_via
        ],
        "press_coverage": [coverage.__dict__ for coverage in candidate.press_coverage],
        "exclusion_flags": [flag.__dict__ for flag in candidate.exclusion_flags],
        "missing_reasons": candidate.missing_reasons,
        "audit_trail": [event.__dict__ for event in candidate.audit_trail],
    }


if __name__ == "__main__":
    main()

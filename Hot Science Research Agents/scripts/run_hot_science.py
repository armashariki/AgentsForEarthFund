#!/usr/bin/env python3
"""Run the UC-I-1 Hot Science research monitoring pipeline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.hot_science.compiler import CompilerAgent
from agents.hot_science.config import load_hot_science_config
from agents.hot_science.criteria import (
    extract_retrieval_query,
    compact_query,
    read_required_text,
    resolve_criteria_text,
    resolve_retrieval_query_text,
)
from agents.hot_science.orchestrator import HotScienceOrchestrator
from agents.hot_science.storage import CandidateStore


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run DeepGreen UC-I-1 Hot Science monitoring."
    )
    parser.add_argument(
        "--target-month",
        required=True,
        help="Target publication month in YYYY-MM format.",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Optional path to source YAML config.",
    )
    parser.add_argument(
        "--db",
        default=".deepgreen/hot_science/candidates.sqlite3",
        help="SQLite candidate store path.",
    )
    parser.add_argument(
        "--source",
        action="append",
        default=None,
        help="Restrict run to a source id. Repeat for multiple sources.",
    )
    parser.add_argument(
        "--criteria",
        default=None,
        help=(
            "Optional plain-language search focus, such as "
            "'extreme heat and human health impacts'."
        ),
    )
    parser.add_argument(
        "--criteria-file",
        default=None,
        help=(
            "Optional path to a Markdown/text file containing a longer search "
            "brief. Use this instead of --criteria for page-long instructions."
        ),
    )
    parser.add_argument(
        "--query",
        default=None,
        help=(
            "Optional concise API search query. Use this with --criteria-file "
            "so APIs receive a short query while the full brief guides filtering."
        ),
    )
    parser.add_argument(
        "--query-file",
        default=None,
        help="Optional path to a text file containing a concise API search query.",
    )
    parser.add_argument(
        "--max-results-per-source",
        type=int,
        default=25,
        help="Maximum records to pull per source.",
    )
    parser.add_argument(
        "--json-out",
        default=None,
        help="Write compiled candidate JSON to this path.",
    )
    parser.add_argument(
        "--markdown-out",
        default=None,
        help="Write Word-doc-friendly Markdown draft to this path.",
    )
    parser.add_argument(
        "--review-csv-out",
        default=None,
        help="Write spreadsheet-friendly candidate review CSV to this path.",
    )
    parser.add_argument(
        "--source-breakdown-csv-out",
        default=None,
        help="Write per-source verified/manual-review/excluded count CSV to this path.",
    )
    args = parser.parse_args()
    criteria = resolve_criteria(args.criteria, args.criteria_file)
    retrieval_query = resolve_retrieval_query(
        args.criteria,
        args.criteria_file,
        args.query,
        args.query_file,
    )

    config = load_hot_science_config(args.config)
    store = CandidateStore(args.db)
    orchestrator = HotScienceOrchestrator(config=config, store=store)
    result = orchestrator.run(
        args.target_month,
        max_results_per_source=args.max_results_per_source,
        source_ids=set(args.source) if args.source else None,
        user_criteria=criteria,
        retrieval_query=retrieval_query,
    )

    print(json.dumps(result.summary, indent=2, sort_keys=True))

    if result.compiled:
        compiler = CompilerAgent()
        if args.json_out:
            compiler.write_json(result.compiled, args.json_out)
            print(f"Wrote JSON: {args.json_out}")
        if args.markdown_out:
            compiler.write_markdown(result.compiled, args.markdown_out)
            print(f"Wrote Markdown: {args.markdown_out}")
        if args.review_csv_out:
            compiler.write_review_csv(result.compiled, args.review_csv_out)
            print(f"Wrote review CSV: {args.review_csv_out}")
        if args.source_breakdown_csv_out:
            compiler.write_source_breakdown_csv(
                result.compiled,
                args.source_breakdown_csv_out,
                sources=config.sources,
                source_errors=result.source_errors,
            )
            print(f"Wrote source breakdown CSV: {args.source_breakdown_csv_out}")

    if result.source_errors:
        print("\nSource errors:")
        for candidate in result.source_errors:
            detail = candidate.discovered_via[0].note if candidate.discovered_via else ""
            print(f"- {candidate.publication.venue}: {detail}")


def resolve_criteria(criteria: str | None, criteria_file: str | None) -> str | None:
    """Resolve inline or file-based run-specific search criteria."""
    if criteria and criteria_file:
        raise SystemExit("Use either --criteria or --criteria-file, not both.")
    try:
        return resolve_criteria_text(criteria, criteria_file)
    except ValueError as exc:
        raise SystemExit(str(exc).replace("criteria file", "--criteria-file")) from exc


def resolve_retrieval_query(
    criteria: str | None,
    criteria_file: str | None,
    query: str | None,
    query_file: str | None,
) -> str | None:
    """Resolve the short API search query separately from the full criteria."""
    if query and query_file:
        raise SystemExit("Use either --query or --query-file, not both.")
    try:
        return resolve_retrieval_query_text(criteria, criteria_file, query, query_file)
    except ValueError as exc:
        message = (
            str(exc)
            .replace("criteria file", "--criteria-file")
            .replace("query file", "--query-file")
            .replace("query text", "--query")
        )
        raise SystemExit(message) from exc


if __name__ == "__main__":
    main()

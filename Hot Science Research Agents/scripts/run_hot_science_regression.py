#!/usr/bin/env python3
"""Run Hot Science April 2026 regression diagnostics from reviewer fixtures."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.hot_science.config import load_hot_science_config
from agents.hot_science.evaluator import SignificanceEvaluatorAgent
from agents.hot_science.schema import CandidateRecord
from agents.hot_science.verification import VerificationAgent


DEFAULT_FIXTURE = Path("tests/fixtures/hot_science_calibration_cases.json")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run deterministic Hot Science April 2026 regression diagnostics."
    )
    parser.add_argument("--fixture", default=str(DEFAULT_FIXTURE))
    parser.add_argument("--json-out", default=None)
    parser.add_argument("--markdown-out", default=None)
    args = parser.parse_args()

    report = run_regression(Path(args.fixture))
    print(json.dumps(report["summary"], indent=2, sort_keys=True))

    if args.json_out:
        output = Path(args.json_out)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, sort_keys=True))
    if args.markdown_out:
        output = Path(args.markdown_out)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(markdown_report(report))


def run_regression(fixture_path: Path) -> dict[str, Any]:
    fixture = json.loads(fixture_path.read_text())
    config = load_hot_science_config()
    evaluator = SignificanceEvaluatorAgent(config)
    verifier = VerificationAgent(non_target_month_watchlist=True)
    cases = []
    for case in fixture["cases"]:
        result = evaluate_case(case, fixture["target_month"], evaluator, verifier)
        cases.append(result)

    passed = sum(1 for case in cases if case["passed"])
    failed = len(cases) - passed
    issn_sources = [
        {
            "id": source.id,
            "name": source.name,
            "issns": list(source.issns),
            "enabled": source.enabled,
        }
        for source in config.sources
        if source.source_type == "peer_reviewed_journal" and source.issns
    ]
    return {
        "fixture_version": fixture["fixture_version"],
        "target_month": fixture["target_month"],
        "run_focus": fixture["run_focus"],
        "summary": {
            "target_month": fixture["target_month"],
            "total_cases": len(cases),
            "passed": passed,
            "failed": failed,
            "status": "passed" if failed == 0 else "failed",
            "rubric_version": config.rubric.version,
            "issn_backfill_sources": len(issn_sources),
        },
        "cases": cases,
        "retrieval_diagnostics": {
            "journal_issn_month_backfill": "enabled",
            "sources": issn_sources,
        },
    }


def evaluate_case(
    case: dict[str, Any],
    target_month: str,
    evaluator: SignificanceEvaluatorAgent,
    verifier: VerificationAgent,
) -> dict[str, Any]:
    expected_bucket = case["expected_bucket"]
    expected_reason = case["expected_reason_code"]

    if case["id"] == "artifact_sea_land_breeze_zenodo_deposit":
        artifact = candidate_from_case(case)
        canonical = CandidateRecord.from_dict(case["canonical_primary"])
        verification = VerificationAgent().verify([artifact, canonical], target_month)
        actual_bucket = "candidate" if verification.verified else "excluded"
        actual_reason = artifact.routing_reason or ""
        passed = (
            actual_bucket == expected_bucket
            and actual_reason == expected_reason
            and bool(verification.verified)
            and artifact.candidate_id in verification.verified[0].verification.consolidated_from
        )
        return case_result(case, actual_bucket, actual_reason, passed, verification.verified[0] if verification.verified else artifact)

    candidate = candidate_from_case(case)
    if expected_bucket in {"candidate", "excluded", "preprint"}:
        evaluation = evaluator.evaluate([candidate])
        if evaluation.evaluated:
            actual_bucket = "candidate"
            routed = evaluation.evaluated[0]
        elif evaluation.preprints:
            actual_bucket = "preprint"
            routed = evaluation.preprints[0]
        else:
            actual_bucket = "excluded"
            routed = evaluation.excluded[0]
        actual_reason = routed.routing_reason or first_flag_code(routed)
        passed = actual_bucket == expected_bucket and actual_reason == expected_reason
        if expected_bucket == "excluded":
            if expected_reason in flag_codes(routed):
                actual_reason = expected_reason
            passed = actual_bucket == expected_bucket and expected_reason in flag_codes(routed)
        return case_result(case, actual_bucket, actual_reason, passed, routed)

    verification = verifier.verify([candidate], target_month)
    if verification.verified:
        actual_bucket = "candidate"
        routed = verification.verified[0]
    elif verification.manual_review:
        routed = verification.manual_review[0]
        actual_bucket = "watchlist" if routed.watchlist_reason else "manual_review"
    else:
        actual_bucket = "excluded"
        routed = verification.excluded[0]
    actual_reason = routed.watchlist_reason or routed.routing_reason or first_flag_code(routed)
    passed = actual_bucket == expected_bucket and actual_reason == expected_reason
    return case_result(case, actual_bucket, actual_reason, passed, routed)


def case_result(
    case: dict[str, Any],
    actual_bucket: str,
    actual_reason: str,
    passed: bool,
    candidate: CandidateRecord,
) -> dict[str, Any]:
    return {
        "id": case["id"],
        "title": candidate.title,
        "expected_bucket": case["expected_bucket"],
        "actual_bucket": actual_bucket,
        "expected_reason_code": case["expected_reason_code"],
        "actual_reason_code": actual_reason,
        "passed": passed,
        "generalized_rule": case["generalized_rule"],
        "reviewer_signal": case["reviewer_signal"],
        "domain_tags": candidate.fit_assessment.supported_domain_tags or candidate.topic_tags,
    }


def markdown_report(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        f"# Hot Science Regression Diagnostics - {summary['target_month']}",
        "",
        "## Summary",
        "",
        f"- Status: {summary['status'].upper()}",
        f"- Cases passed: {summary['passed']} of {summary['total_cases']}",
        f"- Rubric version: {summary['rubric_version']}",
        f"- ISSN/month backfill sources enabled: {summary['issn_backfill_sources']}",
        "",
        "## What Changed",
        "",
        "- Reviewer feedback was converted into deterministic calibration cases.",
        "- Primary-work selection now prefers canonical articles over artifacts.",
        "- Date discipline uses canonical primary publication dates.",
        "- Evidence-of-fit now requires abstract or primary metadata support.",
        "- Preprints, watchlist items, manual review, and exclusions are separated.",
        "- Journal RSS coverage is supplemented by scholarly API ISSN/month backfills.",
        "",
        "## Case Results",
        "",
    ]
    for case in report["cases"]:
        status = "PASS" if case["passed"] else "FAIL"
        lines.extend(
            [
                f"### {status}: {case['id']}",
                "",
                f"- Title: {case['title']}",
                f"- Expected: {case['expected_bucket']} / {case['expected_reason_code']}",
                f"- Actual: {case['actual_bucket']} / {case['actual_reason_code']}",
                f"- Rule: {case['generalized_rule']}",
                "",
            ]
        )
    lines.extend(
        [
            "## Retrieval Diagnostics",
            "",
            "- Journal ISSN/month backfill: enabled",
        ]
    )
    for source in report["retrieval_diagnostics"]["sources"]:
        lines.append(
            f"- {source['name']} ({source['id']}): {', '.join(source['issns'])}"
        )
    return "\n".join(lines) + "\n"


def candidate_from_case(case: dict[str, Any]) -> CandidateRecord:
    return CandidateRecord.from_dict(case["candidate"])


def flag_codes(candidate: CandidateRecord) -> set[str]:
    return {flag.code for flag in candidate.exclusion_flags}


def first_flag_code(candidate: CandidateRecord) -> str:
    return candidate.exclusion_flags[0].code if candidate.exclusion_flags else ""


if __name__ == "__main__":
    main()

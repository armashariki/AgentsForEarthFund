"""Reviewer-derived calibration tests for Hot Science v2 behavior."""

from __future__ import annotations

import json
from pathlib import Path

from agents.hot_science.evaluator import SignificanceEvaluatorAgent
from agents.hot_science.schema import CandidateRecord
from agents.hot_science.verification import VerificationAgent
from scripts.run_hot_science_regression import run_regression


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "hot_science_calibration_cases.json"


def load_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text())


def cases_by_bucket(bucket: str) -> list[dict]:
    return [
        case
        for case in load_fixture()["cases"]
        if case["expected_bucket"] == bucket
    ]


def candidate_from_case(case: dict) -> CandidateRecord:
    return CandidateRecord.from_dict(case["candidate"])


def flag_codes(candidate: CandidateRecord) -> set[str]:
    return {flag.code for flag in candidate.exclusion_flags}


def test_calibration_fixture_is_reviewable_and_unique():
    fixture = load_fixture()

    assert fixture["fixture_version"] == "hot_science_calibration_v1"
    assert fixture["target_month"] == "2026-04"
    assert fixture["run_focus"]
    assert fixture["source_documents"]

    ids = [case["id"] for case in fixture["cases"]]
    assert len(ids) == len(set(ids))
    assert len(ids) >= 12
    assert {
        "candidate",
        "excluded",
        "watchlist",
        "manual_review",
        "preprint",
    }.issubset({case["expected_bucket"] for case in fixture["cases"]})


def test_calibration_candidates_deserialize_to_phase1_schema():
    for case in load_fixture()["cases"]:
        candidate = candidate_from_case(case)

        assert candidate.title
        assert case["reviewer_signal"]
        assert case["generalized_rule"]
        assert case["expected_reason_code"]
        assert candidate.target_month == load_fixture()["target_month"]
        assert candidate.fit_assessment.passed is None
        assert candidate.date_eligibility.eligible is None


def test_calibration_cases_cover_required_reviewer_failure_modes():
    case_ids = {case["id"] for case in load_fixture()["cases"]}

    assert "keep_hidden_ocean_heat_antarctica" in case_ids
    assert "exclude_cascadia_subduction_geology" in case_ids
    assert "exclude_twelve_apostles_formation_history" in case_ids
    assert "exclude_east_africa_rifting_tectonics" in case_ids
    assert "watchlist_alaska_salmon_predator_wrong_month" in case_ids
    assert "artifact_sea_land_breeze_zenodo_deposit" in case_ids
    assert "exclude_airborne_microplastics_ambiguous_emissions" in case_ids
    assert "exclude_arctic_sea_ice_thickness_methods_only" in case_ids
    assert "exclude_turkish_textbooks_social_science" in case_ids
    assert "manual_review_title_only_plausible_climate_item" in case_ids
    assert "preprint_separate_bucket_eartharxiv" in case_ids


def test_april_2026_regression_diagnostics_pass_all_cases():
    report = run_regression(FIXTURE_PATH)

    assert report["summary"]["status"] == "passed"
    assert report["summary"]["passed"] == report["summary"]["total_cases"]
    assert report["summary"]["issn_backfill_sources"] >= 7


def test_calibration_keep_cases_pass_abstract_first_fit_gate():
    evaluator = SignificanceEvaluatorAgent()
    keep_cases = [
        case
        for case in cases_by_bucket("candidate")
        if case["expected_reason_code"] == "evidence_fit_in_target_month"
    ]
    assert keep_cases
    for case in keep_cases:
        candidate = evaluator.evaluate([candidate_from_case(case)]).evaluated[0]

        assert candidate.fit_assessment.passed is True
        assert candidate.fit_assessment.evidence_source in {"abstract", "primary_metadata"}
        assert case["expected_reason_code"] == candidate.routing_reason
        for tag in case.get("expected_domain_tags", []):
            assert tag in candidate.fit_assessment.supported_domain_tags


def test_calibration_exclude_cases_get_expected_general_rule_codes():
    evaluator = SignificanceEvaluatorAgent()
    for case in cases_by_bucket("excluded"):
        result = evaluator.evaluate([candidate_from_case(case)])

        assert not result.evaluated
        assert result.excluded
        assert case["expected_reason_code"] in flag_codes(result.excluded[0])
        assert result.excluded[0].fit_assessment.passed is False


def test_calibration_wrong_month_relevant_cases_route_to_watchlist():
    verifier = VerificationAgent(non_target_month_watchlist=True)
    case = cases_by_bucket("watchlist")[0]
    result = verifier.verify([candidate_from_case(case)], load_fixture()["target_month"])

    assert not result.verified
    assert not result.excluded
    assert result.manual_review[0].watchlist_reason == case["expected_reason_code"]
    assert result.manual_review[0].date_eligibility.eligible is False


def test_calibration_title_only_plausible_item_routes_to_manual_review():
    verifier = VerificationAgent()
    case = cases_by_bucket("manual_review")[0]
    result = verifier.verify([candidate_from_case(case)], load_fixture()["target_month"])

    assert not result.verified
    assert result.manual_review
    assert result.manual_review[0].routing_reason == case["expected_reason_code"]


def test_calibration_preprints_are_separate_bucket_not_primary_exclusions():
    evaluator = SignificanceEvaluatorAgent()
    case = cases_by_bucket("preprint")[0]
    candidate = candidate_from_case(case)
    result = evaluator.evaluate([candidate])

    assert not result.evaluated
    assert not result.excluded
    assert result.preprints
    assert result.preprints[0].routing_reason == case["expected_reason_code"]


def test_calibration_artifact_identity_prefers_canonical_primary_work():
    case = next(
        case
        for case in load_fixture()["cases"]
        if case["id"] == "artifact_sea_land_breeze_zenodo_deposit"
    )
    artifact = candidate_from_case(case)
    canonical = CandidateRecord.from_dict(case["canonical_primary"])
    result = VerificationAgent().verify(
        [artifact, canonical],
        load_fixture()["target_month"],
    )

    assert len(result.verified) == 1
    assert result.verified[0].doi == canonical.normalized_doi()
    assert result.verified[0].publication.primary_work_type == "peer_reviewed_journal_article"
    assert artifact.candidate_id in result.verified[0].verification.consolidated_from

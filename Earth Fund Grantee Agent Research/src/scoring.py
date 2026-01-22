"""
Scoring Utilities for Grant Proposal Analysis

Provides functions for:
- Score to grade conversion
- Confidence level assessment
- Overall score aggregation
- Traffic light assignment
- Report card generation utilities

Copyright (c) 2024 Bezos Earth Fund
All rights reserved.
"""

from typing import List, Dict, Tuple, Optional
from datetime import datetime

from src.models import (
    ConfidenceLevel,
    TrafficLight,
    RecommendationLevel,
    DimensionScore,
    ReportCard,
    VerificationStatus,
    VerificationResult,
)


# ---------------------------
# Score to Grade Conversion
# ---------------------------

def score_to_grade(score: float) -> str:
    """
    Convert a numeric score (0-10) to a letter grade.

    Scale:
    - A  : 9.0 - 10.0 (Exceptional)
    - A- : 8.5 - 8.9
    - B+ : 8.0 - 8.4
    - B  : 7.0 - 7.9 (Good)
    - B- : 6.5 - 6.9
    - C+ : 6.0 - 6.4
    - C  : 5.0 - 5.9 (Fair)
    - C- : 4.5 - 4.9
    - D  : 3.0 - 4.4 (Poor)
    - F  : 0.0 - 2.9 (Fail)
    """
    if score >= 9.0:
        return "A"
    elif score >= 8.5:
        return "A-"
    elif score >= 8.0:
        return "B+"
    elif score >= 7.0:
        return "B"
    elif score >= 6.5:
        return "B-"
    elif score >= 6.0:
        return "C+"
    elif score >= 5.0:
        return "C"
    elif score >= 4.5:
        return "C-"
    elif score >= 3.0:
        return "D"
    else:
        return "F"


def grade_to_description(grade: str) -> str:
    """Return a description for a letter grade."""
    descriptions = {
        "A": "Exceptional - Strong recommend",
        "A-": "Excellent - Recommend",
        "B+": "Very Good - Recommend with minor notes",
        "B": "Good - Recommend with minor concerns",
        "B-": "Above Average - Some concerns to address",
        "C+": "Fair - Notable concerns",
        "C": "Fair - Significant concerns to address",
        "C-": "Below Average - Major concerns",
        "D": "Poor - Major issues identified",
        "F": "Fail - Critical problems",
    }
    return descriptions.get(grade, "Unknown")


# ---------------------------
# Traffic Light Assignment
# ---------------------------

def score_to_traffic_light(score: float) -> TrafficLight:
    """
    Assign traffic light status based on score.

    - GREEN: 7.0+ (Good to go)
    - YELLOW: 5.0 - 6.9 (Caution/attention needed)
    - RED: Below 5.0 (Significant concerns)
    """
    if score >= 7.0:
        return TrafficLight.GREEN
    elif score >= 5.0:
        return TrafficLight.YELLOW
    else:
        return TrafficLight.RED


def traffic_light_emoji(status: TrafficLight) -> str:
    """Return emoji for traffic light status."""
    emojis = {
        TrafficLight.GREEN: "🟢",
        TrafficLight.YELLOW: "🟡",
        TrafficLight.RED: "🔴",
    }
    return emojis.get(status, "⚪")


# ---------------------------
# Confidence Assessment
# ---------------------------

def assess_confidence(
    evidence_count: int,
    source_quality: str = "mixed",
    agreement_level: str = "partial"
) -> ConfidenceLevel:
    """
    Assess confidence level based on evidence quality.

    Args:
        evidence_count: Number of evidence sources found
        source_quality: "high" (peer-reviewed), "medium" (institutional), "low" (other)
        agreement_level: "strong" (sources agree), "partial", "conflicting"

    Returns:
        ConfidenceLevel enum value
    """
    score = 0

    # Evidence count contribution (0-3 points)
    if evidence_count >= 5:
        score += 3
    elif evidence_count >= 3:
        score += 2
    elif evidence_count >= 1:
        score += 1

    # Source quality contribution (0-3 points)
    quality_scores = {"high": 3, "medium": 2, "low": 1}
    score += quality_scores.get(source_quality, 1)

    # Agreement level contribution (0-2 points)
    agreement_scores = {"strong": 2, "partial": 1, "conflicting": 0}
    score += agreement_scores.get(agreement_level, 1)

    # Map total score to confidence level
    if score >= 7:
        return ConfidenceLevel.HIGH
    elif score >= 4:
        return ConfidenceLevel.MEDIUM
    else:
        return ConfidenceLevel.LOW


# ---------------------------
# Overall Score Calculation
# ---------------------------

# Default weights for each dimension (original 5-dimension system)
DEFAULT_WEIGHTS = {
    "Technical Feasibility": 0.25,
    "Innovation": 0.15,
    "Climate Impact": 0.25,
    "Budget": 0.15,
    "Team Credibility": 0.20,
}

# Enhanced weights including Strategic Fit (6-dimension system)
ENHANCED_WEIGHTS = {
    "Technical Feasibility": 0.20,
    "Innovation": 0.12,
    "Climate Impact": 0.20,
    "Budget": 0.12,
    "Team Credibility": 0.16,
    "Strategic Fit": 0.20,  # BEF Investment Criteria
}

# BEF Criteria category weights
BEF_CRITERIA_WEIGHTS = {
    "Why Do This": 0.40,   # Impact & Potential (most important)
    "Why Us": 0.30,        # Strategic Fit for BEF
    "Why Now": 0.30,       # Timing & Sustainability
}


def calculate_overall_score(
    dimension_scores: List[DimensionScore],
    weights: Optional[Dict[str, float]] = None
) -> Tuple[float, str, ConfidenceLevel]:
    """
    Calculate weighted overall score from dimension scores.

    Args:
        dimension_scores: List of DimensionScore objects
        weights: Optional custom weights (defaults to DEFAULT_WEIGHTS)

    Returns:
        Tuple of (overall_score, overall_grade, overall_confidence)
    """
    if not dimension_scores:
        return 0.0, "F", ConfidenceLevel.LOW

    weights = weights or DEFAULT_WEIGHTS

    total_weight = 0.0
    weighted_sum = 0.0
    confidence_scores = []

    for dim in dimension_scores:
        weight = weights.get(dim.dimension, 0.15)  # Default weight if not specified
        weighted_sum += dim.score * weight
        total_weight += weight

        # Map confidence to numeric for averaging
        conf_values = {ConfidenceLevel.HIGH: 3, ConfidenceLevel.MEDIUM: 2, ConfidenceLevel.LOW: 1}
        confidence_scores.append(conf_values.get(dim.confidence, 2))

    # Calculate overall score
    overall_score = weighted_sum / total_weight if total_weight > 0 else 0.0
    overall_grade = score_to_grade(overall_score)

    # Calculate overall confidence (average)
    avg_confidence = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 2
    if avg_confidence >= 2.5:
        overall_confidence = ConfidenceLevel.HIGH
    elif avg_confidence >= 1.5:
        overall_confidence = ConfidenceLevel.MEDIUM
    else:
        overall_confidence = ConfidenceLevel.LOW

    return round(overall_score, 1), overall_grade, overall_confidence


# ---------------------------
# Recommendation Determination
# ---------------------------

def determine_recommendation(
    overall_score: float,
    dimension_scores: List[DimensionScore],
    verification_results: List[VerificationResult]
) -> Tuple[RecommendationLevel, str, List[str]]:
    """
    Determine funding recommendation based on scores and verifications.

    Returns:
        Tuple of (recommendation, summary, conditions)
    """
    conditions = []

    # Check for any red flags (dimension score < 4)
    red_flag_dimensions = [d for d in dimension_scores if d.score < 4.0]
    yellow_flag_dimensions = [d for d in dimension_scores if 4.0 <= d.score < 6.0]

    # Check verification failures
    unverified_claims = [v for v in verification_results
                         if v.status in [VerificationStatus.NOT_VERIFIED, VerificationStatus.UNSUBSTANTIATED]]

    # Decision logic
    if overall_score >= 8.0 and not red_flag_dimensions:
        if unverified_claims:
            recommendation = RecommendationLevel.FUND_WITH_CONDITIONS
            summary = f"Strong proposal with {len(unverified_claims)} claim(s) requiring verification."
            conditions = [f"Verify claim: {v.claim}" for v in unverified_claims[:3]]
        else:
            recommendation = RecommendationLevel.FUND
            summary = "Excellent proposal across all dimensions with verified claims."

    elif overall_score >= 6.5 and not red_flag_dimensions:
        recommendation = RecommendationLevel.FUND_WITH_CONDITIONS
        summary = "Good proposal with areas requiring attention or clarification."

        # Add conditions for yellow flags
        for dim in yellow_flag_dimensions:
            if dim.key_concern:
                conditions.append(f"Address {dim.dimension}: {dim.key_concern}")

        # Add conditions for unverified claims
        for v in unverified_claims[:2]:
            conditions.append(f"Verify: {v.claim}")

    elif overall_score >= 5.0 or (len(red_flag_dimensions) == 1):
        recommendation = RecommendationLevel.REQUEST_REVISION
        summary = "Proposal has potential but requires significant revisions."

        for dim in red_flag_dimensions:
            conditions.append(f"Major revision needed: {dim.dimension}")
        for dim in yellow_flag_dimensions:
            conditions.append(f"Strengthen: {dim.dimension}")

    else:
        recommendation = RecommendationLevel.DECLINE
        issues = [d.dimension for d in red_flag_dimensions]
        summary = f"Proposal has critical issues in: {', '.join(issues)}."

    return recommendation, summary, conditions


# ---------------------------
# Verification Summary
# ---------------------------

def summarize_verifications(
    verification_results: List[VerificationResult]
) -> Tuple[int, int, int, int]:
    """
    Summarize verification results.

    Returns:
        Tuple of (verified_count, partial_count, unverified_count, unsubstantiated_count)
    """
    verified = sum(1 for v in verification_results if v.status == VerificationStatus.VERIFIED)
    partial = sum(1 for v in verification_results if v.status == VerificationStatus.PARTIAL)
    not_verified = sum(1 for v in verification_results if v.status == VerificationStatus.NOT_VERIFIED)
    unsubstantiated = sum(1 for v in verification_results if v.status == VerificationStatus.UNSUBSTANTIATED)

    return verified, partial, not_verified, unsubstantiated


# ---------------------------
# Budget Benchmarking
# ---------------------------

# Reference data for typical grant sizes (AI for Climate/Nature)
BUDGET_BENCHMARKS = {
    "seed_grant": {
        "min": 50_000,
        "typical": 150_000,
        "max": 300_000,
        "duration_months": 12,
    },
    "pilot_project": {
        "min": 200_000,
        "typical": 500_000,
        "max": 1_000_000,
        "duration_months": 18,
    },
    "full_project": {
        "min": 500_000,
        "typical": 1_500_000,
        "max": 3_000_000,
        "duration_months": 24,
    },
    "large_initiative": {
        "min": 2_000_000,
        "typical": 5_000_000,
        "max": 10_000_000,
        "duration_months": 36,
    },
}


def classify_budget_size(amount: float, duration_months: int = 12) -> str:
    """Classify budget into size category."""
    annualized = (amount / duration_months) * 12 if duration_months > 0 else amount

    if annualized <= 300_000:
        return "seed_grant"
    elif annualized <= 1_000_000:
        return "pilot_project"
    elif annualized <= 3_000_000:
        return "full_project"
    else:
        return "large_initiative"


def assess_budget_reasonableness(
    amount: float,
    duration_months: int,
    team_size: int = 5,
    project_type: str = "research"
) -> Tuple[str, float, str]:
    """
    Assess if budget is reasonable for the proposed scope.

    Returns:
        Tuple of (assessment, deviation_percent, benchmark_category)
    """
    category = classify_budget_size(amount, duration_months)
    benchmark = BUDGET_BENCHMARKS[category]

    typical = benchmark["typical"]
    deviation = ((amount - typical) / typical) * 100

    if deviation > 50:
        assessment = "Significantly above benchmark"
    elif deviation > 20:
        assessment = "Above benchmark"
    elif deviation > -20:
        assessment = "Within benchmark"
    elif deviation > -40:
        assessment = "Below benchmark"
    else:
        assessment = "Significantly below benchmark"

    return assessment, round(deviation, 1), category


# ---------------------------
# Utility Functions
# ---------------------------

def format_currency(amount: float, currency: str = "USD") -> str:
    """Format amount as currency string."""
    if currency == "USD":
        if amount >= 1_000_000:
            return f"${amount/1_000_000:.1f}M"
        elif amount >= 1_000:
            return f"${amount/1_000:.0f}K"
        else:
            return f"${amount:.0f}"
    return f"{amount:,.0f} {currency}"


def get_analysis_timestamp() -> str:
    """Get formatted timestamp for analysis."""
    return datetime.now().strftime("%Y-%m-%d %H:%M")


# ---------------------------
# BEF Criteria Scoring
# ---------------------------

def calculate_bef_criteria_score(
    criterion_scores: List[Dict],
) -> Tuple[float, float, float, float]:
    """
    Calculate BEF criteria scores by category and overall.

    Args:
        criterion_scores: List of dicts with 'criterion', 'category', 'score'

    Returns:
        Tuple of (overall_score, why_do_this_avg, why_us_avg, why_now_avg)
    """
    category_scores = {
        "Why Do This": [],
        "Why Us": [],
        "Why Now": [],
    }

    for cs in criterion_scores:
        category = cs.get("category", "")
        score = cs.get("score", 5.0)

        if category in category_scores:
            category_scores[category].append(score)

    # Calculate category averages
    why_do_this_avg = sum(category_scores["Why Do This"]) / len(category_scores["Why Do This"]) if category_scores["Why Do This"] else 5.0
    why_us_avg = sum(category_scores["Why Us"]) / len(category_scores["Why Us"]) if category_scores["Why Us"] else 5.0
    why_now_avg = sum(category_scores["Why Now"]) / len(category_scores["Why Now"]) if category_scores["Why Now"] else 5.0

    # Calculate weighted overall score
    overall_score = (
        why_do_this_avg * BEF_CRITERIA_WEIGHTS["Why Do This"] +
        why_us_avg * BEF_CRITERIA_WEIGHTS["Why Us"] +
        why_now_avg * BEF_CRITERIA_WEIGHTS["Why Now"]
    )

    return round(overall_score, 1), round(why_do_this_avg, 1), round(why_us_avg, 1), round(why_now_avg, 1)


def get_strategic_fit_recommendation(overall_score: float) -> str:
    """
    Get strategic fit recommendation based on BEF criteria score.

    Returns recommendation text for executives.
    """
    if overall_score >= 8.0:
        return "STRONG STRATEGIC FIT - Highly aligned with BEF investment philosophy"
    elif overall_score >= 6.5:
        return "GOOD STRATEGIC FIT - Aligned with conditions or clarifications needed"
    elif overall_score >= 5.0:
        return "MODERATE STRATEGIC FIT - Some alignment concerns to address"
    elif overall_score >= 3.5:
        return "WEAK STRATEGIC FIT - Significant alignment questions"
    else:
        return "POOR STRATEGIC FIT - Does not align with BEF investment criteria"


def calculate_enhanced_overall_score(
    dimension_scores: List[DimensionScore],
    include_strategic_fit: bool = True
) -> Tuple[float, str, ConfidenceLevel]:
    """
    Calculate overall score using enhanced weights (including Strategic Fit).

    Args:
        dimension_scores: List of DimensionScore objects (including Strategic Fit)
        include_strategic_fit: Whether to use enhanced weights

    Returns:
        Tuple of (overall_score, overall_grade, overall_confidence)
    """
    if not dimension_scores:
        return 0.0, "F", ConfidenceLevel.LOW

    weights = ENHANCED_WEIGHTS if include_strategic_fit else DEFAULT_WEIGHTS

    total_weight = 0.0
    weighted_sum = 0.0
    confidence_scores = []

    for dim in dimension_scores:
        weight = weights.get(dim.dimension, 0.10)  # Default weight for unknown dimensions
        weighted_sum += dim.score * weight
        total_weight += weight

        # Map confidence to numeric for averaging
        conf_values = {ConfidenceLevel.HIGH: 3, ConfidenceLevel.MEDIUM: 2, ConfidenceLevel.LOW: 1}
        confidence_scores.append(conf_values.get(dim.confidence, 2))

    # Calculate overall score
    overall_score = weighted_sum / total_weight if total_weight > 0 else 0.0
    overall_grade = score_to_grade(overall_score)

    # Calculate overall confidence (average)
    avg_confidence = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 2
    if avg_confidence >= 2.5:
        overall_confidence = ConfidenceLevel.HIGH
    elif avg_confidence >= 1.5:
        overall_confidence = ConfidenceLevel.MEDIUM
    else:
        overall_confidence = ConfidenceLevel.LOW

    return round(overall_score, 1), overall_grade, overall_confidence

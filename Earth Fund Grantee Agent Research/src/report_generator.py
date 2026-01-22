"""
Report Generator for Grant Proposal Analysis

Generates formatted output in multiple formats:
- Report Card (structured scores with traffic lights)
- Executive Brief (1-page summary)
- Deep Dive (detailed expandable sections)
- Interview Questions (engagement guide for program leads)

Copyright (c) 2024 Bezos Earth Fund
All rights reserved.
"""

from typing import List, Dict, Optional
from datetime import datetime

from src.models import (
    ReportCard,
    DimensionScore,
    VerificationResult,
    InterviewQuestion,
    InterviewGuide,
    ConfidenceLevel,
    TrafficLight,
    RecommendationLevel,
    VerificationStatus,
    BEFCriteriaAssessment,
    BEFCriterionScore,
    BEFCriterion,
)
from src.scoring import (
    score_to_grade,
    score_to_traffic_light,
    traffic_light_emoji,
    format_currency,
    get_analysis_timestamp,
)


def generate_report_card_markdown(report_card: ReportCard) -> str:
    """
    Generate the Report Card in Markdown format.

    This is the primary summary view with scores, grades, and traffic lights.
    """
    md = []

    # Header
    md.append(f"# Proposal Report Card")
    md.append(f"")
    md.append(f"**Proposal**: {report_card.proposal_title}")
    md.append(f"**Organization**: {report_card.organization}")
    if report_card.funding_requested:
        md.append(f"**Funding Requested**: {format_currency(report_card.funding_requested)}")
    md.append(f"**Analysis Date**: {report_card.analysis_date}")
    md.append(f"")

    # Overall Recommendation Box
    rec_emoji = {
        RecommendationLevel.FUND: "✅",
        RecommendationLevel.FUND_WITH_CONDITIONS: "⚠️",
        RecommendationLevel.REQUEST_REVISION: "📝",
        RecommendationLevel.DECLINE: "❌",
    }
    md.append(f"---")
    md.append(f"## Recommendation: {rec_emoji.get(report_card.recommendation, '')} {report_card.recommendation.value}")
    md.append(f"")
    md.append(f"> {report_card.recommendation_summary}")
    if report_card.conditions:
        md.append(f"")
        md.append(f"**Conditions:**")
        for cond in report_card.conditions:
            md.append(f"- {cond}")
    md.append(f"")
    md.append(f"---")
    md.append(f"")

    # Summary Scores Table
    md.append(f"## Summary Scores")
    md.append(f"")
    md.append(f"| Dimension | Score | Grade | Confidence | Status |")
    md.append(f"|-----------|-------|-------|------------|--------|")

    dimensions = [
        report_card.technical,
        report_card.innovation,
        report_card.impact,
        report_card.budget,
        report_card.team,
    ]

    for dim in dimensions:
        emoji = traffic_light_emoji(dim.traffic_light)
        md.append(
            f"| {dim.dimension} | {dim.score}/10 | {dim.grade} | {dim.confidence.value} | {emoji} {dim.traffic_light.value} |"
        )

    # Overall row
    overall_emoji = traffic_light_emoji(score_to_traffic_light(report_card.overall_score))
    md.append(
        f"| **OVERALL** | **{report_card.overall_score}/10** | **{report_card.overall_grade}** | "
        f"**{report_card.overall_confidence.value}** | {overall_emoji} |"
    )
    md.append(f"")

    # Traffic Light Legend
    md.append(f"### Status Legend")
    md.append(f"- 🟢 **GREEN**: Strong - No significant concerns")
    md.append(f"- 🟡 **YELLOW**: Caution - Some concerns to address")
    md.append(f"- 🔴 **RED**: Alert - Significant concerns identified")
    md.append(f"")

    # Verification Summary
    md.append(f"## Verification Summary")
    md.append(f"")
    md.append(f"| Claim | Status | Evidence |")
    md.append(f"|-------|--------|----------|")

    for v in report_card.verifications[:10]:  # Limit to 10 for readability
        status_icon = {
            VerificationStatus.VERIFIED: "✅",
            VerificationStatus.PARTIAL: "⚠️",
            VerificationStatus.NOT_VERIFIED: "❓",
            VerificationStatus.UNSUBSTANTIATED: "❌",
        }
        icon = status_icon.get(v.status, "❓")
        evidence = v.evidence[:50] + "..." if v.evidence and len(v.evidence) > 50 else (v.evidence or "-")
        claim_short = v.claim[:60] + "..." if len(v.claim) > 60 else v.claim
        md.append(f"| {claim_short} | {icon} {v.status.value} | {evidence} |")

    md.append(f"")
    md.append(f"**Summary**: {report_card.verified_count} verified, {report_card.unverified_count} unverified")
    md.append(f"")

    return "\n".join(md)


def generate_executive_brief_markdown(report_card: ReportCard) -> str:
    """
    Generate Executive Brief in Markdown format.

    A concise 1-page summary for quick decision-making.
    """
    md = []

    # Header
    md.append(f"# Executive Brief: {report_card.proposal_title}")
    md.append(f"")
    md.append(f"*Analysis Date: {report_card.analysis_date}*")
    md.append(f"")

    # TL;DR
    md.append(f"---")
    md.append(f"## TL;DR")
    md.append(f"")
    md.append(f"**{report_card.organization}** requests {format_currency(report_card.funding_requested) if report_card.funding_requested else 'funding'}.")
    md.append(f"")
    md.append(f"**Overall Assessment**: {report_card.overall_grade} ({report_card.overall_score}/10) - {report_card.recommendation.value}")
    md.append(f"")
    md.append(f"> {report_card.recommendation_summary}")
    md.append(f"")
    md.append(f"---")
    md.append(f"")

    # Key Strengths
    md.append(f"## Key Strengths")
    md.append(f"")
    for dim in [report_card.technical, report_card.innovation, report_card.impact, report_card.budget, report_card.team]:
        if dim.strengths:
            for strength in dim.strengths[:1]:  # Top strength per dimension
                md.append(f"- **{dim.dimension}**: {strength}")
    md.append(f"")

    # Key Concerns
    md.append(f"## Key Concerns")
    md.append(f"")
    for dim in [report_card.technical, report_card.innovation, report_card.impact, report_card.budget, report_card.team]:
        if dim.concerns:
            for concern in dim.concerns[:1]:  # Top concern per dimension
                md.append(f"- **{dim.dimension}**: {concern}")
    md.append(f"")

    # Unverified Claims
    unverified = [v for v in report_card.verifications
                  if v.status in [VerificationStatus.NOT_VERIFIED, VerificationStatus.UNSUBSTANTIATED]]
    if unverified:
        md.append(f"## Unverified Claims (Require Follow-up)")
        md.append(f"")
        for v in unverified[:5]:
            md.append(f"- {v.claim}")
        md.append(f"")

    # Conditions (if any)
    if report_card.conditions:
        md.append(f"## Recommended Conditions")
        md.append(f"")
        for i, cond in enumerate(report_card.conditions, 1):
            md.append(f"{i}. {cond}")
        md.append(f"")

    # Quick Reference Table
    md.append(f"## Scores at a Glance")
    md.append(f"")
    md.append(f"| Technical | Innovation | Impact | Budget | Team | **Overall** |")
    md.append(f"|-----------|------------|--------|--------|------|-------------|")
    md.append(
        f"| {report_card.technical.score}/10 | {report_card.innovation.score}/10 | "
        f"{report_card.impact.score}/10 | {report_card.budget.score}/10 | "
        f"{report_card.team.score}/10 | **{report_card.overall_score}/10** |"
    )
    md.append(f"")

    return "\n".join(md)


def generate_deep_dive_markdown(report_card: ReportCard) -> str:
    """
    Generate Deep Dive analysis in Markdown format.

    Detailed expandable sections for each assessment dimension.
    """
    md = []

    md.append(f"# Deep Dive Analysis: {report_card.proposal_title}")
    md.append(f"")
    md.append(f"*Comprehensive assessment details for program review*")
    md.append(f"")

    # Generate section for each dimension
    dimensions = [
        ("Technical Feasibility", report_card.technical),
        ("Innovation & Novelty", report_card.innovation),
        ("Climate & Nature Impact", report_card.impact),
        ("Budget & Financial", report_card.budget),
        ("Team Credibility", report_card.team),
    ]

    for title, dim in dimensions:
        md.append(f"---")
        md.append(f"## {title}")
        md.append(f"")
        md.append(f"**Score**: {dim.score}/10 ({dim.grade}) | **Confidence**: {dim.confidence.value} | **Status**: {traffic_light_emoji(dim.traffic_light)} {dim.traffic_light.value}")
        md.append(f"")

        # Summary
        md.append(f"### Summary")
        md.append(f"{dim.summary}")
        md.append(f"")

        # Strengths
        if dim.strengths:
            md.append(f"### Strengths")
            for s in dim.strengths:
                md.append(f"- {s}")
            md.append(f"")

        # Concerns
        if dim.concerns:
            md.append(f"### Concerns")
            for c in dim.concerns:
                md.append(f"- {c}")
            md.append(f"")

        # Evidence
        if dim.evidence:
            md.append(f"### Supporting Evidence")
            for e in dim.evidence:
                md.append(f"- **{e.source}** ({e.source_type}): {e.finding}")
                if e.url:
                    md.append(f"  - Link: {e.url}")
            md.append(f"")

        # Key Concern callout
        if dim.key_concern:
            md.append(f"### Key Concern")
            md.append(f"> ⚠️ {dim.key_concern}")
            md.append(f"")

    return "\n".join(md)


def generate_interview_questions_markdown(
    report_card: ReportCard,
    interview_guide: Optional[InterviewGuide] = None
) -> str:
    """
    Generate Interview Questions guide in Markdown format.

    Prioritized questions for program leads to ask applicants.
    """
    md = []

    md.append(f"# Interview Questions Guide")
    md.append(f"")
    md.append(f"**Proposal**: {report_card.proposal_title}")
    md.append(f"**Organization**: {report_card.organization}")
    md.append(f"")
    md.append(f"*Use these questions to probe concerns and clarify unverified claims during applicant interviews.*")
    md.append(f"")

    # Generate questions from concerns and unverified claims
    question_num = 1

    # Technical Questions
    md.append(f"---")
    md.append(f"## Technical Clarification Questions")
    md.append(f"")
    if report_card.technical.concerns:
        for concern in report_card.technical.concerns[:3]:
            md.append(f"{question_num}. Can you provide more detail on: {concern}?")
            question_num += 1
    else:
        md.append(f"*No major technical concerns identified.*")
    md.append(f"")

    # Team Questions
    question_num = 1
    md.append(f"## Team & Capability Questions")
    md.append(f"")
    unverified_team = [v for v in report_card.verifications if "team" in v.claim.lower() or "credential" in v.claim.lower()]
    if unverified_team or report_card.team.concerns:
        for v in unverified_team[:2]:
            md.append(f"{question_num}. We couldn't verify: \"{v.claim}\". Can you provide documentation?")
            question_num += 1
        for concern in report_card.team.concerns[:2]:
            md.append(f"{question_num}. {concern}")
            question_num += 1
    else:
        md.append(f"*Team credentials verified. No major concerns.*")
    md.append(f"")

    # Impact Questions
    question_num = 1
    md.append(f"## Impact & Metrics Questions")
    md.append(f"")
    unverified_impact = [v for v in report_card.verifications if "impact" in v.claim.lower() or "CO2" in v.claim or "reduce" in v.claim.lower()]
    if unverified_impact or report_card.impact.concerns:
        for v in unverified_impact[:2]:
            md.append(f"{question_num}. How did you calculate: \"{v.claim}\"? What methodology was used?")
            question_num += 1
        for concern in report_card.impact.concerns[:2]:
            md.append(f"{question_num}. {concern}")
            question_num += 1
    else:
        md.append(f"*Impact claims appear reasonable. Minor clarifications may be needed.*")
    md.append(f"")

    # Budget Questions
    question_num = 1
    md.append(f"## Budget Questions")
    md.append(f"")
    if report_card.budget.concerns:
        for concern in report_card.budget.concerns[:3]:
            md.append(f"{question_num}. {concern}")
            question_num += 1
    else:
        md.append(f"*Budget appears reasonable and within benchmarks.*")
    md.append(f"")

    # Red Flag Follow-ups
    red_flags = [v for v in report_card.verifications if v.status == VerificationStatus.UNSUBSTANTIATED]
    if red_flags:
        question_num = 1
        md.append(f"## Red Flag Follow-ups (High Priority)")
        md.append(f"")
        for v in red_flags[:5]:
            md.append(f"{question_num}. **CRITICAL**: The claim \"{v.claim}\" could not be substantiated. Please provide evidence.")
            question_num += 1
        md.append(f"")

    # General Follow-up
    md.append(f"---")
    md.append(f"## General Follow-up")
    md.append(f"")
    md.append(f"1. What is your contingency plan if the primary approach doesn't work?")
    md.append(f"2. How will you measure success at 6 months, 12 months?")
    md.append(f"3. What happens after the grant period ends?")
    md.append(f"")

    return "\n".join(md)


def generate_strategic_fit_markdown(strategic_fit: Optional[BEFCriteriaAssessment]) -> str:
    """
    Generate Strategic Fit Assessment section in Markdown format.

    This shows the BEF Investment Criteria evaluation with 9 criteria scores.
    """
    if not strategic_fit or not strategic_fit.criteria_scores:
        return "## Strategic Fit Assessment\n\n*BEF Criteria Evaluation was not performed.*\n"

    md = []

    md.append(f"# Strategic Fit Assessment")
    md.append(f"")
    md.append(f"*Evaluation against Bezos Earth Fund's 9 Investment Criteria*")
    md.append(f"")

    # Overall Strategic Fit Score
    overall_emoji = traffic_light_emoji(strategic_fit.traffic_light)
    md.append(f"---")
    md.append(f"## Overall Strategic Fit: {overall_emoji} {strategic_fit.overall_strategic_fit}/10 ({strategic_fit.grade})")
    md.append(f"")

    if strategic_fit.executive_summary:
        md.append(f"> {strategic_fit.executive_summary}")
        md.append(f"")

    md.append(f"---")
    md.append(f"")

    # Category Scores Summary
    md.append(f"## Category Scores")
    md.append(f"")
    md.append(f"| Category | Score | Status |")
    md.append(f"|----------|-------|--------|")
    md.append(f"| WHY SHOULD WE DO THIS? | {strategic_fit.why_do_this_score}/10 | {traffic_light_emoji(score_to_traffic_light(strategic_fit.why_do_this_score))} |")
    md.append(f"| WHY US? | {strategic_fit.why_us_score}/10 | {traffic_light_emoji(score_to_traffic_light(strategic_fit.why_us_score))} |")
    md.append(f"| WHY NOW? | {strategic_fit.why_now_score}/10 | {traffic_light_emoji(score_to_traffic_light(strategic_fit.why_now_score))} |")
    md.append(f"")

    # Detailed Criteria Breakdown
    md.append(f"## Detailed Criteria Scores")
    md.append(f"")

    # Group by category
    categories = {
        "Why Do This": [],
        "Why Us": [],
        "Why Now": [],
    }

    for cs in strategic_fit.criteria_scores:
        if cs.category in categories:
            categories[cs.category].append(cs)

    # WHY SHOULD WE DO THIS?
    md.append(f"### WHY SHOULD WE DO THIS?")
    md.append(f"")
    md.append(f"| Criterion | Score | Status | Justification |")
    md.append(f"|-----------|-------|--------|---------------|")
    for cs in categories.get("Why Do This", []):
        emoji = traffic_light_emoji(cs.traffic_light)
        justification_short = cs.justification[:100] + "..." if len(cs.justification) > 100 else cs.justification
        md.append(f"| {cs.criterion.value} | {cs.score}/10 | {emoji} | {justification_short} |")
    md.append(f"")

    # WHY US?
    md.append(f"### WHY US?")
    md.append(f"")
    md.append(f"| Criterion | Score | Status | Justification |")
    md.append(f"|-----------|-------|--------|---------------|")
    for cs in categories.get("Why Us", []):
        emoji = traffic_light_emoji(cs.traffic_light)
        justification_short = cs.justification[:100] + "..." if len(cs.justification) > 100 else cs.justification
        md.append(f"| {cs.criterion.value} | {cs.score}/10 | {emoji} | {justification_short} |")
    md.append(f"")

    # WHY NOW?
    md.append(f"### WHY NOW?")
    md.append(f"")
    md.append(f"| Criterion | Score | Status | Justification |")
    md.append(f"|-----------|-------|--------|---------------|")
    for cs in categories.get("Why Now", []):
        emoji = traffic_light_emoji(cs.traffic_light)
        justification_short = cs.justification[:100] + "..." if len(cs.justification) > 100 else cs.justification
        md.append(f"| {cs.criterion.value} | {cs.score}/10 | {emoji} | {justification_short} |")
    md.append(f"")

    # Key Recommendations
    if strategic_fit.key_recommendations:
        md.append(f"## Executive Recommendations")
        md.append(f"")
        for i, rec in enumerate(strategic_fit.key_recommendations, 1):
            md.append(f"{i}. {rec}")
        md.append(f"")

    return "\n".join(md)


def generate_executive_decision_brief(report_card: ReportCard, strategic_fit: Optional[BEFCriteriaAssessment] = None) -> str:
    """
    Generate a concise Executive Decision Brief for leadership.

    This is designed for quick decision-making by BEF executives.
    """
    md = []

    md.append(f"# EXECUTIVE DECISION BRIEF")
    md.append(f"")
    md.append(f"**Proposal**: {report_card.proposal_title}")
    md.append(f"**Organization**: {report_card.organization}")
    if report_card.funding_requested:
        md.append(f"**Funding Requested**: {format_currency(report_card.funding_requested)}")
    md.append(f"**Date**: {report_card.analysis_date}")
    md.append(f"")

    # Decision Box
    rec_emoji = {
        RecommendationLevel.FUND: "APPROVE",
        RecommendationLevel.FUND_WITH_CONDITIONS: "CONDITIONAL APPROVE",
        RecommendationLevel.REQUEST_REVISION: "REVISIONS NEEDED",
        RecommendationLevel.DECLINE: "DECLINE",
    }
    md.append(f"---")
    md.append(f"## RECOMMENDATION: {rec_emoji.get(report_card.recommendation, '')} - {report_card.recommendation.value}")
    md.append(f"")
    md.append(f"**Overall Score**: {report_card.overall_score}/10 ({report_card.overall_grade})")
    md.append(f"")
    md.append(f"> {report_card.recommendation_summary}")
    md.append(f"")
    md.append(f"---")
    md.append(f"")

    # Quick Score Summary
    md.append(f"## SCORES AT A GLANCE")
    md.append(f"")
    md.append(f"| Dimension | Score | Status |")
    md.append(f"|-----------|-------|--------|")
    md.append(f"| Technical Feasibility | {report_card.technical.score}/10 | {traffic_light_emoji(report_card.technical.traffic_light)} |")
    md.append(f"| Innovation | {report_card.innovation.score}/10 | {traffic_light_emoji(report_card.innovation.traffic_light)} |")
    md.append(f"| Climate Impact | {report_card.impact.score}/10 | {traffic_light_emoji(report_card.impact.traffic_light)} |")
    md.append(f"| Budget | {report_card.budget.score}/10 | {traffic_light_emoji(report_card.budget.traffic_light)} |")
    md.append(f"| Team Credibility | {report_card.team.score}/10 | {traffic_light_emoji(report_card.team.traffic_light)} |")

    if strategic_fit:
        md.append(f"| **Strategic Fit** | **{strategic_fit.score}/10** | {traffic_light_emoji(strategic_fit.traffic_light)} |")

    md.append(f"")

    # Strategic Fit Quick View (if available)
    if strategic_fit:
        md.append(f"## STRATEGIC FIT SUMMARY")
        md.append(f"")
        md.append(f"| WHY DO THIS? | WHY US? | WHY NOW? |")
        md.append(f"|--------------|---------|----------|")
        md.append(f"| {strategic_fit.why_do_this_score}/10 | {strategic_fit.why_us_score}/10 | {strategic_fit.why_now_score}/10 |")
        md.append(f"")

    # Key Points for Decision
    md.append(f"## KEY DECISION FACTORS")
    md.append(f"")

    # Top Strengths
    md.append(f"**Strengths:**")
    all_strengths = []
    for dim in [report_card.technical, report_card.innovation, report_card.impact, report_card.budget, report_card.team]:
        all_strengths.extend(dim.strengths[:1])
    for s in all_strengths[:3]:
        md.append(f"- {s}")
    md.append(f"")

    # Top Concerns
    md.append(f"**Concerns:**")
    all_concerns = []
    for dim in [report_card.technical, report_card.innovation, report_card.impact, report_card.budget, report_card.team]:
        all_concerns.extend(dim.concerns[:1])
    for c in all_concerns[:3]:
        md.append(f"- {c}")
    md.append(f"")

    # Conditions (if any)
    if report_card.conditions:
        md.append(f"## CONDITIONS FOR APPROVAL")
        md.append(f"")
        for i, cond in enumerate(report_card.conditions, 1):
            md.append(f"{i}. {cond}")
        md.append(f"")

    return "\n".join(md)


def generate_full_report(
    report_card: ReportCard,
    include_deep_dive: bool = True,
    include_questions: bool = True,
    strategic_fit: Optional[BEFCriteriaAssessment] = None,
) -> str:
    """
    Generate complete report with all sections combined.
    """
    sections = []

    # Executive Decision Brief (new - for quick executive review)
    sections.append(generate_executive_decision_brief(report_card, strategic_fit))

    # Report Card (always included)
    sections.append("\n\n" + "=" * 80 + "\n\n")
    sections.append(generate_report_card_markdown(report_card))

    # Strategic Fit Assessment (if available)
    if strategic_fit:
        sections.append("\n\n" + "=" * 80 + "\n\n")
        sections.append(generate_strategic_fit_markdown(strategic_fit))

    # Executive Brief
    sections.append("\n\n" + "=" * 80 + "\n\n")
    sections.append(generate_executive_brief_markdown(report_card))

    # Deep Dive (optional)
    if include_deep_dive:
        sections.append("\n\n" + "=" * 80 + "\n\n")
        sections.append(generate_deep_dive_markdown(report_card))

    # Interview Questions (optional)
    if include_questions:
        sections.append("\n\n" + "=" * 80 + "\n\n")
        sections.append(generate_interview_questions_markdown(report_card))

    return "".join(sections)


def parse_crew_output_to_report_card(
    crew_output: str,
    proposal_title: str,
    organization: str,
    funding_requested: Optional[float] = None,
) -> ReportCard:
    """
    Parse the CrewAI output text into a structured ReportCard object.

    This is a best-effort parser that extracts scores and findings from
    the semi-structured output of the synthesis agent.
    """
    # This is a simplified parser - in production, you'd want more robust parsing
    # or have the agent output structured JSON directly

    from src.models import (
        TechnicalAssessment,
        InnovationAssessment,
        ImpactAssessment,
        BudgetAssessment,
        TeamAssessment,
    )

    # Default assessments (will be populated from parsing)
    technical = TechnicalAssessment(
        score=7.0,
        grade="B",
        confidence=ConfidenceLevel.MEDIUM,
        summary="Technical assessment pending detailed parsing.",
        traffic_light=TrafficLight.YELLOW,
    )

    innovation = InnovationAssessment(
        score=7.0,
        grade="B",
        confidence=ConfidenceLevel.MEDIUM,
        summary="Innovation assessment pending detailed parsing.",
        traffic_light=TrafficLight.YELLOW,
    )

    impact = ImpactAssessment(
        score=7.0,
        grade="B",
        confidence=ConfidenceLevel.MEDIUM,
        summary="Impact assessment pending detailed parsing.",
        traffic_light=TrafficLight.YELLOW,
    )

    budget = BudgetAssessment(
        score=7.0,
        grade="B",
        confidence=ConfidenceLevel.MEDIUM,
        summary="Budget assessment pending detailed parsing.",
        traffic_light=TrafficLight.YELLOW,
    )

    team = TeamAssessment(
        score=7.0,
        grade="B",
        confidence=ConfidenceLevel.MEDIUM,
        summary="Team assessment pending detailed parsing.",
        traffic_light=TrafficLight.YELLOW,
    )

    # Try to extract scores from the crew output
    import re

    # Look for score patterns like "Technical Soundness Score: 7.5/10" or "Score: 8/10"
    score_patterns = [
        (r"technical.*?(\d+\.?\d*)\s*/\s*10", "technical"),
        (r"innovation.*?(\d+\.?\d*)\s*/\s*10", "innovation"),
        (r"novelty.*?(\d+\.?\d*)\s*/\s*10", "innovation"),
        (r"impact.*?(\d+\.?\d*)\s*/\s*10", "impact"),
        (r"budget.*?(\d+\.?\d*)\s*/\s*10", "budget"),
        (r"team.*?(\d+\.?\d*)\s*/\s*10", "team"),
        (r"credibility.*?(\d+\.?\d*)\s*/\s*10", "team"),
    ]

    for pattern, dim_type in score_patterns:
        match = re.search(pattern, crew_output.lower())
        if match:
            score = float(match.group(1))
            grade = score_to_grade(score)
            tl = score_to_traffic_light(score)

            if dim_type == "technical":
                technical.score = score
                technical.grade = grade
                technical.traffic_light = tl
            elif dim_type == "innovation":
                innovation.score = score
                innovation.grade = grade
                innovation.traffic_light = tl
            elif dim_type == "impact":
                impact.score = score
                impact.grade = grade
                impact.traffic_light = tl
            elif dim_type == "budget":
                budget.score = score
                budget.grade = grade
                budget.traffic_light = tl
            elif dim_type == "team":
                team.score = score
                team.grade = grade
                team.traffic_light = tl

    # Calculate overall score
    overall_score = (
        technical.score * 0.25 +
        innovation.score * 0.15 +
        impact.score * 0.25 +
        budget.score * 0.15 +
        team.score * 0.20
    )
    overall_grade = score_to_grade(overall_score)

    # Determine recommendation
    if overall_score >= 8.0:
        recommendation = RecommendationLevel.FUND
        rec_summary = "Strong proposal recommended for funding."
    elif overall_score >= 6.5:
        recommendation = RecommendationLevel.FUND_WITH_CONDITIONS
        rec_summary = "Good proposal recommended with conditions."
    elif overall_score >= 5.0:
        recommendation = RecommendationLevel.REQUEST_REVISION
        rec_summary = "Proposal requires revisions before funding decision."
    else:
        recommendation = RecommendationLevel.DECLINE
        rec_summary = "Proposal has significant issues. Decline recommended."

    return ReportCard(
        proposal_title=proposal_title,
        organization=organization,
        funding_requested=funding_requested,
        analysis_date=get_analysis_timestamp(),
        technical=technical,
        innovation=innovation,
        impact=impact,
        budget=budget,
        team=team,
        overall_score=round(overall_score, 1),
        overall_grade=overall_grade,
        overall_confidence=ConfidenceLevel.MEDIUM,
        recommendation=recommendation,
        recommendation_summary=rec_summary,
        conditions=[],
        verifications=[],
        verified_count=0,
        unverified_count=0,
    )

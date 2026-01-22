"""
Pydantic Data Models for Grant Proposal Analysis

Defines structured data models for:
- Proposal parsing and extraction
- Assessment scores and grades
- Report card generation
- Verification results

Copyright (c) 2024 Bezos Earth Fund
All rights reserved.
"""

from typing import List, Dict, Optional, Literal
from pydantic import BaseModel, Field
from enum import Enum


# ---------------------------
# Enums
# ---------------------------

class ConfidenceLevel(str, Enum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class VerificationStatus(str, Enum):
    VERIFIED = "VERIFIED"
    PARTIAL = "PARTIALLY VERIFIED"
    NOT_VERIFIED = "NOT VERIFIED"
    UNSUBSTANTIATED = "UNSUBSTANTIATED"


class RecommendationLevel(str, Enum):
    FUND = "FUND"
    FUND_WITH_CONDITIONS = "FUND WITH CONDITIONS"
    DECLINE = "DECLINE"
    REQUEST_REVISION = "REQUEST REVISION"


class TrafficLight(str, Enum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"


# ---------------------------
# Proposal Data Models
# ---------------------------

class TeamMember(BaseModel):
    """Individual team member information."""
    name: str
    role: str
    credentials: Optional[str] = None
    affiliation: Optional[str] = None
    linkedin_url: Optional[str] = None
    publications_count: Optional[int] = None
    h_index: Optional[int] = None


class BudgetItem(BaseModel):
    """Individual budget line item."""
    category: str
    amount: float
    justification: Optional[str] = None


class BudgetBreakdown(BaseModel):
    """Complete budget information."""
    total_requested: float
    currency: str = "USD"
    duration_months: int
    items: List[BudgetItem] = Field(default_factory=list)
    monthly_burn_rate: Optional[float] = None


class TimelinePhase(BaseModel):
    """Project timeline phase."""
    phase_name: str
    duration_months: int
    deliverables: List[str] = Field(default_factory=list)
    milestones: List[str] = Field(default_factory=list)


class ProposalClaim(BaseModel):
    """A claim made in the proposal that needs verification."""
    claim_text: str
    claim_type: Literal["technical", "impact", "team", "partnership", "metric", "other"]
    evidence_provided: Optional[str] = None
    source_section: Optional[str] = None


class ProposalData(BaseModel):
    """
    Structured representation of a parsed grant proposal.
    Extracted by the Proposal Parser Agent.
    """
    # Basic Info
    title: str
    organization: str
    submission_date: Optional[str] = None

    # Team
    team_members: List[TeamMember] = Field(default_factory=list)
    team_size: Optional[int] = None

    # Content
    executive_summary: Optional[str] = None
    problem_statement: Optional[str] = None
    proposed_solution: Optional[str] = None
    technical_approach: Optional[str] = None
    methodology: Optional[str] = None

    # Impact
    expected_impact: Optional[str] = None
    target_beneficiaries: Optional[str] = None
    success_metrics: List[str] = Field(default_factory=list)
    sdg_alignment: List[str] = Field(default_factory=list)

    # Timeline & Budget
    timeline: List[TimelinePhase] = Field(default_factory=list)
    budget: Optional[BudgetBreakdown] = None

    # Background
    prior_work: Optional[str] = None
    partnerships: List[str] = Field(default_factory=list)
    references: List[str] = Field(default_factory=list)

    # Claims for Verification
    key_claims: List[ProposalClaim] = Field(default_factory=list)

    # Metadata
    word_count: Optional[int] = None
    page_count: Optional[int] = None


# ---------------------------
# Assessment Models
# ---------------------------

class EvidenceItem(BaseModel):
    """A piece of evidence supporting an assessment."""
    source: str
    source_type: str  # e.g., "Peer-reviewed paper", "Government report"
    finding: str
    url: Optional[str] = None
    citation: Optional[str] = None


class DimensionScore(BaseModel):
    """Score for a single assessment dimension."""
    dimension: str
    score: float = Field(ge=0, le=10)
    grade: str  # A, B, C, D, F
    confidence: ConfidenceLevel
    summary: str
    strengths: List[str] = Field(default_factory=list)
    concerns: List[str] = Field(default_factory=list)
    evidence: List[EvidenceItem] = Field(default_factory=list)
    traffic_light: TrafficLight = TrafficLight.YELLOW
    key_concern: Optional[str] = None


class VerificationResult(BaseModel):
    """Result of verifying a specific claim."""
    claim: str
    status: VerificationStatus
    evidence: Optional[str] = None
    source: Optional[str] = None
    notes: Optional[str] = None


class TechnicalAssessment(DimensionScore):
    """Technical feasibility assessment details."""
    dimension: str = "Technical Feasibility"
    trl_level: Optional[int] = Field(None, ge=1, le=9)  # Technology Readiness Level
    prior_art_found: List[Dict] = Field(default_factory=list)
    technical_risks: List[str] = Field(default_factory=list)
    feasibility_rating: Optional[str] = None  # "Highly Feasible", "Feasible", "Challenging", "Unlikely"


class InnovationAssessment(DimensionScore):
    """Innovation and novelty assessment details."""
    dimension: str = "Innovation"
    novelty_type: Optional[str] = None  # "Breakthrough", "Incremental", "Disruptive", "Derivative"
    similar_projects: List[Dict] = Field(default_factory=list)
    differentiation: Optional[str] = None
    patent_landscape: Optional[str] = None
    competitive_advantage: Optional[str] = None


class ImpactAssessment(DimensionScore):
    """Climate/nature impact assessment details."""
    dimension: str = "Climate Impact"
    sdg_alignment: List[str] = Field(default_factory=list)
    impact_metrics: Dict[str, str] = Field(default_factory=dict)
    scalability: Optional[str] = None  # "High", "Medium", "Low"
    co_benefits: List[str] = Field(default_factory=list)
    environmental_risks: List[str] = Field(default_factory=list)


class BudgetAssessment(DimensionScore):
    """Budget and financial assessment details."""
    dimension: str = "Budget"
    benchmark_comparison: Optional[str] = None
    cost_reasonableness: Optional[str] = None  # "Above Benchmark", "Within Benchmark", "Below Benchmark"
    red_flags: List[str] = Field(default_factory=list)
    cost_per_outcome: Optional[str] = None


class TeamAssessment(DimensionScore):
    """Team credibility assessment details."""
    dimension: str = "Team Credibility"
    verified_credentials: List[Dict] = Field(default_factory=list)
    publication_record: Optional[str] = None
    prior_grants: List[str] = Field(default_factory=list)
    capability_gaps: List[str] = Field(default_factory=list)
    org_track_record: Optional[str] = None


# ---------------------------
# Report Card Model
# ---------------------------

class ReportCard(BaseModel):
    """
    Complete proposal assessment report card.
    Contains scores for all dimensions plus overall recommendation.
    """
    # Proposal Info
    proposal_title: str
    organization: str
    funding_requested: Optional[float] = None
    analysis_date: str

    # Dimension Scores
    technical: TechnicalAssessment
    innovation: InnovationAssessment
    impact: ImpactAssessment
    budget: BudgetAssessment
    team: TeamAssessment

    # Overall
    overall_score: float = Field(ge=0, le=10)
    overall_grade: str
    overall_confidence: ConfidenceLevel

    # Recommendation
    recommendation: RecommendationLevel
    recommendation_summary: str
    conditions: List[str] = Field(default_factory=list)

    # Verification Summary
    verifications: List[VerificationResult] = Field(default_factory=list)
    verified_count: int = 0
    unverified_count: int = 0


# ---------------------------
# Interview Questions Model
# ---------------------------

class InterviewQuestion(BaseModel):
    """A suggested question for the program lead."""
    category: str  # "Technical", "Team", "Impact", "Budget", "Red Flag"
    question: str
    context: Optional[str] = None
    priority: Literal["High", "Medium", "Low"] = "Medium"


class InterviewGuide(BaseModel):
    """Complete interview/engagement guide."""
    proposal_title: str
    technical_questions: List[InterviewQuestion] = Field(default_factory=list)
    team_questions: List[InterviewQuestion] = Field(default_factory=list)
    impact_questions: List[InterviewQuestion] = Field(default_factory=list)
    budget_questions: List[InterviewQuestion] = Field(default_factory=list)
    red_flag_followups: List[InterviewQuestion] = Field(default_factory=list)


# ---------------------------
# BEF Investment Criteria Models
# ---------------------------

class BEFCriterion(str, Enum):
    """Bezos Earth Fund's 9 investment criteria."""
    # WHY SHOULD WE DO THIS?
    IMPACT_POTENTIAL = "Impact Potential"
    TRANSFORMATIONAL = "Transformational Nature"
    ORGANIZATIONAL_EFFICIENCY = "Organizational Efficiency"
    # WHY US?
    ADDITIONALITY = "Additionality"
    LEVERAGE_ADVANTAGES = "Leverage BEF Advantages"
    BRAND_ALIGNMENT = "Brand Alignment"
    # WHY NOW?
    TIMING = "Timing"
    SUSTAINABILITY = "Sustainability"
    LEARNING_IMPROVEMENT = "Learning & Improvement"


class BEFCriterionScore(BaseModel):
    """Score for a single BEF investment criterion."""
    criterion: BEFCriterion
    category: Literal["Why Do This", "Why Us", "Why Now"]
    score: float = Field(ge=1, le=10)
    justification: str
    evidence: List[str] = Field(default_factory=list)
    traffic_light: TrafficLight = TrafficLight.YELLOW


class BEFCriteriaAssessment(DimensionScore):
    """
    Complete BEF Strategic Fit assessment.
    Evaluates proposal against all 9 investment criteria.
    """
    dimension: str = "Strategic Fit"
    criteria_scores: List[BEFCriterionScore] = Field(default_factory=list)
    overall_strategic_fit: float = Field(ge=0, le=10, default=5.0)
    executive_summary: str = ""
    key_recommendations: List[str] = Field(default_factory=list)

    # Category sub-scores
    why_do_this_score: float = Field(ge=0, le=10, default=5.0)
    why_us_score: float = Field(ge=0, le=10, default=5.0)
    why_now_score: float = Field(ge=0, le=10, default=5.0)

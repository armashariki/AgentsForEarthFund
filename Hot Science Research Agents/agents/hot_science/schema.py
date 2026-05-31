"""Canonical data schema for UC-I-1 Hot Science candidates."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


Confidence = str
VenueType = str


def utc_now_iso() -> str:
    """Return an ISO timestamp suitable for audit events."""
    return datetime.now(UTC).isoformat()


@dataclass
class SourceMention:
    source: str
    url: str | None = None
    date_seen: str | None = None
    source_type: str | None = None
    note: str | None = None


@dataclass
class PressCoverage:
    outlet: str
    url: str
    headline: str | None = None
    date: str | None = None
    verified: bool = False
    verification_note: str | None = None


@dataclass
class PriorEditionMention:
    title: str
    target_month: str | None = None
    url: str | None = None
    note: str | None = None
    confidence: Confidence = "low"


@dataclass
class PublicationInfo:
    venue: str | None = None
    venue_type: VenueType | None = None
    source_record_type: str | None = None
    online_publication_date: str | None = None
    issue_publication_date: str | None = None
    date_source_field: str | None = None
    raw_publication_date: str | None = None
    url: str | None = None
    primary_source_url: str | None = None
    primary_work_type: str | None = None
    full_text_pdf_url: str | None = None
    downloaded_pdf_path: str | None = None
    open_access: bool | None = None
    paywall: bool | None = None
    abstract_accessible: bool | None = None
    access_note: str | None = None


@dataclass
class ScoreItem:
    score: int | None = None
    rationale: str | None = None
    confidence: Confidence = "low"
    evidence: str | None = None
    subtype: str | None = None
    weight: float | None = None


@dataclass
class SignificanceAssessment:
    rubric_version: str | None = None
    novelty: ScoreItem = field(default_factory=ScoreItem)
    impact_magnitude: ScoreItem = field(default_factory=ScoreItem)
    cross_disciplinary: ScoreItem = field(default_factory=ScoreItem)
    earth_system_signal: ScoreItem = field(default_factory=ScoreItem)
    audience_relevance: ScoreItem = field(default_factory=ScoreItem)
    cascading_impact: ScoreItem = field(default_factory=ScoreItem)
    composite_score: float | None = None
    overall_confidence: Confidence = "low"


@dataclass
class ExclusionFlag:
    code: str
    rationale: str


@dataclass
class VerificationInfo:
    doi_resolved: bool = False
    primary_source_resolved: bool = False
    primary_source_note: str | None = None
    primary_object_verified: bool = False
    primary_object_note: str | None = None
    date_verified: bool = False
    date_verification_source: str | None = None
    duplicate_check_passed: bool = False
    consolidated_from: list[str] = field(default_factory=list)


@dataclass
class FitAssessment:
    """Evidence-backed relevance assessment for Hot Science inclusion."""

    passed: bool | None = None
    relevance_claim: str | None = None
    evidence_source: str | None = None
    evidence_snippet: str | None = None
    standing_scope_aligned: bool | None = None
    run_focus_aligned: bool | None = None
    supported_domain_tags: list[str] = field(default_factory=list)
    manual_review_reason: str | None = None


@dataclass
class DateEligibility:
    """Target-month decision using the primary work's publication date."""

    eligible: bool | None = None
    target_month: str | None = None
    checked_date: str | None = None
    date_kind: str | None = None
    source_field: str | None = None
    reason: str | None = None


@dataclass
class AuditEvent:
    agent: str
    timestamp: str
    action: str
    detail: str | None = None


@dataclass
class CandidateRecord:
    """One Hot Science candidate record.

    The schema intentionally allows nullable fields while requiring a
    ``missing_reasons`` entry for values an agent could not populate.
    """

    title: str
    candidate_id: str = field(default_factory=lambda: str(uuid4()))
    doi: str | None = None
    authors: list[str] = field(default_factory=list)
    first_author_affiliation: str | None = None
    publication: PublicationInfo = field(default_factory=PublicationInfo)
    abstract: str | None = None
    abstract_source: str | None = None
    topic_tags: list[str] = field(default_factory=list)
    discovered_via: list[SourceMention] = field(default_factory=list)
    press_coverage: list[PressCoverage] = field(default_factory=list)
    pop_press_found: bool = False
    prior_editions: list[PriorEditionMention] = field(default_factory=list)
    significance: SignificanceAssessment = field(default_factory=SignificanceAssessment)
    honorable_mention_candidate: bool = False
    exclusion_flags: list[ExclusionFlag] = field(default_factory=list)
    theme_cluster: str | None = None
    verification: VerificationInfo = field(default_factory=VerificationInfo)
    fit_assessment: FitAssessment = field(default_factory=FitAssessment)
    date_eligibility: DateEligibility = field(default_factory=DateEligibility)
    routing_reason: str | None = None
    watchlist_reason: str | None = None
    rubric_version: str | None = None
    audit_trail: list[AuditEvent] = field(default_factory=list)
    target_month: str | None = None
    source_status: str = "raw"
    retrieval_score: float | None = None
    seed_term_matches: list[str] = field(default_factory=list)
    missing_reasons: dict[str, str] = field(default_factory=dict)

    def add_audit(self, agent: str, action: str, detail: str | None = None) -> None:
        """Append an immutable-ish audit event to the candidate record."""
        self.audit_trail.append(
            AuditEvent(agent=agent, timestamp=utc_now_iso(), action=action, detail=detail)
        )

    def add_missing_reason(self, field_path: str, reason: str) -> None:
        """Record why a field is null or unknown."""
        self.missing_reasons[field_path] = reason

    def add_exclusion(self, code: str, rationale: str) -> None:
        """Attach an exclusion flag if it is not already present."""
        if not any(flag.code == code for flag in self.exclusion_flags):
            self.exclusion_flags.append(ExclusionFlag(code=code, rationale=rationale))

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-friendly dict."""
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "CandidateRecord":
        """Deserialize from a dict produced by ``to_dict``."""
        data = dict(payload)
        data["publication"] = PublicationInfo(
            **_dataclass_kwargs(PublicationInfo, data.get("publication", {}))
        )
        data["discovered_via"] = [
            SourceMention(**_dataclass_kwargs(SourceMention, item))
            for item in data.get("discovered_via", [])
        ]
        data["press_coverage"] = [
            PressCoverage(**_dataclass_kwargs(PressCoverage, item))
            for item in data.get("press_coverage", [])
        ]
        data["prior_editions"] = [
            PriorEditionMention(**_dataclass_kwargs(PriorEditionMention, item))
            for item in data.get("prior_editions", [])
        ]
        sig = data.get("significance", {})
        data["significance"] = SignificanceAssessment(
            rubric_version=sig.get("rubric_version"),
            novelty=ScoreItem(**_dataclass_kwargs(ScoreItem, sig.get("novelty", {}))),
            impact_magnitude=ScoreItem(
                **_dataclass_kwargs(ScoreItem, sig.get("impact_magnitude", {}))
            ),
            cross_disciplinary=ScoreItem(
                **_dataclass_kwargs(ScoreItem, sig.get("cross_disciplinary", {}))
            ),
            earth_system_signal=ScoreItem(
                **_dataclass_kwargs(ScoreItem, sig.get("earth_system_signal", {}))
            ),
            audience_relevance=ScoreItem(
                **_dataclass_kwargs(ScoreItem, sig.get("audience_relevance", {}))
            ),
            cascading_impact=ScoreItem(
                **_dataclass_kwargs(ScoreItem, sig.get("cascading_impact", {}))
            ),
            composite_score=sig.get("composite_score"),
            overall_confidence=sig.get("overall_confidence", "low"),
        )
        data["exclusion_flags"] = [
            ExclusionFlag(**_dataclass_kwargs(ExclusionFlag, item))
            for item in data.get("exclusion_flags", [])
        ]
        data["verification"] = VerificationInfo(
            **_dataclass_kwargs(VerificationInfo, data.get("verification", {}))
        )
        data["fit_assessment"] = FitAssessment(
            **_dataclass_kwargs(FitAssessment, data.get("fit_assessment", {}))
        )
        data["date_eligibility"] = DateEligibility(
            **_dataclass_kwargs(DateEligibility, data.get("date_eligibility", {}))
        )
        data["audit_trail"] = [
            AuditEvent(**_dataclass_kwargs(AuditEvent, item))
            for item in data.get("audit_trail", [])
        ]
        return cls(**_dataclass_kwargs(cls, data))

    def normalized_doi(self) -> str | None:
        """Return a lowercase DOI without URL prefixes."""
        if not self.doi:
            return None
        doi = self.doi.strip().lower()
        for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
            if doi.startswith(prefix):
                doi = doi[len(prefix) :]
        return doi or None


def _dataclass_kwargs(
    dataclass_type: type, payload: dict[str, Any] | None
) -> dict[str, Any]:
    """Return only constructor kwargs supported by a dataclass."""
    if not payload:
        return {}
    allowed = {item.name for item in fields(dataclass_type)}
    return {key: value for key, value in payload.items() if key in allowed}

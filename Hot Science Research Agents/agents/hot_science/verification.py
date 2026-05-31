"""Verification Agent for UC-I-1 Hot Science candidates."""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from agents.hot_science.date_utils import in_target_month, parse_date
from agents.hot_science.schema import CandidateRecord
from agents.hot_science.storage import normalize_title


PRIMARY_ELIGIBLE_TYPES = {
    "peer_reviewed_journal",
    "attribution_report",
    "institutional_data_release",
}

ARTIFACT_RECORD_TYPES = {
    "dataset",
    "software",
    "repository",
    "data-management-plan",
    "paratext",
}

ARTIFACT_TEXT_HINTS = (
    "zenodo",
    "figshare",
    "github.com",
    "osf.io",
    "dryad",
    "datadryad",
    "code ocean",
    "codeocean",
    "mendeley data",
    "code for",
    "(code",
    "dataset for",
    "data for",
    "software for",
    "supplementary data",
    "supplementary code",
)

CANONICAL_PUBLICATION_DATE_FIELDS = {
    "date-published",
    "issued",
    "publication_date",
    "publicationdate",
    "publicationDate",
    "published",
    "published-online",
    "published-print",
    "source_metadata_pending_publisher_confirmation",
}

NON_CANONICAL_DATE_FIELDS = {
    "accepted",
    "created",
    "deposited",
    "posted",
    "pubdate",
    "pubDate",
    "received",
    "submitted",
    "updated",
}

ARTICLE_RECORD_TYPES = {
    "article",
    "journal-article",
    "journal_article",
    "paper",
}

JOURNAL_LEVEL_RECORD_TYPES = {
    "journal",
    "journal-issue",
    "journal-volume",
}


@dataclass(frozen=True)
class VerificationResult:
    verified: list[CandidateRecord]
    excluded: list[CandidateRecord]
    manual_review: list[CandidateRecord]


class VerificationAgent:
    """Lock down provenance, date discipline, and duplicate handling."""

    def __init__(self, *, non_target_month_watchlist: bool = False):
        self.non_target_month_watchlist = non_target_month_watchlist

    def verify(self, candidates: list[CandidateRecord], target_month: str) -> VerificationResult:
        manual_review: list[CandidateRecord] = []
        excluded: list[CandidateRecord] = []
        date_survivors: list[CandidateRecord] = []
        prepared_candidates, identity_exclusions = self._prepare_candidates(
            candidates, target_month
        )
        excluded.extend(identity_exclusions)

        for candidate in prepared_candidates:
            self._verify_primary_object(candidate)
            if any(flag.code == "non_primary_research_object" for flag in candidate.exclusion_flags):
                candidate.source_status = "excluded"
                candidate.routing_reason = "non_primary_research_object"
                candidate.add_audit("verification", "excluded", "non_primary_research_object")
                excluded.append(candidate)
                continue
            if any(flag.code == "journal_level_record" for flag in candidate.exclusion_flags):
                candidate.source_status = "excluded"
                candidate.routing_reason = "journal_level_record"
                candidate.add_audit("verification", "excluded", "journal_level_record")
                excluded.append(candidate)
                continue
            self._verify_date(candidate, target_month)
            self._mark_access_state(candidate)

            if candidate.publication.venue_type == "popular_press":
                candidate.source_status = "manual_review"
                candidate.routing_reason = "popular_press_primary_unresolved"
                candidate.add_missing_reason(
                    "publication.primary_source_url",
                    "Popular press item did not resolve to an underlying eligible source.",
                )
                candidate.add_audit("verification", "manual_review", "popular_press_primary_unresolved")
                manual_review.append(candidate)
                continue

            if not candidate.verification.date_verified:
                candidate.source_status = "manual_review"
                candidate.routing_reason = "date_not_verified"
                candidate.add_audit("verification", "manual_review", "date_not_verified")
                manual_review.append(candidate)
                continue

            if not in_target_month(candidate.publication.online_publication_date, target_month):
                candidate.date_eligibility.eligible = False
                candidate.date_eligibility.reason = "outside_target_month"
                if self.non_target_month_watchlist:
                    candidate.source_status = "manual_review"
                    candidate.routing_reason = "non_target_month_watchlist"
                    candidate.watchlist_reason = "relevant_outside_target_month"
                    candidate.add_audit(
                        "verification",
                        "manual_review",
                        "non_target_month_watchlist",
                    )
                    manual_review.append(candidate)
                    continue
                candidate.add_exclusion(
                    "outside_target_month",
                    "Verified online publication date falls outside the target month.",
                )
                candidate.source_status = "excluded"
                candidate.routing_reason = "outside_target_month"
                candidate.add_audit("verification", "excluded", "outside_target_month")
                excluded.append(candidate)
                continue

            candidate.date_eligibility.eligible = True
            candidate.date_eligibility.reason = "in_target_month"

            if not candidate.abstract:
                candidate.source_status = "manual_review"
                candidate.routing_reason = "title_only_abstract_missing"
                candidate.fit_assessment.manual_review_reason = (
                    "Title-only candidate needs abstract or primary metadata before scoring."
                )
                candidate.add_audit(
                    "verification",
                    "manual_review",
                    "title_only_abstract_missing",
                )
                manual_review.append(candidate)
                continue

            date_survivors.append(candidate)

        survivors, duplicate_exclusions = self._dedupe(date_survivors)
        excluded.extend(duplicate_exclusions)
        for candidate in survivors:
            candidate.source_status = "verified"
            candidate.verification.duplicate_check_passed = True
            candidate.add_audit("verification", "verified")

        return VerificationResult(
            verified=survivors,
            excluded=excluded,
            manual_review=manual_review,
        )

    def _prepare_candidates(
        self, candidates: list[CandidateRecord], target_month: str
    ) -> tuple[list[CandidateRecord], list[CandidateRecord]]:
        for candidate in candidates:
            candidate.target_month = target_month
            self._resolve_doi(candidate)
            self._tag_source_type(candidate)
            self._classify_primary_work_type(candidate)
        return self._prefer_canonical_primary_records(candidates)

    def _resolve_doi(self, candidate: CandidateRecord) -> None:
        if not candidate.doi:
            candidate.doi = extract_doi(candidate.publication.url or candidate.title)
        normalized = candidate.normalized_doi()
        if normalized:
            candidate.doi = normalized
            candidate.verification.doi_resolved = True
            candidate.add_audit("verification", "doi_resolved", normalized)
        else:
            candidate.verification.doi_resolved = False
            candidate.add_missing_reason(
                "doi",
                "No DOI was present in source metadata or URL. Route to manual review if otherwise eligible.",
            )

    def _tag_source_type(self, candidate: CandidateRecord) -> None:
        if candidate.publication.venue_type:
            return
        for mention in candidate.discovered_via:
            if mention.source_type:
                candidate.publication.venue_type = mention.source_type
                return
        candidate.publication.venue_type = "unknown"
        candidate.add_missing_reason(
            "publication.venue_type",
            "Source did not declare a venue type.",
        )

    def _verify_date(self, candidate: CandidateRecord, target_month: str) -> None:
        publication = candidate.publication
        candidate.date_eligibility.target_month = target_month
        candidate.date_eligibility.checked_date = publication.online_publication_date
        candidate.date_eligibility.source_field = publication.date_source_field
        candidate.date_eligibility.date_kind = _date_kind(publication.date_source_field)

        if not _has_canonical_date_field(candidate):
            candidate.verification.date_verified = False
            candidate.date_eligibility.eligible = None
            candidate.date_eligibility.reason = "non_canonical_date_field"
            candidate.add_audit(
                "verification",
                "date_not_verified",
                f"non_canonical_field={publication.date_source_field or 'unknown'}",
            )
            candidate.add_missing_reason(
                "publication.online_publication_date",
                (
                    "No canonical online publication date is available; "
                    f"source field was {publication.date_source_field or 'unknown'}."
                ),
            )
            return

        if publication.online_publication_date and parse_date(publication.online_publication_date):
            candidate.verification.date_verified = True
            candidate.verification.date_verification_source = (
                publication.date_source_field
                or "source_metadata_pending_publisher_confirmation"
            )
            candidate.add_audit(
                "verification",
                "date_verified",
                (
                    f"field={publication.date_source_field or 'unknown'}; "
                    f"raw={publication.raw_publication_date or publication.online_publication_date}; "
                    f"normalized={publication.online_publication_date}"
                ),
            )
            return
        candidate.verification.date_verified = False
        candidate.date_eligibility.eligible = None
        candidate.date_eligibility.reason = "date_missing_or_unparseable"
        candidate.add_audit("verification", "date_not_verified")
        candidate.add_missing_reason(
            "publication.online_publication_date",
            f"No canonical online publication date available for target month {target_month}.",
        )

    def _verify_primary_object(self, candidate: CandidateRecord) -> None:
        if candidate.publication.primary_work_type == "journal_level_record":
            candidate.verification.primary_object_verified = False
            candidate.verification.primary_object_note = (
                "Record appears to describe a journal, issue, or venue rather than an article."
            )
            candidate.add_exclusion(
                "journal_level_record",
                "Record appears to be journal-level metadata rather than an article-level work.",
            )
            candidate.add_audit(
                "verification",
                "primary_object_failed",
                candidate.verification.primary_object_note,
            )
            return

        if candidate.publication.venue_type in {
            "popular_press",
            "institutional_data_release",
            "attribution_report",
            "preprint",
        }:
            candidate.verification.primary_object_verified = True
            candidate.verification.primary_object_note = (
                "Source type is routed by its configured eligibility rules."
            )
            return

        if (
            candidate.publication.primary_work_type == "research_artifact"
            or _looks_like_research_artifact(candidate)
        ):
            candidate.verification.primary_object_verified = False
            candidate.verification.primary_object_note = (
                "Record appears to describe a research artifact, repository, code, "
                "dataset, or supplement rather than the canonical primary paper/report."
            )
            candidate.add_exclusion(
                "non_primary_research_object",
                (
                    "Record appears to be a research artifact/repository/data/code item "
                    "rather than the canonical primary paper or report."
                ),
            )
            candidate.add_audit(
                "verification",
                "primary_object_failed",
                candidate.verification.primary_object_note,
            )
            return

        candidate.verification.primary_object_verified = True
        candidate.verification.primary_object_note = (
            "No research-artifact indicators found in source metadata."
        )
        candidate.add_audit("verification", "primary_object_verified")

    def _classify_primary_work_type(self, candidate: CandidateRecord) -> None:
        if candidate.publication.primary_work_type:
            return
        venue_type = candidate.publication.venue_type
        record_type = (candidate.publication.source_record_type or "").casefold()
        if _looks_like_research_artifact(candidate):
            candidate.publication.primary_work_type = "research_artifact"
        elif record_type in JOURNAL_LEVEL_RECORD_TYPES:
            candidate.publication.primary_work_type = "journal_level_record"
        elif venue_type == "peer_reviewed_journal":
            candidate.publication.primary_work_type = "peer_reviewed_journal_article"
        elif venue_type == "attribution_report":
            candidate.publication.primary_work_type = "attribution_report"
        elif venue_type == "institutional_data_release":
            candidate.publication.primary_work_type = "institutional_data_release"
        elif venue_type == "preprint":
            candidate.publication.primary_work_type = "preprint"
        elif venue_type == "popular_press":
            candidate.publication.primary_work_type = "press_lead"
        elif record_type in ARTICLE_RECORD_TYPES:
            candidate.publication.primary_work_type = "peer_reviewed_journal_article"
        else:
            candidate.publication.primary_work_type = "unknown"

    def _prefer_canonical_primary_records(
        self, candidates: list[CandidateRecord]
    ) -> tuple[list[CandidateRecord], list[CandidateRecord]]:
        canonical_candidates = [
            candidate
            for candidate in candidates
            if candidate.publication.primary_work_type == "peer_reviewed_journal_article"
        ]
        prepared: list[CandidateRecord] = []
        excluded: list[CandidateRecord] = []
        for candidate in candidates:
            if candidate.publication.primary_work_type != "research_artifact":
                prepared.append(candidate)
                continue
            canonical = _find_canonical_for_artifact(candidate, canonical_candidates)
            if not canonical:
                prepared.append(candidate)
                continue
            self._merge_artifact_into_canonical(canonical, candidate)
            candidate.source_status = "excluded"
            candidate.routing_reason = "canonical_article_preferred_over_artifact"
            candidate.add_exclusion(
                "non_primary_research_object",
                "Artifact was consolidated into the canonical peer-reviewed article.",
            )
            candidate.add_audit(
                "verification",
                "consolidated_into_canonical_primary",
                canonical.candidate_id,
            )
            excluded.append(candidate)
        return prepared, excluded

    def _merge_artifact_into_canonical(
        self, canonical: CandidateRecord, artifact: CandidateRecord
    ) -> None:
        canonical.discovered_via.extend(artifact.discovered_via)
        canonical.press_coverage.extend(artifact.press_coverage)
        if artifact.candidate_id not in canonical.verification.consolidated_from:
            canonical.verification.consolidated_from.append(artifact.candidate_id)
        canonical.add_audit(
            "verification",
            "canonical_primary_preferred",
            f"Consolidated artifact {artifact.candidate_id}",
        )

    def _mark_access_state(self, candidate: CandidateRecord) -> None:
        if candidate.abstract:
            candidate.publication.abstract_accessible = True
        elif candidate.publication.abstract_accessible is None:
            candidate.publication.abstract_accessible = False
            candidate.add_missing_reason("abstract", "No abstract was available from source metadata.")
        if candidate.publication.paywall is None:
            if candidate.publication.open_access is True:
                candidate.publication.paywall = False
            elif candidate.publication.open_access is False:
                candidate.publication.paywall = True
            else:
                candidate.add_missing_reason(
                    "publication.paywall",
                    "Paywall probe not yet run; access status is unknown.",
                )
        if candidate.publication.primary_source_url is None and candidate.publication.url:
            candidate.publication.primary_source_url = candidate.publication.url

    def _dedupe(
        self, candidates: list[CandidateRecord]
    ) -> tuple[list[CandidateRecord], list[CandidateRecord]]:
        survivors: list[CandidateRecord] = []
        excluded: list[CandidateRecord] = []
        for candidate in candidates:
            match = self._find_duplicate(candidate, survivors)
            if not match:
                survivors.append(candidate)
                continue
            self._merge_duplicate(match, candidate)
            candidate.add_exclusion(
                "duplicate",
                f"Consolidated into candidate {match.candidate_id}.",
            )
            candidate.source_status = "excluded"
            candidate.add_audit("verification", "excluded", "duplicate")
            excluded.append(candidate)
        return survivors, excluded

    def _find_duplicate(
        self, candidate: CandidateRecord, survivors: list[CandidateRecord]
    ) -> CandidateRecord | None:
        candidate_doi = candidate.normalized_doi()
        candidate_title = normalize_title(candidate.title)
        candidate_authors = {author.casefold() for author in candidate.authors}
        for survivor in survivors:
            survivor_doi = survivor.normalized_doi()
            if candidate_doi and survivor_doi and candidate_doi == survivor_doi:
                return survivor
            title_score = SequenceMatcher(
                None, candidate_title, normalize_title(survivor.title)
            ).ratio()
            author_overlap = bool(candidate_authors.intersection(a.casefold() for a in survivor.authors))
            if title_score >= 0.92 and author_overlap:
                return survivor
        return None

    def _merge_duplicate(self, survivor: CandidateRecord, duplicate: CandidateRecord) -> None:
        survivor.discovered_via.extend(duplicate.discovered_via)
        survivor.press_coverage.extend(duplicate.press_coverage)
        survivor.verification.consolidated_from.append(duplicate.candidate_id)
        if not survivor.abstract and duplicate.abstract:
            survivor.abstract = duplicate.abstract
            survivor.abstract_source = duplicate.abstract_source
        survivor.add_audit(
            "verification",
            "deduplicated",
            f"Consolidated duplicate candidate {duplicate.candidate_id}",
        )


def extract_doi(text: str | None) -> str | None:
    """Extract a DOI-looking token from arbitrary text."""
    if not text:
        return None
    match = re.search(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", text, flags=re.I)
    if not match:
        return None
    return match.group(0).rstrip(".,);").lower()


def _date_kind(field_name: str | None) -> str | None:
    if not field_name:
        return None
    normalized = field_name.casefold()
    if normalized in {field.casefold() for field in CANONICAL_PUBLICATION_DATE_FIELDS}:
        return "publication"
    if normalized in {field.casefold() for field in NON_CANONICAL_DATE_FIELDS}:
        return "non_canonical"
    return "unknown"


def _has_canonical_date_field(candidate: CandidateRecord) -> bool:
    publication = candidate.publication
    if not publication.online_publication_date:
        return False
    field_name = publication.date_source_field
    if not field_name:
        return True
    field_normalized = field_name.casefold()
    if publication.primary_work_type == "press_lead":
        return False
    if publication.primary_work_type == "research_artifact":
        return False
    return field_normalized in {
        field.casefold() for field in CANONICAL_PUBLICATION_DATE_FIELDS
    }


def _find_canonical_for_artifact(
    artifact: CandidateRecord, candidates: list[CandidateRecord]
) -> CandidateRecord | None:
    artifact_title = _identity_title(artifact.title)
    best: tuple[float, CandidateRecord] | None = None
    for candidate in candidates:
        if candidate is artifact:
            continue
        candidate_title = _identity_title(candidate.title)
        if not artifact_title or not candidate_title:
            continue
        score = SequenceMatcher(None, artifact_title, candidate_title).ratio()
        if artifact_title in candidate_title or candidate_title in artifact_title:
            score = max(score, 0.95)
        if score < 0.74:
            continue
        if best is None or score > best[0]:
            best = (score, candidate)
    return best[1] if best else None


def _identity_title(title: str) -> str:
    text = title.casefold()
    text = re.sub(r"\([^)]*(?:code|data|simulation|supplement)[^)]*\)", " ", text)
    for phrase in (
        "code for simulation",
        "code for",
        "dataset for",
        "data for",
        "software for",
        "supplementary data",
        "supplementary code",
    ):
        text = text.replace(phrase, " ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _looks_like_research_artifact(candidate: CandidateRecord) -> bool:
    publication = candidate.publication
    record_type = (publication.source_record_type or "").casefold()
    if record_type in ARTIFACT_RECORD_TYPES:
        return True
    text = " ".join(
        part
        for part in [
            candidate.title,
            candidate.doi,
            publication.venue,
            publication.url,
            publication.primary_source_url,
            *(mention.url for mention in candidate.discovered_via),
        ]
        if part
    ).casefold()
    return any(hint in text for hint in ARTIFACT_TEXT_HINTS)

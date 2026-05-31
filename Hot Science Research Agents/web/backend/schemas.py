"""Typed request and response objects for the Hot Science web service boundary."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from agents.hot_science.criteria import (
    compact_query,
    extract_retrieval_query,
    normalize_criteria_text,
)
from agents.hot_science.date_utils import parse_target_month


@dataclass(frozen=True)
class HotScienceRunRequest:
    """A normalized Hot Science run request from the future web UI."""

    target_month: str
    criteria_text: str
    retrieval_query: str | None = None
    source_ids: tuple[str, ...] = ()
    max_results_per_source: int = 25
    requested_by: str | None = None

    def normalized(self) -> "HotScienceRunRequest":
        """Validate and normalize the request without retaining uploaded files."""
        target_month = self.target_month.strip()
        parse_target_month(target_month)
        criteria_text = normalize_criteria_text(self.criteria_text)
        if not criteria_text:
            raise ValueError("Hot Science runs require non-empty search criteria.")
        if self.max_results_per_source < 1:
            raise ValueError("max_results_per_source must be at least 1.")
        source_ids = tuple(
            source_id.strip()
            for source_id in self.source_ids
            if source_id and source_id.strip()
        )
        retrieval_query = self.retrieval_query
        if retrieval_query is None:
            retrieval_query = extract_retrieval_query(criteria_text) or ""
        retrieval_query = compact_query(retrieval_query) if retrieval_query else retrieval_query
        requested_by = self.requested_by.strip() if self.requested_by else None
        return HotScienceRunRequest(
            target_month=target_month,
            criteria_text=criteria_text,
            retrieval_query=retrieval_query,
            source_ids=source_ids,
            max_results_per_source=self.max_results_per_source,
            requested_by=requested_by,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ArtifactLink:
    """Download metadata for an artifact produced by a Hot Science run."""

    artifact_id: str
    run_id: str
    kind: str
    filename: str
    path: str
    download_url: str
    mime_type: str
    size_bytes: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HotScienceRunServiceResult:
    """Result returned by the Phase 1 service boundary."""

    run_id: str
    target_month: str
    summary: dict[str, int | str]
    primary_artifact: ArtifactLink
    artifacts: tuple[ArtifactLink, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["primary_artifact"] = self.primary_artifact.to_dict()
        payload["artifacts"] = [artifact.to_dict() for artifact in self.artifacts]
        return payload

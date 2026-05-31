"""Config loading for UC-I-1 Hot Science monitoring."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


DEFAULT_SOURCE_CONFIG = (
    Path(__file__).resolve().parents[2] / "config" / "hot_science_sources.yaml"
)


@dataclass(frozen=True)
class SourceConfig:
    id: str
    name: str
    kind: str
    source_type: str
    enabled: bool = True
    url: str | None = None
    notes: str | None = None
    issns: tuple[str, ...] = ()
    priority: int = 100


@dataclass(frozen=True)
class IntentConfig:
    description: str
    similarity_threshold: float = 0.55
    raw_candidate_monthly_target_min: int = 200
    raw_candidate_monthly_target_max: int = 500


@dataclass(frozen=True)
class DomainConfig:
    id: str
    label: str
    terms: tuple[str, ...]
    description: str | None = None


@dataclass(frozen=True)
class RubricDimensionConfig:
    id: str
    label: str
    weight: float = 1.0
    selection_signal: bool = True
    bonus_only: bool = False
    description: str | None = None


@dataclass(frozen=True)
class RubricConfig:
    version: str
    composite_method: str
    dimensions: tuple[RubricDimensionConfig, ...]

    def dimension(self, dimension_id: str) -> RubricDimensionConfig:
        for dimension in self.dimensions:
            if dimension.id == dimension_id:
                return dimension
        valid = ", ".join(dimension.id for dimension in self.dimensions)
        raise ValueError(f"Unknown rubric dimension '{dimension_id}'. Choose from: {valid}")


@dataclass(frozen=True)
class WatchlistConfig:
    non_target_month_enabled: bool = False
    preprint_bucket_enabled: bool = True


@dataclass(frozen=True)
class HotScienceConfig:
    intent: IntentConfig
    seed_terms: tuple[str, ...]
    search_queries: tuple[str, ...]
    sources: tuple[SourceConfig, ...]
    domains: tuple[DomainConfig, ...] = ()
    rubric: RubricConfig = field(
        default_factory=lambda: RubricConfig(
            version="hot_science_v1",
            composite_method="simple_sum",
            dimensions=(),
        )
    )
    watchlist: WatchlistConfig = field(default_factory=WatchlistConfig)
    primary_work_type_priority: tuple[str, ...] = (
        "peer_reviewed_journal_article",
        "attribution_report",
        "institutional_data_release",
        "preprint",
        "research_artifact",
    )

    @property
    def enabled_sources(self) -> tuple[SourceConfig, ...]:
        return tuple(source for source in self.sources if source.enabled)


def load_hot_science_config(path: str | Path | None = None) -> HotScienceConfig:
    """Load the editable UC-I-1 source configuration."""
    config_path = Path(path) if path else DEFAULT_SOURCE_CONFIG
    payload = yaml.safe_load(config_path.read_text()) or {}

    intent_payload: dict[str, Any] = payload.get("intent", {})
    target = intent_payload.get("raw_candidate_monthly_target", {})
    intent = IntentConfig(
        description=intent_payload["description"],
        similarity_threshold=float(intent_payload.get("similarity_threshold", 0.55)),
        raw_candidate_monthly_target_min=int(target.get("min", 200)),
        raw_candidate_monthly_target_max=int(target.get("max", 500)),
    )

    sources = tuple(
        SourceConfig(
            id=item["id"],
            name=item["name"],
            kind=item["kind"],
            source_type=item["source_type"],
            enabled=bool(item.get("enabled", True)),
            url=item.get("url"),
            notes=item.get("notes"),
            issns=tuple(item.get("issns", [])),
            priority=int(item.get("priority", 100)),
        )
        for item in payload.get("sources", [])
    )

    domains = tuple(
        DomainConfig(
            id=item["id"],
            label=item["label"],
            terms=tuple(item.get("terms", [])),
            description=item.get("description"),
        )
        for item in payload.get("domains", [])
    )

    rubric_payload: dict[str, Any] = payload.get("rubric", {})
    rubric = RubricConfig(
        version=rubric_payload.get("version", "hot_science_v1"),
        composite_method=rubric_payload.get("composite_method", "simple_sum"),
        dimensions=tuple(
            RubricDimensionConfig(
                id=item["id"],
                label=item["label"],
                weight=float(item.get("weight", 1.0)),
                selection_signal=bool(item.get("selection_signal", True)),
                bonus_only=bool(item.get("bonus_only", False)),
                description=item.get("description"),
            )
            for item in rubric_payload.get("dimensions", [])
        ),
    )

    watchlist_payload: dict[str, Any] = payload.get("watchlist", {})
    watchlist = WatchlistConfig(
        non_target_month_enabled=bool(
            watchlist_payload.get("non_target_month_enabled", False)
        ),
        preprint_bucket_enabled=bool(watchlist_payload.get("preprint_bucket_enabled", True)),
    )

    return HotScienceConfig(
        intent=intent,
        seed_terms=tuple(payload.get("seed_terms", [])),
        search_queries=tuple(payload.get("search_queries", [])),
        sources=sources,
        domains=domains,
        rubric=rubric,
        watchlist=watchlist,
        primary_work_type_priority=tuple(
            payload.get(
                "primary_work_type_priority",
                (
                    "peer_reviewed_journal_article",
                    "attribution_report",
                    "institutional_data_release",
                    "preprint",
                    "research_artifact",
                ),
            )
        ),
    )

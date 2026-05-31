"""Source Monitor Agent for UC-I-1 Hot Science."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from agents.hot_science.clients import scan_source
from agents.hot_science.config import HotScienceConfig, SourceConfig, load_hot_science_config
from agents.hot_science.date_utils import scan_window_for_month
from agents.hot_science.progress import ProgressCallback, ProgressEvent, emit_progress
from agents.hot_science.schema import CandidateRecord
from agents.hot_science.semantic import (
    BedrockSemanticScorer,
    annotate_retrieval_signals,
    semantic_scoring_enabled,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SourceMonitorResult:
    candidates: list[CandidateRecord]
    source_errors: list[CandidateRecord]


class SourceMonitorAgent:
    """Scan configured sources and emit raw candidate records."""

    def __init__(self, config: HotScienceConfig | None = None):
        self.config = config or load_hot_science_config()

    def scan(
        self,
        target_month: str,
        *,
        max_results_per_source: int = 25,
        source_ids: set[str] | None = None,
        user_criteria: str | None = None,
        retrieval_query: str | None = None,
        progress_callback: ProgressCallback | None = None,
        run_id: str | None = None,
    ) -> SourceMonitorResult:
        """Run the source monitor over the wide date window for a target month."""
        window_start, window_end = scan_window_for_month(target_month)
        candidates: list[CandidateRecord] = []
        source_errors: list[CandidateRecord] = []
        semantic_scorer = BedrockSemanticScorer() if semantic_scoring_enabled() else None

        for source in self.config.enabled_sources:
            if source_ids and source.id not in source_ids:
                continue
            logger.info("Scanning source %s for %s", source.id, target_month)
            records: list[CandidateRecord] = []
            queries = build_retrieval_queries(
                self.config,
                source,
                user_criteria=user_criteria,
                retrieval_query=retrieval_query,
            )
            max_per_query = max(
                1,
                -(-max_results_per_source // max(1, len(queries))),
            )
            _emit_source_event(
                progress_callback,
                event_type="source_started",
                source=source,
                target_month=target_month,
                run_id=run_id,
                message=f"Scanning {source.name}",
                counts={"query_count": len(queries), "max_per_query": max_per_query},
            )
            for source_query in queries:
                query_records = scan_source(
                    source,
                    query=source_query,
                    seed_terms=self.config.seed_terms,
                    window_start=window_start,
                    window_end=window_end,
                    max_results=max_per_query,
                )
                records.extend(query_records)
                if any(record.source_status == "source_error" for record in query_records):
                    break
            source_candidate_count = 0
            source_duplicate_count = 0
            source_error_count = 0
            source_error_detail = None
            for record in records:
                record.target_month = target_month
                if record.source_status == "source_error":
                    source_errors.append(record)
                    source_error_count += 1
                    source_error_detail = source_error_detail or _source_error_detail(record)
                else:
                    annotate_retrieval_signals(record, self.config)
                    if semantic_scorer and (record.abstract or record.title):
                        try:
                            semantic_scorer.score_candidate(record, self.config)
                        except Exception as exc:
                            record.add_missing_reason(
                                "retrieval_score",
                                f"Semantic embedding score failed: {exc}",
                            )
                            record.add_audit(
                                "source_monitor",
                                "semantic_score_failed",
                                str(exc),
                            )
                    record.source_status = "raw"
                    record.add_audit(
                        "source_monitor",
                        "emitted_raw_candidate",
                        f"Target month {target_month}",
                    )
                    if user_criteria:
                        record.add_audit("source_monitor", "user_criteria", user_criteria)
                    if not _already_seen(record, candidates):
                        candidates.append(record)
                        source_candidate_count += 1
                    else:
                        source_duplicate_count += 1
            if source_error_count:
                _emit_source_event(
                    progress_callback,
                    event_type="source_error",
                    source=source,
                    target_month=target_month,
                    run_id=run_id,
                    message=f"{source.name} reported a source error",
                    counts={"source_errors": source_error_count},
                    detail=source_error_detail,
                )
            _emit_source_event(
                progress_callback,
                event_type="source_completed",
                source=source,
                target_month=target_month,
                run_id=run_id,
                message=f"Finished scanning {source.name}",
                counts={
                    "raw_records": len(records),
                    "candidates": source_candidate_count,
                    "duplicates": source_duplicate_count,
                    "source_errors": source_error_count,
                },
                detail=source_error_detail,
            )

        return SourceMonitorResult(candidates=candidates, source_errors=source_errors)


def build_retrieval_query(config: HotScienceConfig) -> str:
    """Build a compact broad retrieval query for public scholarly APIs.

    The full natural-language intent stays in config for embedding/scoring.
    API search endpoints perform better with concise terms.
    """
    return "climate change"


def build_retrieval_queries(
    config: HotScienceConfig,
    source: SourceConfig | str,
    *,
    user_criteria: str | None = None,
    retrieval_query: str | None = None,
) -> tuple[str, ...]:
    """Return query variants for searchable APIs while scanning feeds once."""
    source_id = source.id if isinstance(source, SourceConfig) else ""
    source_kind = source.kind if isinstance(source, SourceConfig) else source
    query_input = user_criteria if retrieval_query is None else retrieval_query
    criteria_query = normalize_user_criteria(query_input)
    if source_kind not in {"scholarly_api", "press_api"}:
        if _source_supports_issn_backfill(source):
            return _with_user_criteria(
                config.search_queries or (build_retrieval_query(config),),
                criteria_query,
            )
        return (criteria_query or build_retrieval_query(config),)
    if source_id == "semantic_scholar":
        if not os.getenv("SEMANTIC_SCHOLAR_API_KEY"):
            return (criteria_query or build_retrieval_query(config),)
        queries = (config.search_queries or (build_retrieval_query(config),))[:3]
        return _with_user_criteria(queries, criteria_query)
    return _with_user_criteria(
        config.search_queries or (build_retrieval_query(config),),
        criteria_query,
    )


def normalize_user_criteria(user_criteria: str | None) -> str | None:
    """Normalize a plain-language user focus into an API search query."""
    if not user_criteria:
        return None
    query = " ".join(user_criteria.split())
    return query[:240] or None


def _with_user_criteria(queries: tuple[str, ...], criteria_query: str | None) -> tuple[str, ...]:
    if not criteria_query:
        return queries
    deduped = [criteria_query]
    for query in queries:
        if query.casefold() != criteria_query.casefold():
            deduped.append(query)
    return tuple(deduped)


def _already_seen(candidate: CandidateRecord, candidates: list[CandidateRecord]) -> bool:
    doi = candidate.normalized_doi()
    title = " ".join(candidate.title.casefold().split())
    url = candidate.publication.url
    for existing in candidates:
        if doi and existing.normalized_doi() == doi:
            existing.discovered_via.extend(candidate.discovered_via)
            return True
        if url and existing.publication.url == url:
            existing.discovered_via.extend(candidate.discovered_via)
            return True
        if title and " ".join(existing.title.casefold().split()) == title:
            existing.discovered_via.extend(candidate.discovered_via)
            return True
    return False


def _source_supports_issn_backfill(source: SourceConfig | str) -> bool:
    return (
        isinstance(source, SourceConfig)
        and source.source_type == "peer_reviewed_journal"
        and bool(source.issns)
        and source.kind in {"rss", "scholarly_api"}
    )


def _emit_source_event(
    callback: ProgressCallback | None,
    *,
    event_type: str,
    source: SourceConfig,
    target_month: str,
    message: str,
    run_id: str | None = None,
    counts: dict[str, int] | None = None,
    detail: str | None = None,
) -> None:
    emit_progress(
        callback,
        ProgressEvent(
            event_type=event_type,
            stage="scanning_sources",
            run_id=run_id,
            target_month=target_month,
            source_id=source.id,
            source_name=source.name,
            message=message,
            counts=counts or {},
            detail=detail,
        ),
    )


def _source_error_detail(candidate: CandidateRecord) -> str | None:
    for mention in candidate.discovered_via:
        if mention.note:
            return mention.note
    return candidate.routing_reason

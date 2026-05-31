"""Orchestrator for the UC-I-1 Hot Science multi-agent pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

from agents.hot_science.access import AccessAgent
from agents.hot_science.compiler import CompiledCandidateSet, CompilerAgent
from agents.hot_science.config import HotScienceConfig, load_hot_science_config
from agents.hot_science.coverage import CoverageAgent
from agents.hot_science.evaluator import SignificanceEvaluatorAgent
from agents.hot_science.prior_editions import PriorEditionCheckerAgent
from agents.hot_science.progress import ProgressCallback, ProgressEvent, emit_progress
from agents.hot_science.resolver import PrimarySourceResolverAgent
from agents.hot_science.schema import CandidateRecord, utc_now_iso
from agents.hot_science.source_monitor import SourceMonitorAgent
from agents.hot_science.storage import CandidateStore, RunRecord
from agents.hot_science.verification import VerificationAgent


@dataclass(frozen=True)
class HotScienceRunResult:
    run_id: str
    target_month: str
    user_criteria: str | None = None
    raw_candidates: list[CandidateRecord] = field(default_factory=list)
    source_errors: list[CandidateRecord] = field(default_factory=list)
    unresolved_press: list[CandidateRecord] = field(default_factory=list)
    manual_review: list[CandidateRecord] = field(default_factory=list)
    verified: list[CandidateRecord] = field(default_factory=list)
    evaluated: list[CandidateRecord] = field(default_factory=list)
    preprints: list[CandidateRecord] = field(default_factory=list)
    excluded: list[CandidateRecord] = field(default_factory=list)
    compiled: CompiledCandidateSet | None = None

    @property
    def summary(self) -> dict[str, int | str]:
        return {
            "run_id": self.run_id,
            "target_month": self.target_month,
            "user_criteria": self.user_criteria or "",
            "raw_candidates": len(self.raw_candidates),
            "source_errors": len(self.source_errors),
            "unresolved_press": len(self.unresolved_press),
            "manual_review": len(self.manual_review),
            "verified": len(self.verified),
            "evaluated": len(self.evaluated),
            "preprints": len(self.preprints),
            "excluded": len(self.excluded),
        }


class HotScienceOrchestrator:
    """Coordinate Source Monitor, Verification, Evaluator, Coverage, and Compiler."""

    def __init__(
        self,
        *,
        config: HotScienceConfig | None = None,
        store: CandidateStore | None = None,
    ):
        self.config = config or load_hot_science_config()
        self.store = store or CandidateStore()
        self.source_monitor = SourceMonitorAgent(self.config)
        self.resolver = PrimarySourceResolverAgent()
        self.verifier = VerificationAgent(
            non_target_month_watchlist=self.config.watchlist.non_target_month_enabled
        )
        self.access = AccessAgent()
        self.evaluator = SignificanceEvaluatorAgent()
        self.coverage = CoverageAgent()
        self.prior_editions = PriorEditionCheckerAgent(self.store)
        self.compiler = CompilerAgent()

    def run(
        self,
        target_month: str,
        *,
        max_results_per_source: int = 25,
        source_ids: set[str] | None = None,
        user_criteria: str | None = None,
        retrieval_query: str | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> HotScienceRunResult:
        """Run the full v1 local pipeline for a target month."""
        run_id = str(uuid4())
        _emit_run_event(
            progress_callback,
            event_type="run_started",
            stage="run",
            run_id=run_id,
            target_month=target_month,
            message="Hot Science run started",
            counts={"selected_sources": len(source_ids or self.config.enabled_sources)},
        )
        _emit_stage_started(
            progress_callback,
            run_id=run_id,
            target_month=target_month,
            stage="scanning_sources",
            message="Scanning configured sources",
        )
        monitor_result = self.source_monitor.scan(
            target_month,
            max_results_per_source=max_results_per_source,
            source_ids=source_ids,
            user_criteria=user_criteria,
            retrieval_query=retrieval_query,
            progress_callback=progress_callback,
            run_id=run_id,
        )
        _emit_stage_completed(
            progress_callback,
            run_id=run_id,
            target_month=target_month,
            stage="scanning_sources",
            message="Source scanning complete",
            counts={
                "raw_candidates": len(monitor_result.candidates),
                "source_errors": len(monitor_result.source_errors),
            },
        )
        _emit_stage_started(
            progress_callback,
            run_id=run_id,
            target_month=target_month,
            stage="resolving_primary_sources",
            message="Resolving press leads to primary papers and reports",
            counts={"candidates": len(monitor_result.candidates)},
        )
        resolver_result = self.resolver.resolve(monitor_result.candidates)
        _emit_stage_completed(
            progress_callback,
            run_id=run_id,
            target_month=target_month,
            stage="resolving_primary_sources",
            message="Primary-source resolution complete",
            counts={
                "candidates": len(resolver_result.candidates),
                "unresolved_press": len(resolver_result.unresolved_press),
            },
        )
        _emit_stage_started(
            progress_callback,
            run_id=run_id,
            target_month=target_month,
            stage="verifying_dates_and_sources",
            message="Verifying source type, duplicates, and target-month dates",
            counts={"candidates": len(resolver_result.candidates)},
        )
        verification_result = self.verifier.verify(
            resolver_result.candidates,
            target_month=target_month,
        )
        _emit_stage_completed(
            progress_callback,
            run_id=run_id,
            target_month=target_month,
            stage="verifying_dates_and_sources",
            message="Verification complete",
            counts={
                "verified": len(verification_result.verified),
                "manual_review": len(verification_result.manual_review),
                "excluded": len(verification_result.excluded),
            },
        )
        _emit_stage_started(
            progress_callback,
            run_id=run_id,
            target_month=target_month,
            stage="checking_access",
            message="Checking access and full-text availability",
            counts={"verified": len(verification_result.verified)},
        )
        access_result = self.access.annotate(verification_result.verified)
        _emit_stage_completed(
            progress_callback,
            run_id=run_id,
            target_month=target_month,
            stage="checking_access",
            message="Access check complete",
            counts={"candidates": len(access_result.candidates)},
        )
        _emit_stage_started(
            progress_callback,
            run_id=run_id,
            target_month=target_month,
            stage="evaluating_significance",
            message="Evaluating Hot Science fit and significance",
            counts={"candidates": len(access_result.candidates)},
        )
        evaluation_result = self.evaluator.evaluate(
            access_result.candidates,
            user_criteria=user_criteria,
        )
        _emit_stage_completed(
            progress_callback,
            run_id=run_id,
            target_month=target_month,
            stage="evaluating_significance",
            message="Evaluation complete",
            counts={
                "evaluated": len(evaluation_result.evaluated),
                "preprints": len(evaluation_result.preprints),
                "manual_review": len(evaluation_result.manual_review),
                "excluded": len(evaluation_result.excluded),
            },
        )
        _emit_stage_started(
            progress_callback,
            run_id=run_id,
            target_month=target_month,
            stage="attaching_coverage",
            message="Attaching press and coverage context",
            counts={"evaluated": len(evaluation_result.evaluated)},
        )
        coverage_result = self.coverage.attach_coverage(evaluation_result.evaluated)
        _emit_stage_completed(
            progress_callback,
            run_id=run_id,
            target_month=target_month,
            stage="attaching_coverage",
            message="Coverage attachment complete",
            counts={"candidates": len(coverage_result.candidates)},
        )
        _emit_stage_started(
            progress_callback,
            run_id=run_id,
            target_month=target_month,
            stage="checking_prior_editions",
            message="Checking whether candidates appeared in prior editions",
            counts={"candidates": len(coverage_result.candidates)},
        )
        prior_result = self.prior_editions.check(coverage_result.candidates)
        _emit_stage_completed(
            progress_callback,
            run_id=run_id,
            target_month=target_month,
            stage="checking_prior_editions",
            message="Prior-edition check complete",
            counts={"candidates": len(prior_result.candidates)},
        )
        excluded = [
            *verification_result.excluded,
            *evaluation_result.excluded,
        ]
        manual_review = [
            *verification_result.manual_review,
            *evaluation_result.manual_review,
        ]
        _emit_stage_started(
            progress_callback,
            run_id=run_id,
            target_month=target_month,
            stage="compiling_outputs",
            message="Compiling candidate set and source diagnostics",
            counts={
                "candidates": len(prior_result.candidates),
                "manual_review": len(manual_review),
                "excluded": len(excluded),
            },
        )
        compiled = self.compiler.compile(
            target_month=target_month,
            candidates=prior_result.candidates,
            excluded=excluded,
            manual_review=manual_review,
            preprints=evaluation_result.preprints,
            user_criteria=user_criteria,
            sources=self.config.sources,
            source_errors=monitor_result.source_errors,
            rubric_version=self.config.rubric.version,
        )
        _emit_stage_completed(
            progress_callback,
            run_id=run_id,
            target_month=target_month,
            stage="compiling_outputs",
            message="Compilation complete",
            counts={
                "top_candidates": len(compiled.candidates),
                "manual_review": len(compiled.manual_review),
                "excluded": len(compiled.excluded),
                "preprints": len(compiled.preprints),
            },
        )

        _emit_stage_started(
            progress_callback,
            run_id=run_id,
            target_month=target_month,
            stage="storing_results",
            message="Saving candidates and run summary",
        )
        for candidate in [
            *monitor_result.source_errors,
            *manual_review,
            *prior_result.candidates,
            *evaluation_result.preprints,
            *excluded,
        ]:
            self.store.upsert_candidate(candidate)

        self.store.record_run(
            RunRecord(
                run_id=run_id,
                target_month=target_month,
                status="complete",
                raw_count=len(monitor_result.candidates),
                verified_count=len(verification_result.verified),
                evaluated_count=len(prior_result.candidates),
                excluded_count=len(excluded),
                created_at=utc_now_iso(),
            )
        )
        _emit_stage_completed(
            progress_callback,
            run_id=run_id,
            target_month=target_month,
            stage="storing_results",
            message="Run results saved",
            counts={
                "saved_records": (
                    len(monitor_result.source_errors)
                    + len(manual_review)
                    + len(prior_result.candidates)
                    + len(evaluation_result.preprints)
                    + len(excluded)
                )
            },
        )

        result = HotScienceRunResult(
            run_id=run_id,
            target_month=target_month,
            user_criteria=user_criteria,
            raw_candidates=monitor_result.candidates,
            source_errors=monitor_result.source_errors,
            unresolved_press=resolver_result.unresolved_press,
            manual_review=manual_review,
            verified=verification_result.verified,
            evaluated=prior_result.candidates,
            preprints=evaluation_result.preprints,
            excluded=excluded,
            compiled=compiled,
        )
        _emit_run_event(
            progress_callback,
            event_type="run_completed",
            stage="run",
            run_id=run_id,
            target_month=target_month,
            message="Hot Science run completed",
            counts={
                key: value
                for key, value in result.summary.items()
                if isinstance(value, int)
            },
        )
        return result


def _emit_stage_started(
    callback: ProgressCallback | None,
    *,
    run_id: str,
    target_month: str,
    stage: str,
    message: str,
    counts: dict[str, int] | None = None,
) -> None:
    _emit_run_event(
        callback,
        event_type="stage_started",
        stage=stage,
        run_id=run_id,
        target_month=target_month,
        message=message,
        counts=counts,
    )


def _emit_stage_completed(
    callback: ProgressCallback | None,
    *,
    run_id: str,
    target_month: str,
    stage: str,
    message: str,
    counts: dict[str, int] | None = None,
) -> None:
    _emit_run_event(
        callback,
        event_type="stage_completed",
        stage=stage,
        run_id=run_id,
        target_month=target_month,
        message=message,
        counts=counts,
    )


def _emit_run_event(
    callback: ProgressCallback | None,
    *,
    event_type: str,
    stage: str,
    run_id: str,
    target_month: str,
    message: str,
    counts: dict[str, int] | None = None,
) -> None:
    emit_progress(
        callback,
        ProgressEvent(
            event_type=event_type,
            stage=stage,
            run_id=run_id,
            target_month=target_month,
            message=message,
            counts=counts or {},
        ),
    )

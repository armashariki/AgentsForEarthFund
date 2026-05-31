"""Phase 1 Hot Science service boundary for the future web UI."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from agents.hot_science.config import HotScienceConfig, load_hot_science_config
from agents.hot_science.orchestrator import HotScienceOrchestrator, HotScienceRunResult
from agents.hot_science.progress import ProgressCallback
from agents.hot_science.storage import CandidateStore
from web.backend.artifacts import HotScienceArtifactStore, primary_artifact
from web.backend.schemas import HotScienceRunRequest, HotScienceRunServiceResult


class HotScienceRunner(Protocol):
    """Small protocol implemented by the real orchestrator and test fakes."""

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
        ...


class HotScienceRunService:
    """Run Hot Science agents and materialize shareable artifacts."""

    def __init__(
        self,
        *,
        config: HotScienceConfig | None = None,
        store: CandidateStore | None = None,
        db_path: str | Path | None = None,
        artifact_store: HotScienceArtifactStore | None = None,
        runner: HotScienceRunner | None = None,
    ):
        self.config = config or load_hot_science_config()
        self.store = store or CandidateStore(
            db_path if db_path is not None else self._default_db_path(artifact_store)
        )
        self.artifact_store = artifact_store or HotScienceArtifactStore()
        self.runner = runner

    def run(
        self,
        request: HotScienceRunRequest,
        *,
        progress_callback: ProgressCallback | None = None,
    ) -> HotScienceRunServiceResult:
        """Run the orchestrator and return artifact metadata for the UI."""
        normalized = request.normalized()
        runner = self.runner or HotScienceOrchestrator(config=self.config, store=self.store)
        result = runner.run(
            normalized.target_month,
            max_results_per_source=normalized.max_results_per_source,
            source_ids=set(normalized.source_ids) if normalized.source_ids else None,
            user_criteria=normalized.criteria_text,
            retrieval_query=normalized.retrieval_query,
            progress_callback=progress_callback,
        )
        artifacts = self.artifact_store.write_run_artifacts(result, normalized)
        return HotScienceRunServiceResult(
            run_id=result.run_id,
            target_month=result.target_month,
            summary=result.summary,
            primary_artifact=primary_artifact(artifacts),
            artifacts=artifacts,
        )

    def _default_db_path(self, artifact_store: HotScienceArtifactStore | None) -> Path:
        data_dir = artifact_store.data_dir if artifact_store else HotScienceArtifactStore().data_dir
        return data_dir / "candidates.sqlite3"

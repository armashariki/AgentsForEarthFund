"""Artifact storage for Hot Science web runs."""

from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Iterable

from agents.hot_science.compiler import CompilerAgent
from agents.hot_science.orchestrator import HotScienceRunResult
from agents.hot_science.schema import utc_now_iso
from web.backend.schemas import ArtifactLink, HotScienceRunRequest


DEFAULT_DATA_DIR = Path(os.getenv("HOT_SCIENCE_DATA_DIR", ".deepgreen/hot_science"))
DEFAULT_DOWNLOAD_PREFIX = "/api/hot-science/artifacts"
_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9._-]+$")


class HotScienceArtifactStore:
    """Write run outputs to a pilot filesystem artifact store."""

    def __init__(
        self,
        data_dir: str | Path | None = None,
        *,
        download_prefix: str = DEFAULT_DOWNLOAD_PREFIX,
    ):
        self.data_dir = Path(data_dir) if data_dir is not None else DEFAULT_DATA_DIR
        self.download_prefix = download_prefix.rstrip("/")

    def write_run_artifacts(
        self,
        result: HotScienceRunResult,
        request: HotScienceRunRequest,
        *,
        compiler: CompilerAgent | None = None,
    ) -> tuple[ArtifactLink, ...]:
        """Write DOCX plus QA/debug artifacts and return download metadata."""
        if result.compiled is None:
            raise ValueError("Hot Science run did not produce a compiled candidate set.")
        compiler = compiler or CompilerAgent()
        run_dir = self.run_dir(result.run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        prefix = _artifact_prefix(result.target_month, result.run_id)

        paths = {
            "docx": run_dir / f"{prefix}.docx",
            "json": run_dir / f"{prefix}.json",
            "markdown": run_dir / f"{prefix}.md",
            "review_csv": run_dir / f"{prefix}_review.csv",
            "source_breakdown_csv": run_dir / f"{prefix}_sources.csv",
        }
        compiler.write_docx(result.compiled, paths["docx"])
        compiler.write_json(result.compiled, paths["json"])
        compiler.write_markdown(result.compiled, paths["markdown"])
        compiler.write_review_csv(result.compiled, paths["review_csv"])
        compiler.write_source_breakdown_csv(
            result.compiled,
            paths["source_breakdown_csv"],
            sources=result.compiled.sources,
            source_errors=result.source_errors,
        )

        artifacts = tuple(
            self._artifact_link(result.run_id, kind, path)
            for kind, path in paths.items()
        )
        self.write_manifest(
            result=result,
            request=request,
            artifacts=artifacts,
            path=run_dir / "manifest.json",
        )
        return artifacts

    def write_manifest(
        self,
        *,
        result: HotScienceRunResult,
        request: HotScienceRunRequest,
        artifacts: Iterable[ArtifactLink],
        path: Path,
    ) -> None:
        """Persist a minimal run manifest for later hidden run history."""
        created_at = utc_now_iso()
        payload = {
            "run_id": result.run_id,
            "created_at": created_at,
            "expires_at": _expires_at(created_at),
            "target_month": result.target_month,
            "requested_by": request.requested_by,
            "request": request.to_dict(),
            "summary": result.summary,
            "artifacts": [asdict(artifact) for artifact in artifacts],
        }
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def list_run_manifests(self, *, include_expired: bool = False) -> list[dict]:
        """List saved run manifests newest first for the hidden run-history view."""
        runs_dir = self.data_dir / "runs"
        if not runs_dir.exists():
            return []
        manifests: list[dict] = []
        for manifest_path in runs_dir.glob("*/manifest.json"):
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not include_expired and manifest_expired(manifest):
                continue
            manifests.append(manifest)
        return sorted(
            manifests,
            key=lambda manifest: str(manifest.get("created_at") or ""),
            reverse=True,
        )

    def load_manifest(self, run_id: str) -> dict | None:
        """Load one run manifest if present."""
        manifest_path = self.run_dir(run_id) / "manifest.json"
        try:
            return json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def artifact_metadata(self, run_id: str, filename: str) -> dict | None:
        """Return manifest metadata for an artifact filename."""
        manifest = self.load_manifest(run_id)
        if not manifest:
            return None
        for artifact in manifest.get("artifacts", []):
            if artifact.get("filename") == filename:
                return artifact
        return None

    def prune_expired_runs(self) -> int:
        """Delete expired run directories and return the number removed."""
        removed = 0
        for manifest in self.list_run_manifests(include_expired=True):
            if not manifest_expired(manifest):
                continue
            run_id = manifest.get("run_id")
            if not isinstance(run_id, str):
                continue
            try:
                shutil.rmtree(self.run_dir(run_id))
                removed += 1
            except OSError:
                continue
        return removed

    def run_dir(self, run_id: str) -> Path:
        return self.data_dir / "runs" / _safe_segment(run_id, "run_id")

    def resolve_artifact_path(self, run_id: str, filename: str) -> Path:
        """Resolve a future download request while preventing path traversal."""
        safe_run_id = _safe_segment(run_id, "run_id")
        if Path(filename).name != filename or not _SAFE_SEGMENT.match(filename):
            raise ValueError("Invalid artifact filename.")
        run_dir = (self.data_dir / "runs" / safe_run_id).resolve()
        path = (run_dir / filename).resolve()
        if path.parent != run_dir:
            raise ValueError("Artifact path escapes the run directory.")
        return path

    def _artifact_link(self, run_id: str, kind: str, path: Path) -> ArtifactLink:
        filename = path.name
        artifact_id = f"{run_id}/{filename}"
        return ArtifactLink(
            artifact_id=artifact_id,
            run_id=run_id,
            kind=kind,
            filename=filename,
            path=str(path),
            download_url=f"{self.download_prefix}/{run_id}/{filename}",
            mime_type=_mime_type(kind),
            size_bytes=path.stat().st_size,
        )


def primary_artifact(artifacts: Iterable[ArtifactLink]) -> ArtifactLink:
    """Return the primary team-facing artifact from an artifact set."""
    for artifact in artifacts:
        if artifact.kind == "docx":
            return artifact
    raise ValueError("No primary DOCX artifact was produced.")


def public_manifest(manifest: dict) -> dict:
    """Return the normal-user run-history view."""
    primary = next(
        (
            artifact
            for artifact in manifest.get("artifacts", [])
            if artifact.get("kind") == "docx"
        ),
        None,
    )
    return {
        "run_id": manifest.get("run_id"),
        "created_at": manifest.get("created_at"),
        "expires_at": manifest.get("expires_at"),
        "target_month": manifest.get("target_month"),
        "requested_by": manifest.get("requested_by"),
        "summary": manifest.get("summary", {}),
        "primary_artifact": primary,
    }


def manifest_expired(manifest: dict, *, now: datetime | None = None) -> bool:
    expires_at = manifest.get("expires_at")
    if not isinstance(expires_at, str) or not expires_at:
        return False
    try:
        expires = datetime.fromisoformat(expires_at)
    except ValueError:
        return False
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    return expires <= (now or datetime.now(UTC))


def artifact_requires_admin(kind: str | None) -> bool:
    """Only the Word doc is normal-user facing in Phase 3."""
    return kind != "docx"


def _expires_at(created_at: str) -> str:
    retention_days = int(os.getenv("HOT_SCIENCE_REPORT_RETENTION_DAYS", "30"))
    created = datetime.fromisoformat(created_at)
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    return (created + timedelta(days=retention_days)).isoformat()


def _artifact_prefix(target_month: str, run_id: str) -> str:
    safe_month = target_month.replace("-", "_")
    safe_run = _safe_segment(run_id, "run_id")[:8]
    return f"hot_science_{safe_month}_{safe_run}"


def _safe_segment(value: str, label: str) -> str:
    if not value or not _SAFE_SEGMENT.match(value):
        raise ValueError(f"Invalid {label}.")
    return value


def _mime_type(kind: str) -> str:
    return {
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "json": "application/json",
        "markdown": "text/markdown",
        "review_csv": "text/csv",
        "source_breakdown_csv": "text/csv",
    }.get(kind, "application/octet-stream")

"""FastAPI backend for the Hot Science Fly.io pilot."""

from __future__ import annotations

from pathlib import Path as FsPath

from fastapi import Depends, FastAPI, HTTPException, Path
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from web.backend.artifacts import (
    HotScienceArtifactStore,
    artifact_requires_admin,
    manifest_expired,
    public_manifest,
)
from web.backend.auth import AuthConfig, UserIdentity
from web.backend.hot_science_service import HotScienceRunService
from web.backend.schemas import HotScienceRunRequest


bearer_scheme = HTTPBearer(auto_error=False)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class RunRequest(BaseModel):
    target_month: str
    criteria_text: str
    retrieval_query: str | None = None
    source_ids: list[str] = Field(default_factory=list)
    max_results_per_source: int = Field(default=25, ge=1)


def create_app(
    *,
    service: HotScienceRunService | None = None,
    artifact_store: HotScienceArtifactStore | None = None,
    auth_config: AuthConfig | None = None,
) -> FastAPI:
    """Create the FastAPI app with injectable dependencies for tests."""
    app = FastAPI(title="DeepGreen Hot Science API", version="0.1.0")
    auth = auth_config or AuthConfig.from_env()
    store = artifact_store or HotScienceArtifactStore()
    run_service = service or HotScienceRunService(artifact_store=store)

    def current_user(
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    ) -> UserIdentity:
        if credentials is None:
            raise HTTPException(status_code=401, detail="Authentication required.")
        identity = auth.verify_token(credentials.credentials)
        if identity is None:
            raise HTTPException(status_code=401, detail="Invalid or expired token.")
        return identity

    def current_admin(user: UserIdentity = Depends(current_user)) -> UserIdentity:
        if not user.is_admin:
            raise HTTPException(status_code=403, detail="Admin access required.")
        return user

    @app.get("/health")
    def health() -> dict[str, str | bool]:
        return {
            "status": "ok",
            "service": "hot_science_api",
            "auth_configured": bool(auth.users),
        }

    @app.post("/api/auth/login")
    def login(payload: LoginRequest) -> dict:
        if not auth.users:
            raise HTTPException(status_code=503, detail="Pilot users are not configured.")
        identity = auth.authenticate(payload.username, payload.password)
        if identity is None:
            raise HTTPException(status_code=401, detail="Invalid username or password.")
        return {
            "access_token": auth.create_token(identity),
            "token_type": "bearer",
            "user": identity.to_dict(),
        }

    @app.get("/api/me")
    def me(user: UserIdentity = Depends(current_user)) -> dict:
        return {"user": user.to_dict()}

    @app.post("/api/hot-science/runs")
    def run_hot_science(
        payload: RunRequest,
        user: UserIdentity = Depends(current_user),
    ) -> dict:
        events = []
        request = HotScienceRunRequest(
            target_month=payload.target_month,
            criteria_text=payload.criteria_text,
            retrieval_query=payload.retrieval_query,
            source_ids=tuple(payload.source_ids),
            max_results_per_source=payload.max_results_per_source,
            requested_by=user.username,
        )
        try:
            result = run_service.run(
                request,
                progress_callback=events.append,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "run_id": result.run_id,
            "target_month": result.target_month,
            "summary": result.summary,
            "primary_artifact": result.primary_artifact.to_dict(),
            "progress_events": [event.to_dict() for event in events],
        }

    @app.get("/api/hot-science/runs")
    def list_runs(user: UserIdentity = Depends(current_user)) -> dict:
        return {
            "runs": [
                public_manifest(manifest)
                for manifest in store.list_run_manifests(include_expired=False)
            ]
        }

    @app.get("/api/admin/hot-science/runs")
    def list_admin_runs(user: UserIdentity = Depends(current_admin)) -> dict:
        return {"runs": store.list_run_manifests(include_expired=False)}

    @app.post("/api/admin/hot-science/prune-expired")
    def prune_expired(user: UserIdentity = Depends(current_admin)) -> dict:
        return {"removed": store.prune_expired_runs()}

    @app.get("/api/hot-science/artifacts/{run_id}/{filename}")
    def download_artifact(
        run_id: str = Path(pattern=r"^[A-Za-z0-9._-]+$"),
        filename: str = Path(pattern=r"^[A-Za-z0-9._-]+$"),
        user: UserIdentity = Depends(current_user),
    ):
        try:
            artifact_path = store.resolve_artifact_path(run_id, filename)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not artifact_path.exists():
            raise HTTPException(status_code=404, detail="Artifact not found.")

        manifest = store.load_manifest(run_id)
        if manifest and manifest_expired(manifest):
            raise HTTPException(status_code=410, detail="Artifact has expired.")
        metadata = store.artifact_metadata(run_id, filename)
        kind = metadata.get("kind") if metadata else None
        if artifact_requires_admin(kind) and not user.is_admin:
            raise HTTPException(status_code=403, detail="Admin access required for this artifact.")
        media_type = metadata.get("mime_type") if metadata else "application/octet-stream"
        return FileResponse(
            artifact_path,
            media_type=media_type,
            filename=filename,
        )

    _mount_frontend(app)
    return app

def _mount_frontend(app: FastAPI) -> None:
    """Serve the built React app when `web/frontend/dist` exists."""
    dist = FsPath(__file__).resolve().parents[1] / "frontend" / "dist"
    if not dist.exists():
        return
    assets = dist / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="frontend_assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_frontend(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found.")
        dist_root = dist.resolve()
        candidate = (dist_root / full_path).resolve()
        if candidate.is_file() and dist_root in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(dist_root / "index.html")


app = create_app()

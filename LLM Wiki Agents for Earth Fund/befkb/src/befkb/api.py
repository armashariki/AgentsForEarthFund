"""Minimal FastAPI surface for the befkb engine.

Two endpoints mirror the two core operations:

- ``POST /ingest``  → ingest a document already present on disk (under ``raw/``),
  returning the :class:`~befkb.models.IngestReport`.
- ``POST /apply``   → answer "how does this new content connect to my grants?",
  returning the :class:`~befkb.models.ApplicabilityResult`.

The engine is local-first and single-tenant; this server is a convenience layer
(``befkb serve``), not a multi-user backend. Paths are validated to live inside
the configured ``wiki_root`` so the API can't be pointed at arbitrary files.

Heavy modules are imported lazily inside the handlers so that importing this
module (and the OpenAPI schema) never fails on a missing optional dependency.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .config import Settings, load_settings
from .models import ApplicabilityResult, IngestReport

app = FastAPI(
    title="befkb",
    version="0.1.0",
    summary="Ingest documents into a knowledge graph and ask how they connect to your grants.",
)


# --------------------------------------------------------------------------- #
# Request bodies
# --------------------------------------------------------------------------- #

class IngestRequest(BaseModel):
    path: str = Field(..., description="Path to a source document, absolute or relative to wiki_root.")


class ApplyRequest(BaseModel):
    path: str = Field(..., description="Path to the new content to evaluate against your grants.")
    max_hops: int | None = Field(None, description="Optional graph-traversal depth override.")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _resolve_path(raw_path: str, settings: Settings) -> Path:
    """Resolve a request path and confine it to the wiki root for safety."""
    p = Path(raw_path)
    if not p.is_absolute():
        p = (settings.wiki_root / p).resolve()
    else:
        p = p.resolve()
    try:
        p.relative_to(settings.wiki_root.resolve())
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"path must live under the wiki root ({settings.wiki_root}); got {p}",
        )
    if not p.exists() or not p.is_file():
        raise HTTPException(status_code=404, detail=f"file not found: {p}")
    return p


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #

@app.get("/health")
def health() -> dict:
    """Liveness probe."""
    return {"status": "ok", "service": "befkb"}


@app.post("/ingest", response_model=IngestReport)
def ingest_endpoint(req: IngestRequest) -> IngestReport:
    """Ingest a source document into the knowledge graph + vector index."""
    settings = load_settings()
    settings.ensure_dirs()
    path = _resolve_path(req.path, settings)  # validate path BEFORE importing the engine
    from . import pipeline

    try:
        return pipeline.ingest(path, settings)
    except Exception as exc:  # surface engine errors as 500 with a message, not a stack trace
        raise HTTPException(status_code=500, detail=f"ingest failed: {exc}") from exc


@app.post("/apply", response_model=ApplicabilityResult)
def apply_endpoint(req: ApplyRequest) -> ApplicabilityResult:
    """Answer how new content connects to the grants in the knowledge base."""
    import inspect

    settings = load_settings()
    settings.ensure_dirs()
    path = _resolve_path(req.path, settings)  # validate path BEFORE importing the engine
    from . import pipeline

    try:
        params = inspect.signature(pipeline.apply).parameters
        if req.max_hops is not None and "max_hops" in params:
            return pipeline.apply(path, settings, max_hops=req.max_hops)
        return pipeline.apply(path, settings)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"apply failed: {exc}") from exc

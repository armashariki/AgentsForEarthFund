"""Progress events for Hot Science runs."""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Callable

from agents.hot_science.schema import utc_now_iso


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProgressEvent:
    """A UI-friendly progress event emitted by the Hot Science pipeline."""

    event_type: str
    stage: str
    message: str
    run_id: str | None = None
    target_month: str | None = None
    source_id: str | None = None
    source_name: str | None = None
    counts: dict[str, int] = field(default_factory=dict)
    detail: str | None = None
    timestamp: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict:
        """Serialize the event for API responses or logs."""
        return asdict(self)


ProgressCallback = Callable[[ProgressEvent], None]


def emit_progress(callback: ProgressCallback | None, event: ProgressEvent) -> None:
    """Emit a progress event without letting UI callbacks change run behavior."""
    if callback is None:
        return
    try:
        callback(event)
    except Exception as exc:
        logger.warning("Hot Science progress callback failed: %s", exc)

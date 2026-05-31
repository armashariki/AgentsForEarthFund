"""Backend service boundary for the DeepGreen web UI."""

from agents.hot_science.progress import ProgressEvent
from web.backend.hot_science_service import HotScienceRunService
from web.backend.schemas import HotScienceRunRequest, HotScienceRunServiceResult

__all__ = [
    "HotScienceRunRequest",
    "HotScienceRunService",
    "HotScienceRunServiceResult",
    "ProgressEvent",
]

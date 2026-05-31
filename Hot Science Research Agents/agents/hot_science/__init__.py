"""UC-I-1 Hot Science research monitoring pipeline."""

from agents.hot_science.orchestrator import HotScienceOrchestrator
from agents.hot_science.progress import ProgressEvent
from agents.hot_science.schema import CandidateRecord

__all__ = ["CandidateRecord", "HotScienceOrchestrator", "ProgressEvent"]

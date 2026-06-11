"""Configuration — one Settings object loaded from env with sane local-first defaults.

The engine lives at ``LLM Wiki/befkb`` and reads ``../raw`` (immutable) and writes
``../wiki`` (the existing markdown wiki). Engine-owned state lives in ``./data``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# befkb/src/befkb/config.py  -> parents[2] == befkb/ ; parents[3] == "LLM Wiki/"
_PKG_ROOT = Path(__file__).resolve().parents[2]          # .../LLM Wiki/befkb
_WIKI_ROOT = _PKG_ROOT.parent                            # .../LLM Wiki


@dataclass
class Settings:
    # paths
    wiki_root: Path = _WIKI_ROOT
    raw_dir: Path = _WIKI_ROOT / "raw"
    wiki_dir: Path = _WIKI_ROOT / "wiki"
    data_dir: Path = _PKG_ROOT / "data"

    # models (both already pulled + smoke-tested)
    ollama_host: str = "http://localhost:11434"
    chat_model: str = "qwen2.5:7b-instruct"
    embed_model: str = "nomic-embed-text"
    embed_dim: int = 768

    # optional cloud accuracy lever (extraction/claims only) — off unless a key is present
    cloud_provider: str | None = None     # "anthropic" | "openai" | None
    cloud_model: str | None = None

    # entity-resolution thresholds
    resolve_auto_merge: float = 0.92      # >= -> auto-merge
    resolve_review_min: float = 0.78      # [review_min, auto) -> human review queue; below -> new node

    # applicability traversal knobs
    max_hops: int = 3
    hub_penalty: bool = True
    hub_degree_threshold: int = 8         # nodes with degree above this are penalised as hubs

    # chunking
    chunk_chars: int = 1200
    chunk_overlap: int = 150

    @property
    def graph_dir(self) -> Path:
        return self.data_dir / "graph"

    @property
    def lancedb_dir(self) -> Path:
        return self.data_dir / "lancedb"

    @property
    def review_dir(self) -> Path:
        return self.data_dir / "review"

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.graph_dir, self.lancedb_dir, self.review_dir):
            d.mkdir(parents=True, exist_ok=True)


def load_settings() -> Settings:
    """Build Settings from defaults, overridden by env vars where present."""
    s = Settings()
    s.ollama_host = os.environ.get("OLLAMA_HOST", s.ollama_host)
    s.chat_model = os.environ.get("BEFKB_CHAT_MODEL", s.chat_model)
    s.embed_model = os.environ.get("BEFKB_EMBED_MODEL", s.embed_model)
    # cloud lever: only on if a key is explicitly present
    if os.environ.get("ANTHROPIC_API_KEY"):
        s.cloud_provider = "anthropic"
        s.cloud_model = os.environ.get("BEFKB_CLOUD_MODEL", "claude-3-5-sonnet-latest")
    elif os.environ.get("OPENAI_API_KEY"):
        s.cloud_provider = "openai"
        s.cloud_model = os.environ.get("BEFKB_CLOUD_MODEL", "gpt-4o-mini")
    if os.environ.get("BEFKB_DATA_DIR"):
        s.data_dir = Path(os.environ["BEFKB_DATA_DIR"]).resolve()
    return s

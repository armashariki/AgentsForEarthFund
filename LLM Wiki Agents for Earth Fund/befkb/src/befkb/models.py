"""befkb data model — the single source of truth for all shapes.

Mirrors the wiki ontology in ``wiki/_schema/bef-ai-knowledge-model.md`` so the
knowledge graph and the human-facing markdown wiki speak one language.

Pure Pydantic v2 + a few tiny id/slug helpers. No I/O, no LLM, no graph logic.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field

# --------------------------------------------------------------------------- #
# Controlled vocabularies (transcribed 1:1 from the wiki v3 ontology)
# --------------------------------------------------------------------------- #

NodeType = Literal[
    "Technology",    # tools / models / systems / open-source / hardware (CAPTAIN, GPUs, an LLM)
    "Method",        # AI technique/approach (reinforcement learning, remote sensing, bioacoustics)
    "Concept",       # domain concept/metric (30x30, irrecoverable carbon, Species Habitat Index)
    "Idea",          # abstract recurring idea/worldview (top-down optimization, ecosystems-as-data,
                     # relational accountability, Indigenous data sovereignty) — the bridge node type
    "Person",        # author / builder
    "Organization",  # lab / company / funder (Anthropic, Microsoft, UBC)
    "Source",        # an ingested document (paper / blog / PPTX / grant report)
    "Grant",         # INTERNAL work — the target set of the applicability query (internal=true)
    "Assessment",    # head-of-AI verdict (human-approved; agent only drafts) — not emitted in Phase 1
    "Thesis",        # standing position on AI capability for climate/nature (human-approved)
]

# Edge.rel controlled vocabulary — exactly the schema's relation words.
RELATION_VOCAB: tuple[str, ...] = (
    "authored-by",        # Source -> Person
    "built-by",           # Technology -> Organization
    "uses-technology",    # Source/Grant -> Technology
    "uses-method",        # Source/Grant -> Method
    "applies-idea",       # Source -> Idea           (the idea-level bridge)
    "addresses-domain",   # Source/Grant -> Concept
    "advances-over",      # Source/Method -> Source/Method
    "benchmarked-against",
    "state-of-the-art-for",
    "supports",           # Source <-> Source/Assessment
    "contradicts",
    "duplicates",
    "supersedes",
    "has-tradeoff-with",  # climate <-> nature
    "informs",            # -> Thesis
    "challenges",         # -> Thesis
    "verified-by",        # VVB
    "assessed-as",        # Source -> Assessment
    "affiliated-with",    # Person -> Organization
    "mentions",           # generic fallback Source -> any
)

ClaimStatus = Literal["supported", "unsupported-by-source", "contradicts-KB", "vague"]
Sensitivity = Literal["public", "internal", "restricted"]
ConnectionKind = Literal["shared-entity", "shared-idea", "capability-transfer", "tradeoff", "same-org"]


# --------------------------------------------------------------------------- #
# id / slug helpers (tiny, deterministic, no external deps)
# --------------------------------------------------------------------------- #

def slugify(text: str) -> str:
    """Lowercase, ascii, kebab-case — matches the wiki's filename convention."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text or "x"


def node_id(node_type: str, name: str) -> str:
    """Stable canonical node id: ``type:slug`` (entity resolution may remap aliases to this)."""
    return f"{node_type.lower()}:{slugify(name)}"


def short_hash(text: str, n: int = 8) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:n]


# --------------------------------------------------------------------------- #
# Core shapes
# --------------------------------------------------------------------------- #

class Citation(BaseModel):
    source_slug: str
    char_span: Optional[tuple[int, int]] = None
    quote: Optional[str] = None


class Section(BaseModel):
    title: str
    text: str
    char_span: tuple[int, int]


class Doc(BaseModel):
    """A parsed source document (one entry in raw/)."""
    source_slug: str
    path: str
    title: str = ""
    markdown: str
    sections: list[Section] = Field(default_factory=list)
    doc_date: Optional[date] = None
    meta: dict = Field(default_factory=dict)


class Chunk(BaseModel):
    id: str
    source_slug: str
    section: str
    text: str
    char_span: tuple[int, int]
    embedding: Optional[list[float]] = None


class Claim(BaseModel):
    id: str
    text: str
    source_slug: str
    source_span: Optional[tuple[int, int]] = None
    status: ClaimStatus = "supported"
    rationale: str = ""
    evidence: list[Citation] = Field(default_factory=list)
    confidence: float = 0.5


class Node(BaseModel):
    id: str                       # canonical id, e.g. "technology:captain"
    type: NodeType
    name: str                     # canonical display name
    aliases: list[str] = Field(default_factory=list)
    props: dict = Field(default_factory=dict)   # internal=True for Grants, sensitivity, etc.
    provenance: list[Citation] = Field(default_factory=list)
    sensitivity: Sensitivity = "internal"


class Edge(BaseModel):
    src: str                      # node id
    rel: str                      # one of RELATION_VOCAB (validated softly)
    dst: str                      # node id
    citation: Optional[Citation] = None
    confidence: float = 0.6


# --------------------------------------------------------------------------- #
# Extraction / resolution / applicability result shapes
# --------------------------------------------------------------------------- #

class ExtractedEntity(BaseModel):
    """Raw LLM output before canonicalization (resolve.py maps these to Nodes)."""
    name: str
    type: NodeType
    span_quote: Optional[str] = None


class ExtractedRelation(BaseModel):
    src_name: str
    rel: str
    dst_name: str
    quote: Optional[str] = None


class ResolutionResult(BaseModel):
    merged: list[tuple[str, str]] = Field(default_factory=list)        # (new_id, canonical_id)
    created: list[Node] = Field(default_factory=list)
    needs_review: list[tuple[str, str, float]] = Field(default_factory=list)  # (a_id, b_id, score)


class Connection(BaseModel):
    grant_id: str
    grant_name: str
    path: list[Edge] = Field(default_factory=list)
    shared_nodes: list[str] = Field(default_factory=list)
    evidence: list[Citation] = Field(default_factory=list)
    why: str = ""
    kind: ConnectionKind = "shared-entity"
    strength: float = 0.0


class ApplicabilityResult(BaseModel):
    new_doc: str
    connections: list[Connection] = Field(default_factory=list)
    novel_to_kb: list[str] = Field(default_factory=list)   # entity names new to the KB
    flagged_claims: list[Claim] = Field(default_factory=list)
    summary: str = ""


class IngestReport(BaseModel):
    source_slug: str
    nodes_created: int = 0
    nodes_merged: int = 0
    edges: int = 0
    claims_total: int = 0
    flagged_claims: int = 0
    chunks: int = 0
    pages_written: list[str] = Field(default_factory=list)

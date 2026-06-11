"""Pipeline orchestration — wire the whole engine together.

Two public entry points, both constructed entirely from a :class:`Settings`:

* :func:`ingest` — parse a raw source, mine claims, extract a graph, resolve
  entities against the persistent KB (writing merges), upsert nodes/edges,
  chunk + index for retrieval, queue shaky claims, persist, and log.
* :func:`apply` — answer "how does this *new* content connect to my grants?"
  by delegating to :func:`applicability.how_does_this_apply` over the existing
  KB (read-only on the graph; no write-back of the new doc's nodes).

Design notes
------------
* **Lazy sibling imports.** Heavy/composable modules (parser, chunk, extract,
  resolve, graphstore, retrieve, claims, applicability) are imported *inside*
  the functions, not at module top-level. This keeps ``pipeline`` importable on
  its own (the CLI imports it without forcing every sibling to exist yet) and
  sidesteps import cycles.
* **Canonical remap.** :func:`resolve.resolve` returns a mapping new-id ->
  canonical-id for auto-merged nodes. We apply that mapping to *both* the
  surviving node set and every edge endpoint before upserting, so the graph
  never accrues duplicate-but-unmerged nodes.
* **Provenance is preserved**, not invented: we only ever move ids around; the
  per-node ``provenance`` and per-edge ``citation`` set upstream by extract.py
  travel with the remapped objects.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from .config import Settings
from .llm import get_embedder, get_llm
from .models import ApplicabilityResult, Edge, IngestReport, Node, ResolutionResult

__all__ = ["ingest", "apply", "build_context", "EngineContext"]


# --------------------------------------------------------------------------- #
# Shared engine context (built once from Settings)
# --------------------------------------------------------------------------- #

class EngineContext:
    """Bundle of fully-constructed collaborators for one operation.

    Construction is lazy on the sibling modules so importing :mod:`pipeline`
    never requires every sibling to exist. Building a context *does* require
    them (you cannot run a pipeline without its parts).
    """

    def __init__(self, settings: Settings):
        # Local sibling modules — imported here, not at top level, on purpose.
        from .chunk import LanceStore
        from .graphstore import NetworkXGraphStore
        from .retrieve import Retriever

        self.settings = settings
        self.llm = get_llm(settings)
        self.embedder = get_embedder(settings)

        # Graph spine: load any persisted state so ingests/applies are cumulative.
        # ``load`` is a no-op on a fresh install (no graph.jsonl yet); guard
        # broadly so a corrupt/partial persisted file can't sink construction.
        self.graph = NetworkXGraphStore(settings)
        try:
            self.graph.load()
        except Exception:  # pragma: no cover - first-ever / recoverable load
            pass

        # Vector + lexical index.
        self.lance = LanceStore(settings)

        # Retriever sits on top of both.
        self.retriever = Retriever(self.lance, self.embedder, self.graph)


def build_context(settings: Settings) -> EngineContext:
    """Construct GraphStore/LanceStore/Retriever/llm/embedder from settings."""
    return EngineContext(settings)


# --------------------------------------------------------------------------- #
# Canonical-id remapping after entity resolution
# --------------------------------------------------------------------------- #

def _merge_map(res: ResolutionResult) -> dict[str, str]:
    """new_node_id -> canonical_id for every auto-merged node (identity elsewhere)."""
    return {new_id: canon_id for new_id, canon_id in res.merged}


def _remap_nodes(nodes: list[Node], merge: dict[str, str]) -> list[Node]:
    """Replace merged nodes by their canonical id; keep the rest as-is.

    For auto-merged nodes we drop the *new* node object (the canonical node in
    the graph is authoritative and ``resolve`` already wrote the merge); the new
    node's provenance was folded in by ``resolve``/``upsert``'s alias+provenance
    union. We keep only nodes that survive as their own canonical entity.
    """
    survivors: list[Node] = []
    seen: set[str] = set()
    for n in nodes:
        canon = merge.get(n.id, n.id)
        if canon != n.id:
            # merged away — the canonical node already exists in the graph.
            continue
        if canon in seen:
            continue
        seen.add(canon)
        survivors.append(n)
    return survivors


def _remap_edges(edges: list[Edge], merge: dict[str, str]) -> list[Edge]:
    """Rewrite both endpoints of every edge through the merge map; drop self-loops."""
    out: list[Edge] = []
    seen: set[tuple[str, str, str]] = set()
    for e in edges:
        src = merge.get(e.src, e.src)
        dst = merge.get(e.dst, e.dst)
        if not src or not dst or src == dst:
            continue  # collapsed onto itself after merge — meaningless self-loop
        key = (src, e.rel, dst)
        if key in seen:
            continue
        seen.add(key)
        out.append(e.model_copy(update={"src": src, "dst": dst}))
    return out


# --------------------------------------------------------------------------- #
# log.md (append one line per operation)
# --------------------------------------------------------------------------- #

def _append_log(settings: Settings, line: str) -> None:
    """Append one greppable ``## [date] ...`` entry to ``wiki/log.md``.

    Best-effort and never fatal: a logging failure must not sink an ingest.
    """
    try:
        log_path = settings.wiki_dir / "log.md"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        prefix = "\n" if log_path.exists() and log_path.stat().st_size else ""
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(f"{prefix}## {line}\n")
    except Exception:  # pragma: no cover - logging is advisory only
        pass


# --------------------------------------------------------------------------- #
# INGEST
# --------------------------------------------------------------------------- #

def ingest(path: Path, settings: Settings) -> IngestReport:
    """Ingest one raw source into the KB and return an :class:`IngestReport`.

    Steps (each delegated to a sibling module):
        parse -> claims (extract + flag_shaky) -> extract_graph
        -> resolve(write=True) -> remap to canonical ids -> graph upsert
        -> chunk_and_index -> write_review_queue -> graph.save -> log.
    """
    from .claims import extract_claims, flag_shaky, write_review_queue
    from .chunk import chunk_and_index
    from .extract import extract_graph
    from .ingest.parser import get_parser
    from .resolve import resolve

    path = Path(path)
    settings.ensure_dirs()
    ctx = build_context(settings)

    # 1) Parse -----------------------------------------------------------------
    parser = get_parser(path)
    doc = parser.parse(path)

    # 2) Claims: mine, then flag the shaky ones against KB + retrieval ----------
    # NB: flag_shaky mutates `claims` in place and returns only the flagged
    # subset — so we keep `claims` intact (full set) and capture the subset.
    claims = extract_claims(doc, ctx.llm)
    flagged: list = []
    try:
        flagged = flag_shaky(claims, doc, ctx.retriever, ctx.graph, ctx.llm, settings)
    except Exception:
        # flagging is an enrichment; never let it block the ingest. Fall back to
        # whatever status extraction itself assigned.
        flagged = [c for c in claims if c.status != "supported"]

    # 3) Extract the graph (schema-constrained; emits Idea bridge nodes) --------
    nodes, edges = extract_graph(doc, claims, ctx.llm, settings)

    # 4) Resolve new nodes against the persistent KB (writes merges) -----------
    res = resolve(nodes, ctx.graph, ctx.embedder, settings, write=True)
    merge = _merge_map(res)

    # 5) Remap surviving nodes + all edges to canonical ids, then upsert -------
    nodes = _remap_nodes(nodes, merge)
    edges = _remap_edges(edges, merge)
    ctx.graph.upsert_nodes(nodes)
    ctx.graph.upsert_edges(edges)

    # 6) Chunk + index for hybrid retrieval ------------------------------------
    chunks = chunk_and_index(doc, ctx.embedder, ctx.lance, settings)

    # 7) Queue shaky claims for human review -----------------------------------
    if flagged:
        try:
            write_review_queue(flagged, settings.review_dir)
        except Exception:  # pragma: no cover - advisory
            pass

    # 8) Persist the graph ------------------------------------------------------
    ctx.graph.save()

    # 9) Report -----------------------------------------------------------------
    report = IngestReport(
        source_slug=doc.source_slug,
        nodes_created=len(res.created),
        nodes_merged=len(res.merged),
        edges=len(edges),
        claims_total=len(claims),
        flagged_claims=len(flagged),
        chunks=len(chunks),
        pages_written=[],
    )

    _append_log(
        settings,
        f"[{date.today().isoformat()}] ingest | {doc.title or doc.source_slug}"
        f"  →  nodes:{report.nodes_created} merged:{report.nodes_merged} "
        f"edges:{report.edges} chunks:{report.chunks} flagged:{report.flagged_claims}",
    )
    return report


# --------------------------------------------------------------------------- #
# APPLY
# --------------------------------------------------------------------------- #

def apply(
    path: Path,
    settings: Settings,
    max_hops: int | None = None,
) -> ApplicabilityResult:
    """Answer "how does this new content connect to my grants?" (read-only graph).

    Parses the new doc, extracts its entities (no write-back), anchors them to
    existing canonical nodes, seeds the Grant set, finds undirected bridge paths,
    gathers per-edge evidence, and narrates — all inside
    :func:`applicability.how_does_this_apply`.

    ``max_hops`` overrides ``settings.max_hops`` for this one call (the CLI/API
    surface a ``--max-hops`` knob and probe this parameter's presence).
    """
    from .applicability import how_does_this_apply

    path = Path(path)
    settings.ensure_dirs()
    ctx = build_context(settings)

    hops = settings.max_hops if max_hops is None else int(max_hops)
    result = how_does_this_apply(
        path,
        ctx.llm,
        ctx.graph,
        ctx.retriever,
        ctx.embedder,
        settings,
        max_hops=hops,
    )

    _append_log(
        settings,
        f"[{date.today().isoformat()}] apply  | \"{result.new_doc}\""
        f"  →  connections:{len(result.connections)} "
        f"novel:{len(result.novel_to_kb)} flagged:{len(result.flagged_claims)}",
    )
    return result

"""The spine — the knowledge-graph store.

A :class:`GraphStore` Protocol plus :class:`NetworkXGraphStore`, an embedded
graph on a ``networkx.MultiDiGraph``. Nodes carry the full :class:`~befkb.models.Node`
(stored under the ``node`` data key); edges carry the full :class:`~befkb.models.Edge`
and are keyed by their ``rel`` so parallel relations between the same pair coexist.

The single most important method is :meth:`NetworkXGraphStore.paths`. Directed
shortest-path traversal *fails* on the canonical applicability shape::

    paper  --applies-idea-->  idea  <--applies-idea--  grant

because there is no directed walk from ``paper`` to ``grant`` — the idea is a
*sink* reached from both sides. We therefore enumerate simple paths over an
**undirected** view of the multigraph, then map each node-path back to the
concrete :class:`Edge` list that connects it, optionally penalising routes that
pass through high-degree hub nodes.

Persistence is intentionally boring and local-first:
  * ``graph_dir/graph.jsonl`` — one JSON object per line, ``{"kind": "node"|"edge", ...}``.
  * ``graph_dir/aliases.sqlite`` — an ``id -> canonical_id`` alias table that
    entity-resolution writes and read-side code consults to follow merges.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterable, Optional, Protocol, runtime_checkable

import networkx as nx

from .config import Settings
from .models import Edge, Node, NodeType

__all__ = ["GraphStore", "NetworkXGraphStore"]


# --------------------------------------------------------------------------- #
# Interface
# --------------------------------------------------------------------------- #

@runtime_checkable
class GraphStore(Protocol):
    """The minimal contract every storage backend must satisfy."""

    def upsert_nodes(self, nodes: Iterable[Node]) -> None: ...
    def upsert_edges(self, edges: Iterable[Edge]) -> None: ...
    def get_node(self, node_id: str) -> Optional[Node]: ...
    def neighbors(self, node_id: str, rels: Optional[Iterable[str]] = None) -> list[Edge]: ...
    def nodes_by_type(self, node_type: str) -> list[Node]: ...
    def paths(
        self,
        src: str,
        dst: str,
        max_hops: int = 3,
        undirected: bool = True,
        hub_penalty: bool = True,
    ) -> list[list[Edge]]: ...
    def save(self) -> None: ...
    def load(self) -> None: ...


# --------------------------------------------------------------------------- #
# NetworkX implementation
# --------------------------------------------------------------------------- #

class NetworkXGraphStore:
    """A ``MultiDiGraph``-backed :class:`GraphStore` with JSONL + sqlite persistence."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.g: nx.MultiDiGraph = nx.MultiDiGraph()
        self._graph_dir: Path = settings.graph_dir
        self._jsonl_path: Path = self._graph_dir / "graph.jsonl"
        self._alias_path: Path = self._graph_dir / "aliases.sqlite"

    # ---- write ---------------------------------------------------------- #

    def upsert_nodes(self, nodes: Iterable[Node]) -> None:
        """Insert or merge nodes by id.

        On id collision the *existing* node is kept as the spine and the new
        node's ``aliases``, ``provenance`` and ``props`` are folded in (union /
        last-write-wins for scalar props). Empty names are dropped defensively —
        the graph never holds a nameless node.
        """
        for node in nodes:
            if not node or not node.name or not node.name.strip():
                continue
            if not node.id:
                continue
            existing = self._node_obj(node.id)
            if existing is None:
                # store a deep-ish copy so callers can't mutate graph state by reference
                self.g.add_node(node.id, node=node.model_copy(deep=True))
            else:
                merged = self._merge_node(existing, node)
                self.g.add_node(node.id, node=merged)

    def upsert_edges(self, edges: Iterable[Edge]) -> None:
        """Insert or update edges, keyed by ``rel`` between a (src, dst) pair.

        Endpoints that are missing are created as lightweight placeholder nodes
        so an edge is never silently dropped; later ``upsert_nodes`` will enrich
        them. On an existing (src, rel, dst) triple we keep the higher-confidence
        edge and prefer one that carries a citation.
        """
        for edge in edges:
            if not edge or not edge.src or not edge.dst or not edge.rel:
                continue
            self._ensure_node(edge.src)
            self._ensure_node(edge.dst)
            key = edge.rel
            if self.g.has_edge(edge.src, edge.dst, key=key):
                prev: Edge = self.g[edge.src][edge.dst][key]["edge"]
                self.g[edge.src][edge.dst][key]["edge"] = self._merge_edge(prev, edge)
            else:
                self.g.add_edge(edge.src, edge.dst, key=key, edge=edge.model_copy(deep=True))

    # ---- read ----------------------------------------------------------- #

    def get_node(self, node_id: str) -> Optional[Node]:
        """Return the canonical Node for an id, following the alias table."""
        canonical = self.resolve_alias(node_id)
        return self._node_obj(canonical)

    def neighbors(self, node_id: str, rels: Optional[Iterable[str]] = None) -> list[Edge]:
        """All edges incident to ``node_id`` (both directions), optionally filtered by rel."""
        canonical = self.resolve_alias(node_id)
        if canonical not in self.g:
            return []
        rel_set = set(rels) if rels is not None else None
        out: list[Edge] = []
        for _, _, data in self.g.out_edges(canonical, data=True):
            edge = data.get("edge")
            if edge is not None and (rel_set is None or edge.rel in rel_set):
                out.append(edge)
        for _, _, data in self.g.in_edges(canonical, data=True):
            edge = data.get("edge")
            if edge is not None and (rel_set is None or edge.rel in rel_set):
                out.append(edge)
        return out

    def nodes_by_type(self, node_type: str) -> list[Node]:
        """Every node whose ``type`` equals ``node_type``."""
        out: list[Node] = []
        for _, data in self.g.nodes(data=True):
            node = data.get("node")
            if node is not None and node.type == node_type:
                out.append(node)
        return out

    # ---- path finding (the spine's reason to exist) --------------------- #

    def paths(
        self,
        src: str,
        dst: str,
        max_hops: int = 3,
        undirected: bool = True,
        hub_penalty: bool = True,
    ) -> list[list[Edge]]:
        """Enumerate simple paths from ``src`` to ``dst`` as ordered edge lists.

        ``max_hops`` bounds the number of *edges* (path length). When
        ``undirected`` is True (the default, and the only correct setting for
        applicability) traversal ignores edge direction — this is what lets a
        ``paper -> idea <- grant`` bridge be discovered.

        ``hub_penalty`` deprioritises (and, for clearly hubby routes, drops)
        paths that pass through *intermediate* nodes whose total degree exceeds
        ``settings.hub_degree_threshold``: those nodes connect to everything, so
        a path through them is rarely a meaningful explanation.

        Returns paths sorted shortest-first, then by ascending hub cost.
        """
        src = self.resolve_alias(src)
        dst = self.resolve_alias(dst)
        if src not in self.g or dst not in self.g or src == dst:
            return []

        # cutoff is in nodes for all_simple_paths; a path with `max_hops` edges
        # visits `max_hops + 1` nodes, so cutoff = max_hops.
        view = self.g.to_undirected(as_view=True) if undirected else self.g

        scored: list[tuple[int, float, list[Edge]]] = []
        try:
            node_paths = nx.all_simple_paths(view, src, dst, cutoff=max_hops)
        except (nx.NodeNotFound, nx.NetworkXNoPath):
            return []

        for node_path in node_paths:
            hub_cost = self._path_hub_cost(node_path) if hub_penalty else 0.0
            # Drop a path only if an *intermediate* node is a hub AND a
            # cleaner alternative could exist (we always keep at least the
            # direct, hub-free routes; hubby ones sink to the bottom but are
            # not discarded outright so the caller still sees a connection).
            edge_path = self._edges_for_node_path(node_path)
            if edge_path is None:
                continue
            scored.append((len(edge_path), hub_cost, edge_path))

        # shortest-first, then least-hubby
        scored.sort(key=lambda t: (t[0], t[1]))
        return [edges for _, _, edges in scored]

    # ---- persistence ---------------------------------------------------- #

    def save(self, force: bool = False) -> None:
        """Write nodes+edges to ``graph.jsonl`` atomically (temp file + os.replace).

        Guards the classic "failed load -> save truncates the whole KB" footgun: refuses
        to overwrite a non-empty persisted graph when this instance's load() failed or the
        in-memory graph is empty. Pass ``force=True`` to override intentionally.
        """
        import os

        self.settings.ensure_dirs()
        self._graph_dir.mkdir(parents=True, exist_ok=True)

        disk_nonempty = self._jsonl_path.exists() and self._jsonl_path.stat().st_size > 0
        if not force and disk_nonempty:
            if getattr(self, "_load_failed", False):
                raise RuntimeError(
                    "Refusing to save: a previous graph.load() failed, so the in-memory graph "
                    "is incomplete and saving would destroy the on-disk KB. Fix graph.jsonl or "
                    "call save(force=True)."
                )
            if self.g.number_of_nodes() == 0:
                raise RuntimeError(
                    "Refusing to overwrite a non-empty graph.jsonl with an empty graph "
                    "(call save(force=True) if intentional)."
                )

        tmp = self._jsonl_path.with_suffix(".jsonl.tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            for _, data in self.g.nodes(data=True):
                node = data.get("node")
                if node is None:
                    continue
                fh.write(json.dumps({"kind": "node", **node.model_dump(mode="json")}) + "\n")
            for u, v, key, data in self.g.edges(keys=True, data=True):
                edge = data.get("edge")
                if edge is None:
                    continue
                fh.write(json.dumps({"kind": "edge", **edge.model_dump(mode="json")}) + "\n")
        os.replace(tmp, self._jsonl_path)  # atomic: a crash can't leave a half-written KB
        # touch the alias db so a fresh load() always has a table to read
        self._ensure_alias_db()

    def load(self) -> None:
        """Replace in-memory graph with the contents of ``graph.jsonl``.

        Sets ``self._load_failed`` if the file exists but cannot be read; :meth:`save`
        uses that flag to refuse clobbering a real on-disk KB with a failed load.
        """
        self._load_failed = False
        self.g = nx.MultiDiGraph()
        if not self._jsonl_path.exists():
            return
        nodes: list[Node] = []
        edges: list[Edge] = []
        try:
            # errors="replace" so an invalid byte can't raise mid-iteration.
            with self._jsonl_path.open("r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    kind = rec.pop("kind", None)
                    try:
                        if kind == "node":
                            nodes.append(Node.model_validate(rec))
                        elif kind == "edge":
                            edges.append(Edge.model_validate(rec))
                    except Exception:
                        # tolerate a corrupt/legacy line rather than failing the whole load
                        continue
        except Exception:
            # hard read failure (permissions, unreadable file) — flag, don't pretend empty.
            self._load_failed = True
            return
        self.upsert_nodes(nodes)
        self.upsert_edges(edges)

    # ---- alias table (id -> canonical_id) ------------------------------- #

    def set_alias(self, alias_id: str, canonical_id: str) -> None:
        """Record that ``alias_id`` was merged into ``canonical_id`` (resolve.py owns this)."""
        if not alias_id or not canonical_id or alias_id == canonical_id:
            return
        conn = self._ensure_alias_db()
        with conn:
            conn.execute(
                "INSERT INTO aliases(id, canonical) VALUES(?, ?) "
                "ON CONFLICT(id) DO UPDATE SET canonical=excluded.canonical",
                (alias_id, canonical_id),
            )

    def resolve_alias(self, node_id: str, _depth: int = 0) -> str:
        """Follow the alias chain to the canonical id (cycle-safe, bounded depth)."""
        if not node_id or _depth > 16:
            return node_id
        conn = self._ensure_alias_db()
        row = conn.execute(
            "SELECT canonical FROM aliases WHERE id = ?", (node_id,)
        ).fetchone()
        if row is None or row[0] == node_id:
            return node_id
        return self.resolve_alias(row[0], _depth + 1)

    # ---- internals ------------------------------------------------------ #

    def _node_obj(self, node_id: str) -> Optional[Node]:
        if node_id in self.g:
            return self.g.nodes[node_id].get("node")
        return None

    def _ensure_node(self, node_id: str) -> None:
        """Create a minimal placeholder node if the id is unknown."""
        if node_id in self.g and self.g.nodes[node_id].get("node") is not None:
            return
        ntype = self._infer_type(node_id)
        name = node_id.split(":", 1)[1] if ":" in node_id else node_id
        placeholder = Node(id=node_id, type=ntype, name=name or node_id)
        self.g.add_node(node_id, node=placeholder)

    @staticmethod
    def _infer_type(node_id: str) -> NodeType:
        """Recover a node's type from the ``type:slug`` id convention; default to Concept."""
        prefix = node_id.split(":", 1)[0].lower() if ":" in node_id else ""
        mapping = {
            "technology": "Technology", "method": "Method", "concept": "Concept",
            "idea": "Idea", "person": "Person", "organization": "Organization",
            "source": "Source", "grant": "Grant", "assessment": "Assessment",
            "thesis": "Thesis",
        }
        return mapping.get(prefix, "Concept")  # type: ignore[return-value]

    @staticmethod
    def _merge_node(existing: Node, incoming: Node) -> Node:
        """Fold incoming aliases/provenance/props into the existing spine node."""
        aliases = list(dict.fromkeys([*existing.aliases, *incoming.aliases, incoming.name]))
        # don't list the canonical name as its own alias
        aliases = [a for a in aliases if a and a != existing.name]
        prov = list(existing.provenance)
        seen = {(c.source_slug, c.char_span, c.quote) for c in prov}
        for c in incoming.provenance:
            sig = (c.source_slug, c.char_span, c.quote)
            if sig not in seen:
                prov.append(c)
                seen.add(sig)
        props = {**existing.props, **incoming.props}
        return existing.model_copy(
            update={"aliases": aliases, "provenance": prov, "props": props}
        )

    @staticmethod
    def _merge_edge(existing: Edge, incoming: Edge) -> Edge:
        """Keep the stronger edge; prefer one that carries a citation."""
        keep = existing
        if incoming.confidence > existing.confidence:
            keep = incoming
        citation = keep.citation or existing.citation or incoming.citation
        return keep.model_copy(
            update={
                "citation": citation,
                "confidence": max(existing.confidence, incoming.confidence),
            }
        )

    def _degree(self, node_id: str) -> int:
        """Undirected degree (number of incident edges, counting parallels)."""
        try:
            return self.g.degree(node_id)  # MultiDiGraph degree counts in+out incl. parallels
        except Exception:
            return 0

    def _path_hub_cost(self, node_path: list[str]) -> float:
        """Penalty proportional to how hubby the *intermediate* nodes are."""
        threshold = self.settings.hub_degree_threshold
        cost = 0.0
        for nid in node_path[1:-1]:  # endpoints are the query, never penalised
            deg = self._degree(nid)
            if deg > threshold:
                cost += float(deg - threshold)
        return cost

    def _edges_for_node_path(self, node_path: list[str]) -> Optional[list[Edge]]:
        """Map a node sequence back to the best concrete Edge per adjacent pair.

        For each ``(a, b)`` we look for an edge in either direction (the path was
        found undirected); among parallels we pick the highest-confidence one.
        Returns ``None`` if any link cannot be realised (should not happen for a
        path that came out of the graph, but we stay defensive).
        """
        edges: list[Edge] = []
        for a, b in zip(node_path, node_path[1:]):
            best = self._best_edge_between(a, b)
            if best is None:
                return None
            edges.append(best)
        return edges

    def _best_edge_between(self, a: str, b: str) -> Optional[Edge]:
        candidates: list[Edge] = []
        if self.g.has_edge(a, b):
            for data in self.g[a][b].values():
                if data.get("edge") is not None:
                    candidates.append(data["edge"])
        if self.g.has_edge(b, a):
            for data in self.g[b][a].values():
                if data.get("edge") is not None:
                    candidates.append(data["edge"])
        if not candidates:
            return None
        return max(candidates, key=lambda e: e.confidence)

    # ---- sqlite helpers ------------------------------------------------- #

    _alias_conn: Optional[sqlite3.Connection] = None

    def _ensure_alias_db(self) -> sqlite3.Connection:
        if self._alias_conn is not None:
            return self._alias_conn
        self._graph_dir.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._alias_path))
        conn.execute(
            "CREATE TABLE IF NOT EXISTS aliases ("
            "  id TEXT PRIMARY KEY,"
            "  canonical TEXT NOT NULL"
            ")"
        )
        conn.commit()
        self._alias_conn = conn
        return conn

    def close(self) -> None:
        if self._alias_conn is not None:
            self._alias_conn.close()
            self._alias_conn = None

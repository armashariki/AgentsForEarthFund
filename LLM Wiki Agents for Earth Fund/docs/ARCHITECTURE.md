# Architecture

How **LLM Wiki Agents for Earth Fund** is built — the system structure, the data‑flow pipeline, and the
source‑code components. All diagrams render natively on GitHub.

---

## 1. The big picture

The system has two halves that share one markdown knowledge base:

- **`befkb` — the comprehension‑and‑connection engine.** A local‑first Python package that turns documents
  into a connected knowledge graph and answers *"how does this connect to my grants?"*.
- **The LLM Wiki.** An AI‑maintained markdown knowledge base (Karpathy's *LLM Wiki* pattern). The engine
  writes into it; an agent (Claude Code, governed by [`../CLAUDE.md`](../CLAUDE.md)) also curates it.

```mermaid
flowchart TB
  subgraph IN["① Sources (immutable)"]
    RAW["raw/ — PDFs, blogs,<br/>slides, notes, grants"]
  end

  subgraph ENGINE["② befkb engine — local, runs on Ollama, no server"]
    direction LR
    PARSE["parse<br/>(PyMuPDF)"] --> CLAIMS["claims +<br/>fact-check"]
    CLAIMS --> EXTRACT["extract<br/>entities + relations<br/>(incl. Idea nodes + stance)"]
    EXTRACT --> RESOLVE["entity<br/>resolution"]
    RESOLVE --> STORES
  end

  subgraph STORES["③ Stores (embedded, on-disk, no DB server)"]
    direction LR
    GRAPH[("knowledge graph<br/>NetworkX → graph.jsonl")]
    VEC[("vectors + BM25<br/>LanceDB")]
  end

  subgraph OUT["④ Answers"]
    APPLY["apply — the killer query:<br/>how does this connect<br/>to my grants?"]
    WIKI["wiki/ — markdown<br/>(Obsidian, git)"]
  end

  RAW --> PARSE
  STORES --> APPLY
  STORES --> WIKI
  APPLY --> WIKI
```

**Design stance:** the knowledge graph is the *spine*; the markdown wiki is a human‑readable *view*. This
closes the gap that no off‑the‑shelf GraphRAG system fills — exporting a knowledge graph back to a wiki.

---

## 2. Ingest pipeline (`befkb ingest`)

What happens to a single document, step by step:

```mermaid
flowchart LR
  A["PDF / text"] --> B["parse → Doc<br/>(sections, char-spans)"]
  B --> C["extract_claims<br/>+ flag shaky ones"]
  B --> D["extract_graph<br/>entities + relations"]
  D --> E["resolve<br/>(dedupe vs. graph)"]
  E --> F["upsert nodes + edges<br/>→ knowledge graph"]
  B --> G["chunk + embed<br/>→ LanceDB + BM25"]
  C --> H["review queue<br/>(data/review/)"]
  F --> I["save graph<br/>(atomic)"]
  G --> I
```

Every node and edge carries a **citation** back to the source text — so any answer is *cited by
construction*.

---

## 3. The killer query (`befkb apply`)

*"Given this new document, how does it connect to my grants?"* — discovered **structurally** in the graph;
the language model only *narrates* a path it cannot invent.

```mermaid
flowchart TD
  N["new document"] --> EX["extract entities + ideas<br/>(NOT committed to the graph)"]
  EX --> AN["anchor onto existing<br/>canonical nodes (read-only)"]
  AN --> SEED["seed targets =<br/>all Grant nodes"]
  SEED --> WALK["walk UNDIRECTED,<br/>hub-penalised paths<br/>anchor → grant"]
  WALK --> CLASS["classify each connection:<br/>shared-idea · capability-transfer · TRADEOFF"]
  CLASS --> STANCE["apply the new doc's STANCE:<br/>challenges → tradeoff,<br/>not false 'alignment'"]
  STANCE --> EVID["attach per-hop evidence<br/>(citations)"]
  EVID --> NARR["one LLM call narrates<br/>the given paths"]
  NARR --> OUT["ApplicabilityResult<br/>+ filed to wiki/analyses/"]
```

Two design choices make this work where naive approaches fail:
1. **Undirected traversal** — the gold connection `paper —applies-idea→ idea ←applies-idea— grant` has *no*
   directed path; directed shortest‑path returns nothing.
2. **Stance‑aware** — a critique that `challenges` a shared idea is a **tension**, not an overlap. The new
   doc's own edges drive the valence so a critique is never narrated as agreement.

---

## 4. Source‑code components

Each module is a swappable seam (interface), so parts can be upgraded without a rewrite.

```mermaid
flowchart TD
  CLI["cli.py / api.py<br/>(Typer + FastAPI)"] --> PIPE["pipeline.py<br/>(orchestration)"]
  PIPE --> PARSER["ingest/ (parser)"]
  PIPE --> CHUNK["chunk.py<br/>(LanceDB + BM25)"]
  PIPE --> CLAIMS["claims.py<br/>★ custom layer 1"]
  PIPE --> EXTRACT["extract.py"]
  PIPE --> RESOLVE["resolve.py"]
  PIPE --> APPLIC["applicability.py<br/>★ custom layer 2"]
  EXTRACT --> GRAPH["graphstore.py<br/>(NetworkX; swap-seam)"]
  RESOLVE --> GRAPH
  APPLIC --> GRAPH
  APPLIC --> RETR["retrieve.py<br/>(hybrid RRF)"]
  RETR --> CHUNK
  RESOLVE --> LLM["llm.py (Ollama / cloud)"]
  EXTRACT --> LLM
  CLAIMS --> LLM
  APPLIC --> LLM
  subgraph CONTRACT["the shared contract"]
    MODELS["models.py — Pydantic shapes"]
    CONFIG["config.py — Settings"]
  end
  PIPE -.-> MODELS
  GRAPH -.-> MODELS
```

★ = the two layers no open‑source system provides off the shelf, so they are **owned here**:
**claim fact‑checking** and the **applicability/connection query**.

| Module | Responsibility |
|---|---|
| `models.py` | The data contract — every shape (Node, Edge, Claim, Connection…), 1:1 with the wiki ontology. |
| `config.py` | One `Settings` object (paths, model names, thresholds). |
| `llm.py` | Provider‑agnostic LLM + embeddings — **Ollama default**, cloud opt‑in via one env var. |
| `ingest/` | `Parser` protocol + PyMuPDF / text parsers (Docling is a future drop‑in). |
| `chunk.py` | Chunking + embedded **LanceDB** vectors + **BM25** lexical index. |
| `extract.py` | Schema‑constrained entity/relation extraction — emits abstract **Idea** nodes + **stance**. |
| `resolve.py` | Entity resolution (dedupe) with a confidence gate; read‑only `anchor()` for the query. |
| `graphstore.py` | The knowledge‑graph spine (NetworkX) behind a `GraphStore` interface — **the swap‑seam** to Graphiti/Neo4j later. |
| `retrieve.py` | Hybrid retrieval (vector ∪ BM25, fused with Reciprocal Rank Fusion). |
| `claims.py` | **★** Claim extraction + shaky‑flagging — *assists* a human, never asserts truth. |
| `applicability.py` | **★** The killer query — anchor → multi‑hop traversal → cited narration. |
| `pipeline.py` | Orchestrates ingest / apply; writes to the wiki + a log. |
| `cli.py` / `api.py` | Typer CLI + a thin FastAPI (the seam where auth/permissions attach later). |

---

## 5. Technology choices (and why)

| Layer | Choice | Why |
|---|---|---|
| LLM + embeddings | **Ollama** (`qwen2.5:7b‑instruct`, `nomic‑embed‑text`) | Local‑first, free, offline, no key. Cloud is a config flip for higher quality. |
| Knowledge graph | **NetworkX** → `graph.jsonl` | Embedded, zero‑server, diffable, free multi‑hop traversal. Swappable to Graphiti/Neo4j at scale. |
| Vectors + lexical | **LanceDB** (embedded) + **rank‑bm25** | No server; hybrid retrieval via RRF. Swappable to Qdrant. |
| Parsing | **PyMuPDF** | Near‑pure, fast, no heavy deps. Docling is a later adapter for slides/scans. |
| Packaging / API | **uv** · **Typer** · **FastAPI** | One command to run; CLI now, API for colleagues later. |

This **lean, zero‑server design won a multi‑agent architecture review** against heavier alternatives
(R2R‑in‑Docker, a Graphiti+Neo4j assembly) — chosen because the operator is a solo builder on a Mac with
no Docker, and the killer query is fundamentally a graph‑traversal problem.

---

## 6. Roadmap (deliberately deferred)

The `GraphStore`, `Parser`, `LLMClient`, and `Retriever` interfaces exist so the following are **backend
swaps, not rewrites**:

| Phase | Adds | Swap |
|---|---|---|
| 1.5 | Harden claim‑contradiction detection; ingest the real grant portfolio | — |
| 2 | Richer parsing for slides/scans/tables | `Parser` → **Docling** |
| 3 | Scale to 1k–10k docs (temporal KG, robust entity resolution) | `GraphStore` → **Graphiti/Neo4j**; LanceDB → **Qdrant** |
| 4 | Colleagues + permissions (SSO, audit, document‑level ACLs) | API seam → **Onyx**‑style backbone + permission‑tiered synthesis |

The reasoning behind each is in [`../wiki/analyses/`](../wiki/analyses/) (the build‑vs‑buy and "middle‑framework" research that drove these decisions). Open bugs/limitations: [`../befkb/KNOWN_ISSUES.md`](../befkb/KNOWN_ISSUES.md).

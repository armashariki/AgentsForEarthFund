# befkb — comprehension-and-connection engine (v0.1)

A local-first knowledge engine for the Bezos Earth Fund. It ingests any document, **comprehends**
it (extracting entities + relations + fact-checked claims), connects everything into a knowledge
graph, and answers the question that matters:

> **"Given this new piece of content, how does it connect to my grants and current work?"**

It is **not** a scoring/judgment tool. It builds a connected, cited picture of who/what/which-ideas
relate across your documents — and surfaces tensions (a critique that *challenges* a grant), not just
overlaps. Runs entirely on your machine: **no Docker, no servers, no cloud key required.**

## What it does (the pipeline)
`ingest` → parse (PyMuPDF) → extract atomic **claims** + flag the shaky ones → extract **entities**
(Technology / Method / Concept / **Idea** / Person / Organization) + **relations** → **entity
resolution** (dedupe "GPT-4"/"GPT 4") → persist to a **NetworkX** knowledge graph + **LanceDB**
vectors / BM25. `apply` → anchor a new doc's entities onto the graph (read-only) → walk **undirected,
hub-penalised** multi-hop paths to your `Grant` nodes → narrate the connection with the correct
*valence* (tension vs. overlap), cited, and file it back as a wiki page.

## Prerequisites
- **[uv](https://docs.astral.sh/uv/)** (Python package manager) — already used here.
- **[Ollama](https://ollama.com)** running locally, with two models pulled:
  ```bash
  ollama pull qwen2.5:7b-instruct   # extraction + claims + narration
  ollama pull nomic-embed-text      # embeddings (768-d)
  ```
- A cloud key is **optional** — set `ANTHROPIC_API_KEY` (or `OPENAI_API_KEY`) to route *extraction/claims*
  to a stronger model for higher quality; retrieval + the graph stay local.

## Install & run
```bash
cd "LLM Wiki/befkb"
uv sync                                   # install deps into a local venv

# ingest documents from ../raw (or anywhere)
uv run befkb ingest ../raw/some-paper.pdf

# ask how a new document connects to your grants
uv run befkb apply ../raw/anthropic-agents-in-biology.pdf

# run the HTTP API (POST /ingest, POST /apply)
uv run befkb serve
```
*(You can also call it as a library: `from befkb.pipeline import ingest, apply`.)*

## Layout
```
befkb/
├── src/befkb/
│   ├── models.py        # the data contract (nodes, edges, claims, ...)
│   ├── config.py        # Settings (paths, model names, thresholds)
│   ├── llm.py           # Ollama (default) / cloud LLM + embeddings
│   ├── ingest/          # PyMuPDF + text parsers (Parser protocol; Docling later)
│   ├── chunk.py         # chunking + LanceDB vectors + BM25
│   ├── extract.py       # entity/relation extraction (incl. Idea nodes + stance)
│   ├── resolve.py       # entity resolution / dedupe
│   ├── graphstore.py    # NetworkX knowledge graph (swappable: Graphiti/Neo4j later)
│   ├── retrieve.py      # hybrid (vector + BM25, RRF) retrieval
│   ├── claims.py        # claim extraction + shaky-flagging (assist, never assert)
│   ├── applicability.py # the killer query: "how does this apply to my grants?"
│   ├── pipeline.py      # orchestration (ingest / apply)
│   ├── cli.py / api.py  # Typer CLI + FastAPI
├── data/                # engine-owned, gitignored (graph.jsonl, lancedb/, review/)
├── tests/               # 94 tests
├── KNOWN_ISSUES.md      # the v0.2 hardening backlog (from the adversarial review)
└── README.md
```
The design rationale lives in `../wiki/_schema/bef-ai-knowledge-model.md`; the engine writes its
human-facing output into the `../wiki/` markdown knowledge base.

## Status
**v0.1 — works end-to-end on real documents, locally.** Demonstrated: ingesting a method paper
(Alejo, RL for conservation) and a critique (Stein, relational accountability), then correctly
surfacing that the critique **challenges** a grant's "top-down optimization" approach — a cited,
idea-level connection. The 6 data-integrity bugs from review are fixed; remaining hardening (perf,
parser edge cases) is tracked in `KNOWN_ISSUES.md`. Real grant data, Docling ingestion, Graphiti/Neo4j
scaling, and multi-user/permissions are the deliberate Phase-2+ roadmap.

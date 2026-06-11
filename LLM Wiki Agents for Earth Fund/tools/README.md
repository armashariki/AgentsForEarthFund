# tools/ — optional local tooling

Small tools that help the agent operate on the wiki efficiently. At small scale you don't need
any of this — reading `wiki/index.md` is enough. Add tools as the wiki grows.

## Search (the first tool you'll want)

When `index.md` gets too big to read wholesale, add real search over `wiki/`:

- **qmd** — `https://github.com/tobi/qmd` — local hybrid (BM25 + vector) search over markdown
  with LLM re-ranking, fully on-device. Has a **CLI** (the agent can shell out to it) and an
  **MCP server** (the agent uses it as a native tool). Recommended starting point.
- Or vibe-code a naive search script here and have the agent shell out to it.

Once a search tool exists, update `CLAUDE.md` → "Search" so future sessions prefer it over
reading the whole index.

## Later (enterprise scale)

Heavier components — a hierarchical indexer, an entity-resolution/knowledge-graph builder, a
permission-aware retrieval backend — will be decided by the build-vs-buy research and, if built,
will live here or in a sibling service. See `README.md` → Scaling and the research write-up at
`wiki/analyses/enterprise-scaling-research.md` (once produced).

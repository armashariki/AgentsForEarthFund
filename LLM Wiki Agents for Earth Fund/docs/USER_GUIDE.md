# User Guide

How to install and use the **befkb** engine and the markdown wiki. Written for someone who has never
run a Python project — copy/paste the commands.

---

## 1. What you need (one-time setup)

You need two free tools and two small AI models that run **on your own machine** (nothing is sent to the
cloud).

1. **uv** — a Python installer/runner. Install it:
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```
2. **Ollama** — runs the local AI models. Download from <https://ollama.com>, install, and open it once so
   it's running in the background.
3. **The two models** (a one-time download, ~5 GB total):
   ```bash
   ollama pull qwen2.5:7b-instruct      # reads documents, extracts, narrates
   ollama pull nomic-embed-text         # turns text into searchable vectors
   ```

That's it. No Docker, no database server, no API key.

> **Optional — higher quality:** if you have an Anthropic or OpenAI key, set it before running and the
> engine will use it for the *reading/extraction* step only (everything else stays local):
> ```bash
> export ANTHROPIC_API_KEY=sk-...     # or OPENAI_API_KEY=...
> ```

## 2. Install the engine

```bash
cd "LLM Wiki Agents for Earth Fund/befkb"
uv sync          # creates a private environment and installs everything (~1 min)
```

Check it works:
```bash
uv run befkb --help
```

## 3. The core workflow

### a) Ingest documents — build the knowledge base
Point it at any PDF (papers, reports, grant documents):
```bash
uv run befkb ingest /path/to/document.pdf
```
What happens: the engine reads the document, pulls out the **technologies, methods, concepts, ideas,
people, and organizations** it mentions, extracts and **fact‑checks its key claims**, and weaves it all
into a knowledge graph. Run it on as many documents as you like — the knowledge **accumulates**.

You'll see a report like:
```
source_slug: ...   nodes_created: 119  nodes_merged: 80  edges: 141
claims_total: 122  flagged_claims: 13  chunks: 109
```

### b) Ask "how does this apply to my grants?"
Point it at a *new* document:
```bash
uv run befkb apply /path/to/new-paper.pdf
```
The engine connects the new document to your existing knowledge — especially to your **grants** — through
shared technologies and ideas, and explains the connection (including when a paper **challenges** a grant's
approach), with citations. The answer is also written into `wiki/analyses/` as a durable page.

### c) Search the knowledge base
```bash
uv run befkb query "geospatial foundation models"
```

### d) Run it as an API (for colleagues / other apps)
```bash
uv run befkb serve     # then POST to /ingest and /apply on http://localhost:8000
```

## 4. Seeding a "grant" (until real grants are wired in)

The killer query connects new content to **`Grant`** nodes. Today you add one by hand (real grant import is
on the roadmap). The simplest path is a tiny Python snippet — see
[USE_CASES.md → "How a critique applies to a grant"](USE_CASES.md) for a copy‑paste example.

## 5. The markdown wiki side

Everything the engine produces lives as plain markdown under [`../wiki/`](../wiki/). To browse it nicely:

1. Install **[Obsidian](https://obsidian.md)** (free).
2. *Open folder as vault* → choose the `LLM Wiki Agents for Earth Fund` folder.
3. You can now follow `[[links]]`, see the **graph view**, and read the engine's filed analyses.

The wiki is *also* maintained directly by an AI agent (Claude Code) following the rules in
[`../CLAUDE.md`](../CLAUDE.md) — that's the "LLM Wiki" half of the project, separate from the `befkb` engine.

## 6. Troubleshooting

| Symptom | Fix |
|---|---|
| `connection refused` / no output | Ollama isn't running — open the Ollama app. |
| `model 'qwen2.5:7b-instruct' not found` | Run the `ollama pull` commands in step 1. |
| Extraction quality feels thin | The local 7B model is the default; add a cloud key (step 1, optional) for the extraction pass. |
| `befkb: command not found` | Use `uv run befkb ...` (not bare `befkb`), from inside the `befkb/` folder. |
| Want a clean slate | Delete `befkb/data/` and re‑ingest. |

## 7. Running the tests
```bash
cd befkb && uv run pytest -q      # 94 tests
```

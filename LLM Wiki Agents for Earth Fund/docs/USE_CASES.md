# Use Cases

Worked examples of what the system does, with real commands and real output.

---

## 1. "How does this new critique apply to a grant we fund?" (the flagship)

**Scenario.** You've ingested a method paper — *Maximizing Nature‑Based Solutions Using AI* (Alejo et al.,
2026), which uses reinforcement learning to prioritize conservation areas. A colleague forwards a new,
very different document — *AI for climate: from technological solutions to relational accountability*
(Stein, 2026), a **critique** arguing that AI‑for‑climate reproduces "top‑down optimization" and bypasses
Indigenous data sovereignty. **Is it relevant to anything we fund?**

**Step 1 — ingest both documents:**
```bash
uv run befkb ingest "raw/Earth s Future - 2026 - Alejo ... .pdf"
uv run befkb ingest "raw/s44168-026-00376-0.pdf"
```

**Step 2 — seed a grant** that resembles current work (real grant import is on the roadmap; for now,
one snippet):
```python
# seed_grant.py
from befkb.config import load_settings
from befkb.models import Node, Edge, Citation
from befkb.graphstore import NetworkXGraphStore

s = load_settings(); g = NetworkXGraphStore(s); g.load()
grant = Node(id="grant:rl-conservation", type="Grant",
             name="RL-based conservation prioritization (current grant)",
             props={"internal": True}, provenance=[Citation(source_slug="grant-seed")])
g.upsert_nodes([grant])
# link it to ideas/methods that exist in the graph
for rel, name in [("applies-idea", "optim"), ("uses-method", "reinforcement")]:
    n = next((x for t in ("Idea","Method") for x in g.nodes_by_type(t) if name in x.name.lower()), None)
    if n: g.upsert_edges([Edge(src=grant.id, rel=rel, dst=n.id, confidence=0.9,
                               citation=Citation(source_slug="grant-seed"))])
g.save(); print("seeded grant")
```
```bash
cd befkb && uv run python ../seed_grant.py
```

**Step 3 — ask the question:**
```bash
uv run befkb apply "../raw/s44168-026-00376-0.pdf"
```

**Real output:**
```
SUMMARY: The new document challenges the grant's focus on technosolutionism and
optimization, suggesting a need to consider relational accountability in AI applications
for conservation.

[tradeoff] strength=0.92  ->  RL-based conservation prioritization (current grant)
  why: The new document challenges the grant's approach by questioning the reliance on
       technosolutionism and optimization, advocating for a more relational and accountable
       approach to AI in conservation efforts. This highlights a potential tradeoff in the
       grant's focus on technological solutions over broader ethical considerations.
  path: grant —applies-idea→ technosolutionism and optimization
```

**Why this matters.** The two documents share *no obvious keywords* — the connection runs through an
**abstract idea node** ("top‑down optimization"), and the engine correctly flags it as a **tension**
(`tradeoff`), not false agreement. That's a non‑obvious, cited, decision‑relevant insight a keyword search
would never surface. The answer is also filed to `wiki/analyses/` so it compounds.

---

## 2. Build institutional memory over time

Ingest everything you read — papers, blog posts, reports — and the knowledge graph grows. Entity
resolution keeps it clean (e.g. "GPT‑4" and "GPT 4" become one node), so a query months later traverses a
single, deduplicated picture instead of scattered notes.

```bash
for f in raw/*.pdf; do uv run befkb ingest "$f"; done
uv run befkb query "what have we seen about bioacoustics?"
```

---

## 3. Fact‑check what a document actually claims

On every ingest the engine decomposes the document into atomic **claims** and flags the shaky ones
(unsupported‑by‑source / vague) into a review queue under `befkb/data/review/`. This is *assistance for a
human reviewer*, never an automated verdict — it surfaces the caveats that should temper trust in a
flashy result.

```bash
uv run befkb ingest raw/some-bold-claims-paper.pdf
cat befkb/data/review/*.md          # the human-review checklist
```

---

## 4. The research/wiki side: a compounding analyst

Separate from the engine, the markdown wiki (maintained by an AI agent per [`../CLAUDE.md`](../CLAUDE.md))
holds durable, deep‑research analyses that were used to *design* this very system, for example:

- [`../wiki/analyses/enterprise-scaling-research.md`](../wiki/analyses/enterprise-scaling-research.md) — build‑vs‑buy for scaling to 1k–10k docs.
- [`../wiki/topics/ai-for-climate-and-nature-landscape.md`](../wiki/topics/ai-for-climate-and-nature-landscape.md) — a maturity‑tiered map of the AI‑for‑climate‑and‑nature frontier (what's deployed vs. hype).
- [`../wiki/_schema/bef-ai-knowledge-model.md`](../wiki/_schema/bef-ai-knowledge-model.md) — the evaluative knowledge model.

Open the folder in Obsidian and use the **graph view** to see how it all connects.

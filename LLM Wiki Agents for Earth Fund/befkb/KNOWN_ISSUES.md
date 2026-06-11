# befkb — Known Issues

From an adversarial code review (43 agents, 27 bugs confirmed + verified). The **6 data-integrity
bugs are fixed**; the remaining 21 are performance / edge-case quality and are safe to defer.
Each line: *module — issue — fix direction.*

## ✅ Fixed (data integrity — were silent data loss / corruption)
- **[CRITICAL] chunk.py** — `_split_section` dropped a span of body text (~15% of inputs lost real content). → advance from the actual window end, not `start+step`. *(regression test: 0/2000 fuzz cases lose content)*
- **[HIGH] chunk.py** — re-ingesting a changed doc orphaned its old chunks (stale content stayed searchable). → delete by `source_slug`, prune BM25 by slug prefix.
- **[HIGH] chunk.py** — un-embedded chunks were stored as zero vectors → silently invisible to vector search. → never fabricate zero vectors; keep un-embedded chunks lexical-only + warn; re-embed short batches.
- **[HIGH] applicability.py** — step-8 silently dropped the new doc's flagged claims (slug never matched). → surface the new doc's shaky claims (thread `doc.source_slug`).
- **[HIGH] applicability.py** — `dict.setdefault` eagerly embedded on every call, defeating the cache. → explicit membership check.
- **[HIGH] pipeline.py / graphstore.py** — a swallowed `graph.load()` failure then `save()`-truncated the whole KB to one doc. → atomic save (temp + `os.replace`) + refuse to clobber a non-empty KB after a failed/empty load; `load()` flags failure + tolerates bad bytes.

## ⏭️ Open — worth doing next (cheap, real impact)
- **retrieve.py** — `hybrid_search` candidate pool `== k`, so RRF can't surface a chunk just below each leg's cutoff (degraded recall, worst at small k). → over-fetch: `pool = max(k*5, 20)`, truncate after fusion.
- **graphstore.py / cli.py / api.py** — `--max-hops` is unbounded → `all_simple_paths` can blow up (super-exponential; abuse/DoS). → clamp max_hops to a ceiling + `itertools.islice` the path generator.
- **text_parser.py** — UTF-8 BOM not stripped → corrupts the title + loses the first heading. → read with `encoding="utf-8-sig"`.
- **text_parser.py / pymupdf_parser.py** — filename date parser clamps day to 28 (corrupts days 29-31) and fabricates dates from DOIs/accession IDs. → `calendar.monthrange` cap; anchor the regex / require separators; reject (don't clamp) invalid M/D. *(latent: nothing currently sorts by `doc_date`)*

## ⏭️ Open — performance (correct output, just slower at scale)
- **resolve.py** — `resolve()`/`anchor()` scan the whole graph 2×N per batch. → bucket by type once.
- **claims.py** — Check B re-embeds the claim once per neighbour. → embed once per claim; carry LanceDB distance through.
- **applicability.py** — grant-less fallback embeds every KB node serially (O(n) round-trips). → batch into one `embed([...])`.
- **chunk.py** — `bm25_search` re-tokenizes the whole corpus on every query. → cache per-chunk token sets in `_rebuild_bm25`.

## ⏭️ Open — low / latent (no live trigger today; defensive hardening)
- **graphstore.py** — `paths()` returns duplicate identical edge-paths when parallel edges exist (only `scored[0]` is used, so output is correct). → dedup node-paths.
- **resolve.py** — `_merge_into` lets a lower-confidence restatement clobber a canonical scalar prop (e.g. grant amount). → only add missing keys, or flag the conflict (don't silently overwrite).
- **pymupdf_parser.py** — author byline with a Roman-numeral initial (`C.`, `M.`, `I.`…) mis-detected as a section heading. → require a real numbered-heading pattern.
- **parser.py** — `register(ext, SomeClass)` (a class, not an instance) is returned un-instantiated. → `isinstance(p, Parser) and not isinstance(p, type)`.
- **retrieve.py** — `expand_to_subgraph` omits frontier-boundary edges + can duplicate alias-resolved nodes (no production caller today). → closing edge pass; canonicalize endpoint ids.
- **retrieve.py / applicability.py / claims.py** — `embed([x])[0]` trusts a 2-D return; a 1-D embedder would search on a scalar. → normalize to 2-D + guard.
- **claims.py** — Check-A evidence `char_span` (a ±200 window) doesn't bound its own `quote`. → set the quote's true span or `None`.
- **applicability.py** — the "always surface contradicts-KB" branch is dead (Check B is a stub that never sets that status). → drop it or comment as aspirational.
- **pipeline.py** — per-operation `EngineContext` leaks its alias-DB sqlite connection (matters on `befkb serve`). → add `close()`/context-manager + `try/finally`.

---
*Generated 2026-06-11 from the v0.1 adversarial review. The fixed set is the line between "demo" and "won't quietly corrupt your knowledge base." The open set is the v0.2 hardening backlog.*

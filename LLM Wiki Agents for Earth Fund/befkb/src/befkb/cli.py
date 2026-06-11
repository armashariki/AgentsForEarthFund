"""befkb command-line interface.

A thin Typer app over the pipeline. The heavy modules (``pipeline``, ``retrieve``,
``chunk``, ``graphstore``) are imported *lazily inside each command* so that
``import befkb.cli`` always succeeds — even while sibling modules are still being
built — and so a missing-deps error surfaces only for the command that needs it.

Commands
--------
- ``befkb ingest <path>``  : parse -> claims -> extract -> resolve -> graph -> index.
- ``befkb apply <path>``   : answer "how does this new content connect to my grants?".
- ``befkb query "<text>"`` : hybrid (vector + BM25) search over the indexed chunks.
- ``befkb serve``          : run the FastAPI app (POST /ingest, POST /apply).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

app = typer.Typer(
    name="befkb",
    help="Local-first knowledge-graph engine: ingest docs, ask how they connect to your grants.",
    add_completion=False,
    no_args_is_help=True,
)

# ANSI is handled by Typer/click's color support; we keep formatting plain-text so
# output stays readable when piped. These are tiny presentation helpers only.


def _rule(label: str = "") -> None:
    line = "─" * 60
    if label:
        typer.echo(typer.style(f"── {label} ".ljust(60, "─"), bold=True))
    else:
        typer.echo(line)


def _kv(key: str, value: object) -> None:
    typer.echo(f"  {typer.style(key + ':', bold=True)} {value}")


# --------------------------------------------------------------------------- #
# Pretty-printers (kept in the CLI so the result models stay presentation-free)
# --------------------------------------------------------------------------- #

def _print_ingest_report(report) -> None:
    """Pretty-print an :class:`befkb.models.IngestReport`."""
    _rule(f"ingested  {report.source_slug}")
    _kv("nodes created", report.nodes_created)
    _kv("nodes merged", report.nodes_merged)
    _kv("edges", report.edges)
    _kv("claims", f"{report.claims_total} total, {report.flagged_claims} flagged")
    _kv("chunks indexed", report.chunks)
    if report.pages_written:
        _kv("pages written", "")
        for p in report.pages_written:
            typer.echo(f"      - {p}")
    if report.flagged_claims:
        typer.echo(
            typer.style(
                f"\n  ⚠ {report.flagged_claims} claim(s) flagged for review — "
                "see the review queue.",
                fg=typer.colors.YELLOW,
            )
        )


def _print_applicability(result) -> None:
    """Pretty-print an :class:`befkb.models.ApplicabilityResult`."""
    _rule(f"how does  {result.new_doc}  connect?")
    if result.summary:
        typer.echo(result.summary.strip() + "\n")

    if not result.connections:
        typer.echo(typer.style("  No connections to existing grants found.", fg=typer.colors.YELLOW))
    else:
        typer.echo(typer.style(f"  Connections to grants ({len(result.connections)}):", bold=True))
        # strongest first
        for conn in sorted(result.connections, key=lambda c: c.strength, reverse=True):
            bar = _strength_bar(conn.strength)
            typer.echo(
                f"\n  • {typer.style(conn.grant_name, fg=typer.colors.GREEN, bold=True)}"
                f"  [{conn.kind}]  {bar} {conn.strength:.2f}"
            )
            if conn.why:
                typer.echo(f"      {conn.why.strip()}")
            if conn.shared_nodes:
                typer.echo(f"      shared: {', '.join(conn.shared_nodes)}")
            if conn.path:
                hops = "  →  ".join(_edge_str(e) for e in conn.path)
                typer.echo(f"      path: {hops}")
            for cite in conn.evidence[:2]:
                quote = (cite.quote or "").strip().replace("\n", " ")
                if quote:
                    if len(quote) > 160:
                        quote = quote[:157] + "…"
                    typer.echo(f"      “{quote}”  ({cite.source_slug})")

    if result.novel_to_kb:
        typer.echo(typer.style(f"\n  New to the knowledge base ({len(result.novel_to_kb)}):", bold=True))
        typer.echo("    " + ", ".join(result.novel_to_kb))

    if result.flagged_claims:
        typer.echo(
            typer.style(
                f"\n  ⚠ {len(result.flagged_claims)} shaky claim(s) flagged:",
                fg=typer.colors.YELLOW,
            )
        )
        for c in result.flagged_claims:
            txt = c.text.strip().replace("\n", " ")
            if len(txt) > 140:
                txt = txt[:137] + "…"
            typer.echo(f"    - [{c.status}] {txt}")


def _edge_str(edge) -> str:
    return f"{edge.src} -[{edge.rel}]→ {edge.dst}"


def _strength_bar(strength: float, width: int = 10) -> str:
    strength = max(0.0, min(1.0, float(strength)))
    filled = int(round(strength * width))
    return "█" * filled + "░" * (width - filled)


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #

@app.command()
def ingest(
    path: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True,
                                help="Path to a source document (PDF / md / txt / html)."),
) -> None:
    """Parse a source, extract its graph + claims, resolve entities, and index it."""
    from .config import load_settings
    from . import pipeline

    settings = load_settings()
    settings.ensure_dirs()
    report = pipeline.ingest(path, settings)
    _print_ingest_report(report)


@app.command()
def apply(
    path: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True,
                                help="Path to new content to evaluate against your grants."),
    max_hops: int = typer.Option(None, "--max-hops", help="Override graph traversal depth."),
    file_back: bool = typer.Option(
        False, "--file-back/--no-file-back",
        help="Write the answer back into the wiki as a markdown analysis page.",
    ),
) -> None:
    """Answer: how does this new content connect to my grants?"""
    from .config import load_settings
    from . import pipeline

    settings = load_settings()
    settings.ensure_dirs()
    hops = max_hops if max_hops is not None else settings.max_hops
    result = pipeline.apply(path, settings, max_hops=hops) if _accepts_max_hops(pipeline.apply) \
        else pipeline.apply(path, settings)
    _print_applicability(result)

    if file_back:
        try:
            from .applicability import file_back as _file_back
            out = _file_back(result, settings.wiki_dir)
            typer.echo(typer.style(f"\n  filed back → {out}", fg=typer.colors.CYAN))
        except Exception as exc:  # pragma: no cover - best-effort convenience
            typer.echo(typer.style(f"\n  file-back failed: {exc}", fg=typer.colors.RED))


@app.command()
def query(
    text: str = typer.Argument(..., help="Search query over the indexed chunks."),
    k: int = typer.Option(10, "--k", "-k", help="Number of results to return."),
) -> None:
    """Hybrid (vector + BM25) search over the indexed chunks."""
    from .config import load_settings
    from .chunk import LanceStore
    from .graphstore import NetworkXGraphStore
    from .llm import get_embedder
    from .retrieve import Retriever

    settings = load_settings()
    settings.ensure_dirs()

    embedder = get_embedder(settings)
    lance = LanceStore(settings)
    graph = NetworkXGraphStore(settings)
    # graph is optional for pure search, but load it so a Retriever that uses it works.
    try:
        graph.load()
    except Exception:
        pass

    retriever = Retriever(lance, embedder, graph)
    chunks = retriever.hybrid_search(text, k=k)

    _rule(f'query  "{text}"')
    if not chunks:
        typer.echo(typer.style("  No matching chunks. Have you ingested anything yet?", fg=typer.colors.YELLOW))
        raise typer.Exit(code=0)

    for i, ch in enumerate(chunks, 1):
        snippet = ch.text.strip().replace("\n", " ")
        if len(snippet) > 240:
            snippet = snippet[:237] + "…"
        header = f"  {i:>2}. {typer.style(ch.source_slug, bold=True)}"
        if ch.section:
            header += f"  · {ch.section}"
        typer.echo(header)
        typer.echo(f"      {snippet}")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="Bind host."),
    port: int = typer.Option(8000, help="Bind port."),
    reload: bool = typer.Option(False, "--reload", help="Auto-reload on code changes (dev)."),
) -> None:
    """Run the FastAPI server (POST /ingest, POST /apply)."""
    import uvicorn

    typer.echo(typer.style(f"befkb api → http://{host}:{port}  (docs at /docs)", bold=True))
    # Pass the import string so uvicorn can manage workers / reload cleanly.
    uvicorn.run("befkb.api:app", host=host, port=port, reload=reload)


# --------------------------------------------------------------------------- #
# small helper: tolerate either apply(path, settings) or apply(path, settings, max_hops=...)
# --------------------------------------------------------------------------- #

def _accepts_max_hops(fn) -> bool:
    import inspect
    try:
        return "max_hops" in inspect.signature(fn).parameters
    except (TypeError, ValueError):  # pragma: no cover
        return False


if __name__ == "__main__":  # pragma: no cover
    app()

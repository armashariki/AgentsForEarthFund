"""Smoke tests for the CLI + API surface.

These exercise structure only (help text, app wiring, pretty-printers, request
validation) — NOT the heavy pipeline, so they pass before sibling modules land
and stay fast/deterministic.
"""

from __future__ import annotations

import importlib

from typer.testing import CliRunner

from befkb import api, cli
from befkb.models import (
    ApplicabilityResult,
    Citation,
    Claim,
    Connection,
    Edge,
    IngestReport,
)

runner = CliRunner()


def test_cli_imports_without_sibling_modules() -> None:
    # Importing the CLI must never require pipeline/retrieve/etc. to exist.
    importlib.reload(cli)
    assert cli.app is not None


def test_help_lists_all_commands() -> None:
    result = runner.invoke(cli.app, ["--help"])
    assert result.exit_code == 0
    for cmd in ("ingest", "apply", "query", "serve"):
        assert cmd in result.output


def test_each_command_has_help() -> None:
    for cmd in ("ingest", "apply", "query", "serve"):
        result = runner.invoke(cli.app, [cmd, "--help"])
        assert result.exit_code == 0, f"{cmd} --help failed: {result.output}"


def test_print_ingest_report_runs(capsys) -> None:
    report = IngestReport(
        source_slug="some-paper",
        nodes_created=3,
        nodes_merged=1,
        edges=5,
        claims_total=7,
        flagged_claims=2,
        chunks=42,
        pages_written=["wiki/sources/2026-06-10-some-paper.md"],
    )
    cli._print_ingest_report(report)
    out = capsys.readouterr().out
    assert "some-paper" in out
    assert "42" in out  # chunks
    assert "flagged" in out


def test_print_applicability_runs(capsys) -> None:
    result = ApplicabilityResult(
        new_doc="new-method-paper",
        connections=[
            Connection(
                grant_id="grant:reef-monitoring",
                grant_name="Reef Monitoring",
                path=[Edge(src="source:x", rel="uses-method", dst="method:rl")],
                shared_nodes=["method:rl"],
                evidence=[Citation(source_slug="new-method-paper", quote="we use reinforcement learning")],
                why="Both rely on reinforcement learning for conservation planning.",
                kind="shared-idea",
                strength=0.81,
            )
        ],
        novel_to_kb=["CAPTAIN"],
        flagged_claims=[Claim(id="c1", text="This beats all prior work.", source_slug="new-method-paper", status="vague")],
        summary="One strong connection via reinforcement learning.",
    )
    cli._print_applicability(result)
    out = capsys.readouterr().out
    assert "Reef Monitoring" in out
    assert "CAPTAIN" in out
    assert "shared-idea" in out


def test_strength_bar_bounds() -> None:
    assert cli._strength_bar(0.0).count("█") == 0
    assert cli._strength_bar(1.0).count("░") == 0
    # clamps out-of-range input
    assert cli._strength_bar(5.0).count("░") == 0
    assert cli._strength_bar(-1.0).count("█") == 0


def test_api_imports_and_has_routes() -> None:
    paths = {r.path for r in api.app.routes}
    assert "/ingest" in paths
    assert "/apply" in paths
    assert "/health" in paths


def test_api_health() -> None:
    # Use FastAPI's TestClient if available; skip cleanly otherwise.
    try:
        from fastapi.testclient import TestClient
    except Exception:  # pragma: no cover
        return
    client = TestClient(api.app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_api_apply_rejects_path_outside_wiki_root() -> None:
    try:
        from fastapi.testclient import TestClient
    except Exception:  # pragma: no cover
        return
    client = TestClient(api.app)
    resp = client.post("/apply", json={"path": "/etc/passwd"})
    # 400 (outside root) or 404 (missing) — never a server error or success.
    assert resp.status_code in (400, 404)

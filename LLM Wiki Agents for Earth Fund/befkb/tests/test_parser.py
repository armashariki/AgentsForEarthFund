"""Tests for the parser dispatch layer (registry + get_parser).

These exercise the dispatch logic with fake parsers injected via ``register`` so
they stay independent of the concrete (heavier) sibling parsers. A separate test
confirms the built-in default mappings point at the right sibling parser classes
*lazily*, without importing ``fitz`` unless a ``.pdf`` is actually requested.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from befkb.ingest import get_parser as pkg_get_parser
from befkb.ingest.parser import Parser, get_parser, register
from befkb.models import Doc


class FakeParser:
    """Minimal Parser-protocol implementation that tags the Doc with its name."""

    def __init__(self, name: str):
        self.name = name

    def parse(self, path: Path) -> Doc:
        return Doc(source_slug="x", path=str(path), markdown="", meta={"by": self.name})


def test_package_reexports_get_parser():
    assert pkg_get_parser is get_parser


def test_register_instance_and_dispatch_by_extension():
    p = FakeParser("fake-foo")
    register("foo", p)
    got = get_parser(Path("/tmp/whatever.FOO"))  # case-insensitive
    assert got is p
    assert got.parse(Path("/tmp/a.foo")).meta["by"] == "fake-foo"


def test_register_factory_is_resolved_lazily():
    calls = {"n": 0}

    def factory() -> Parser:
        calls["n"] += 1
        return FakeParser("fake-bar")

    register("bar", factory)
    assert calls["n"] == 0  # not built until requested
    got = get_parser(Path("doc.bar"))
    assert calls["n"] == 1
    assert isinstance(got, FakeParser) and got.name == "fake-bar"


def test_register_normalises_leading_dot_and_case():
    p = FakeParser("dotted")
    register(".BAZ", p)
    assert get_parser(Path("x.baz")) is p


def test_prefer_overrides_extension():
    text_like = FakeParser("text-like")
    register("qux", text_like)
    # path says .pdf, but prefer forces the qux parser
    assert get_parser(Path("report.pdf"), prefer="qux") is text_like


def test_prefer_unknown_raises():
    with pytest.raises(ValueError):
        get_parser(Path("a.txt"), prefer="definitely-not-a-parser")


def test_unknown_extension_falls_back_to_text(monkeypatch):
    # The text fallback is a built-in factory; stub it so we don't need TextParser.
    import befkb.ingest.parser as mod

    sentinel = FakeParser("text-fallback")
    monkeypatch.setattr(mod, "_text_factory", lambda: sentinel)
    got = get_parser(Path("/tmp/mystery.unknownext"))
    assert got is sentinel


def test_extensionless_path_falls_back_to_text(monkeypatch):
    import befkb.ingest.parser as mod

    sentinel = FakeParser("text-fallback")
    monkeypatch.setattr(mod, "_text_factory", lambda: sentinel)
    assert get_parser(Path("/tmp/README")) is sentinel


def test_defaults_present_for_known_extensions():
    import befkb.ingest.parser as mod

    for ext in ("pdf", "md", "txt", "html"):
        assert ext in mod._REGISTRY, f"missing default registration for .{ext}"


def test_pdf_default_points_at_pymupdf_lazily(monkeypatch):
    # Resolving the .pdf provider should call our factory, which imports the
    # sibling module. We stub the import target so the test never needs `fitz`.
    import befkb.ingest.parser as mod

    sentinel = FakeParser("pymupdf-stub")
    monkeypatch.setattr(mod, "_pymupdf_factory", lambda: sentinel)
    # Re-point the registry entry to the patched factory for this test.
    monkeypatch.setitem(mod._REGISTRY, "pdf", mod._pymupdf_factory)
    assert get_parser(Path("paper.pdf")) is sentinel

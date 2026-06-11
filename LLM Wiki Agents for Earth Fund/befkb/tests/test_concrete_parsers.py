"""Tests for the concrete parsers (PyMuPDFParser + TextParser).

The dispatch/registry layer is covered by ``test_parser.py``; this file exercises
the actual text extraction and section segmentation, and the invariant that every
downstream provenance citation relies on:

    markdown[lo:hi] == section.text   for every section

The PDF test runs against the real Alejo / CAPTAIN paper if it is present in
``raw/``, otherwise it is skipped.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from befkb.ingest.pymupdf_parser import PyMuPDFParser
from befkb.ingest.text_parser import TextParser
from befkb.models import Doc, slugify

_RAW = Path(__file__).resolve().parents[2] / "raw"
_ALEJO = next(_RAW.glob("Earth*Alejo*Maximizing*.pdf"), None) if _RAW.exists() else None


def _assert_spans_roundtrip(doc: Doc) -> None:
    assert doc.markdown, "expected non-empty markdown"
    for sec in doc.sections:
        lo, hi = sec.char_span
        assert 0 <= lo <= hi <= len(doc.markdown)
        assert doc.markdown[lo:hi] == sec.text, f"span mismatch in section {sec.title!r}"
    starts = [s.char_span[0] for s in doc.sections]
    assert starts == sorted(starts), "sections must be ordered by start offset"


# --------------------------------------------------------------------------- #
# TextParser: markdown / plain text / HTML
# --------------------------------------------------------------------------- #

def test_markdown_headings_and_title(tmp_path: Path):
    p = tmp_path / "note.md"
    p.write_text(
        "# CAPTAIN\n\nIntro about reinforcement learning.\n\n"
        "## Methods\n\nWe optimize reserve placement.\n\n"
        "## Results\n\nBiodiversity goes up.\n",
        encoding="utf-8",
    )
    doc = TextParser().parse(p)
    assert doc.source_slug == slugify("note")
    assert doc.title == "CAPTAIN"
    titles = [s.title for s in doc.sections]
    assert {"CAPTAIN", "Methods", "Results"} <= set(titles)
    _assert_spans_roundtrip(doc)


def test_plain_text_single_body_section(tmp_path: Path):
    p = tmp_path / "plain.txt"
    p.write_text("Just a short note about bioacoustics monitoring.\n", encoding="utf-8")
    doc = TextParser().parse(p)
    assert len(doc.sections) == 1 and doc.sections[0].title == "body"
    _assert_spans_roundtrip(doc)


def test_html_is_stripped_and_titled(tmp_path: Path):
    p = tmp_path / "page.html"
    p.write_text(
        "<html><head><title>Relational Accountability</title>"
        "<style>.x{color:red}</style></head><body>"
        "<h1>Relational Accountability</h1><p>AI for climate as power.</p>"
        "<script>bad()</script><h2>Discussion</h2><p>Stewardship &amp; care.</p>"
        "</body></html>",
        encoding="utf-8",
    )
    doc = TextParser().parse(p)
    assert doc.title == "Relational Accountability"
    assert "bad()" not in doc.markdown and "color:red" not in doc.markdown
    assert "Stewardship & care" in doc.markdown  # HTML entity unescaped
    assert any(s.title == "Discussion" for s in doc.sections)
    _assert_spans_roundtrip(doc)


def test_setext_heading(tmp_path: Path):
    p = tmp_path / "setext.md"
    p.write_text("Overview\n========\n\nbody text here\n\nDetails\n-------\n\nmore\n", encoding="utf-8")
    doc = TextParser().parse(p)
    titles = {s.title for s in doc.sections}
    assert "Overview" in titles and "Details" in titles
    _assert_spans_roundtrip(doc)


def test_empty_text_doc(tmp_path: Path):
    p = tmp_path / "empty.txt"
    p.write_text("", encoding="utf-8")
    doc = TextParser().parse(p)
    assert doc.markdown == "" and doc.sections == []
    assert doc.title == "empty"  # falls back to filename stem


def test_filename_date_extraction(tmp_path: Path):
    p = tmp_path / "2026-03-15-report.md"
    p.write_text("# Report\n\nbody\n", encoding="utf-8")
    doc = TextParser().parse(p)
    assert doc.doc_date is not None and doc.doc_date.year == 2026 and doc.doc_date.month == 3


# --------------------------------------------------------------------------- #
# PyMuPDFParser: real Alejo / CAPTAIN paper
# --------------------------------------------------------------------------- #

@pytest.mark.skipif(_ALEJO is None, reason="Alejo PDF not present in raw/")
def test_real_pdf_parses_with_sections_and_spans():
    doc = PyMuPDFParser().parse(_ALEJO)
    assert doc.source_slug.startswith("earth")
    assert len(doc.markdown) > 5000
    assert len(doc.sections) >= 3
    assert doc.title
    _assert_spans_roundtrip(doc)
    low = doc.markdown.lower()
    assert "artificial intelligence" in low or "nature" in low

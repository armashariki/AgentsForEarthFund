"""PyMuPDF-backed PDF parser.

Opens a PDF with ``fitz`` (PyMuPDF), pulls text page by page, cleans it into
readable markdown, and segments the markdown into char-spanned
:class:`~befkb.models.Section` objects using lightweight heading heuristics.

Design choices:
- **char_span integrity is sacred.** All sections index into the *single* full
  markdown string, and ``markdown[lo:hi]`` round-trips to the section text. Every
  downstream provenance citation depends on this, so we build the markdown first
  and only ever take substrings of it.
- **Heading heuristics, not ML.** A line starts a new section when it looks like a
  heading: numbered (``2. Materials and Methods``, ``3.1 Results``), short
  ALL-CAPS (``ABSTRACT``, ``REFERENCES``), or a known academic section word. We
  stay conservative — false negatives just yield coarser sections, which is fine.
- **Page fallback.** If no headings are detected, we segment by page instead so a
  Doc always has structure to chunk and cite against.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

from ..models import Doc, Section, slugify

# --------------------------------------------------------------------------- #
# Heading heuristics
# --------------------------------------------------------------------------- #

# Numbered headings: "2 Methods", "2. Methods", "3.1. Results", "IV. Discussion".
_NUMBERED_HEADING = re.compile(
    r"^\s*((?:\d+|[IVXLCM]+)(?:\.\d+)*)[.)]?\s+(?P<title>\S.{0,80})$"
)

# Common academic / report section words (case-insensitive, whole-line-ish).
_KNOWN_SECTIONS = {
    "abstract", "introduction", "background", "related work", "related works",
    "materials and methods", "methods", "method", "methodology", "materials",
    "results", "results and discussion", "discussion", "conclusion", "conclusions",
    "acknowledgements", "acknowledgments", "references", "bibliography",
    "appendix", "supplementary material", "supplementary materials",
    "data availability", "data availability statement", "author contributions",
    "conflict of interest", "conflicts of interest", "funding", "summary",
    "keywords", "highlights", "limitations", "future work", "ethics statement",
}

# Lines longer than this are body text, never headings.
_MAX_HEADING_LEN = 90
# A short ALL-CAPS line (letters mostly uppercase) reads as a heading.
_MIN_CAPS_LETTERS = 3

# Journal "furniture" that superficially looks like a heading but is page noise:
# running page markers ("1 of 21"), running-header author refs ("ALEJO ET AL."),
# DOI/copyright lines. These are rejected before any heading rule fires.
_PAGE_MARKER = re.compile(r"^\s*\d+\s+of\s+\d+\s*$", re.IGNORECASE)
_RUNNING_HEADER = re.compile(r"\bet\s+al\.?\b", re.IGNORECASE)
_JOURNAL_NOISE = re.compile(
    r"(?i)\b(doi|https?://|©|copyright|all rights reserved|research article|"
    r"review article|wiley|elsevier|springer|creative commons)\b"
)


def _is_furniture(s: str) -> bool:
    """True if ``s`` is page furniture (footer/header/label), not a real heading."""
    if _PAGE_MARKER.match(s) or _RUNNING_HEADER.search(s) or _JOURNAL_NOISE.search(s):
        return True
    # Author-line fragments ending in a comma ("C. Alejo,") — never a section head.
    if s.endswith(",") or s.endswith(";"):
        return True
    return False


def _looks_like_heading(line: str) -> str | None:
    """Return the heading title if ``line`` reads like a heading, else ``None``."""
    s = line.strip()
    if not s or len(s) > _MAX_HEADING_LEN:
        return None
    if _is_furniture(s):
        return None
    # Sentences ending in a period are almost never headings (numbered ones ok).
    if s.endswith(".") and len(s.split()) > 8 and not _NUMBERED_HEADING.match(s):
        return None

    # 1) Numbered headings.
    m = _NUMBERED_HEADING.match(s)
    if m:
        title = m.group("title").strip()
        # Avoid catching list items / references like "1. Smith, J. (2020)..." and
        # prose like "2 of the cells" — require a title-cased / capitalised lead word.
        words = title.split()
        if (
            len(words) <= 10
            and not re.search(r"\(\d{4}\)|et al", title, re.IGNORECASE)
            and title[:1].isupper()
            and words[0].lower() not in ("of", "the", "and", "to", "in", "for", "with", "a", "an")
        ):
            return s.rstrip(".")

    # 2) Known section words (possibly with a leading number already handled above).
    low = re.sub(r"^\s*(?:\d+|[IVXLCM]+)[.)]?\s*", "", s).strip().lower().rstrip(".:")
    if low in _KNOWN_SECTIONS:
        return s.rstrip(".:")

    # 3) Short ALL-CAPS lines (e.g. "ABSTRACT", "DATA AVAILABILITY").
    letters = [c for c in s if c.isalpha()]
    if (
        letters
        and len(letters) >= _MIN_CAPS_LETTERS
        and sum(c.isupper() for c in letters) / len(letters) >= 0.85
        and len(s.split()) <= 8
        and not re.fullmatch(r"[A-Z0-9 .,()-]*\d{4}[A-Z0-9 .,()-]*", s)  # not a citation/year line
    ):
        return s

    return None


# --------------------------------------------------------------------------- #
# Text cleaning
# --------------------------------------------------------------------------- #

_HYPHEN_BREAK = re.compile(r"(\w)-\n(\w)")          # de-hyphenate across line breaks
_MULTISPACE = re.compile(r"[ \t]+")
_MANY_NEWLINES = re.compile(r"\n{3,}")


def _clean_page_text(text: str) -> str:
    """Light cleanup of one page's raw text into readable lines."""
    if not text:
        return ""
    # Normalise newlines and de-hyphenate words split across line wraps.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _HYPHEN_BREAK.sub(r"\1\2", text)
    lines = []
    for raw in text.split("\n"):
        line = _MULTISPACE.sub(" ", raw).strip()
        lines.append(line)
    out = "\n".join(lines)
    out = _MANY_NEWLINES.sub("\n\n", out)
    return out.strip()


# --------------------------------------------------------------------------- #
# Date extraction (best-effort)
# --------------------------------------------------------------------------- #

_FILENAME_DATE = re.compile(r"(20\d{2}|19\d{2})[-_]?(\d{2})?[-_]?(\d{2})?")


def _parse_meta_date(value: str | None) -> date | None:
    """Parse a PDF metadata date like ``D:20260115...`` or an ISO-ish string."""
    if not value:
        return None
    v = value.strip()
    if v.startswith("D:"):
        v = v[2:]
    m = re.match(r"(\d{4})(\d{2})(\d{2})", v)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y"):
        try:
            return datetime.strptime(v[: len(fmt) + 4], fmt).date()
        except ValueError:
            continue
    return None


def _date_from_filename(stem: str) -> date | None:
    m = _FILENAME_DATE.search(stem)
    if not m:
        return None
    y = int(m.group(1))
    mo = int(m.group(2)) if m.group(2) else 1
    d = int(m.group(3)) if m.group(3) else 1
    try:
        return date(y, min(max(mo, 1), 12), min(max(d, 1), 28))
    except ValueError:
        return date(y, 1, 1)


# --------------------------------------------------------------------------- #
# Section assembly
# --------------------------------------------------------------------------- #

def _segment_into_sections(markdown: str, page_breaks: list[int]) -> list[Section]:
    """Segment full ``markdown`` into char-spanned sections.

    Heading-driven when headings exist; otherwise page-driven (using the recorded
    page-break offsets). Spans index into ``markdown`` and round-trip exactly.
    """
    if not markdown.strip():
        return []

    lines = markdown.split("\n")
    # Precompute the char offset where each line begins in `markdown`.
    offsets: list[int] = []
    pos = 0
    for ln in lines:
        offsets.append(pos)
        pos += len(ln) + 1  # +1 for the '\n' join char

    # Find heading boundaries: (char_offset, title).
    boundaries: list[tuple[int, str]] = []
    for i, ln in enumerate(lines):
        title = _looks_like_heading(ln)
        if title is not None:
            boundaries.append((offsets[i], title))

    sections: list[Section] = []
    if boundaries:
        # Preamble before the first heading (title block / abstract lead-in).
        first_off = boundaries[0][0]
        if markdown[:first_off].strip():
            sections.append(_mk_section("Front matter", markdown, 0, first_off))
        for idx, (start, title) in enumerate(boundaries):
            end = boundaries[idx + 1][0] if idx + 1 < len(boundaries) else len(markdown)
            sec = _mk_section(title, markdown, start, end)
            if sec is not None:
                sections.append(sec)
    else:
        # No headings detected — fall back to page-based sections.
        bounds = [0, *[b for b in page_breaks if 0 < b < len(markdown)], len(markdown)]
        bounds = sorted(set(bounds))
        for pno, start in enumerate(bounds[:-1], start=1):
            end = bounds[pno]
            sec = _mk_section(f"Page {pno}", markdown, start, end)
            if sec is not None:
                sections.append(sec)
        if not sections:  # single short page with no breaks
            sections.append(_mk_section("body", markdown, 0, len(markdown)))

    return [s for s in sections if s is not None]


def _mk_section(title: str, markdown: str, start: int, end: int) -> Section | None:
    """Build a Section whose text is exactly ``markdown[start:end]`` (trimmed-aware).

    We keep the *span* aligned to the trimmed text so ``markdown[lo:hi] == text``
    holds for downstream provenance checks.
    """
    raw = markdown[start:end]
    stripped = raw.strip()
    if not stripped:
        return None
    lead = len(raw) - len(raw.lstrip())
    trail = len(raw) - len(raw.rstrip())
    lo = start + lead
    hi = end - trail
    return Section(title=title.strip() or "section", text=markdown[lo:hi], char_span=(lo, hi))


# --------------------------------------------------------------------------- #
# Parser
# --------------------------------------------------------------------------- #

class PyMuPDFParser:
    """Parse a PDF into a :class:`Doc` using PyMuPDF (``fitz``)."""

    def parse(self, path: Path) -> Doc:
        import fitz  # PyMuPDF; imported lazily so the module stays import-light

        path = Path(path)
        source_slug = slugify(path.stem)

        page_texts: list[str] = []
        meta: dict = {}
        doc_date: date | None = None
        with fitz.open(path) as pdf:
            meta = {k: v for k, v in (pdf.metadata or {}).items() if v}
            for page in pdf:
                page_texts.append(_clean_page_text(page.get_text("text")))
            meta["page_count"] = pdf.page_count

        # Assemble full markdown and record page-break char offsets as we go.
        parts: list[str] = []
        page_breaks: list[int] = []
        running = 0
        for text in page_texts:
            if not text:
                continue
            if parts:
                parts.append("\n\n")
                running += 2
            page_breaks.append(running)
            parts.append(text)
            running += len(text)
        markdown = "".join(parts)

        sections = _segment_into_sections(markdown, page_breaks)

        # Title: PDF metadata, else first non-empty line, else filename stem.
        title = (meta.get("title") or "").strip()
        if not title:
            for ln in markdown.split("\n"):
                if ln.strip():
                    title = ln.strip()
                    break
        if not title:
            title = path.stem

        # Date: metadata creation/mod date, then filename heuristic.
        doc_date = (
            _parse_meta_date(meta.get("creationDate"))
            or _parse_meta_date(meta.get("modDate"))
            or _date_from_filename(path.stem)
        )

        return Doc(
            source_slug=source_slug,
            path=str(path),
            title=title[:300],
            markdown=markdown,
            sections=sections,
            doc_date=doc_date,
            meta=meta,
        )

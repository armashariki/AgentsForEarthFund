"""Plain-text / markdown / HTML parser.

Handles ``.md``, ``.txt``, and ``.html``/``.htm``. HTML gets a *simple* tag strip
(no external dependency) — enough to recover readable prose from a saved web page;
it is not a full DOM parser. Markdown is passed through largely as-is (it already
is the target format) and segmented on ATX (``#``) and Setext headings. Plain text
is segmented on heading-ish lines, falling back to a single ``body`` section.

As with the PDF parser, section ``char_span`` offsets index into the single full
markdown string and round-trip exactly, so provenance stays exact.
"""

from __future__ import annotations

import html as _html
import re
from datetime import date
from pathlib import Path

from ..models import Doc, Section, slugify

# --------------------------------------------------------------------------- #
# HTML -> text (dependency-free, deliberately simple)
# --------------------------------------------------------------------------- #

_SCRIPT_STYLE = re.compile(r"(?is)<(script|style|head)[^>]*>.*?</\1>")
_BR = re.compile(r"(?i)<br\s*/?>")
_BLOCK_CLOSE = re.compile(
    r"(?i)</(p|div|section|article|li|ul|ol|h[1-6]|tr|table|blockquote)\s*>"
)
_HEADING_OPEN = re.compile(r"(?i)<h([1-6])[^>]*>")
_TAG = re.compile(r"(?s)<[^>]+>")
_TITLE_TAG = re.compile(r"(?is)<title[^>]*>(.*?)</title>")
_MULTISPACE = re.compile(r"[ \t]+")
_MANY_NEWLINES = re.compile(r"\n{3,}")


def _strip_html(text: str) -> tuple[str, str | None]:
    """Convert HTML to readable text. Returns ``(text, title_or_None)``."""
    title_m = _TITLE_TAG.search(text)
    title = _html.unescape(title_m.group(1)).strip() if title_m else None

    text = _SCRIPT_STYLE.sub("", text)
    # Mark headings as markdown so segmentation can pick them up.
    text = _HEADING_OPEN.sub(lambda m: "\n\n" + "#" * int(m.group(1)) + " ", text)
    text = re.sub(r"(?i)</h[1-6]\s*>", "\n", text)
    text = _BR.sub("\n", text)
    text = _BLOCK_CLOSE.sub("\n\n", text)
    text = _TAG.sub("", text)
    text = _html.unescape(text)
    # Tidy whitespace.
    lines = [_MULTISPACE.sub(" ", ln).strip() for ln in text.replace("\r", "\n").split("\n")]
    text = _MANY_NEWLINES.sub("\n\n", "\n".join(lines)).strip()
    return text, title


# --------------------------------------------------------------------------- #
# Heading detection for markdown / plain text
# --------------------------------------------------------------------------- #

_ATX = re.compile(r"^\s{0,3}(#{1,6})\s+(?P<title>.+?)\s*#*\s*$")
_NUMBERED = re.compile(r"^\s*((?:\d+)(?:\.\d+)*)[.)]?\s+(?P<title>\S.{0,80})$")
_MAX_HEADING_LEN = 90


def _heading_title(line: str, prev_blank: bool, next_line: str | None) -> str | None:
    """Return a heading title for ``line`` or ``None``."""
    s = line.rstrip()
    if not s.strip():
        return None
    # ATX markdown heading.
    m = _ATX.match(s)
    if m:
        return m.group("title").strip()
    # Setext heading: a line followed by a run of '=' or '-'.
    if next_line is not None and re.fullmatch(r"\s{0,3}(=+|-+)\s*", next_line) and len(s) <= _MAX_HEADING_LEN:
        return s.strip()
    # Numbered heading on its own short line, preceded by a blank line.
    if prev_blank:
        nm = _NUMBERED.match(s)
        if nm and len(nm.group("title").split()) <= 10 and not re.search(r"\(\d{4}\)|et al", nm.group("title")):
            return s.strip().rstrip(".")
        # Short ALL-CAPS standalone line.
        letters = [c for c in s if c.isalpha()]
        if (
            letters
            and len(letters) >= 3
            and sum(c.isupper() for c in letters) / len(letters) >= 0.85
            and len(s.split()) <= 8
        ):
            return s.strip()
    return None


def _segment(markdown: str) -> list[Section]:
    """Segment ``markdown`` into char-spanned sections on heading boundaries."""
    if not markdown.strip():
        return []
    lines = markdown.split("\n")
    offsets: list[int] = []
    pos = 0
    for ln in lines:
        offsets.append(pos)
        pos += len(ln) + 1

    boundaries: list[tuple[int, str]] = []
    for i, ln in enumerate(lines):
        prev_blank = (i == 0) or not lines[i - 1].strip()
        nxt = lines[i + 1] if i + 1 < len(lines) else None
        title = _heading_title(ln, prev_blank, nxt)
        if title is not None:
            boundaries.append((offsets[i], title))

    if not boundaries:
        return [_mk_section("body", markdown, 0, len(markdown))]

    sections: list[Section] = []
    first_off = boundaries[0][0]
    if markdown[:first_off].strip():
        sections.append(_mk_section("Front matter", markdown, 0, first_off))
    for idx, (start, title) in enumerate(boundaries):
        end = boundaries[idx + 1][0] if idx + 1 < len(boundaries) else len(markdown)
        sec = _mk_section(title, markdown, start, end)
        if sec is not None:
            sections.append(sec)
    return [s for s in sections if s is not None]


def _mk_section(title: str, markdown: str, start: int, end: int) -> Section | None:
    """Build a Section whose text equals ``markdown[lo:hi]`` after trimming."""
    raw = markdown[start:end]
    if not raw.strip():
        return None
    lead = len(raw) - len(raw.lstrip())
    trail = len(raw) - len(raw.rstrip())
    lo = start + lead
    hi = end - trail
    return Section(title=title.strip() or "section", text=markdown[lo:hi], char_span=(lo, hi))


# --------------------------------------------------------------------------- #
# Parser
# --------------------------------------------------------------------------- #

class TextParser:
    """Parse ``.md`` / ``.txt`` / ``.html`` into a :class:`Doc`."""

    def parse(self, path: Path) -> Doc:
        path = Path(path)
        raw = path.read_text(encoding="utf-8", errors="replace")
        ext = path.suffix.lower().lstrip(".")

        html_title: str | None = None
        if ext in ("html", "htm"):
            markdown, html_title = _strip_html(raw)
        else:
            # Normalise newlines; otherwise keep markdown/text verbatim.
            markdown = _MANY_NEWLINES.sub("\n\n", raw.replace("\r\n", "\n").replace("\r", "\n")).strip()

        sections = _segment(markdown)

        # Title: HTML <title>, else first heading/non-empty line, else filename.
        title = html_title or ""
        if not title:
            for ln in markdown.split("\n"):
                if ln.strip():
                    title = _ATX.match(ln).group("title").strip() if _ATX.match(ln) else ln.strip()
                    break
        if not title:
            title = path.stem

        return Doc(
            source_slug=slugify(path.stem),
            path=str(path),
            title=title[:300],
            markdown=markdown,
            sections=sections,
            doc_date=_date_from_filename(path.stem),
            meta={"ext": ext, "char_count": len(markdown)},
        )


_FILENAME_DATE = re.compile(r"(20\d{2}|19\d{2})[-_]?(\d{2})?[-_]?(\d{2})?")


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

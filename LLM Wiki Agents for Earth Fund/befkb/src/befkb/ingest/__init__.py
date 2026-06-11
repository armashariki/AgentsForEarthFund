"""befkb ingest package — parsers that turn raw sources into :class:`Doc`.

Dispatch lives in :mod:`befkb.ingest.parser`; concrete parsers live in
:mod:`befkb.ingest.pymupdf_parser` and :mod:`befkb.ingest.text_parser`.
"""

from __future__ import annotations

from .parser import Parser, get_parser, register

__all__ = ["Parser", "get_parser", "register"]

"""Parser protocol + a tiny extension-keyed registry.

A ``Parser`` turns a file on disk into a :class:`befkb.models.Doc` (clean markdown
+ char-spanned :class:`~befkb.models.Section` list). ``get_parser`` dispatches on
file extension; concrete parsers live in sibling modules and are wired in lazily so
that importing *this* module never drags in optional/heavy deps (e.g. ``fitz``)
until a file of that type is actually parsed.

Public surface (matches the cross-module contract):

- ``class Parser(Protocol)``        — ``parse(self, path) -> Doc``
- ``def get_parser(path, prefer=None) -> Parser``
- ``def register(ext, parser) -> None``
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Protocol, Union, runtime_checkable

from ..models import Doc

__all__ = ["Parser", "get_parser", "register"]


@runtime_checkable
class Parser(Protocol):
    """Anything that can turn a path into a :class:`Doc`."""

    def parse(self, path: Path) -> Doc: ...


# A registry value is either a ready Parser instance or a zero-arg factory that
# builds one on first use. The factory form keeps optional deps lazy: the PDF
# parser's ``fitz`` import only fires the first time a ``.pdf`` is parsed.
_ParserProvider = Union[Parser, Callable[[], Parser]]

# extension (lowercased, no leading dot) -> provider
_REGISTRY: dict[str, _ParserProvider] = {}


def _norm_ext(ext: str) -> str:
    """Normalise an extension to lowercase, no leading dot (e.g. ``"pdf"``)."""
    ext = ext.strip().lower().lstrip(".")
    if not ext:
        raise ValueError("extension must be non-empty")
    return ext


def register(ext: str, parser: _ParserProvider) -> None:
    """Register a parser (instance or zero-arg factory) for extension ``ext``.

    Examples::

        register("pdf", PyMuPDFParser())          # eager instance
        register("pdf", lambda: PyMuPDFParser())   # lazy factory

    Re-registering an extension overrides the previous provider.
    """
    _REGISTRY[_norm_ext(ext)] = parser


def _resolve(provider: _ParserProvider) -> Parser:
    """Materialise a registry value into a concrete Parser instance."""
    # A Parser instance already satisfies the protocol (has ``.parse``); a bare
    # factory is a plain callable we invoke to build one.
    if isinstance(provider, Parser):
        return provider
    if callable(provider):
        built = provider()
        if not isinstance(built, Parser):
            raise TypeError(
                f"parser factory returned {type(built)!r}, which is not a Parser"
            )
        return built
    raise TypeError(f"registry value {provider!r} is neither a Parser nor a factory")


# --------------------------------------------------------------------------- #
# Built-in providers — lazy factories so this module stays import-light and is
# robust to *how* the sibling parser modules are written: whether or not they
# self-register at import time, these factories still find them.
# --------------------------------------------------------------------------- #

def _pymupdf_factory() -> Parser:
    from .pymupdf_parser import PyMuPDFParser  # local import: defers `fitz`
    return PyMuPDFParser()


def _text_factory() -> Parser:
    from .text_parser import TextParser
    return TextParser()


# ext -> factory. Keep this list aligned with the sibling parsers' coverage.
_DEFAULTS: dict[str, Callable[[], Parser]] = {
    "pdf": _pymupdf_factory,
    "md": _text_factory,
    "markdown": _text_factory,
    "txt": _text_factory,
    "text": _text_factory,
    "html": _text_factory,
    "htm": _text_factory,
}


def _install_defaults() -> None:
    """Seed the registry with the built-in extension -> factory mappings.

    Sibling parser modules may *also* call :func:`register` at import time to add
    or override entries; that still works (and overrides these defaults).
    """
    for ext, factory in _DEFAULTS.items():
        _REGISTRY.setdefault(ext, factory)


_install_defaults()


# `prefer` keyword -> factory, so a caller can force a parser family regardless
# of the path's extension (e.g. feed an ``.html`` export through the text parser).
_PREFER_FACTORIES: dict[str, Callable[[], Parser]] = {
    "pdf": _pymupdf_factory,
    "pymupdf": _pymupdf_factory,
    "text": _text_factory,
    "txt": _text_factory,
    "md": _text_factory,
    "markdown": _text_factory,
    "html": _text_factory,
}


def get_parser(path: Path, prefer: str | None = None) -> Parser:
    """Return a parser for ``path``.

    Dispatch is by file extension (``.pdf`` -> PyMuPDF, ``.md``/``.txt``/``.html``
    -> text). ``prefer`` overrides extension-based dispatch: it may name a built-in
    family ("pdf"/"text"/"md"/"html"/...) or any :func:`register`-ed extension.
    Unknown extensions fall back to the text parser, which tolerates arbitrary
    UTF-8 text rather than refusing to ingest.
    """
    path = Path(path)

    if prefer is not None:
        key = prefer.strip().lower().lstrip(".")
        if key in _REGISTRY:
            return _resolve(_REGISTRY[key])
        if key in _PREFER_FACTORIES:
            return _PREFER_FACTORIES[key]()
        raise ValueError(
            f"unknown prefer={prefer!r}; expected one of "
            f"{sorted(set(_REGISTRY) | set(_PREFER_FACTORIES))}"
        )

    ext = path.suffix.lower().lstrip(".")
    provider = _REGISTRY.get(ext)
    if provider is None:
        # Last resort: treat unknown / extension-less files as plain text.
        provider = _text_factory
    return _resolve(provider)

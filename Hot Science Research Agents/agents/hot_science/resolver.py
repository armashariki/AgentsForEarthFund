"""Primary-source resolution for Hot Science press-first discoveries."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from html import unescape
from urllib.parse import urlparse

from agents.hot_science.clients import fetch_text
from agents.hot_science.schema import CandidateRecord, PressCoverage, SourceMention
from agents.hot_science.verification import extract_doi


PRESS_SOURCE_TYPES = {"popular_press"}


@dataclass(frozen=True)
class ResolverResult:
    candidates: list[CandidateRecord]
    unresolved_press: list[CandidateRecord]


class PrimarySourceResolverAgent:
    """Convert press discoveries into reviewable primary-study candidates.

    ScienceDaily, university notices, and media stories are useful discovery
    paths, but Hot Science decisions are made against the underlying paper or
    institutional report. This agent preserves the press item as coverage while
    extracting DOI/primary-source hints when they are present.
    """

    def __init__(
        self,
        *,
        fetch_press_pages: bool | None = None,
        press_fetch_timeout: int = 6,
    ):
        self.fetch_press_pages = (
            os.getenv("HOT_SCIENCE_FETCH_PRESS_PAGES") == "1"
            if fetch_press_pages is None
            else fetch_press_pages
        )
        self.press_fetch_timeout = press_fetch_timeout

    def resolve(self, candidates: list[CandidateRecord]) -> ResolverResult:
        resolved: list[CandidateRecord] = []
        unresolved_press: list[CandidateRecord] = []
        for candidate in candidates:
            if candidate.publication.venue_type not in PRESS_SOURCE_TYPES:
                candidate.verification.primary_source_resolved = True
                candidate.verification.primary_source_note = "Candidate was discovered as a primary source."
                resolved.append(candidate)
                continue

            self._attach_press_coverage(candidate)
            resolver_text = _resolver_text(candidate)
            doi = candidate.normalized_doi() or extract_doi(resolver_text)
            if not doi and self.fetch_press_pages:
                press_page_text = self._fetch_press_page_text(candidate)
                doi = extract_doi(press_page_text)
            primary_url = _primary_source_url(candidate, doi)
            if doi:
                candidate.doi = doi
                candidate.publication.venue_type = "peer_reviewed_journal"
                candidate.publication.primary_source_url = primary_url
                candidate.publication.url = primary_url or candidate.publication.url
                candidate.verification.primary_source_resolved = True
                candidate.verification.primary_source_note = "DOI extracted from press metadata."
                candidate.discovered_via.append(
                    SourceMention(
                        source="Primary Source Resolver",
                        url=primary_url,
                        source_type="peer_reviewed_journal",
                        note="Primary study inferred from DOI in press item.",
                    )
                )
                candidate.add_audit("primary_source_resolver", "resolved_from_press", doi)
                resolved.append(candidate)
                continue

            candidate.verification.primary_source_resolved = False
            candidate.verification.primary_source_note = (
                "Press item did not include a DOI or machine-readable primary source."
            )
            candidate.add_missing_reason(
                "publication.primary_source_url",
                "Press item needs human review to identify the underlying paper/report.",
            )
            candidate.add_audit("primary_source_resolver", "manual_review", "primary_source_unresolved")
            unresolved_press.append(candidate)
            resolved.append(candidate)
        return ResolverResult(candidates=resolved, unresolved_press=unresolved_press)

    def _attach_press_coverage(self, candidate: CandidateRecord) -> None:
        for mention in candidate.discovered_via:
            if mention.source_type not in PRESS_SOURCE_TYPES or not mention.url:
                continue
            if any(coverage.url == mention.url for coverage in candidate.press_coverage):
                continue
            candidate.press_coverage.append(
                PressCoverage(
                    outlet=mention.source,
                    url=mention.url,
                    headline=candidate.title,
                    date=mention.date_seen,
                    verified=True,
                    verification_note="Original discovery source; primary paper resolution pending.",
                )
            )
        candidate.pop_press_found = bool(candidate.press_coverage)

    def _fetch_press_page_text(self, candidate: CandidateRecord) -> str:
        urls = []
        if candidate.publication.url:
            urls.append(candidate.publication.url)
        urls.extend(mention.url for mention in candidate.discovered_via if mention.url)
        for url in dict.fromkeys(urls):
            if not _is_http_url(url):
                continue
            try:
                html = fetch_text(url, timeout=self.press_fetch_timeout)
            except Exception as exc:
                candidate.add_audit(
                    "primary_source_resolver",
                    "press_page_fetch_failed",
                    f"{url}: {exc}",
                )
                continue
            text = _strip_html(html)
            candidate.add_audit(
                "primary_source_resolver",
                "press_page_fetched",
                url,
            )
            if text:
                return text
        return ""


def _resolver_text(candidate: CandidateRecord) -> str:
    return " ".join(
        part
        for part in [
            candidate.title,
            candidate.abstract,
            candidate.publication.url,
            *_source_notes(candidate),
        ]
        if part
    )


def _source_notes(candidate: CandidateRecord) -> list[str]:
    return [mention.note for mention in candidate.discovered_via if mention.note]


def _primary_source_url(candidate: CandidateRecord, doi: str | None) -> str | None:
    if doi:
        return f"https://doi.org/{doi}"
    text = _resolver_text(candidate)
    match = re.search(r"https?://[^\s)>\"]+", text)
    return match.group(0).rstrip(".,") if match else candidate.publication.primary_source_url


def _is_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _strip_html(value: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", value)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return " ".join(unescape(text).split())

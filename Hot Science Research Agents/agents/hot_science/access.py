"""Access, paywall, and PDF metadata handling for Hot Science candidates."""

from __future__ import annotations

import os
import re
import ssl
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import certifi

from agents.hot_science.clients import fetch_json
from agents.hot_science.schema import CandidateRecord


_SSL_CTX = ssl.create_default_context(cafile=certifi.where())


@dataclass(frozen=True)
class AccessResult:
    candidates: list[CandidateRecord]


class AccessAgent:
    """Annotate candidates with open-access, paywall, and PDF-download state."""

    def __init__(self, *, pdf_root: str | Path = ".deepgreen/hot_science/pdfs"):
        self.pdf_root = Path(pdf_root)

    def annotate(self, candidates: list[CandidateRecord]) -> AccessResult:
        for candidate in candidates:
            self._apply_existing_metadata(candidate)
            self._apply_unpaywall_metadata(candidate)
            self._maybe_download_pdf(candidate)
            candidate.add_audit("access", "access_annotated", candidate.publication.access_note)
        return AccessResult(candidates=candidates)

    def _apply_existing_metadata(self, candidate: CandidateRecord) -> None:
        publication = candidate.publication
        if publication.url and publication.primary_source_url is None:
            publication.primary_source_url = publication.url
        if publication.abstract_accessible is None:
            publication.abstract_accessible = bool(candidate.abstract)
        if publication.open_access is True:
            publication.paywall = False
            publication.access_note = publication.access_note or "Source metadata indicates open access."
        elif publication.open_access is False:
            publication.paywall = True
            publication.access_note = publication.access_note or (
                "Source metadata indicates the full text may be paywalled."
            )
        elif publication.paywall is None:
            publication.access_note = publication.access_note or (
                "Open-access status unknown; keep candidate if abstract/metadata are useful."
            )
            candidate.add_missing_reason(
                "publication.paywall",
                "Access probe has not confirmed whether the paper is paywalled.",
            )
        if publication.full_text_pdf_url is None:
            publication.full_text_pdf_url = _pdf_url_from_text(publication.url)

    def _apply_unpaywall_metadata(self, candidate: CandidateRecord) -> None:
        if os.getenv("HOT_SCIENCE_ENABLE_UNPAYWALL") != "1":
            return
        doi = candidate.normalized_doi()
        email = os.getenv("UNPAYWALL_EMAIL") or os.getenv("DEEPGREEN_CONTACT_EMAIL")
        if not doi or not email:
            return
        try:
            payload = fetch_json(f"https://api.unpaywall.org/v2/{doi}?email={email}")
        except Exception as exc:
            candidate.add_audit("access", "unpaywall_failed", str(exc))
            return
        candidate.publication.open_access = bool(payload.get("is_oa"))
        candidate.publication.paywall = not candidate.publication.open_access
        candidate.publication.access_note = "Unpaywall metadata checked."
        candidate.publication.venue = candidate.publication.venue or payload.get("journal_name")
        location = payload.get("best_oa_location") or {}
        candidate.publication.full_text_pdf_url = (
            location.get("url_for_pdf")
            or candidate.publication.full_text_pdf_url
            or location.get("url")
        )

    def _maybe_download_pdf(self, candidate: CandidateRecord) -> None:
        if os.getenv("HOT_SCIENCE_DOWNLOAD_PDFS") != "1":
            return
        pdf_url = candidate.publication.full_text_pdf_url
        if not pdf_url:
            candidate.add_missing_reason("publication.downloaded_pdf_path", "No open PDF URL available.")
            return
        target_month = candidate.target_month or "unknown_month"
        output_dir = self.pdf_root / target_month
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{candidate.candidate_id}.pdf"
        try:
            req = urllib.request.Request(pdf_url, headers={"User-Agent": "DeepGreen/0.1"})
            with urllib.request.urlopen(req, timeout=30, context=_SSL_CTX) as response:
                content_type = response.headers.get("content-type", "")
                data = response.read()
            if "pdf" not in content_type.casefold() and not data.startswith(b"%PDF"):
                candidate.add_missing_reason(
                    "publication.downloaded_pdf_path",
                    "Open URL did not return a PDF payload.",
                )
                return
            output_path.write_bytes(data)
            candidate.publication.downloaded_pdf_path = str(output_path)
            candidate.add_audit("access", "pdf_downloaded", str(output_path))
        except Exception as exc:
            candidate.add_missing_reason("publication.downloaded_pdf_path", f"PDF download failed: {exc}")
            candidate.add_audit("access", "pdf_download_failed", str(exc))


def _pdf_url_from_text(text: str | None) -> str | None:
    if not text:
        return None
    match = re.search(r"https?://[^\s)>\"]+\.pdf(?:\?[^\s)>\"]*)?", text, flags=re.I)
    return match.group(0).rstrip(".,") if match else None

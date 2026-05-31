"""External source clients for UC-I-1 Hot Science monitoring."""

from __future__ import annotations

import json
import logging
import os
import shutil
import ssl
import subprocess
import time
import urllib.parse
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from datetime import date
from typing import Any

import certifi
import requests

from agents.hot_science.config import SourceConfig
from agents.hot_science.date_utils import parse_date
from agents.hot_science.schema import CandidateRecord, PublicationInfo, SourceMention

logger = logging.getLogger(__name__)

_SSL_CTX = ssl.create_default_context(cafile=certifi.where())


class SourceClientError(RuntimeError):
    """Raised when an external source cannot be fetched."""


def fetch_json(url: str, headers: dict[str, str] | None = None, timeout: int = 30) -> Any:
    return json.loads(_fetch_bytes(url, headers=headers, timeout=timeout).decode("utf-8"))


def fetch_text(url: str, headers: dict[str, str] | None = None, timeout: int = 30) -> str:
    return _fetch_bytes(url, headers=headers, timeout=timeout).decode("utf-8", errors="replace")


def user_agent() -> str:
    contact = os.getenv("DEEPGREEN_CONTACT_EMAIL") or os.getenv("OPENALEX_MAILTO")
    if contact:
        return f"DeepGreen/0.1 (mailto:{contact})"
    return "DeepGreen/0.1"


def scan_source(
    source: SourceConfig,
    *,
    query: str,
    seed_terms: Iterable[str],
    window_start: date,
    window_end: date,
    max_results: int,
) -> list[CandidateRecord]:
    """Dispatch a source scan based on source type."""
    try:
        if source.id == "openalex":
            return scan_openalex(source, query, window_start, window_end, max_results)
        if source.id == "crossref":
            return scan_crossref(source, query, window_start, window_end, max_results)
        if source.id == "semantic_scholar":
            return scan_semantic_scholar(source, query, window_start, window_end, max_results)
        if _journal_source_has_issns(source):
            return scan_journal_by_issn(source, query, window_start, window_end, max_results)
        if source.kind == "oai_pmh" and source.url:
            return scan_oai_pmh(source, window_start, window_end, max_results)
        if source.kind in {"rss", "institutional_feed", "preprint_feed"} and source.url:
            return scan_rss(source, window_start, window_end, max_results)
    except Exception as exc:
        logger.warning("Source '%s' scan failed: %s", source.id, exc)
        placeholder = CandidateRecord(
            title=f"Source scan failed: {source.name}",
            publication=PublicationInfo(venue=source.name, venue_type=source.source_type),
            discovered_via=[
                SourceMention(
                    source=source.name,
                    url=source.url,
                    source_type=source.source_type,
                    note=str(exc),
                )
            ],
            source_status="source_error",
        )
        placeholder.add_audit("source_monitor", "source_error", str(exc))
        placeholder.add_missing_reason("title", "Synthetic record describing source failure.")
        return [placeholder]
    return []


def scan_journal_by_issn(
    source: SourceConfig,
    query: str,
    window_start: date,
    window_end: date,
    max_results: int,
) -> list[CandidateRecord]:
    """Supplement journal RSS feeds with scholarly API queries by ISSN/month."""
    records: list[CandidateRecord] = []
    errors: list[str] = []
    for scanner_name, scanner in (
        ("openalex_issn", scan_openalex_by_issn),
        ("crossref_issn", scan_crossref_by_issn),
    ):
        try:
            records.extend(scanner(source, query, window_start, window_end, max_results))
        except Exception as exc:
            errors.append(f"{scanner_name}: {exc}")
            logger.info("Journal ISSN scan failed for %s via %s: %s", source.id, scanner_name, exc)

    if source.url and len(records) < max_results:
        try:
            records.extend(scan_rss(source, window_start, window_end, max_results - len(records)))
        except Exception as exc:
            errors.append(f"rss: {exc}")
            logger.info("Journal RSS scan failed for %s: %s", source.id, exc)

    deduped = _dedupe_records(records)
    if deduped:
        return deduped[:max_results]
    if errors:
        raise SourceClientError("; ".join(errors))
    return []


def scan_openalex_by_issn(
    source: SourceConfig,
    query: str,
    window_start: date,
    window_end: date,
    max_results: int,
) -> list[CandidateRecord]:
    params = {
        "search": query,
        "filter": (
            f"from_publication_date:{window_start.isoformat()},"
            f"to_publication_date:{window_end.isoformat()},"
            f"locations.source.issn:{'|'.join(source.issns)}"
        ),
        "per-page": str(max_results),
    }
    mailto = os.getenv("OPENALEX_MAILTO") or os.getenv("DEEPGREEN_CONTACT_EMAIL")
    if mailto:
        params["mailto"] = mailto
    url = f"https://api.openalex.org/works?{urllib.parse.urlencode(params)}"
    records = _records_from_openalex_payload(fetch_json(url), source)
    for record in records:
        record.add_audit(
            "source_monitor",
            "issn_backfill",
            f"OpenAlex ISSN/month query for {source.id}",
        )
    return records


def scan_crossref_by_issn(
    source: SourceConfig,
    query: str,
    window_start: date,
    window_end: date,
    max_results: int,
) -> list[CandidateRecord]:
    records: list[CandidateRecord] = []
    per_issn = max(1, -(-max_results // max(1, len(source.issns))))
    for issn in source.issns:
        params = {
            "query.bibliographic": query,
            "filter": (
                f"type:journal-article,issn:{issn},"
                f"from-pub-date:{window_start.isoformat()},"
                f"until-pub-date:{window_end.isoformat()}"
            ),
            "rows": str(per_issn),
            "select": "DOI,title,author,published-online,published-print,container-title,URL,abstract,type",
        }
        mailto = os.getenv("CROSSREF_MAILTO") or os.getenv("DEEPGREEN_CONTACT_EMAIL")
        if mailto:
            params["mailto"] = mailto
        url = f"https://api.crossref.org/works?{urllib.parse.urlencode(params)}"
        issn_records = _records_from_crossref_payload(fetch_json(url), source)
        for record in issn_records:
            record.add_audit(
                "source_monitor",
                "issn_backfill",
                f"Crossref ISSN/month query for {source.id}:{issn}",
            )
        records.extend(issn_records)
    return _dedupe_records(records)[:max_results]


def scan_openalex(
    source: SourceConfig,
    query: str,
    window_start: date,
    window_end: date,
    max_results: int,
) -> list[CandidateRecord]:
    mailto = os.getenv("OPENALEX_MAILTO") or os.getenv("DEEPGREEN_CONTACT_EMAIL")
    params = {
        "search": query,
        "filter": (
            f"from_publication_date:{window_start.isoformat()},"
            f"to_publication_date:{window_end.isoformat()}"
        ),
        "per-page": str(max_results),
    }
    if mailto:
        params["mailto"] = mailto
    url = f"https://api.openalex.org/works?{urllib.parse.urlencode(params)}"
    payload = fetch_json(url)
    return _records_from_openalex_payload(payload, source)


def _records_from_openalex_payload(payload: dict[str, Any], source: SourceConfig) -> list[CandidateRecord]:
    records: list[CandidateRecord] = []
    for item in payload.get("results", []):
        title = _strip_html(item.get("title") or "")
        if not title:
            continue
        authors = [
            (authorship.get("author") or {}).get("display_name", "")
            for authorship in item.get("authorships", [])
            if (authorship.get("author") or {}).get("display_name")
        ]
        date_text = item.get("publication_date")
        primary_location = item.get("primary_location") or {}
        primary_source = primary_location.get("source") or {}
        record = CandidateRecord(
            title=title,
            doi=item.get("doi"),
            authors=authors,
            publication=PublicationInfo(
                venue=primary_source.get("display_name") or source.name,
                venue_type=source.source_type,
                source_record_type=item.get("type") or item.get("type_crossref"),
                online_publication_date=date_text,
                date_source_field="publication_date",
                raw_publication_date=date_text,
                url=primary_location.get("landing_page_url") or item.get("doi") or item.get("id"),
                open_access=(item.get("open_access") or {}).get("is_oa"),
            ),
            abstract=_openalex_abstract(item.get("abstract_inverted_index")),
            abstract_source="openalex",
            discovered_via=[
                SourceMention(
                    source=source.name,
                    url=item.get("id"),
                    date_seen=date_text,
                    source_type=source.source_type,
                )
            ],
        )
        record.add_audit("source_monitor", "discovered", f"OpenAlex work {item.get('id')}")
        records.append(record)
    return records


def scan_crossref(
    source: SourceConfig,
    query: str,
    window_start: date,
    window_end: date,
    max_results: int,
) -> list[CandidateRecord]:
    params = {
        "query.bibliographic": query,
        "filter": (
            f"type:journal-article,from-pub-date:{window_start.isoformat()},"
            f"until-pub-date:{window_end.isoformat()}"
        ),
        "rows": str(max_results),
        "select": "DOI,title,author,published-online,published-print,container-title,URL,abstract",
    }
    mailto = os.getenv("CROSSREF_MAILTO") or os.getenv("DEEPGREEN_CONTACT_EMAIL")
    if mailto:
        params["mailto"] = mailto
    url = f"https://api.crossref.org/works?{urllib.parse.urlencode(params)}"
    payload = fetch_json(url)
    return _records_from_crossref_payload(payload, source)


def _records_from_crossref_payload(payload: dict[str, Any], source: SourceConfig) -> list[CandidateRecord]:
    records: list[CandidateRecord] = []
    for item in payload.get("message", {}).get("items", []):
        title = _first(item.get("title")) or ""
        if not title:
            continue
        online_date = _crossref_date(item.get("published-online")) or _crossref_date(
            item.get("published-print")
        )
        raw_online = item.get("published-online") or item.get("published-print")
        date_source_field = (
            "published-online" if item.get("published-online") else "published-print"
        )
        authors = [
            " ".join(part for part in [a.get("given"), a.get("family")] if part)
            for a in item.get("author", [])
        ]
        abstract = _strip_html(item.get("abstract") or "") or None
        record = CandidateRecord(
            title=title,
            doi=item.get("DOI"),
            authors=[author for author in authors if author],
            publication=PublicationInfo(
                venue=_first(item.get("container-title")) or source.name,
                venue_type=source.source_type,
                source_record_type=item.get("type"),
                online_publication_date=online_date,
                issue_publication_date=_crossref_date(item.get("published-print")),
                date_source_field=date_source_field,
                raw_publication_date=json.dumps(raw_online, sort_keys=True) if raw_online else None,
                url=item.get("URL"),
            ),
            abstract=abstract,
            abstract_source="crossref" if abstract else None,
            discovered_via=[
                SourceMention(
                    source=source.name,
                    url=item.get("URL"),
                    date_seen=online_date,
                    source_type=source.source_type,
                )
            ],
        )
        if not abstract:
            record.add_missing_reason("abstract", "Crossref did not provide an abstract.")
        record.add_audit("source_monitor", "discovered", f"Crossref DOI {item.get('DOI')}")
        records.append(record)
    return records


def scan_semantic_scholar(
    source: SourceConfig,
    query: str,
    window_start: date,
    window_end: date,
    max_results: int,
) -> list[CandidateRecord]:
    headers = {"User-Agent": user_agent()}
    api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY")
    if api_key:
        headers["x-api-key"] = api_key
    params = {
        "query": query,
        "limit": str(max_results),
        "fields": "title,authors,year,publicationDate,venue,externalIds,url,abstract,isOpenAccess,openAccessPdf",
    }
    url = "https://api.semanticscholar.org/graph/v1/paper/search?" + urllib.parse.urlencode(
        params
    )
    payload = fetch_json(url, headers=headers)
    records: list[CandidateRecord] = []
    for item in payload.get("data", []):
        title = item.get("title") or ""
        if not title:
            continue
        date_text = item.get("publicationDate") or str(item.get("year") or "")
        date_source_field = "publicationDate" if item.get("publicationDate") else "year"
        parsed = parse_date(date_text)
        if parsed and not (window_start <= parsed <= window_end):
            continue
        external_ids = item.get("externalIds") or {}
        record = CandidateRecord(
            title=title,
            doi=external_ids.get("DOI"),
            authors=[a.get("name", "") for a in item.get("authors", []) if a.get("name")],
            publication=PublicationInfo(
                venue=item.get("venue"),
                venue_type=source.source_type,
                source_record_type="paper",
                online_publication_date=parsed.isoformat() if parsed else None,
                date_source_field=date_source_field,
                raw_publication_date=date_text,
                url=item.get("url"),
                open_access=item.get("isOpenAccess"),
            ),
            abstract=item.get("abstract"),
            abstract_source="semantic_scholar" if item.get("abstract") else None,
            discovered_via=[
                SourceMention(
                    source=source.name,
                    url=item.get("url"),
                    date_seen=parsed.isoformat() if parsed else None,
                    source_type=source.source_type,
                )
            ],
        )
        if not record.abstract:
            record.add_missing_reason("abstract", "Semantic Scholar did not provide an abstract.")
        record.add_audit(
            "source_monitor",
            "discovered",
            f"Semantic Scholar paper {item.get('paperId')}",
        )
        records.append(record)
    return records


def scan_oai_pmh(
    source: SourceConfig,
    window_start: date,
    window_end: date,
    max_results: int,
) -> list[CandidateRecord]:
    if not source.url:
        return []
    params = {
        "verb": "ListRecords",
        "metadataPrefix": "oai_dc",
    }
    url = f"{source.url}?{urllib.parse.urlencode(params)}"
    data = fetch_text(url)
    root = ET.fromstring(data)
    records: list[CandidateRecord] = []
    ns = {
        "oai": "http://www.openarchives.org/OAI/2.0/",
        "dc": "http://purl.org/dc/elements/1.1/",
    }
    for item in root.findall(".//oai:record", ns):
        title = _first_text(item.findall(".//dc:title", ns))
        if not title:
            continue
        dates = [
            text
            for text in (
                _node_text(node) for node in item.findall(".//dc:date", ns)
            )
            if text
        ]
        datestamp = _node_text(item.find("./oai:header/oai:datestamp", ns))
        parsed_date = _oai_publication_date(dates, datestamp, window_start, window_end)
        if not parsed_date or not (window_start <= parsed_date <= window_end):
            continue

        creators = [
            text
            for text in (
                _node_text(node) for node in item.findall(".//dc:creator", ns)
            )
            if text
        ]
        descriptions = [
            text
            for text in (
                _node_text(node) for node in item.findall(".//dc:description", ns)
            )
            if text
        ]
        identifiers = [
            text
            for text in (
                _node_text(node) for node in item.findall(".//dc:identifier", ns)
            )
            if text
        ]
        source_url = _oai_primary_url(identifiers)
        doi = _oai_primary_doi(identifiers)
        record = CandidateRecord(
            title=_strip_html(title),
            doi=doi,
            authors=creators,
            publication=PublicationInfo(
                venue=source.name,
                venue_type=source.source_type,
                source_record_type="oai_pmh_record",
                online_publication_date=parsed_date.isoformat(),
                date_source_field="dc:date",
                raw_publication_date="; ".join(dates) or datestamp,
                url=source_url,
            ),
            abstract=_strip_html(" ".join(descriptions)) or None,
            abstract_source="oai_pmh" if descriptions else None,
            discovered_via=[
                SourceMention(
                    source=source.name,
                    url=source_url,
                    date_seen=parsed_date.isoformat(),
                    source_type=source.source_type,
                )
            ],
        )
        if not record.abstract:
            record.add_missing_reason("abstract", "OAI-PMH record did not include a description.")
        record.add_audit("source_monitor", "discovered", f"OAI-PMH record from {source.id}")
        records.append(record)
        if len(records) >= max_results:
            break
    return records


def scan_rss(
    source: SourceConfig,
    window_start: date,
    window_end: date,
    max_results: int,
) -> list[CandidateRecord]:
    if not source.url:
        return []
    # Respect public feeds a little; the orchestrator can add stronger rate
    # limiting as source volume grows.
    time.sleep(0.1)
    data = fetch_text(source.url)
    root = ET.fromstring(data)
    records: list[CandidateRecord] = []
    for item in _rss_items(root):
        title = _text(item, "title") or ""
        if not title:
            continue
        link = _text(item, "link")
        date_text = None
        date_source_field = None
        for field_name in ("pubDate", "published", "updated"):
            date_text = _text(item, field_name)
            if date_text:
                date_source_field = field_name
                break
        parsed = parse_date(date_text)
        if parsed and not (window_start <= parsed <= window_end):
            continue
        abstract = _text(item, "description") or _text(item, "summary")
        record = CandidateRecord(
            title=_strip_html(title),
            publication=PublicationInfo(
                venue=source.name,
                venue_type=source.source_type,
                source_record_type="rss_item",
                online_publication_date=parsed.isoformat() if parsed else None,
                date_source_field=date_source_field,
                raw_publication_date=date_text,
                url=link,
            ),
            abstract=_strip_html(abstract or "") or None,
            abstract_source="rss" if abstract else None,
            discovered_via=[
                SourceMention(
                    source=source.name,
                    url=link,
                    date_seen=parsed.isoformat() if parsed else None,
                    source_type=source.source_type,
                )
            ],
        )
        if not parsed:
            record.add_missing_reason(
                "publication.online_publication_date",
                "RSS item did not include a parseable date.",
            )
        record.add_audit("source_monitor", "discovered", f"RSS item from {source.id}")
        records.append(record)
        if len(records) >= max_results:
            break
    return records


def _fetch_bytes(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: int,
) -> bytes:
    request_headers = headers or {"User-Agent": user_agent()}
    req = urllib.request.Request(url, headers=request_headers)
    try:
        return _urlopen_read_with_retries(req, timeout=timeout)
    except (urllib.error.URLError, ConnectionResetError, TimeoutError, OSError):
        try:
            response = requests.get(url, headers=request_headers, timeout=timeout)
            response.raise_for_status()
            return response.content
        except requests.exceptions.RequestException:
            return _curl_fetch_bytes(url, headers=request_headers, timeout=timeout)


def _urlopen_read_with_retries(
    req: urllib.request.Request,
    *,
    timeout: int,
    attempts: int = 3,
) -> bytes:
    retriable_statuses = {429, 500, 502, 503, 504}
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            last_exc = exc
            if exc.code not in retriable_statuses or attempt == attempts - 1:
                raise
            time.sleep(_retry_delay(attempt, exc))
        except (urllib.error.URLError, ConnectionResetError, TimeoutError, OSError) as exc:
            last_exc = exc
            if attempt == attempts - 1:
                raise
            time.sleep(_retry_delay(attempt))
    if last_exc:
        raise last_exc
    raise SourceClientError("Request failed without an exception.")


def _retry_delay(attempt: int, exc: urllib.error.HTTPError | None = None) -> float:
    retry_after = exc.headers.get("Retry-After") if exc else None
    if retry_after and retry_after.isdigit():
        return min(float(retry_after), 5.0)
    return min(0.5 * (2**attempt), 2.0)


def _curl_fetch_bytes(url: str, *, headers: dict[str, str], timeout: int) -> bytes:
    curl = shutil.which("curl")
    if not curl:
        raise SourceClientError("curl fallback is unavailable for a reset HTTP feed.")
    args = [
        curl,
        "-fsSL",
        "--retry",
        "2",
        "--retry-delay",
        "1",
        "--max-time",
        str(timeout),
    ]
    for key, value in headers.items():
        args.extend(["-H", f"{key}: {value}"])
    args.append(url)
    completed = subprocess.run(args, capture_output=True, check=True)
    return completed.stdout


def _openalex_abstract(index: dict[str, list[int]] | None) -> str | None:
    if not index:
        return None
    words: list[tuple[int, str]] = []
    for word, positions in index.items():
        for pos in positions:
            words.append((pos, word))
    return " ".join(word for _, word in sorted(words)) or None


def _crossref_date(payload: dict[str, Any] | None) -> str | None:
    parts = (payload or {}).get("date-parts") or []
    if not parts or not parts[0]:
        return None
    year, month, day = (list(parts[0]) + [1, 1])[:3]
    try:
        return date(int(year), int(month), int(day)).isoformat()
    except ValueError:
        return None


def _rss_items(root: ET.Element) -> list[ET.Element]:
    channel_items = root.findall("./channel/item")
    if channel_items:
        return channel_items
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    return root.findall("atom:entry", ns)


def _text(parent: ET.Element, name: str) -> str | None:
    found = parent.find(name)
    if found is not None and found.text:
        return found.text.strip()
    for child in parent:
        if child.tag.endswith("}" + name) and child.text:
            return child.text.strip()
    if name == "link":
        for child in parent:
            if child.tag.endswith("}link"):
                return child.attrib.get("href")
    return None


def _first_text(nodes: list[ET.Element]) -> str | None:
    for node in nodes:
        text = _node_text(node)
        if text:
            return text
    return None


def _node_text(node: ET.Element | None) -> str | None:
    if node is not None and node.text:
        return node.text.strip()
    return None


def _first(values: list[str] | tuple[str, ...] | None) -> str | None:
    if not values:
        return None
    return values[0]


def _strip_html(value: str) -> str:
    text = value.replace("<jats:p>", " ").replace("</jats:p>", " ")
    text = text.replace("<p>", " ").replace("</p>", " ")
    return " ".join(text.split())


def _oai_publication_date(
    dates: list[str],
    datestamp: str | None,
    window_start: date,
    window_end: date,
) -> date | None:
    parsed_dates = [parsed for parsed in (parse_date(value) for value in dates) if parsed]
    for parsed in parsed_dates:
        if window_start <= parsed <= window_end:
            return parsed
    parsed_datestamp = parse_date(datestamp)
    if parsed_datestamp and window_start <= parsed_datestamp <= window_end:
        return parsed_datestamp
    return parsed_dates[0] if parsed_dates else parsed_datestamp


def _oai_primary_doi(identifiers: list[str]) -> str | None:
    for identifier in identifiers:
        cleaned = identifier.strip()
        if cleaned.lower().startswith("https://doi.org/"):
            return cleaned.removeprefix("https://doi.org/")
        if cleaned.lower().startswith("http://doi.org/"):
            return cleaned.removeprefix("http://doi.org/")
        if cleaned.startswith("10."):
            return cleaned
    return None


def _oai_primary_url(identifiers: list[str]) -> str | None:
    for identifier in identifiers:
        cleaned = identifier.strip()
        if cleaned.startswith(("http://", "https://")):
            return cleaned
    return None


def _journal_source_has_issns(source: SourceConfig) -> bool:
    return (
        source.source_type == "peer_reviewed_journal"
        and bool(source.issns)
        and source.kind in {"rss", "scholarly_api"}
    )


def _dedupe_records(records: list[CandidateRecord]) -> list[CandidateRecord]:
    deduped: list[CandidateRecord] = []
    seen: set[str] = set()
    for record in records:
        key = record.normalized_doi() or _normalized_title_key(record.title)
        if key in seen:
            match = next(
                existing
                for existing in deduped
                if (existing.normalized_doi() or _normalized_title_key(existing.title)) == key
            )
            match.discovered_via.extend(record.discovered_via)
            continue
        seen.add(key)
        deduped.append(record)
    return deduped


def _normalized_title_key(title: str) -> str:
    return " ".join(title.casefold().split())

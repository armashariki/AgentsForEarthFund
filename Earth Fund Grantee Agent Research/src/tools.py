"""
Deep Research Tools

Custom CrewAI tools for academic and institutional research:
- arXiv search (academic preprints)
- PubMed search (peer-reviewed medical/scientific papers)
- Semantic Scholar search (highly-cited papers)
- Government source search (.gov, WHO, World Bank, etc.)
- Deep research (comprehensive multi-database search)

Copyright (c) 2024 Bezos Earth Fund
All rights reserved.

Author: [Your Name], Bezos Earth Fund
Contact: [email@bezosearthfund.org]
Version: 1.0.0
"""

import os
import requests
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from typing import List, Dict, Type, Optional
from urllib.parse import quote_plus
import io
import threading
from hashlib import md5
from functools import wraps
from concurrent.futures import ThreadPoolExecutor, as_completed

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

# Optional: tenacity for retry logic (will gracefully degrade if not installed)
try:
    from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
    TENACITY_AVAILABLE = True
except ImportError:
    TENACITY_AVAILABLE = False


# ---------------------------
# Caching Infrastructure
# ---------------------------

# Session-scoped cache for API results
_tool_cache: Dict[str, any] = {}
_cache_lock = threading.Lock()


def get_cache_key(func_name: str, *args, **kwargs) -> str:
    """Generate a cache key from function name and arguments."""
    key_data = f"{func_name}:{str(args)}:{str(sorted(kwargs.items()))}"
    return md5(key_data.encode()).hexdigest()


def cached_api_call(func_name: str, func, *args, **kwargs):
    """Execute function with caching."""
    cache_key = get_cache_key(func_name, *args, **kwargs)

    with _cache_lock:
        if cache_key in _tool_cache:
            return _tool_cache[cache_key]

    result = func(*args, **kwargs)

    with _cache_lock:
        _tool_cache[cache_key] = result

    return result


def clear_tool_cache():
    """Clear the tool cache (call at start of each analysis)."""
    global _tool_cache
    with _cache_lock:
        _tool_cache = {}


# ---------------------------
# Retry Decorator
# ---------------------------

def api_retry(func):
    """Decorator to add retry logic with exponential backoff (if tenacity available)."""
    if TENACITY_AVAILABLE:
        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=2, max=10),
            retry=retry_if_exception_type((requests.RequestException, requests.Timeout)),
            reraise=True
        )
        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        return wrapper
    else:
        # If tenacity not installed, just return the function as-is
        return func


# ---------------------------
# Low-level helper functions (with caching and retry)
# ---------------------------

@api_retry
def _arxiv_search_impl(query: str, max_results: int = 10) -> List[Dict]:
    """
    Search arXiv for academic papers (implementation).
    Returns titles, authors, abstracts, and PDF links.
    """
    base_url = "http://export.arxiv.org/api/query"
    params = {
        "search_query": f"all:{query}",
        "start": 0,
        "max_results": max_results,
        "sortBy": "relevance",
        "sortOrder": "descending"
    }

    headers = {
        "User-Agent": "ResearchAssistant/1.0 (Academic Research Tool)"
    }

    try:
        r = requests.get(base_url, params=params, headers=headers, timeout=30)
        r.raise_for_status()

        # Parse XML response
        root = ET.fromstring(r.content)
        ns = {"atom": "http://www.w3.org/2005/Atom"}

        results = []
        for entry in root.findall("atom:entry", ns):
            title = entry.find("atom:title", ns)
            summary = entry.find("atom:summary", ns)
            published = entry.find("atom:published", ns)

            # Get authors
            authors = []
            for author in entry.findall("atom:author", ns):
                name = author.find("atom:name", ns)
                if name is not None:
                    authors.append(name.text)

            # Get PDF link
            pdf_link = ""
            for link in entry.findall("atom:link", ns):
                if link.get("title") == "pdf":
                    pdf_link = link.get("href")
                    break

            # Get abstract page link
            id_elem = entry.find("atom:id", ns)
            abstract_link = id_elem.text if id_elem is not None else ""

            results.append({
                "title": title.text.strip().replace("\n", " ") if title is not None else "",
                "authors": ", ".join(authors[:3]) + ("..." if len(authors) > 3 else ""),
                "abstract": summary.text.strip()[:500] + "..." if summary is not None and len(summary.text) > 500 else (summary.text.strip() if summary is not None else ""),
                "published": published.text[:10] if published is not None else "",
                "link": abstract_link,
                "pdf": pdf_link,
                "source_type": "Peer-reviewed preprint (arXiv)"
            })

        return results
    except Exception as e:
        return [{"error": str(e)}]


def _arxiv_search(query: str, max_results: int = 10) -> List[Dict]:
    """Search arXiv with caching."""
    return cached_api_call("arxiv", _arxiv_search_impl, query, max_results)


@api_retry
def _pubmed_search_impl(query: str, max_results: int = 10) -> List[Dict]:
    """
    Search PubMed for peer-reviewed medical/scientific papers (implementation).
    Uses NCBI E-utilities API (free, no key required for low volume).
    """
    # First, search for IDs
    search_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    search_params = {
        "db": "pubmed",
        "term": query,
        "retmax": max_results,
        "retmode": "json",
        "sort": "relevance"
    }

    headers = {
        "User-Agent": "ResearchAssistant/1.0 (Academic Research Tool)"
    }

    try:
        r = requests.get(search_url, params=search_params, headers=headers, timeout=30)
        r.raise_for_status()
        search_data = r.json()

        id_list = search_data.get("esearchresult", {}).get("idlist", [])
        if not id_list:
            return []

        # Fetch details for each paper
        fetch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
        fetch_params = {
            "db": "pubmed",
            "id": ",".join(id_list),
            "retmode": "json"
        }

        r = requests.get(fetch_url, params=fetch_params, headers=headers, timeout=30)
        r.raise_for_status()
        fetch_data = r.json()

        results = []
        for pmid in id_list:
            paper = fetch_data.get("result", {}).get(pmid, {})
            if not paper or pmid == "uids":
                continue

            authors = paper.get("authors", [])
            author_names = ", ".join([a.get("name", "") for a in authors[:3]])
            if len(authors) > 3:
                author_names += "..."

            results.append({
                "title": paper.get("title", ""),
                "authors": author_names,
                "journal": paper.get("fulljournalname", paper.get("source", "")),
                "published": paper.get("pubdate", ""),
                "link": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                "doi": paper.get("elocationid", ""),
                "source_type": "Peer-reviewed journal (PubMed)"
            })

        return results
    except Exception as e:
        return [{"error": str(e)}]


def _pubmed_search(query: str, max_results: int = 10) -> List[Dict]:
    """Search PubMed with caching."""
    return cached_api_call("pubmed", _pubmed_search_impl, query, max_results)


@api_retry
def _semantic_scholar_search_impl(query: str, max_results: int = 10) -> List[Dict]:
    """
    Search Semantic Scholar for academic papers with citation counts (implementation).
    Free API, no key required.
    """
    base_url = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {
        "query": query,
        "limit": max_results,
        "fields": "title,authors,year,abstract,citationCount,url,venue,publicationTypes"
    }

    headers = {
        "User-Agent": "ResearchAssistant/1.0 (Academic Research Tool)"
    }

    try:
        r = requests.get(base_url, params=params, headers=headers, timeout=30)
        r.raise_for_status()
        data = r.json()

        results = []
        for paper in data.get("data", []):
            authors = paper.get("authors", [])
            author_names = ", ".join([a.get("name", "") for a in authors[:3]])
            if len(authors) > 3:
                author_names += "..."

            pub_types = paper.get("publicationTypes", [])
            source_type = "Academic paper"
            if pub_types:
                if "JournalArticle" in pub_types:
                    source_type = "Peer-reviewed journal article"
                elif "Conference" in pub_types:
                    source_type = "Peer-reviewed conference paper"
                elif "Review" in pub_types:
                    source_type = "Review article"

            abstract = paper.get("abstract", "") or ""
            results.append({
                "title": paper.get("title", ""),
                "authors": author_names,
                "year": paper.get("year", ""),
                "venue": paper.get("venue", ""),
                "citations": paper.get("citationCount", 0),
                "abstract": abstract[:500] + "..." if len(abstract) > 500 else abstract,
                "link": paper.get("url", ""),
                "source_type": source_type
            })

        return sorted(results, key=lambda x: x.get("citations", 0), reverse=True)
    except Exception as e:
        return [{"error": str(e)}]


def _semantic_scholar_search(query: str, max_results: int = 10) -> List[Dict]:
    """Search Semantic Scholar with caching."""
    return cached_api_call("semantic_scholar", _semantic_scholar_search_impl, query, max_results)


@api_retry
def _search_government_sources_impl(query: str) -> List[Dict]:
    """
    Search for government and institutional sources (implementation).
    Targets .gov, .edu, and major institutional domains.
    """
    # Use DuckDuckGo HTML search (no API key needed) with site filters
    sites = ["site:gov", "site:edu", "site:who.int", "site:worldbank.org", "site:imf.org", "site:oecd.org"]
    site_filter = " OR ".join(sites)

    search_url = "https://html.duckduckgo.com/html/"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0 Safari/537.36"
        )
    }

    try:
        # Search with site restrictions
        r = requests.post(
            search_url,
            data={"q": f"{query} ({site_filter})"},
            headers=headers,
            timeout=30
        )
        r.raise_for_status()

        soup = BeautifulSoup(r.text, "html.parser")
        results = []

        for result in soup.select(".result")[:10]:
            title_elem = result.select_one(".result__title")
            link_elem = result.select_one(".result__url")
            snippet_elem = result.select_one(".result__snippet")

            if title_elem and link_elem:
                link = link_elem.get_text(strip=True)
                if not link.startswith("http"):
                    link = "https://" + link

                # Determine source type based on domain
                source_type = "Institutional source"
                if ".gov" in link:
                    source_type = "Government report/data"
                elif ".edu" in link:
                    source_type = "Academic institution"
                elif "who.int" in link:
                    source_type = "WHO (International health authority)"
                elif "worldbank.org" in link:
                    source_type = "World Bank (Economic data)"
                elif "imf.org" in link:
                    source_type = "IMF (Economic analysis)"
                elif "oecd.org" in link:
                    source_type = "OECD (Policy research)"

                results.append({
                    "title": title_elem.get_text(strip=True),
                    "link": link,
                    "snippet": snippet_elem.get_text(strip=True) if snippet_elem else "",
                    "source_type": source_type
                })

        return results
    except Exception as e:
        return [{"error": str(e)}]


def _search_government_sources(query: str) -> List[Dict]:
    """Search government sources with caching."""
    return cached_api_call("government", _search_government_sources_impl, query)


def _wikipedia_search(query: str, k: int = 6) -> List[Dict]:
    """
    Wikipedia search API (stable, no scraping, no API key).
    NOTE: Wikipedia is a SECONDARY source - use for context only.
    """
    url = "https://en.wikipedia.org/w/api.php"
    params = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "format": "json",
        "srlimit": k,
        "origin": "*",
    }
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0 Safari/537.36"
        ),
        "Accept": "application/json,text/plain,*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://en.wikipedia.org/",
    }

    r = requests.get(url, params=params, headers=headers, timeout=30)
    r.raise_for_status()
    data = r.json()

    results: List[Dict] = []
    for item in data.get("query", {}).get("search", []):
        title = item.get("title", "")
        page_url = f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"
        results.append(
            {
                "title": title,
                "link": page_url,
                "snippet": item.get("snippet", ""),
                "source_type": "Secondary source (Wikipedia) - verify with primary sources"
            }
        )
    return results


def _fetch_page_text(url: str, max_chars: int = 12000) -> str:
    """Fetch and extract text from a webpage."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }
    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")

    # Remove noise
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header"]):
        tag.decompose()

    text = " ".join(soup.get_text(" ").split())
    return text[:max_chars]


def _fetch_arxiv_pdf_text(arxiv_url: str, max_chars: int = 15000) -> str:
    """
    Fetch the abstract and full text from arXiv.
    Uses the abstract page since PDF parsing requires additional dependencies.
    """
    # Convert PDF URL to abstract URL if needed
    if "/pdf/" in arxiv_url:
        arxiv_url = arxiv_url.replace("/pdf/", "/abs/").replace(".pdf", "")

    return _fetch_page_text(arxiv_url, max_chars)


def write_file(path: str, content: str) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


# ---------------------------
# File Processing Functions
# ---------------------------

def process_uploaded_files(uploaded_files) -> List[Dict]:
    """
    Process uploaded files (PDF, TXT, MD) and extract text content.

    Args:
        uploaded_files: List of Streamlit UploadedFile objects

    Returns:
        List of dictionaries with filename, content, source_type, and char_count
    """
    from pypdf import PdfReader

    processed_docs = []

    for uploaded_file in uploaded_files:
        filename = uploaded_file.name
        file_ext = filename.lower().split('.')[-1]
        content = ""

        try:
            if file_ext == 'pdf':
                # Process PDF using pypdf
                pdf_reader = PdfReader(io.BytesIO(uploaded_file.getvalue()))
                text_parts = []
                for page_num, page in enumerate(pdf_reader.pages):
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(f"[Page {page_num + 1}]\n{page_text}")
                content = "\n\n".join(text_parts)

            elif file_ext in ['txt', 'md']:
                # Process text/markdown files
                content = uploaded_file.getvalue().decode('utf-8')

            if content.strip():
                processed_docs.append({
                    'filename': filename,
                    'content': content[:50000],  # Limit to 50k chars
                    'source_type': f"User-provided {file_ext.upper()} (UNVERIFIED)",
                    'char_count': len(content)
                })
            else:
                processed_docs.append({
                    'filename': filename,
                    'content': "[No text content could be extracted]",
                    'source_type': f"User-provided {file_ext.upper()} (EMPTY)",
                    'char_count': 0
                })

        except Exception as e:
            processed_docs.append({
                'filename': filename,
                'content': f"[Error processing file: {str(e)}]",
                'source_type': f"User-provided {file_ext.upper()} (ERROR)",
                'char_count': 0
            })

    return processed_docs


def extract_pdf_text(pdf_bytes: bytes, max_chars: int = 50000) -> str:
    """
    Extract text from PDF bytes.

    Args:
        pdf_bytes: Raw PDF file content as bytes
        max_chars: Maximum characters to extract

    Returns:
        Extracted text content
    """
    from pypdf import PdfReader

    try:
        pdf_reader = PdfReader(io.BytesIO(pdf_bytes))
        text_parts = []
        total_chars = 0

        for page in pdf_reader.pages:
            page_text = page.extract_text() or ""
            if total_chars + len(page_text) > max_chars:
                remaining = max_chars - total_chars
                text_parts.append(page_text[:remaining] + "... [TRUNCATED]")
                break
            text_parts.append(page_text)
            total_chars += len(page_text)

        return "\n\n".join(text_parts)
    except Exception as e:
        return f"[Error extracting PDF text: {str(e)}]"


# ---------------------------
# CrewAI Tool wrappers
# ---------------------------

class SearchInput(BaseModel):
    query: str = Field(..., description="Search query for finding relevant content")
    max_results: int = Field(10, description="Maximum number of results to return")


class ArxivSearchTool(BaseTool):
    name: str = "arxiv_search"
    description: str = (
        "Search arXiv for peer-reviewed academic preprints and papers. "
        "Best for: computer science, physics, mathematics, quantitative biology, statistics. "
        "Returns titles, authors, abstracts, publication dates, and links. "
        "These are PRIMARY SOURCES - highly credible for academic research."
    )
    args_schema: Type[BaseModel] = SearchInput

    def _run(self, query: str, max_results: int = 10) -> str:
        results = _arxiv_search(query=query, max_results=max_results)
        if not results:
            return "No arXiv results found."
        if "error" in results[0]:
            return f"arXiv search error: {results[0]['error']}"

        output = "## arXiv Academic Papers Found:\n\n"
        for i, r in enumerate(results, 1):
            output += f"### {i}. {r['title']}\n"
            output += f"- **Authors**: {r['authors']}\n"
            output += f"- **Published**: {r['published']}\n"
            output += f"- **Source Type**: {r['source_type']}\n"
            output += f"- **Link**: {r['link']}\n"
            output += f"- **Abstract**: {r['abstract']}\n\n"

        return output


class PubMedSearchTool(BaseTool):
    name: str = "pubmed_search"
    description: str = (
        "Search PubMed for peer-reviewed medical and life science journal articles. "
        "Best for: medicine, biology, health sciences, biomedical research. "
        "Returns titles, authors, journals, publication dates. "
        "These are PRIMARY SOURCES - peer-reviewed and highly credible."
    )
    args_schema: Type[BaseModel] = SearchInput

    def _run(self, query: str, max_results: int = 10) -> str:
        results = _pubmed_search(query=query, max_results=max_results)
        if not results:
            return "No PubMed results found."
        if results and "error" in results[0]:
            return f"PubMed search error: {results[0]['error']}"

        output = "## PubMed Peer-Reviewed Articles Found:\n\n"
        for i, r in enumerate(results, 1):
            output += f"### {i}. {r['title']}\n"
            output += f"- **Authors**: {r['authors']}\n"
            output += f"- **Journal**: {r['journal']}\n"
            output += f"- **Published**: {r['published']}\n"
            output += f"- **Source Type**: {r['source_type']}\n"
            output += f"- **Link**: {r['link']}\n\n"

        return output


class SemanticScholarSearchTool(BaseTool):
    name: str = "semantic_scholar_search"
    description: str = (
        "Search Semantic Scholar for academic papers across all fields with citation counts. "
        "Results are sorted by citation count (most influential first). "
        "Best for: finding highly-cited, influential research papers. "
        "These are PRIMARY SOURCES - peer-reviewed academic literature."
    )
    args_schema: Type[BaseModel] = SearchInput

    def _run(self, query: str, max_results: int = 10) -> str:
        results = _semantic_scholar_search(query=query, max_results=max_results)
        if not results:
            return "No Semantic Scholar results found."
        if results and "error" in results[0]:
            return f"Semantic Scholar search error: {results[0]['error']}"

        output = "## Semantic Scholar Academic Papers (sorted by citations):\n\n"
        for i, r in enumerate(results, 1):
            output += f"### {i}. {r['title']}\n"
            output += f"- **Authors**: {r['authors']}\n"
            output += f"- **Year**: {r['year']}\n"
            output += f"- **Venue**: {r['venue']}\n"
            output += f"- **Citations**: {r['citations']}\n"
            output += f"- **Source Type**: {r['source_type']}\n"
            output += f"- **Link**: {r['link']}\n"
            if r['abstract']:
                output += f"- **Abstract**: {r['abstract']}\n"
            output += "\n"

        return output


class GovernmentSourceSearchTool(BaseTool):
    name: str = "government_search"
    description: str = (
        "Search for government reports, official statistics, and institutional analyses. "
        "Targets: .gov sites, WHO, World Bank, IMF, OECD, and .edu institutions. "
        "Best for: official statistics, policy documents, regulatory information. "
        "These are PRIMARY SOURCES - authoritative institutional data."
    )
    args_schema: Type[BaseModel] = SearchInput

    def _run(self, query: str, max_results: int = 10) -> str:
        results = _search_government_sources(query=query)
        if not results:
            return "No government/institutional sources found."
        if results and "error" in results[0]:
            return f"Government search error: {results[0]['error']}"

        output = "## Government & Institutional Sources Found:\n\n"
        for i, r in enumerate(results[:max_results], 1):
            output += f"### {i}. {r['title']}\n"
            output += f"- **Source Type**: {r['source_type']}\n"
            output += f"- **Link**: {r['link']}\n"
            output += f"- **Snippet**: {r['snippet']}\n\n"

        return output


class WikipediaSearchTool(BaseTool):
    name: str = "wikipedia_search"
    description: str = (
        "Search Wikipedia for background context and general information. "
        "WARNING: Wikipedia is a SECONDARY source. Use only for background context. "
        "Always verify claims with PRIMARY sources (academic papers, government data). "
        "Do NOT cite Wikipedia as a primary source in research."
    )
    args_schema: Type[BaseModel] = SearchInput

    def _run(self, query: str, max_results: int = 6) -> str:
        results = _wikipedia_search(query=query, k=max_results)
        if not results:
            return "No Wikipedia results found."

        output = "## Wikipedia Results (SECONDARY SOURCE - verify with primary sources):\n\n"
        for r in results:
            output += f"- **{r['title']}** ({r['source_type']})\n"
            output += f"  Link: {r['link']}\n\n"

        return output


class UrlListInput(BaseModel):
    urls: List[str] = Field(..., description="List of URLs to analyze")


class UseProvidedUrlsTool(BaseTool):
    name: str = "use_provided_urls"
    description: str = "Use user-provided URLs as the source list. Classify each by source type."
    args_schema: Type[BaseModel] = UrlListInput

    def _run(self, urls: List[str]) -> str:
        cleaned = [u.strip() for u in urls if u and u.strip()]
        if not cleaned:
            return "No URLs provided."

        output = "## Provided URLs for Analysis:\n\n"
        for url in cleaned:
            # Classify source type
            source_type = "Unknown source type"
            if "arxiv.org" in url:
                source_type = "PRIMARY: Peer-reviewed preprint (arXiv)"
            elif "pubmed" in url or "ncbi.nlm.nih.gov" in url:
                source_type = "PRIMARY: Peer-reviewed journal (PubMed)"
            elif ".gov" in url:
                source_type = "PRIMARY: Government source"
            elif ".edu" in url:
                source_type = "PRIMARY: Academic institution"
            elif "nature.com" in url or "science.org" in url or "sciencedirect" in url:
                source_type = "PRIMARY: Peer-reviewed journal"
            elif "who.int" in url:
                source_type = "PRIMARY: WHO official source"
            elif "worldbank.org" in url or "imf.org" in url or "oecd.org" in url:
                source_type = "PRIMARY: International institution"
            elif "wikipedia" in url:
                source_type = "SECONDARY: Wikipedia (verify with primary sources)"
            elif "medium.com" in url or "blog" in url:
                source_type = "SECONDARY: Blog/opinion (low credibility)"
            else:
                source_type = "UNCLASSIFIED: Verify credibility manually"

            output += f"- {url}\n  → **{source_type}**\n\n"

        return output


class FetchPageInput(BaseModel):
    url: str = Field(..., description="URL of the webpage to fetch")
    max_chars: int = Field(12000, description="Max characters to return")


class FetchPageTextTool(BaseTool):
    name: str = "fetch_page_text"
    description: str = (
        "Fetch a webpage and extract readable text for deep analysis. "
        "Use this to read the full content of papers, reports, and articles. "
        "Supports academic pages, government reports, and general web pages."
    )
    args_schema: Type[BaseModel] = FetchPageInput

    def _run(self, url: str, max_chars: int = 12000) -> str:
        try:
            # Handle arXiv specially
            if "arxiv.org" in url:
                return _fetch_arxiv_pdf_text(url, max_chars)
            return _fetch_page_text(url=url, max_chars=max_chars)
        except Exception as e:
            return f"Error fetching {url}: {str(e)}"


class DeepResearchInput(BaseModel):
    query: str = Field(..., description="Research query/topic")
    include_arxiv: bool = Field(True, description="Search arXiv for academic preprints")
    include_pubmed: bool = Field(True, description="Search PubMed for medical/bio papers")
    include_semantic_scholar: bool = Field(True, description="Search Semantic Scholar")
    include_government: bool = Field(True, description="Search government sources")


class DeepResearchTool(BaseTool):
    name: str = "deep_research"
    description: str = (
        "Conduct comprehensive deep research across multiple PRIMARY source databases. "
        "Searches: arXiv (academic), PubMed (medical), Semantic Scholar (all fields), Government sources. "
        "Use this for thorough academic and institutional research. "
        "Returns consolidated results from all primary source databases."
    )
    args_schema: Type[BaseModel] = DeepResearchInput

    def _run(
        self,
        query: str,
        include_arxiv: bool = True,
        include_pubmed: bool = True,
        include_semantic_scholar: bool = True,
        include_government: bool = True
    ) -> str:
        """Execute research queries in parallel for better performance."""
        # Build task list based on requested sources
        tasks = {}
        if include_arxiv:
            tasks["arxiv"] = lambda q=query: _arxiv_search(q, max_results=5)
        if include_pubmed:
            tasks["pubmed"] = lambda q=query: _pubmed_search(q, max_results=5)
        if include_semantic_scholar:
            tasks["semantic_scholar"] = lambda q=query: _semantic_scholar_search(q, max_results=5)
        if include_government:
            tasks["government"] = lambda q=query: _search_government_sources(q)

        # Execute all searches in parallel
        results = {}
        with ThreadPoolExecutor(max_workers=4) as executor:
            future_to_name = {executor.submit(func): name for name, func in tasks.items()}
            for future in as_completed(future_to_name):
                name = future_to_name[future]
                try:
                    results[name] = future.result(timeout=35)
                except Exception as e:
                    results[name] = [{"error": str(e)}]

        # Format output in consistent order
        output = f"# Deep Research Results for: {query}\n\n"
        output += "---\n\n"

        if include_arxiv:
            output += "## 1. arXiv Academic Preprints\n\n"
            arxiv_results = results.get("arxiv", [])
            if arxiv_results and "error" not in arxiv_results[0]:
                for r in arxiv_results:
                    output += f"- **{r['title']}** ({r['published']})\n"
                    output += f"  Authors: {r['authors']}\n"
                    output += f"  Link: {r['link']}\n"
                    output += f"  Type: {r['source_type']}\n\n"
            else:
                output += "No arXiv results or error occurred.\n\n"

        if include_pubmed:
            output += "## 2. PubMed Peer-Reviewed Articles\n\n"
            pubmed_results = results.get("pubmed", [])
            if pubmed_results and "error" not in pubmed_results[0]:
                for r in pubmed_results:
                    output += f"- **{r['title']}**\n"
                    output += f"  Journal: {r['journal']} ({r['published']})\n"
                    output += f"  Link: {r['link']}\n"
                    output += f"  Type: {r['source_type']}\n\n"
            else:
                output += "No PubMed results or error occurred.\n\n"

        if include_semantic_scholar:
            output += "## 3. Semantic Scholar (by citation count)\n\n"
            ss_results = results.get("semantic_scholar", [])
            if ss_results and "error" not in ss_results[0]:
                for r in ss_results:
                    output += f"- **{r['title']}** ({r['year']})\n"
                    output += f"  Citations: {r['citations']}\n"
                    output += f"  Venue: {r['venue']}\n"
                    output += f"  Link: {r['link']}\n"
                    output += f"  Type: {r['source_type']}\n\n"
            else:
                output += "No Semantic Scholar results or error occurred.\n\n"

        if include_government:
            output += "## 4. Government & Institutional Sources\n\n"
            gov_results = results.get("government", [])
            if gov_results and "error" not in gov_results[0]:
                for r in gov_results[:5]:
                    output += f"- **{r['title']}**\n"
                    output += f"  Link: {r['link']}\n"
                    output += f"  Type: {r['source_type']}\n\n"
            else:
                output += "No government sources found or error occurred.\n\n"

        output += "---\n"
        output += "**Note**: All sources above are PRIMARY sources. Prioritize peer-reviewed and government sources.\n"

        return output


# ---------------------------
# NEW: Grant Proposal Analysis Tools
# ---------------------------

class PatentSearchInput(BaseModel):
    query: str = Field(..., description="Patent search query (technology or concept)")
    max_results: int = Field(10, description="Maximum number of results")


class PatentSearchTool(BaseTool):
    name: str = "patent_search"
    description: str = (
        "Search for patents and prior art related to a technology or concept. "
        "Uses Google Patents search to find relevant patents. "
        "Useful for: assessing novelty, finding prior art, identifying IP landscape. "
        "Returns patent titles, assignees, dates, and abstracts."
    )
    args_schema: Type[BaseModel] = PatentSearchInput

    def _run(self, query: str, max_results: int = 10) -> str:
        """Search Google Patents via DuckDuckGo site search."""
        search_url = "https://html.duckduckgo.com/html/"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0 Safari/537.36"
            )
        }

        try:
            r = requests.post(
                search_url,
                data={"q": f"{query} site:patents.google.com"},
                headers=headers,
                timeout=30
            )
            r.raise_for_status()

            soup = BeautifulSoup(r.text, "html.parser")
            results = []

            for result in soup.select(".result")[:max_results]:
                title_elem = result.select_one(".result__title")
                link_elem = result.select_one(".result__url")
                snippet_elem = result.select_one(".result__snippet")

                if title_elem and link_elem:
                    link = link_elem.get_text(strip=True)
                    if not link.startswith("http"):
                        link = "https://" + link

                    results.append({
                        "title": title_elem.get_text(strip=True),
                        "link": link,
                        "snippet": snippet_elem.get_text(strip=True) if snippet_elem else "",
                    })

            if not results:
                return f"No patents found for query: {query}"

            output = f"## Patent Search Results for: {query}\n\n"
            for i, r in enumerate(results, 1):
                output += f"### {i}. {r['title']}\n"
                output += f"- **Link**: {r['link']}\n"
                output += f"- **Summary**: {r['snippet']}\n\n"

            output += "\n**Note**: Review full patents for detailed claims and prior art analysis.\n"
            return output

        except Exception as e:
            return f"Patent search error: {str(e)}"


class AuthorSearchInput(BaseModel):
    author_name: str = Field(..., description="Full name of the author to search")
    affiliation: str = Field("", description="Optional: author's affiliation/institution")


class AuthorPublicationsTool(BaseTool):
    name: str = "search_author_publications"
    description: str = (
        "Search for an author's academic publication record using Semantic Scholar. "
        "Returns: publication count, citation count, h-index estimate, and top papers. "
        "Useful for: verifying team credentials, assessing research track record."
    )
    args_schema: Type[BaseModel] = AuthorSearchInput

    def _run(self, author_name: str, affiliation: str = "") -> str:
        """Search Semantic Scholar for author information."""
        base_url = "https://api.semanticscholar.org/graph/v1/author/search"

        query = author_name
        if affiliation:
            query += f" {affiliation}"

        params = {
            "query": query,
            "limit": 5,
            "fields": "name,affiliations,paperCount,citationCount,hIndex,url"
        }

        headers = {
            "User-Agent": "GrantProposalAnalyzer/1.0 (Academic Research Tool)"
        }

        try:
            r = requests.get(base_url, params=params, headers=headers, timeout=30)
            r.raise_for_status()
            data = r.json()

            authors = data.get("data", [])
            if not authors:
                return f"No author found matching: {author_name}"

            output = f"## Author Search Results for: {author_name}\n\n"

            for i, author in enumerate(authors[:3], 1):
                output += f"### {i}. {author.get('name', 'Unknown')}\n"

                affiliations = author.get("affiliations", [])
                if affiliations:
                    output += f"- **Affiliations**: {', '.join(affiliations)}\n"

                output += f"- **Publications**: {author.get('paperCount', 'N/A')}\n"
                output += f"- **Total Citations**: {author.get('citationCount', 'N/A')}\n"
                output += f"- **h-index**: {author.get('hIndex', 'N/A')}\n"

                url = author.get("url", "")
                if url:
                    output += f"- **Profile**: {url}\n"

                output += "\n"

            # Also search for their papers
            if authors:
                top_author_id = authors[0].get("authorId")
                if top_author_id:
                    papers_url = f"https://api.semanticscholar.org/graph/v1/author/{top_author_id}/papers"
                    papers_params = {
                        "limit": 5,
                        "fields": "title,year,citationCount,venue"
                    }
                    try:
                        papers_r = requests.get(papers_url, params=papers_params, headers=headers, timeout=30)
                        if papers_r.status_code == 200:
                            papers_data = papers_r.json()
                            papers = papers_data.get("data", [])
                            if papers:
                                output += "### Top Publications:\n"
                                for p in papers[:5]:
                                    output += f"- **{p.get('title', 'Untitled')}** ({p.get('year', 'N/A')})\n"
                                    output += f"  Venue: {p.get('venue', 'N/A')} | Citations: {p.get('citationCount', 0)}\n"
                    except:
                        pass

            return output

        except Exception as e:
            return f"Author search error: {str(e)}"


class OrganizationInput(BaseModel):
    organization_name: str = Field(..., description="Name of the organization to verify")


class OrganizationVerifierTool(BaseTool):
    name: str = "verify_organization"
    description: str = (
        "Verify an organization's legitimacy and track record. "
        "Searches for official websites, institutional pages, and public records. "
        "Useful for: verifying grantee organization exists and has credible history."
    )
    args_schema: Type[BaseModel] = OrganizationInput

    def _run(self, organization_name: str) -> str:
        """Search for organization information."""
        search_url = "https://html.duckduckgo.com/html/"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0 Safari/537.36"
            )
        }

        try:
            # Search for official site and news
            r = requests.post(
                search_url,
                data={"q": f'"{organization_name}" official site OR about OR team'},
                headers=headers,
                timeout=30
            )
            r.raise_for_status()

            soup = BeautifulSoup(r.text, "html.parser")
            results = []

            for result in soup.select(".result")[:8]:
                title_elem = result.select_one(".result__title")
                link_elem = result.select_one(".result__url")
                snippet_elem = result.select_one(".result__snippet")

                if title_elem and link_elem:
                    link = link_elem.get_text(strip=True)
                    if not link.startswith("http"):
                        link = "https://" + link

                    # Categorize the source
                    source_type = "General"
                    if ".gov" in link:
                        source_type = "Government"
                    elif ".edu" in link:
                        source_type = "Academic"
                    elif ".org" in link:
                        source_type = "Non-profit/NGO"
                    elif "linkedin.com" in link:
                        source_type = "LinkedIn"
                    elif "crunchbase" in link or "pitchbook" in link:
                        source_type = "Business Database"

                    results.append({
                        "title": title_elem.get_text(strip=True),
                        "link": link,
                        "snippet": snippet_elem.get_text(strip=True) if snippet_elem else "",
                        "source_type": source_type,
                    })

            if not results:
                return f"No information found for organization: {organization_name}"

            output = f"## Organization Verification: {organization_name}\n\n"

            # Group by source type
            source_types = {}
            for r in results:
                st = r["source_type"]
                if st not in source_types:
                    source_types[st] = []
                source_types[st].append(r)

            for source_type, items in source_types.items():
                output += f"### {source_type} Sources:\n"
                for item in items[:3]:
                    output += f"- **{item['title']}**\n"
                    output += f"  Link: {item['link']}\n"
                    output += f"  {item['snippet'][:200]}...\n\n"

            output += "\n**Verification Note**: Cross-reference multiple sources for confirmation.\n"
            return output

        except Exception as e:
            return f"Organization verification error: {str(e)}"


class SimilarProjectInput(BaseModel):
    project_description: str = Field(..., description="Brief description of the project")
    technology_focus: str = Field("AI climate", description="Technology/domain focus")


class SimilarProjectFinderTool(BaseTool):
    name: str = "find_similar_projects"
    description: str = (
        "Find similar funded projects in the climate tech and AI for nature space. "
        "Searches climate tech databases, accelerator portfolios, and grant databases. "
        "Useful for: benchmarking, assessing differentiation, finding competitors."
    )
    args_schema: Type[BaseModel] = SimilarProjectInput

    def _run(self, project_description: str, technology_focus: str = "AI climate") -> str:
        """Search for similar projects in climate/AI space."""
        search_url = "https://html.duckduckgo.com/html/"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0 Safari/537.36"
            )
        }

        # Keywords for climate tech sources
        climate_sites = (
            "site:climatetechvc.org OR site:ctvc.co OR "
            "site:cleantech.com OR site:greentechmedia.com OR "
            "site:climatepolicyinitiative.org"
        )

        try:
            r = requests.post(
                search_url,
                data={"q": f"{project_description} {technology_focus} funding OR grant OR investment ({climate_sites})"},
                headers=headers,
                timeout=30
            )
            r.raise_for_status()

            soup = BeautifulSoup(r.text, "html.parser")
            results = []

            for result in soup.select(".result")[:10]:
                title_elem = result.select_one(".result__title")
                link_elem = result.select_one(".result__url")
                snippet_elem = result.select_one(".result__snippet")

                if title_elem:
                    link = ""
                    if link_elem:
                        link = link_elem.get_text(strip=True)
                        if not link.startswith("http"):
                            link = "https://" + link

                    results.append({
                        "title": title_elem.get_text(strip=True),
                        "link": link,
                        "snippet": snippet_elem.get_text(strip=True) if snippet_elem else "",
                    })

            # Also search academic papers for similar research
            academic_results = _semantic_scholar_search(f"{project_description} {technology_focus}", max_results=5)

            output = f"## Similar Projects & Research\n\n"
            output += f"**Search Focus**: {project_description}\n\n"

            if results:
                output += "### Climate Tech / Funded Projects:\n\n"
                for i, r in enumerate(results[:5], 1):
                    output += f"{i}. **{r['title']}**\n"
                    if r['link']:
                        output += f"   Link: {r['link']}\n"
                    output += f"   {r['snippet'][:200]}...\n\n"

            if academic_results and "error" not in academic_results[0]:
                output += "### Related Academic Research:\n\n"
                for i, r in enumerate(academic_results[:5], 1):
                    output += f"{i}. **{r['title']}** ({r.get('year', 'N/A')})\n"
                    output += f"   Citations: {r.get('citations', 0)} | {r.get('source_type', 'Academic')}\n"
                    output += f"   Link: {r.get('link', 'N/A')}\n\n"

            output += "\n**Use this information to assess differentiation and competitive landscape.**\n"
            return output

        except Exception as e:
            return f"Similar project search error: {str(e)}"


class BudgetInput(BaseModel):
    project_type: str = Field(..., description="Type of project (research, pilot, deployment, etc.)")
    budget_amount: float = Field(..., description="Proposed budget amount in USD")
    duration_months: int = Field(12, description="Project duration in months")
    team_size: int = Field(5, description="Approximate team size")


class BudgetBenchmarkTool(BaseTool):
    name: str = "benchmark_budget"
    description: str = (
        "Compare proposed budget against typical funding amounts for similar projects. "
        "Provides industry benchmarks for AI research, climate tech, and nature projects. "
        "Useful for: assessing if budget is reasonable for the proposed scope."
    )
    args_schema: Type[BaseModel] = BudgetInput

    def _run(
        self,
        project_type: str,
        budget_amount: float,
        duration_months: int = 12,
        team_size: int = 5
    ) -> str:
        """Provide budget benchmarking analysis."""
        # Reference benchmarks for AI/Climate grants
        benchmarks = {
            "seed_research": {
                "range": "$50K - $300K",
                "typical": 150_000,
                "duration": "6-12 months",
                "typical_team": "2-4 people",
            },
            "pilot_project": {
                "range": "$200K - $1M",
                "typical": 500_000,
                "duration": "12-18 months",
                "typical_team": "4-8 people",
            },
            "full_research": {
                "range": "$500K - $3M",
                "typical": 1_500_000,
                "duration": "24-36 months",
                "typical_team": "6-12 people",
            },
            "deployment": {
                "range": "$1M - $10M",
                "typical": 3_000_000,
                "duration": "24-48 months",
                "typical_team": "10-25 people",
            },
        }

        # Determine category based on budget
        if budget_amount < 300_000:
            category = "seed_research"
        elif budget_amount < 1_000_000:
            category = "pilot_project"
        elif budget_amount < 3_000_000:
            category = "full_research"
        else:
            category = "deployment"

        benchmark = benchmarks[category]
        typical = benchmark["typical"]

        # Calculate metrics
        monthly_burn = budget_amount / duration_months if duration_months > 0 else 0
        cost_per_person = budget_amount / team_size if team_size > 0 else 0
        deviation = ((budget_amount - typical) / typical) * 100

        # Assessment
        if deviation > 50:
            assessment = "SIGNIFICANTLY ABOVE BENCHMARK"
            flag = "Review justification carefully"
        elif deviation > 20:
            assessment = "ABOVE BENCHMARK"
            flag = "May be justified for complex scope"
        elif deviation > -20:
            assessment = "WITHIN BENCHMARK"
            flag = "Reasonable for project type"
        elif deviation > -40:
            assessment = "BELOW BENCHMARK"
            flag = "May be underfunded for scope"
        else:
            assessment = "SIGNIFICANTLY BELOW BENCHMARK"
            flag = "Risk of underfunding"

        output = f"## Budget Benchmark Analysis\n\n"
        output += f"**Proposed Budget**: ${budget_amount:,.0f}\n"
        output += f"**Duration**: {duration_months} months\n"
        output += f"**Team Size**: {team_size} people\n\n"

        output += f"### Category: {category.replace('_', ' ').title()}\n"
        output += f"- **Typical Range**: {benchmark['range']}\n"
        output += f"- **Typical Budget**: ${typical:,.0f}\n"
        output += f"- **Typical Duration**: {benchmark['duration']}\n"
        output += f"- **Typical Team**: {benchmark['typical_team']}\n\n"

        output += f"### Assessment\n"
        output += f"- **Status**: {assessment}\n"
        output += f"- **Deviation from Typical**: {deviation:+.1f}%\n"
        output += f"- **Monthly Burn Rate**: ${monthly_burn:,.0f}/month\n"
        output += f"- **Cost per Team Member**: ${cost_per_person:,.0f}\n"
        output += f"- **Flag**: {flag}\n\n"

        # Common budget breakdown expectations
        output += f"### Typical Budget Allocation (AI/Climate Research):\n"
        output += f"- Personnel: 60-70%\n"
        output += f"- Equipment/Computing: 10-20%\n"
        output += f"- Travel/Fieldwork: 5-10%\n"
        output += f"- Overhead/Admin: 10-15%\n"
        output += f"- Contingency: 5-10%\n"

        return output


# ---------------------------
# Research Context Retriever Tool
# ---------------------------

class ResearchContextInput(BaseModel):
    topic: str = Field(..., description="Research topic to search for in the knowledge base")
    domain: str = Field("", description="Optional: specific domain (wildfires, invasive species, conservation, energy)")
    max_results: int = Field(5, description="Maximum number of research items to retrieve")


class ResearchContextRetrieverTool(BaseTool):
    name: str = "retrieve_research_context"
    description: str = (
        "Retrieve relevant research context from the Deep Research Assistant knowledge base. "
        "Searches for prior research briefs, findings, and analyses related to the proposal topic. "
        "Use this to find relevant context from BEF's continuous research on frontier AI applications. "
        "Sources: Prior research briefs, web searches, deep research analyses."
    )
    args_schema: Type[BaseModel] = ResearchContextInput

    def _run(self, topic: str, domain: str = "", max_results: int = 5) -> str:
        """
        Retrieve relevant research context from multiple sources.

        This searches:
        1. Local knowledge base (output/ folder) for prior research briefs
        2. Academic databases for relevant frontier research
        3. Climate tech databases for similar funded projects
        """
        output = f"# Research Context for: {topic}\n\n"

        # 1. Search local knowledge base (output folder)
        output += "## Prior Research from Knowledge Base\n\n"
        knowledge_base_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output")

        try:
            if os.path.exists(knowledge_base_path):
                found_files = []
                topic_keywords = topic.lower().split()

                for filename in os.listdir(knowledge_base_path):
                    if filename.endswith(('.md', '.txt')):
                        file_path = os.path.join(knowledge_base_path, filename)
                        try:
                            with open(file_path, 'r', encoding='utf-8') as f:
                                content = f.read()[:5000]  # First 5000 chars
                                # Check if any topic keyword appears in content
                                if any(kw in content.lower() for kw in topic_keywords):
                                    found_files.append({
                                        'filename': filename,
                                        'excerpt': content[:500] + "..."
                                    })
                        except:
                            pass

                if found_files:
                    for f in found_files[:max_results]:
                        output += f"### {f['filename']}\n"
                        output += f"{f['excerpt']}\n\n"
                else:
                    output += "*No directly relevant prior research found in knowledge base.*\n\n"
            else:
                output += "*Knowledge base not yet initialized.*\n\n"
        except Exception as e:
            output += f"*Error searching knowledge base: {str(e)}*\n\n"

        # 2. Search academic literature for frontier research
        output += "## Frontier AI Research (Academic)\n\n"

        academic_query = f"{topic} AI machine learning"
        if domain:
            academic_query = f"{domain} {topic} AI"

        try:
            ss_results = _semantic_scholar_search(academic_query, max_results=3)
            if ss_results and "error" not in ss_results[0]:
                for r in ss_results[:3]:
                    output += f"- **{r['title']}** ({r.get('year', 'N/A')})\n"
                    output += f"  Citations: {r.get('citations', 0)} | {r.get('source_type', 'Academic')}\n"
                    if r.get('abstract'):
                        output += f"  Summary: {r['abstract'][:200]}...\n"
                    output += f"  Link: {r.get('link', 'N/A')}\n\n"
            else:
                output += "*No academic results found.*\n\n"
        except:
            output += "*Could not search academic databases.*\n\n"

        # 3. Search for similar funded projects
        output += "## Similar Climate Tech Projects\n\n"

        try:
            search_url = "https://html.duckduckgo.com/html/"
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0 Safari/537.36"
                )
            }

            climate_query = f"{topic} climate grant funding OR investment"
            if domain:
                climate_query = f"{domain} {topic} grant funding"

            r = requests.post(
                search_url,
                data={"q": f"{climate_query} site:climatetechvc.org OR site:ctvc.co OR site:climatepolicyinitiative.org"},
                headers=headers,
                timeout=15
            )

            if r.status_code == 200:
                soup = BeautifulSoup(r.text, "html.parser")
                results = []

                for result in soup.select(".result")[:3]:
                    title_elem = result.select_one(".result__title")
                    snippet_elem = result.select_one(".result__snippet")

                    if title_elem:
                        results.append({
                            "title": title_elem.get_text(strip=True),
                            "snippet": snippet_elem.get_text(strip=True) if snippet_elem else "",
                        })

                if results:
                    for r in results:
                        output += f"- **{r['title']}**\n"
                        output += f"  {r['snippet'][:200]}...\n\n"
                else:
                    output += "*No similar funded projects found.*\n\n"
            else:
                output += "*Could not search climate tech databases.*\n\n"
        except:
            output += "*Could not search climate tech databases.*\n\n"

        output += "---\n"
        output += "**Use this context to inform your assessment. Cross-reference with proposal claims.**\n"

        return output


class ClimateImpactInput(BaseModel):
    technology_type: str = Field(..., description="Type of climate technology or intervention")
    claimed_impact: str = Field("", description="Optional: claimed impact metrics from proposal")


class ClimateImpactDatabaseTool(BaseTool):
    name: str = "search_climate_impact_data"
    description: str = (
        "Search climate impact databases for benchmark metrics and evidence. "
        "Sources: Project Drawdown, IPCC reports, climate research papers. "
        "Useful for: validating impact claims, finding comparable impact metrics."
    )
    args_schema: Type[BaseModel] = ClimateImpactInput

    def _run(self, technology_type: str, claimed_impact: str = "") -> str:
        """Search for climate impact benchmarks and data."""
        # Search Project Drawdown and climate sources
        search_url = "https://html.duckduckgo.com/html/"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0 Safari/537.36"
            )
        }

        climate_sites = (
            "site:drawdown.org OR site:ipcc.ch OR "
            "site:iea.org OR site:climatewatchdata.org OR "
            "site:wri.org"
        )

        try:
            r = requests.post(
                search_url,
                data={"q": f"{technology_type} climate impact CO2 reduction ({climate_sites})"},
                headers=headers,
                timeout=30
            )
            r.raise_for_status()

            soup = BeautifulSoup(r.text, "html.parser")
            results = []

            for result in soup.select(".result")[:8]:
                title_elem = result.select_one(".result__title")
                link_elem = result.select_one(".result__url")
                snippet_elem = result.select_one(".result__snippet")

                if title_elem:
                    link = ""
                    if link_elem:
                        link = link_elem.get_text(strip=True)
                        if not link.startswith("http"):
                            link = "https://" + link

                    # Identify source
                    source = "Climate Research"
                    if "drawdown" in link.lower():
                        source = "Project Drawdown"
                    elif "ipcc" in link.lower():
                        source = "IPCC"
                    elif "iea" in link.lower():
                        source = "Int'l Energy Agency"
                    elif "wri" in link.lower():
                        source = "World Resources Institute"

                    results.append({
                        "title": title_elem.get_text(strip=True),
                        "link": link,
                        "snippet": snippet_elem.get_text(strip=True) if snippet_elem else "",
                        "source": source,
                    })

            output = f"## Climate Impact Data: {technology_type}\n\n"

            if claimed_impact:
                output += f"**Claimed Impact**: {claimed_impact}\n\n"

            if results:
                output += "### Reference Sources Found:\n\n"
                for i, r in enumerate(results, 1):
                    output += f"{i}. **{r['title']}** ({r['source']})\n"
                    if r['link']:
                        output += f"   Link: {r['link']}\n"
                    output += f"   {r['snippet'][:250]}...\n\n"
            else:
                output += "No specific climate impact data found in databases.\n\n"

            # SDG mapping for climate/nature
            output += "### Relevant UN Sustainable Development Goals:\n"
            sdg_map = {
                "renewable": ["SDG 7 (Clean Energy)", "SDG 13 (Climate Action)"],
                "carbon": ["SDG 13 (Climate Action)", "SDG 12 (Responsible Consumption)"],
                "forest": ["SDG 15 (Life on Land)", "SDG 13 (Climate Action)"],
                "ocean": ["SDG 14 (Life Below Water)", "SDG 13 (Climate Action)"],
                "biodiversity": ["SDG 15 (Life on Land)", "SDG 14 (Life Below Water)"],
                "agriculture": ["SDG 2 (Zero Hunger)", "SDG 12 (Responsible Consumption)"],
                "water": ["SDG 6 (Clean Water)", "SDG 14 (Life Below Water)"],
                "energy": ["SDG 7 (Clean Energy)", "SDG 13 (Climate Action)"],
                "ai": ["SDG 9 (Innovation)", "SDG 17 (Partnerships)"],
                "default": ["SDG 13 (Climate Action)", "SDG 17 (Partnerships)"],
            }

            matched_sdgs = set()
            tech_lower = technology_type.lower()
            for keyword, sdgs in sdg_map.items():
                if keyword in tech_lower:
                    matched_sdgs.update(sdgs)

            if not matched_sdgs:
                matched_sdgs = set(sdg_map["default"])

            for sdg in sorted(matched_sdgs):
                output += f"- {sdg}\n"

            output += "\n**Note**: Verify claimed metrics against these authoritative sources.\n"
            return output

        except Exception as e:
            return f"Climate impact search error: {str(e)}"

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

from crewai.tools import BaseTool
from pydantic import BaseModel, Field


# ---------------------------
# Low-level helper functions
# ---------------------------

def _arxiv_search(query: str, max_results: int = 10) -> List[Dict]:
    """
    Search arXiv for academic papers.
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


def _pubmed_search(query: str, max_results: int = 10) -> List[Dict]:
    """
    Search PubMed for peer-reviewed medical/scientific papers.
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


def _semantic_scholar_search(query: str, max_results: int = 10) -> List[Dict]:
    """
    Search Semantic Scholar for academic papers with citation counts.
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


def _search_government_sources(query: str) -> List[Dict]:
    """
    Search for government and institutional sources.
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
        output = f"# Deep Research Results for: {query}\n\n"
        output += "---\n\n"

        if include_arxiv:
            output += "## 1. arXiv Academic Preprints\n\n"
            arxiv_results = _arxiv_search(query, max_results=5)
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
            pubmed_results = _pubmed_search(query, max_results=5)
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
            ss_results = _semantic_scholar_search(query, max_results=5)
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
            gov_results = _search_government_sources(query)
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

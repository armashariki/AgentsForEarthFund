"""
Research Context Import Module for Grant Proposal Analysis

Imports and formats outputs from the Research Assistant Agent
to provide context for grant proposal analysis.

Copyright (c) 2024 Bezos Earth Fund
All rights reserved.
"""

import os
import re
from datetime import datetime
from typing import List, Dict, Optional
from dataclasses import dataclass


@dataclass
class ResearchReport:
    """Represents an imported research report."""
    filename: str
    filepath: str
    title: str
    modified_date: datetime
    size_kb: float
    content: str
    key_findings: List[str]
    evidence_sources: List[str]
    domains: List[str]


class ResearchContextImporter:
    """
    Import research outputs from the Research Assistant Agent.

    Provides functionality to:
    - List available research reports
    - Import and parse reports
    - Extract key findings for context injection
    - Format findings for agent consumption
    """

    def __init__(self, research_folder: str = "../Research Assistant Agent/output"):
        self.research_folder = research_folder

    def is_folder_valid(self) -> bool:
        """Check if the research folder exists and is accessible."""
        return os.path.isdir(self.research_folder)

    def list_available_reports(self) -> List[Dict]:
        """
        List all available research reports with metadata.

        Returns:
            List of dicts with filename, modified_date, size_kb
        """
        if not self.is_folder_valid():
            return []

        reports = []
        for filename in os.listdir(self.research_folder):
            if filename.endswith(('.md', '.txt')):
                filepath = os.path.join(self.research_folder, filename)
                stat = os.stat(filepath)

                reports.append({
                    "filename": filename,
                    "filepath": filepath,
                    "modified_date": datetime.fromtimestamp(stat.st_mtime),
                    "size_kb": stat.st_size / 1024,
                })

        # Sort by modified date (newest first)
        reports.sort(key=lambda x: x["modified_date"], reverse=True)
        return reports

    def import_report(self, filename: str) -> Optional[ResearchReport]:
        """
        Import and parse a single research report.

        Args:
            filename: Name of the file to import

        Returns:
            ResearchReport object or None if file doesn't exist
        """
        filepath = os.path.join(self.research_folder, filename)

        if not os.path.exists(filepath):
            return None

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception:
            return None

        stat = os.stat(filepath)

        return ResearchReport(
            filename=filename,
            filepath=filepath,
            title=self._extract_title(content, filename),
            modified_date=datetime.fromtimestamp(stat.st_mtime),
            size_kb=stat.st_size / 1024,
            content=content,
            key_findings=self._extract_key_findings(content),
            evidence_sources=self._extract_sources(content),
            domains=self._extract_domains(content),
        )

    def import_multiple_reports(self, filenames: List[str]) -> List[ResearchReport]:
        """Import multiple reports at once."""
        reports = []
        for filename in filenames:
            report = self.import_report(filename)
            if report:
                reports.append(report)
        return reports

    def _extract_title(self, content: str, filename: str) -> str:
        """Extract the title from report content."""
        # Look for markdown title
        title_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
        if title_match:
            return title_match.group(1).strip()

        # Fall back to filename
        return filename.replace('.md', '').replace('.txt', '').replace('_', ' ').title()

    def _extract_key_findings(self, content: str) -> List[str]:
        """Extract key findings from the research report."""
        findings = []

        # Look for explicit key findings section
        findings_section = re.search(
            r'(?:Key Findings|Executive Summary|Main Findings|Summary)[:\s]*\n(.*?)(?:\n#|\n---|\Z)',
            content,
            re.IGNORECASE | re.DOTALL
        )

        if findings_section:
            section_text = findings_section.group(1)
            # Extract bullet points
            bullets = re.findall(r'[-*]\s+(.+?)(?:\n|$)', section_text)
            findings.extend(bullets[:10])  # Limit to 10

        # Also look for numbered findings
        numbered = re.findall(r'\d+\.\s+\*\*(.+?)\*\*', content)
        findings.extend(numbered[:5])

        # Look for highlighted statements
        highlights = re.findall(r'\*\*([^*]{20,150})\*\*', content)
        findings.extend(highlights[:5])

        # Deduplicate while preserving order
        seen = set()
        unique_findings = []
        for f in findings:
            f_lower = f.lower().strip()
            if f_lower not in seen and len(f.strip()) > 10:
                seen.add(f_lower)
                unique_findings.append(f.strip())

        return unique_findings[:15]  # Return top 15

    def _extract_sources(self, content: str) -> List[str]:
        """Extract evidence sources from the report."""
        sources = []

        # Look for URLs
        urls = re.findall(r'https?://[^\s\)]+', content)
        sources.extend(urls[:10])

        # Look for citations in format [Author, Year]
        citations = re.findall(r'\[([A-Za-z]+(?:\s+et\s+al\.?)?,?\s*\d{4})\]', content)
        sources.extend(citations[:10])

        # Look for paper titles in quotes or italics
        papers = re.findall(r'"([^"]{20,100})"', content)
        sources.extend(papers[:5])

        return list(set(sources))[:20]  # Dedupe and limit

    def _extract_domains(self, content: str) -> List[str]:
        """Extract research domains/topics from the report."""
        domains = []

        # Climate/nature keywords
        domain_keywords = {
            "wildfires": ["wildfire", "fire", "forest fire", "burn"],
            "carbon_capture": ["carbon capture", "ccs", "direct air capture", "carbon removal"],
            "ocean": ["ocean", "marine", "coastal", "sea"],
            "biodiversity": ["biodiversity", "species", "conservation", "wildlife"],
            "agriculture": ["agriculture", "farming", "crops", "food"],
            "energy": ["renewable", "solar", "wind", "energy"],
            "water": ["water", "freshwater", "drought", "irrigation"],
            "deforestation": ["deforestation", "forest", "trees", "logging"],
            "invasive_species": ["invasive", "invasive species", "pest"],
            "climate_modeling": ["climate model", "prediction", "forecast"],
        }

        content_lower = content.lower()
        for domain, keywords in domain_keywords.items():
            if any(kw in content_lower for kw in keywords):
                domains.append(domain)

        return domains

    def format_for_context(self, reports: List[ResearchReport]) -> str:
        """
        Format imported research reports for injection into agent context.

        Creates a structured summary suitable for LLM consumption.
        """
        if not reports:
            return ""

        md = []
        md.append("# Prior Research Context")
        md.append("")
        md.append("The following research has been conducted by the Deep Research Assistant")
        md.append("and may be relevant to this proposal analysis:")
        md.append("")
        md.append("---")
        md.append("")

        for report in reports:
            md.append(f"## {report.title}")
            md.append(f"*Source: {report.filename} (Updated: {report.modified_date.strftime('%Y-%m-%d')})*")
            md.append("")

            if report.domains:
                md.append(f"**Domains**: {', '.join(report.domains)}")
                md.append("")

            if report.key_findings:
                md.append("**Key Findings**:")
                for finding in report.key_findings[:7]:  # Limit to 7 per report
                    md.append(f"- {finding}")
                md.append("")

            if report.evidence_sources:
                md.append(f"**Evidence Sources**: {len(report.evidence_sources)} sources referenced")
                md.append("")

            md.append("---")
            md.append("")

        md.append("**Note**: Use this context to cross-reference proposal claims and assess")
        md.append("alignment with current research in the field.")
        md.append("")

        return "\n".join(md)

    def extract_relevant_context(
        self,
        reports: List[ResearchReport],
        proposal_keywords: List[str],
        max_chars: int = 5000,
    ) -> str:
        """
        Extract research context most relevant to the proposal.

        Args:
            reports: List of imported research reports
            proposal_keywords: Keywords from the proposal to match against
            max_chars: Maximum characters to return

        Returns:
            Formatted context string
        """
        if not reports or not proposal_keywords:
            return self.format_for_context(reports)

        # Score reports by relevance
        scored_reports = []
        keywords_lower = [kw.lower() for kw in proposal_keywords]

        for report in reports:
            content_lower = report.content.lower()
            score = sum(1 for kw in keywords_lower if kw in content_lower)

            # Boost for domain matches
            for domain in report.domains:
                if any(kw in domain for kw in keywords_lower):
                    score += 5

            scored_reports.append((report, score))

        # Sort by score and take top reports
        scored_reports.sort(key=lambda x: x[1], reverse=True)

        # Build context from most relevant reports
        md = []
        md.append("# Relevant Prior Research")
        md.append("")
        md.append("The following research from the Deep Research Assistant is most relevant")
        md.append("to this proposal:")
        md.append("")

        char_count = len("\n".join(md))

        for report, score in scored_reports:
            if score == 0:
                continue

            section = []
            section.append(f"## {report.title}")
            section.append(f"*Relevance Score: {score} | Source: {report.filename}*")
            section.append("")

            if report.key_findings:
                section.append("**Key Findings**:")
                for finding in report.key_findings[:5]:
                    section.append(f"- {finding}")
                section.append("")

            section_text = "\n".join(section)

            if char_count + len(section_text) > max_chars:
                break

            md.extend(section)
            char_count += len(section_text)

        if len(md) <= 5:  # Only header
            return self.format_for_context(reports)

        return "\n".join(md)


def get_default_research_folder() -> str:
    """Get the default path to the Research Assistant Agent output folder."""
    # Try relative path first
    current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    parent_dir = os.path.dirname(current_dir)

    possible_paths = [
        os.path.join(parent_dir, "Research Assistant Agent", "output"),
        os.path.join(current_dir, "..", "Research Assistant Agent", "output"),
        "../Research Assistant Agent/output",
    ]

    for path in possible_paths:
        if os.path.isdir(path):
            return path

    return possible_paths[0]  # Return first option as default

"""
Deep Research Crew Configuration

Defines the multi-agent research pipeline using CrewAI with Claude Opus 4.5.
Agents conduct comprehensive academic research using primary sources only.

Copyright (c) 2024 Bezos Earth Fund
All rights reserved.

Author: [Your Name], Bezos Earth Fund
Contact: [email@bezosearthfund.org]
Version: 1.0.0
"""

from typing import List, Optional, Dict

from crewai import Agent, Task, Crew, LLM
from dotenv import load_dotenv

from src.prompts import RESEARCH_INSTRUCTIONS, SUMMARY_INSTRUCTIONS
from src.tools import (
    DeepResearchTool,
    ArxivSearchTool,
    PubMedSearchTool,
    SemanticScholarSearchTool,
    GovernmentSourceSearchTool,
    WikipediaSearchTool,
    FetchPageTextTool,
    UseProvidedUrlsTool,
)

load_dotenv()


def build_crew(
    topic: str,
    urls: Optional[List[str]] = None,
    llm_model: str = "anthropic/claude-opus-4-5-20251101",
    user_documents: Optional[List[Dict]] = None
) -> Crew:
    """
    Build a 2-agent CrewAI pipeline for DEEP RESEARCH:
      - Researcher: Conducts comprehensive academic research using primary sources
      - Summarizer: Synthesizes findings into evidence-based brief

    Uses: arXiv, PubMed, Semantic Scholar, Government sources
    Prioritizes: Peer-reviewed papers, government reports, institutional analyses

    Args:
        topic: Research topic string
        urls: Optional list of URLs to analyze
        llm_model: LLM model string (e.g., "anthropic/claude-opus-4-5-20251101")
        user_documents: Optional list of user-uploaded documents with keys:
                       filename, content, source_type, char_count
    """
    llm = LLM(model=llm_model)

    # Deep Research Tools - prioritized for primary sources
    research_tools = [
        DeepResearchTool(),  # Comprehensive multi-database search
        ArxivSearchTool(),  # Academic preprints (CS, physics, math, AI)
        PubMedSearchTool(),  # Peer-reviewed medical/bio papers
        SemanticScholarSearchTool(),  # Highly-cited academic papers
        GovernmentSourceSearchTool(),  # Government & institutional sources
        FetchPageTextTool(),  # Deep content extraction
        UseProvidedUrlsTool(),  # User-provided URLs
        WikipediaSearchTool(),  # Background context only (secondary)
    ]

    researcher = Agent(
        role="Deep Research Analyst",
        goal=f"Conduct comprehensive academic research on: {topic}. Use ONLY primary sources: peer-reviewed papers, government reports, and institutional analyses. Extract verifiable evidence with full citations.",
        backstory="""You are a senior academic researcher with a PhD and 20+ years of experience in systematic literature review and evidence synthesis.

Your expertise spans:
- Systematic literature reviews following PRISMA guidelines
- Meta-analysis and evidence synthesis methodologies
- Academic database navigation (PubMed, arXiv, Semantic Scholar)
- Government and institutional data analysis
- Research methodology evaluation and critique

Your research standards are STRICT:
- You ONLY cite PRIMARY sources: peer-reviewed papers, government reports, institutional studies
- You NEVER cite Wikipedia, blogs, or news articles as evidence (only for background)
- Every claim must be traceable to a specific peer-reviewed or institutional source
- You evaluate source quality using the CRAAP test (Currency, Relevance, Authority, Accuracy, Purpose)
- You explicitly note the evidence tier (Tier 1-4) for each source
- You document citation counts and peer-review status

Your workflow:
1. Start with `deep_research` for comprehensive database search
2. Use specialized tools (arxiv_search, pubmed_search, etc.) for targeted queries
3. Fetch full content from promising sources using `fetch_page_text`
4. Cross-reference findings across multiple papers
5. Document methodology, limitations, and evidence gaps

You are known for:
- Finding the seminal papers in any field
- Identifying conflicts between studies and explaining why
- Never overstating evidence or making unsupported claims
- Providing complete academic citations for all sources""",
        llm=llm,
        verbose=True,
        tools=research_tools,
        max_iter=20,  # More iterations for thorough research
        max_retry_limit=3,
    )

    summarizer = Agent(
        role="Evidence Synthesis Analyst",
        goal=f"Transform academic research findings into a rigorous, evidence-based brief on: {topic}. Maintain strict source attribution and clearly indicate evidence strength for all claims.",
        backstory="""You are a senior evidence synthesis specialist who has authored systematic reviews and policy briefs for government agencies, research institutions, and Fortune 500 companies.

Your expertise includes:
- Synthesizing complex academic literature into actionable insights
- Grading evidence using established frameworks (GRADE, Oxford CEBM)
- Communicating research findings to non-expert audiences
- Identifying research gaps and limitations
- Translating scientific consensus into recommendations

Your quality standards:
- Every claim must trace to a PRIMARY source from the research notes
- Evidence strength (Strong/Moderate/Preliminary/Insufficient) must be stated
- You distinguish between scientific consensus and active debates
- You acknowledge limitations and knowledge gaps explicitly
- You NEVER speculate beyond what the evidence supports
- Citations follow academic format (Author, Year, Journal)

Your approach:
- Lead with the strongest evidence (highest tier sources)
- Clearly separate facts from interpretations from recommendations
- Note when evidence is conflicting or insufficient
- Provide confidence levels calibrated to the actual evidence base
- Make recommendations proportional to evidence strength""",
        llm=llm,
        verbose=True,
        max_iter=15,
        max_retry_limit=3,
    )

    # Build URL block if URLs provided
    urls_block = ""
    if urls:
        urls_block = "\n".join(f"- {u}" for u in urls)

    # Build user documents block if documents provided
    user_docs_block = ""
    if user_documents:
        docs_list = []
        for doc in user_documents:
            docs_list.append(
                f"### {doc['filename']}\n"
                f"**Source Type:** {doc['source_type']}\n"
                f"**Length:** {doc['char_count']:,} characters\n\n"
                f"**Content:**\n{doc['content'][:10000]}{'... [TRUNCATED]' if len(doc['content']) > 10000 else ''}\n"
            )
        user_docs_block = "\n---\n".join(docs_list)

    research_task = Task(
        description=(
            f"{RESEARCH_INSTRUCTIONS}\n\n"
            f"---\n\n"
            f"# DEEP RESEARCH ASSIGNMENT\n\n"
            f"## Research Topic\n{topic}\n\n"
            f"## Mission\n"
            f"Conduct comprehensive academic research using PRIMARY SOURCES ONLY.\n"
            f"Your output will inform executive decisions, so evidence quality is paramount.\n\n"
            f"## Required Research Strategy\n\n"
            f"### Step 1: Comprehensive Database Search\n"
            f"{'**User has provided specific URLs - analyze these first.**' if urls else '**No URLs provided - conduct systematic database search.**'}\n\n"
            f"{'Provided URLs (analyze these as primary sources):' if urls else 'Use these tools in order:'}\n"
            f"{urls_block if urls else ''}\n"
            f"{'Then supplement with database searches if needed.' if urls else ''}\n\n"
            f"{'1. `deep_research` - Comprehensive multi-database search' if not urls else ''}\n"
            f"{'2. `arxiv_search` - For CS, AI/ML, physics, math papers' if not urls else ''}\n"
            f"{'3. `pubmed_search` - For medical, biological, health research' if not urls else ''}\n"
            f"{'4. `semantic_scholar_search` - For highly-cited papers across all fields' if not urls else ''}\n"
            f"{'5. `government_search` - For official data and policy documents' if not urls else ''}\n\n"
            f"{'## User-Provided Documents' if user_documents else ''}\n"
            f"{'**The user has uploaded the following documents for analysis.**' if user_documents else ''}\n"
            f"{'**IMPORTANT:** These are UNVERIFIED sources. Cross-reference claims with peer-reviewed literature.' if user_documents else ''}\n\n"
            f"{user_docs_block if user_documents else ''}\n\n"
            f"### Step 2: Source Quality Filtering\n"
            f"For each source found, assess:\n"
            f"- Is it peer-reviewed? (Required for Tier 1-2)\n"
            f"- What is the citation count? (Higher = more influential)\n"
            f"- How recent is it? (Consider field dynamics)\n"
            f"- Who are the authors and their affiliations?\n\n"
            f"**REJECT**: Wikipedia, blogs, news articles, marketing materials\n"
            f"**ACCEPT**: Peer-reviewed journals, arXiv preprints, .gov, .edu, WHO, World Bank\n\n"
            f"### Step 3: Deep Content Extraction\n"
            f"For the TOP sources (minimum 5, aim for 10+):\n"
            f"- Call `fetch_page_text` to get full content\n"
            f"- Extract: methodology, key findings, statistics, limitations\n"
            f"- Note exact quotes for important claims\n\n"
            f"### Step 4: Evidence Synthesis\n"
            f"- Cross-reference findings across papers\n"
            f"- Identify consensus vs. disagreement\n"
            f"- Note evidence gaps\n"
            f"- Assign confidence levels based on source quality and agreement\n\n"
            f"## Output Requirements\n"
            f"Your research notes MUST include:\n"
            f"- Complete source table with Tier ratings\n"
            f"- Key findings with specific citations\n"
            f"- Quantitative data in tabular format\n"
            f"- Conflicting evidence analysis\n"
            f"- Research gaps identified\n"
            f"- Full academic citations for all sources\n\n"
            f"## Quality Standards\n"
            f"- Minimum 5 primary sources (peer-reviewed or institutional)\n"
            f"- Every claim must cite a specific source\n"
            f"- No Wikipedia or blog citations as evidence\n"
            f"- Evidence tier (1-4) stated for each source\n"
            f"- If no peer-reviewed evidence exists, say so explicitly\n"
        ),
        expected_output=(
            "Comprehensive academic research notes containing:\n"
            "- Research overview with methodology description\n"
            "- Primary sources table (peer-reviewed papers, government reports)\n"
            "- Key findings with full citations and evidence tiers\n"
            "- Quantitative data/statistics in tabular format\n"
            "- Conflicting evidence analysis\n"
            "- Research gaps and limitations\n"
            "- Complete academic citations (Author, Year, Journal, URL)\n"
            "- Source quality assessment for each reference"
        ),
        agent=researcher,
    )

    summary_task = Task(
        description=(
            f"{SUMMARY_INSTRUCTIONS}\n\n"
            f"---\n\n"
            f"# EVIDENCE SYNTHESIS ASSIGNMENT\n\n"
            f"## Topic\n{topic}\n\n"
            f"## Mission\n"
            f"Transform the academic research into a rigorous, evidence-based brief.\n"
            f"Maintain strict source attribution and evidence grading throughout.\n\n"
            f"## Input Quality Check\n"
            f"Before synthesizing, verify the research notes contain:\n"
            f"- [ ] Primary sources only (peer-reviewed, government, institutional)\n"
            f"- [ ] Citation information (authors, year, venue)\n"
            f"- [ ] Evidence tier ratings\n"
            f"- [ ] Specific findings with data\n\n"
            f"If primary sources are missing, note this prominently in your brief.\n\n"
            f"## Evidence Grading Framework\n"
            f"Grade each finding based on evidence strength:\n\n"
            f"| Grade | Criteria |\n"
            f"|-------|----------|\n"
            f"| **Strong** | Multiple Tier 1-2 sources agree, high citation counts |\n"
            f"| **Moderate** | Single Tier 1-2 source, or multiple Tier 3 sources |\n"
            f"| **Preliminary** | Preprints only, or single Tier 3-4 source |\n"
            f"| **Insufficient** | No primary sources available |\n\n"
            f"## Synthesis Requirements\n"
            f"1. **Lead with strongest evidence** - What do multiple peer-reviewed studies agree on?\n"
            f"2. **Note active debates** - Where do researchers disagree?\n"
            f"3. **Acknowledge gaps** - What questions remain unanswered?\n"
            f"4. **Calibrate recommendations** - Actions should match evidence strength\n\n"
            f"## Output Standards\n"
            f"- Every claim must cite a source from the research notes\n"
            f"- Evidence grade must be stated for all findings\n"
            f"- Recommendations must be proportional to evidence strength\n"
            f"- Knowledge gaps must be explicitly acknowledged\n"
            f"- No speculation beyond what sources support\n"
        ),
        expected_output=(
            "Executive-ready evidence brief containing:\n"
            "- TL;DR with evidence strength summary\n"
            "- Evidence summary table\n"
            "- Executive summary with source-backed findings\n"
            "- Detailed analysis organized by theme with evidence grades\n"
            "- Research consensus vs. active debates\n"
            "- Risks with evidence-based likelihood assessments\n"
            "- Knowledge gaps and research needs\n"
            "- Recommendations calibrated to evidence strength\n"
            "- Complete primary source citations"
        ),
        agent=summarizer,
        context=[research_task],
    )

    return Crew(
        agents=[researcher, summarizer],
        tasks=[research_task, summary_task],
        verbose=True,
    )

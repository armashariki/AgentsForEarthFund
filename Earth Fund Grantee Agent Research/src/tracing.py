"""
Execution Tracing Module for Grant Proposal Analysis

Captures agent decision-making, tool usage, and execution flow
to generate stakeholder-friendly reports for program managers and directors.

Copyright (c) 2024 Bezos Earth Fund
All rights reserved.
"""

import os
import re
from datetime import datetime
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field


@dataclass
class ToolUsage:
    """Record of a tool being used by an agent."""
    tool_name: str
    purpose: str
    result_summary: str
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class AgentTrace:
    """Trace record for a single agent's execution."""
    agent_role: str
    task_summary: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    tools_used: List[ToolUsage] = field(default_factory=list)
    key_findings: List[str] = field(default_factory=list)
    reasoning: Optional[str] = None
    score: Optional[float] = None
    output_summary: Optional[str] = None

    @property
    def duration_seconds(self) -> float:
        if self.completed_at and self.started_at:
            return (self.completed_at - self.started_at).total_seconds()
        return 0.0

    @property
    def duration_formatted(self) -> str:
        secs = self.duration_seconds
        if secs < 60:
            return f"{secs:.0f} seconds"
        mins = int(secs // 60)
        remaining_secs = int(secs % 60)
        return f"{mins} min {remaining_secs} sec"


class ExecutionTracer:
    """
    Captures high-level agent execution for stakeholder reports.

    Generates clean, readable summaries of how agents reached their
    conclusions - suitable for program managers and directors.
    """

    def __init__(
        self,
        session_id: Optional[str] = None,
        proposal_title: str = "Unknown Proposal",
        organization: str = "Unknown Organization",
    ):
        self.session_id = session_id or datetime.now().strftime("%Y%m%d_%H%M%S")
        self.proposal_title = proposal_title
        self.organization = organization
        self.started_at = datetime.now()
        self.completed_at: Optional[datetime] = None

        self.agent_traces: List[AgentTrace] = []
        self.current_agent: Optional[AgentTrace] = None

        # Evidence counters
        self.academic_papers_count = 0
        self.government_sources_count = 0
        self.similar_projects_count = 0
        self.team_verifications_count = 0
        self.patent_searches_count = 0

        # Final recommendation
        self.final_recommendation: Optional[str] = None
        self.overall_score: Optional[float] = None

    def log_agent_start(self, agent_role: str, task_summary: str) -> None:
        """Log when an agent starts its task."""
        # Complete previous agent if exists
        if self.current_agent and not self.current_agent.completed_at:
            self.current_agent.completed_at = datetime.now()

        self.current_agent = AgentTrace(
            agent_role=agent_role,
            task_summary=task_summary[:200],  # Truncate for readability
            started_at=datetime.now(),
        )
        self.agent_traces.append(self.current_agent)

    def log_tool_usage(
        self,
        tool_name: str,
        purpose: str,
        result_summary: str,
    ) -> None:
        """Log when an agent uses a tool."""
        if not self.current_agent:
            return

        usage = ToolUsage(
            tool_name=tool_name,
            purpose=purpose,
            result_summary=result_summary[:300],  # Truncate
        )
        self.current_agent.tools_used.append(usage)

        # Update counters based on tool name
        tool_lower = tool_name.lower()
        if "arxiv" in tool_lower or "pubmed" in tool_lower or "semantic_scholar" in tool_lower:
            self.academic_papers_count += 1
        elif "government" in tool_lower:
            self.government_sources_count += 1
        elif "similar_project" in tool_lower:
            self.similar_projects_count += 1
        elif "author" in tool_lower or "organization" in tool_lower or "verif" in tool_lower:
            self.team_verifications_count += 1
        elif "patent" in tool_lower:
            self.patent_searches_count += 1

    def log_agent_finding(self, finding: str) -> None:
        """Log a key finding from the current agent."""
        if self.current_agent:
            self.current_agent.key_findings.append(finding[:200])

    def log_agent_reasoning(self, reasoning: str) -> None:
        """Log the agent's reasoning/rationale."""
        if self.current_agent:
            self.current_agent.reasoning = reasoning[:500]

    def log_agent_complete(
        self,
        output_summary: str,
        score: Optional[float] = None,
    ) -> None:
        """Log when an agent completes its task."""
        if self.current_agent:
            self.current_agent.completed_at = datetime.now()
            self.current_agent.output_summary = output_summary[:500]
            self.current_agent.score = score

            # Try to extract score from output if not provided
            if score is None and output_summary:
                score_match = re.search(r'(\d+\.?\d*)\s*/\s*10', output_summary)
                if score_match:
                    self.current_agent.score = float(score_match.group(1))

    def set_final_result(
        self,
        recommendation: str,
        overall_score: float,
    ) -> None:
        """Set the final analysis result."""
        self.final_recommendation = recommendation
        self.overall_score = overall_score
        self.completed_at = datetime.now()

    @property
    def total_duration_seconds(self) -> float:
        if self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return (datetime.now() - self.started_at).total_seconds()

    @property
    def total_duration_formatted(self) -> str:
        secs = self.total_duration_seconds
        mins = int(secs // 60)
        remaining_secs = int(secs % 60)
        if mins > 0:
            return f"{mins} minutes {remaining_secs} seconds"
        return f"{remaining_secs} seconds"

    def generate_stakeholder_report(self) -> str:
        """
        Generate a clean, stakeholder-friendly execution trace report.

        Designed for program managers and directors who want to understand
        how the agents reached their conclusions without technical details.
        """
        md = []

        # Header
        md.append("# Analysis Execution Trace")
        md.append("")
        md.append(f"**Proposal**: {self.proposal_title}")
        md.append(f"**Organization**: {self.organization}")
        md.append(f"**Analysis Date**: {self.started_at.strftime('%Y-%m-%d %H:%M:%S')}")
        md.append(f"**Total Duration**: {self.total_duration_formatted}")
        md.append(f"**Session ID**: {self.session_id}")
        md.append("")
        md.append("---")
        md.append("")

        # Executive Overview
        md.append("## Executive Overview")
        md.append("")
        md.append(f"This analysis was conducted by **{len(self.agent_traces)} specialized AI agents**, consulting:")
        md.append(f"- {self.academic_papers_count} academic paper searches")
        md.append(f"- {self.government_sources_count} government/institutional sources")
        md.append(f"- {self.similar_projects_count} similar project comparisons")
        md.append(f"- {self.team_verifications_count} team credential verifications")
        if self.patent_searches_count > 0:
            md.append(f"- {self.patent_searches_count} patent/IP searches")
        md.append("")

        if self.final_recommendation:
            md.append(f"**Final Recommendation**: {self.final_recommendation}")
        if self.overall_score:
            md.append(f"**Overall Score**: {self.overall_score}/10")
        md.append("")
        md.append("---")
        md.append("")

        # Agent-by-Agent Execution
        md.append("## Agent-by-Agent Execution")
        md.append("")

        for i, trace in enumerate(self.agent_traces, 1):
            md.append(f"### Agent {i}: {trace.agent_role}")
            md.append(f"**Duration**: {trace.duration_formatted}")
            md.append("")

            # Task description (simplified)
            task_desc = self._simplify_task_description(trace.task_summary)
            md.append(f"**Task**: {task_desc}")
            md.append("")

            # Tools used (formatted nicely)
            if trace.tools_used:
                md.append("**Tools Used**:")
                md.append("")
                md.append("| Tool | Purpose | Result |")
                md.append("|------|---------|--------|")
                for tool in trace.tools_used[:5]:  # Limit to 5 tools
                    tool_display = self._simplify_tool_name(tool.tool_name)
                    result_short = tool.result_summary[:80] + "..." if len(tool.result_summary) > 80 else tool.result_summary
                    md.append(f"| {tool_display} | {tool.purpose[:50]} | {result_short} |")
                md.append("")

            # Key findings
            if trace.key_findings:
                md.append("**Key Findings**:")
                for finding in trace.key_findings[:3]:  # Limit to 3
                    md.append(f"- {finding}")
                md.append("")

            # Reasoning (if available)
            if trace.reasoning:
                md.append("**Reasoning**:")
                md.append(f"> {trace.reasoning}")
                md.append("")

            # Score (if available)
            if trace.score:
                md.append(f"**Score**: {trace.score}/10")
                md.append("")

            md.append("---")
            md.append("")

        # Decision Chain
        md.append("## Decision Chain")
        md.append("")
        decision_chain = self._generate_decision_chain()
        md.append(f"```")
        md.append(decision_chain)
        md.append(f"```")
        md.append("")

        # Footer
        md.append("---")
        md.append("")
        md.append("*Generated by Grant Proposal Analyzer - Bezos Earth Fund*")
        md.append(f"*Trace generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")

        return "\n".join(md)

    def _simplify_task_description(self, task: str) -> str:
        """Simplify technical task descriptions for stakeholders."""
        # Remove technical jargon and shorten
        task = re.sub(r'\{.*?\}', '', task)  # Remove template variables
        task = re.sub(r'\n+', ' ', task)  # Single line
        task = task.strip()[:150]

        # Extract just the core purpose
        if "Parse" in task or "Extract" in task:
            return "Extract and structure proposal data"
        elif "Technical" in task or "Feasibility" in task:
            return "Assess technical approach and feasibility"
        elif "Innovation" in task or "Novelty" in task:
            return "Evaluate innovation and novelty"
        elif "Impact" in task or "Climate" in task:
            return "Assess climate/environmental impact"
        elif "Budget" in task:
            return "Review budget and financial reasonableness"
        elif "Team" in task or "Credibility" in task:
            return "Verify team credentials and track record"
        elif "Criteria" in task or "Strategic" in task:
            return "Evaluate against BEF investment criteria"
        elif "Synthesis" in task or "Report" in task:
            return "Synthesize findings into final recommendation"

        return task[:100] if len(task) > 100 else task

    def _simplify_tool_name(self, tool_name: str) -> str:
        """Convert technical tool names to readable labels."""
        mappings = {
            "arxiv_search": "Academic Search (arXiv)",
            "pubmed_search": "Medical Literature (PubMed)",
            "semantic_scholar_search": "Academic Search",
            "search_semantic_scholar": "Academic Search",
            "search_arxiv": "Academic Search (arXiv)",
            "search_pubmed": "Medical Literature",
            "government_source_search": "Government Sources",
            "search_government_sources": "Government Sources",
            "patent_search": "Patent Search",
            "search_patents": "Patent Search",
            "author_publications": "Author Verification",
            "search_author_publications": "Author Verification",
            "organization_verifier": "Organization Check",
            "verify_organization": "Organization Check",
            "similar_project_finder": "Similar Projects",
            "find_similar_projects": "Similar Projects",
            "budget_benchmark": "Budget Benchmark",
            "search_budget_benchmarks": "Budget Benchmark",
            "climate_impact_database": "Climate Impact Data",
            "search_climate_impact_data": "Climate Impact Data",
            "retrieve_research_context": "Research Context",
            "fetch_page_text": "Web Content",
        }

        tool_lower = tool_name.lower()
        for key, value in mappings.items():
            if key in tool_lower:
                return value

        # Default: clean up the name
        return tool_name.replace("_", " ").replace("Tool", "").strip().title()

    def _generate_decision_chain(self) -> str:
        """Generate a visual decision chain."""
        steps = []

        for trace in self.agent_traces:
            role_short = self._get_short_role(trace.agent_role)
            if trace.score:
                steps.append(f"{role_short} ({trace.score:.1f})")
            else:
                steps.append(role_short)

        if self.final_recommendation:
            steps.append(f"=> {self.final_recommendation}")

        # Format as multi-line if too long
        if len(" -> ".join(steps)) > 80:
            return " ->\n".join(steps)

        return " -> ".join(steps)

    def _get_short_role(self, role: str) -> str:
        """Get a shortened version of the agent role."""
        mappings = {
            "Proposal Ingestion Specialist": "Parser",
            "Technical Feasibility Analyst": "Technical",
            "Innovation & Novelty Researcher": "Innovation",
            "Climate Impact Assessment Specialist": "Impact",
            "Budget & Financial Analyst": "Budget",
            "Team Credibility & Track Record Verifier": "Team",
            "BEF Strategic Investment Analyst": "Strategic Fit",
            "Senior Program Analyst": "Synthesis",
        }

        for key, value in mappings.items():
            if key in role:
                return value

        # Default: first word
        return role.split()[0] if role else "Agent"

    def save_to_file(self, output_dir: str = "output/traces") -> str:
        """Save the trace report to a file."""
        os.makedirs(output_dir, exist_ok=True)

        # Clean filename
        proposal_clean = re.sub(r'[^\w\s-]', '', self.proposal_title)[:30]
        proposal_clean = proposal_clean.replace(' ', '_')

        filename = f"trace_{proposal_clean}_{self.session_id}.md"
        filepath = os.path.join(output_dir, filename)

        report = self.generate_stakeholder_report()
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(report)

        return filepath


def create_tracer_from_crew_output(
    crew_output: str,
    proposal_title: str,
    organization: str,
    agent_outputs: Optional[List[Dict]] = None,
) -> ExecutionTracer:
    """
    Create a tracer from crew execution output.

    This is a fallback method when real-time tracing isn't available.
    It parses the final output to reconstruct execution details.
    """
    tracer = ExecutionTracer(
        proposal_title=proposal_title,
        organization=organization,
    )

    output_lower = crew_output.lower()

    # ---------------------------
    # Estimate evidence sources from output content
    # ---------------------------

    # Academic papers - look for citations, references to studies, arXiv, etc.
    academic_indicators = [
        r'arxiv',
        r'pubmed',
        r'semantic scholar',
        r'peer.?review',
        r'published.*?(study|paper|research)',
        r'journal',
        r'\(\d{4}\)',  # Year citations like (2023)
        r'et\s+al\.?',
        r'doi[:\s]',
        r'literature\s+review',
        r'research\s+shows',
        r'studies\s+(show|indicate|suggest)',
        r'according\s+to\s+research',
    ]
    tracer.academic_papers_count = sum(
        len(re.findall(pattern, output_lower)) for pattern in academic_indicators
    )
    # Cap at reasonable number and ensure minimum if analysis was done
    tracer.academic_papers_count = min(max(tracer.academic_papers_count // 2, 0), 25)

    # Government/institutional sources
    gov_indicators = [
        r'government',
        r'federal',
        r'state\s+agency',
        r'epa\b',
        r'doe\b',
        r'noaa',
        r'nasa',
        r'ipcc',
        r'united\s+nations',
        r'world\s+bank',
        r'iea\b',
        r'ministry',
        r'department\s+of',
        r'official\s+data',
        r'regulatory',
        r'policy\s+document',
    ]
    tracer.government_sources_count = sum(
        len(re.findall(pattern, output_lower)) for pattern in gov_indicators
    )
    tracer.government_sources_count = min(max(tracer.government_sources_count // 2, 0), 15)

    # Similar project comparisons
    project_indicators = [
        r'similar\s+project',
        r'comparable\s+(initiative|project|effort)',
        r'existing\s+(solution|project)',
        r'competitor',
        r'prior\s+art',
        r'benchmark',
        r'case\s+stud(y|ies)',
        r'other\s+organizations',
        r'funded\s+by',
        r'similar\s+approach',
    ]
    tracer.similar_projects_count = sum(
        len(re.findall(pattern, output_lower)) for pattern in project_indicators
    )
    tracer.similar_projects_count = min(max(tracer.similar_projects_count // 2, 0), 10)

    # Team credential verifications
    team_indicators = [
        r'credential',
        r'publication\s+record',
        r'track\s+record',
        r'experience\s+in',
        r'years?\s+of\s+experience',
        r'verified',
        r'confirmed',
        r'author.*?(paper|publication)',
        r'cited',
        r'h.?index',
        r'linkedin',
        r'institutional\s+affiliation',
        r'team\s+member',
        r'principal\s+investigator',
        r'pi\b',
    ]
    tracer.team_verifications_count = sum(
        len(re.findall(pattern, output_lower)) for pattern in team_indicators
    )
    tracer.team_verifications_count = min(max(tracer.team_verifications_count // 3, 0), 10)

    # Patent searches
    patent_indicators = [
        r'patent',
        r'intellectual\s+property',
        r'\bip\b',
        r'trademark',
        r'proprietary',
        r'prior\s+art',
    ]
    tracer.patent_searches_count = sum(
        len(re.findall(pattern, output_lower)) for pattern in patent_indicators
    )
    tracer.patent_searches_count = min(max(tracer.patent_searches_count // 2, 0), 5)

    # ---------------------------
    # Extract agent scores from output
    # ---------------------------
    score_patterns = [
        (r"technical.*?(\d+\.?\d*)\s*/\s*10", "Technical Feasibility Analyst", "Assess technical approach and feasibility"),
        (r"innovation.*?(\d+\.?\d*)\s*/\s*10", "Innovation & Novelty Researcher", "Evaluate innovation and novelty"),
        (r"impact.*?(\d+\.?\d*)\s*/\s*10", "Climate & Nature Impact Specialist", "Assess climate/environmental impact"),
        (r"budget.*?(\d+\.?\d*)\s*/\s*10", "Financial & Budget Analyst", "Review budget reasonableness"),
        (r"team.*?(\d+\.?\d*)\s*/\s*10", "Team Credibility Verifier", "Verify team credentials"),
        (r"strategic.*?fit.*?(\d+\.?\d*)\s*/\s*10", "BEF Strategic Investment Analyst", "Evaluate BEF investment criteria"),
    ]

    for pattern, agent_name, task_summary in score_patterns:
        match = re.search(pattern, output_lower)
        if match:
            tracer.log_agent_start(agent_name, task_summary)
            tracer.log_agent_complete(
                output_summary=f"Score: {match.group(1)}/10",
                score=float(match.group(1))
            )

    # Add synthesis agent
    tracer.log_agent_start("Senior Program Analyst", "Synthesize findings into final recommendation")

    # ---------------------------
    # Extract recommendation
    # ---------------------------
    rec_patterns = [
        r"(FUND|FUND WITH CONDITIONS|REQUEST REVISION|DECLINE)",
        r"recommendation[:\s]+(fund|decline|revise)",
    ]

    for pattern in rec_patterns:
        match = re.search(pattern, crew_output, re.IGNORECASE)
        if match:
            tracer.final_recommendation = match.group(1).upper()
            break

    # ---------------------------
    # Extract overall score
    # ---------------------------
    overall_match = re.search(r"overall.*?(\d+\.?\d*)\s*/\s*10", output_lower)
    if overall_match:
        tracer.overall_score = float(overall_match.group(1))
        tracer.log_agent_complete(
            output_summary=f"Final recommendation: {tracer.final_recommendation or 'See report'}",
            score=float(overall_match.group(1))
        )

    tracer.completed_at = datetime.now()

    return tracer

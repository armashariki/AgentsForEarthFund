"""
Grant Proposal Analysis Crew Configuration

Defines the 7-agent proposal analysis pipeline using CrewAI.
Agents analyze grant proposals for AI for Climate and Nature projects,
verify claims, and generate comprehensive assessment reports.

Includes execution tracing for stakeholder visibility into agent decisions.

Copyright (c) 2024 Bezos Earth Fund
All rights reserved.
"""

from typing import List, Optional, Dict, Callable, Tuple, Union
from datetime import datetime
from crewai import Agent, Task, Crew, LLM
from dotenv import load_dotenv

from src.tracing import ExecutionTracer, create_tracer_from_crew_output

from src.prompts import (
    PROPOSAL_PARSER_PROMPT,
    TECHNICAL_ANALYSIS_PROMPT,
    INNOVATION_ANALYSIS_PROMPT,
    IMPACT_ANALYSIS_PROMPT,
    BUDGET_ANALYSIS_PROMPT,
    TEAM_VERIFICATION_PROMPT,
    SYNTHESIS_PROMPT,
    BEF_CRITERIA_PROMPT,
)
from src.tools import (
    # Existing research tools
    ArxivSearchTool,
    PubMedSearchTool,
    SemanticScholarSearchTool,
    GovernmentSourceSearchTool,
    FetchPageTextTool,
    # New verification tools
    PatentSearchTool,
    AuthorPublicationsTool,
    OrganizationVerifierTool,
    SimilarProjectFinderTool,
    BudgetBenchmarkTool,
    ClimateImpactDatabaseTool,
    # BEF Criteria tools
    ResearchContextRetrieverTool,
)

load_dotenv()


def build_proposal_analysis_crew(
    proposal_text: str,
    proposal_metadata: Optional[Dict] = None,
    llm_model: str = "anthropic/claude-opus-4-5-20251101",
    progress_callback: Optional[Callable[[str, int], None]] = None,
    analyses_to_run: Optional[List[str]] = None,
    include_criteria_evaluation: bool = True,
    enable_tracing: bool = True,
    research_context: Optional[str] = None,
) -> Tuple[Crew, Optional[ExecutionTracer]]:
    """
    Build the 7-agent proposal analysis pipeline with BEF Criteria Evaluation.

    Args:
        proposal_text: Full text of the uploaded proposal
        proposal_metadata: Optional metadata (org name, budget amount, duration)
        llm_model: LLM model string (e.g., "anthropic/claude-opus-4-5-20251101")
        progress_callback: Optional callback for progress updates (stage_name, percent)
        analyses_to_run: Optional list of analyses to run (default: all)
            Options: ["technical", "innovation", "impact", "budget", "team", "criteria"]
        include_criteria_evaluation: Whether to include BEF Criteria Evaluation (default: True)
        enable_tracing: Whether to capture execution trace for stakeholder reports (default: True)
        research_context: Optional pre-formatted research context from Research Assistant Agent

    Returns:
        Tuple of (Configured Crew ready for kickoff, ExecutionTracer if enabled)
    """
    llm = LLM(model=llm_model)

    # Default to all analyses including criteria
    if analyses_to_run is None:
        analyses_to_run = ["technical", "innovation", "impact", "budget", "team"]
        if include_criteria_evaluation:
            analyses_to_run.append("criteria")

    # Extract metadata with defaults
    metadata = proposal_metadata or {}
    org_name = metadata.get("organization", "Unknown Organization")
    budget_amount = metadata.get("budget_amount", 0)
    duration_months = metadata.get("duration_months", 12)
    team_size = metadata.get("team_size", 5)
    proposal_title = metadata.get("title", "Grant Proposal")
    user_context = metadata.get("user_context", "")

    # ---------------------------
    # Initialize Execution Tracer (if enabled)
    # ---------------------------
    tracer = None
    if enable_tracing:
        tracer = ExecutionTracer(
            proposal_title=proposal_title,
            organization=org_name,
        )

    # ---------------------------
    # Format User Context (if provided)
    # ---------------------------
    user_context_section = ""
    if user_context:
        user_context_section = f"""

---

## Reviewer Notes & Additional Context

The following context has been provided by the BEF program team to inform this analysis:

{user_context}

**Important**: Consider this context carefully in your assessment. It may highlight specific concerns, provide background on prior relationships, or indicate areas requiring special attention.

---
"""

    # ---------------------------
    # Format Research Context (if provided)
    # ---------------------------
    research_context_section = ""
    if research_context:
        research_context_section = f"""

---

## Prior Research Context

The following research has been conducted by the Deep Research Assistant and may be relevant to this analysis:

{research_context}

Use this context to cross-reference proposal claims and assess alignment with current research in the field.

---
"""

    # ---------------------------
    # Define Tools for Each Agent
    # ---------------------------

    technical_tools = [
        ArxivSearchTool(),
        SemanticScholarSearchTool(),
        PatentSearchTool(),
        FetchPageTextTool(),
    ]

    innovation_tools = [
        PatentSearchTool(),
        SimilarProjectFinderTool(),
        ArxivSearchTool(),
        SemanticScholarSearchTool(),
        FetchPageTextTool(),
    ]

    impact_tools = [
        ClimateImpactDatabaseTool(),
        GovernmentSourceSearchTool(),
        SemanticScholarSearchTool(),
        FetchPageTextTool(),
    ]

    budget_tools = [
        BudgetBenchmarkTool(),
        GovernmentSourceSearchTool(),
    ]

    team_tools = [
        AuthorPublicationsTool(),
        OrganizationVerifierTool(),
        SemanticScholarSearchTool(),
        FetchPageTextTool(),
    ]

    criteria_tools = [
        ResearchContextRetrieverTool(),
        ClimateImpactDatabaseTool(),
        SimilarProjectFinderTool(),
        GovernmentSourceSearchTool(),
        SemanticScholarSearchTool(),
    ]

    # ---------------------------
    # Agent 1: Proposal Parser
    # ---------------------------

    proposal_parser = Agent(
        role="Proposal Ingestion Specialist",
        goal="Parse and structure the uploaded grant proposal into analyzable components for downstream analysts",
        backstory="""You are an expert document analyst with 15+ years of experience processing
grant proposals for major foundations and government agencies. You excel at:
- Extracting key sections from varied proposal formats
- Identifying claims, metrics, and commitments that require verification
- Structuring unstructured content for systematic analysis
- Flagging missing or incomplete sections

Your output provides the foundation for all other analysts. Be thorough and precise.""",
        llm=llm,
        verbose=True,
        max_iter=8,
        max_retry_limit=2,
    )

    # ---------------------------
    # Agent 2: Technical Feasibility Analyst
    # ---------------------------

    technical_analyst = Agent(
        role="Technical Feasibility Analyst",
        goal="Evaluate whether the proposed technical approach is achievable, sound, and based on established science",
        backstory="""You are a senior technical reviewer with a PhD in Computer Science and 20+ years
evaluating AI/ML research proposals. Your expertise spans:
- Machine learning and AI systems architecture
- Climate modeling and environmental technology
- Technical risk assessment methodologies
- Technology Readiness Level (TRL) evaluation

You rigorously assess technical claims against peer-reviewed literature. You are known for:
- Finding prior art that applicants may have missed
- Identifying technical risks that could derail projects
- Distinguishing proven technology from aspirational claims
- Never overstating feasibility when evidence is lacking""",
        llm=llm,
        verbose=True,
        tools=technical_tools,
        max_iter=12,
        max_retry_limit=2,
    )

    # ---------------------------
    # Agent 3: Innovation/Novelty Researcher
    # ---------------------------

    innovation_researcher = Agent(
        role="Innovation & Novelty Researcher",
        goal="Assess the true novelty of the proposal compared to existing solutions and state-of-the-art research",
        backstory="""You are a technology scout specializing in AI for climate innovation with experience at
leading climate tech VCs and research foundations. Your expertise includes:
- Tracking cutting-edge research in AI for sustainability
- Patent landscape analysis and IP due diligence
- Competitive intelligence for climate tech
- Identifying incremental vs. breakthrough innovation

You maintain healthy skepticism about novelty claims. You've seen many proposals claim to be
"first ever" when similar work exists. You are meticulous about finding comparable projects
and assessing true differentiation.""",
        llm=llm,
        verbose=True,
        tools=innovation_tools,
        max_iter=12,
        max_retry_limit=2,
    )

    # ---------------------------
    # Agent 4: Climate Impact Specialist
    # ---------------------------

    impact_specialist = Agent(
        role="Climate & Nature Impact Specialist",
        goal="Evaluate the potential environmental impact and verify impact claims against established data",
        backstory="""You are an environmental impact analyst with expertise in climate science and
impact measurement frameworks. Your background includes:
- Climate change mitigation and adaptation assessment
- Nature-based solutions evaluation
- SDG (Sustainable Development Goals) alignment analysis
- Impact measurement (IRIS+, GHG Protocol, Science Based Targets)

You critically distinguish between aspirational claims and evidence-based projections.
You reference authoritative sources like IPCC, Project Drawdown, and IEA. You flag impact
claims that seem implausible based on physical or biological constraints.""",
        llm=llm,
        verbose=True,
        tools=impact_tools,
        max_iter=10,
        max_retry_limit=2,
    )

    # ---------------------------
    # Agent 5: Budget/Financial Reviewer
    # ---------------------------

    budget_reviewer = Agent(
        role="Financial & Budget Analyst",
        goal="Evaluate budget reasonableness against industry benchmarks and identify financial red flags",
        backstory="""You are a financial analyst specializing in grant and research project budgets
with experience at major foundations and government agencies. Your expertise includes:
- AI/ML project cost benchmarking
- Climate tech funding patterns and typical budgets
- Resource allocation analysis
- Cost-benefit assessment for research projects

You compare budgets against industry benchmarks and flag significant deviations. You identify
common red flags like excessive overhead, missing contingency, or unrealistic personnel costs.""",
        llm=llm,
        verbose=True,
        tools=budget_tools,
        max_iter=7,
        max_retry_limit=2,
    )

    # ---------------------------
    # Agent 6: Team Credibility Verifier
    # ---------------------------

    team_verifier = Agent(
        role="Team Credibility & Track Record Verifier",
        goal="Verify team credentials, publication records, and organizational track record",
        backstory="""You are a due diligence specialist focusing on team assessment for
grant applications and venture investments. Your expertise includes:
- Academic credential verification
- Publication and citation analysis
- Professional background investigation
- Organizational track record assessment

You cross-reference claimed credentials with public records. You are thorough in checking
publication records, institutional affiliations, and prior project outcomes. You flag
discrepancies and unverifiable claims.""",
        llm=llm,
        verbose=True,
        tools=team_tools,
        max_iter=10,
        max_retry_limit=2,
    )

    # ---------------------------
    # Agent 7: BEF Criteria Evaluator
    # ---------------------------

    bef_criteria_evaluator = Agent(
        role="BEF Strategic Investment Analyst",
        goal="Evaluate proposal against Bezos Earth Fund's 9 investment criteria to assess strategic fit and provide executive recommendations",
        backstory="""You are a senior strategic analyst at the Bezos Earth Fund with deep understanding
of our investment philosophy and grantmaking criteria. You have reviewed hundreds of proposals
and understand how to evaluate strategic alignment across BEF's 9 investment criteria:

WHY SHOULD WE DO THIS?
1. Impact Potential - Could this make substantial impact on climate/nature outcomes?
2. Transformational Nature - Is this transformational vs incremental?
3. Organizational Efficiency - Does this organization get things done efficiently?

WHY US?
4. Additionality - Will this happen without BEF? Are we leading, not following?
5. Leverage BEF Advantages - Does it leverage our financial scale, convening power, risk tolerance?
6. Brand Alignment - Will we be recognized positively? Does it build our brand?

WHY NOW?
7. Timing - Is now the right time? Is there societal will?
8. Sustainability - How will this be sustained after our support ends?
9. Learning & Improvement - Is this smarter than our last investment?

You provide clear, actionable guidance for executives making funding decisions. You are direct
about strategic misalignment and opportunity costs. Your assessments help BEF maximize impact
with limited resources.""",
        llm=llm,
        verbose=True,
        tools=criteria_tools,
        max_iter=12,
        max_retry_limit=2,
    )

    # ---------------------------
    # Synthesis Agent (Report Generator)
    # ---------------------------

    synthesis_agent = Agent(
        role="Senior Program Analyst",
        goal="Synthesize all assessment reports into a comprehensive Report Card with clear funding recommendation",
        backstory="""You are a senior program analyst at a major climate foundation with responsibility
for final funding recommendations. You have reviewed thousands of proposals and excel at:
- Synthesizing complex multi-dimensional assessments
- Calibrating recommendations to evidence strength
- Identifying the most critical questions for follow-up
- Communicating findings clearly to program leadership

Your Report Cards are known for being fair, thorough, and actionable. You never recommend
funding without addressing concerns, and you provide specific questions for applicant interviews.""",
        llm=llm,
        verbose=True,
        max_iter=6,
        max_retry_limit=2,
    )

    # ---------------------------
    # Define Tasks
    # ---------------------------

    # Task 1: Parse the proposal
    parse_task = Task(
        description=f"""
{PROPOSAL_PARSER_PROMPT}

---

## PROPOSAL TO PARSE

{proposal_text}

---

## Additional Context (if available)
- Organization: {org_name}
- Requested Budget: ${budget_amount:,.0f} (if known)
- Project Duration: {duration_months} months (if known)
{user_context_section}{research_context_section}
Extract all structured information and identify key claims for verification.
""",
        expected_output="""Structured proposal data including:
- Basic info (title, org, team)
- Project content (problem, solution, approach)
- Impact claims and metrics
- Timeline and milestones
- Budget breakdown
- Key claims for verification (technical, impact, team, partnership)""",
        agent=proposal_parser,
    )

    # Build list of analysis tasks that depend on parsing
    analysis_tasks = []

    # Task 2: Technical Analysis (if enabled)
    if "technical" in analyses_to_run:
        technical_task = Task(
            description=f"""
{TECHNICAL_ANALYSIS_PROMPT}

---

## Your Mission
Analyze the technical feasibility of the proposal parsed above. Use your tools to:
1. Search for prior art in academic literature
2. Check patent landscape
3. Verify technical claims against published research
4. Assess technology readiness level

Provide a Technical Soundness Score (1-10) with detailed justification.
""",
            expected_output="""Technical assessment including:
- Technical Soundness Score (1-10)
- TRL Assessment (1-9)
- Prior Art Summary
- Technical Risks ranked by severity
- Key Technical Concerns
- Strengths of the approach
- Evidence citations""",
            agent=technical_analyst,
            context=[parse_task],
        )
        analysis_tasks.append(technical_task)

    # Task 3: Innovation Analysis (if enabled)
    if "innovation" in analyses_to_run:
        innovation_task = Task(
            description=f"""
{INNOVATION_ANALYSIS_PROMPT}

---

## Your Mission
Assess the true novelty of this proposal. Use your tools to:
1. Find similar funded projects in climate/AI space
2. Search patent databases for prior art
3. Compare against academic state-of-the-art
4. Evaluate competitive differentiation

Provide a Novelty Score (1-10) with detailed justification.
""",
            expected_output="""Innovation assessment including:
- Novelty Score (1-10)
- Innovation Type classification
- Similar Projects found
- Competitive Differentiation analysis
- Patent Landscape assessment
- Key Strengths in innovation
- Key Concerns about novelty""",
            agent=innovation_researcher,
            context=[parse_task],
        )
        analysis_tasks.append(innovation_task)

    # Task 4: Impact Analysis (if enabled)
    if "impact" in analyses_to_run:
        impact_task = Task(
            description=f"""
{IMPACT_ANALYSIS_PROMPT}

---

## Your Mission
Evaluate the climate/nature impact potential. Use your tools to:
1. Search climate impact databases for benchmark metrics
2. Verify impact claims against authoritative sources
3. Assess SDG alignment
4. Evaluate scalability of impact

Provide an Impact Potential Score (1-10) with detailed justification.
""",
            expected_output="""Impact assessment including:
- Impact Potential Score (1-10)
- SDG Alignment list
- Verified Impact Metrics
- Unverified Claims
- Scalability Assessment
- Co-Benefits and Risks
- Comparison to similar projects""",
            agent=impact_specialist,
            context=[parse_task],
        )
        analysis_tasks.append(impact_task)

    # Task 5: Budget Analysis (if enabled)
    if "budget" in analyses_to_run:
        budget_task = Task(
            description=f"""
{BUDGET_ANALYSIS_PROMPT}

---

## Your Mission
Evaluate the budget reasonableness. Use your tools to:
1. Compare against industry benchmarks for similar project types
2. Analyze budget allocation across categories
3. Identify red flags or unusual patterns
4. Assess cost-effectiveness

## Budget Context
- Total Budget: ${budget_amount:,.0f}
- Duration: {duration_months} months
- Estimated Team Size: {team_size}

Provide a Budget Reasonableness Score (1-10) with detailed justification.
""",
            expected_output="""Budget assessment including:
- Budget Reasonableness Score (1-10)
- Benchmark Comparison results
- Red Flags identified
- Cost-Effectiveness assessment
- Sustainability concerns
- Budget Strengths
- Questions for the applicant""",
            agent=budget_reviewer,
            context=[parse_task],
        )
        analysis_tasks.append(budget_task)

    # Task 6: Team Verification (if enabled)
    if "team" in analyses_to_run:
        team_task = Task(
            description=f"""
{TEAM_VERIFICATION_PROMPT}

---

## Your Mission
Verify team credentials and track record. Use your tools to:
1. Search for publication records of key team members
2. Verify organizational legitimacy
3. Check for prior project track record
4. Assess capability gaps

Provide a Team Credibility Score (1-10) with detailed justification.
""",
            expected_output="""Team assessment including:
- Team Credibility Score (1-10)
- Individual Verifications for each team member
- Publication/Research Record summary
- Organization Assessment
- Verified Partnerships
- Unverified Claims
- Capability Gaps
- Recommended Questions""",
            agent=team_verifier,
            context=[parse_task],
        )
        analysis_tasks.append(team_task)

    # Task 7: BEF Criteria Evaluation (if enabled)
    if "criteria" in analyses_to_run:
        criteria_task = Task(
            description=f"""
{BEF_CRITERIA_PROMPT}

---

## Your Mission
Evaluate this proposal against Bezos Earth Fund's 9 investment criteria. Use your tools to:
1. Retrieve relevant research context from the knowledge base
2. Search for similar funded projects to assess additionality
3. Find climate impact benchmarks to validate claims
4. Assess strategic fit with BEF's mission and advantages

## Proposal Context
- Organization: {org_name}
- Budget: ${budget_amount:,.0f}
- Duration: {duration_months} months

For each of the 9 criteria, provide:
- Score (1-10)
- Traffic Light (GREEN/YELLOW/RED)
- Justification with evidence

Calculate category averages and overall Strategic Fit Score.
Provide Executive Summary and Key Recommendations for leadership.
""",
            expected_output="""BEF Criteria Assessment including:
- WHY SHOULD WE DO THIS? (3 criteria with scores)
  - Impact Potential Score
  - Transformational Nature Score
  - Organizational Efficiency Score
  - Category Average

- WHY US? (3 criteria with scores)
  - Additionality Score
  - Leverage BEF Advantages Score
  - Brand Alignment Score
  - Category Average

- WHY NOW? (3 criteria with scores)
  - Timing Score
  - Sustainability Score
  - Learning & Improvement Score
  - Category Average

- Overall Strategic Fit Score (1-10)
- Executive Summary
- Key Recommendations for leadership
- Critical Questions for decision-makers""",
            agent=bef_criteria_evaluator,
            context=[parse_task],
        )
        analysis_tasks.append(criteria_task)

    # Task 8: Synthesis (always runs)
    synthesis_task = Task(
        description=f"""
{SYNTHESIS_PROMPT}

---

## Your Mission
Synthesize all the assessment reports above into a comprehensive Report Card.

Create:
1. Summary Scores table with traffic lights (include Strategic Fit if BEF Criteria evaluation was run)
2. Verification Status summary
3. Strategic Fit Assessment (if BEF Criteria evaluation was run):
   - WHY SHOULD WE DO THIS? category score
   - WHY US? category score
   - WHY NOW? category score
   - Overall Strategic Fit score
4. Top 3 Strengths (verified)
5. Top 3 Concerns (verified)
6. Unverified Claims requiring follow-up
7. Executive Recommendations for leadership
8. Final Recommendation (FUND / FUND WITH CONDITIONS / REQUEST REVISION / DECLINE)
9. Interview Questions for program lead organized by category

## Proposal Context
- Title: (from parsed data)
- Organization: {org_name}
- Budget: ${budget_amount:,.0f}
- Duration: {duration_months} months

Be direct about concerns - this informs funding decisions for climate action.
Include Strategic Fit analysis prominently if the BEF Criteria Evaluation was performed.
""",
        expected_output="""Complete Report Card including:
- Executive Summary (TL;DR)
- Scores Table with grades and traffic lights (6 dimensions if Strategic Fit included)
- Strategic Fit Assessment with category breakdowns (if criteria evaluation run)
- Verification Status Summary
- Key Strengths with evidence
- Key Concerns with evidence
- Unverified Claims
- Executive Recommendations (actionable guidance for leadership)
- Final Recommendation with conditions
- Interview Questions by category (Technical, Team, Impact, Budget, Strategic Fit, Red Flags)""",
        agent=synthesis_agent,
        context=[parse_task] + analysis_tasks,
    )

    # ---------------------------
    # Build and Return Crew
    # ---------------------------

    all_agents = [proposal_parser]
    all_tasks = [parse_task]

    # Add analysis agents and tasks based on what's enabled
    if "technical" in analyses_to_run:
        all_agents.append(technical_analyst)
    if "innovation" in analyses_to_run:
        all_agents.append(innovation_researcher)
    if "impact" in analyses_to_run:
        all_agents.append(impact_specialist)
    if "budget" in analyses_to_run:
        all_agents.append(budget_reviewer)
    if "team" in analyses_to_run:
        all_agents.append(team_verifier)
    if "criteria" in analyses_to_run:
        all_agents.append(bef_criteria_evaluator)

    all_tasks.extend(analysis_tasks)
    all_agents.append(synthesis_agent)
    all_tasks.append(synthesis_task)

    crew = Crew(
        agents=all_agents,
        tasks=all_tasks,
        verbose=True,
    )

    return crew, tracer


# ---------------------------
# Legacy function for backward compatibility
# ---------------------------

def build_crew(
    topic: str,
    urls: Optional[List[str]] = None,
    llm_model: str = "anthropic/claude-opus-4-5-20251101",
    user_documents: Optional[List[Dict]] = None
) -> Crew:
    """
    Legacy function maintained for backward compatibility.
    Wraps the new proposal analysis crew for research topics.
    Returns only the Crew (not the tracer) for backward compatibility.
    """
    # Build proposal text from topic and documents
    proposal_text = f"# Research Topic\n\n{topic}\n"

    if user_documents:
        proposal_text += "\n\n# Provided Documents\n\n"
        for doc in user_documents:
            proposal_text += f"## {doc.get('filename', 'Document')}\n"
            proposal_text += f"{doc.get('content', '')[:20000]}\n\n"

    if urls:
        proposal_text += "\n\n# Reference URLs\n\n"
        for url in urls:
            proposal_text += f"- {url}\n"

    crew, _ = build_proposal_analysis_crew(
        proposal_text=proposal_text,
        llm_model=llm_model,
        enable_tracing=False,  # Disable tracing for legacy usage
    )
    return crew

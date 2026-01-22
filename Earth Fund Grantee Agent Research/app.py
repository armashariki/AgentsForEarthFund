"""
Grant Proposal Analyzer - Streamlit UI

AI-powered analysis system for grant proposals focused on AI for Climate and Nature.
Uses 7 specialized AI agents to analyze, verify, and assess proposals,
generating comprehensive Report Cards with funding recommendations.

Includes BEF Investment Criteria Evaluation for strategic alignment assessment.

Copyright (c) 2024 Bezos Earth Fund
All rights reserved.
"""

import os
import time
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from src.crew import build_proposal_analysis_crew
from src.tools import write_file, process_uploaded_files, clear_tool_cache
from src.report_generator import parse_crew_output_to_report_card, generate_full_report
from src.tracing import ExecutionTracer, create_tracer_from_crew_output
from src.research_import import ResearchContextImporter, get_default_research_folder

# Load .env from project root
ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")


# ---------------------------
# LLM Provider Configuration
# ---------------------------
LLM_PROVIDERS = {
    "Claude (Opus 4.5)": {
        "model": "anthropic/claude-opus-4-5-20251101",
        "env_key": "ANTHROPIC_API_KEY",
        "description": "Anthropic's most capable model"
    },
    "ChatGPT (GPT-4o)": {
        "model": "openai/gpt-4o",
        "env_key": "OPENAI_API_KEY",
        "description": "OpenAI's flagship model"
    },
    "Gemini (2.0 Flash)": {
        "model": "google/gemini-2.0-flash",
        "env_key": "GOOGLE_API_KEY",
        "description": "Google's fast multimodal model"
    },
    "Grok": {
        "model": "xai/grok-4",
        "env_key": "XAI_API_KEY",
        "description": "xAI's conversational model"
    },
}


# ---------------------------
# Helper Functions
# ---------------------------
def strip_markdown_fences(text: str) -> str:
    """Remove markdown code fences for proper rendering."""
    if not text:
        return text

    t = text.strip()
    if t.startswith("```"):
        lines = t.splitlines()
        lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        t = "\n".join(lines).strip()
    return t


def check_api_key(env_key: str) -> bool:
    """Check if an API key is configured and not a placeholder."""
    key = os.getenv(env_key, "")
    if not key:
        return False
    placeholders = ["your-", "sk-xxx", "placeholder", "api-key-here"]
    return not any(p in key.lower() for p in placeholders)


# ---------------------------
# Page Configuration
# ---------------------------
st.set_page_config(
    page_title="Grant Proposal Analyzer",
    page_icon="🌍",
    layout="wide",
)

# ---------------------------
# Custom CSS Theme
# ---------------------------
st.markdown(
    """
    <style>
      /* Remove Streamlit chrome */
      header[data-testid="stHeader"] { height: 0rem; background: transparent; }
      div[data-testid="stToolbar"] { visibility: hidden; height: 0; }
      div[data-testid="stDecoration"] { visibility: hidden; height: 0; }
      #MainMenu { visibility: hidden; }
      footer { visibility: hidden; }

      /* Page background */
      .stApp {
        background: linear-gradient(180deg, #ecfdf5 0%, #f0fdf4 50%, #f8fafc 100%);
        color: #1e293b;
      }

      .block-container { padding-top: 1rem; padding-bottom: 2rem; }

      h1, h2, h3, h4 { color: #064e3b; }

      .subtitle {
        font-size: 1.1rem;
        color: #047857;
        margin-top: -0.5rem;
        margin-bottom: 1rem;
      }

      .badge {
        display: inline-block;
        padding: 0.35rem 0.85rem;
        border-radius: 999px;
        font-size: 0.85rem;
        font-weight: 600;
        background: linear-gradient(90deg, #059669, #0d9488);
        color: #ffffff;
        margin-bottom: 0.75rem;
      }

      .card {
        background: #ffffff;
        border: 1px solid #d1fae5;
        border-radius: 12px;
        padding: 20px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.04), 0 1px 2px rgba(0,0,0,0.02);
        margin-bottom: 16px;
      }

      .card-header {
        font-size: 0.85rem;
        font-weight: 600;
        color: #047857;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 12px;
        padding-bottom: 8px;
        border-bottom: 1px solid #d1fae5;
      }

      .hint {
        font-size: 0.9rem;
        color: #6b7280;
        margin-top: 4px;
      }

      /* Input styling */
      .stTextInput > div > div,
      .stTextArea > div > div,
      .stSelectbox > div > div,
      .stNumberInput > div > div {
        background: #ffffff !important;
        border-radius: 8px !important;
        border: 1px solid #d1fae5 !important;
      }

      .stTextInput > div > div:focus-within,
      .stTextArea > div > div:focus-within,
      .stSelectbox > div > div:focus-within {
        border-color: #059669 !important;
        box-shadow: 0 0 0 2px rgba(5, 150, 105, 0.1) !important;
      }

      /* Primary button */
      .stButton > button {
        background: linear-gradient(90deg, #059669, #0d9488) !important;
        color: white !important;
        border: 0 !important;
        border-radius: 8px !important;
        padding: 0.65rem 1.5rem !important;
        font-weight: 600 !important;
        width: 100%;
        transition: all 0.2s ease;
      }
      .stButton > button:hover {
        filter: brightness(1.05);
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(5, 150, 105, 0.3);
      }

      /* Status indicators */
      .status-ok {
        background: #ecfdf5;
        border: 1px solid #a7f3d0;
        padding: 12px 16px;
        border-radius: 8px;
        color: #047857;
        font-size: 0.9rem;
      }
      .status-warning {
        background: #fffbeb;
        border: 1px solid #fcd34d;
        padding: 12px 16px;
        border-radius: 8px;
        color: #b45309;
        font-size: 0.9rem;
      }
      .status-error {
        background: #fef2f2;
        border: 1px solid #fca5a5;
        padding: 12px 16px;
        border-radius: 8px;
        color: #b91c1c;
        font-size: 0.9rem;
      }

      /* API key badges */
      .key-ok {
        display: inline-block;
        background: #d1fae5;
        color: #047857;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 0.75rem;
        font-weight: 500;
      }
      .key-missing {
        display: inline-block;
        background: #fee2e2;
        color: #b91c1c;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 0.75rem;
        font-weight: 500;
      }

      /* File uploader */
      .stFileUploader > div {
        background: #f0fdf4 !important;
        border: 2px dashed #a7f3d0 !important;
        border-radius: 8px !important;
      }
      .stFileUploader > div:hover {
        border-color: #059669 !important;
        background: #ecfdf5 !important;
      }

      /* Checkbox styling */
      .stCheckbox > label {
        color: #1e293b;
      }

      /* Tabs styling */
      .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
      }
      .stTabs [data-baseweb="tab"] {
        background: #f0fdf4;
        border-radius: 8px 8px 0 0;
        padding: 8px 16px;
        color: #047857;
      }
      .stTabs [aria-selected="true"] {
        background: #059669 !important;
        color: white !important;
      }

      /* Progress bar */
      .stProgress > div > div {
        background: linear-gradient(90deg, #059669, #0d9488) !important;
      }

      /* Download button */
      .stDownloadButton > button {
        background: #ffffff !important;
        color: #059669 !important;
        border: 1px solid #059669 !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
      }
      .stDownloadButton > button:hover {
        background: #ecfdf5 !important;
      }

      code, pre {
        background: #f0fdf4 !important;
        border-radius: 6px !important;
        border: 1px solid #d1fae5 !important;
      }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------
# Header
# ---------------------------
st.markdown("<span class='badge'>Grant Proposal Analyzer</span>", unsafe_allow_html=True)
st.title("AI for Climate & Nature")
st.markdown(
    "<div class='subtitle'>Upload a grant proposal for comprehensive AI-powered analysis. "
    "Our 7 specialized agents verify claims, assess feasibility, evaluate strategic fit, and generate actionable recommendations.</div>",
    unsafe_allow_html=True,
)

# ---------------------------
# Initialize Session State
# ---------------------------
if "analysis_complete" not in st.session_state:
    st.session_state.analysis_complete = False
if "analysis_result" not in st.session_state:
    st.session_state.analysis_result = None
if "report_card" not in st.session_state:
    st.session_state.report_card = None
if "execution_trace" not in st.session_state:
    st.session_state.execution_trace = None
if "research_context_used" not in st.session_state:
    st.session_state.research_context_used = None
if "analysis_start_time" not in st.session_state:
    st.session_state.analysis_start_time = None
if "analysis_duration" not in st.session_state:
    st.session_state.analysis_duration = None

# ---------------------------
# Layout: Left Panel (Config) | Right Panel (Results)
# ---------------------------
left, right = st.columns([1, 1.4], gap="large")

with left:
    # --- Model Configuration Card ---
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("<div class='card-header'>Model Configuration</div>", unsafe_allow_html=True)

    selected_llm_name = st.selectbox(
        "Select AI Model",
        options=list(LLM_PROVIDERS.keys()),
        index=0,
        help="Choose the language model for analysis agents"
    )

    selected_provider = LLM_PROVIDERS[selected_llm_name]
    api_key_configured = check_api_key(selected_provider["env_key"])

    if api_key_configured:
        st.markdown(
            f"<span class='key-ok'>API Key Configured</span> "
            f"<span class='hint'>{selected_provider['description']}</span>",
            unsafe_allow_html=True
        )
    else:
        st.markdown(
            f"<span class='key-missing'>API Key Missing</span> "
            f"<span class='hint'>Add {selected_provider['env_key']} to .env file</span>",
            unsafe_allow_html=True
        )

    st.markdown("</div>", unsafe_allow_html=True)

    # --- Proposal Upload Card ---
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("<div class='card-header'>Upload Proposal</div>", unsafe_allow_html=True)

    st.markdown(
        "<div class='hint'>Upload the grant proposal document for analysis. "
        "Supported formats: PDF, TXT, Markdown</div>",
        unsafe_allow_html=True
    )

    uploaded_file = st.file_uploader(
        "Drop proposal here or click to browse",
        type=["pdf", "txt", "md"],
        accept_multiple_files=False,
        label_visibility="collapsed"
    )

    if uploaded_file:
        file_size = len(uploaded_file.getvalue()) / 1024
        st.markdown(f"**Selected:** {uploaded_file.name} ({file_size:.1f} KB)")

    st.markdown("</div>", unsafe_allow_html=True)

    # --- Proposal Metadata Card ---
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("<div class='card-header'>Proposal Details (Optional)</div>", unsafe_allow_html=True)

    org_name = st.text_input(
        "Organization Name",
        value="",
        placeholder="e.g., Climate AI Research Institute",
        help="Name of the applicant organization"
    )

    col1, col2 = st.columns(2)
    with col1:
        budget_amount = st.number_input(
            "Funding Requested ($)",
            min_value=0,
            max_value=100_000_000,
            value=0,
            step=50000,
            help="Total funding amount requested"
        )
    with col2:
        duration_months = st.selectbox(
            "Project Duration",
            options=[6, 12, 18, 24, 36, 48],
            index=2,
            help="Project duration in months"
        )

    team_size = st.slider(
        "Estimated Team Size",
        min_value=1,
        max_value=50,
        value=5,
        help="Approximate number of team members"
    )

    st.markdown("---", unsafe_allow_html=False)
    st.markdown("<div class='hint'><b>Additional Context:</b></div>", unsafe_allow_html=True)
    user_context = st.text_area(
        "Provide additional details or context",
        value="",
        height=120,
        placeholder="Add any relevant context about this proposal that may not be in the document itself. For example:\n- Prior relationship with the organization\n- Specific concerns or areas to focus on\n- Related initiatives or competing proposals\n- Internal notes or background information",
        help="This context will be shared with all analysis agents to inform their evaluation"
    )

    st.markdown("</div>", unsafe_allow_html=True)

    # --- Analysis Configuration Card ---
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("<div class='card-header'>Analysis Options</div>", unsafe_allow_html=True)

    st.markdown("<div class='hint'>Select which analyses to run:</div>", unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        run_technical = st.checkbox("Technical Feasibility", value=True)
        run_innovation = st.checkbox("Innovation/Novelty", value=True)
        run_impact = st.checkbox("Climate Impact", value=True)
    with col2:
        run_budget = st.checkbox("Budget Review", value=True)
        run_team = st.checkbox("Team Verification", value=True)

    st.markdown("---", unsafe_allow_html=False)
    st.markdown("<div class='hint'><b>Strategic Assessment:</b></div>", unsafe_allow_html=True)
    run_criteria = st.checkbox(
        "BEF Investment Criteria (9 criteria)",
        value=True,
        help="Evaluate proposal against Bezos Earth Fund's 9 investment criteria: Why Do This, Why Us, Why Now"
    )

    st.markdown("---", unsafe_allow_html=False)
    st.markdown("<div class='hint'><b>Execution Tracing:</b></div>", unsafe_allow_html=True)
    enable_tracing = st.checkbox(
        "Generate Execution Trace",
        value=True,
        help="Create a stakeholder-friendly report showing how agents reached their conclusions"
    )

    st.markdown("</div>", unsafe_allow_html=True)

    # --- Research Context Import Card ---
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("<div class='card-header'>Research Context (Optional)</div>", unsafe_allow_html=True)

    use_research_context = st.checkbox(
        "Import Research Assistant outputs",
        value=False,
        help="Include findings from prior research to inform the analysis"
    )

    selected_research_reports = []
    research_context_text = None

    if use_research_context:
        default_folder = get_default_research_folder()
        research_folder = st.text_input(
            "Research Output Folder",
            value=default_folder,
            help="Path to the Research Assistant Agent output folder"
        )

        if os.path.isdir(research_folder):
            importer = ResearchContextImporter(research_folder)
            available_reports = importer.list_available_reports()

            if available_reports:
                report_options = [r["filename"] for r in available_reports]
                selected_research_reports = st.multiselect(
                    "Select Research Reports",
                    options=report_options,
                    help="Choose which research reports to include as context"
                )

                if selected_research_reports:
                    st.markdown(f"<div class='hint'>Selected {len(selected_research_reports)} report(s)</div>", unsafe_allow_html=True)
            else:
                st.markdown("<div class='hint' style='color:#b45309;'>No research reports found in folder</div>", unsafe_allow_html=True)
        else:
            st.markdown("<div class='hint' style='color:#b91c1c;'>Folder not found</div>", unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

    # --- Run Analysis Button ---
    st.markdown("<div style='height: 8px'></div>", unsafe_allow_html=True)
    run_btn = st.button("Analyze Proposal", use_container_width=True)


with right:
    # --- Results Panel ---
    st.markdown("<div class='card' style='min-height: 600px;'>", unsafe_allow_html=True)
    st.markdown("<div class='card-header'>Analysis Results</div>", unsafe_allow_html=True)

    if st.session_state.analysis_complete and st.session_state.analysis_result:
        # Display analysis duration prominently
        if st.session_state.analysis_duration:
            duration_mins = int(st.session_state.analysis_duration // 60)
            duration_secs = int(st.session_state.analysis_duration % 60)
            st.markdown(
                f"<div style='background:#ecfdf5;border:1px solid #a7f3d0;"
                f"border-radius:8px;padding:12px;margin-bottom:16px;"
                f"display:flex;align-items:center;gap:12px;'>"
                f"<span style='font-size:1.5rem;'>&#9201;</span>"
                f"<div><span style='font-weight:600;color:#047857;'>Analysis Complete</span><br/>"
                f"<span style='color:#059669;font-size:1.1rem;'>Total time: {duration_mins}m {duration_secs}s</span>"
                f"</div></div>",
                unsafe_allow_html=True
            )

        # Show results in tabs
        tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
            "Executive Summary",
            "Report Card",
            "Strategic Fit",
            "Execution Trace",
            "Deep Dive",
            "Interview Questions"
        ])

        result_text = st.session_state.analysis_result

        with tab1:
            st.markdown("### Executive Decision Brief")
            st.markdown(
                "*Quick summary for leadership decision-making.*"
            )
            # Extract key sections for executive view
            st.markdown(result_text)

        with tab2:
            st.markdown("### Proposal Report Card")
            st.markdown(
                "*Detailed scores with traffic lights and recommendations.*"
            )
            st.markdown(result_text)

        with tab3:
            st.markdown("### Strategic Fit Assessment")
            st.markdown(
                "*Evaluation against Bezos Earth Fund's 9 Investment Criteria*"
            )
            st.markdown("---")
            st.markdown("""
**BEF Investment Criteria Framework:**

| Category | Criteria |
|----------|----------|
| **WHY SHOULD WE DO THIS?** | Impact Potential, Transformational Nature, Organizational Efficiency |
| **WHY US?** | Additionality, Leverage BEF Advantages, Brand Alignment |
| **WHY NOW?** | Timing, Sustainability, Learning & Improvement |

---
            """)
            st.markdown(result_text)

        with tab4:
            st.markdown("### Analysis Execution Trace")
            st.markdown("*How the agents reached their conclusions*")
            st.markdown("---")

            if st.session_state.get("execution_trace"):
                st.markdown(st.session_state.execution_trace)

                # Download button for trace
                st.download_button(
                    label="Download Trace Report",
                    data=st.session_state.execution_trace.encode("utf-8"),
                    file_name="execution_trace.md",
                    mime="text/markdown",
                )
            else:
                st.markdown(
                    "<div style='color: #6b7280; text-align: center; padding: 50px 20px;'>"
                    "<p>Execution tracing was not enabled for this analysis.</p>"
                    "<p style='font-size: 0.9rem;'>Enable 'Generate Execution Trace' in Analysis Options to capture agent decision-making details.</p>"
                    "</div>",
                    unsafe_allow_html=True
                )

            # Show research context if used
            if st.session_state.get("research_context_used"):
                st.markdown("---")
                st.markdown("### Research Context Included")
                st.markdown("*The following research reports were used to inform the analysis:*")
                st.markdown(st.session_state.research_context_used)

        with tab5:
            st.markdown("### Deep Dive Analysis")
            with st.expander("Full Analysis Output", expanded=True):
                st.markdown(result_text)

        with tab6:
            st.markdown("### Interview Questions")
            st.markdown(
                "Based on the analysis, consider asking the applicant:\n\n"
                "**Technical & Feasibility:**\n"
                "1. Can you provide documentation for any unverified claims?\n"
                "2. What is your contingency plan if the primary approach doesn't work?\n\n"
                "**Impact & Metrics:**\n"
                "3. How did you calculate your impact projections?\n"
                "4. How will you measure success at key milestones?\n\n"
                "**Strategic Fit (BEF Criteria):**\n"
                "5. Will this initiative continue without BEF support? (Additionality)\n"
                "6. How will this be sustained after our funding ends? (Sustainability)\n"
                "7. What makes now the right time for this investment? (Timing)\n"
            )

        # Export buttons
        st.markdown("---")
        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                label="Download Report (Markdown)",
                data=result_text.encode("utf-8"),
                file_name="proposal_analysis_report.md",
                mime="text/markdown",
            )
        with col2:
            st.download_button(
                label="Download Report (TXT)",
                data=result_text.encode("utf-8"),
                file_name="proposal_analysis_report.txt",
                mime="text/plain",
            )

    else:
        st.markdown(
            "<div style='color: #6b7280; text-align: center; padding: 150px 20px;'>"
            "<p style='font-size: 1.2rem;'>Upload a proposal and click 'Analyze Proposal' to begin.</p>"
            "<p style='font-size: 0.9rem;'>Analysis typically takes 5-15 minutes depending on proposal length.</p>"
            "</div>",
            unsafe_allow_html=True
        )

    st.markdown("</div>", unsafe_allow_html=True)


# ---------------------------
# Run Analysis Logic
# ---------------------------
if run_btn:
    # Validation
    if not uploaded_file:
        st.markdown(
            "<div class='status-error'>Please upload a proposal document.</div>",
            unsafe_allow_html=True
        )
        st.stop()

    if not check_api_key(selected_provider["env_key"]):
        st.markdown(
            f"<div class='status-error'>API key not configured for {selected_llm_name}. "
            f"Please add {selected_provider['env_key']} to your .env file.</div>",
            unsafe_allow_html=True
        )
        st.stop()

    # Build analyses list
    analyses_to_run = []
    if run_technical:
        analyses_to_run.append("technical")
    if run_innovation:
        analyses_to_run.append("innovation")
    if run_impact:
        analyses_to_run.append("impact")
    if run_budget:
        analyses_to_run.append("budget")
    if run_team:
        analyses_to_run.append("team")
    if run_criteria:
        analyses_to_run.append("criteria")

    if not analyses_to_run:
        st.markdown(
            "<div class='status-warning'>Please select at least one analysis type.</div>",
            unsafe_allow_html=True
        )
        st.stop()

    # Process uploaded file
    with st.spinner("Processing proposal document..."):
        processed_docs = process_uploaded_files([uploaded_file])
        if not processed_docs:
            st.markdown(
                "<div class='status-error'>Failed to process the uploaded document.</div>",
                unsafe_allow_html=True
            )
            st.stop()

        proposal_text = processed_docs[0].get("content", "")
        if not proposal_text.strip():
            st.markdown(
                "<div class='status-error'>Could not extract text from the document.</div>",
                unsafe_allow_html=True
            )
            st.stop()

    st.markdown(
        f"<div class='status-ok'>Proposal loaded: {len(proposal_text):,} characters extracted.</div>",
        unsafe_allow_html=True
    )

    # Build metadata
    proposal_metadata = {
        "organization": org_name or "Unknown Organization",
        "budget_amount": budget_amount,
        "duration_months": duration_months,
        "team_size": team_size,
        "title": uploaded_file.name.replace('.pdf', '').replace('.txt', '').replace('.md', '').replace('_', ' '),
        "user_context": user_context.strip() if user_context else "",
    }

    # Import research context if selected
    research_context_formatted = None
    if use_research_context and selected_research_reports:
        try:
            importer = ResearchContextImporter(research_folder)
            imported_reports = importer.import_multiple_reports(selected_research_reports)
            if imported_reports:
                research_context_formatted = importer.format_for_context(imported_reports)
                st.session_state.research_context_used = f"**Reports included:** {', '.join(selected_research_reports)}"
        except Exception as e:
            st.markdown(
                f"<div class='status-warning'>Could not import research context: {str(e)}</div>",
                unsafe_allow_html=True
            )

    # Clear tool cache for fresh analysis and capture start time
    clear_tool_cache()
    st.session_state.analysis_start_time = time.time()

    # Run analysis
    with st.spinner(f"Running {len(analyses_to_run)} analysis agents with {selected_llm_name}..."):
        progress_placeholder = st.empty()
        progress_bar = st.progress(0)
        status_text = st.empty()

        try:
            # Show progress
            progress_bar.progress(10)
            status_text.text("Building analysis crew...")

            crew, tracer = build_proposal_analysis_crew(
                proposal_text=proposal_text,
                proposal_metadata=proposal_metadata,
                llm_model=selected_provider["model"],
                analyses_to_run=analyses_to_run,
                include_criteria_evaluation=run_criteria,
                enable_tracing=enable_tracing,
                research_context=research_context_formatted,
            )

            progress_bar.progress(20)
            status_text.text("Starting analysis (this may take several minutes)...")

            result = crew.kickoff()
            result_text = str(result)

            progress_bar.progress(85)
            status_text.text("Generating report...")

            # Clean up the result
            cleaned_result = strip_markdown_fences(result_text)

            # Generate execution trace if enabled
            if enable_tracing and tracer:
                status_text.text("Generating execution trace...")
                # Use the helper to create trace from output since we don't have real-time callbacks
                tracer = create_tracer_from_crew_output(
                    crew_output=cleaned_result,
                    proposal_title=proposal_metadata.get("title", "Grant Proposal"),
                    organization=proposal_metadata.get("organization", "Unknown Organization"),
                )
                trace_report = tracer.generate_stakeholder_report()
                st.session_state.execution_trace = trace_report

                # Save trace to file
                os.makedirs("output/traces", exist_ok=True)
                trace_path = tracer.save_to_file("output/traces")

            progress_bar.progress(95)

            # Save to session state
            st.session_state.analysis_result = cleaned_result
            st.session_state.analysis_complete = True

            # Save to file
            output_filename = f"proposal_analysis_{uploaded_file.name.replace('.', '_')}.md"
            out_path = f"output/{output_filename}"
            write_file(out_path, cleaned_result)

            progress_bar.progress(100)
            status_text.text("Analysis complete!")

            # Calculate and store analysis duration
            elapsed_seconds = time.time() - st.session_state.analysis_start_time
            st.session_state.analysis_duration = elapsed_seconds

            trace_msg = " Execution trace saved to output/traces/ folder." if enable_tracing else ""
            st.markdown(
                f"<div class='status-ok'>Analysis complete! Report saved to output/ folder.{trace_msg} "
                "View results in the tabs above.</div>",
                unsafe_allow_html=True
            )

            # Rerun to show results
            st.rerun()

        except Exception as e:
            st.markdown(
                f"<div class='status-error'><b>Analysis failed:</b> {str(e)}</div>",
                unsafe_allow_html=True,
            )
            progress_bar.empty()
            status_text.empty()

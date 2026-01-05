"""
Deep Research Assistant Agent - Streamlit UI

A multi-agent research system that conducts comprehensive academic research
using primary sources (peer-reviewed papers, government reports, institutional data).

Copyright (c) 2024 Bezos Earth Fund
All rights reserved.

Author: [Your Name], Bezos Earth Fund
Contact: [email@bezosearthfund.org]
Version: 1.0.0
"""

import os
import time
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from src.crew import build_crew
from src.tools import write_file, process_uploaded_files

# Load .env reliably from project root
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
# Helper: strip markdown fences
# ---------------------------
def strip_markdown_fences(text: str) -> str:
    """
    Removes leading/trailing ``` or ```markdown fences
    so Streamlit renders markdown instead of code blocks.
    """
    if not text:
        return text

    t = text.strip()

    if t.startswith("```"):
        lines = t.splitlines()
        # remove opening fence line: ``` or ```markdown
        lines = lines[1:]
        # remove closing fence if present
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


st.set_page_config(
    page_title="Deep Research Assistant",
    page_icon="🔬",
    layout="wide",
)

# ---------- Light Professional Theme ----------
st.markdown(
    """
    <style>
      /* --- Remove Streamlit top chrome spacing --- */
      header[data-testid="stHeader"] {
        height: 0rem;
        background: transparent;
      }
      div[data-testid="stToolbar"] { visibility: hidden; height: 0; }
      div[data-testid="stDecoration"] { visibility: hidden; height: 0; }
      #MainMenu { visibility: hidden; }
      footer { visibility: hidden; }

      /* --- Page background: Light gradient --- */
      .stApp {
        background: linear-gradient(180deg, #f8fafc 0%, #f1f5f9 100%);
        color: #1e293b;
      }

      /* Reduce top padding */
      .block-container { padding-top: 1rem; padding-bottom: 2rem; }

      h1, h2, h3, h4 { color: #0f172a; }

      .subtitle {
        font-size: 1.05rem;
        color: #64748b;
        margin-top: -0.25rem;
        margin-bottom: 0.75rem;
      }

      .badge {
        display: inline-block;
        padding: 0.3rem 0.75rem;
        border-radius: 999px;
        font-size: 0.8rem;
        font-weight: 600;
        background: linear-gradient(90deg, #0d9488, #0891b2);
        color: #ffffff;
        margin-bottom: 0.75rem;
      }

      .card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 20px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04);
        margin-bottom: 16px;
      }

      .card-header {
        font-size: 0.85rem;
        font-weight: 600;
        color: #64748b;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 12px;
        padding-bottom: 8px;
        border-bottom: 1px solid #e2e8f0;
      }

      .hint {
        font-size: 0.9rem;
        color: #64748b;
        margin-top: 4px;
      }

      /* Input styling */
      .stTextInput > div > div,
      .stTextArea > div > div,
      .stSelectbox > div > div {
        background: #ffffff !important;
        border-radius: 8px !important;
        border: 1px solid #e2e8f0 !important;
      }

      .stTextInput > div > div:focus-within,
      .stTextArea > div > div:focus-within,
      .stSelectbox > div > div:focus-within {
        border-color: #0d9488 !important;
        box-shadow: 0 0 0 2px rgba(13, 148, 136, 0.1) !important;
      }

      /* Primary button */
      .stButton > button {
        background: linear-gradient(90deg, #0d9488, #0891b2) !important;
        color: white !important;
        border: 0 !important;
        border-radius: 8px !important;
        padding: 0.6rem 1.25rem !important;
        font-weight: 600 !important;
        width: 100%;
        transition: all 0.2s ease;
      }
      .stButton > button:hover {
        filter: brightness(1.05);
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(13, 148, 136, 0.25);
      }

      /* Status indicators */
      .status-ok {
        background: #f0fdf4;
        border: 1px solid #bbf7d0;
        padding: 12px 16px;
        border-radius: 8px;
        color: #166534;
        font-size: 0.9rem;
      }
      .status-warning {
        background: #fefce8;
        border: 1px solid #fef08a;
        padding: 12px 16px;
        border-radius: 8px;
        color: #854d0e;
        font-size: 0.9rem;
      }
      .status-error {
        background: #fef2f2;
        border: 1px solid #fecaca;
        padding: 12px 16px;
        border-radius: 8px;
        color: #991b1b;
        font-size: 0.9rem;
      }

      /* API key status badge */
      .key-ok {
        display: inline-block;
        background: #dcfce7;
        color: #166534;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 0.75rem;
        font-weight: 500;
      }
      .key-missing {
        display: inline-block;
        background: #fee2e2;
        color: #991b1b;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 0.75rem;
        font-weight: 500;
      }

      /* File uploader styling */
      .stFileUploader > div {
        background: #f8fafc !important;
        border: 2px dashed #cbd5e1 !important;
        border-radius: 8px !important;
      }
      .stFileUploader > div:hover {
        border-color: #0d9488 !important;
        background: #f0fdfa !important;
      }

      /* Toggle styling */
      .stToggle > label > div {
        background-color: #cbd5e1 !important;
      }
      .stToggle > label > div[data-checked="true"] {
        background-color: #0d9488 !important;
      }

      code, pre {
        background: #f1f5f9 !important;
        border-radius: 6px !important;
        border: 1px solid #e2e8f0 !important;
      }

      /* Download button */
      .stDownloadButton > button {
        background: #ffffff !important;
        color: #0d9488 !important;
        border: 1px solid #0d9488 !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
      }
      .stDownloadButton > button:hover {
        background: #f0fdfa !important;
      }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------- Header ----------
st.markdown("<span class='badge'>Deep Research Assistant</span>", unsafe_allow_html=True)
st.title("Research Assistant Agent")
st.markdown(
    "<div class='subtitle'>Multi-agent research system using primary academic sources. "
    "Configure your model, upload documents, and run comprehensive research.</div>",
    unsafe_allow_html=True,
)

# ---------- Layout ----------
left, right = st.columns([1, 1.3], gap="large")

with left:
    # --- Model Configuration Card ---
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("<div class='card-header'>Model Configuration</div>", unsafe_allow_html=True)

    selected_llm_name = st.selectbox(
        "Select LLM",
        options=list(LLM_PROVIDERS.keys()),
        index=0,
        help="Choose the language model for your research agents"
    )

    selected_provider = LLM_PROVIDERS[selected_llm_name]
    api_key_configured = check_api_key(selected_provider["env_key"])

    # Show API key status
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

    # --- Research Configuration Card ---
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("<div class='card-header'>Research Configuration</div>", unsafe_allow_html=True)

    topic = st.text_input(
        "Research Topic",
        value="",
        placeholder="e.g., Impact of AI on climate change mitigation strategies",
        help="Describe what you want the research team to investigate"
    )

    st.markdown("<div class='hint' style='margin-bottom: 12px;'>Optional: Add specific URLs for the agents to analyze</div>", unsafe_allow_html=True)

    urls_text = st.text_area(
        "Source URLs (one per line)",
        value="",
        height=100,
        placeholder="https://example.com/paper1\nhttps://example.com/paper2",
    )

    st.markdown("</div>", unsafe_allow_html=True)

    # --- Document Upload Card ---
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("<div class='card-header'>Upload Documents</div>", unsafe_allow_html=True)

    st.markdown(
        "<div class='hint'>Upload prior research, papers, or reports to include in the analysis. "
        "Supported formats: PDF, TXT, Markdown</div>",
        unsafe_allow_html=True
    )

    uploaded_files = st.file_uploader(
        "Drop files here or click to browse",
        type=["pdf", "txt", "md"],
        accept_multiple_files=True,
        label_visibility="collapsed"
    )

    if uploaded_files:
        st.markdown(f"**{len(uploaded_files)} file(s) selected:**")
        for f in uploaded_files:
            file_size = len(f.getvalue()) / 1024
            st.markdown(f"- {f.name} ({file_size:.1f} KB)")

    st.markdown("</div>", unsafe_allow_html=True)

    # --- Output Settings Card ---
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("<div class='card-header'>Output Settings</div>", unsafe_allow_html=True)

    try_search = st.toggle(
        "Enable web search (when no URLs provided)",
        value=True,
        help="Allow agents to search the web when no URLs are specified"
    )

    save_name = st.text_input(
        "Report filename",
        value="research_report.md",
        help="Name for the output file"
    )

    st.markdown("</div>", unsafe_allow_html=True)

    # --- Run Button ---
    st.markdown("<div style='height: 8px'></div>", unsafe_allow_html=True)
    run_btn = st.button("Run Research Crew", use_container_width=True)

with right:
    st.markdown("<div class='card' style='min-height: 500px;'>", unsafe_allow_html=True)
    st.markdown("<div class='card-header'>Research Output</div>", unsafe_allow_html=True)
    output_placeholder = st.empty()
    output_placeholder.markdown(
        "<div style='color: #94a3b8; text-align: center; padding: 100px 20px;'>"
        "Configure your research parameters and click 'Run Research Crew' to begin."
        "</div>",
        unsafe_allow_html=True
    )
    st.markdown("</div>", unsafe_allow_html=True)


# ---------- Run logic ----------
def parse_urls(text: str):
    urls = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        # basic cleanup
        if line.startswith("- "):
            line = line[2:].strip()
        urls.append(line)
    return urls


if run_btn:
    urls = parse_urls(urls_text)
    selected_provider = LLM_PROVIDERS[selected_llm_name]

    # Validation
    if not topic.strip():
        st.markdown(
            "<div class='status-error'>Please enter a research topic.</div>",
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

    if not urls and not try_search and not uploaded_files:
        st.markdown(
            "<div class='status-warning'>No URLs provided and web search is disabled. "
            "Please provide URLs, upload documents, or enable web search.</div>",
            unsafe_allow_html=True
        )
        st.stop()

    # Process uploaded files
    user_documents = None
    if uploaded_files:
        with st.spinner("Processing uploaded documents..."):
            user_documents = process_uploaded_files(uploaded_files)
            if user_documents:
                st.markdown(
                    f"<div class='status-ok'>Processed {len(user_documents)} document(s) successfully.</div>",
                    unsafe_allow_html=True
                )

    with st.spinner(f"Running research agents with {selected_llm_name}..."):
        try:
            # Build and run crew
            urls_arg = urls if urls else (None if try_search else [])

            crew = build_crew(
                topic=topic,
                urls=urls_arg,
                llm_model=selected_provider["model"],
                user_documents=user_documents
            )
            result = crew.kickoff()
            result_text = str(result)

            # Strip fences BEFORE saving/rendering
            cleaned = strip_markdown_fences(result_text)

            out_path = f"output/{save_name}"
            write_file(out_path, cleaned)

            st.markdown(
                "<div class='status-ok'>Research complete! Report saved to output/ folder.</div>",
                unsafe_allow_html=True
            )

            # Render cleaned markdown
            output_placeholder.markdown(cleaned)

            # Download button
            st.download_button(
                label="Download Report",
                data=cleaned.encode("utf-8"),
                file_name=save_name,
                mime="text/markdown",
            )

        except Exception as e:
            st.markdown(
                f"<div class='status-error'><b>Run failed:</b> {e}</div>",
                unsafe_allow_html=True,
            )

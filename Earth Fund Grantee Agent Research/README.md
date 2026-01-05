# Deep Research Assistant Agent

**CrewAI · Claude Opus 4.5 · Streamlit**

A production-ready **multi-agent deep research assistant** built with **CrewAI**, **Claude Opus 4.5**, and a **Streamlit UI**.

This system uses a *team of AI agents* to conduct comprehensive academic research using **primary sources only** — peer-reviewed papers, government reports, and institutional analyses. It generates structured, evidence-based research briefs suitable for executive decision-making.

---

## Copyright & License

**Copyright (c) 2024 Bezos Earth Fund**
All rights reserved.

**Author:** [Your Name], Bezos Earth Fund
**Contact:** [email@bezosearthfund.org]
**Version:** 1.0.0

---

## Key Features

- **Primary Source Research**: Searches arXiv, PubMed, Semantic Scholar, and government databases
- **Evidence Grading**: All findings rated by evidence strength (Strong/Moderate/Preliminary)
- **Source Credibility Tiers**: Strict hierarchy from Tier 1 (peer-reviewed) to Tier 4 (avoid)
- **Academic Citations**: Full citations with authors, year, venue, and URLs
- **Multi-Agent Pipeline**: Research Agent → Synthesis Agent workflow

---

## What This Project Does

- Accepts a **topic** and optional **list of URLs**
- Runs a **2-agent CrewAI workflow**:
  - **Deep Research Analyst** → searches academic databases, extracts evidence
  - **Evidence Synthesis Analyst** → produces structured brief with confidence levels
- Outputs a **Markdown research report** with:
  - Executive summary with evidence grades
  - Findings backed by primary sources
  - Risks and uncertainties
  - Prioritized recommendations
  - Complete academic citations

---

## Project Structure

```
research-assistant-agent/
├── app.py                # Streamlit UI
├── requirements.txt      # Python dependencies
├── .env                  # API keys (not committed)
├── .gitignore           # Git ignore rules
├── output/
│   └── report.md         # Generated research brief
└── src/
    ├── main.py           # CLI entry point
    ├── crew.py           # Agent + task definitions
    ├── tools.py          # Research tools (arXiv, PubMed, etc.)
    └── prompts.py        # Agent instructions
```

---

## Setup Instructions

### 1. Python Environment

Requires **Python 3.10+** (recommended: **Python 3.12**)

```bash
python -m venv .venv
source .venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Environment Variables

Create a `.env` file in the project root:

```env
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxxxxxxxxxxxxx
```

> **Warning:** Never commit `.env` to source control.

---

## Research Tools

The system includes specialized tools for primary source discovery:

| Tool | Database | Best For |
|------|----------|----------|
| `deep_research` | All databases | Comprehensive multi-database search |
| `arxiv_search` | arXiv | CS, physics, math, AI/ML papers |
| `pubmed_search` | PubMed | Medical, biological, health research |
| `semantic_scholar_search` | Semantic Scholar | Highly-cited papers (all fields) |
| `government_search` | .gov, WHO, World Bank | Official data, policy documents |

---

## Source Credibility Hierarchy

| Tier | Source Type | Usage |
|------|-------------|-------|
| **Tier 1** | Peer-reviewed journals, systematic reviews, government stats | **Required** |
| **Tier 2** | arXiv preprints, conference papers, WHO/World Bank | **Preferred** |
| **Tier 3** | Industry reports (Gartner, McKinsey), think tanks | **Use with caution** |
| **Tier 4** | News articles, Wikipedia | **Avoid** |
| **Reject** | Blogs, social media, marketing materials | **Never cite** |

---

## Running the Agent

### Option 1: Streamlit UI (Recommended)

```bash
streamlit run app.py
```

**UI Features:**
- Topic input
- URL input (one per line)
- Deep research toggle
- Live output preview
- Downloadable Markdown report

### Option 2: Command Line

```bash
python -m src.main
```

Or with a custom topic + URLs:

```bash
python -m src.main "Climate change mitigation strategies" \
  https://arxiv.org/abs/example1 \
  https://pubmed.ncbi.nlm.nih.gov/example2
```

Output will be written to: `output/report.md`

---

## Use Cases

- **Environmental research** and policy analysis
- **Literature reviews** for scientific topics
- **Competitive analysis** of technologies and approaches
- **Due diligence** research with primary sources
- **Grant proposal** background research
- **Technical deep dives** with academic backing

---

## Extending the System

Potential enhancements:
- Add a **fact-checker agent** for source verification
- Integrate **RAG / vector databases** for document retrieval
- Add **citation validation** against original sources
- Schedule automated research runs
- Deploy on cloud infrastructure

---

## Built With

- **CrewAI** - Multi-agent orchestration
- **Claude Opus 4.5** - Advanced reasoning and research
- **Streamlit** - Interactive web UI
- **arXiv API** - Academic preprint access
- **PubMed E-utilities** - Medical literature search
- **Semantic Scholar API** - Citation-aware paper search

---

## Contact

**Bezos Earth Fund**
[email@bezosearthfund.org]

For questions, issues, or contributions, please contact the development team.

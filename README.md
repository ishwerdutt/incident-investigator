# Incident Investigator 🔍🚨

> **Autonomous Agentic Root-Cause Investigation Engine for Server Logs**
>
> Reads high-volume server logs, condenses them using deterministic Drain3 template extraction and time bucketing, coordinates a multi-agent team to hypothesize and test causes using structured tools over DuckDB, enforces strict evidence ledger citations, and generates verified post-mortem reports.

---

## 🏗️ Architecture

```
Logs (file upload / paste / Loki / CloudWatch / ELK)
        │
        ▼
[1. Ingestion & Preprocessing] ── Sensitive data redaction (PII/secrets) & format normalization
        │
        ▼
[2. Drain3 Template Extraction] ── Parameterized pattern clustering & 1m/5m time-bucketing
        │
        ▼
[3. Anomaly Scorer] ── Deterministic z-score spike detection & first-occurrence tagging
        │
        ▼
[4. DuckDB Columnar Log Store] ── High-performance SQL queries & temporal indexing
        │
        ▼
[5. Multi-Agent Orchestrator] <──> [OpenAI GPT-4o / Pluggable LLM Layer]
   │   │   │   │
   │   │   │   └─ Critic / Verifier Agent (Causality & temporal consistency gate)
   │   │   └──── Hypothesis Tester Agents (Parallel tool execution)
   │   └──────── Hypothesis Generator Agent (3–5 falsifiable hypotheses)
   └──────────── Triage Agent (Incident window & symptom isolation)
        │  (All agents query the 8 bounded tools over DuckDB)
        ▼
[6. Evidence Ledger] ── Invariant checks (cause precedes symptom, mandatory event citations)
        │
        ▼
[7. Report Generator] ── Root cause, incident timeline, verified evidence citations, mitigations
        │
        ▼
[8. Live Web App & API] ── Real-time SSE streaming dashboard (React + Vite + FastAPI)
```

---

## ✨ Key Features

- **Engine First, Web App Second**: Standalone Python library (`incident_investigator`) with zero web dependencies. The FastAPI + React web dashboard simply consumes the core engine and its live SSE stream.
- **Log Reduction Without LLM Bloat**: Millions of raw log lines collapse into a few dozen templates via the Drain algorithm (`drain3`). Agents start from compact summaries and drill into raw lines only through tools.
- **8 Bounded Investigation Tools over DuckDB**:
  - `search_logs(query, time_range, service, level, limit)`
  - `get_template_stats(template_id, time_range)`
  - `get_context(event_id, before, after)`
  - `trace_request(request_id)`
  - `compare_windows(window_a, window_b)`
  - `find_first_occurrence(template_id)`
  - `correlate(template_a, template_b, max_lag_seconds)`
  - `get_service_dependencies()`
- **Evidence Ledger (Hallucination Control)**:
  - Strict citation rule: Every claim in the post-mortem report must link to verified `event_ids`.
  - Temporal precedence invariant: A hypothesis can only be marked supported if $t_{\text{cause}} < t_{\text{symptom}}$.
  - Refuted hypotheses preserved: What was ruled out is recorded with refutation rationale.
- **Real-Time Live Web Dashboard**:
  - Built with React, Vite, and Tailwind CSS.
  - Live 6-stage pipeline stepper (Ingestion → Triage → Hypotheses → Testing → Critique → Report).
  - Dynamic hypothesis status cards (Open, Testing, Supported, Refuted).
  - Streaming tool execution feed and "Show Your Work" audit drawer.
- **Chaos Incident Benchmark**:
  - 4 reproducible production failure scenarios (DB connection pool starvation, OOM kill, regression deploy, upstream outage).
  - Automated evaluation harness checking root-cause accuracy, citation precision, and duration.

---

## 🚀 Quick Start

### 1. Installation

Clone the repository and install dependencies with [`uv`](https://github.com/astral-sh/uv):

```bash
git clone https://github.com/ishwerdutt/incident-investigator.git
cd incident-investigator

# Install all dependencies including web and dev extras
uv sync --all-extras
```

### 2. Configure API Key

Create a `.env` file in the root directory:

```bash
OPENAI_API_KEY=sk-proj-your-api-key-here
```

### 3. Run via CLI

#### Dry-run mode (deterministic analysis, no LLM cost):
```bash
uv run incident-investigator investigate examples/db_outage.log --hint "Checkout failing with 504 errors" --dry-run
```

#### Full Agentic Investigation:
```bash
uv run incident-investigator investigate examples/db_outage.log --hint "Checkout failing with 504 errors" --output report.md
```

### 4. Start the Web Dashboard

```bash
uv run uvicorn web.backend.main:app --host 127.0.0.1 --port 8000 --reload
```

Open **[http://localhost:8000](http://localhost:8000)** in your browser. You can click **"Load Sample db_outage Scenario"** to run an instant investigation with real-time SSE streaming.

---

## 💻 Python Library Usage

```python
import asyncio
from incident_investigator import Investigator

async def main():
    investigator = Investigator()
    result = await investigator.investigate_async(
        files=["examples/db_outage.log"],
        hint="Checkout service timeouts",
    )
    print(result.report_markdown())

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 🧪 Testing

The test suite contains **98 automated tests** covering parsers, redaction, Drain3 clustering, DuckDB queries, the 8 tools, evidence ledger invariants, multi-agent orchestration, CLI, benchmarks, and FastAPI endpoints.

```bash
# Run all tests
uv run pytest -v

# Run linter
uv run ruff check .
```

---

## 📂 Project Layout

```
├── src/incident_investigator/    # Standalone Core Library
│   ├── models.py                # Pydantic schemas (LogEvent, Hypothesis, etc.)
│   ├── investigator.py          # High-level public API facade
│   ├── cli.py                   # Click + Rich CLI tool
│   ├── ingest/                  # Parsers: JSON, Syslog, ISO-format, AutoParser
│   ├── preprocess/              # Redactor, Drain3 extractor, LogAnalyzer
│   ├── store/                   # DuckDB columnar store
│   ├── tools/                   # 8 bounded query tools
│   ├── llm/                     # OpenAIProvider + MockLLMProvider
│   ├── ledger/                  # EvidenceLedger with invariant verification
│   ├── agents/                  # Triage, Generator, Tester, Critic, Reporter
│   ├── orchestrator.py          # Multi-round orchestration loop
│   └── report/                  # Markdown, JSON, and HTML report renderers
├── web/                         # Web Application
│   ├── backend/                 # FastAPI server with SSE streaming & REST API
│   └── frontend/                # React + Vite + Tailwind CSS dashboard
├── benchmark/                   # Chaos failure scenario generators & runner
├── examples/                    # Sample incident log files (.log and .json)
└── tests/                       # 98 automated unit & integration tests
```

---

## 📄 License

MIT

# Walkthrough: Log and Incident Investigator System

A complete, production-ready, agentic incident investigation engine that ingests high-volume server logs, condenses them using Drain3 template extraction and time bucketing, coordinates a multi-agent team over a DuckDB log store, enforces evidence ledger invariants, and streams live investigation progress to a web application.

---

## 1. System Architecture & Components

```
┌────────────────────────────────────────────────────────────────────────┐
│ Web Dashboard (React + Vite + Tailwind CSS)                           │
│  Live Stage Tracker · Hypothesis Cards · Tool Feed · Report Viewer     │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ SSE / REST API
┌───────────────────────────────────▼────────────────────────────────────┐
│ Web Backend (FastAPI + sse-starlette)                                  │
│  Multipart Ingestion · Async Task Queue · Live Event Broadcaster       │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ calls
┌───────────────────────────────────▼────────────────────────────────────┐
│ Core Library: `incident_investigator`                                  │
│                                                                        │
│  [1. Ingestion & Preprocessing]                                       │
│    • PII Redactor: Regex scrubber (Emails, IPv4/6, Tokens, Keys)       │
│    • Parsers: JsonLogParser, RegexLogParser (ISO/Syslog), AutoParser   │
│    • Template Extractor: Drain3 wrapper for parameterized patterns     │
│    • Analyzer: 1m/5m time-bucketing & z-score anomaly detector         │
│                                                                        │
│  [2. Log Store & Investigation Tools]                                 │
│    • DuckDB LogStore (in-memory / file-backed columnar index)          │
│    • 8 Bounded Query Tools with Event ID citations:                    │
│      1. search_logs            5. compare_windows                      │
│      2. get_template_stats     6. find_first_occurrence               │
│      3. get_context            7. correlate                            │
│      4. trace_request          8. get_service_dependencies             │
│                                                                        │
│  [3. Multi-Agent Orchestration & Evidence Ledger]                      │
│    • EvidenceLedger: Invariant checks (temporal order, citations)      │
│    • Agents: Triage, HypGen, Parallel Testers, Critic, Reporter        │
│    • LLM Provider: OpenAIProvider (GPT-4o) + MockLLMProvider (offline) │
│    • Token & Round Budget Controls with Event Stream Callbacks         │
│                                                                        │
│  [4. Report Renderers]                                                 │
│    • MarkdownRenderer · JsonRenderer · HtmlRenderer (print-to-PDF)     │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Changes Made & File Inventory

### Core Library (`src/incident_investigator/`)
- [models.py](file:///home/carpenter/Desktop/dev/agents/google_adk/src/incident_investigator/models.py): Core data models (`LogEvent`, `LogLevel`, `TemplateCluster`, `BucketCount`, `Hypothesis`, `EvidenceItem`, `IncidentBrief`, `InvestigationConfig`, `InvestigationEvent`, `InvestigationResult`).
- [investigator.py](file:///home/carpenter/Desktop/dev/agents/google_adk/src/incident_investigator/investigator.py): Clean high-level public interface `Investigator` providing both async and sync entry points.
- [cli.py](file:///home/carpenter/Desktop/dev/agents/google_adk/src/incident_investigator/cli.py): Click + Rich CLI (`incident-investigator investigate <files>`).
- **Ingestion & Preprocessing**:
  - [redactor.py](file:///home/carpenter/Desktop/dev/agents/google_adk/src/incident_investigator/preprocess/redactor.py): Sensitive data scrubber for PII and secrets.
  - [parsers.py](file:///home/carpenter/Desktop/dev/agents/google_adk/src/incident_investigator/ingest/parsers.py): `JsonLogParser`, `RegexLogParser`, and heuristic `AutoParser`.
  - [drain.py](file:///home/carpenter/Desktop/dev/agents/google_adk/src/incident_investigator/preprocess/drain.py): Drain3 template mining wrapper.
  - [analyzer.py](file:///home/carpenter/Desktop/dev/agents/google_adk/src/incident_investigator/preprocess/analyzer.py): Time-bucketing and z-score anomaly scoring.
- **Store & Tools**:
  - [duckdb_store.py](file:///home/carpenter/Desktop/dev/agents/google_adk/src/incident_investigator/store/duckdb_store.py): Columnar DuckDB store managing events, templates, and buckets.
  - [investigation_tools.py](file:///home/carpenter/Desktop/dev/agents/google_adk/src/incident_investigator/tools/investigation_tools.py): 8 bounded, read-only tools returning event ID citations with JSON schema tool definitions for LLMs.
- **Ledger & Agents**:
  - [evidence_ledger.py](file:///home/carpenter/Desktop/dev/agents/google_adk/src/incident_investigator/ledger/evidence_ledger.py): Central truth structure enforcing temporal consistency ($t_{\text{cause}} < t_{\text{symptom}}$) and strict citation rules.
  - [provider.py](file:///home/carpenter/Desktop/dev/agents/google_adk/src/incident_investigator/llm/provider.py): Async OpenAI provider with structured tool-calling + deterministic offline mock provider.
  - [base.py](file:///home/carpenter/Desktop/dev/agents/google_adk/src/incident_investigator/agents/base.py): Base agent class with token and tool usage accounting.
  - [triage.py](file:///home/carpenter/Desktop/dev/agents/google_adk/src/incident_investigator/agents/triage.py): Triage agent producing structured `IncidentBrief`.
  - [generator.py](file:///home/carpenter/Desktop/dev/agents/google_adk/src/incident_investigator/agents/generator.py): Hypothesis generator formulating 3–5 falsifiable hypotheses.
  - [tester.py](file:///home/carpenter/Desktop/dev/agents/google_adk/src/incident_investigator/agents/tester.py): Tool-calling hypothesis tester feeding observations into ledger.
  - [critic.py](file:///home/carpenter/Desktop/dev/agents/google_adk/src/incident_investigator/agents/critic.py): Adversarial verifier assessing causality, precedence, and alternative explanations.
  - [reporter.py](file:///home/carpenter/Desktop/dev/agents/google_adk/src/incident_investigator/agents/reporter.py): Ledger-grounded report synthesizer.
  - [orchestrator.py](file:///home/carpenter/Desktop/dev/agents/google_adk/src/incident_investigator/orchestrator.py): Parallel multi-round loop with budget controls and live SSE callbacks.
- **Report Renderers**:
  - [renderers.py](file:///home/carpenter/Desktop/dev/agents/google_adk/src/incident_investigator/report/renderers.py): Rich Markdown, JSON, and standalone dark/light HTML post-mortem renderers.

### Web Application (`web/`)
- **Backend (`web/backend/`)**:
  - [main.py](file:///home/carpenter/Desktop/dev/agents/google_adk/web/backend/main.py): FastAPI application with CORS, multipart upload handling, background investigation queue, `/api/investigations/{id}/events` SSE streaming, report exports, and static mounting for the production UI.
- **Frontend (`web/frontend/`)**:
  - [App.jsx](file:///home/carpenter/Desktop/dev/agents/google_adk/web/frontend/src/App.jsx): React dashboard with drag-and-drop log uploader, sample scenario loader, live 6-stage pipeline stepper, dynamic hypothesis cards, streaming tool execution feed, collapsible "Show Your Work" audit drawer, verified report viewer, and investigation history sidebar.
  - [index.css](file:///home/carpenter/Desktop/dev/agents/google_adk/web/frontend/src/index.css): Custom dark-theme styling, glassy cards, and responsive layouts.

### Benchmarks & Synthetic Scenarios (`benchmark/`)
- [generator.py](file:///home/carpenter/Desktop/dev/agents/google_adk/benchmark/generator.py): 4 realistic chaos failure generators:
  1. `db_pool_exhaustion` (DB pool starvation cascading to 504 timeouts).
  2. `oom_kill` (memory leak in worker process killed by kernel OOM-killer).
  3. `bad_deployment` (release regression with NullPointerException cascade).
  4. `upstream_outage` (third-party payment gateway 503 and retry storm).
- [runner.py](file:///home/carpenter/Desktop/dev/agents/google_adk/benchmark/runner.py): Automated benchmark evaluator testing root-cause accuracy, citation validity, and temporal consistency.

### Example Datasets (`examples/`)
- [db_outage.log](file:///home/carpenter/Desktop/dev/agents/google_adk/examples/db_outage.log): 598-line realistic plain-text incident log across 5 microservices.
- [db_outage.json](file:///home/carpenter/Desktop/dev/agents/google_adk/examples/db_outage.json): 250-line JSON-lines log with trace and request correlation IDs.

---

## 3. Verification & Test Results

The test suite contains **98 automated tests** covering all layers of the system:

```bash
uv run pytest -v
```

| Test File | Tests | Status | Coverage Focus |
|---|---|---|---|
| `test_ingest.py` | 13 | ✅ Pass | JSON parser, Syslog/ISO regex parser, AutoParser format detection |
| `test_preprocess.py` | 14 | ✅ Pass | Sensitive data redaction, Drain3 template extraction, time-bucketing, z-score spikes |
| `test_store.py` | 7 | ✅ Pass | DuckDB tables, bulk ingestion, event retrieval, arbitrary SQL queries |
| `test_tools.py` | 17 | ✅ Pass | 8 query tools: search, stats, context, trace, compare, first occurrence, correlate, dependencies |
| `test_ledger.py` | 9 | ✅ Pass | Invariant enforcement: citations required, temporal precedence check, refuted hypotheses preserved |
| `test_agents.py` | 6 | ✅ Pass | Triage, Generator, Tester, Critic, Reporter, Orchestrator pipeline |
| `test_cli.py` | 8 | ✅ Pass | CLI argument parsing, dry-run mode on plain-text & JSON, error handling |
| `test_report.py` | 10 | ✅ Pass | Markdown, JSON roundtrip, HTML report structure, collapsible drawers, XSS safety |
| `test_benchmark.py` | 7 | ✅ Pass | All 4 chaos generators, benchmark evaluation loop, scorecard rendering |
| `test_web_api.py` | 7 | ✅ Pass | FastAPI endpoints: multipart upload, sample run, SSE event streaming, report export |
| **Total** | **98** | **✅ 100%** | **All 98 tests green in ~12 seconds** |

### Linter & Formatter Status
```bash
uv run ruff check . && uv run ruff format .
# Output: All checks passed!
```

### Frontend Build Status
```bash
cd web/frontend && npm run build
# Output: ✓ built in 1.77s (zero errors, zero warnings)
```

---

## 4. How to Run the System

### 1. Run via CLI
```bash
# Dry-run analysis (no API key needed)
uv run incident-investigator investigate examples/db_outage.log --hint "Checkout failing with 504 errors" --dry-run

# Full LLM investigation (uses OPENAI_API_KEY from environment)
export OPENAI_API_KEY="sk-..."
uv run incident-investigator investigate examples/db_outage.log --hint "Checkout failing with 504 errors" --output report.md
```

### 2. Run via Web Dashboard
```bash
# Start backend (serves both API and production frontend)
uv run uvicorn web.backend.main:app --host 127.0.0.1 --port 8000 --reload
```
Open [http://localhost:8000](http://localhost:8000) in your browser. You can click **"Load Sample db_outage Scenario"** to run an instant investigation with live SSE streaming of hypothesis status cards and tool calls.

For frontend live development with hot module reloading:
```bash
cd web/frontend && npm run dev
# Open http://localhost:5173
```

### 3. Use as a Python Library
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

asyncio.run(main())
```

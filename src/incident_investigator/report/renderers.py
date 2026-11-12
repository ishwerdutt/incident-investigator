"""Comprehensive report renderers for incident investigations: Markdown, JSON, and HTML."""

from __future__ import annotations

import html
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from incident_investigator.models import IncidentBrief, InvestigationResult


# ---------------------------------------------------------------------------
# SVG Icons for HTML Reports
# ---------------------------------------------------------------------------

SVG_CHECK = (
    '<svg class="icon icon-success" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor">'
    '<path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.857-9.809a.75.75 0 00-1.214-.882l-3.483 4.79-1.88-1.88a.75.75 0 10-1.06 1.061l2.5 2.5a.75.75 0 001.137-.089l4-5.5z" clip-rule="evenodd"/>'
    "</svg>"
)

SVG_CROSS = (
    '<svg class="icon icon-danger" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor">'
    '<path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.28 7.22a.75.75 0 00-1.06 1.06L8.94 10l-1.72 1.72a.75.75 0 101.06 1.06L10 11.06l1.72 1.72a.75.75 0 101.06-1.06L11.06 10l1.72-1.72a.75.75 0 00-1.06-1.06L10 8.94 8.28 7.22z" clip-rule="evenodd"/>'
    "</svg>"
)

SVG_WARNING = (
    '<svg class="icon icon-warning" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor">'
    '<path fill-rule="evenodd" d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 5a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 5zm0 9a1 1 0 100-2 1 1 0 000 2z" clip-rule="evenodd"/>'
    "</svg>"
)

SVG_CLOCK = (
    '<svg class="icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor">'
    '<path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm.75-13a.75.75 0 00-1.5 0v5c0 .414.336.75.75.75h4a.75.75 0 000-1.5h-3.25V5z" clip-rule="evenodd"/>'
    "</svg>"
)

SVG_WRENCH = (
    '<svg class="icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor">'
    '<path fill-rule="evenodd" d="M14.5 2a3.5 3.5 0 00-2.475 5.975l-7.79 7.79a1.5 1.5 0 000 2.122l.142.141a1.5 1.5 0 002.121 0l7.79-7.79A3.5 3.5 0 1014.5 2zm1.768 3.232a1.5 1.5 0 11-2.122-2.121 1.5 1.5 0 012.122 2.121z" clip-rule="evenodd"/>'
    "</svg>"
)

SVG_SHIELD = (
    '<svg class="icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor">'
    '<path fill-rule="evenodd" d="M10.362 1.015a.75.75 0 00-.724 0C8.17 1.83 5.438 3.328 3.52 5.086A2.75 2.75 0 002.5 7.108c0 5.447 3.504 9.94 7.218 11.758a.75.75 0 00.564 0c3.714-1.818 7.218-6.31 7.218-11.758 0-.756-.395-1.472-1.02-2.022C14.562 3.328 11.83 1.83 10.362 1.015z" clip-rule="evenodd"/>'
    "</svg>"
)


# ---------------------------------------------------------------------------
# Markdown Renderer
# ---------------------------------------------------------------------------


class MarkdownRenderer:
    """Renders InvestigationResult as a rich GitHub-Flavored Markdown report."""

    def render(self, result: InvestigationResult, brief: IncidentBrief | None = None) -> str:
        if brief is None and getattr(result, "brief", None) is not None:
            brief = result.brief

        lines: list[str] = []

        # 1. Header
        lines.append(f"# 🚨 Incident Investigation Report: `{result.incident_id}`\n")

        # 2. Executive Summary
        lines.append("## 📋 Executive Summary\n")
        lines.append(result.executive_summary.strip() or "*No executive summary provided.*")
        lines.append("")

        # 3. Root Cause & Verdict Banner
        lines.append("## 🎯 Root Cause & Verdict\n")
        conf_pct = f"{result.confidence:.0%}"
        conf_bars = int(result.confidence * 10)
        conf_gauge = f"[{'█' * conf_bars}{'░' * (10 - conf_bars)}] {conf_pct}"

        lines.append(f"- **Root Cause:** {result.root_cause or 'Under investigation'}")
        lines.append(f"- **Confidence:** {conf_gauge}")
        status_tag = "✅ VERIFIED ROOT CAUSE" if result.confidence >= 0.7 else "⚠️ LOW CONFIDENCE / TENTATIVE"
        lines.append(f"- **Verdict:** {status_tag}\n")

        # 4. Incident Brief (if available)
        if brief is not None:
            lines.append("## ⏱️ Incident Brief\n")
            lines.append("| Property | Value |")
            lines.append("| :--- | :--- |")
            lines.append(f"| **Incident Window** | `{brief.incident_window_start}` → `{brief.incident_window_end}` |")
            services_str = ", ".join(f"`{s}`" for s in brief.affected_services) if brief.affected_services else "None"
            lines.append(f"| **Affected Services** | {services_str} |")
            symptoms_str = ", ".join(brief.primary_symptoms) if brief.primary_symptoms else "None"
            lines.append(f"| **Primary Symptoms** | {symptoms_str} |")
            if brief.user_hint:
                lines.append(f"| **User Hint** | {brief.user_hint} |")
            lines.append("")

        # 5. Incident Timeline Table
        lines.append("## 📅 Incident Timeline\n")
        if result.incident_timeline:
            lines.append("| Timestamp | Description | Service |")
            lines.append("| :--- | :--- | :--- |")
            for item in result.incident_timeline:
                ts = item.get("timestamp", "-")
                desc = item.get("description", "").replace("|", "\\|")
                svc = item.get("service", "-")
                lines.append(f"| `{ts}` | {desc} | `{svc}` |")
            lines.append("")
        else:
            lines.append("*No timeline events recorded.*\n")

        # 6. Supported Root-Cause Hypothesis with Evidence Citations
        lines.append("## 🔬 Root-Cause Analysis (Supported Hypothesis)\n")
        if result.supported_hypothesis:
            h = result.supported_hypothesis
            lines.append(f"### Hypothesis: {h.statement}\n")
            lines.append(f"- **Status:** ✅ `{h.status.value.upper()}`")
            lines.append(f"- **Confidence:** {h.confidence:.0%}")
            if h.predicted_evidence:
                lines.append(f"- **Predicted Evidence:** {', '.join(h.predicted_evidence)}")
            if h.falsification_conditions:
                lines.append(f"- **Falsification Conditions:** {', '.join(h.falsification_conditions)}")
            lines.append("")

            if h.evidence:
                lines.append("#### 🧾 Evidence Trail\n")
                lines.append("| Support | Summary | Cited Event IDs | Tool / Source |")
                lines.append("| :---: | :--- | :--- | :--- |")
                for ev in h.evidence:
                    tag = "✅ Yes" if ev.supports else "❌ No"
                    events = ", ".join(f"`{eid}`" for eid in ev.event_ids[:4])
                    if len(ev.event_ids) > 4:
                        events += f" *+{len(ev.event_ids) - 4} more*"
                    events = events or "*None*"
                    summary_clean = ev.summary.replace("|", "\\|")
                    tool = f"`{ev.tool_name}`" if ev.tool_name else "-"
                    lines.append(f"| {tag} | {summary_clean} | {events} | {tool} |")
                lines.append("")

                lines.append("#### 🔍 Evidence Citation Details\n")
                for i, ev in enumerate(h.evidence, 1):
                    tag = "✅ [SUPPORTS]" if ev.supports else "❌ [REFUTES]"
                    lines.append(f"{i}. **{tag} {ev.summary}**")
                    if ev.event_ids:
                        lines.append(f"   - **Event IDs:** {', '.join(f'`{eid}`' for eid in ev.event_ids)}")
                    if ev.explanation:
                        lines.append(f"   - **Explanation:** {ev.explanation}")
                    if ev.tool_name:
                        call_info = f" (call ID: `{ev.tool_call_id}`)" if ev.tool_call_id else ""
                        lines.append(f"   - **Tool:** `{ev.tool_name}`{call_info}")
                    if ev.earliest_timestamp or ev.latest_timestamp:
                        lines.append(f"   - **Time Range:** `{ev.earliest_timestamp}` → `{ev.latest_timestamp}`")
                lines.append("")
        else:
            lines.append("*No supported hypothesis recorded.*\n")

        if result.verified_evidence_event_ids:
            citations = ", ".join(f"`{eid}`" for eid in sorted(result.verified_evidence_event_ids))
            lines.append(f"**Verified Event Citations ({len(result.verified_evidence_event_ids)}):** {citations}\n")

        # 7. Ruled-Out Hypotheses with Refutation Rationale
        lines.append("## ❌ Ruled-Out Hypotheses\n")
        if result.ruled_out_hypotheses:
            for h in result.ruled_out_hypotheses:
                lines.append(f"### ~~{h.statement}~~\n")
                lines.append("- **Status:** 🚫 `REFUTED`")
                rationale = h.critic_notes or "Refuted by evidence during investigation."
                lines.append(f"- **Refutation Rationale:** {rationale}")
                if h.tests_run:
                    tests_str = ", ".join(f"`{t}`" for t in h.tests_run)
                    lines.append(f"- **Tests Run:** {tests_str}")
                if h.evidence:
                    refuting_ev = [e for e in h.evidence if not e.supports]
                    if refuting_ev:
                        ev_summaries = "; ".join(e.summary for e in refuting_ev)
                        lines.append(f"- **Counter-Evidence:** {ev_summaries}")
                lines.append("")
        else:
            lines.append("*No hypotheses were ruled out during this investigation.*\n")

        # 8. Recommended Mitigations
        lines.append("## 🛠️ Recommended Mitigations\n")
        if result.recommended_mitigations:
            for item in result.recommended_mitigations:
                lines.append(f"- [ ] 🔧 {item}")
            lines.append("")
        else:
            lines.append("*No specific mitigations recorded.*\n")

        # 9. Unknowns & Limitations
        lines.append("## ⚠️ Unknowns & Limitations\n")
        if result.unknowns:
            for item in result.unknowns:
                lines.append(f"- ❓ {item}")
            lines.append("")
        else:
            lines.append("*None identified.*\n")

        # 10. Execution Stats
        lines.append("---\n")
        lines.append("### 📊 Execution Statistics\n")
        lines.append("| Metric | Value |")
        lines.append("| :--- | :--- |")
        lines.append(f"| **Total Tokens Used** | {result.total_tokens_used:,} |")
        lines.append(f"| **Total Tool Calls** | {result.total_tool_calls} |")
        lines.append(f"| **Investigation Duration** | {result.investigation_duration_seconds:.2f}s |")
        lines.append(f"| **Verified Citations** | {len(result.verified_evidence_event_ids)} |")
        lines.append("")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# JSON Renderer
# ---------------------------------------------------------------------------


class JsonRenderer:
    """Serializes InvestigationResult into structured JSON with ISO timestamps and full citation details."""

    def render(self, result: InvestigationResult, indent: int = 2) -> str:
        """Serialize *result* to a formatted JSON string."""
        return result.model_dump_json(indent=indent)

    def to_dict(self, result: InvestigationResult) -> dict[str, Any]:
        """Convert *result* to a JSON-compatible Python dictionary."""
        return result.model_dump(mode="json")


# ---------------------------------------------------------------------------
# HTML Renderer
# ---------------------------------------------------------------------------


class HtmlRenderer:
    """Generates a self-contained, beautifully styled HTML post-mortem report."""

    def render(self, result: InvestigationResult, brief: IncidentBrief | None = None) -> str:
        if brief is None and getattr(result, "brief", None) is not None:
            brief = result.brief

        incident_id = html.escape(result.incident_id)
        exec_summary = html.escape(result.executive_summary or "No executive summary provided.")
        root_cause = html.escape(result.root_cause or "Under investigation")
        confidence_pct = int(result.confidence * 100)

        # Brief HTML
        brief_html = ""
        if brief is not None:
            services_badges = (
                "".join(f'<span class="badge badge-service">{html.escape(s)}</span>' for s in brief.affected_services)
                or '<span class="text-muted">None specified</span>'
            )

            symptoms_list = (
                "".join(f"<li>{html.escape(s)}</li>" for s in brief.primary_symptoms) or "<li>None specified</li>"
            )

            hint_row = ""
            if brief.user_hint:
                hint_row = f'<div class="meta-item"><strong>User Hint:</strong> {html.escape(brief.user_hint)}</div>'

            brief_html = f"""
            <section class="card mb-4">
                <h2 class="section-title">{SVG_CLOCK} Incident Brief</h2>
                <div class="grid grid-2">
                    <div class="meta-item">
                        <strong>Window:</strong>
                        <code>{html.escape(str(brief.incident_window_start))}</code> &rarr;
                        <code>{html.escape(str(brief.incident_window_end))}</code>
                    </div>
                    <div class="meta-item">
                        <strong>Affected Services:</strong>
                        <div class="badges-row">{services_badges}</div>
                    </div>
                </div>
                <div class="mt-2">
                    <strong>Primary Symptoms:</strong>
                    <ul class="styled-list">{symptoms_list}</ul>
                </div>
                {hint_row}
            </section>
            """

        # Timeline HTML
        timeline_html = ""
        if result.incident_timeline:
            items_html = []
            for item in result.incident_timeline:
                ts = html.escape(str(item.get("timestamp", "-")))
                desc = html.escape(str(item.get("description", "")))
                svc = item.get("service")
                svc_badge = f'<span class="badge badge-service">{html.escape(svc)}</span> ' if svc else ""
                items_html.append(f"""
                <div class="timeline-item">
                    <div class="timeline-marker"></div>
                    <div class="timeline-content">
                        <span class="timeline-time">{ts}</span>
                        <div class="timeline-desc">{svc_badge}{desc}</div>
                    </div>
                </div>
                """)
            timeline_html = f"""
            <section class="card mb-4">
                <h2 class="section-title">{SVG_CLOCK} Incident Timeline</h2>
                <div class="timeline">
                    {"".join(items_html)}
                </div>
            </section>
            """
        else:
            timeline_html = """
            <section class="card mb-4">
                <h2 class="section-title">Incident Timeline</h2>
                <p class="text-muted">No timeline events recorded.</p>
            </section>
            """

        # Supported Hypothesis & Evidence HTML
        hypo_html = ""
        if result.supported_hypothesis:
            h = result.supported_hypothesis
            h_stmt = html.escape(h.statement)
            h_conf = int(h.confidence * 100)

            evidence_cards = []
            for ev in h.evidence:
                ev_icon = SVG_CHECK if ev.supports else SVG_CROSS
                status_class = "support" if ev.supports else "refute"
                status_label = "Supports" if ev.supports else "Refutes"
                ev_summary = html.escape(ev.summary)
                explanation = html.escape(ev.explanation) if ev.explanation else ""

                event_badges = (
                    "".join(f'<span class="badge badge-event">{html.escape(eid)}</span>' for eid in ev.event_ids)
                    or '<span class="text-muted">No specific event IDs</span>'
                )

                tool_info = ""
                if ev.tool_name:
                    tool_info = f'<span class="badge badge-tool">{html.escape(ev.tool_name)}</span>'
                    if ev.tool_call_id:
                        tool_info += f' <span class="text-muted">call: {html.escape(ev.tool_call_id)}</span>'

                time_info = ""
                if ev.earliest_timestamp or ev.latest_timestamp:
                    time_info = f'<div class="text-muted small mt-1">Time: {html.escape(str(ev.earliest_timestamp))} &rarr; {html.escape(str(ev.latest_timestamp))}</div>'

                evidence_cards.append(f"""
                <div class="evidence-card {status_class}">
                    <div class="evidence-header">
                        <div class="evidence-title">
                            {ev_icon}
                            <strong>{ev_summary}</strong>
                        </div>
                        <span class="badge badge-{status_class}">{status_label}</span>
                    </div>
                    <details class="evidence-details mt-2">
                        <summary>Citations &amp; Details ({len(ev.event_ids)} event{"s" if len(ev.event_ids) != 1 else ""})</summary>
                        <div class="evidence-drawer mt-2">
                            {f'<p class="mb-2">{explanation}</p>' if explanation else ""}
                            <div class="mb-2"><strong>Referenced Events:</strong><div class="badges-row mt-1">{event_badges}</div></div>
                            {f'<div class="mb-1"><strong>Tool:</strong> {tool_info}</div>' if tool_info else ""}
                            {time_info}
                        </div>
                    </details>
                </div>
                """)

            hypo_html = f"""
            <section class="card mb-4">
                <h2 class="section-title">{SVG_SHIELD} Root-Cause Analysis</h2>
                <div class="hypothesis-lead">
                    <div class="hypothesis-statement">{h_stmt}</div>
                    <div class="badges-row mt-2">
                        <span class="badge badge-success">Status: SUPPORTED</span>
                        <span class="badge badge-primary">Confidence: {h_conf}%</span>
                    </div>
                </div>
                <div class="evidence-list mt-3">
                    <h3 class="subsection-title">Evidence Citations ({len(h.evidence)})</h3>
                    {"".join(evidence_cards) if evidence_cards else '<p class="text-muted">No evidence items attached.</p>'}
                </div>
            </section>
            """
        else:
            hypo_html = """
            <section class="card mb-4">
                <h2 class="section-title">Root-Cause Analysis</h2>
                <p class="text-muted">No supported hypothesis recorded.</p>
            </section>
            """

        # Ruled-Out Hypotheses HTML
        ruled_out_html = ""
        if result.ruled_out_hypotheses:
            ro_items = []
            for h in result.ruled_out_hypotheses:
                stmt = html.escape(h.statement)
                notes = html.escape(h.critic_notes or "Refuted by empirical evidence.")
                tests = ", ".join(html.escape(t) for t in h.tests_run) if h.tests_run else "None"
                ro_items.append(f"""
                <div class="ruled-out-card">
                    <div class="ruled-out-title">
                        {SVG_CROSS}
                        <s>{stmt}</s>
                        <span class="badge badge-danger ml-auto">REFUTED</span>
                    </div>
                    <div class="ruled-out-body mt-2">
                        <p><strong>Refutation Rationale:</strong> {notes}</p>
                        <p class="text-muted small mt-1"><strong>Tests Run:</strong> {tests}</p>
                    </div>
                </div>
                """)
            ruled_out_html = f"""
            <section class="card mb-4">
                <h2 class="section-title">{SVG_CROSS} Ruled-Out Hypotheses</h2>
                <div class="ruled-out-list">
                    {"".join(ro_items)}
                </div>
            </section>
            """
        else:
            ruled_out_html = """
            <section class="card mb-4">
                <h2 class="section-title">Ruled-Out Hypotheses</h2>
                <p class="text-muted">No hypotheses were ruled out during this investigation.</p>
            </section>
            """

        # Mitigations HTML
        mitigations_html = ""
        if result.recommended_mitigations:
            m_items = "".join(
                f'<li class="mitigation-item">{SVG_WRENCH} <span>{html.escape(m)}</span></li>'
                for m in result.recommended_mitigations
            )
            mitigations_html = f"""
            <section class="card mb-4">
                <h2 class="section-title">{SVG_WRENCH} Recommended Mitigations</h2>
                <ul class="mitigation-list">{m_items}</ul>
            </section>
            """
        else:
            mitigations_html = """
            <section class="card mb-4">
                <h2 class="section-title">Recommended Mitigations</h2>
                <p class="text-muted">No mitigations specified.</p>
            </section>
            """

        # Unknowns HTML
        unknowns_html = ""
        if result.unknowns:
            u_items = "".join(
                f'<li class="unknown-item">{SVG_WARNING} <span>{html.escape(u)}</span></li>' for u in result.unknowns
            )
            unknowns_html = f"""
            <section class="card mb-4">
                <h2 class="section-title">{SVG_WARNING} Unknowns & Limitations</h2>
                <ul class="unknown-list">{u_items}</ul>
            </section>
            """

        # Verified Events Citation Badge Row
        citations_summary = ""
        if result.verified_evidence_event_ids:
            cit_badges = "".join(
                f'<span class="badge badge-event">{html.escape(eid)}</span>'
                for eid in sorted(result.verified_evidence_event_ids)
            )
            citations_summary = f"""
            <div class="mt-3">
                <strong>All Verified Evidence IDs ({len(result.verified_evidence_event_ids)}):</strong>
                <div class="badges-row mt-1">{cit_badges}</div>
            </div>
            """

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Incident Report: {incident_id}</title>
    <style>
        :root {{
            --bg: #f8fafc;
            --card-bg: #ffffff;
            --card-border: #e2e8f0;
            --text: #0f172a;
            --text-muted: #64748b;
            --primary: #2563eb;
            --primary-bg: #eff6ff;
            --success: #16a34a;
            --success-bg: #f0fdf4;
            --danger: #dc2626;
            --danger-bg: #fef2f2;
            --warning: #d97706;
            --warning-bg: #fffbeb;
            --badge-bg: #f1f5f9;
            --timeline-line: #cbd5e1;
            --radius: 8px;
            --shadow: 0 1px 3px 0 rgb(0 0 0 / 0.1), 0 1px 2px -1px rgb(0 0 0 / 0.1);
        }}

        @media (prefers-color-scheme: dark) {{
            :root {{
                --bg: #090d16;
                --card-bg: #111827;
                --card-border: #1f2937;
                --text: #f3f4f6;
                --text-muted: #9ca3af;
                --primary: #3b82f6;
                --primary-bg: #1e3a8a;
                --success: #22c55e;
                --success-bg: #052e16;
                --danger: #ef4444;
                --danger-bg: #450a0a;
                --warning: #f59e0b;
                --warning-bg: #451a03;
                --badge-bg: #1f2937;
                --timeline-line: #374151;
                --shadow: 0 1px 3px 0 rgb(0 0 0 / 0.4);
            }}
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background-color: var(--bg);
            color: var(--text);
            line-height: 1.6;
            padding: 2rem 1rem;
        }}

        .container {{
            max-width: 900px;
            margin: 0 auto;
        }}

        .card {{
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: var(--radius);
            box-shadow: var(--shadow);
            padding: 1.5rem;
        }}

        .mb-2 {{ margin-bottom: 0.5rem; }}
        .mb-4 {{ margin-bottom: 1.5rem; }}
        .mt-1 {{ margin-top: 0.25rem; }}
        .mt-2 {{ margin-top: 0.5rem; }}
        .mt-3 {{ margin-top: 1rem; }}
        .ml-auto {{ margin-left: auto; }}

        .text-muted {{ color: var(--text-muted); }}
        .small {{ font-size: 0.875rem; }}

        /* Header Banner */
        .report-header {{
            background: linear-gradient(135deg, var(--card-bg), var(--card-border));
            border: 1px solid var(--card-border);
            border-radius: var(--radius);
            padding: 1.75rem;
            margin-bottom: 1.5rem;
            box-shadow: var(--shadow);
        }}

        .header-top {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-wrap: wrap;
            gap: 0.5rem;
        }}

        .incident-id-badge {{
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
            background: var(--badge-bg);
            padding: 0.25rem 0.6rem;
            border-radius: 4px;
            font-size: 0.95rem;
            border: 1px solid var(--card-border);
        }}

        .root-cause-banner {{
            margin-top: 1.25rem;
            padding: 1rem 1.25rem;
            background: var(--danger-bg);
            border-left: 4px solid var(--danger);
            border-radius: 4px;
        }}

        .root-cause-banner h3 {{
            color: var(--danger);
            font-size: 0.85rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 0.25rem;
        }}

        .root-cause-statement {{
            font-size: 1.15rem;
            font-weight: 600;
        }}

        /* Progress / Confidence */
        .confidence-box {{
            display: flex;
            align-items: center;
            gap: 0.75rem;
            margin-top: 0.75rem;
        }}

        .progress-bar {{
            flex: 1;
            height: 8px;
            background: var(--card-border);
            border-radius: 9999px;
            overflow: hidden;
        }}

        .progress-fill {{
            height: 100%;
            background: var(--primary);
            border-radius: 9999px;
            transition: width 0.3s ease;
        }}

        /* Section Titles */
        .section-title {{
            font-size: 1.25rem;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 0.5rem;
            margin-bottom: 1rem;
            padding-bottom: 0.5rem;
            border-bottom: 1px solid var(--card-border);
        }}

        .subsection-title {{
            font-size: 1.05rem;
            font-weight: 600;
            margin-bottom: 0.75rem;
        }}

        /* Badges */
        .badge {{
            display: inline-block;
            font-size: 0.75rem;
            font-weight: 600;
            padding: 0.2rem 0.5rem;
            border-radius: 4px;
            text-transform: uppercase;
        }}

        .badge-service {{
            background: var(--primary-bg);
            color: var(--primary);
            border: 1px solid var(--primary);
        }}

        .badge-event {{
            font-family: ui-monospace, SFMono-Regular, monospace;
            background: var(--badge-bg);
            color: var(--text);
            border: 1px solid var(--card-border);
            text-transform: none;
        }}

        .badge-tool {{
            font-family: ui-monospace, SFMono-Regular, monospace;
            background: var(--badge-bg);
            color: var(--primary);
            text-transform: none;
        }}

        .badge-support {{
            background: var(--success-bg);
            color: var(--success);
        }}

        .badge-refute {{
            background: var(--danger-bg);
            color: var(--danger);
        }}

        .badge-success {{ background: var(--success-bg); color: var(--success); }}
        .badge-danger {{ background: var(--danger-bg); color: var(--danger); }}
        .badge-primary {{ background: var(--primary-bg); color: var(--primary); }}

        .badges-row {{
            display: flex;
            flex-wrap: wrap;
            gap: 0.4rem;
        }}

        /* Timeline */
        .timeline {{
            position: relative;
            padding-left: 1.5rem;
        }}

        .timeline::before {{
            content: '';
            position: absolute;
            left: 7px;
            top: 6px;
            bottom: 6px;
            width: 2px;
            background: var(--timeline-line);
        }}

        .timeline-item {{
            position: relative;
            margin-bottom: 1.25rem;
        }}

        .timeline-item:last-child {{
            margin-bottom: 0;
        }}

        .timeline-marker {{
            position: absolute;
            left: -1.5rem;
            top: 5px;
            width: 16px;
            height: 16px;
            border-radius: 50%;
            background: var(--primary);
            border: 3px solid var(--card-bg);
        }}

        .timeline-content {{
            background: var(--bg);
            padding: 0.75rem 1rem;
            border-radius: var(--radius);
            border: 1px solid var(--card-border);
        }}

        .timeline-time {{
            font-size: 0.8rem;
            font-family: ui-monospace, SFMono-Regular, monospace;
            color: var(--text-muted);
            font-weight: 600;
        }}

        .timeline-desc {{
            margin-top: 0.25rem;
        }}

        /* Evidence Cards */
        .evidence-card {{
            border: 1px solid var(--card-border);
            border-radius: var(--radius);
            padding: 0.9rem 1.1rem;
            margin-bottom: 0.75rem;
            background: var(--bg);
        }}

        .evidence-card.support {{
            border-left: 4px solid var(--success);
        }}

        .evidence-card.refute {{
            border-left: 4px solid var(--danger);
        }}

        .evidence-header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.5rem;
        }}

        .evidence-title {{
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }}

        .evidence-details summary {{
            cursor: pointer;
            color: var(--primary);
            font-size: 0.85rem;
            font-weight: 500;
        }}

        .evidence-drawer {{
            padding-top: 0.5rem;
            border-top: 1px dashed var(--card-border);
        }}

        /* Ruled-out Hypotheses */
        .ruled-out-card {{
            border: 1px solid var(--card-border);
            border-radius: var(--radius);
            padding: 0.9rem 1.1rem;
            margin-bottom: 0.75rem;
            background: var(--bg);
            border-left: 4px solid var(--danger);
        }}

        .ruled-out-title {{
            display: flex;
            align-items: center;
            gap: 0.5rem;
            font-weight: 600;
        }}

        /* Mitigation & Unknowns */
        .mitigation-list, .unknown-list, .styled-list {{
            list-style: none;
        }}

        .mitigation-item, .unknown-item {{
            display: flex;
            align-items: flex-start;
            gap: 0.6rem;
            padding: 0.5rem 0;
            border-bottom: 1px solid var(--card-border);
        }}

        .mitigation-item:last-child, .unknown-item:last-child {{
            border-bottom: none;
        }}

        /* Grid */
        .grid {{
            display: grid;
            gap: 1rem;
        }}

        .grid-2 {{
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
        }}

        .grid-3 {{
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
        }}

        .stat-box {{
            background: var(--bg);
            padding: 1rem;
            border-radius: var(--radius);
            border: 1px solid var(--card-border);
            text-align: center;
        }}

        .stat-value {{
            font-size: 1.5rem;
            font-weight: 700;
            color: var(--primary);
        }}

        .stat-label {{
            font-size: 0.8rem;
            color: var(--text-muted);
            text-transform: uppercase;
        }}

        /* Icons */
        .icon {{
            width: 1.25rem;
            height: 1.25rem;
            display: inline-block;
            vertical-align: middle;
            flex-shrink: 0;
        }}

        .icon-success {{ color: var(--success); }}
        .icon-danger {{ color: var(--danger); }}
        .icon-warning {{ color: var(--warning); }}

        /* Print Styles */
        @media print {{
            body {{
                background: #ffffff !important;
                color: #000000 !important;
                padding: 0;
            }}
            .card, .report-header, .evidence-card, .ruled-out-card {{
                box-shadow: none !important;
                border: 1px solid #ccc !important;
                break-inside: avoid;
            }}
            .timeline-item {{
                break-inside: avoid;
            }}
            details[open] summary ~ *, details summary ~ * {{
                display: block !important;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <header class="report-header">
            <div class="header-top">
                <h1>Incident Post-Mortem Report</h1>
                <span class="incident-id-badge">{incident_id}</span>
            </div>

            <div class="root-cause-banner">
                <h3>Identified Root Cause</h3>
                <div class="root-cause-statement">{root_cause}</div>
            </div>

            <div class="confidence-box">
                <span class="small text-muted">Investigation Confidence:</span>
                <div class="progress-bar">
                    <div class="progress-fill" style="width: {confidence_pct}%;"></div>
                </div>
                <span class="small font-bold"><strong>{confidence_pct}%</strong></span>
            </div>
        </header>

        <!-- Executive Summary -->
        <section class="card mb-4">
            <h2 class="section-title">{SVG_SHIELD} Executive Summary</h2>
            <p>{exec_summary}</p>
        </section>

        <!-- Incident Brief (if provided) -->
        {brief_html}

        <!-- Timeline -->
        {timeline_html}

        <!-- Supported Hypothesis & Evidence -->
        {hypo_html}

        <!-- Ruled-Out Hypotheses -->
        {ruled_out_html}

        <!-- Mitigations -->
        {mitigations_html}

        <!-- Unknowns -->
        {unknowns_html}

        <!-- Execution Stats Footer -->
        <section class="card mb-4">
            <h2 class="section-title">Investigation Metadata & Stats</h2>
            <div class="grid grid-3">
                <div class="stat-box">
                    <div class="stat-value">{result.total_tokens_used:,}</div>
                    <div class="stat-label">Tokens Used</div>
                </div>
                <div class="stat-box">
                    <div class="stat-value">{result.total_tool_calls}</div>
                    <div class="stat-label">Tool Calls</div>
                </div>
                <div class="stat-box">
                    <div class="stat-value">{result.investigation_duration_seconds:.2f}s</div>
                    <div class="stat-label">Duration</div>
                </div>
            </div>
            {citations_summary}
        </section>
    </div>
</body>
</html>"""

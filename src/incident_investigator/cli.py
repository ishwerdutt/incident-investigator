"""Command-line interface for the Incident Investigator."""

from __future__ import annotations

import asyncio
import os
import sys
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from incident_investigator.ingest import AutoParser
from incident_investigator.llm.provider import OpenAIProvider
from incident_investigator.models import InvestigationConfig, LogEvent
from incident_investigator.orchestrator import InvestigationOrchestrator
from incident_investigator.preprocess import LogAnalyzer, Redactor, TemplateExtractor
from incident_investigator.store import LogStore


@click.group()
def main() -> None:
    """Incident Investigator: automated agentic root-cause analysis from server logs."""


@main.command()
@click.argument("log_files", nargs=-1, required=True, type=click.Path(exists=True))
@click.option("--hint", "-h", help="What went wrong?")
@click.option("--model", default="gpt-4o", help="OpenAI model")
@click.option("--max-rounds", default=3, type=int)
@click.option("--output", "-o", type=click.Path(), help="Save report to file")
@click.option("--dry-run", is_flag=True, help="Run ingestion only, skip LLM investigation")
def investigate(
    log_files: Sequence[str],
    hint: str | None,
    model: str,
    max_rounds: int,
    output: str | None,
    dry_run: bool,
) -> None:
    """Investigate an incident across one or more log files."""
    console = Console()

    if not dry_run and not os.environ.get("OPENAI_API_KEY"):
        console.print(
            Panel(
                "[bold red]Error: OPENAI_API_KEY is not set.[/bold red]\n\n"
                "An OpenAI API key is required to run the agentic investigation.\n"
                "Please set the OPENAI_API_KEY environment variable, or use [bold cyan]--dry-run[/bold cyan] "
                "to parse and inspect logs without calling the LLM.",
                title="Authentication Error",
                border_style="red",
            )
        )
        sys.exit(1)

    redactor = Redactor()
    extractor = TemplateExtractor()
    all_events: list[LogEvent] = []

    with console.status("[bold cyan]Reading and parsing log files...[/bold cyan]", spinner="dots"):
        for file_path_str in log_files:
            file_path = Path(file_path_str)
            try:
                lines = file_path.read_text(encoding="utf-8").splitlines()
            except OSError as e:
                console.print(f"[bold red]Error reading file {file_path}: {e}[/bold red]")
                continue

            parser = AutoParser(lines)
            for line_idx, line in enumerate(lines, start=1):
                event = parser.parse_line(line, str(file_path), line_idx)
                if event is not None:
                    # Run PII and secret redaction
                    event.message = redactor.redact(event.message)
                    # Run Drain3 template clustering
                    event.template_id = extractor.add_log_message(event.message)
                    all_events.append(event)

    if not all_events:
        console.print("[yellow]Warning: No valid log events parsed from the provided files.[/yellow]")
        return

    # Sort events chronologically
    all_events.sort(key=lambda e: e.timestamp)

    with console.status("[bold cyan]Extracting templates and scoring anomalies...[/bold cyan]", spinner="dots"):
        templates = extractor.get_templates()

        # Correlate template occurrences to compute first_seen, last_seen, and services
        events_by_template: dict[str, list[LogEvent]] = defaultdict(list)
        for ev in all_events:
            if ev.template_id:
                events_by_template[ev.template_id].append(ev)

        for tpl in templates:
            t_events = events_by_template.get(tpl.template_id, [])
            if t_events:
                tpl.first_seen = min(e.timestamp for e in t_events)
                tpl.last_seen = max(e.timestamp for e in t_events)
                tpl.services = sorted({e.service for e in t_events})

        buckets = LogAnalyzer.bucket_events(all_events, bucket_minutes=1)
        scored_templates = LogAnalyzer.score_anomalies(templates, buckets, z_threshold=3.0)
        anomalies = [t for t in scored_templates if t.is_anomaly]

    # Print summary: total events, templates found, anomalies detected
    summary_table = Table(title="Log Ingestion & Analysis Summary", show_header=True, header_style="bold magenta")
    summary_table.add_column("Metric", style="bold")
    summary_table.add_column("Value")
    summary_table.add_row("Log Files Processed", str(len(log_files)))
    summary_table.add_row("Total Events Ingested", f"{len(all_events):,}")
    summary_table.add_row("Templates Found", f"{len(scored_templates):,}")
    summary_table.add_row("Anomalies Detected", f"{len(anomalies):,}")
    console.print(summary_table)

    if anomalies:
        anom_table = Table(title="Top Anomalous Templates", show_header=True, header_style="bold red")
        anom_table.add_column("Score", justify="right", style="cyan")
        anom_table.add_column("Count", justify="right")
        anom_table.add_column("Services", style="yellow")
        anom_table.add_column("Pattern")
        for tpl in anomalies[:10]:
            pat = tpl.pattern
            if len(pat) > 80:
                pat = pat[:77] + "..."
            anom_table.add_row(
                f"{tpl.anomaly_score:.2f}",
                str(tpl.total_count),
                ", ".join(tpl.services) if tpl.services else "unknown",
                pat,
            )
        console.print(anom_table)

    if dry_run:
        console.print("\n[bold green]Dry run completed successfully.[/bold green] Skipped LLM investigation.")
        if output:
            out_path = Path(output)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            dry_summary_lines = [
                "# Ingestion & Analysis Summary (Dry Run)\n",
                f"- **Log Files:** {', '.join(str(f) for f in log_files)}",
                f"- **Total Events:** {len(all_events):,}",
                f"- **Templates Found:** {len(scored_templates):,}",
                f"- **Anomalies Detected:** {len(anomalies):,}\n",
                "## Top Anomalies\n",
            ]
            for tpl in anomalies[:10]:
                dry_summary_lines.append(
                    f"- **Score {tpl.anomaly_score:.2f}** ({tpl.total_count} events, services: {', '.join(tpl.services)}): `{tpl.pattern}`"
                )
            out_path.write_text("\n".join(dry_summary_lines), encoding="utf-8")
            console.print(f"[bold green]Dry run summary saved to:[/bold green] {output}")
        return

    with console.status("[bold blue]Initializing DuckDB log store and ingesting data...[/bold blue]", spinner="dots"):
        store = LogStore()
        store.ingest_events(all_events)
        store.ingest_templates(scored_templates)
        store.ingest_buckets(buckets)

    api_key = os.environ.get("OPENAI_API_KEY")
    provider = OpenAIProvider(api_key=api_key, default_model=model)
    config = InvestigationConfig(max_rounds=max_rounds, openai_model=model)
    orchestrator = InvestigationOrchestrator(llm=provider, config=config)

    def on_event(ev: Any) -> None:
        if ev.event_type == "STAGE_CHANGED":
            console.print(f"[bold cyan]▶ Stage:[/bold cyan] {ev.stage} (agent: {ev.agent})")
        elif ev.event_type == "TOOL_CALLED":
            tool_name = ev.data.get("tool", "")
            console.print(f"  [dim]• Tool call:[/dim] [yellow]{tool_name}[/yellow]")
        elif ev.event_type == "LEDGER_UPDATED" and ev.stage == "generate":
            count = ev.data.get("hypotheses_count", 0)
            console.print(f"  [green]• Formulated {count} candidate hypotheses[/green]")

    orchestrator.on_event = on_event

    console.print("\n[bold green]Starting agentic incident investigation...[/bold green]\n")
    try:
        result = asyncio.run(
            orchestrator.investigate(
                events=all_events,
                templates=scored_templates,
                buckets=buckets,
                store=store,
                user_hint=hint,
            )
        )
    except Exception as exc:  # noqa: BLE001
        console.print(f"[bold red]Investigation failed:[/bold red] {exc}")
        sys.exit(1)
    finally:
        store.close()

    report_md = result.report_markdown()
    console.print("\n")
    console.print(
        Panel(
            Markdown(report_md),
            title=f"Investigation Report: {result.incident_id}",
            border_style="bold green",
        )
    )

    if output:
        out_path = Path(output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report_md, encoding="utf-8")
        console.print(f"\n[bold green]Report saved to:[/bold green] {output}")


if __name__ == "__main__":
    main()

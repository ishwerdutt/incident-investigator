"""Tests for the Incident Investigator CLI."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from incident_investigator.cli import main

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOG_FILE = PROJECT_ROOT / "examples" / "db_outage.log"
JSON_FILE = PROJECT_ROOT / "examples" / "db_outage.json"


def test_main_help():
    """Test root command help text."""
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "Incident Investigator" in result.output
    assert "investigate" in result.output


def test_investigate_help():
    """Test investigate subcommand help text."""
    runner = CliRunner()
    result = runner.invoke(main, ["investigate", "--help"])
    assert result.exit_code == 0
    assert "--hint" in result.output
    assert "--model" in result.output
    assert "--max-rounds" in result.output
    assert "--output" in result.output
    assert "--dry-run" in result.output


def test_missing_log_files_argument():
    """Test that omitting required log files argument raises an error."""
    runner = CliRunner()
    result = runner.invoke(main, ["investigate"])
    assert result.exit_code != 0
    assert "Missing argument" in result.output or "Error" in result.output


def test_nonexistent_log_file():
    """Test providing a non-existent log file fails gracefully."""
    runner = CliRunner()
    result = runner.invoke(main, ["investigate", "nonexistent_file_xyz.log", "--dry-run"])
    assert result.exit_code != 0
    assert "does not exist" in result.output or "Error" in result.output


def test_dry_run_log_file():
    """Test dry-run mode on examples/db_outage.log."""
    if not LOG_FILE.exists():
        pytest.skip(f"Example log file not found at {LOG_FILE}")

    runner = CliRunner()
    result = runner.invoke(main, ["investigate", str(LOG_FILE), "--dry-run"])
    assert result.exit_code == 0, f"Command failed with output:\n{result.output}"
    assert "Log Ingestion & Analysis Summary" in result.output
    assert "Total Events Ingested" in result.output
    assert "598" in result.output
    assert "Templates Found" in result.output
    assert "Anomalies Detected" in result.output
    assert "Dry run completed successfully" in result.output


def test_dry_run_json_file():
    """Test dry-run mode on examples/db_outage.json."""
    if not JSON_FILE.exists():
        pytest.skip(f"Example JSON log file not found at {JSON_FILE}")

    runner = CliRunner()
    result = runner.invoke(main, ["investigate", str(JSON_FILE), "--dry-run"])
    assert result.exit_code == 0, f"Command failed with output:\n{result.output}"
    assert "Log Ingestion & Analysis Summary" in result.output
    assert "Total Events Ingested" in result.output
    assert "250" in result.output
    assert "Templates Found" in result.output
    assert "Anomalies Detected" in result.output
    assert "Dry run completed successfully" in result.output


def test_dry_run_output_flag(tmp_path: Path):
    """Test saving dry-run summary with --output."""
    if not LOG_FILE.exists():
        pytest.skip(f"Example log file not found at {LOG_FILE}")

    out_file = tmp_path / "summary.md"
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["investigate", str(LOG_FILE), "--dry-run", "-o", str(out_file)],
    )
    assert result.exit_code == 0
    assert out_file.exists()
    content = out_file.read_text(encoding="utf-8")
    assert "Ingestion & Analysis Summary" in content
    assert "Total Events" in content
    assert "598" in content


def test_missing_openai_api_key_without_dry_run():
    """Test that running without --dry-run when OPENAI_API_KEY is unset fails with exit code 1."""
    if not LOG_FILE.exists():
        pytest.skip(f"Example log file not found at {LOG_FILE}")

    runner = CliRunner()
    env = {k: v for k, v in os.environ.items() if k != "OPENAI_API_KEY"}
    result = runner.invoke(
        main,
        ["investigate", str(LOG_FILE)],
        env=env,
    )
    assert result.exit_code == 1
    assert "OPENAI_API_KEY" in result.output

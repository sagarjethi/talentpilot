"""Rich-powered console output."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from talentpilot.models import SessionMetrics, SubmissionRecord

_console = Console()


def print_banner() -> None:
    """Display the startup banner."""
    _console.print(
        Panel.fit(
            "[bold cyan]TalentPilot[/bold cyan]  —  Automated Job Application Pipeline",
            border_style="cyan",
        )
    )


def print_progress(record: SubmissionRecord, index: int) -> None:
    """Print a single application result line."""
    style_map = {
        "succeeded": "bold green",
        "dry_run": "bold yellow",
        "skipped_blacklist": "dim red",
        "skipped_duplicate": "dim",
        "failed": "bold red",
    }
    style = style_map.get(record.outcome, "")
    title = record.posting.title or "(untitled)"
    company = record.posting.company or "(unknown)"
    _console.print(
        f"  [{style}]{index:>4}[/{style}]  "
        f"[{style}]{record.outcome:<20}[/{style}]  "
        f"{title}  @  {company}"
    )


def print_session_report(metrics: SessionMetrics) -> None:
    """Display a session summary table."""
    table = Table(title="Session Report", show_header=True, header_style="bold magenta")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")

    table.add_row("Inspected", str(metrics.total_inspected))
    table.add_row("Submitted", str(metrics.total_submitted))
    table.add_row("Filtered (blacklist)", str(metrics.total_filtered))
    table.add_row("Failed", str(metrics.total_failed))
    table.add_row("Skipped (already applied)", str(metrics.total_skipped))
    table.add_row("Session ID", metrics.session_id)
    table.add_row("Started", metrics.started_at)
    table.add_row("Ended", metrics.ended_at or "—")

    _console.print()
    _console.print(table)
    _console.print()

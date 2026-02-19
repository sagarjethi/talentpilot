"""Integration tests for the orchestrator (mock browser)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from talentpilot.models import SessionMetrics
from talentpilot.reporting.tracker import SubmissionTracker
from talentpilot.settings import AppSettings


def test_tracker_roundtrip(tmp_path):
    """Verify tracker can start a session, upsert a posting, and record."""
    db = tmp_path / "test.db"
    tracker = SubmissionTracker(db)
    try:
        tracker.start_session("sess-1", ["python"], ["NorthAmerica"], simulation=True)

        from talentpilot.models import JobPosting

        posting = JobPosting(
            platform="linkedin",
            platform_id="42",
            url="https://example.com/42",
            title="Dev",
            company="TestCo",
        )
        pid = tracker.upsert_posting(posting)
        assert pid > 0

        # Same posting should return same id
        pid2 = tracker.upsert_posting(posting)
        assert pid2 == pid

        tracker.record_submission(pid, "sess-1", "succeeded")
        rows = tracker.get_recent_submissions(10)
        assert len(rows) == 1
        assert rows[0]["outcome"] == "succeeded"

        summary = tracker.get_session_summary("sess-1")
        assert summary is not None
        assert summary["simulation_mode"] == 1

        metrics = SessionMetrics(
            session_id="sess-1",
            total_inspected=5,
            total_submitted=1,
        )
        tracker.end_session("sess-1", metrics)
        updated = tracker.get_session_summary("sess-1")
        assert updated["total_inspected"] == 5
    finally:
        tracker.close()


def test_tracker_export_json(tmp_path):
    db = tmp_path / "export.db"
    tracker = SubmissionTracker(db)
    try:
        tracker.start_session("s1", [], [], simulation=False)
        from talentpilot.models import JobPosting

        posting = JobPosting(
            platform="linkedin",
            platform_id="99",
            url="https://example.com/99",
            title="Tester",
            company="Co",
        )
        pid = tracker.upsert_posting(posting)
        tracker.record_submission(pid, "s1", "succeeded")

        json_str = tracker.export_json()
        assert '"Tester"' in json_str
        assert '"succeeded"' in json_str

        csv_str = tracker.export_csv()
        assert "Tester" in csv_str
    finally:
        tracker.close()

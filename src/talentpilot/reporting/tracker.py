"""SQLite-backed submission history — designed for future UI consumption."""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from talentpilot.models import JobPosting, SessionMetrics

logger = logging.getLogger(__name__)

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS postings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    platform        TEXT NOT NULL DEFAULT 'linkedin',
    platform_id     TEXT NOT NULL,
    url             TEXT NOT NULL,
    title           TEXT DEFAULT '',
    company         TEXT DEFAULT '',
    location_label  TEXT DEFAULT '',
    detail_text     TEXT DEFAULT '',
    salary_text     TEXT DEFAULT '',
    discovered_at   TEXT NOT NULL,
    UNIQUE(platform, platform_id)
);

CREATE TABLE IF NOT EXISTS submissions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    posting_id      INTEGER NOT NULL REFERENCES postings(id),
    session_id      TEXT NOT NULL,
    outcome         TEXT NOT NULL,
    failure_reason  TEXT DEFAULT '',
    attempted_at    TEXT NOT NULL,
    duration_ms     INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS sessions (
    id              TEXT PRIMARY KEY,
    started_at      TEXT NOT NULL,
    ended_at        TEXT,
    search_terms    TEXT DEFAULT '',
    regions         TEXT DEFAULT '',
    total_inspected INTEGER DEFAULT 0,
    total_submitted INTEGER DEFAULT 0,
    total_filtered  INTEGER DEFAULT 0,
    total_failed    INTEGER DEFAULT 0,
    total_skipped   INTEGER DEFAULT 0,
    simulation_mode INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS status_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    posting_id      INTEGER NOT NULL REFERENCES postings(id),
    status          TEXT NOT NULL,
    notes           TEXT DEFAULT '',
    changed_at      TEXT NOT NULL
);
"""


class SubmissionTracker:
    """Persistent application history stored in SQLite."""

    def __init__(self, db_path: str | Path) -> None:
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        logger.info("Tracker database ready at %s.", db_path)

    # ---- session lifecycle ----

    def start_session(
        self,
        session_id: str,
        keywords: list[str],
        regions: list[str],
        simulation: bool,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "INSERT INTO sessions (id, started_at, search_terms, regions, simulation_mode) "
            "VALUES (?, ?, ?, ?, ?)",
            (session_id, now, json.dumps(keywords), json.dumps(regions), int(simulation)),
        )
        self._conn.commit()

    def end_session(self, session_id: str, metrics: SessionMetrics) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "UPDATE sessions SET ended_at=?, total_inspected=?, total_submitted=?, "
            "total_filtered=?, total_failed=?, total_skipped=? WHERE id=?",
            (
                now,
                metrics.total_inspected,
                metrics.total_submitted,
                metrics.total_filtered,
                metrics.total_failed,
                metrics.total_skipped,
                session_id,
            ),
        )
        self._conn.commit()

    # ---- postings ----

    def upsert_posting(self, posting: JobPosting) -> int:
        """Insert a posting or return the existing row's ID."""
        cur = self._conn.execute(
            "SELECT id FROM postings WHERE platform=? AND platform_id=?",
            (posting.platform, posting.platform_id),
        )
        row = cur.fetchone()
        if row:
            return row["id"]
        cur = self._conn.execute(
            "INSERT INTO postings (platform, platform_id, url, title, company, "
            "location_label, detail_text, salary_text, discovered_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                posting.platform,
                posting.platform_id,
                posting.url,
                posting.title,
                posting.company,
                posting.location_label,
                posting.detail_text,
                posting.salary_text,
                posting.discovered_at,
            ),
        )
        self._conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    # ---- submissions ----

    def record_submission(
        self,
        posting_id: int,
        session_id: str,
        outcome: str,
        failure_reason: str = "",
        duration_ms: int = 0,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "INSERT INTO submissions (posting_id, session_id, outcome, failure_reason, "
            "attempted_at, duration_ms) VALUES (?, ?, ?, ?, ?, ?)",
            (posting_id, session_id, outcome, failure_reason, now, duration_ms),
        )
        # Insert initial status_history entry if succeeded
        if outcome == "succeeded":
            self._conn.execute(
                "INSERT INTO status_history (posting_id, status, notes, changed_at) "
                "VALUES (?, 'applied', '', ?)",
                (posting_id, now),
            )
        self._conn.commit()

    # ---- queries ----

    def get_recent_submissions(self, limit: int = 20) -> list[dict]:
        cur = self._conn.execute(
            "SELECT p.title, p.company, p.url, s.outcome, s.attempted_at "
            "FROM submissions s JOIN postings p ON p.id = s.posting_id "
            "ORDER BY s.attempted_at DESC LIMIT ?",
            (limit,),
        )
        return [dict(r) for r in cur.fetchall()]

    def get_session_summary(self, session_id: str) -> dict | None:
        cur = self._conn.execute("SELECT * FROM sessions WHERE id=?", (session_id,))
        row = cur.fetchone()
        return dict(row) if row else None

    # ---- export ----

    def export_json(self, since_date: str = "") -> str:
        """Export submissions as JSON (for UI consumption)."""
        query = (
            "SELECT p.title, p.company, p.url, p.location_label, "
            "s.outcome, s.attempted_at, s.duration_ms "
            "FROM submissions s JOIN postings p ON p.id = s.posting_id "
        )
        params: list[str] = []
        if since_date:
            query += "WHERE s.attempted_at >= ? "
            params.append(since_date)
        query += "ORDER BY s.attempted_at DESC"
        cur = self._conn.execute(query, params)
        rows = [dict(r) for r in cur.fetchall()]
        return json.dumps(rows, indent=2)

    def export_csv(self, since_date: str = "") -> str:
        """Export submissions as CSV string."""
        data = json.loads(self.export_json(since_date))
        if not data:
            return ""
        headers = list(data[0].keys())
        lines = [",".join(headers)]
        for row in data:
            lines.append(",".join(str(row.get(h, "")).replace(",", ";") for h in headers))
        return "\n".join(lines)

    def close(self) -> None:
        self._conn.close()

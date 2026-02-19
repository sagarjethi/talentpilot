"""Lightweight dashboard API server — reads from history.db and serves JSON + HTML."""

import json
import sqlite3
import os
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

DB_PATH = Path(__file__).resolve().parent.parent / ".state" / "history.db"
DASHBOARD_DIR = Path(__file__).resolve().parent


def get_db():
    if not DB_PATH.exists():
        return None
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def query_all(sql, params=()):
    conn = get_db()
    if not conn:
        return []
    try:
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def query_one(sql, params=()):
    conn = get_db()
    if not conn:
        return None
    try:
        row = conn.execute(sql, params).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def scalar(sql, params=()):
    conn = get_db()
    if not conn:
        return 0
    try:
        row = conn.execute(sql, params).fetchone()
        return row[0] if row else 0
    finally:
        conn.close()


class DashboardHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DASHBOARD_DIR), **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/stats":
            self._json_response(self._get_stats())
        elif path == "/api/applications":
            self._json_response(self._get_applications())
        elif path == "/api/sessions":
            self._json_response(self._get_sessions())
        elif path == "/api/export/json":
            self._json_response(self._get_applications())
        elif path == "/api/export/csv":
            self._csv_response(self._get_applications())
        else:
            super().do_GET()

    def _json_response(self, data):
        body = json.dumps(data, default=str).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _csv_response(self, rows):
        if not rows:
            lines = ["No data"]
        else:
            keys = list(rows[0].keys())
            lines = [",".join(keys)]
            for r in rows:
                lines.append(",".join(
                    f'"{str(r.get(k, "") or "").replace(chr(34), chr(34)+chr(34))}"'
                    for k in keys
                ))
        body = "\n".join(lines).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/csv")
        self.send_header("Content-Disposition", "attachment; filename=talentpilot-export.csv")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _get_stats(self):
        total = scalar("SELECT COUNT(*) FROM submissions") or 0
        succeeded = scalar("SELECT COUNT(*) FROM submissions WHERE outcome='succeeded'") or 0
        dry_run = scalar("SELECT COUNT(*) FROM submissions WHERE outcome='dry_run'") or 0
        failed = scalar("SELECT COUNT(*) FROM submissions WHERE outcome='failed'") or 0
        skipped = scalar("SELECT COUNT(*) FROM submissions WHERE outcome LIKE 'skipped%'") or 0
        avg_dur = scalar("SELECT AVG(duration_ms) FROM submissions WHERE duration_ms > 0") or 0
        sessions = scalar("SELECT COUNT(*) FROM sessions") or 0

        top_company = query_one(
            "SELECT p.company, COUNT(*) as c FROM submissions s "
            "JOIN postings p ON p.id=s.posting_id "
            "WHERE p.company != '' AND p.company != '(unknown)' "
            "GROUP BY p.company ORDER BY c DESC LIMIT 1"
        )

        return {
            "total": total,
            "succeeded": succeeded,
            "dry_run": dry_run,
            "failed": failed,
            "skipped": skipped,
            "avg_duration_ms": round(avg_dur),
            "sessions": sessions,
            "top_company": top_company["company"] if top_company else "—",
            "top_company_count": top_company["c"] if top_company else 0,
        }

    def _get_applications(self):
        return query_all(
            "SELECT s.id as sid, p.title, p.company, p.location_label, p.url, "
            "s.outcome, s.attempted_at, s.duration_ms, s.failure_reason "
            "FROM submissions s "
            "LEFT JOIN postings p ON p.id = s.posting_id "
            "ORDER BY s.attempted_at DESC"
        )

    def _get_sessions(self):
        return query_all("SELECT * FROM sessions ORDER BY started_at DESC")

    def log_message(self, format, *args):
        pass  # Suppress request logs


def main():
    port = int(os.environ.get("DASHBOARD_PORT", 8787))
    server = HTTPServer(("0.0.0.0", port), DashboardHandler)
    print(f"Dashboard running at http://localhost:{port}")
    print(f"Reading from: {DB_PATH}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.server_close()


if __name__ == "__main__":
    main()

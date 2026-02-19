# TalentPilot

Automated LinkedIn Easy Apply pipeline built with **Playwright** (async), **Pydantic** settings, **SQLite** tracking, and **Rich** console output.

## Architecture

```
Discover  -->  Filter  -->  Submit  -->  Report
```

| Stage | Description |
|-------|-------------|
| **Discover** | Build search URLs from config, scrape job listings across pages |
| **Filter** | Chain-of-responsibility pattern — block by company name, title keywords |
| **Submit** | Multi-step form navigation: fill fields, upload resume, handle radio/dropdown/text |
| **Report** | SQLite persistence (`history.db`), Rich console output, JSON/CSV export |

## Project Structure

```
talentpilot/
├── pyproject.toml              # Dependencies & build config
├── settings.yaml               # User configuration
├── responses.yaml              # Pre-filled form answers
├── Dockerfile / compose.yaml   # Docker support
├── src/talentpilot/
│   ├── __main__.py             # Entry point
│   ├── settings.py             # Pydantic settings + YAML loader
│   ├── models.py               # Domain dataclasses
│   ├── exceptions.py           # Exception hierarchy
│   ├── orchestrator.py         # Pipeline coordinator
│   ├── auth/
│   │   └── session_manager.py  # Login + session persistence
│   ├── browser/
│   │   ├── base.py             # BrowserAdapter protocol
│   │   ├── playwright_adapter.py
│   │   └── stealth.py          # Anti-detection
│   ├── discovery/
│   │   ├── query_builder.py    # Search URL generation
│   │   └── listing_scraper.py  # Job ID extraction
│   ├── evaluation/
│   │   └── filter_chain.py     # Company/title blocking
│   ├── submission/
│   │   ├── form_handler.py     # Multi-step form navigation
│   │   ├── field_filler.py     # Phone, text, dropdown, radio filling
│   │   └── resume_picker.py    # Resume upload / card selection
│   └── reporting/
│       ├── tracker.py          # SQLite history database
│       ├── console.py          # Rich console output
│       └── data_export.py      # JSON/CSV export
├── dashboard/
│   └── index.html              # Log viewer UI (single-file)
└── tests/
    ├── test_settings.py
    ├── test_query_builder.py
    ├── test_filter_chain.py
    └── test_orchestrator.py
```

## Quick Start

### 1. Install dependencies

```bash
cd talentpilot
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
playwright install chromium
```

### 2. Configure

Edit `settings.yaml` with your LinkedIn credentials and job search preferences:

```yaml
email: "your@email.com"
password: "your-password"

keywords:
  - "frontend"
  - "react"

locations:
  - "NorthAmerica"

resume_file_path: "/path/to/your/resume.pdf"
simulation_mode: true          # Dry run — no actual submissions
max_submissions_per_session: 5
```

Edit `responses.yaml` with your form answers (name, phone, experience levels, etc.).

### 3. Run

```bash
# Dry run (simulation mode)
python -m talentpilot

# Live mode — set simulation_mode: false in settings.yaml
```

### 4. View logs

Open `dashboard/index.html` in your browser to see application history, session stats, and export data.

## Environment Variables

Any setting can be overridden via environment variables prefixed with `TALENTPILOT_`:

```bash
export TALENTPILOT_EMAIL="me@example.com"
export TALENTPILOT_SIMULATION_MODE=true
```

## Data Layer

Application history is stored in `.state/history.db` (SQLite) with four tables:

- **postings** — Every job encountered (title, company, URL, location)
- **submissions** — Every application attempt (outcome, duration, failure reason)
- **sessions** — Per-run session stats (inspected, submitted, filtered, failed)
- **status_history** — Manual status updates (applied → interview → offer)

### Export

```python
from talentpilot.reporting.tracker import SubmissionTracker
tracker = SubmissionTracker(".state/history.db")
print(tracker.export_json())   # JSON export
print(tracker.export_csv())    # CSV export
tracker.close()
```

## Docker

```bash
docker compose up --build
```

Mount your `settings.yaml` and `responses.yaml` via the compose file.

## Tests

```bash
pytest tests/ -v
```

## Key Features

- **Playwright async** — faster than Selenium, built-in stealth
- **Resume upload** — auto-detects file inputs and uploads your PDF
- **Smart form filling** — matches labels to your responses.yaml answers
- **JS fallback** — handles LinkedIn's SDUI / hashed class names
- **Page recovery** — auto-recovers from stale browser pages
- **Session persistence** — reuses login across runs
- **SQLite tracking** — full application history, UI-ready schema
- **Simulation mode** — test the full pipeline without submitting

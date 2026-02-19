"""Shared test fixtures."""

from __future__ import annotations

import pytest


@pytest.fixture()
def tmp_settings_yaml(tmp_path):
    """Write a minimal settings.yaml and return its path."""
    content = """\
email: "test@example.com"
password: "hunter2"
headless: true
keywords:
  - "python"
locations:
  - "NorthAmerica"
experience_levels:
  - "Entry level"
date_posted: "Past Week"
job_types:
  - "Full-time"
remote_options:
  - "Remote"
salary_bracket: "$80,000+"
sort_order: "recent"
blocked_companies:
  - "SpamCorp"
blocked_titles:
  - "senior"
simulation_mode: true
max_submissions_per_session: 5
state_dir: "{state}"
""".format(state=str(tmp_path / ".state"))
    p = tmp_path / "settings.yaml"
    p.write_text(content)
    return p

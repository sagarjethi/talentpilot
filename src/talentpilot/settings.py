"""Pydantic-based settings loaded from YAML with env-var overrides."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class AppSettings(BaseSettings):
    """Application configuration with YAML + env var support.

    Env vars are prefixed with ``TALENTPILOT_`` and use ``__`` for nesting.
    Example: ``TALENTPILOT_EMAIL=me@example.com``
    """

    model_config = {"env_prefix": "TALENTPILOT_"}

    # --- credentials ---
    email: str = ""
    password: str = ""

    # --- browser ---
    headless: bool = False
    chrome_profile_path: str = ""
    slow_mo: int = 50  # ms between Playwright actions

    # --- search ---
    keywords: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    experience_levels: list[str] = Field(default_factory=list)
    date_posted: str = "Past Week"
    job_types: list[str] = Field(default_factory=list)
    remote_options: list[str] = Field(default_factory=list)
    salary_bracket: str = ""
    sort_order: str = "recent"

    # --- filtering ---
    blocked_companies: list[str] = Field(default_factory=list)
    blocked_titles: list[str] = Field(default_factory=list)
    follow_companies: bool = False

    # --- applicant profile ---
    applicant_experience_years: int = 3  # total years of work experience

    # --- submission ---
    preferred_resume_index: int = 1  # 1-based
    resume_file_path: str = ""  # path to resume PDF/DOC for upload
    phone_number: str = ""
    simulation_mode: bool = False
    max_submissions_per_session: int = 0  # 0 = unlimited

    # --- paths ---
    state_dir: str = ".state"
    responses_file: str = "responses.yaml"

    @field_validator("sort_order")
    @classmethod
    def _normalise_sort(cls, v: str) -> str:
        return v.strip().lower()

    # ---- factory ----

    @classmethod
    def from_yaml(cls, path: str | Path | None = None) -> "AppSettings":
        """Load settings from a YAML file, then overlay env vars.

        Env vars (``TALENTPILOT_*``) take priority over YAML values.
        """
        import os

        if path is None:
            path = _PROJECT_ROOT / "settings.yaml"
        path = Path(path)
        raw: dict[str, Any] = {}
        if path.exists():
            with open(path) as fh:
                raw = yaml.safe_load(fh) or {}

        # Let env vars override YAML: remove YAML keys that have an env override
        prefix = "TALENTPILOT_"
        for key in list(raw.keys()):
            env_key = f"{prefix}{key.upper()}"
            if env_key in os.environ:
                del raw[key]

        return cls(**raw)


def load_responses(path: str | Path | None = None) -> dict[str, dict[str, str]]:
    """Load the form-response lookup tables from *responses.yaml*."""
    if path is None:
        path = _PROJECT_ROOT / "responses.yaml"
    path = Path(path)
    if not path.exists():
        return {"input_field": {}, "radio": {}, "dropdown": {}}
    with open(path) as fh:
        data = yaml.safe_load(fh) or {}
    return {
        "input_field": {str(k).lower(): str(v) for k, v in data.get("input_field", {}).items()},
        "radio": {str(k).lower(): str(v) for k, v in data.get("radio", {}).items()},
        "dropdown": {str(k).lower(): str(v) for k, v in data.get("dropdown", {}).items()},
    }

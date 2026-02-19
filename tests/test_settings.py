"""Tests for settings loading and validation."""

from __future__ import annotations

import os

from talentpilot.settings import AppSettings


def test_load_from_yaml(tmp_settings_yaml):
    settings = AppSettings.from_yaml(tmp_settings_yaml)
    assert settings.email == "test@example.com"
    assert settings.headless is True
    assert settings.keywords == ["python"]
    assert settings.blocked_companies == ["SpamCorp"]
    assert settings.simulation_mode is True
    assert settings.max_submissions_per_session == 5


def test_env_var_override(tmp_settings_yaml, monkeypatch):
    monkeypatch.setenv("TALENTPILOT_EMAIL", "override@example.com")
    settings = AppSettings.from_yaml(tmp_settings_yaml)
    assert settings.email == "override@example.com"


def test_sort_order_normalised(tmp_settings_yaml):
    settings = AppSettings.from_yaml(tmp_settings_yaml)
    assert settings.sort_order == "recent"


def test_defaults_when_no_file(tmp_path):
    settings = AppSettings.from_yaml(tmp_path / "nonexistent.yaml")
    assert settings.keywords == []
    assert settings.simulation_mode is False

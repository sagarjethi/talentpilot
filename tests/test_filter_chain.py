"""Tests for the filter chain."""

from __future__ import annotations

from talentpilot.evaluation.filter_chain import build_filter_chain
from talentpilot.models import JobPosting


def _posting(title: str = "Engineer", company: str = "Acme") -> JobPosting:
    return JobPosting(
        platform="linkedin",
        platform_id="123",
        url="https://example.com",
        title=title,
        company=company,
    )


def test_no_filters():
    chain = build_filter_chain([], [])
    assert chain is None


def test_company_blocked():
    chain = build_filter_chain(["SpamCorp"], [])
    assert chain is not None
    assert chain.evaluate(_posting(company="SpamCorp Inc.")) is not None


def test_company_not_blocked():
    chain = build_filter_chain(["SpamCorp"], [])
    assert chain is not None
    assert chain.evaluate(_posting(company="GoodCo")) is None


def test_title_blocked():
    chain = build_filter_chain([], ["senior"])
    assert chain is not None
    assert chain.evaluate(_posting(title="Senior Engineer")) is not None


def test_title_not_blocked():
    chain = build_filter_chain([], ["senior"])
    assert chain is not None
    assert chain.evaluate(_posting(title="Junior Engineer")) is None


def test_combined_chain():
    chain = build_filter_chain(["BadCo"], ["intern"])
    assert chain is not None
    # Company blocked
    assert chain.evaluate(_posting(company="BadCo Ltd")) is not None
    # Title blocked
    assert chain.evaluate(_posting(title="Intern Developer")) is not None
    # Both clean
    assert chain.evaluate(_posting(title="Dev", company="GoodCo")) is None

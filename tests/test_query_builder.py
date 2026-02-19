"""Tests for URL generation."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from talentpilot.discovery.query_builder import build_search_url
from talentpilot.models import SearchCriteria


def _parse(url: str) -> dict[str, list[str]]:
    return parse_qs(urlparse(url).query)


def test_basic_url():
    c = SearchCriteria(keywords="python", location="NorthAmerica")
    url = build_search_url(c)
    params = _parse(url)
    assert params["keywords"] == ["python"]
    assert params["f_AL"] == ["true"]
    assert params["geoId"] == ["102221843"]


def test_experience_level():
    c = SearchCriteria(
        keywords="react",
        location="Europe",
        experience_levels=("Entry level", "Mid-Senior level"),
    )
    url = build_search_url(c)
    params = _parse(url)
    assert "2" in params["f_E"][0]
    assert "4" in params["f_E"][0]


def test_job_types():
    c = SearchCriteria(
        keywords="dev",
        location="Asia",
        job_types=("Full-time", "Contract"),
    )
    url = build_search_url(c)
    params = _parse(url)
    assert "F" in params["f_JT"][0]
    assert "C" in params["f_JT"][0]


def test_salary_bracket():
    c = SearchCriteria(
        keywords="eng",
        location="Australia",
        salary_bracket="$120,000+",
    )
    url = build_search_url(c)
    params = _parse(url)
    assert params["f_SB2"] == ["5"]


def test_sort_recent():
    c = SearchCriteria(keywords="data", location="Africa", sort_order="recent")
    url = build_search_url(c)
    params = _parse(url)
    assert params["sortBy"] == ["DD"]


def test_custom_location_no_geoid():
    c = SearchCriteria(keywords="ml", location="San Francisco")
    url = build_search_url(c)
    params = _parse(url)
    assert "geoId" not in params
    assert params["location"] == ["San Francisco"]

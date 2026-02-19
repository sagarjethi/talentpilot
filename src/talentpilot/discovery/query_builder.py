"""Pure-function URL builder for LinkedIn job search."""

from __future__ import annotations

from urllib.parse import quote, urlencode

from talentpilot.models import SearchCriteria
from talentpilot.settings import AppSettings

_BASE = "https://www.linkedin.com/jobs/search/"

# ---- lookup tables ----

_GEO_IDS: dict[str, str] = {
    "asia": "102393603",
    "europe": "100506914",
    "northamerica": "102221843",
    "southamerica": "104514572",
    "australia": "101452733",
    "africa": "103537801",
}

_EXPERIENCE_CODES: dict[str, str] = {
    "internship": "1",
    "entry level": "2",
    "associate": "3",
    "mid-senior level": "4",
    "director": "5",
    "executive": "6",
}

_JOB_TYPE_CODES: dict[str, str] = {
    "full-time": "F",
    "part-time": "P",
    "contract": "C",
    "temporary": "T",
    "volunteer": "V",
    "internship": "I",
    "other": "O",
}

_REMOTE_CODES: dict[str, str] = {
    "on-site": "1",
    "remote": "2",
    "hybrid": "3",
}

_SALARY_CODES: dict[str, str] = {
    "$40,000+": "1",
    "$60,000+": "2",
    "$80,000+": "3",
    "$100,000+": "4",
    "$120,000+": "5",
    "$140,000+": "6",
    "$160,000+": "7",
    "$180,000+": "8",
    "$200,000+": "9",
}

_DATE_SECONDS: dict[str, str] = {
    "past month": "r2592000",
    "past week": "r604800",
    "past 24 hours": "r86400",
}


def _encode_multi(codes: list[str]) -> str:
    """Join multiple filter codes with URL-encoded commas."""
    return ",".join(codes)


def _resolve_location(name: str) -> tuple[str, str]:
    """Return ``(location_param, geo_id_param)`` for *name*."""
    key = name.strip().lower().replace(" ", "")
    geo_id = _GEO_IDS.get(key, "")
    return name, geo_id


def build_search_criteria(settings: AppSettings) -> list[SearchCriteria]:
    """Expand all keyword × location combinations into SearchCriteria objects."""
    results: list[SearchCriteria] = []
    for kw in settings.keywords:
        for loc in settings.locations:
            results.append(
                SearchCriteria(
                    keywords=kw,
                    location=loc,
                    experience_levels=tuple(settings.experience_levels),
                    date_posted=settings.date_posted,
                    job_types=tuple(settings.job_types),
                    remote_options=tuple(settings.remote_options),
                    salary_bracket=settings.salary_bracket,
                    sort_order=settings.sort_order,
                )
            )
    return results


def build_search_url(criteria: SearchCriteria) -> str:
    """Convert a single *SearchCriteria* into a fully-formed LinkedIn URL."""
    params: dict[str, str] = {"f_AL": "true"}

    # keywords
    params["keywords"] = criteria.keywords

    # location + geoId
    location_label, geo_id = _resolve_location(criteria.location)
    params["location"] = location_label
    if geo_id:
        params["geoId"] = geo_id

    # experience levels
    exp_codes = [
        _EXPERIENCE_CODES[e.strip().lower()]
        for e in criteria.experience_levels
        if e.strip().lower() in _EXPERIENCE_CODES
    ]
    if exp_codes:
        params["f_E"] = _encode_multi(exp_codes)

    # date posted
    dp_key = criteria.date_posted.strip().lower()
    if dp_key in _DATE_SECONDS:
        params["f_TPR"] = _DATE_SECONDS[dp_key]

    # job type
    jt_codes = [
        _JOB_TYPE_CODES[j.strip().lower()]
        for j in criteria.job_types
        if j.strip().lower() in _JOB_TYPE_CODES
    ]
    if jt_codes:
        params["f_JT"] = _encode_multi(jt_codes)

    # remote
    rm_codes = [
        _REMOTE_CODES[r.strip().lower()]
        for r in criteria.remote_options
        if r.strip().lower() in _REMOTE_CODES
    ]
    if rm_codes:
        params["f_WT"] = _encode_multi(rm_codes)

    # salary
    sal_key = criteria.salary_bracket.strip()
    if sal_key in _SALARY_CODES:
        params["f_SB2"] = _SALARY_CODES[sal_key]

    # sort
    if criteria.sort_order == "recent":
        params["sortBy"] = "DD"
    elif criteria.sort_order in ("relevant", "relevent"):
        params["sortBy"] = "R"

    return f"{_BASE}?{urlencode(params, quote_via=quote)}"


def build_search_urls(settings: AppSettings) -> list[str]:
    """Build all search URLs from the application settings."""
    return [build_search_url(c) for c in build_search_criteria(settings)]

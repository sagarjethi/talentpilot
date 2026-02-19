"""Scrape job IDs from LinkedIn search result pages."""

from __future__ import annotations

import asyncio
import logging
import math
from typing import Any

from talentpilot.browser.base import BrowserAdapter
from talentpilot.exceptions import SessionExpiredError

logger = logging.getLogger(__name__)

_RESULTS_PER_PAGE = 25
_MAX_PAGES = 40

_TOTAL_JOBS_SELECTOR = "small"
_JOB_CARD_SELECTOR = "li[data-occludable-job-id]"


def compute_page_count(total_text: str) -> int:
    """Derive the number of result pages from the total-jobs text.

    LinkedIn shows e.g. ``"1,234 results"`` or just ``"25"``.
    """
    stripped = total_text.strip().replace(",", "")
    parts = stripped.split()
    try:
        n = int(parts[0]) if parts else int(stripped)
    except ValueError:
        return 1
    pages = math.ceil(n / _RESULTS_PER_PAGE)
    return min(pages, _MAX_PAGES)


async def extract_job_ids(adapter: BrowserAdapter) -> list[str]:
    """Return job IDs visible on the current results page.

    Excludes IDs already marked as "Applied".
    """
    cards = await adapter.query_all(_JOB_CARD_SELECTOR)
    all_ids: list[str] = []

    for card in cards:
        job_id = await card.get_attribute("data-occludable-job-id")
        if not job_id:
            continue
        # Check if this card has an "Applied" label
        applied_marker = await card.query_selector("li-icon[type='success-pebble-icon']")
        if applied_marker:
            continue
        all_ids.append(job_id.strip())

    logger.debug("Extracted %d unapplied job IDs from page.", len(all_ids))
    return all_ids


async def scrape_search_results(
    adapter: BrowserAdapter, base_url: str
) -> list[str]:
    """Iterate all result pages for *base_url* and collect job IDs."""
    await adapter.navigate(base_url)
    await asyncio.sleep(3)

    if await adapter.is_auth_redirect():
        raise SessionExpiredError("Auth redirect detected on search page.")

    # Check if LinkedIn shows "No matching jobs found" or similar
    no_results = await adapter.evaluate("""
        () => {
            const body = document.body.innerText.toLowerCase();
            return body.includes('no matching jobs') ||
                   body.includes('no results found') ||
                   body.includes('0 results') ||
                   body.includes('no jobs found');
        }
    """)
    if no_results:
        logger.info("No matching jobs for this search — skipping: %s", base_url)
        return []

    total_text = await adapter.inner_text(_TOTAL_JOBS_SELECTOR)
    if not total_text:
        logger.info("No results text found for URL: %s", base_url)
        return []

    pages = compute_page_count(total_text)
    if pages == 0:
        logger.info("Zero result pages — skipping: %s", base_url)
        return []
    logger.info("Found %s — scanning %d page(s).", total_text.strip(), pages)

    collected: list[str] = []
    for page_idx in range(pages):
        page_url = f"{base_url}&start={page_idx * _RESULTS_PER_PAGE}"
        if page_idx > 0:
            await adapter.navigate(page_url)
            await asyncio.sleep(2)

            if await adapter.is_auth_redirect():
                raise SessionExpiredError("Auth redirect detected during pagination.")

        ids = await extract_job_ids(adapter)
        collected.extend(ids)

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for jid in collected:
        if jid not in seen:
            seen.add(jid)
            unique.append(jid)

    logger.info("Total unique job IDs collected: %d", len(unique))
    return unique

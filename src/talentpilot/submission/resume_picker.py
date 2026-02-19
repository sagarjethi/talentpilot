"""Resume selection and upload on Easy Apply forms."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from talentpilot.browser.base import BrowserAdapter

logger = logging.getLogger(__name__)

# Old-style LinkedIn: select from pre-uploaded resumes
_REQUIRED_UPLOAD_SELECTOR = ".jobs-document-upload__title--is-required"
_RESUME_CARD_SELECTOR = "div[class*='ui-attachment--pdf']"

# New-style: file upload input
_FILE_INPUT_SELECTORS = [
    "input[type='file']",
    "input[name*='resume']",
    "input[accept*='.pdf']",
]


async def select_resume(
    adapter: BrowserAdapter,
    preferred_index: int = 1,
    resume_file_path: str = "",
) -> None:
    """Pick or upload a resume on the current form page.

    Handles two modes:
    1. **File upload**: If a file input is found and *resume_file_path* is set,
       upload the resume file directly.
    2. **Card selection**: If LinkedIn shows pre-uploaded resume cards,
       select the one at *preferred_index* (1-based).
    """
    # --- Mode 1: File upload ---
    if resume_file_path and Path(resume_file_path).exists():
        uploaded = await _try_file_upload(adapter, resume_file_path)
        if uploaded:
            return

    # --- Mode 2: Card selection (old-style) ---
    await _try_card_selection(adapter, preferred_index)


async def _try_file_upload(adapter: BrowserAdapter, file_path: str) -> bool:
    """Attempt to find a file input and upload the resume.

    Returns ``True`` if upload was triggered.
    """
    for selector in _FILE_INPUT_SELECTORS:
        inputs = await adapter.query_all(selector)
        for inp in inputs:
            try:
                await inp.set_input_files(file_path)
                logger.info("Uploaded resume via file input: %s", selector)
                return True
            except Exception:
                continue

    # JS fallback: find hidden file inputs (LinkedIn sometimes hides them)
    try:
        found = await adapter.evaluate("""
            () => {
                const inputs = document.querySelectorAll('input[type="file"]');
                return inputs.length > 0;
            }
        """)
        if found:
            file_input = await adapter.query('input[type="file"]', timeout=3_000)
            if file_input:
                await file_input.set_input_files(file_path)
                logger.info("Uploaded resume via hidden file input.")
                return True
    except Exception as exc:
        logger.debug("File upload JS fallback failed: %s", exc)

    return False


async def _try_card_selection(adapter: BrowserAdapter, preferred_index: int) -> None:
    """Select from pre-uploaded resume cards (old LinkedIn flow)."""
    required_marker = await adapter.query(_REQUIRED_UPLOAD_SELECTOR, timeout=3_000)
    if required_marker is None:
        return

    resumes = await adapter.query_all(_RESUME_CARD_SELECTOR)
    if not resumes:
        logger.debug("No resume cards found on page.")
        return

    idx = max(0, preferred_index - 1)
    if idx >= len(resumes):
        idx = 0

    target = resumes[idx]
    try:
        aria = await target.get_attribute("aria-label")
        if aria and "select this resume" in aria.lower():
            await target.click()
        else:
            await target.click()
        logger.info("Selected resume card at index %d.", preferred_index)
    except Exception as exc:
        logger.warning("Failed to click resume card: %s", exc)

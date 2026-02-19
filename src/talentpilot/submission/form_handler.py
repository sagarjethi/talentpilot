"""Multi-step Easy Apply form navigation."""

from __future__ import annotations

import asyncio
import logging
import math
from typing import Any

from talentpilot.browser.base import BrowserAdapter
from talentpilot.exceptions import FormSubmissionError
from talentpilot.submission.field_filler import populate_visible_fields
from talentpilot.submission.resume_picker import select_resume

logger = logging.getLogger(__name__)

# Multiple selector candidates for each action button
_SUBMIT_SELECTORS = [
    "button[aria-label='Submit application']",
    "button[aria-label='Submit']",
    "button:has-text('Submit application')",
    "button:has-text('Submit')",
]

_REVIEW_SELECTORS = [
    "button[aria-label='Review your application']",
    "button[aria-label='Review']",
    "button:has-text('Review')",
]

_NEXT_SELECTORS = [
    "button[aria-label='Continue to next step']",
    "button[aria-label='Next']",
    "button:has-text('Next')",
    "button:has-text('Continue')",
]

_PROGRESS_SELECTOR = "progress"
_FOLLOW_CHECKBOX = "label[for*='follow-company']"

# Max form steps to prevent infinite loops
_MAX_FORM_STEPS = 10


class ApplicationFormHandler:
    """Navigates Easy Apply forms — single-page and multi-step."""

    def __init__(
        self,
        adapter: BrowserAdapter,
        preferred_resume_index: int,
        phone: str,
        responses: dict[str, dict[str, str]],
        follow_companies: bool,
        simulation: bool,
        resume_file_path: str = "",
        experience_years: int = 3,
    ) -> None:
        self._adapter = adapter
        self._resume_idx = preferred_resume_index
        self._phone = phone
        self._responses = responses
        self._follow_companies = follow_companies
        self._simulation = simulation
        self._resume_path = resume_file_path
        self._experience_years = experience_years

    async def _find_button(self, selectors: list[str], timeout: float = 3_000) -> Any | None:
        """Try multiple selectors and return the first matching button."""
        for sel in selectors:
            btn = await self._adapter.query(sel, timeout=timeout)
            if btn is not None:
                return btn
        return None

    async def attempt_submission(self) -> str:
        """Try submitting the current Easy Apply form.

        Returns an outcome string: ``"succeeded"``, ``"dry_run"``, or raises
        :class:`FormSubmissionError`.
        """
        await asyncio.sleep(2)

        # Fill any visible fields on the first page (contact info form)
        await select_resume(self._adapter, self._resume_idx, self._resume_path)
        await populate_visible_fields(self._adapter, self._phone, self._responses, self._experience_years)

        # Try single-page fast path — look for Submit button (scroll to find it)
        submit_btn = await self._find_submit_with_scroll()
        if submit_btn:
            return await self._submit_final(submit_btn)

        # Click Next/Continue if available
        await self._scroll_modal_to_bottom()
        next_btn = await self._find_button(_NEXT_SELECTORS)
        if next_btn:
            try:
                await next_btn.evaluate("el => el.click()")
            except Exception:
                await next_btn.click(force=True, timeout=5_000)
            await asyncio.sleep(2)

        # Check again for direct Submit (2-page form)
        submit_btn = await self._find_submit_with_scroll()
        if submit_btn:
            await populate_visible_fields(self._adapter, self._phone, self._responses, self._experience_years)
            return await self._submit_final(submit_btn)

        # Multi-step path
        return await self._navigate_multi_step()

    async def _submit_final(self, submit_btn: Any) -> str:
        """Handle the final submit step."""
        if self._simulation:
            logger.info("[Simulation] Would submit application.")
            await self._dismiss_modal()
            return "dry_run"

        # Unfollow company if configured
        if not self._follow_companies:
            follow_lbl = await self._adapter.query(_FOLLOW_CHECKBOX, timeout=2_000)
            if follow_lbl:
                try:
                    await follow_lbl.evaluate("el => el.click()")
                except Exception:
                    pass

        # Scroll to Submit button and click
        await self._scroll_modal_to_bottom()
        await asyncio.sleep(0.5)

        # Try JS click on the element handle
        clicked = False
        try:
            await submit_btn.evaluate("el => el.click()")
            clicked = True
        except Exception:
            pass

        # Fallback: force click via Playwright
        if not clicked:
            try:
                await submit_btn.click(force=True, timeout=5_000)
                clicked = True
            except Exception:
                pass

        # Last resort: pure JS find-and-click
        if not clicked:
            clicked = await self._js_click_submit()

        if not clicked:
            raise FormSubmissionError("Submit button not clickable after all attempts.")

        await asyncio.sleep(3)
        await self._dismiss_modal()
        logger.info("Application submitted successfully.")
        return "succeeded"

    async def _scroll_modal_to_bottom(self) -> None:
        """Scroll the Easy Apply modal container to the bottom.

        The review page and some form steps have the Submit button
        below the visible area.  Scrolling ensures Playwright can
        find and click it.
        """
        try:
            await self._adapter.evaluate("""
                () => {
                    // Strategy 1: Find any scrollable element inside modal/dialog
                    const dialog = document.querySelector('[role="dialog"]') ||
                                   document.querySelector('.artdeco-modal');
                    if (dialog) {
                        // Find all scrollable children
                        const allElements = dialog.querySelectorAll('*');
                        for (const el of allElements) {
                            if (el.scrollHeight > el.clientHeight + 10 &&
                                el.clientHeight > 100) {
                                el.scrollTo({ top: el.scrollHeight, behavior: 'instant' });
                            }
                        }
                        // Also scroll the dialog itself
                        dialog.scrollTo({ top: dialog.scrollHeight, behavior: 'instant' });
                    }

                    // Strategy 2: Try known class patterns
                    const candidates = [
                        '.jobs-easy-apply-content',
                        '.artdeco-modal__content',
                        '.jobs-easy-apply-modal__content',
                        '[class*="easy-apply"] [class*="content"]',
                        '[class*="modal"] [class*="content"]',
                    ];
                    for (const sel of candidates) {
                        const c = document.querySelector(sel);
                        if (c && c.scrollHeight > c.clientHeight) {
                            c.scrollTo({ top: c.scrollHeight, behavior: 'instant' });
                        }
                    }

                    // Strategy 3: Scroll the Submit button into view if it exists
                    const buttons = document.querySelectorAll('button');
                    for (const btn of buttons) {
                        const text = btn.innerText.trim().toLowerCase();
                        if (text.includes('submit application') || text.includes('submit')) {
                            btn.scrollIntoView({ block: 'center', behavior: 'instant' });
                            return;
                        }
                    }
                }
            """)
            await asyncio.sleep(1)
        except Exception:
            pass

    async def _find_submit_with_scroll(self) -> Any | None:
        """Scroll modal to bottom and find the Submit button.

        Uses both Playwright selectors and JS fallback.
        """
        # First try without scroll
        btn = await self._find_button(_SUBMIT_SELECTORS, timeout=2_000)
        if btn:
            return btn

        # Scroll to bottom and try again
        await self._scroll_modal_to_bottom()
        btn = await self._find_button(_SUBMIT_SELECTORS, timeout=2_000)
        if btn:
            return btn

        # JS fallback: scroll Submit button into view
        try:
            found = await self._adapter.evaluate("""
                () => {
                    const buttons = document.querySelectorAll('button');
                    for (const btn of buttons) {
                        const text = btn.innerText.trim().toLowerCase();
                        const aria = (btn.getAttribute('aria-label') || '').toLowerCase();
                        if (text.includes('submit') || aria.includes('submit')) {
                            btn.scrollIntoView({ block: 'center', behavior: 'instant' });
                            return true;
                        }
                    }
                    return false;
                }
            """)
            if found:
                await asyncio.sleep(1)
                return await self._find_button(_SUBMIT_SELECTORS, timeout=3_000)
        except Exception:
            pass

        return None

    async def _js_click_submit(self) -> bool:
        """Last resort: find and click 'Submit application' button entirely via JS."""
        try:
            return await self._adapter.evaluate("""
                () => {
                    const buttons = document.querySelectorAll('button');
                    for (const btn of buttons) {
                        const text = btn.innerText.trim();
                        const aria = btn.getAttribute('aria-label') || '';
                        if (text.toLowerCase().includes('submit application') ||
                            aria.toLowerCase().includes('submit application') ||
                            text.toLowerCase() === 'submit') {
                            // Scroll into view first
                            btn.scrollIntoView({ block: 'center', behavior: 'instant' });
                            // Small delay via setTimeout for scroll to complete
                            btn.click();
                            return true;
                        }
                    }
                    return false;
                }
            """)
        except Exception:
            return False

    async def _dismiss_modal(self) -> None:
        """Close the Easy Apply modal / confirmation dialog if present."""
        dismiss_selectors = [
            "button[aria-label='Dismiss']",
            "button[aria-label='Close']",
            "button[data-test-modal-close-btn]",
            "button.artdeco-modal__dismiss",
            "button.artdeco-toast-item__dismiss",
        ]
        for sel in dismiss_selectors:
            btn = await self._adapter.query(sel, timeout=2_000)
            if btn:
                try:
                    await btn.click()
                    await asyncio.sleep(1)
                    logger.debug("Dismissed modal via %s.", sel)
                    return
                except Exception:
                    continue

    async def _navigate_multi_step(self) -> str:
        """Page through a multi-step application form."""
        for step in range(_MAX_FORM_STEPS):
            # Scroll modal so all fields and buttons are reachable
            await self._scroll_modal_to_bottom()
            await populate_visible_fields(self._adapter, self._phone, self._responses, self._experience_years)
            await select_resume(self._adapter, self._resume_idx, self._resume_path)

            # Check for Submit — scroll to bottom first (review page has it below fold)
            submit_btn = await self._find_submit_with_scroll()
            if submit_btn:
                return await self._submit_final(submit_btn)

            # Check for Review button (penultimate step)
            await self._scroll_modal_to_bottom()
            review_btn = await self._find_button(_REVIEW_SELECTORS, timeout=2_000)
            if review_btn:
                try:
                    await review_btn.evaluate("el => el.click()")
                except Exception:
                    await review_btn.click(force=True, timeout=5_000)
                await asyncio.sleep(2)
                continue  # Loop back to check for Submit

            # Click Next/Continue
            await self._scroll_modal_to_bottom()
            next_btn = await self._find_button(_NEXT_SELECTORS, timeout=3_000)
            if next_btn is None:
                # Last attempt: try JS to find any actionable button
                clicked_any = await self._js_click_bottom_button()
                if clicked_any:
                    await asyncio.sleep(2)
                    continue

                if self._simulation:
                    logger.info("[Simulation] Would submit (no nav button found).")
                    await self._dismiss_modal()
                    return "dry_run"
                raise FormSubmissionError(
                    "No Submit, Review, or Next button found on form step."
                )
            try:
                await next_btn.evaluate("el => el.click()")
            except Exception:
                await next_btn.click(force=True, timeout=5_000)
            await asyncio.sleep(2)

        # Hit max steps
        if self._simulation:
            logger.info("[Simulation] Would submit (max steps reached).")
            await self._dismiss_modal()
            return "dry_run"
        raise FormSubmissionError(f"Exceeded max form steps ({_MAX_FORM_STEPS}).")

    async def _js_click_bottom_button(self) -> bool:
        """JS fallback: find and click the bottom-most action button in the modal."""
        try:
            return await self._adapter.evaluate("""
                () => {
                    // Find all buttons in the modal footer area
                    const buttons = document.querySelectorAll('button');
                    const actionButtons = [];
                    for (const btn of buttons) {
                        const text = btn.innerText.trim().toLowerCase();
                        const aria = (btn.getAttribute('aria-label') || '').toLowerCase();
                        if (text.includes('submit') || text.includes('next') ||
                            text.includes('review') || text.includes('continue') ||
                            aria.includes('submit') || aria.includes('next') ||
                            aria.includes('review') || aria.includes('continue')) {
                            actionButtons.push(btn);
                        }
                    }
                    if (actionButtons.length > 0) {
                        // Click the last matching button (usually the primary action)
                        const btn = actionButtons[actionButtons.length - 1];
                        btn.scrollIntoView({ block: 'center' });
                        btn.click();
                        return true;
                    }
                    return false;
                }
            """)
        except Exception:
            return False

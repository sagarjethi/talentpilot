"""Playwright-backed implementation of BrowserAdapter."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from talentpilot.browser.stealth import apply_stealth
from talentpilot.exceptions import BrowserLaunchError

logger = logging.getLogger(__name__)

_AUTH_REDIRECT_FRAGMENTS: frozenset[str] = frozenset(
    {"/login", "/checkpoint", "/authwall", "/uas/login"}
)


class PlaywrightAdapter:
    """Async browser driver built on Playwright Chromium."""

    def __init__(self) -> None:
        self._pw: Any = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    @property
    def page(self) -> Page:
        assert self._page is not None, "Browser not launched — call launch() first."
        return self._page

    # --- lifecycle ---

    async def launch(
        self,
        headless: bool = False,
        slow_mo: int = 50,
        storage_state_path: str | None = None,
    ) -> None:
        try:
            self._pw = await async_playwright().start()
            self._browser = await self._pw.chromium.launch(
                headless=headless,
                slow_mo=slow_mo,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                ],
            )
            ctx_kwargs: dict[str, Any] = {
                "viewport": {"width": 1280, "height": 900},
                "locale": "en-US",
                "user_agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "extra_http_headers": {
                    "Accept-Language": "en-US,en;q=0.9",
                },
            }
            if storage_state_path and Path(storage_state_path).exists():
                ctx_kwargs["storage_state"] = storage_state_path

            self._context = await self._browser.new_context(**ctx_kwargs)
            self._page = await self._context.new_page()
            await apply_stealth(self._page)
            logger.info("Browser launched (headless=%s).", headless)
        except Exception as exc:
            raise BrowserLaunchError(f"Failed to start Playwright Chromium: {exc}") from exc

    async def close(self) -> None:
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()
        logger.info("Browser closed.")

    # --- navigation ---

    async def navigate(self, url: str, wait_until: str = "domcontentloaded") -> None:
        try:
            await self.page.goto(url, wait_until=wait_until)
        except Exception as exc:
            if "Target" in str(exc) and "closed" in str(exc):
                await self.ensure_valid_page()
                await self.page.goto(url, wait_until=wait_until)
            else:
                raise

    # --- querying ---

    async def query(self, selector: str, *, timeout: float = 5_000) -> Any | None:
        try:
            handle = await self.page.wait_for_selector(selector, timeout=timeout)
            return handle
        except Exception as exc:
            if "Target" in str(exc) and "closed" in str(exc):
                await self.ensure_valid_page()
            return None

    async def query_all(self, selector: str) -> list[Any]:
        try:
            return await self.page.query_selector_all(selector)
        except Exception:
            # Page may have been closed — try recovery
            await self.ensure_valid_page()
            try:
                return await self.page.query_selector_all(selector)
            except Exception:
                return []

    # --- interaction ---

    async def fill(self, selector: str, value: str) -> None:
        await self.page.fill(selector, value)

    async def click(self, selector: str, *, timeout: float = 5_000) -> None:
        await self.page.click(selector, timeout=timeout)

    # --- reading ---

    async def inner_text(self, selector: str) -> str:
        el = await self.query(selector)
        if el is None:
            return ""
        return (await el.inner_text()).strip()

    async def inner_html(self, selector: str) -> str:
        el = await self.query(selector)
        if el is None:
            return ""
        return (await el.inner_html()).strip()

    async def get_attribute(self, selector: str, name: str) -> str | None:
        el = await self.query(selector)
        if el is None:
            return None
        return await el.get_attribute(name)

    # --- state ---

    async def save_storage_state(self, path: str) -> None:
        if self._context is None:
            return
        await self._context.storage_state(path=path)
        logger.debug("Storage state saved to %s.", path)

    async def load_storage_state(self, path: str) -> None:
        # Storage state is loaded at context creation; this is a no-op
        # if the context was already created with the state.
        pass

    async def ensure_valid_page(self) -> None:
        """Ensure ``_page`` points to a live, usable page.

        After Easy Apply form submission LinkedIn may close popup pages,
        leaving the adapter with a stale reference.  This method recovers
        by switching to the first remaining page in the context (or opening
        a new one if all pages were closed).
        """
        if self._context is None:
            return

        # If current page is still open, nothing to do
        if self._page and not self._page.is_closed():
            return

        pages = self._context.pages
        if pages:
            self._page = pages[0]
            logger.debug("Recovered page — switched to first open page.")
        else:
            self._page = await self._context.new_page()
            await apply_stealth(self._page)
            logger.debug("All pages were closed — opened a new page.")

    async def close_extra_pages(self) -> None:
        """Close every page except the first one and point ``_page`` at it."""
        if self._context is None:
            return
        pages = self._context.pages
        if len(pages) <= 1:
            if pages:
                self._page = pages[0]
            return
        # Keep the first page, close the rest
        self._page = pages[0]
        for extra in pages[1:]:
            try:
                await extra.close()
            except Exception:
                pass
        logger.debug("Closed %d extra page(s).", len(pages) - 1)

    async def page_url(self) -> str:
        return self.page.url

    async def page_content(self) -> str:
        return await self.page.content()

    async def wait_for_selector(
        self, selector: str, *, state: str = "visible", timeout: float = 10_000
    ) -> Any | None:
        try:
            return await self.page.wait_for_selector(selector, state=state, timeout=timeout)
        except Exception:
            return None

    async def is_auth_redirect(self) -> bool:
        """Return ``True`` if the current URL indicates a login/auth redirect."""
        current = self.page.url.lower()
        return any(frag in current for frag in _AUTH_REDIRECT_FRAGMENTS)

    async def evaluate(self, expression: str, arg: Any = None) -> Any:
        try:
            if arg is not None:
                return await self.page.evaluate(expression, arg)
            return await self.page.evaluate(expression)
        except Exception as exc:
            if "Target" in str(exc) and "closed" in str(exc):
                await self.ensure_valid_page()
                if arg is not None:
                    return await self.page.evaluate(expression, arg)
                return await self.page.evaluate(expression)
            raise

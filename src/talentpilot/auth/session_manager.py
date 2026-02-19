"""Login and session persistence via Playwright storage state."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from pathlib import Path

from talentpilot.browser.base import BrowserAdapter
from talentpilot.exceptions import AuthenticationError

logger = logging.getLogger(__name__)

_FEED_URL = "https://www.linkedin.com/feed"
_LOGIN_URL = "https://www.linkedin.com/login"

# Multiple selectors — LinkedIn's DOM varies across sessions/rollouts.
_LOGGED_IN_SELECTORS = [
    "div.feed-identity-module",
    "div.global-nav__me",
    "img.global-nav__me-photo",
    "div[data-control-name='identity_welcome_message']",
    "nav.global-nav",
    "input[aria-label='Search']",
]


class SessionManager:
    """Handles LinkedIn authentication and session storage."""

    def __init__(
        self,
        adapter: BrowserAdapter,
        email: str,
        password: str,
        state_dir: str = ".state",
    ) -> None:
        self._adapter = adapter
        self._email = email
        self._password = password
        self._state_dir = Path(state_dir)
        self._state_dir.mkdir(parents=True, exist_ok=True)

    def _state_file(self) -> Path:
        """Return the path for this account's storage state JSON."""
        digest = hashlib.sha256(self._email.encode()).hexdigest()[:16]
        return self._state_dir / f"session_{digest}.json"

    async def ensure_authenticated(self) -> None:
        """Restore a stored session or perform a fresh login."""
        state_path = self._state_file()

        # Try restoring session from storage state (loaded at browser launch)
        if state_path.exists():
            logger.info("Found stored session — verifying…")
            if await self._verify_logged_in():
                logger.info("Stored session is valid.")
                await self._ensure_english()
                return
            logger.warning("Stored session expired — logging in fresh.")

        await self._perform_login()
        await self._ensure_english()
        await self._adapter.save_storage_state(str(state_path))
        logger.info("Session saved to %s.", state_path)

    async def _verify_logged_in(self) -> bool:
        """Navigate to the feed and check for a logged-in indicator."""
        await self._adapter.navigate(_FEED_URL)
        await asyncio.sleep(4)

        # Check current URL — if redirected away from /feed, not logged in
        current_url = await self._adapter.page_url()
        if "/feed" in current_url:
            return True

        # Also try element-based checks
        for selector in _LOGGED_IN_SELECTORS:
            element = await self._adapter.query(selector, timeout=3_000)
            if element is not None:
                return True

        return False

    async def _perform_login(self) -> None:
        """Enter credentials on the login page and submit."""
        if not self._email or not self._password:
            raise AuthenticationError("Email and password must be configured.")

        await self._adapter.navigate(_LOGIN_URL)
        await asyncio.sleep(2)

        await self._adapter.fill('input#username', self._email)
        await self._adapter.fill('input#password', self._password)
        await self._adapter.click('button[type="submit"]')

        # Retry loop: give user up to ~90 s to handle CAPTCHA / 2FA / verification
        logger.info(
            "Waiting for login to complete. If you see a CAPTCHA or 2FA prompt, "
            "complete it in the browser window…"
        )
        for attempt in range(18):  # 18 × 5 s = 90 s
            await asyncio.sleep(5)
            current_url = await self._adapter.page_url()
            if "/feed" in current_url:
                logger.info("Login succeeded (URL check).")
                return
            # Also check for known logged-in elements without navigating away
            for selector in _LOGGED_IN_SELECTORS:
                el = await self._adapter.query(selector, timeout=2_000)
                if el is not None:
                    logger.info("Login succeeded (element check).")
                    return
            if attempt % 3 == 2:
                logger.info(
                    "Still waiting for login… (%d s elapsed). "
                    "Complete any challenge in the browser.",
                    (attempt + 1) * 5,
                )

        raise AuthenticationError(
            "Login failed after 90 s — check credentials or complete "
            "CAPTCHA / 2FA manually in the browser window."
        )

    async def _ensure_english(self) -> None:
        """Switch LinkedIn UI language to English if it isn't already.

        Uses LinkedIn's language settings API endpoint to change the
        interface language to English (en_US).
        """
        try:
            # Navigate to LinkedIn language settings page
            await self._adapter.navigate(
                "https://www.linkedin.com/mypreferences/d/languages"
            )
            await asyncio.sleep(3)

            # Check if already English by looking at the page content
            is_english = await self._adapter.evaluate("""
                () => {
                    const body = document.body.innerText.toLowerCase();
                    // If we can find "language" in English text, it's likely English
                    return body.includes('language') && body.includes('english');
                }
            """)

            if is_english:
                logger.info("LinkedIn language is already English.")
                return

            # Try to change language via the footer language selector
            # LinkedIn has a language selector in the footer of most pages
            changed = await self._adapter.evaluate("""
                () => {
                    // Look for a language select/dropdown in the footer
                    const selects = document.querySelectorAll('select');
                    for (const sel of selects) {
                        const options = sel.querySelectorAll('option');
                        for (const opt of options) {
                            if (opt.value === 'en_US' || opt.text.includes('English')) {
                                sel.value = opt.value;
                                sel.dispatchEvent(new Event('change', {bubbles: true}));
                                return 'select';
                            }
                        }
                    }

                    // Try clicking an English language link
                    const links = document.querySelectorAll('a');
                    for (const a of links) {
                        const text = a.innerText.trim();
                        if (text === 'English' || text === 'English (English)') {
                            a.click();
                            return 'link';
                        }
                    }

                    return null;
                }
            """)

            if changed:
                logger.info("Switched LinkedIn language to English via %s.", changed)
                await asyncio.sleep(3)
            else:
                # Direct API approach: set language via LinkedIn's settings URL
                await self._adapter.navigate(
                    "https://www.linkedin.com/psettings/select-language?selectedLanguage=en_US"
                )
                await asyncio.sleep(3)

                # Click save/confirm button if present
                save_clicked = await self._adapter.evaluate("""
                    () => {
                        const buttons = document.querySelectorAll('button');
                        for (const btn of buttons) {
                            const text = btn.innerText.trim().toLowerCase();
                            if (text.includes('save') || text.includes('apply') ||
                                text.includes('confirm') || text.includes('حفظ')) {
                                btn.click();
                                return true;
                            }
                        }
                        return false;
                    }
                """)
                if save_clicked:
                    logger.info("Language set to English via settings page.")
                    await asyncio.sleep(3)
                else:
                    logger.warning(
                        "Could not auto-switch language to English. "
                        "Please change it manually in LinkedIn Settings > Language."
                    )
        except Exception as exc:
            logger.warning("Language switch failed: %s — continuing.", exc)

    async def reauthenticate(self) -> None:
        """Delete the stale session and perform a fresh login.

        Called mid-run when a ``SessionExpiredError`` is caught.
        """
        state_path = self._state_file()
        if state_path.exists():
            state_path.unlink()
            logger.info("Deleted stale session file %s.", state_path)

        await self._perform_login()
        await self._ensure_english()
        await self._adapter.save_storage_state(str(state_path))
        logger.info("Re-authentication complete — session saved to %s.", state_path)

    def storage_state_path(self) -> str:
        """Public accessor for the state file path (used at browser launch)."""
        p = self._state_file()
        return str(p) if p.exists() else ""

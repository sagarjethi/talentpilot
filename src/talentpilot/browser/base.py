"""Protocol definition for browser adapters."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class BrowserAdapter(Protocol):
    """Thin abstraction over a browser automation library.

    Every method is async so the pipeline can ``await`` each interaction.
    """

    async def launch(self, headless: bool = False, slow_mo: int = 50) -> None:
        """Start the browser process."""
        ...

    async def close(self) -> None:
        """Shut down the browser and free resources."""
        ...

    async def navigate(self, url: str, wait_until: str = "domcontentloaded") -> None:
        """Navigate to *url* and wait for the specified load event."""
        ...

    async def query(self, selector: str, *, timeout: float = 5_000) -> Any | None:
        """Return the first element matching *selector*, or ``None``."""
        ...

    async def query_all(self, selector: str) -> list[Any]:
        """Return every element matching *selector*."""
        ...

    async def fill(self, selector: str, value: str) -> None:
        """Clear and type *value* into the element matching *selector*."""
        ...

    async def click(self, selector: str, *, timeout: float = 5_000) -> None:
        """Click the element matching *selector*."""
        ...

    async def inner_text(self, selector: str) -> str:
        """Return the visible text of the element matching *selector*."""
        ...

    async def inner_html(self, selector: str) -> str:
        """Return the inner HTML of the element matching *selector*."""
        ...

    async def get_attribute(self, selector: str, name: str) -> str | None:
        """Return the value of attribute *name* on the first match."""
        ...

    async def save_storage_state(self, path: str) -> None:
        """Persist cookies / localStorage to *path* (JSON)."""
        ...

    async def load_storage_state(self, path: str) -> None:
        """Restore cookies / localStorage from *path*."""
        ...

    async def page_url(self) -> str:
        """Return the current page URL."""
        ...

    async def page_content(self) -> str:
        """Return the full page HTML."""
        ...

    async def wait_for_selector(
        self, selector: str, *, state: str = "visible", timeout: float = 10_000
    ) -> Any | None:
        """Wait until *selector* reaches the desired *state*."""
        ...

    async def evaluate(self, expression: str) -> Any:
        """Run a JS expression and return the result."""
        ...

    async def is_auth_redirect(self) -> bool:
        """Return ``True`` if the current URL indicates a login/auth redirect."""
        ...

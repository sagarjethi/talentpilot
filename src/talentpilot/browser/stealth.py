"""Anti-detection helpers for Playwright pages."""

from __future__ import annotations

from typing import Any


async def apply_stealth(page: Any) -> None:
    """Inject JS patches that mask common automation fingerprints."""
    await page.add_init_script("""
        // Remove webdriver flag
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

        // Spoof chrome.runtime to appear as a real Chrome install
        window.chrome = { runtime: {} };

        // Override permissions query for notifications
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) =>
            parameters.name === 'notifications'
                ? Promise.resolve({ state: Notification.permission })
                : originalQuery(parameters);

        // Spoof plugins array (real Chrome always has at least 3)
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5],
        });

        // Spoof language list
        Object.defineProperty(navigator, 'languages', {
            get: () => ['en-US', 'en'],
        });

        // Spoof WebGL vendor / renderer
        const getParameter = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(parameter) {
            if (parameter === 37445) return 'Intel Inc.';
            if (parameter === 37446) return 'Intel Iris OpenGL Engine';
            return getParameter.call(this, parameter);
        };
    """)

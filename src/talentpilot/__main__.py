"""Entry point: ``python -m talentpilot``."""

from __future__ import annotations

import asyncio
import logging
import sys

from talentpilot.orchestrator import ApplicationPipeline
from talentpilot.settings import AppSettings


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )
    # Quiet noisy libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)


async def _async_main() -> None:
    settings = AppSettings.from_yaml()
    pipeline = ApplicationPipeline(settings)
    await pipeline.run()


def main() -> None:
    _configure_logging()
    try:
        asyncio.run(_async_main())
    except KeyboardInterrupt:
        logging.info("Interrupted by user.")
        sys.exit(130)


if __name__ == "__main__":
    main()

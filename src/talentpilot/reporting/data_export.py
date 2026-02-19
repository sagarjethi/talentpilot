"""JSON / CSV export helpers for UI consumption."""

from __future__ import annotations

import logging
from pathlib import Path

from talentpilot.reporting.tracker import SubmissionTracker

logger = logging.getLogger(__name__)


def export_to_file(
    tracker: SubmissionTracker,
    output_dir: str | Path,
    fmt: str = "json",
    since_date: str = "",
) -> Path:
    """Write an export file and return its path.

    *fmt* is ``"json"`` or ``"csv"``.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if fmt == "csv":
        content = tracker.export_csv(since_date)
        suffix = ".csv"
    else:
        content = tracker.export_json(since_date)
        suffix = ".json"

    dest = output_dir / f"submissions_export{suffix}"
    dest.write_text(content, encoding="utf-8")
    logger.info("Exported %s to %s.", fmt.upper(), dest)
    return dest

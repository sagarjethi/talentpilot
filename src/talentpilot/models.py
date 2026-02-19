"""Domain models for TalentPilot."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True)
class JobPosting:
    """Immutable representation of a discovered job listing."""

    platform: str
    platform_id: str
    url: str
    title: str = ""
    company: str = ""
    location_label: str = ""
    detail_text: str = ""
    salary_text: str = ""
    discovered_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass(frozen=True)
class SearchCriteria:
    """Parameters for a single job search URL."""

    keywords: str
    location: str
    geo_id: str = ""
    experience_levels: tuple[str, ...] = ()
    date_posted: str = ""
    job_types: tuple[str, ...] = ()
    remote_options: tuple[str, ...] = ()
    salary_bracket: str = ""
    sort_order: str = "recent"


@dataclass
class SubmissionRecord:
    """Outcome of a single application attempt."""

    posting: JobPosting
    outcome: str  # succeeded, skipped_blacklist, skipped_duplicate, failed, dry_run
    failure_reason: str = ""
    duration_ms: int = 0


@dataclass
class SessionMetrics:
    """Aggregated counters for one bot run."""

    session_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    started_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    ended_at: str = ""
    total_inspected: int = 0
    total_submitted: int = 0
    total_filtered: int = 0
    total_failed: int = 0
    total_skipped: int = 0

    def finalize(self) -> None:
        self.ended_at = datetime.now(timezone.utc).isoformat()

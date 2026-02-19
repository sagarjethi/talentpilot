"""Chain of Responsibility filtering for job postings."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from talentpilot.models import JobPosting

logger = logging.getLogger(__name__)


class PostingFilter(ABC):
    """Abstract base for a single filter in the chain."""

    def __init__(self) -> None:
        self._next: PostingFilter | None = None

    def set_next(self, handler: PostingFilter) -> PostingFilter:
        self._next = handler
        return handler

    def evaluate(self, posting: JobPosting) -> str | None:
        """Return a rejection reason string, or ``None`` to accept.

        If this filter accepts, delegates to the next filter in the chain.
        """
        reason = self._check(posting)
        if reason is not None:
            return reason
        if self._next:
            return self._next.evaluate(posting)
        return None

    @abstractmethod
    def _check(self, posting: JobPosting) -> str | None:
        ...


class CompanyBlockFilter(PostingFilter):
    """Reject postings from blocked companies."""

    def __init__(self, blocked: list[str]) -> None:
        super().__init__()
        self._blocked = [c.strip().lower() for c in blocked if c.strip()]

    def _check(self, posting: JobPosting) -> str | None:
        company_lower = posting.company.lower()
        for term in self._blocked:
            if term in company_lower:
                logger.info("Blocked company: %s (matched '%s').", posting.company, term)
                return f"blocked_company:{term}"
        return None


class TitleBlockFilter(PostingFilter):
    """Reject postings whose title contains a blocked keyword."""

    def __init__(self, blocked: list[str]) -> None:
        super().__init__()
        self._blocked = [t.strip().lower() for t in blocked if t.strip()]

    def _check(self, posting: JobPosting) -> str | None:
        title_lower = posting.title.lower()
        for term in self._blocked:
            if term in title_lower:
                logger.info("Blocked title: %s (matched '%s').", posting.title, term)
                return f"blocked_title:{term}"
        return None


def build_filter_chain(
    blocked_companies: list[str],
    blocked_titles: list[str],
) -> PostingFilter | None:
    """Assemble and return the head of the filter chain (or ``None`` if empty)."""
    filters: list[PostingFilter] = []
    if blocked_companies:
        filters.append(CompanyBlockFilter(blocked_companies))
    if blocked_titles:
        filters.append(TitleBlockFilter(blocked_titles))

    if not filters:
        return None

    for i in range(len(filters) - 1):
        filters[i].set_next(filters[i + 1])

    return filters[0]

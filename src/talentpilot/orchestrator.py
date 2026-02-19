"""Pipeline coordinator — Discover → Filter → Submit → Report."""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

from talentpilot.auth.session_manager import SessionManager
from talentpilot.browser.playwright_adapter import PlaywrightAdapter
from talentpilot.discovery.listing_scraper import scrape_search_results
from talentpilot.discovery.query_builder import build_search_urls
from talentpilot.evaluation.filter_chain import PostingFilter, build_filter_chain
from talentpilot.exceptions import CapReachedError, FormSubmissionError, SessionExpiredError
from talentpilot.models import JobPosting, SessionMetrics, SubmissionRecord
from talentpilot.reporting.console import print_banner, print_progress, print_session_report
from talentpilot.reporting.tracker import SubmissionTracker
from talentpilot.settings import AppSettings, load_responses
from talentpilot.submission.form_handler import ApplicationFormHandler

logger = logging.getLogger(__name__)

_JOB_VIEW_URL = "https://www.linkedin.com/jobs/view/{job_id}"


class ApplicationPipeline:
    """Wires together all pipeline stages and drives the bot run."""

    _MAX_REAUTH_ATTEMPTS = 3

    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings
        self._adapter = PlaywrightAdapter()
        self._responses = load_responses(settings.responses_file)
        self._metrics = SessionMetrics()
        self._tracker = SubmissionTracker(
            Path(settings.state_dir) / "history.db"
        )
        self._filter_head: PostingFilter | None = build_filter_chain(
            settings.blocked_companies,
            settings.blocked_titles,
        )
        self._session_mgr: SessionManager | None = None

    async def run(self) -> None:
        """Execute the full pipeline."""
        print_banner()

        state_path = SessionManager(
            self._adapter,
            self._settings.email,
            self._settings.password,
            self._settings.state_dir,
        ).storage_state_path()

        await self._adapter.launch(
            headless=self._settings.headless,
            slow_mo=self._settings.slow_mo,
            storage_state_path=state_path or None,
        )

        try:
            self._session_mgr = SessionManager(
                self._adapter,
                self._settings.email,
                self._settings.password,
                self._settings.state_dir,
            )
            await self._session_mgr.ensure_authenticated()

            self._tracker.start_session(
                self._metrics.session_id,
                keywords=self._settings.keywords,
                regions=self._settings.locations,
                simulation=self._settings.simulation_mode,
            )

            urls = build_search_urls(self._settings)
            logger.info("Generated %d search URL(s).", len(urls))

            for url in urls:
                try:
                    await self._run_with_reauth(self._process_search, url)
                except CapReachedError:
                    logger.info("Submission cap reached — stopping.")
                    break
                except Exception as exc:
                    logger.warning("Search processing error: %s — moving to next URL.", exc)

            self._metrics.finalize()
            self._tracker.end_session(self._metrics.session_id, self._metrics)
            print_session_report(self._metrics)
        finally:
            await self._adapter.close()
            self._tracker.close()

    # ---- re-auth wrapper ----

    async def _run_with_reauth(self, coro_fn, *args):
        """Call *coro_fn(*args)*, retrying after re-authentication on session expiry."""
        for attempt in range(1, self._MAX_REAUTH_ATTEMPTS + 1):
            try:
                return await coro_fn(*args)
            except SessionExpiredError:
                logger.warning(
                    "Session expired (attempt %d/%d) — re-authenticating…",
                    attempt,
                    self._MAX_REAUTH_ATTEMPTS,
                )
                if attempt >= self._MAX_REAUTH_ATTEMPTS:
                    raise
                assert self._session_mgr is not None
                await self._session_mgr.reauthenticate()

    # ---- internal stages ----

    async def _process_search(self, search_url: str) -> None:
        """Discover job IDs for one search URL and process each."""
        job_ids = await scrape_search_results(self._adapter, search_url)
        if not job_ids:
            logger.info("No jobs found for this search — moving to next.")
            return
        logger.info("Processing %d job(s) from search results.", len(job_ids))
        for job_id in job_ids:
            self._check_cap()
            try:
                await self._process_single_posting(job_id)
            except (CapReachedError, SessionExpiredError):
                raise
            except Exception as exc:
                logger.warning("Unrecoverable error on job %s: %s — continuing.", job_id, exc)

    async def _process_single_posting(self, job_id: str) -> None:
        """Navigate to a job, filter it, and attempt application."""
        # Ensure we have a valid page before each job
        await self._adapter.ensure_valid_page()

        url = _JOB_VIEW_URL.format(job_id=job_id)
        try:
            await self._adapter.navigate(url)
        except Exception:
            # Page may be stale — try recovery once
            try:
                await self._adapter.ensure_valid_page()
                await self._adapter.navigate(url)
            except Exception:
                logger.warning("Failed to navigate to %s — skipping.", url)
                return
        await asyncio.sleep(8)  # LinkedIn needs time to render job details

        if await self._adapter.is_auth_redirect():
            raise SessionExpiredError("Auth redirect detected on job page.")

        try:
            posting = await self._extract_posting_details(job_id, url)
        except Exception:
            logger.warning("Failed to extract details for %s — skipping.", url)
            posting = JobPosting(platform="linkedin", platform_id=job_id, url=url)
        self._metrics.total_inspected += 1

        # --- filter ---
        if self._filter_head:
            reason = self._filter_head.evaluate(posting)
            if reason:
                self._record(posting, "skipped_blacklist", reason)
                self._metrics.total_filtered += 1
                return

        # --- find Easy Apply link/button ---
        apply_el = await self._find_easy_apply_element()
        if apply_el is None:
            self._record(posting, "skipped_duplicate")
            self._metrics.total_skipped += 1
            return

        # --- click Easy Apply ---
        # LinkedIn's SDUI overlay intercepts pointer events. Use JS click
        # to bypass, and handle any new page/popup.
        try:
            await apply_el.evaluate("el => el.click()")
        except Exception:
            try:
                await apply_el.click(force=True, timeout=5_000)
            except Exception:
                self._record(posting, "failed", "Could not click Easy Apply")
                self._metrics.total_failed += 1
                return
        await asyncio.sleep(4)

        # Check if LinkedIn opened a new page (popup or navigation)
        if self._adapter._context:
            pages = self._adapter._context.pages
            if len(pages) > 1:
                # Switch to the newest page (the apply form)
                self._adapter._page = pages[-1]
                await asyncio.sleep(2)

        handler = ApplicationFormHandler(
            adapter=self._adapter,
            preferred_resume_index=self._settings.preferred_resume_index,
            phone=self._settings.phone_number,
            responses=self._responses,
            follow_companies=self._settings.follow_companies,
            simulation=self._settings.simulation_mode,
            resume_file_path=self._settings.resume_file_path,
            experience_years=self._settings.applicant_experience_years,
        )

        start_ms = time.monotonic_ns() // 1_000_000
        try:
            try:
                outcome = await handler.attempt_submission()
            except FormSubmissionError as exc:
                duration = (time.monotonic_ns() // 1_000_000) - start_ms
                self._record(posting, "failed", str(exc), duration)
                self._metrics.total_failed += 1
                return
            except Exception as exc:
                duration = (time.monotonic_ns() // 1_000_000) - start_ms
                logger.exception("Unexpected error applying to %s.", url)
                self._record(posting, "failed", str(exc), duration)
                self._metrics.total_failed += 1
                return

            duration = (time.monotonic_ns() // 1_000_000) - start_ms
            self._record(posting, outcome, duration_ms=duration)
            if outcome == "succeeded":
                self._metrics.total_submitted += 1
        finally:
            # Clean up: close any extra pages opened by the Easy Apply flow
            # and ensure the adapter points to a valid page for the next job.
            await self._adapter.close_extra_pages()
            await self._adapter.ensure_valid_page()

    # ---- helpers ----

    async def _find_easy_apply_element(self):
        """Locate the Easy Apply button or link on the job detail page.

        LinkedIn's current DOM uses an <a> tag (not <button>) for Easy Apply,
        with an href ending in ``/apply/``. Falls back to text-based matching.
        """
        # Primary: <a> link whose href contains /apply/ and text says "Easy Apply"
        apply_link = await self._adapter.evaluate("""
            () => {
                const links = document.querySelectorAll('a[href*="/apply/"]');
                for (const a of links) {
                    if (a.innerText.trim().toLowerCase().includes('easy apply'))
                        return true;
                }
                return false;
            }
        """)
        if apply_link:
            el = await self._adapter.query('a[href*="/apply/"]', timeout=3_000)
            if el:
                return el

        # Fallback: button with text containing "Easy Apply"
        buttons = await self._adapter.query_all("button")
        for btn in buttons:
            txt = ""
            try:
                txt = (await btn.inner_text()).strip().lower()
            except Exception:
                pass
            if "easy apply" in txt:
                return btn

        # Fallback: any element with "Easy Apply" text
        el = await self._adapter.query("text='Easy Apply'", timeout=3_000)
        return el

    async def _extract_posting_details(self, job_id: str, url: str) -> JobPosting:
        """Scrape title, company, and location from the job detail page.

        LinkedIn's current DOM uses hashed class names, so we rely on
        JavaScript-based extraction using element positions and link patterns.
        """
        details = await self._adapter.evaluate("""
            () => {
                let title = '';
                let company = '';
                let location = '';

                // Title: get from document.title (format: "Job Title - Company | LinkedIn")
                const docTitle = document.title || '';
                if (docTitle.includes(' | LinkedIn')) {
                    const parts = docTitle.replace(' | LinkedIn', '').split(' - ');
                    if (parts.length >= 1) title = parts[0].trim();
                }

                // Company: first <a> linking to /company/ with short text
                const companyLinks = document.querySelectorAll('a[href*="/company/"]');
                for (const a of companyLinks) {
                    const text = a.innerText.trim().split('\\n')[0].trim();
                    if (text && text.length < 60) {
                        company = text;
                        break;
                    }
                }

                // Location: top span in position range ~180-200px with city-like text
                const spans = document.querySelectorAll('span');
                for (const s of spans) {
                    const rect = s.getBoundingClientRect();
                    const text = s.innerText.trim();
                    // Location spans are typically near top (180-200px) and contain comma
                    if (rect.top > 150 && rect.top < 250 && text.length > 3 && text.length < 50) {
                        if (text.includes(',') || /^[A-Z]/.test(text)) {
                            // Skip non-location texts
                            if (!text.includes('ago') && !text.includes('applicant') &&
                                !text.includes('Promoted') && !text.includes('review')) {
                                location = text;
                                break;
                            }
                        }
                    }
                }

                return { title, company, location };
            }
        """)

        title = details.get("title", "")
        company = details.get("company", "")
        location_label = details.get("location", "")

        return JobPosting(
            platform="linkedin",
            platform_id=job_id,
            url=url,
            title=title,
            company=company,
            location_label=location_label,
        )

    def _record(
        self,
        posting: JobPosting,
        outcome: str,
        failure_reason: str = "",
        duration_ms: int = 0,
    ) -> None:
        """Persist a submission record and print progress."""
        posting_id = self._tracker.upsert_posting(posting)
        self._tracker.record_submission(
            posting_id,
            self._metrics.session_id,
            outcome,
            failure_reason,
            duration_ms,
        )
        record = SubmissionRecord(posting, outcome, failure_reason, duration_ms)
        print_progress(record, self._metrics.total_inspected)

    def _check_cap(self) -> None:
        cap = self._settings.max_submissions_per_session
        if cap > 0 and self._metrics.total_submitted >= cap:
            raise CapReachedError(f"Reached cap of {cap} submissions.")

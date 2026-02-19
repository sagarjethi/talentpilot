"""Custom exception hierarchy for TalentPilot."""


class TalentPilotError(Exception):
    """Base exception for all TalentPilot errors."""


class AuthenticationError(TalentPilotError):
    """Raised when login or session verification fails."""


class SessionExpiredError(AuthenticationError):
    """Raised when a stored session is no longer valid."""


class BrowserLaunchError(TalentPilotError):
    """Raised when the browser fails to start."""


class NavigationError(TalentPilotError):
    """Raised when a page fails to load or an expected element is missing."""


class FormSubmissionError(TalentPilotError):
    """Raised when a form step cannot be completed."""


class ConfigurationError(TalentPilotError):
    """Raised when settings are invalid or missing."""


class CapReachedError(TalentPilotError):
    """Raised when the per-session submission cap is hit."""

"""Typed errors: a short user-facing message plus technical detail for the log."""


class EvError(Exception):
    """Base class for every error EV raises on purpose."""

    def __init__(self, user_message: str, detail: str = "") -> None:
        super().__init__(detail or user_message)
        self.user_message = user_message
        self.detail = detail


class StartupError(EvError):
    """Core cannot start (bad environment, unusable data directory)."""

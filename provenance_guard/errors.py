"""Structured application errors.

Service functions raise :class:`APIError`; the Flask layer translates these into
structured JSON responses with the right status code. Python tracebacks are
never exposed to API clients.
"""

from __future__ import annotations


class APIError(Exception):
    """An error that maps to a structured JSON API response."""

    def __init__(
        self,
        error: str,
        message: str,
        status_code: int,
        details: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.error = error
        self.message = message
        self.status_code = status_code
        self.details = details or {}

    def to_dict(self) -> dict:
        return {
            "error": self.error,
            "message": self.message,
            "details": self.details,
        }


def validation_error(message: str, details: dict | None = None) -> APIError:
    return APIError("validation_error", message, 400, details)


def not_found(message: str, details: dict | None = None) -> APIError:
    return APIError("not_found", message, 404, details)


def forbidden(message: str, details: dict | None = None) -> APIError:
    return APIError("forbidden", message, 403, details)


def conflict(message: str, details: dict | None = None) -> APIError:
    return APIError("conflict", message, 409, details)


def service_unavailable(message: str, details: dict | None = None) -> APIError:
    return APIError("service_unavailable", message, 503, details)

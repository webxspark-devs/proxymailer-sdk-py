from __future__ import annotations

from typing import Any


class ProxyMailerError(RuntimeError):
    def __init__(
        self,
        message: str,
        status_code: int = 0,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.context = context or {}


class AuthenticationError(ProxyMailerError):
    pass


class ValidationError(ProxyMailerError):
    def __init__(
        self,
        message: str,
        errors: dict[str, list[str]] | None = None,
        status_code: int = 422,
    ) -> None:
        super().__init__(message, status_code, {"errors": errors or {}})
        self.errors = errors or {}


class RateLimitError(ProxyMailerError):
    def __init__(
        self,
        message: str,
        retry_after_seconds: int | None = None,
        status_code: int = 429,
    ) -> None:
        super().__init__(message, status_code, {"retry_after": retry_after_seconds})
        self.retry_after_seconds = retry_after_seconds


class ApiError(ProxyMailerError):
    pass

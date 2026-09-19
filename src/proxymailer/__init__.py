"""Official ProxyMailer Python SDK."""

from .client import Client, __version__
from .errors import (
    ApiError,
    AuthenticationError,
    ProxyMailerError,
    RateLimitError,
    ValidationError,
)
from .send_result import SendResult

__all__ = [
    "Client",
    "SendResult",
    "ProxyMailerError",
    "AuthenticationError",
    "ValidationError",
    "RateLimitError",
    "ApiError",
    "__version__",
]

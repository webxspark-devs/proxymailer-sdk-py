from __future__ import annotations

import base64
import mimetypes
import random
import time
import uuid
from pathlib import Path
from typing import Any, Mapping, MutableMapping
from urllib.parse import urlencode

import httpx

from .errors import (
    ApiError,
    AuthenticationError,
    ProxyMailerError,
    RateLimitError,
    ValidationError,
)
from .send_result import SendResult

__version__ = "1.0.0"


class Client:
    """Official ProxyMailer Python SDK client."""

    VERSION = __version__

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://mail.example.com",
        timeout: float = 30.0,
        max_retries: int = 3,
        transport: httpx.BaseTransport | None = None,
        user_agent: str | None = None,
    ) -> None:
        key = api_key.strip()
        if not key.startswith("pm_live_"):
            raise ValueError("API key must be a ProxyMailer key starting with pm_live_.")
        self._api_key = key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._max_retries = max_retries
        self._user_agent = user_agent or f"proxymailer-python/{__version__}"
        self._client = httpx.Client(
            base_url=self._base_url,
            timeout=timeout,
            transport=transport,
            headers={
                "Authorization": f"Bearer {key}",
                "Accept": "application/json",
                "User-Agent": self._user_agent,
                "X-ProxyMailer-Client": self._user_agent,
            },
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> Client:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def send(self, message: Mapping[str, Any]) -> SendResult:
        payload = self._normalize(dict(message))
        attempt = 0
        while True:
            try:
                status, body, retry_after = self._post_json(payload)
                if self._is_terminal(status, body):
                    return SendResult.from_response(body, status)
                if self._should_retry(attempt, status) and not self._is_sync_failure(status, body):
                    attempt += 1
                    wait = float(retry_after) if status == 429 and retry_after is not None else self._delay(attempt)
                    time.sleep(wait)
                    continue
                self._raise_for_status(status, body, retry_after)
            except RateLimitError as exc:
                if not self._should_retry(attempt, 429):
                    raise
                attempt += 1
                time.sleep(float(exc.retry_after_seconds or self._delay(attempt)))
            except ProxyMailerError:
                raise
            except Exception as exc:  # noqa: BLE001
                if not self._should_retry(attempt, 0):
                    raise ApiError(f"Transport error: {exc}") from exc
                attempt += 1
                time.sleep(self._delay(attempt))

    @staticmethod
    def attachment_from_bytes(
        filename: str,
        data: bytes | str,
        content_type: str = "application/octet-stream",
    ) -> dict[str, str]:
        raw = data.encode("utf-8") if isinstance(data, str) else data
        return {
            "filename": filename,
            "content_type": content_type,
            "content": base64.b64encode(raw).decode("ascii"),
        }

    @classmethod
    def attachment_from_path(
        cls,
        path: str | Path,
        filename: str | None = None,
        content_type: str | None = None,
    ) -> dict[str, str]:
        p = Path(path)
        if not p.is_file():
            raise ValueError(f"Attachment path is not readable: {path}")
        guessed, _ = mimetypes.guess_type(str(p))
        return cls.attachment_from_bytes(
            filename or p.name,
            p.read_bytes(),
            content_type or guessed or "application/octet-stream",
        )

    def list_groups(self) -> dict[str, Any]:
        """List email groups for this API key's organization (read-only)."""
        return self._get_json("/api/v1/groups")

    def get_group(self, group_id: int) -> dict[str, Any]:
        """Fetch one email group including resolved recipients."""
        body = self._get_json(f"/api/v1/groups/{group_id}")
        data = body.get("data")
        return data if isinstance(data, dict) else body

    def get_mappings(self) -> dict[str, Any]:
        """Fetch tenant group/alias mapping graph for mail-client visualization."""
        return self._get_json("/api/v1/mappings")

    def list_approved_senders(self, page: int = 1, per_page: int = 50) -> dict[str, Any]:
        """List approved senders this application registered (requires admin opt-in)."""
        qs = urlencode({"page": max(1, page), "per_page": min(100, max(1, per_page))})
        return self._get_json(f"/api/v1/approved-senders?{qs}")

    def get_approved_sender(self, sender_id: int) -> dict[str, Any]:
        body = self._get_json(f"/api/v1/approved-senders/{sender_id}")
        data = body.get("data")
        return data if isinstance(data, dict) else body

    def create_approved_sender(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Register an approved sender owned by this application."""
        body = self._write_json("POST", "/api/v1/approved-senders", dict(payload))
        data = body.get("data")
        return data if isinstance(data, dict) else body

    def update_approved_sender(self, sender_id: int, payload: Mapping[str, Any]) -> dict[str, Any]:
        body = self._write_json("PATCH", f"/api/v1/approved-senders/{sender_id}", dict(payload))
        data = body.get("data")
        return data if isinstance(data, dict) else body

    def delete_approved_sender(self, sender_id: int) -> dict[str, Any]:
        body = self._write_json("DELETE", f"/api/v1/approved-senders/{sender_id}", None)
        data = body.get("data")
        return data if isinstance(data, dict) else body

    def _normalize(self, message: MutableMapping[str, Any]) -> dict[str, Any]:
        if not message.get("from"):
            raise ValidationError("`from` is required.")
        if not message.get("to"):
            raise ValidationError("`to` is required.")
        payload: dict[str, Any] = {
            "from": message["from"],
            "to": message["to"],
            "stream": message.get("stream") or "transactional",
        }
        for field in ("subject", "text", "html"):
            if message.get(field) is not None:
                payload[field] = message[field]
        for field in ("cc", "bcc", "meta", "attachments"):
            if message.get(field):
                payload[field] = message[field]
        if message.get("sync") is not None:
            payload["sync"] = bool(message["sync"])
        return payload

    def _post_json(self, payload: Mapping[str, Any]) -> tuple[int, dict[str, Any], int | None]:
        return self._request_json("POST", "/api/v1/send", dict(payload))

    def _get_json(self, path: str) -> dict[str, Any]:
        status, body, retry_after = self._request_json("GET", path, None)
        if status < 200 or status >= 300:
            self._raise_for_status(status, body, retry_after)
        return body

    def _write_json(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None,
    ) -> dict[str, Any]:
        status, body, retry_after = self._request_json(method, path, payload)
        if status < 200 or status >= 300:
            self._raise_for_status(status, body, retry_after)
        return body

    def _request_json(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None,
    ) -> tuple[int, dict[str, Any], int | None]:
        request_id = uuid.uuid4().hex[:16]
        headers = {"X-Request-Id": request_id}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        response = self._client.request(
            method,
            path,
            json=payload,
            headers=headers,
        )
        try:
            body = response.json() if response.content else {}
        except ValueError:
            body = {"message": response.text}
        if not isinstance(body, dict):
            body = {"message": str(body)}
        retry_after = None
        header = response.headers.get("retry-after")
        if header and header.isdigit():
            retry_after = int(header)
        return response.status_code, body, retry_after

    def _should_retry(self, attempt: int, status: int) -> bool:
        if attempt >= self._max_retries:
            return False
        return status in {0, 408, 425, 429, 500, 502, 503, 504}

    def _delay(self, attempt: int) -> float:
        exp = 0.25 * (2 ** max(0, attempt))
        jitter = exp * random.random() * 0.25
        return min(8.0, exp + jitter)

    @staticmethod
    def _is_sync_failure(status: int, body: Mapping[str, Any]) -> bool:
        return status == 502 and "id" in body and "status" in body

    def _is_terminal(self, status: int, body: Mapping[str, Any]) -> bool:
        return (200 <= status < 300) or self._is_sync_failure(status, body)

    def _raise_for_status(
        self,
        status: int,
        body: Mapping[str, Any],
        retry_after: int | None,
    ) -> None:
        message = str(body.get("message") or "ProxyMailer request failed")
        if status in (401, 403):
            raise AuthenticationError(message, status, dict(body))
        if status == 422:
            errors = body.get("errors") if isinstance(body.get("errors"), dict) else {}
            raise ValidationError(message, errors, status)  # type: ignore[arg-type]
        if status == 429:
            raise RateLimitError(message, retry_after, status)
        raise ApiError(message, status, dict(body))

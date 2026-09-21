from __future__ import annotations

import base64
from pathlib import Path

import httpx
import pytest
import respx

from proxymailer import (
    AuthenticationError,
    Client,
    RateLimitError,
    ValidationError,
)

KEY = "pm_live_abcdefghijklmnopqrstuvwxyz0123456789ab"


@respx.mock
def test_send_success_maps_result() -> None:
    route = respx.post("https://proxymailer.wxp.app/api/v1/send").mock(
        return_value=httpx.Response(
            202,
            json={
                "id": "11111111-1111-1111-1111-111111111111",
                "status": "queued",
                "provider_message_id": None,
                "attachment_count": 0,
            },
        )
    )
    client = Client(KEY, base_url="https://proxymailer.wxp.app", max_retries=0)
    result = client.send(
        {
            "from": "noreply@acme.test",
            "to": ["user@example.com"],
            "subject": "Hello",
            "text": "Hi",
        }
    )
    assert result.is_queued()
    assert result.http_status == 202
    assert route.called
    headers = route.calls.last.request.headers
    assert headers["Authorization"] == f"Bearer {KEY}"
    assert "proxymailer-python/" in headers["User-Agent"]
    assert headers["X-ProxyMailer-Client"] == headers["User-Agent"]
    assert len(headers["X-Request-Id"]) == 16
    client.close()


@respx.mock
def test_auth_error_throws() -> None:
    respx.post("https://proxymailer.wxp.app/api/v1/send").mock(
        return_value=httpx.Response(401, json={"message": "Valid application API key required."})
    )
    client = Client(KEY, base_url="https://proxymailer.wxp.app", max_retries=0)
    with pytest.raises(AuthenticationError):
        client.send({"from": "a@b.c", "to": ["c@d.e"]})
    client.close()


@respx.mock
def test_validation_error_exposes_fields() -> None:
    respx.post("https://proxymailer.wxp.app/api/v1/send").mock(
        return_value=httpx.Response(
            422,
            json={
                "message": "The given data was invalid.",
                "errors": {"from": ["Unauthorized sender"]},
            },
        )
    )
    client = Client(KEY, base_url="https://proxymailer.wxp.app", max_retries=0)
    with pytest.raises(ValidationError) as exc:
        client.send({"from": "bad@acme.test", "to": ["user@example.com"]})
    assert "from" in exc.value.errors
    client.close()


def test_rejects_non_pm_live_keys() -> None:
    with pytest.raises(ValueError):
        Client("sk_test_123")


def test_attachment_helpers(tmp_path: Path) -> None:
    att = Client.attachment_from_bytes("note.txt", b"hello", "text/plain")
    assert att["filename"] == "note.txt"
    assert att["content"] == base64.b64encode(b"hello").decode("ascii")

    path = tmp_path / "invoice.txt"
    path.write_bytes(b"path-bytes")
    from_path = Client.attachment_from_path(path)
    assert from_path["filename"] == "invoice.txt"
    assert from_path["content"] == base64.b64encode(b"path-bytes").decode("ascii")


@respx.mock
def test_sync_failure_502_returns_result_without_retry() -> None:
    route = respx.post("https://proxymailer.wxp.app/api/v1/send").mock(
        return_value=httpx.Response(
            502,
            json={
                "id": "22222222-2222-2222-2222-222222222222",
                "status": "failed",
                "provider_message_id": None,
                "attachment_count": 0,
            },
        )
    )
    client = Client(KEY, base_url="https://proxymailer.wxp.app", max_retries=3)
    result = client.send({"from": "a@b.c", "to": "c@d.e", "sync": True})
    assert result.is_failed()
    assert result.http_status == 502
    assert route.call_count == 1
    client.close()


@respx.mock
def test_rate_limit_retries_then_raises() -> None:
    route = respx.post("https://proxymailer.wxp.app/api/v1/send").mock(
        return_value=httpx.Response(
            429,
            json={"message": "Too many requests"},
            headers={"Retry-After": "0"},
        )
    )
    client = Client(KEY, base_url="https://proxymailer.wxp.app", max_retries=1)
    with pytest.raises(RateLimitError) as exc:
        client.send({"from": "a@b.c", "to": ["c@d.e"]})
    assert exc.value.retry_after_seconds == 0
    assert route.call_count == 2
    client.close()


@respx.mock
def test_context_manager_send() -> None:
    respx.post("https://proxymailer.wxp.app/api/v1/send").mock(
        return_value=httpx.Response(
            202,
            json={
                "id": "33333333-3333-3333-3333-333333333333",
                "status": "sent",
                "provider_message_id": "prov-1",
                "attachment_count": 0,
            },
        )
    )
    with Client(KEY, base_url="https://proxymailer.wxp.app", max_retries=0) as client:
        result = client.send({"from": "a@b.c", "to": "c@d.e"})
        assert result.is_sent()
        assert result.provider_message_id == "prov-1"


@respx.mock
def test_approved_sender_helpers_unwrap_data() -> None:
    list_route = respx.get(
        url__regex=r"https://mail\.example\.com/api/v1/approved-senders\?.*"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [{"id": 1, "email": "a@acme.test", "owned_by_application": True}],
                "meta": {
                    "count": 1,
                    "total": 1,
                    "page": 1,
                    "per_page": 50,
                    "can_manage_approved_senders": True,
                },
            },
        )
    )
    create_route = respx.post("https://proxymailer.wxp.app/api/v1/approved-senders").mock(
        return_value=httpx.Response(
            201,
            json={
                "data": {
                    "id": 9,
                    "email": "b@acme.test",
                    "status": "active",
                    "owned_by_application": True,
                }
            },
        )
    )
    update_route = respx.patch("https://proxymailer.wxp.app/api/v1/approved-senders/9").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "id": 9,
                    "email": "b@acme.test",
                    "status": "disabled",
                    "owned_by_application": True,
                }
            },
        )
    )
    delete_route = respx.delete("https://proxymailer.wxp.app/api/v1/approved-senders/9").mock(
        return_value=httpx.Response(
            200,
            json={"data": {"id": 9, "email": "b@acme.test", "deleted": True}},
        )
    )

    client = Client(KEY, base_url="https://proxymailer.wxp.app", max_retries=0)
    listed = client.list_approved_senders()
    assert "data" in listed
    assert list_route.called

    created = client.create_approved_sender({"email": "b@acme.test"})
    assert created["id"] == 9
    assert create_route.called

    updated = client.update_approved_sender(9, {"status": "disabled"})
    assert updated["status"] == "disabled"
    assert update_route.called

    deleted = client.delete_approved_sender(9)
    assert deleted["deleted"] is True
    assert delete_route.called
    client.close()

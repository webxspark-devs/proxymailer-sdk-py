# ProxyMailer Python SDK

Official Python client for the ProxyMailer application send API.

- **Package:** [`proxymailer`](https://pypi.org/project/proxymailer/)
- **Repository:** [webxspark-devs/proxymailer-sdk-py](https://github.com/webxspark-devs/proxymailer-sdk-py)
- **Production API origin:** `https://proxymailer.wxp.app`
- **Contract (OpenAPI):** [`proxy-mailer/sdks/openapi.yaml`](https://github.com/webxspark-devs/proxy-mailer/blob/main/sdks/openapi.yaml)
- **Full developer guide:** [docs/developers/sdks.md](https://github.com/webxspark-devs/proxy-mailer/blob/main/docs/developers/sdks.md)

ProxyMailer is a multi-tenant **BYOK email control plane**. Applications send to ProxyMailer over HTTP; outbound delivery uses organization-owned Generic SMTP / ESP credentials.

---

## Requirements

| Item | Version / note |
| --- | --- |
| Python | **3.10+** |
| Runtime | `httpx>=0.27` (pulled in automatically) |

---

## Install

```bash
pip install proxymailer
# poetry add proxymailer
# uv add proxymailer
```

Dev extras (tests):

```bash
pip install -e ".[dev]"
```

---

## Configuration

### Production (always)

```bash
export PROXYMAILER_API_KEY=pm_live_…
export PROXYMAILER_BASE_URL=https://proxymailer.wxp.app
```

| Variable | Required | Rules |
| --- | --- | --- |
| `PROXYMAILER_API_KEY` | yes | Must start with `pm_live_` |
| `PROXYMAILER_BASE_URL` | strongly recommended | Origin only — **no** trailing slash, **no** `/api/v1`. Production: `https://proxymailer.wxp.app` |

Local override:

```bash
export PROXYMAILER_BASE_URL=http://localhost:8080
```

Never commit real keys. Log prefix only.

---

## Quick start

```python
import os
from proxymailer import (
    Client,
    ValidationError,
    AuthenticationError,
    RateLimitError,
    ApiError,
)

with Client(
    api_key=os.environ["PROXYMAILER_API_KEY"],
    base_url=os.environ.get("PROXYMAILER_BASE_URL", "https://proxymailer.wxp.app"),
    timeout=30.0,
    max_retries=3,
) as client:
    try:
        result = client.send({
            "from": "Acme <noreply@acme.com>",
            "to": ["user@example.com"],
            "subject": "Welcome",
            "html": "<p>Hello</p>",
            "text": "Hello",
            "stream": "transactional",
            "meta": {"user_id": "42"},
            "attachments": [
                Client.attachment_from_bytes("note.txt", b"hello", "text/plain"),
                Client.attachment_from_path("/tmp/invoice.pdf"),
            ],
        })
    except ValidationError as exc:
        print(exc.errors)
        raise
    except AuthenticationError:
        raise
    except RateLimitError as exc:
        print(exc.retry_after_seconds)
        raise
    except ApiError:
        raise

    print(result.id, result.status, result.is_queued())
    print(result.provider_message_id, result.attachment_count, result.http_status)
```

Prefer `with Client(...)` (or call `client.close()`) so the underlying `httpx.Client` is closed.

---

## `Client` constructor

```python
Client(
    api_key: str,
    *,
    base_url: str = "https://proxymailer.wxp.app",
    timeout: float = 30.0,
    max_retries: int = 3,
    transport: httpx.BaseTransport | None = None,
    user_agent: str | None = None,
)
```

| Param | Default | Notes |
| --- | --- | --- |
| `api_key` | — | Must start with `pm_live_` or `ValueError` before any HTTP |
| `base_url` | `https://proxymailer.wxp.app` | Trailing `/` stripped |
| `timeout` | `30.0` | Seconds (httpx) |
| `max_retries` | `3` | |
| `transport` | none | Inject in tests (e.g. with respx) |
| `user_agent` | `proxymailer-python/{VERSION}` | Also `X-ProxyMailer-Client` |

Each request adds `Authorization: Bearer …`, `Accept: application/json`, and a fresh `X-Request-Id`.

---

## `send(message)`

| Field | Required | Notes |
| --- | --- | --- |
| `from` | **yes** | string or mapping with `email`/`address` + optional `name` |
| `to` | **yes** | string or list; may include group/alias identifiers |
| `cc` / `bcc` | no | |
| `subject` / `text` / `html` | no | |
| `stream` | no | Defaults to **`transactional`** in the client |
| `meta` | no | dict for correlation |
| `sync` | no | wait for provider attempt |
| `attachments` | no | max 10 |

### Streams

| Examples | Class | Queue | Weight |
| --- | --- | --- | --- |
| `transactional`, `otp`, `auth`, `alert`, `notification`, `receipt` | high | `mail-high` | 4 |
| `invoice`, `lifecycle`, `onboarding`, unmapped | normal | `mail-normal` | 2 |
| `marketing`, `newsletter`, `bulk`, `campaign`, `blast` | bulk | `mail-bulk` | 1 |

### `SendResult`

| Attribute | Meaning |
| --- | --- |
| `id` | Message UUID — **store this** |
| `status` | `queued` \| `sent` \| `failed` |
| `provider_message_id` | May be `None` on async accept |
| `attachment_count` | |
| `http_status` | `202`, or `502` for sync-failure body |
| `is_queued()` / `is_sent()` / `is_failed()` | Helpers |

HTTP **502** with `{id, status}` is a terminal failed `SendResult` (not retried as transport).
No public application `GET /messages/{id}` — use dashboard, webhooks, or `sync=True`.

---

## Attachments

```python
Client.attachment_from_bytes("note.txt", b"hello", "text/plain")
Client.attachment_from_bytes("note.txt", "hello")  # str encoded as UTF-8
Client.attachment_from_path("/tmp/invoice.pdf")    # MIME via mimetypes
```

Emits Base64 in `content`.

---

## Groups & mapping graph

```python
groups = client.list_groups()
group = client.get_group(12)
graph = client.get_mappings()  # graph["data"]["nodes"] / ["edges"]
```

Tenant-scoped; cross-tenant → **404**. Read-only for application keys.

---

## Approved senders (opt-in)

Requires **Allow API to manage approved senders**.

```python
client.list_approved_senders(page=1, per_page=50)
client.get_approved_sender(9)
client.create_approved_sender({"email": "user@acme.com", "display_name": "User"})
client.update_approved_sender(9, {"status": "disabled"})
client.delete_approved_sender(9)
```

---

## Errors & retries

| HTTP | Class | Retried? |
| --- | --- | --- |
| `401` / `403` | `AuthenticationError` | No |
| `422` | `ValidationError` (`.errors`) | No |
| `429` | `RateLimitError` (`.retry_after_seconds`) | Yes |
| `408` / `425` / `500` / `503` / `504` | `ApiError` | Yes |
| `502` + send body | `SendResult` failed | **No** |
| Other / network | `ApiError` | Yes |

Base: `ProxyMailerError` (`status_code`, `context`). Backoff ~250ms × 2^n + jitter, cap ~8s.

---

## Testing

```bash
pip install -e ".[dev]"
pytest
```

---

## Versioning & publishing

SemVer. Align major bumps with PHP / Node SDKs and OpenAPI when the wire format
breaks. PyPI publishes from **this** repo’s CI. Maintainer notes:
[publishing.md](https://github.com/webxspark-devs/proxy-mailer/blob/main/docs/developers/publishing.md).

---

## Related docs

- [Authentication](https://github.com/webxspark-devs/proxy-mailer/blob/main/docs/developers/authentication.md)
- [Sending](https://github.com/webxspark-devs/proxy-mailer/blob/main/docs/developers/sending.md)
- [Groups](https://github.com/webxspark-devs/proxy-mailer/blob/main/docs/developers/groups.md)
- [Approved senders](https://github.com/webxspark-devs/proxy-mailer/blob/main/docs/developers/approved-senders.md)
- [Errors](https://github.com/webxspark-devs/proxy-mailer/blob/main/docs/developers/errors.md)

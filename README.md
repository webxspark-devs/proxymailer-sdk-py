# ProxyMailer Python SDK

Official Python client for the ProxyMailer application send API.

## Install

```bash
pip install proxymailer
```

Requires Python 3.10+.

## Usage

```python
import os
from proxymailer import Client

client = Client(
    api_key=os.environ["PROXYMAILER_API_KEY"],
    base_url=os.environ.get("PROXYMAILER_BASE_URL", "https://mail.example.com"),
)

result = client.send({
    "from": "Acme <noreply@acme.com>",
    "to": ["user@example.com"],
    "subject": "Welcome",
    "html": "<p>Hello</p>",
    "text": "Hello",
    "attachments": [
        Client.attachment_from_bytes("note.txt", b"hello", "text/plain"),
    ],
})

print(result.id, result.status)

# Read-only groups + visualization graph (tenant-scoped)
groups = client.list_groups()
graph = client.get_mappings()  # data["nodes"] / data["edges"]
client.close()
```

See [`docs/developers`](../../docs/developers/README.md) for the full guide, including [groups & mappings](../../docs/developers/groups.md).

## Publishing (maintainers)

To release `proxymailer` on **PyPI**:

```bash
cd sdks/python
pip install -U build twine
pytest
python -m build && twine check dist/*
twine upload --repository testpypi dist/*   # recommended first
twine upload dist/*
```

Full checklist (tokens, TestPyPI, CI): [`docs/developers/publishing.md`](../../docs/developers/publishing.md#3-python--pypi).

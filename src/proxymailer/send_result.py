from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class SendResult:
    id: str
    status: str
    provider_message_id: str | None
    attachment_count: int
    http_status: int

    @classmethod
    def from_response(cls, data: Mapping[str, Any], http_status: int) -> SendResult:
        pmid = data.get("provider_message_id")
        return cls(
            id=str(data.get("id") or ""),
            status=str(data.get("status") or "unknown"),
            provider_message_id=None if pmid is None else str(pmid),
            attachment_count=int(data.get("attachment_count") or 0),
            http_status=http_status,
        )

    def is_queued(self) -> bool:
        return self.status == "queued"

    def is_sent(self) -> bool:
        return self.status == "sent"

    def is_failed(self) -> bool:
        return self.status == "failed"

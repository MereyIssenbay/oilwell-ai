"""Bounded opaque cursors bound to endpoint and optional well filter."""
from __future__ import annotations

import base64
import json

from backend.app.errors import ServiceError


def encode_cursor(kind: str, position: int, scope: str | None = None) -> str:
    value = json.dumps([kind, position, scope], separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def decode_cursor(value: str | None, kind: str, scope: str | None = None) -> int:
    if value is None:
        return 0
    try:
        if len(value) > 256:
            raise ValueError("Long cursor")
        payload = json.loads(base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True))
        if (not isinstance(payload, list) or len(payload) != 3 or payload[0] != kind
                or payload[2] != scope or type(payload[1]) is not int or not 0 <= payload[1] <= 2**63 - 1):
            raise ValueError("Invalid cursor")
        return payload[1]
    except (ValueError, TypeError, UnicodeDecodeError) as exc:
        raise ServiceError("INVALID_CURSOR", "Cursor is invalid for this resource", 400) from exc

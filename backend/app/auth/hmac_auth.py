"""HMAC-SHA256 request signing for Hermes -> Dashboard Backend calls (DOC 5
§9): message = `{timestamp}\\n{method}\\n{path}\\n{body}`, header
`X-Hermes-Signature` + `X-Hermes-Timestamp`. A 60-second timestamp window
guards against replay — this is why the timestamp is part of the signed
message, not just a freshness check on its own.
"""

from __future__ import annotations

import hashlib
import hmac
import time

DEFAULT_MAX_SKEW_SECONDS = 60


def compute_hermes_signature(secret: str, timestamp: str, method: str, path: str, body: bytes) -> str:
    message = f"{timestamp}\n{method.upper()}\n{path}\n".encode("utf-8") + body
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def verify_hermes_request(
    secret: str,
    timestamp: str,
    method: str,
    path: str,
    body: bytes,
    provided_signature: str,
    now: float | None = None,
    max_skew_seconds: int = DEFAULT_MAX_SKEW_SECONDS,
) -> bool:
    if not provided_signature or not timestamp:
        return False

    try:
        ts = float(timestamp)
    except ValueError:
        return False

    now = now if now is not None else time.time()
    if abs(now - ts) > max_skew_seconds:
        return False

    expected = compute_hermes_signature(secret, timestamp, method, path, body)
    return hmac.compare_digest(expected, provided_signature)

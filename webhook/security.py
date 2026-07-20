"""HMAC-SHA256 signature verification for the TradingView webhook (DOC 2 §4)."""

from __future__ import annotations

import hashlib
import hmac


def compute_signature(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def verify_signature(secret: str, body: bytes, provided_signature: str) -> bool:
    if not provided_signature:
        return False
    expected = compute_signature(secret, body)
    return hmac.compare_digest(expected, provided_signature)

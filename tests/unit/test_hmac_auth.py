import time

from backend.app.auth.hmac_auth import compute_hermes_signature, verify_hermes_request

SECRET = "hermes-secret"


def test_valid_signature_accepted():
    now = time.time()
    ts = str(now)
    body = b'{"command":"status"}'
    sig = compute_hermes_signature(SECRET, ts, "POST", "/api/hermes/command", body)
    assert verify_hermes_request(SECRET, ts, "POST", "/api/hermes/command", body, sig, now=now)


def test_wrong_secret_rejected():
    now = time.time()
    ts = str(now)
    body = b"{}"
    sig = compute_hermes_signature("other-secret", ts, "POST", "/path", body)
    assert not verify_hermes_request(SECRET, ts, "POST", "/path", body, sig, now=now)


def test_tampered_body_rejected():
    now = time.time()
    ts = str(now)
    sig = compute_hermes_signature(SECRET, ts, "POST", "/path", b"original")
    assert not verify_hermes_request(SECRET, ts, "POST", "/path", b"tampered", sig, now=now)


def test_stale_timestamp_rejected():
    now = time.time()
    ts = str(now - 120)  # 2 minutes old, beyond the 60s window
    body = b"{}"
    sig = compute_hermes_signature(SECRET, ts, "POST", "/path", body)
    assert not verify_hermes_request(SECRET, ts, "POST", "/path", body, sig, now=now)


def test_future_timestamp_rejected():
    now = time.time()
    ts = str(now + 120)
    body = b"{}"
    sig = compute_hermes_signature(SECRET, ts, "POST", "/path", body)
    assert not verify_hermes_request(SECRET, ts, "POST", "/path", body, sig, now=now)


def test_missing_signature_rejected():
    now = time.time()
    assert not verify_hermes_request(SECRET, str(now), "POST", "/path", b"{}", "", now=now)


def test_missing_timestamp_rejected():
    assert not verify_hermes_request(SECRET, "", "POST", "/path", b"{}", "deadbeef")


def test_malformed_timestamp_rejected():
    assert not verify_hermes_request(SECRET, "not-a-number", "POST", "/path", b"{}", "deadbeef")


def test_different_method_or_path_changes_signature():
    now = time.time()
    ts = str(now)
    body = b"{}"
    sig = compute_hermes_signature(SECRET, ts, "POST", "/path-a", body)
    assert not verify_hermes_request(SECRET, ts, "POST", "/path-b", body, sig, now=now)
    assert not verify_hermes_request(SECRET, ts, "GET", "/path-a", body, sig, now=now)

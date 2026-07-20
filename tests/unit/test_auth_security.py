import time

import pyotp
import pytest

from backend.app.auth.security import (
    TokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
    verify_totp,
)


def test_password_hash_and_verify_roundtrip():
    hashed = hash_password("correct-horse-battery-staple")
    assert verify_password("correct-horse-battery-staple", hashed)
    assert not verify_password("wrong-password", hashed)


def test_password_hash_is_salted_differently_each_time():
    h1 = hash_password("same-password")
    h2 = hash_password("same-password")
    assert h1 != h2
    assert verify_password("same-password", h1)
    assert verify_password("same-password", h2)


def test_totp_verify_accepts_current_code():
    secret = pyotp.random_base32()
    code = pyotp.TOTP(secret).now()
    assert verify_totp(secret, code)


def test_totp_verify_rejects_wrong_code():
    secret = pyotp.random_base32()
    assert not verify_totp(secret, "000000")


def test_create_and_decode_access_token():
    token = create_access_token("admin", secret="s3cret")
    payload = decode_access_token(token, secret="s3cret")
    assert payload["sub"] == "admin"


def test_decode_rejects_wrong_secret():
    token = create_access_token("admin", secret="s3cret")
    with pytest.raises(TokenError):
        decode_access_token(token, secret="wrong-secret")


def test_decode_rejects_expired_token():
    token = create_access_token("admin", secret="s3cret", expires_minutes=-1)
    with pytest.raises(TokenError):
        decode_access_token(token, secret="s3cret")


def test_decode_rejects_tampered_token():
    token = create_access_token("admin", secret="s3cret")
    tampered = token[:-4] + "abcd"
    with pytest.raises(TokenError):
        decode_access_token(tampered, secret="s3cret")


def test_extra_claims_included():
    token = create_access_token("admin", secret="s3cret", extra_claims={"role": "operator"})
    payload = decode_access_token(token, secret="s3cret")
    assert payload["role"] == "operator"

"""Direct tests for the fail-closed local JWT verifier.

``common.security.auth.decode_access_token`` prefers ``python-jose`` but keeps a
built-in HMAC-SHA256 verifier as a fallback. That fallback is what silently
accepted forged tokens before DEF-001, so it is exercised explicitly here rather
than only through the jose path.

Every test forces the ``ImportError`` branch by hiding the ``jose`` module, so the
assertions really do cover the code that runs when the dependency is missing.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import sys
from datetime import UTC, datetime, timedelta

import pytest

from common.config import get_settings
from common.security.auth import TokenError, create_access_token, decode_access_token
from common.ttl_cache import TTLCache  # noqa: F401  (import kept for parity of env checks)


@pytest.fixture
def without_jose(monkeypatch):
    """Force ``from jose import jwt`` to raise ImportError."""

    saved = {
        name: sys.modules.get(name)
        for name in list(sys.modules)
        if name == "jose" or name.startswith("jose.")
    }
    for name in saved:
        monkeypatch.delitem(sys.modules, name, raising=False)
    monkeypatch.setitem(sys.modules, "jose", None)
    yield
    for name, module in saved.items():
        if module is not None:
            sys.modules[name] = module


def _seg(payload: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()


def _sign(header: str, payload: str, secret: str) -> str:
    digest = hmac.new(secret.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def _token(
    subject: str = "7",
    *,
    alg: str = "HS256",
    secret: str | None = None,
    exp: int | None = None,
    signature: str | None = None,
) -> str:
    settings = get_settings()
    header = _seg({"alg": alg, "typ": "JWT"})
    payload = _seg(
        {
            "sub": subject,
            "exp": exp
            if exp is not None
            else int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
        }
    )
    sig = (
        signature
        if signature is not None
        else _sign(header, payload, secret or settings.jwt_secret_key)
    )
    return f"{header}.{payload}.{sig}"


def test_fallback_accepts_genuinely_signed_token(without_jose):
    """The fallback verifier must still accept a correctly signed token."""

    payload = decode_access_token(_token("42"))
    assert payload["sub"] == "42"


def test_fallback_rejects_alg_none(without_jose):
    """SEC-AUTH-001: unsigned tokens must never be accepted."""

    for signature in ("", "x", "AAAA"):
        with pytest.raises(TokenError):
            decode_access_token(_token(alg="none", signature=signature))


def test_fallback_rejects_empty_signature_with_hs256_header(without_jose):
    """A missing signature is not a valid signature."""

    with pytest.raises(TokenError):
        decode_access_token(_token(alg="HS256", signature=""))


def test_fallback_rejects_wrong_signature(without_jose):
    """SEC-AUTH-002: a signature made with another secret must fail."""

    with pytest.raises(TokenError):
        decode_access_token(_token(signature="AAAA"))
    with pytest.raises(TokenError):
        decode_access_token(_token(secret="a-different-secret"))


def test_fallback_rejects_expired_token(without_jose):
    """SEC-AUTH-005: expiry is enforced on the fallback path too."""

    with pytest.raises(TokenError):
        decode_access_token(_token(exp=1))


def test_fallback_rejects_malformed_tokens(without_jose):
    """SEC-AUTH-003: malformed input raises TokenError, never a crash type."""

    for bad in ("forged.token.value", "a.b.c", "not-a-jwt", "..", "x.y.z.w", ""):
        with pytest.raises(TokenError):
            decode_access_token(bad)


def test_fallback_rejects_wrong_algorithm(without_jose):
    """Only the configured algorithm is accepted."""

    with pytest.raises(TokenError):
        decode_access_token(_token(alg="HS512"))


def test_fallback_rejects_missing_subject(without_jose):
    """A signed token without a subject cannot identify a user."""

    settings = get_settings()
    header = _seg({"alg": "HS256", "typ": "JWT"})
    payload = _seg({"exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp())})
    token = f"{header}.{payload}.{_sign(header, payload, settings.jwt_secret_key)}"
    with pytest.raises(TokenError):
        decode_access_token(token)


def test_fallback_interoperates_with_create_access_token(without_jose):
    """Tokens minted by create_access_token verify under the fallback."""

    token = create_access_token("123")
    assert decode_access_token(token)["sub"] == "123"

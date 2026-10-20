"""JWT algorithm hardening and residual-risk tests (round 3).

``pip-audit`` reports CVE-2026-85394 against ``python-jose`` 3.5.0 (and two
against its ``ecdsa`` dependency) with no upstream fix available. The exploitable
surface for a HS256-only deployment is algorithm handling, so this module pins:

* only symmetric HMAC algorithms are accepted; RSA/ECDSA/PS/none are rejected at
  configuration time (fail-fast) rather than at request time;
* the default is HS256;
* algorithm confusion (a token claiming ``RS256`` against an HMAC secret) and
  key/algorithm confusion (asymmetric material offered as an HMAC secret) cannot
  authenticate;
* the local fallback uses the digest matching the configured algorithm, so
  HS384/HS512 are not silently mis-verified as SHA-256.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta

import pytest

from common.config import get_settings
from common.security.auth import (
    JWT_ALGORITHM,
    SUPPORTED_JWT_ALGORITHMS,
    TokenError,
    create_access_token,
    decode_access_token,
    resolve_jwt_algorithm,
)


def _segment(payload: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()


def _signed(header_alg: str, secret: str, *, subject: str = "1", signature: str | None = None) -> str:
    header = _segment({"alg": header_alg, "typ": "JWT"})
    payload = _segment(
        {"sub": subject, "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp())}
    )
    if signature is None:
        digest = hashlib.sha256(f"{header}.{payload}".encode()).digest()
        signature = base64.urlsafe_b64encode(hmac.new(secret.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()).rstrip(b"=").decode()
        del digest
    return f"{header}.{payload}.{signature}"


# --------------------------------------------------------------------- defaults
def test_default_algorithm_is_hs256() -> None:
    """The service must default to a symmetric algorithm."""

    assert resolve_jwt_algorithm(None) == "HS256"
    assert resolve_jwt_algorithm("  hs256 ") == "HS256"
    assert JWT_ALGORITHM == "HS256"


def test_supported_algorithms_are_hmac_only() -> None:
    """No asymmetric algorithm may appear in the allow-list."""

    assert set(SUPPORTED_JWT_ALGORITHMS) == {"HS256", "HS384", "HS512"}
    for algorithm in SUPPORTED_JWT_ALGORITHMS:
        assert algorithm.startswith("HS")


@pytest.mark.parametrize(
    "algorithm",
    ["RS256", "RS384", "RS512", "ES256", "ES384", "ES512", "PS256", "PS512", "EdDSA", "none", "NONE", "HS999"],
)
def test_asymmetric_and_none_algorithms_are_rejected(algorithm: str) -> None:
    """Algorithm confusion starts with accepting a non-HMAC algorithm."""

    with pytest.raises(ValueError) as excinfo:
        resolve_jwt_algorithm(algorithm)
    message = str(excinfo.value)
    assert "HMAC" in message or "algorithm" in message.lower()


@pytest.mark.parametrize("algorithm", ["", "   "])
def test_empty_algorithm_is_an_explicit_error(algorithm: str) -> None:
    """An empty value must not silently fall back to the default."""

    with pytest.raises(ValueError):
        resolve_jwt_algorithm(algorithm)


# ------------------------------------------------------- confusion / key material
def test_token_claiming_rs256_cannot_authenticate() -> None:
    """A token that advertises an asymmetric algorithm must be refused."""

    token = _signed("RS256", get_settings().jwt_secret_key)
    with pytest.raises(TokenError):
        decode_access_token(token)


@pytest.mark.parametrize(
    "material",
    [
        # PEM public keys offered as an HMAC secret (classic key confusion).
        "-----BEGIN PUBLIC KEY-----\nMFwwDQYJKoZIhvcNAQEBBQADSwAwSAJBAK0=\n-----END PUBLIC KEY-----",
        "",
        "   ",
        "not-a-key",
    ],
)
def test_non_secret_key_material_cannot_authenticate(material: str) -> None:
    """A token signed with anything other than the configured secret fails."""

    token = _signed("HS256", material)
    with pytest.raises(TokenError):
        decode_access_token(token)


def test_der_like_bytes_are_not_accepted_as_a_signing_key() -> None:
    """Binary key material must not accidentally verify."""

    binary_secret = bytes(range(32)).decode("latin-1")
    token = _signed("HS256", binary_secret)
    with pytest.raises(TokenError):
        decode_access_token(token)


def test_alg_none_with_plausible_signature_is_rejected() -> None:
    """``alg=none`` must be refused even when a signature segment is present."""

    token = _signed("none", "irrelevant")
    with pytest.raises(TokenError):
        decode_access_token(token)


# --------------------------------------------------------- fallback digest parity
def test_fallback_uses_the_configured_digest(monkeypatch) -> None:
    """HS384/HS512 must not be verified with SHA-256 in the fallback path.

    Forces the ImportError branch so the hand-rolled verifier is exercised.
    """

    import sys

    import common.security.auth as auth_module

    saved = {name: sys.modules.get(name) for name in list(sys.modules) if name == "jose" or name.startswith("jose.")}
    for name in saved:
        monkeypatch.delitem(sys.modules, name, raising=False)
    monkeypatch.setitem(sys.modules, "jose", None)
    try:
        for algorithm in ("HS256", "HS384", "HS512"):
            monkeypatch.setattr(auth_module, "JWT_ALGORITHM", algorithm)
            header = _segment({"alg": algorithm, "typ": "JWT"})
            payload = _segment(
                {"sub": "9", "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp())}
            )
            digest = getattr(hashlib, SUPPORTED_JWT_ALGORITHMS[algorithm])
            signature = base64.urlsafe_b64encode(
                hmac.new(
                    auth_module.settings.jwt_secret_key.encode(),
                    f"{header}.{payload}".encode(),
                    digest,
                ).digest()
            ).rstrip(b"=").decode()
            token = f"{header}.{payload}.{signature}"
            assert auth_module._decode_with_local_hmac(token)["sub"] == "9", algorithm

            # A signature produced with the wrong digest must fail.
            wrong = base64.urlsafe_b64encode(
                hmac.new(
                    auth_module.settings.jwt_secret_key.encode(),
                    f"{header}.{payload}".encode(),
                    hashlib.sha256 if algorithm != "HS256" else hashlib.sha384,
                ).digest()
            ).rstrip(b"=").decode()
            with pytest.raises(TokenError):
                auth_module._decode_with_local_hmac(f"{header}.{payload}.{wrong}")
    finally:
        for name, module in saved.items():
            if module is not None:
                sys.modules[name] = module


def test_roundtrip_works_with_validated_algorithm() -> None:
    """Hardening must not break genuine tokens."""

    assert decode_access_token(create_access_token("123"))["sub"] == "123"

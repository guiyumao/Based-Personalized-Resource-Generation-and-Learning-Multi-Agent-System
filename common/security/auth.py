"""JWT and password utilities."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from common.config import get_settings

settings = get_settings()


class TokenError(Exception):
    """Raised when a JWT cannot be verified."""


#: Only HMAC algorithms are supported. Asymmetric algorithms (RS*/ES*/PS*) are
#: rejected outright: this service authenticates with a single shared secret, and
#: accepting an asymmetric algorithm would open the classic key-confusion path
#: (an RSA public key used as an HMAC secret).
SUPPORTED_JWT_ALGORITHMS: dict[str, str] = {
    "HS256": "sha256",
    "HS384": "sha384",
    "HS512": "sha512",
}

_DEFAULT_JWT_ALGORITHM = "HS256"


def resolve_jwt_algorithm(configured: str | None) -> str:
    """Validate ``JWT_ALGORITHM`` and return the canonical name.

    ``None`` (unset) falls back to HS256. Any other value must be a supported
    HMAC algorithm; an explicitly empty value is an error rather than a silent
    fallback, so a typo in deployment configuration cannot go unnoticed.

    Raises ``ValueError`` so a misconfiguration fails at startup instead of
    silently accepting or rejecting every token at request time.
    """

    if configured is None:
        return _DEFAULT_JWT_ALGORITHM

    candidate = str(configured).strip().upper()
    if not candidate:
        raise ValueError(
            "JWT_ALGORITHM is set but empty; unset it to use the HS256 default or "
            "provide an explicit HMAC algorithm."
        )
    if candidate not in SUPPORTED_JWT_ALGORITHMS:
        supported = ", ".join(sorted(SUPPORTED_JWT_ALGORITHMS))
        raise ValueError(
            f"Unsupported JWT_ALGORITHM {configured!r}; only symmetric HMAC algorithms "
            f"are allowed ({supported}). Asymmetric algorithms are rejected to prevent "
            "algorithm-confusion attacks."
        )
    return candidate


#: The validated algorithm actually used for signing and verification. Resolved
#: once at import so a bad JWT_ALGORITHM fails fast rather than per request.
JWT_ALGORITHM: str = resolve_jwt_algorithm(settings.jwt_algorithm)


try:  # python-jose is the declared dependency; the local verifier is a fallback.
    from jose import JWTError
except ImportError:  # pragma: no cover - depends on the installed environment

    class JWTError(Exception):  # type: ignore[no-redef]
        """Stand-in used when python-jose is unavailable."""


def hash_password(password: str) -> str:
    """Hash password with bcrypt, with a local fallback when dependency is unavailable."""

    try:
        import bcrypt

        hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
        return hashed.decode("utf-8")
    except ImportError:
        fallback = f"{password}{settings.password_salt}".encode()
        return hashlib.sha256(fallback).hexdigest()


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Verify a plain password against bcrypt or fallback hash."""

    try:
        import bcrypt

        return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))
    except ImportError:
        fallback = f"{plain_password}{settings.password_salt}".encode()
        return hashlib.sha256(fallback).hexdigest() == password_hash


def create_access_token(subject: str) -> str:
    """Generate a JWT access token using the validated HMAC algorithm."""

    expire = datetime.now(UTC) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": subject, "exp": expire}
    try:
        from jose import jwt

        return jwt.encode(payload, settings.jwt_secret_key, algorithm=JWT_ALGORITHM)
    except ImportError:
        header = {"alg": JWT_ALGORITHM, "typ": "JWT"}
        normalized_payload = {
            "sub": subject,
            "exp": int(expire.timestamp()),
        }
        header_b64 = base64.urlsafe_b64encode(json.dumps(header).encode("utf-8")).rstrip(b"=")
        payload_b64 = base64.urlsafe_b64encode(
            json.dumps(normalized_payload).encode("utf-8")
        ).rstrip(b"=")
        signing_input = header_b64 + b"." + payload_b64
        signature = hmac.new(
            settings.jwt_secret_key.encode("utf-8"),
            signing_input,
            _hmac_digest(JWT_ALGORITHM),
        ).digest()
        signature_b64 = base64.urlsafe_b64encode(signature).rstrip(b"=")
        return b".".join([header_b64, payload_b64, signature_b64]).decode("utf-8")


def _hmac_digest(algorithm: str):
    """Map a JWT algorithm name to its hashlib digest constructor."""

    return getattr(hashlib, SUPPORTED_JWT_ALGORITHMS[algorithm])


def decode_access_token(token: str) -> dict[str, Any]:
    """Verify a JWT access token and return its payload.

    Raises ``TokenError`` when the token is malformed, expired, unsigned, or its
    signature does not match ``JWT_SECRET_KEY``.

    Verification is fail-closed: when ``python-jose`` is unavailable the built-in
    HMAC-SHA256 verifier is used, which still rejects unsigned/``alg=none`` tokens
    and any token whose signature was produced with a different secret.
    """

    try:
        from jose import jwt
    except ImportError:
        return _decode_with_local_hmac(token)

    try:
        return jwt.decode(token, settings.jwt_secret_key, algorithms=[JWT_ALGORITHM])
    except JWTError as exc:  # expired / bad signature / malformed / wrong alg
        raise TokenError(str(exc)) from exc


def _b64url_decode(value: str) -> bytes:
    """Decode one unpadded base64url JWT segment."""

    padding = "=" * (-len(value) % 4)
    try:
        return base64.urlsafe_b64decode(value + padding)
    except (binascii.Error, ValueError) as exc:
        raise TokenError("Malformed base64url segment") from exc


def _decode_with_local_hmac(token: str) -> dict[str, Any]:
    """Fail-closed verifier used only when ``python-jose`` is not installed."""

    parts = token.split(".")
    if len(parts) != 3:
        raise TokenError("Malformed token: expected three segments")
    header_segment, payload_segment, signature_segment = parts

    try:
        header = json.loads(_b64url_decode(header_segment).decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise TokenError("Malformed token header") from exc

    if not isinstance(header, dict):
        raise TokenError("Malformed token header")

    algorithm = str(header.get("alg", "")).upper()
    if algorithm in {"NONE", ""} or not signature_segment:
        raise TokenError("Unsigned tokens are not accepted")
    if algorithm != JWT_ALGORITHM:
        raise TokenError(f"Unsupported token algorithm: {header.get('alg')!r}")

    signing_input = f"{header_segment}.{payload_segment}".encode("ascii", "strict")
    expected = hmac.new(
        settings.jwt_secret_key.encode("utf-8"),
        signing_input,
        _hmac_digest(JWT_ALGORITHM),
    ).digest()
    supplied = _b64url_decode(signature_segment)
    if not hmac.compare_digest(expected, supplied):
        raise TokenError("Token signature verification failed")

    try:
        payload = json.loads(_b64url_decode(payload_segment).decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise TokenError("Malformed token payload") from exc

    if not isinstance(payload, dict):
        raise TokenError("Malformed token payload")

    exp = payload.get("exp")
    if exp is not None:
        try:
            expired = datetime.now(UTC).timestamp() > float(exp)
        except (TypeError, ValueError) as exc:
            raise TokenError("Malformed 'exp' claim") from exc
        if expired:
            raise TokenError("Token has expired")

    if not payload.get("sub"):
        raise TokenError("Token is missing the 'sub' claim")

    return payload

"""JWT and password utilities."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from common.config import get_settings

settings = get_settings()


def hash_password(password: str) -> str:
    """Hash password with bcrypt, with a local fallback when dependency is unavailable."""

    try:
        import bcrypt

        hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
        return hashed.decode("utf-8")
    except ImportError:
        fallback = f"{password}{settings.password_salt}".encode("utf-8")
        return hashlib.sha256(fallback).hexdigest()


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Verify a plain password against bcrypt or fallback hash."""

    try:
        import bcrypt

        return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))
    except ImportError:
        fallback = f"{plain_password}{settings.password_salt}".encode("utf-8")
        return hashlib.sha256(fallback).hexdigest() == password_hash


def create_access_token(subject: str) -> str:
    """Generate a JWT access token."""

    expire = datetime.now(UTC) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": subject, "exp": expire}
    try:
        from jose import jwt

        return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    except ImportError:
        header = {"alg": settings.jwt_algorithm, "typ": "JWT"}
        normalized_payload = {
            "sub": subject,
            "exp": int(expire.timestamp()),
        }
        header_b64 = base64.urlsafe_b64encode(json.dumps(header).encode("utf-8")).rstrip(b"=")
        payload_b64 = base64.urlsafe_b64encode(json.dumps(normalized_payload).encode("utf-8")).rstrip(b"=")
        signing_input = header_b64 + b"." + payload_b64
        signature = hmac.new(
            settings.jwt_secret_key.encode("utf-8"),
            signing_input,
            hashlib.sha256,
        ).digest()
        signature_b64 = base64.urlsafe_b64encode(signature).rstrip(b"=")
        return b".".join([header_b64, payload_b64, signature_b64]).decode("utf-8")


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode a JWT access token and return its payload."""

    try:
        from jose import jwt

        return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except ImportError:
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("Invalid token format")
        payload_bytes = parts[1].encode("utf-8")
        padding = b"=" * (-len(payload_bytes) % 4)
        decoded = base64.urlsafe_b64decode(payload_bytes + padding)
        return json.loads(decoded.decode("utf-8"))

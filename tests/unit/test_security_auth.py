"""Security regression tests for authentication, token verification and object scope.

These tests encode the defects found during end-to-end global testing so they
cannot silently return:

* ``SEC-AUTH-001`` unsigned / ``alg=none`` tokens must never be accepted
* ``SEC-AUTH-002`` tokens signed with a different key must be rejected
* ``SEC-AUTH-003`` malformed tokens must produce 401, never a 500
* ``SEC-AUTH-004`` no anonymous token-minting endpoint may exist
* ``SEC-IDOR-001`` a learner token must not read another learner's profile
* ``SEC-IDOR-002`` a learner token must not read another learner's records
* ``SEC-ANON-001`` report/notebook endpoints must not be readable anonymously

Run:
    python -m pytest tests/unit/test_security_auth.py -v
"""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from common.security.auth import create_access_token, decode_access_token
from services.evaluation_service.app.main import app as evaluation_app
from services.user_service.app.main import app as user_app

USER_CLIENT = TestClient(user_app)
EVALUATION_CLIENT = TestClient(evaluation_app)


def _segment(payload: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()


def _unsigned_token(subject: str, *, alg: str = "none", signature: str = "") -> str:
    header = _segment({"alg": alg, "typ": "JWT"})
    payload = _segment(
        {"sub": subject, "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp())}
    )
    return f"{header}.{payload}.{signature}"


# --------------------------------------------------------------------------- JWT
@pytest.mark.parametrize(
    "token_name,factory",
    [
        ("alg-none-empty-signature", lambda sub: _unsigned_token(sub)),
        ("alg-none-with-signature", lambda sub: _unsigned_token(sub, signature="x")),
        (
            "alg-HS256-bogus-signature",
            lambda sub: _unsigned_token(sub, alg="HS256", signature="AAAA"),
        ),
    ],
)
def test_unsigned_or_forged_token_is_rejected(token_name, factory) -> None:
    """SEC-AUTH-001/002: token signature verification must be fail-closed."""

    token = factory("1")
    response = USER_CLIENT.get("/users/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401, f"{token_name} was accepted: {response.status_code}"


@pytest.mark.parametrize("token", ["forged.token.value", "a.b.c", "not-a-jwt", "..", "x.y.z.w"])
def test_malformed_token_returns_401_not_500(token: str) -> None:
    """SEC-AUTH-003: a broken token is an auth failure, not a server error."""

    response = USER_CLIENT.get("/users/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401, f"{token!r} -> {response.status_code}"


def test_missing_token_is_401() -> None:
    """SEC-AUTH-003: absent credentials must be rejected."""

    assert USER_CLIENT.get("/users/me").status_code == 401


def test_token_signed_with_another_key_is_rejected() -> None:
    """SEC-AUTH-002: rotating/guessing the secret must invalidate signatures."""

    # A correctly shaped HS256 token whose signature was produced with a wrong key.
    header = _segment({"alg": "HS256", "typ": "JWT"})
    payload = _segment({"sub": "1", "exp": 9999999999})
    forged = f"{header}.{payload}.{_segment({'sig': 'nope'})}"
    response = USER_CLIENT.get("/users/me", headers={"Authorization": f"Bearer {forged}"})
    assert response.status_code == 401


def test_valid_token_round_trips() -> None:
    """The hardened verifier must still accept genuine tokens."""

    payload = decode_access_token(create_access_token("42"))
    assert payload["sub"] == "42"


def test_expired_token_is_rejected() -> None:
    """SEC-AUTH-005: the expiry claim must be enforced on every code path."""

    header = _segment({"alg": "HS256", "typ": "JWT"})
    body = _segment({"sub": "1", "exp": 1})
    import hashlib
    import hmac

    from common.config import get_settings

    signing_input = f"{header}.{body}".encode()
    signature = (
        base64.urlsafe_b64encode(
            hmac.new(get_settings().jwt_secret_key.encode(), signing_input, hashlib.sha256).digest()
        )
        .rstrip(b"=")
        .decode()
    )
    expired = f"{header}.{body}.{signature}"

    response = USER_CLIENT.get("/users/me", headers={"Authorization": f"Bearer {expired}"})
    assert response.status_code == 401


# --------------------------------------------------------------- anonymous access
def test_no_anonymous_token_minting_endpoint(test_user) -> None:
    """SEC-AUTH-004: tokens may only be obtained by authenticating."""

    response = USER_CLIENT.post(f"/users/{test_user.id}/token")
    assert response.status_code in {404, 405}, "anonymous token minting endpoint is back"


def test_profile_endpoints_require_authentication(test_user) -> None:
    """SEC-ANON-001: learner profile data must not be world readable."""

    for path in (
        f"/users/{test_user.id}",
        f"/users/{test_user.id}/profile",
        f"/users/{test_user.id}/profile/status",
        f"/users/{test_user.id}/profile/dashboard",
    ):
        assert USER_CLIENT.get(path).status_code == 401, f"{path} is anonymously readable"


def test_evaluation_endpoints_require_authentication(test_user) -> None:
    """SEC-ANON-002: report and notebook endpoints must not be anonymously readable."""

    for path in (
        f"/evaluation/mistakes/{test_user.id}",
        f"/evaluation/mistakes/{test_user.id}/detail",
        f"/evaluation/reports/comprehensive/{test_user.id}",
        f"/evaluation/reports/suggestions/{test_user.id}",
        f"/evaluation/profiles/{test_user.id}/snapshot",
    ):
        assert EVALUATION_CLIENT.get(path).status_code == 401, f"{path} is anonymously readable"


# -------------------------------------------------------------------- object scope
def test_learner_cannot_read_another_learner_profile(test_user, other_user, auth_headers) -> None:
    """SEC-IDOR-001: a valid token for one learner must not read another's data."""

    response = USER_CLIENT.get(f"/users/{other_user.id}/profile", headers=auth_headers)
    assert response.status_code == 403


def test_learner_cannot_update_another_learner_profile(test_user, other_user, auth_headers) -> None:
    """SEC-IDOR-002: cross-account writes must be refused."""

    response = USER_CLIENT.put(
        f"/users/{other_user.id}/profile",
        headers=auth_headers,
        json={"learning_style": "visual", "profile_dimensions": {"knowledgeBase": "tampered"}},
    )
    assert response.status_code == 403


def test_learner_cannot_read_another_learner_evaluation(
    test_user, other_user, auth_headers
) -> None:
    """SEC-IDOR-003: evaluation records are scoped to the owning learner."""

    for path in (
        f"/evaluation/mistakes/{other_user.id}",
        f"/evaluation/mistakes/{other_user.id}/detail",
        f"/evaluation/reports/comprehensive/{other_user.id}",
    ):
        response = EVALUATION_CLIENT.get(path, headers=auth_headers)
        assert response.status_code == 403, f"{path} -> {response.status_code}"


def test_owner_can_read_own_profile(test_user, auth_headers, db_session) -> None:
    """The ownership guard must not break legitimate self-access."""

    from common.models.learning import UserProfile

    if db_session.get(UserProfile, test_user.id) is None:
        db_session.add(
            UserProfile(
                user_id=test_user.id,
                mastery_json={},
                learning_style="visual",
                cognitive_abilities={},
                habits={},
            )
        )
        db_session.commit()

    response = USER_CLIENT.get(f"/users/{test_user.id}/profile", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["user_id"] == test_user.id

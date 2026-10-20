"""Non-destructive live API probe for the personalized-learning multi-agent system.

Purpose
-------
Collect *real* HTTP evidence (status code + latency + key field presence) from the
locally running Python services so that test cases, defects and the final report
are grounded in observed behaviour instead of assumptions.

Safety
------
* Every request goes to 127.0.0.1 only (never a remote host).
* Only read-only or self-contained write calls are issued. The probe never
  deletes existing data: it registers its own throwaway student account and
  operates on that account's own records.
* Destructive candidates (resource delete, mistake-notebook clear, knowledge
  base reindex, transcript share-revoke) are only reported as "manual only",
  they are not executed.

Usage
-----
    python tests/global/probe_api.py --out artifacts/global-testing/api-probe.json
    python tests/global/probe_api.py --only health --timeout 10
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import statistics
import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx

SERVICES: dict[str, str] = {
    "user": os.getenv("USER_SERVICE_URL", "http://127.0.0.1:8001"),
    "agent": os.getenv("AGENT_SERVICE_URL", "http://127.0.0.1:8002"),
    "resource": os.getenv("RESOURCE_SERVICE_URL", "http://127.0.0.1:8003"),
    "evaluation": os.getenv("EVALUATION_SERVICE_URL", "http://127.0.0.1:8004"),
    "teacher": os.getenv("TEACHER_SERVICE_URL", "http://127.0.0.1:8005"),
    "system": os.getenv("SYSTEM_SERVICE_URL", "http://127.0.0.1:8006"),
    "qa_compat": os.getenv("AGENT_SERVICE_QA_COMPAT_URL", "http://127.0.0.1:8007"),
}

# Endpoints whose URL contains an identifier that only exists after a previous
# probe step created it. They are resolved at runtime from `ctx`.
DESTRUCTIVE_METHODS = {"DELETE"}

#: Resource id that is guaranteed absent, so write probes can exercise the auth
#: gate without any chance of mutating a real resource.
ABSENT_RESOURCE_ID = 999_999_999

BAD_REQUEST_BODY = {"__probe": "invalid-body-on-purpose", "unexpected": [1, 2, 3]}


@dataclass
class Result:
    """One probed endpoint outcome."""

    case_id: str
    name: str
    service: str
    method: str
    path: str
    status: int | None = None
    latency_ms: float | None = None
    verdict: str = "not-run"
    note: str = ""
    data_shape: str = ""
    body_preview: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "name": self.name,
            "service": self.service,
            "method": self.method,
            "path": self.path,
            "status": self.status,
            "latency_ms": None if self.latency_ms is None else round(self.latency_ms, 1),
            "verdict": self.verdict,
            "note": self.note,
            "data_shape": self.data_shape,
            "body_preview": self.body_preview,
        }


@dataclass
class Probe:
    """Probe run state."""

    client: httpx.Client
    results: list[Result] = field(default_factory=list)
    ctx: dict[str, Any] = field(default_factory=dict)
    only: str | None = None

    # ------------------------------------------------------------------ helpers
    def _select(self, group: str) -> bool:
        return self.only is None or self.only == group

    def check(
        self,
        group: str,
        case_id: str,
        name: str,
        service: str,
        method: str,
        path: str,
        *,
        json_body: Any = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        expect: tuple[int, ...] = (200,),
        expect_key: str | None = None,
    ) -> tuple[Result, Any]:
        """Issue one probe request and return (result, parsed-json-payload)."""

        result = Result(case_id=case_id, name=name, service=service, method=method, path=path)
        if not self._select(group):
            result.verdict = "skipped"
            self.results.append(result)
            return result, None
        # A DELETE is only allowed through when it targets the absent-sentinel id;
        # bulk delete (`DELETE /resources`) stays manual-only.
        if method.upper() in DESTRUCTIVE_METHODS and not path.endswith(
            f"/resources/{ABSENT_RESOURCE_ID}"
        ):
            result.verdict = "manual-only"
            result.note = "destructive call intentionally not executed by the automated probe"
            self.results.append(result)
            return result, None

        url = SERVICES[service] + path
        payload: Any = None
        try:
            started = time.perf_counter()
            response = self.client.request(
                method.upper(),
                url,
                json=json_body,
                params=params,
                headers=headers or {},
            )
            result.latency_ms = (time.perf_counter() - started) * 1000
            result.status = response.status_code
            text = response.text
            result.body_preview = text[:400].replace("\n", " ")
            try:
                payload = response.json()
                result.data_shape = _shape(payload)
            except Exception:  # noqa: BLE001 - non JSON response is itself evidence
                result.data_shape = f"non-json(len={len(text)})"
        except httpx.HTTPError as exc:  # connection refused / timeout / etc.
            result.verdict = "error"
            result.note = f"{type(exc).__name__}: {exc}"
            self.results.append(result)
            return result, None

        if result.status in expect:
            if expect_key and expect_key not in result.body_preview:
                result.verdict = "fail"
                result.note = f"status {result.status} but key '{expect_key}' missing in body"
            else:
                result.verdict = "pass"
        else:
            result.verdict = "fail"
            result.note = f"expected {expect}, got {result.status}"
        self.results.append(result)
        return result, payload

    def run(self) -> dict[str, Any]:
        self._probe_health()
        self._probe_auth()
        self._probe_validation()
        self._probe_cors()
        self._probe_student_journey()
        self._probe_resource_authz()
        self._probe_system_configs()
        self._probe_teacher_system()
        return self._summary()

    # ------------------------------------------------------------------- groups
    def _probe_health(self) -> None:
        for name in SERVICES:
            self.check(
                "health",
                f"HLT-{name.upper()}-001",
                f"{name} service health endpoint",
                name,
                "GET",
                "/health",
                expect=(200,),
            )

    def _probe_auth(self) -> None:
        email = f"probe_{uuid.uuid4().hex[:10]}@example.com"
        username = f"probe_{uuid.uuid4().hex[:10]}"
        password = "Probe#Passw0rd123"
        self.ctx.update(email=email, username=username, password=password)

        _, registered = self.check(
            "auth",
            "AUTH-API-001",
            "student self-registration returns 201 + token",
            "user",
            "POST",
            "/users/register",
            json_body={
                "username": username,
                "email": email,
                "password": password,
                "role": "student",
            },
            expect=(200, 201),
        )
        self._harvest(registered)

        _, logged_in = self.check(
            "auth",
            "AUTH-API-002",
            "valid credentials return bearer token",
            "user",
            "POST",
            "/users/login",
            json_body={"username": username, "password": password},
            expect=(200,),
        )
        self._harvest(logged_in)

        self.check(
            "auth",
            "AUTH-NEG-001",
            "wrong password must be rejected (401/400)",
            "user",
            "POST",
            "/users/login",
            json_body={"username": username, "password": "definitely-wrong-password"},
            expect=(400, 401, 403),
        )

        self.check(
            "auth",
            "AUTH-NEG-002",
            "unknown user with a valid-length password must not leak account existence",
            "user",
            "POST",
            "/users/login",
            json_body={"username": "probe_user_does_not_exist_9999", "password": "WrongPassw0rd!"},
            expect=(401, 403, 404),
        )
        self.check(
            "auth",
            "BOUND-API-003",
            "short password is rejected by the schema before any credential check",
            "user",
            "POST",
            "/users/login",
            json_body={"username": "probe_user_does_not_exist_9999", "password": "x"},
            expect=(400, 422),
        )

        self.check(
            "auth",
            "AUTH-SEC-001",
            "GET /users/me without token must be rejected",
            "user",
            "GET",
            "/users/me",
            expect=(401, 403),
        )

        self.check(
            "auth",
            "AUTH-SEC-002",
            "GET /users/me with a forged token must be rejected",
            "user",
            "GET",
            "/users/me",
            headers={"Authorization": "Bearer forged.token.value"},
            expect=(401, 403),
        )

        self.check(
            "auth",
            "AUTH-API-003",
            "GET /users/me with valid token returns own profile",
            "user",
            "GET",
            "/users/me",
            headers=self._auth(),
            expect=(200,),
        )

        # IDOR probe: a fresh student token must not be able to read user id 1
        # (the pre-existing local admin account).
        idor_result, _ = self.check(
            "auth",
            "AUTH-SEC-003",
            "IDOR probe: student token reading another user id (/users/1)",
            "user",
            "GET",
            "/users/1",
            headers=self._auth(),
            expect=(200, 401, 403, 404),
        )
        if idor_result.status == 200:
            idor_result.verdict = "suspect"
            idor_result.note = (
                "student token returned HTTP 200 for another user id: "
                "verify whether this is self-read only or a broken object-level check"
            )

    def _probe_validation(self) -> None:
        self.check(
            "validation",
            "NEG-API-001",
            "login with schema-invalid body must be 422/400, not 500",
            "user",
            "POST",
            "/users/login",
            json_body=BAD_REQUEST_BODY,
            expect=(400, 422),
        )
        self.check(
            "validation",
            "NEG-API-002",
            "register with empty payload must be rejected",
            "user",
            "POST",
            "/users/register",
            json_body={},
            expect=(400, 422),
        )
        self.check(
            "validation",
            "BOUND-API-001",
            "unknown path under /users is rejected (401 before routing, or 404)",
            "user",
            "GET",
            "/users/__no_such_endpoint__",
            expect=(401, 404, 405),
        )
        self.check(
            "validation",
            "NEG-API-003",
            "wrong method on /users/login is rejected (401 before routing, or 405)",
            "user",
            "GET",
            "/users/login",
            expect=(401, 404, 405),
        )
        self.check(
            "validation",
            "NEG-API-004",
            "undocumented query parameter is ignored, not fatal (resource list)",
            "resource",
            "GET",
            "/resources?limit=not-a-number",
            expect=(200,),
        )
        self.check(
            "validation",
            "BOUND-API-002",
            "negative limit on recommendations must be rejected by the ge=1 bound",
            "resource",
            "GET",
            "/resources/recommendations?limit=-5",
            headers=self._auth(),
            expect=(400, 422),
        )
        self.check(
            "validation",
            "SEC-API-001",
            "SQL-injection-shaped query parameter must not return 500",
            "resource",
            "GET",
            "/resources?subject=' OR '1'='1",
            expect=(200, 400, 422),
        )

    def _probe_cors(self) -> None:
        origin = "http://evil.example.com"
        result, _ = self.check(
            "cors",
            "SEC-CORS-001",
            "CORS preflight from an untrusted origin",
            "user",
            "OPTIONS",
            "/users/login",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
            expect=(200, 204, 400, 403),
        )
        allow = ""
        try:
            response = self.client.options(
                SERVICES["user"] + "/users/login",
                headers={
                    "Origin": origin,
                    "Access-Control-Request-Method": "POST",
                },
            )
            allow = response.headers.get("access-control-allow-origin", "")
        except httpx.HTTPError:
            allow = "<request failed>"
        result.note = (result.note + f" | allow-origin={allow or '<absent>'}").strip(" |")
        self.ctx["cors_allow_origin"] = allow

    def _probe_student_journey(self) -> None:
        user_id = self.ctx.get("user_id")
        auth = self._auth()
        if not user_id:
            self.results.append(
                Result(
                    "JRN-000",
                    "student journey skipped: no user id from registration",
                    "user",
                    "-",
                    "-",
                    verdict="blocked",
                    note="registration did not return an id",
                )
            )
            return

        self.check(
            "journey",
            "PROF-API-001",
            "learner profile read model",
            "user",
            "GET",
            f"/users/{user_id}/profile",
            headers=auth,
            expect=(200, 404),
        )
        self.check(
            "journey",
            "PROF-API-002",
            "profile status for onboarding gate",
            "user",
            "GET",
            f"/users/{user_id}/profile/status",
            headers=auth,
            expect=(200,),
        )
        self.check(
            "journey",
            "PROF-API-003",
            "profile dashboard aggregate",
            "user",
            "GET",
            f"/users/{user_id}/profile/dashboard",
            headers=auth,
            expect=(200,),
        )
        self.check(
            "journey",
            "KB-API-001",
            "knowledge base index status requires a teacher/admin token (pre-existing contract)",
            "agent",
            "GET",
            "/knowledge-base/status",
            expect=(401, 403),
        )
        self.check(
            "journey",
            "KB-API-002",
            "knowledge base subject list",
            "agent",
            "GET",
            "/knowledge-base/subjects",
            expect=(200,),
        )
        self.check(
            "journey",
            "KB-SEC-001",
            "knowledge base reindex must not be callable anonymously",
            "agent",
            "POST",
            "/knowledge-base/reindex",
            expect=(401, 403, 422),
        )
        self.check(
            "journey",
            "KB-SEC-002",
            "knowledge base crawl trigger must not be callable anonymously",
            "agent",
            "POST",
            "/knowledge-base/sources/crawl",
            json_body={"subject": "probe", "limit": 1},
            expect=(401, 403, 422),
        )
        self.check(
            "journey",
            "PATH-API-001",
            "learning path read for a brand new user",
            "agent",
            "GET",
            f"/paths/{user_id}",
            headers=auth,
            expect=(200, 404),
        )
        self.check(
            "journey",
            "CHAT-API-001",
            "chat session creation for own user scope",
            "agent",
            "POST",
            "/chat/sessions/new",
            json_body={"user_id": int(user_id), "title": "probe session"},
            headers=auth,
            expect=(200, 201),
        )
        self.check(
            "journey",
            "CHAT-API-002",
            "chat session list for own user scope",
            "agent",
            "GET",
            "/chat/sessions",
            params={"user_id": int(user_id)},
            headers=auth,
            expect=(200,),
        )
        self.check(
            "journey",
            "CHAT-SEC-001",
            "chat session list without token must be rejected",
            "agent",
            "GET",
            "/chat/sessions",
            params={"user_id": int(user_id)},
            expect=(401, 403),
        )
        self.check(
            "journey",
            "CHAT-SEC-002",
            "chat session list for a foreign user id must be forbidden",
            "agent",
            "GET",
            "/chat/sessions",
            params={"user_id": 1},
            headers=auth,
            expect=(401, 403),
        )
        self.check(
            "journey",
            "EVAL-API-001",
            "mistake notebook read (empty for new user)",
            "evaluation",
            "GET",
            f"/evaluation/mistakes/{user_id}",
            headers=auth,
            expect=(200,),
        )
        self.check(
            "journey",
            "EVAL-API-002",
            "comprehensive report for a user with no answers returns a business-level error",
            "evaluation",
            "GET",
            f"/evaluation/reports/comprehensive/{user_id}",
            headers=auth,
            expect=(200, 400, 404),
        )
        self.check(
            "journey",
            "EVAL-API-003",
            "analytics suggestions endpoint",
            "evaluation",
            "GET",
            f"/evaluation/reports/suggestions/{user_id}",
            headers=auth,
            expect=(200,),
        )
        self.check(
            "journey",
            "RES-API-001",
            "resource listing",
            "resource",
            "GET",
            "/resources",
            expect=(200,),
        )
        self.check(
            "journey",
            "RES-API-002",
            "resource recommendations for the authenticated learner",
            "resource",
            "GET",
            "/resources/recommendations",
            headers=auth,
            expect=(200,),
        )
        self.check(
            "journey",
            "RES-SEC-001",
            "resource recommendations without token must be rejected",
            "resource",
            "GET",
            "/resources/recommendations",
            expect=(401, 403),
        )
        self.check(
            "journey",
            "GRAPH-API-001",
            "knowledge graph visualization for one knowledge point",
            "agent",
            "POST",
            "/graph/visualization",
            json_body={"knowledge_point": "数据结构"},
            expect=(200,),
        )
        self.check(
            "journey",
            "COMM-API-001",
            "learning community discussions require authentication",
            "teacher",
            "GET",
            "/learning/discussions",
            expect=(401, 403),
        )
        self.check(
            "journey",
            "COMM-API-002",
            "learning community discussion list (no auth expected?)",
            "teacher",
            "GET",
            "/learning/notifications?user_id=1",
            expect=(200, 401, 403, 422),
        )

    def _probe_resource_authz(self) -> None:
        """DEF-007: the resource write endpoints must be gated before business logic.

        Only read-only or non-mutating calls are issued: the single-resource writes
        target an id that does not exist (so a gated call returns 401/403 and an
        ungated one still cannot change data), and bulk delete is never executed.
        """

        auth = self._auth()
        self.check(
            "resource_authz",
            "RES-SEC-001",
            "anonymous import-external must be 401",
            "resource",
            "POST",
            "/resources/import-external",
            json_body={
                "title": "probe",
                "provider": "probe",
                "url": "https://example.com/x",
                "knowledge_point": "probe",
            },
            expect=(401,),
        )
        self.check(
            "resource_authz",
            "RES-SEC-002",
            "anonymous status update must be 401",
            "resource",
            "PATCH",
            f"/resources/{ABSENT_RESOURCE_ID}/status",
            json_body={"status": "ready"},
            expect=(401,),
        )
        self.check(
            "resource_authz",
            "RES-SEC-003",
            "anonymous export must be 401",
            "resource",
            "POST",
            f"/resources/{ABSENT_RESOURCE_ID}/export",
            json_body={"export_format": "pdf"},
            expect=(401,),
        )
        self.check(
            "resource_authz",
            "RES-SEC-004",
            "anonymous single delete must be 401",
            "resource",
            "DELETE",
            f"/resources/{ABSENT_RESOURCE_ID}",
            expect=(401,),
        )
        self.check(
            "resource_authz",
            "RES-SEC-005",
            "anonymous bulk delete must be 401 (destructive; auth gate only)",
            "resource",
            "DELETE",
            "/resources",
            expect=(401,),
        )
        self.check(
            "resource_authz",
            "RES-SEC-006",
            "anonymous download must be 401 (no local file exposure)",
            "resource",
            "GET",
            f"/resources/{ABSENT_RESOURCE_ID}/download",
            expect=(401,),
        )
        self.check(
            "resource_authz",
            "RES-SEC-007",
            "student token on teacher/admin write must be 403",
            "resource",
            "DELETE",
            f"/resources/{ABSENT_RESOURCE_ID}",
            headers=auth,
            expect=(403,),
        )
        self.check(
            "resource_authz",
            "RES-SEC-008",
            "authenticated download keeps working (404 for absent id, not 401/403)",
            "resource",
            "GET",
            f"/resources/{ABSENT_RESOURCE_ID}/download",
            headers=auth,
            expect=(404,),
        )
        self.check(
            "resource_authz",
            "RES-API-003",
            "public read catalog stays public (must not be over-hardened)",
            "resource",
            "GET",
            "/resources",
            expect=(200,),
        )

    def _probe_system_configs(self) -> None:
        """DEF-006: system configuration is admin-only and filters secrets."""

        auth = self._auth()
        self.check(
            "system_configs",
            "SYS-CFG-001",
            "anonymous /system/configs must be 401",
            "system",
            "GET",
            "/system/configs",
            expect=(401,),
        )
        self.check(
            "system_configs",
            "SYS-CFG-002",
            "student token on /system/configs must be 403",
            "system",
            "GET",
            "/system/configs",
            headers=auth,
            expect=(403,),
        )
        self.check(
            "system_configs",
            "SYS-CFG-003",
            "/system/subjects remains a public read catalog",
            "system",
            "GET",
            "/system/subjects",
            expect=(200,),
        )

    def _probe_teacher_system(self) -> None:
        self.check(
            "teacher",
            "TEACH-API-001",
            "teacher class list without token",
            "teacher",
            "GET",
            "/teacher/classes",
            expect=(401, 403),
        )
        self.check(
            "teacher",
            "SYS-API-001",
            "system audit log read without token",
            "system",
            "GET",
            "/system/logs",
            expect=(401, 403),
        )
        self.check(
            "teacher",
            "SYS-API-002",
            "system config list now requires admin (DEF-006 closed)",
            "system",
            "GET",
            "/system/configs",
            expect=(401, 403),
        )
        self.check(
            "teacher",
            "SYS-NEG-001",
            "role assignment without token",
            "system",
            "POST",
            "/system/roles/assign",
            json_body={"user_id": 1, "role": "admin"},
            expect=(401, 403, 422),
        )
        self.check(
            "teacher",
            "SYS-NEG-002",
            "role escalation attempt with a student token",
            "system",
            "POST",
            "/system/roles/assign",
            json_body={"user_id": self.ctx.get("user_id") or 1, "role": "admin"},
            headers=self._auth(),
            expect=(401, 403),
        )
        self.check(
            "teacher",
            "SEC-DOCS-001",
            "OpenAPI docs exposure on agent service",
            "agent",
            "GET",
            "/openapi.json",
            expect=(200, 401, 403, 404),
        )

    # ------------------------------------------------------------------ runtime
    def _auth(self) -> dict[str, str]:
        token = self.ctx.get("token")
        return {"Authorization": f"Bearer {token}"} if token else {}

    def _harvest(self, payload: Any) -> None:
        """Extract token / user id from a registration or login response."""

        if not isinstance(payload, dict):
            return
        token = payload.get("access_token") or payload.get("token")
        if isinstance(token, str) and token:
            self.ctx["token"] = token
        if payload.get("user_id") is not None:
            self.ctx["user_id"] = payload["user_id"]
        user = payload.get("user")
        if isinstance(user, dict):
            if user.get("id") is not None:
                self.ctx["user_id"] = user["id"]
            if user.get("role"):
                self.ctx["role"] = user["role"]
        elif payload.get("id") is not None:
            self.ctx["user_id"] = payload["id"]

    def _summary(self) -> dict[str, Any]:
        passed = [r for r in self.results if r.verdict == "pass"]
        failed = [r for r in self.results if r.verdict == "fail"]
        errored = [r for r in self.results if r.verdict == "error"]
        suspects = [r for r in self.results if r.verdict == "suspect"]
        latencies = [r.latency_ms for r in self.results if r.latency_ms is not None]
        return {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "target": "127.0.0.1 local development services",
            "safety": "read-only + self-owned writes; destructive endpoints not called",
            "auth_context": {
                "user_id": self.ctx.get("user_id"),
                "role": self.ctx.get("role"),
                "cors_allow_origin": self.ctx.get("cors_allow_origin"),
                "token_captured": bool(self.ctx.get("token")),
            },
            "counts": {
                "total": len(self.results),
                "pass": len(passed),
                "fail": len(failed),
                "error": len(errored),
                "suspect": len(suspects),
                "skipped": len([r for r in self.results if r.verdict == "skipped"]),
                "manual_only": len([r for r in self.results if r.verdict == "manual-only"]),
            },
            "latency_ms": {
                "min": round(min(latencies), 1) if latencies else None,
                "median": round(statistics.median(latencies), 1) if latencies else None,
                "max": round(max(latencies), 1) if latencies else None,
            },
            "failures": [r.as_dict() for r in failed + errored + suspects],
            "results": [r.as_dict() for r in self.results],
        }


def _shape(payload: Any, depth: int = 0) -> str:
    """Describe a JSON payload structure without dumping its full content."""

    if depth > 3:
        return "..."
    if isinstance(payload, dict):
        keys = list(payload.keys())[:12]
        return "{" + ", ".join(f"{k}: {_shape(payload[k], depth + 1)}" for k in keys) + "}"
    if isinstance(payload, list):
        if not payload:
            return "[]"
        return f"[{len(payload)} x {_shape(payload[0], depth + 1)}]"
    if isinstance(payload, str):
        return f"str(len={len(payload)})"
    return type(payload).__name__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Non-destructive live API probe")
    parser.add_argument("--only", default=None, help="run a single group only")
    parser.add_argument("--timeout", type=float, default=20.0, help="per-request timeout (s)")
    parser.add_argument("--out", default=None, help="JSON report path")
    args = parser.parse_args(argv)

    with httpx.Client(timeout=args.timeout, follow_redirects=False) as client:
        probe = Probe(client=client, only=args.only)
        summary = probe.run()

    payload = json.dumps(summary, ensure_ascii=False, indent=2)
    if args.out:
        out_path = pathlib.Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(payload, encoding="utf-8")
        print(f"[probe] report written to {out_path}")
    else:
        print(payload)

    counts = summary["counts"]
    print(
        f"[probe] pass={counts['pass']} fail={counts['fail']} "
        f"error={counts['error']} manual_only={counts['manual_only']} total={counts['total']}"
    )
    return 1 if (counts["fail"] or counts["error"]) else 0


if __name__ == "__main__":
    sys.exit(main())

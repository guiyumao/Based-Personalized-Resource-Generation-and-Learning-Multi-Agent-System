"""Real business APIs/Worker under local-only guard, authorized gateway upstream."""

from __future__ import annotations

import json
import os
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

from common.db.bootstrap import ensure_database_schema
from common.db.session import SessionLocal
from common.models.learning import Exercise, Resource

ROOT = Path(__file__).resolve().parents[1]


def main():
    assert os.getenv("NO_COST_GUARD_ACTIVE") == "1" and os.environ.get("LIVE_GATEWAY_BASE")
    output = Path(os.environ["LIVE_OUTPUT"])
    ensure_database_schema()
    processes = []
    logs = []
    services = {}
    results = []

    def port():
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            return sock.getsockname()[1]

    frontend_port = port()
    frontend = f"http://127.0.0.1:{frontend_port}"
    ports = {
        name: port() for name in ["user", "agent", "resource", "evaluation", "teacher", "system"]
    }
    env = dict(os.environ)
    env.update(
        ASSISTANT_TASK_EXECUTION_MODE="worker",
        CORS_ALLOW_ORIGINS=frontend,
        NO_COST_ALLOWED_PORTS=os.environ["NO_COST_ALLOWED_PORTS"],
    )

    def launch(name, command, environment):
        log = (output / (name + ".log")).open("w", encoding="utf-8")
        logs.append(log)
        proc = subprocess.Popen(
            command, cwd=ROOT, env=environment, stdout=log, stderr=subprocess.STDOUT
        )
        processes.append((name, proc))
        return proc

    def wait(url, proc):
        end = time.monotonic() + 40
        while time.monotonic() < end:
            if proc.poll() is not None:
                raise RuntimeError("Startup failed: " + url)
            try:
                if httpx.get(url, timeout=1, trust_env=False).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.2)
        raise TimeoutError("Startup timeout")

    try:
        for name, number in ports.items():
            services[name] = f"http://127.0.0.1:{number}"
            proc = launch(
                name,
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    f"services.{name}_service.app.main:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(number),
                ],
                dict(env),
            )
            wait(services[name] + "/health", proc)
        launch(
            "worker",
            [
                sys.executable,
                "-m",
                "services.agent_service.app.services.assistant_worker",
                "--poll-interval",
                "0.5",
            ],
            dict(env),
        )
        username = "live_authorized_" + secrets.token_hex(4)
        password = secrets.token_urlsafe(18)
        resource_id = None
        with httpx.Client(timeout=90, trust_env=False) as client:
            response = client.post(
                services["user"] + "/users/register",
                json={"username": username, "password": password, "role": "student"},
            )
            assert response.status_code == 201, response.text
            auth = response.json()
            headers = {"Authorization": "Bearer " + auth["access_token"]}
            for action, message in [
                ("courseware", "生成 TCP 可靠传输课件，讲清序号、确认和超时重传"),
                ("exercise", "生成 TCP 可靠传输的三道选择题，每题有答案和解析"),
            ]:
                payload = {
                    "message": message,
                    "action": action,
                    "client_request_id": "authorized-live-" + action,
                    "exercise_count": 3,
                    "use_learning_context": False,
                }
                response = client.post(
                    services["agent"] + "/assistant/chat", json=payload, headers=headers
                )
                assert response.status_code == 200, response.text
                task_id = response.json()["task"]["id"]
                end = time.monotonic() + 150
                while time.monotonic() < end:
                    task = client.get(
                        services["agent"] + f"/assistant/tasks/{task_id}", headers=headers
                    ).json()
                    if task["status"] not in {"PENDING", "RUNNING", "CANCEL_REQUESTED"}:
                        break
                    time.sleep(0.5)
                case = {
                    "action": action,
                    "task_id": task_id,
                    "task_status": task["status"],
                    "passed": task["status"] == "SUCCEEDED",
                }
                if case["passed"]:
                    with SessionLocal() as db:
                        if action == "courseware":
                            resource = (
                                db.query(Resource)
                                .filter(Resource.generated_for_user_id == auth["user_id"])
                                .order_by(Resource.id.desc())
                                .first()
                            )
                            resource_id = resource.id
                            case.update(
                                resource_id=resource.id,
                                characters=len(resource.content),
                                audit_status=resource.audit_status,
                                source="authorized_live",
                            )
                            assert len(resource.content) > 300 and "TCP" in resource.content
                            export = client.get(
                                services["resource"] + f"/resources/{resource_id}/export.docx",
                                headers=headers,
                            )
                            assert export.status_code == 200 and export.content[:2] == b"PK"
                            (output / "live-courseware.docx").write_bytes(export.content)
                            (output / "live-courseware.md").write_text(
                                resource.content, encoding="utf-8"
                            )
                        else:
                            exercises = (
                                db.query(Exercise)
                                .filter(Exercise.generated_for_user_id == auth["user_id"])
                                .all()
                                if hasattr(Exercise, "generated_for_user_id")
                                else db.query(Exercise).all()
                            )
                            text = json.dumps(task["result"], ensure_ascii=False)
                            case.update(
                                exercise_count=len(exercises),
                                fallback="deterministic_fallback" in text,
                            )
                            case["passed"] = len(exercises) == 3 and not case["fallback"]
                            (output / "live-exercise-result.json").write_text(
                                text, encoding="utf-8"
                            )
                    # Same request key must reuse task; no deliberate paid regeneration.
                    replay = client.post(
                        services["agent"] + "/assistant/chat", json=payload, headers=headers
                    )
                    case["replay_same_task"] = (
                        replay.status_code == 200 and replay.json()["task"]["id"] == task_id
                    )
                else:
                    case["error"] = str(task.get("result"))[:800]
                results.append(case)
                (output / "business-results.json").write_text(
                    json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
                )
            from services.agent_service.app.services.deepseek_search import (
                fetch_source,
                search_sources,
            )

            try:
                sources = search_sources("TCP congestion control site:ietf.org", count=2)
                results.append({"action": "search", "passed": bool(sources), "sources": sources})
                if sources:
                    try:
                        fetched = fetch_source(sources[0]["url"])
                        results.append(
                            {
                                "action": "fetch",
                                "passed": True,
                                "characters": len(fetched["content"]),
                            }
                        )
                    except Exception as exc:
                        results.append(
                            {
                                "action": "fetch",
                                "passed": False,
                                "status": "BLOCKED_OR_FAILED",
                                "error": type(exc).__name__ + ": " + str(exc)[:240],
                            }
                        )
            except Exception as exc:
                results.append(
                    {
                        "action": "search",
                        "passed": False,
                        "error": type(exc).__name__ + ": " + str(exc)[:240],
                    }
                )
        node_env = dict(env)
        node_env.update(
            FRONTEND_HOST="127.0.0.1",
            FRONTEND_PORT=str(frontend_port),
            VITE_SAKURAFRP_SAME_ORIGIN="false",
        )
        for name, url in services.items():
            node_env[f"VITE_{name.upper()}_API_BASE_URL"] = url
        empty = output / "empty-env"
        empty.mkdir()
        config = output / "vite.live.config.mjs"
        config.write_text(
            "import original from "
            + json.dumps((ROOT / "web-app/vite.config.ts").as_posix())
            + ";export default {...original,root:"
            + json.dumps((ROOT / "web-app").as_posix())
            + ",envDir:"
            + json.dumps(empty.as_posix())
            + ",cacheDir:"
            + json.dumps((output / "vite-cache").as_posix())
            + "};",
            encoding="utf-8",
        )
        vite = launch(
            "vite",
            [
                "node",
                str(ROOT / "web-app/node_modules/vite/bin/vite.js"),
                "--config",
                str(config),
                "--host",
                "127.0.0.1",
                "--port",
                str(frontend_port),
                "--strictPort",
            ],
            node_env,
        )
        wait(frontend, vite)
        node_env["LIVE_E2E_CONFIG"] = json.dumps(
            dict(
                frontend=frontend,
                services=services,
                username=username,
                password=password,
                output=str(output),
                resourceId=resource_id,
            )
        )
        browser = launch(
            "browser", ["node", str(ROOT / "tests/e2e/run-live-authorized.mjs")], node_env
        )
        code = browser.wait(timeout=120)
        results.append({"action": "real_browser", "passed": code == 0})
    finally:
        for name, proc in reversed(processes):
            if proc.poll() is None:
                if name in {"vite", "browser"} and os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                        capture_output=True,
                        timeout=10,
                    )
                else:
                    proc.terminate()
                try:
                    proc.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
        for log in logs:
            log.close()
        (output / "business-results.json").write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (output / "process-cleanup.json").write_text(
            json.dumps(
                [{"name": n, "pid": p.pid, "stopped": p.poll() is not None} for n, p in processes],
                indent=2,
            ),
            encoding="utf-8",
        )
    assert all(r["passed"] for r in results if r.get("action") not in {"fetch", "search"}), results


if __name__ == "__main__":
    main()

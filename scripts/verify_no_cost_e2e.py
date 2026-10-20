"""Launch isolated APIs, Worker, Vite and browser against a local model simulator.

Run only through run_no_cost_tests.py; no production dotenv or credentials.
"""

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
from no_cost_mock_provider import MockProvider

from common.db.bootstrap import ensure_database_schema
from common.db.session import SessionLocal
from common.models.learning import AssistantTask, ChatMessage, Resource

ROOT = Path(__file__).resolve().parents[1]


def main():
    if os.environ.get("NO_COST_GUARD_ACTIVE") != "1":
        raise RuntimeError("Use scripts/run_no_cost_tests.py")
    output = Path(os.environ["NO_COST_NETWORK_LEDGER"]).parent
    ensure_database_schema()
    model = MockProvider(output / "mock-requests.jsonl").start()
    processes = []
    logs = []
    services = {}
    result = {"source": "LOCAL_MOCK", "api_checks": [], "browser": "NOT_RUN"}

    def port():
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            return sock.getsockname()[1]

    base_env = dict(os.environ)
    # The guard replaces even inherited sentinel keys; only local bases survive.
    base_env.update(
        DEEPSEEK_API_BASE=model.base_url,
        DEEPSEEK_API_KEY="no-cost-stub",
        DEEPSEEK_MODEL="no-cost-stub",
        ASSISTANT_TASK_EXECUTION_MODE="worker",
        CORS_ALLOW_ORIGINS="",
    )
    frontend_port = port()
    frontend = f"http://127.0.0.1:{frontend_port}"
    base_env["CORS_ALLOW_ORIGINS"] = frontend

    def launch(name, command, env):
        log = (output / (name + ".log")).open("w", encoding="utf-8")
        logs.append(log)
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        processes.append((name, process))
        return process

    def wait(url, process):
        end = time.monotonic() + 40
        while time.monotonic() < end:
            if process.poll() is not None:
                raise RuntimeError(f"Process exited during startup; see logs: {process.returncode}")
            try:
                if httpx.get(url, trust_env=False, timeout=1).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.2)
        raise TimeoutError(url)

    try:
        # Reserve all ports before starting children so each inherits the same
        # explicit allowlist; sequential startup avoids SQLite bootstrap races.
        ports = {
            name: port()
            for name in ["user", "agent", "resource", "evaluation", "teacher", "system"]
        }
        base_env["NO_COST_ALLOWED_PORTS"] = os.environ["NO_COST_ALLOWED_PORTS"]
        for name, value in ports.items():
            services[name] = f"http://127.0.0.1:{value}"
            process = launch(
                name,
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    f"services.{name}_service.app.main:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(value),
                ],
                dict(base_env),
            )
            wait(services[name] + "/health", process)
        launch(
            "worker",
            [
                sys.executable,
                "-m",
                "services.agent_service.app.services.assistant_worker",
                "--poll-interval",
                "0.5",
            ],
            dict(base_env),
        )
        username = "no_cost_" + secrets.token_hex(4)
        password = "NoCost-" + secrets.token_hex(8)
        with httpx.Client(timeout=40, trust_env=False) as client:
            registered = client.post(
                services["user"] + "/users/register",
                json={"username": username, "password": password, "role": "student"},
            )
            assert registered.status_code == 201, registered.text
            auth = registered.json()
            headers = {"Authorization": "Bearer " + auth["access_token"]}
            # A real persistent Worker task, followed by an idempotent replay.
            payload = {
                "message": "生成 TCP 课件",
                "action": "courseware",
                "client_request_id": "no-cost-e2e-resource-0001",
                "use_learning_context": False,
            }
            created = client.post(
                services["agent"] + "/assistant/chat", json=payload, headers=headers
            )
            assert created.status_code == 200, created.text
            task_id = created.json()["task"]["id"]
            deadline = time.monotonic() + 65
            while time.monotonic() < deadline:
                task = client.get(
                    services["agent"] + f"/assistant/tasks/{task_id}", headers=headers
                ).json()
                if task["status"] not in {"PENDING", "RUNNING", "CANCEL_REQUESTED"}:
                    break
                time.sleep(0.25)
            assert task["status"] == "SUCCEEDED", task
            count_before = model.calls
            replay = client.post(
                services["agent"] + "/assistant/chat", json=payload, headers=headers
            )
            assert replay.status_code == 200 and replay.json()["task"]["id"] == task_id
            assert model.calls == count_before
            result["api_checks"].append(
                {
                    "case": "resource_worker_and_replay",
                    "passed": True,
                    "task_id": task_id,
                    "source": "local_mock",
                }
            )
            exercise_payload = {
                "message": "生成 TCP 的三道练习题",
                "action": "exercise",
                "exercise_count": 3,
                "client_request_id": "no-cost-e2e-exercise-0001",
                "use_learning_context": False,
            }
            exercise_response = client.post(
                services["agent"] + "/assistant/chat", json=exercise_payload, headers=headers
            )
            assert exercise_response.status_code == 200, exercise_response.text
            exercise_id = exercise_response.json()["task"]["id"]
            deadline = time.monotonic() + 65
            while time.monotonic() < deadline:
                exercise_task = client.get(
                    services["agent"] + f"/assistant/tasks/{exercise_id}", headers=headers
                ).json()
                if exercise_task["status"] not in {"PENDING", "RUNNING", "CANCEL_REQUESTED"}:
                    break
                time.sleep(0.25)
            assert exercise_task["status"] == "SUCCEEDED", exercise_task
            exercise_set = exercise_task["result"]["exercise_set"]
            assert len(exercise_set["exercises"]) == 3, exercise_set
            assert "deterministic_fallback" not in json.dumps(exercise_set), exercise_set
            result["api_checks"].append(
                {
                    "case": "exercise_worker_no_fallback",
                    "passed": True,
                    "task_id": exercise_id,
                    "source": "local_mock",
                }
            )
            # Grade import is a real CSV parse, not a model capability claim.
            schema = client.get(services["evaluation"] + "/openapi.json").json()
            result["evaluation_paths"] = list(schema["paths"])
        node_env = dict(base_env)
        node_env.update(
            FRONTEND_HOST="127.0.0.1",
            FRONTEND_PORT=str(frontend_port),
            VITE_SAKURAFRP_SAME_ORIGIN="false",
        )
        for name, url in services.items():
            node_env[f"VITE_{name.upper()}_API_BASE_URL"] = url
        # Override envDir: Vite must not discover web-app developer env files.
        empty_env = output / "empty-env"
        empty_env.mkdir(exist_ok=True)
        vite_config = output / "vite.no-cost.config.mjs"
        vite_config.write_text(
            "import original from "
            + json.dumps((ROOT / "web-app/vite.config.ts").as_posix())
            + ";\nexport default {...original,root:"
            + json.dumps((ROOT / "web-app").as_posix())
            + ",envDir:"
            + json.dumps(empty_env.as_posix())
            + ",cacheDir:"
            + json.dumps((output / "vite-cache").as_posix())
            + "};\n",
            encoding="utf-8",
        )
        vite = launch(
            "vite",
            [
                "node",
                str(ROOT / "web-app/node_modules/vite/bin/vite.js"),
                "--config",
                str(vite_config),
                "--host",
                "127.0.0.1",
                "--port",
                str(frontend_port),
                "--strictPort",
            ],
            node_env,
        )
        wait(frontend, vite)
        node_env["NO_COST_E2E_CONFIG"] = json.dumps(
            dict(
                frontend=frontend,
                services=services,
                username=username,
                password=password,
                output=str(output),
            )
        )
        browser = launch("browser", ["node", str(ROOT / "tests/e2e/run-no-cost.mjs")], node_env)
        code = browser.wait(timeout=150)
        result["browser"] = "PASS_LOCAL_E2E" if code == 0 else "FAIL"
        if (output / "browser-report.json").exists():
            result["browser_details"] = json.loads(
                (output / "browser-report.json").read_text(encoding="utf-8")
            )
        assert code == 0, "Browser failed; inspect browser.log and failure-dom.txt"
        with SessionLocal() as db:
            result["database"] = {
                "resources": db.query(Resource).count(),
                "tasks": db.query(AssistantTask).count(),
                "messages": db.query(ChatMessage).count(),
            }
        docx = output / "courseware.docx"
        if docx.exists():
            from docx import Document

            document = Document(str(docx))
            result["docx_paragraphs"] = len(document.paragraphs)
            assert any("NC-RESOURCE-001" in p.text for p in document.paragraphs)
        result["passed"] = True
    except Exception as exc:
        result["passed"] = False
        result["error"] = str(exc)
        raise
    finally:
        for name, process in reversed(processes):
            if process.poll() is None:
                if name in {"vite", "browser"} and os.name == "nt":
                    subprocess.run(
                        ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                        capture_output=True,
                        timeout=10,
                    )
                else:
                    process.terminate()
                try:
                    process.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
        for log in logs:
            log.close()
        model.close()
        result["processes"] = [
            {"name": name, "pid": process.pid, "stopped": process.poll() is not None}
            for name, process in processes
        ]
        result["mock_requests"] = model.calls
        (output / "local-e2e-report.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )


if __name__ == "__main__":
    main()

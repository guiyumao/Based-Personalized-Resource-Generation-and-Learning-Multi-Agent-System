"""Run live knowledge APIs/worker/Chroma in an isolated runtime directory.

Usage: python scripts/verify_knowledge_v83.py --live --port 8012
The live option permits one Search and one Fetch task (each client has one retry).
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import shutil
import subprocess
import sys
import time
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", required=True)
    parser.add_argument("--port", type=int, default=8012)
    parser.add_argument("--runtime", type=Path)
    parser.add_argument("--plan", action="store_true", help="Also verify a live DeepSeek subject outline")
    parser.add_argument("--rollback", action="store_true", help="Verify a reviewed revision and rollback in real Chroma")
    parser.add_argument("--browser", action="store_true", help="Run existing Vue admin UI against isolated services")
    parser.add_argument("--build-point", action="store_true", help="Build one confirmed curriculum point using live sources")
    parser.add_argument("--maintenance", action="store_true", help="Verify scheduled inspection and bounded supplementation")
    parser.add_argument("--student", action="store_true", help="Generate real BBR courseware/exercises with one shared knowledge context")
    args = parser.parse_args()
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", args.port))
    runtime = (args.runtime or ROOT / "artifacts" / f"knowledge-v83-{time.strftime('%Y%m%d-%H%M%S')}").resolve()
    runtime.mkdir(parents=True, exist_ok=True)
    location_file = runtime / "chroma-location.json"
    if location_file.exists():
        chroma_directory = Path(json.loads(location_file.read_text(encoding="utf-8"))["path"])
    else:
        chroma_directory = Path(tempfile.mkdtemp(prefix="knowledge-v83-chroma-"))
        location_file.write_text(json.dumps({"path": str(chroma_directory)}), encoding="utf-8")
    env = os.environ.copy()
    env.update({
        "DATABASE_URL": f"sqlite:///{(runtime / 'verification.db').as_posix()}",
        "KNOWLEDGE_RUNTIME_ROOT": str(runtime), "CHROMA_MODE": "http",
        "CHROMA_PERSIST_DIRECTORY": str(chroma_directory), "CHROMA_HOST": "127.0.0.1", "CHROMA_PORT": "8016",
        "CHROMA_COLLECTION_NAME": "knowledge_v83_verification", "LLM_PREWARM_ENABLED": "false",
        "ASSISTANT_TASK_EXECUTION_MODE": "worker",
    })
    os.environ.update(env)
    import httpx
    from common.db.session import SessionLocal
    from common.models.learning import User
    from common.security.auth import create_access_token, hash_password

    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT, env=env, check=True)
    with SessionLocal() as db:
        browser_password = os.urandom(24).hex()
        admin = db.query(User).filter_by(username="v83-verifier").first()
        if admin is None:
            admin = User(username="v83-verifier", password_hash=hash_password(os.urandom(24).hex()), role="admin")
            db.add(admin); db.commit(); db.refresh(admin)
        token = create_access_token(str(admin.id))
        if args.browser:
            admin.password_hash = hash_password(browser_password)
            db.commit()
    api_log = open(runtime / "api.log", "a", encoding="utf-8")
    worker_log = open(runtime / "worker.log", "a", encoding="utf-8")
    api = subprocess.Popen([sys.executable, "-m", "uvicorn", "services.agent_service.app.main:app", "--host", "127.0.0.1", "--port", str(args.port)], cwd=ROOT, env=env, stdout=api_log, stderr=subprocess.STDOUT)
    worker = None
    extra_processes = []
    extra_logs = []
    report = {"runtime": str(runtime), "chroma_directory": str(chroma_directory), "port": args.port, "mock": False}
    try:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 8016))
        chroma_log = open(runtime / "chroma-http.log", "a", encoding="utf-8"); extra_logs.append(chroma_log)
        chroma = subprocess.Popen([shutil.which("chroma"), "run", "--path", str(chroma_directory), "--host", "127.0.0.1", "--port", "8016"], cwd=ROOT, env=env, stdout=chroma_log, stderr=subprocess.STDOUT)
        extra_processes.append(chroma)
        for _ in range(60):
            try:
                if httpx.get("http://127.0.0.1:8016/api/v2/heartbeat", timeout=2).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(1)
        with httpx.Client(base_url=f"http://127.0.0.1:{args.port}", timeout=1000) as client:
            for _ in range(90):
                try:
                    if client.get("/health", timeout=2).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                if api.poll() is not None:
                    raise RuntimeError("API exited; inspect isolated api.log")
                time.sleep(1)
            routes = client.get("/openapi.json").json()["paths"]
            assert "/knowledge-base/candidates/{candidate_id}/publish" in routes
            assert client.get("/knowledge-base/candidates").status_code == 401
            client.headers["Authorization"] = f"Bearer {token}"
            assert client.get("/knowledge-base/candidates").status_code == 200
            report["authenticated_http"] = True

            def call(method: str, path: str, **kwargs):
                response = client.request(method, path, **kwargs)
                if response.status_code >= 400:
                    raise RuntimeError(f"{method} {path}: HTTP {response.status_code}: {response.text[:1500]}")
                return response.json()

            worker = subprocess.Popen([sys.executable, "-m", "services.agent_service.app.services.knowledge_worker"], cwd=ROOT, env=env, stdout=worker_log, stderr=subprocess.STDOUT)

            def task(operation: str, key: str, **kwargs):
                queued = call("POST", "/knowledge-base/tasks", json={"client_request_id": key, "operation_type": operation, "subject": "computer_networks", **kwargs})
                deadline = time.monotonic() + 180
                while time.monotonic() < deadline:
                    result = call("GET", f"/knowledge-base/tasks/{queued['id']}")
                    if result["status"] in {"COMPLETED", "FAILED", "CANCELLED"}:
                        if result["status"] != "COMPLETED":
                            raise RuntimeError(f"Task {operation} failed: {result['error_code']}")
                        return result
                    time.sleep(1)
                raise RuntimeError(f"Task {operation} exceeded verification deadline")

            # A new HTTP index is rebuilt from the preserved canonical corpus;
            # the previous embedded index is retained for diagnosis.
            indexed = task("INDEX_REPAIR", f"v83-http-baseline-{time.time_ns()}")
            report["http_index_task_id"] = indexed["id"]

            search = task("SEARCH_SOURCES", "v83-bbr-search", query="site:ietf.org BBR congestion control draft")
            sources = search["result"]["sources"]
            assert sources
            report["search_task_id"] = search["id"]
            report["sources"] = sources
            fetched = task("FETCH_SOURCE", "v83-bbr-fetch", source_task_id=search["id"], source_index=0)
            report["fetch_task_id"] = fetched["id"]
            report["fetched_characters"] = len(fetched["result"]["source"]["content"])
            candidate = call("POST", "/knowledge-base/candidates", json={"source_task_id": fetched["id"], "subject": "computer_networks", "knowledge_point": "BBR congestion control"})
            candidate_id = candidate["id"]
            report["candidate_id"] = candidate_id
            if candidate["status"] == "PUBLISHED":
                active = next((item for item in call("GET", f"/knowledge-base/versions?candidate_id={candidate_id}")["items"] if item["is_active"]), None)
                if active and candidate["published_version_id"] != active["id"]:
                    call("POST", f"/knowledge-base/versions/{active['id']}/rollback")
            if candidate["status"] in {"DRAFT", "REJECTED", "APPROVED"}:
                call("PATCH", f"/knowledge-base/candidates/{candidate_id}", json={"license_name": "INTERNAL_TEST_ONLY", "license_evidence_url": candidate["source_url"], "publication_allowed": True})
                candidate = call("POST", f"/knowledge-base/candidates/{candidate_id}/submit")
            if candidate["status"] == "PENDING_REVIEW":
                call("POST", f"/knowledge-base/candidates/{candidate_id}/review", json={"decision": "APPROVE", "notes": "Isolated verification corpus only; source and fetched text inspected"})
            published = call("POST", f"/knowledge-base/candidates/{candidate_id}/publish")
            report["publication"] = {key: value for key, value in published.items() if key != "candidate"}
            assert (runtime / published["corpus_path"]).exists()
            again = call("POST", f"/knowledge-base/candidates/{candidate_id}/publish")
            assert again["version_id"] == published["version_id"]
            from services.agent_service.app.services.rag import ChromaRetriever
            retriever = ChromaRetriever()
            records = retriever.collection.get(where={"subject": "computer_networks"}, include=["documents", "metadatas"])
            assert records["ids"]
            report["vector_records"] = len(records["ids"])
            if args.rollback:
                versions = call("GET", f"/knowledge-base/versions?candidate_id={candidate_id}")["items"]
                original = min(versions, key=lambda item: item["number"])
                if len(versions) == 1:
                    revision = call("POST", f"/knowledge-base/candidates/{candidate_id}/revision")
                    call("PATCH", f"/knowledge-base/candidates/{candidate_id}", json={"content": revision["content"] + "\n\n## Isolated verification revision\n\nThis paragraph is a test marker for version restoration.\n"})
                    call("POST", f"/knowledge-base/candidates/{candidate_id}/submit")
                    call("POST", f"/knowledge-base/candidates/{candidate_id}/review", json={"decision": "APPROVE", "notes": "Isolated version restoration test"})
                    updated = call("POST", f"/knowledge-base/candidates/{candidate_id}/publish")
                    report["revision_version_id"] = updated["version_id"]
                else:
                    report["revision_version_id"] = max(versions, key=lambda item: item["number"])["id"]
                compared = call("GET", f"/knowledge-base/versions/{original['id']}/compare/{report['revision_version_id']}")
                assert compared["diff"]
                restored = call("POST", f"/knowledge-base/versions/{original['id']}/rollback")
                report["rollback"] = restored
                assert (runtime / original["corpus_path"]).exists()
                records = retriever.collection.get(where={"subject": "computer_networks"}, include=["metadatas"])
                expected_source = Path(original["corpus_path"]).relative_to("knowledge_base/corpus").as_posix()
                assert all(item["source"] == expected_source for item in records["metadatas"])
                report["rollback_vector_records"] = len(records["ids"])
            if args.plan:
                existing = next((item for item in call("GET", "/knowledge-base/tasks?limit=100")["items"]
                                 if item["operation_type"] == "AI_SUBJECT_PLAN"), None)
                planned = existing or call("POST", "/knowledge-base/construction/subject-plans", json={
                        "client_request_id": "v83-machine-learning-plan", "name": "机器学习", "stage": "本科",
                        "requirements": "仅两个章节：监督学习、模型评估；每章两个基础知识点，提供先修知识与教学目标。",
                    })
                for _ in range(180):
                    planned = call("GET", f"/knowledge-base/tasks/{planned['id']}")
                    if planned["status"] in {"COMPLETED", "FAILED"}:
                        break
                    time.sleep(1)
                assert planned["status"] == "COMPLETED", planned.get("error_code")
                confirmed = call("POST", f"/knowledge-base/construction/subject-plans/{planned['id']}/confirm", json=planned["result"]["outline"])
                report["subject_plan"] = {"task_id": planned["id"], "subject": confirmed, "usage": planned["result"].get("usage")}
                if args.build_point or args.maintenance:
                    points = call("GET", f"/knowledge-base/construction/subjects/{confirmed['subject_id']}/points")["items"]
                    point_id = points[0]["id"]
                    batch = call("POST", "/knowledge-base/construction/points/build", json={"client_request_id": "v83-one-point-draft-v2", "point_ids": [point_id], "mode": "COMPLETE_POINT", "focus": "site:scikit-learn.org stable linear_model LinearRegression"})
                    built = batch["items"][0]
                    if built["status"] == "FAILED":
                        built = call("POST", f"/knowledge-base/tasks/{built['id']}/retry")
                    for _ in range(180):
                        built = call("GET", f"/knowledge-base/tasks/{built['id']}")
                        if built["status"] in {"COMPLETED", "FAILED"}:
                            break
                        time.sleep(1)
                    assert built["status"] == "COMPLETED", built.get("error_code")
                    report["point_build"] = built
                    if args.maintenance:
                        from datetime import datetime, timedelta, timezone
                        existing_plans = call("GET", "/knowledge-base/maintenance-plans")["items"]
                        scheduled = next((item for item in existing_plans if item["name"] == "V83 isolated one-time maintenance"), None)
                        if scheduled is None:
                            scheduled = call("POST", "/knowledge-base/maintenance-plans", json={
                                "name": "V83 isolated one-time maintenance", "subject": confirmed["code"],
                                "next_run_at": (datetime.now(timezone.utc) + timedelta(seconds=5)).isoformat(),
                                "policy": {"mode": "AUTO_SUPPLEMENT_REVIEW", "point_ids": [point_id], "max_supplement_points": 1, "max_search_calls": 2, "max_fetch_calls": 2},
                            })
                        reports = []
                        for _ in range(180):
                            reports = call("GET", f"/knowledge-base/maintenance-plans/{scheduled['id']}/reports")["items"]
                            if reports and reports[0]["status"] in {"COMPLETED", "FAILED"}:
                                break
                            time.sleep(1)
                        assert reports and reports[0]["status"] == "COMPLETED", reports
                        report["maintenance"] = reports[0]
            if args.browser:
                original_version = min(call("GET", f"/knowledge-base/versions?candidate_id={candidate_id}")["items"], key=lambda item: item["number"])
                env["V83_BROWSER_CANDIDATE_ID"] = str(candidate_id)
                env["V83_ORIGINAL_VERSION_ID"] = str(original_version["id"])
                env["CORS_ALLOW_ORIGINS"] = "http://127.0.0.1:5186"
                # Restart only the API created by this verifier so its CORS
                # configuration matches the isolated Vue origin.
                api.terminate(); api.wait(timeout=15)
                api = subprocess.Popen([sys.executable, "-m", "uvicorn", "services.agent_service.app.main:app", "--host", "127.0.0.1", "--port", str(args.port)], cwd=ROOT, env=env, stdout=api_log, stderr=subprocess.STDOUT)
                for service, port in (("user_service", 8013), ("resource_service", 8014), ("system_service", 8015)):
                    with socket.socket() as probe:
                        probe.bind(("127.0.0.1", port))
                    log = open(runtime / f"{service}.log", "a", encoding="utf-8"); extra_logs.append(log)
                    process = subprocess.Popen([sys.executable, "-m", "uvicorn", f"services.{service}.app.main:app", "--host", "127.0.0.1", "--port", str(port)], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
                    extra_processes.append(process)
                for port in (args.port, 8013, 8014, 8015):
                    for _ in range(60):
                        try:
                            if httpx.get(f"http://127.0.0.1:{port}/health", timeout=2).status_code == 200:
                                break
                        except httpx.HTTPError:
                            pass
                        time.sleep(1)
                env.update({"VITE_USER_API_BASE_URL": "http://127.0.0.1:8013", "VITE_AGENT_API_BASE_URL": f"http://127.0.0.1:{args.port}",
                            "VITE_RESOURCE_API_BASE_URL": "http://127.0.0.1:8014", "VITE_SYSTEM_API_BASE_URL": "http://127.0.0.1:8015",
                            "VITE_EVALUATION_API_BASE_URL": f"http://127.0.0.1:{args.port}", "VITE_TEACHER_API_BASE_URL": f"http://127.0.0.1:{args.port}",
                            "VITE_SAKURAFRP_SAME_ORIGIN": "false", "E2E_BASE_URL": "http://127.0.0.1:5186",
                            "V83_RUNTIME": str(runtime), "V83_BROWSER_PASSWORD": browser_password})
                with socket.socket() as probe:
                    probe.bind(("127.0.0.1", 5186))
                log = open(runtime / "vite.log", "a", encoding="utf-8"); extra_logs.append(log)
                vite = subprocess.Popen([shutil.which("node"), "node_modules/vite/bin/vite.js", "--host", "127.0.0.1", "--port", "5186", "--strictPort"], cwd=ROOT / "web-app", env=env, stdout=log, stderr=subprocess.STDOUT)
                extra_processes.append(vite)
                subprocess.run([shutil.which("node"), "tests/e2e/run-knowledge-v83.mjs"], cwd=ROOT, env=env, check=True, timeout=300)
                report["browser"] = json.loads((runtime / "browser-report.json").read_text(encoding="utf-8"))
            if args.student:
                # Catalog registration reuses the existing BBR corpus; it does
                # not recreate or crawl the computer networking subject.
                subject = call("POST", "/knowledge-base/construction/subjects", json={"name": "计算机网络", "code": "computer_networks", "description": "Isolated BBR verification"})
                call("POST", f"/knowledge-base/construction/subjects/{subject['id']}/points", json={"name": "BBR", "chapter": "传输层", "aliases": ["BBR拥塞控制"], "objectives": ["理解带宽与时延模型"]})
                with SessionLocal() as db:
                    student = db.query(User).filter_by(username="v83-student").first()
                    if student is None:
                        student = User(username="v83-student", password_hash=hash_password(os.urandom(24).hex()), role="student")
                        db.add(student); db.commit(); db.refresh(student)
                    student_token = create_access_token(str(student.id))
                assistant_log = open(runtime / "assistant-worker.log", "a", encoding="utf-8"); extra_logs.append(assistant_log)
                assistant_worker = subprocess.Popen([sys.executable, "-m", "services.agent_service.app.services.assistant_worker"], cwd=ROOT, env=env, stdout=assistant_log, stderr=subprocess.STDOUT)
                extra_processes.append(assistant_worker)
                admin_token = client.headers["Authorization"]
                client.headers["Authorization"] = f"Bearer {student_token}"
                response = call("POST", "/assistant/chat", json={"client_request_id": "v83-student-bbr-combined-v1", "action": "combined", "knowledge_point": "BBR", "message": "生成BBR拥塞控制算法课件和3道练习", "exercise_count": 3, "course_key": "computer_networks", "use_learning_context": False, "allow_web_knowledge": False})
                generated = response["task"]
                for _ in range(240):
                    generated = call("GET", f"/assistant/tasks/{generated['id']}")
                    if generated["status"] in {"SUCCEEDED", "FAILED", "CANCELLED"}:
                        break
                    time.sleep(1)
                report["student_generation"] = {key: generated.get(key) for key in ("id", "status", "error_code")}
                body = generated.get("result") or {}
                report["student_generation"]["evidence"] = body.get("evidence")
                report["student_generation"]["cards"] = body.get("cards")
                assert generated["status"] == "SUCCEEDED", generated.get("error_code")
                assert body.get("evidence", {}).get("shared_knowledge_context_id")
                assert len((body.get("exercise_set") or {}).get("exercises", [])) == 3
                assert any(card.get("resource_id") for card in body.get("cards", []))
                client.headers["Authorization"] = admin_token
            report["passed"] = True
    except Exception as exc:
        report["passed"] = False
        report["error"] = str(exc)[:1000]
        raise
    finally:
        for process in (*reversed(extra_processes), worker, api):
            if process and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait(timeout=5)
        api_log.close(); worker_log.close()
        for log in extra_logs:
            log.close()
        (runtime / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"report": str(runtime / "report.json"), "passed": report.get("passed"), "error": report.get("error")}, ensure_ascii=True))


if __name__ == "__main__":
    main()

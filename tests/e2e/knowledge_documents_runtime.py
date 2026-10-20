"""Isolated real HTTP Chroma + Worker + Vue/Chromium document acceptance.

Run through scripts/run_no_cost_tests.py with allowed ports 18207/18208/15188.
No model or external source calls. All fixture identities are temporary.
"""

# ruff: noqa: E402 -- isolation environment must be set before application imports

import io
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

assert os.environ.get("NO_COST_GUARD_ACTIVE") == "1"
for required_port in (18207, 18208, 15188):
    with socket.socket() as probe:
        assert probe.connect_ex(("127.0.0.1", required_port)) != 0, (
            f"Test port already occupied: {required_port}"
        )
root = Path(os.environ["KNOWLEDGE_RUNTIME_ROOT"])
deps = Path("artifacts/aura-full-integration-20261020/chroma-test-deps").resolve()
if deps.exists():
    sys.path.append(str(deps))
    os.environ["PYTHONPATH"] += os.pathsep + str(deps)
chroma_dir = tempfile.mkdtemp(prefix="aura-doc-chroma-")
os.environ.update(
    CHROMA_MODE="http",
    CHROMA_HOST="127.0.0.1",
    CHROMA_PORT="18208",
    CHROMA_COLLECTION_NAME="aura_documents_acceptance",
    CHROMA_PERSIST_DIRECTORY=chroma_dir,
    IS_PERSISTENT="TRUE",
    PERSIST_DIRECTORY=chroma_dir,
    ANONYMIZED_TELEMETRY="FALSE",
    CORS_ALLOW_ORIGINS="http://127.0.0.1:15188",
)
import httpx
import uvicorn
from fastapi import FastAPI
from reportlab.pdfgen.canvas import Canvas

from common.db.bootstrap import ensure_database_schema
from common.db.session import SessionLocal
from common.models.learning import (
    KnowledgeBuildTask,
    KnowledgePoint,
    KnowledgeVersion,
    SystemSubject,
    User,
)
from common.security.auth import hash_password
from services.agent_service.app.main import app as agent_app
from services.agent_service.app.services.knowledge_tasks import expire_interrupted_tasks
from services.system_service.app.main import app as system_app
from services.user_service.app.main import app as user_app

ensure_database_schema()
password = secrets.token_urlsafe(20)
with SessionLocal() as db:
    db.add_all(
        [
            User(username="documents-admin", role="admin", password_hash=hash_password(password)),
            User(
                username="documents-student", role="student", password_hash=hash_password(password)
            ),
        ]
    )
    subject = SystemSubject(
        name="隔离文档数学", code="document_math", description="Isolated fixture"
    )
    db.add(subject)
    db.flush()
    point = KnowledgePoint(name="向量谱线", subject_id=subject.id)
    db.add(point)
    db.commit()
    subject_id, point_id = subject.id, point.id
stream = io.BytesIO()
canvas = Canvas(stream)
canvas.drawString(35, 800, "AURA_DOC_VECTOR_MARKER: vector spectral learning fixture.")
canvas.drawString(
    35, 780, "Vectors have magnitude and direction. This is isolated acceptance content."
)
canvas.save()
(root / "sample.pdf").write_bytes(stream.getvalue())
app = FastAPI()
app.mount("/user", user_app)
app.mount("/system", system_app)
app.mount("/agent", agent_app)
server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=18207, log_level="warning"))
thread = threading.Thread(target=server.run, daemon=True)
processes, streams = [], []


def start(args, name, *, cwd=None, env=None):
    log = (root / name).open("w", encoding="utf-8")
    streams.append(log)
    process = subprocess.Popen(
        args, cwd=cwd, env=env or dict(os.environ), stdout=log, stderr=subprocess.STDOUT
    )
    processes.append(process)
    return process


def ready(url):
    for _ in range(100):
        if any(process.poll() is not None for process in processes):
            raise RuntimeError("An owned test service exited during startup; inspect its log")
        try:
            if httpx.get(url, timeout=1).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    raise RuntimeError(f"Isolated service did not start: {url}")


report = {
    "passed": False,
    "real_chroma": True,
    "paid_calls": 0,
    "chroma_directory": chroma_dir,
    "steps": [],
}
try:
    start(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "chromadb.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            "18208",
        ],
        "chroma.log",
    )
    ready("http://127.0.0.1:18208/api/v2/heartbeat")
    thread.start()
    for _ in range(50):
        if server.started:
            break
        time.sleep(0.1)
    assert server.started, "Owned API server did not bind"
    ready("http://127.0.0.1:18207/agent/health")
    env = dict(os.environ)
    for service in ["USER", "AGENT", "SYSTEM", "RESOURCE", "EVALUATION", "TEACHER"]:
        env[f"VITE_{service}_API_BASE_URL"] = f"http://127.0.0.1:18207/{service.lower()}"
    env.update(
        VITE_SAKURAFRP_SAME_ORIGIN="false",
        E2E_BASE_URL="http://127.0.0.1:15188",
        DOCS_API="http://127.0.0.1:18207",
        DOCS_PASSWORD=password,
        DOCS_ARTIFACTS=str(root),
    )
    start(
        [
            "node",
            "node_modules/vite/bin/vite.js",
            "--host",
            "127.0.0.1",
            "--port",
            "15188",
            "--strictPort",
        ],
        "vite.log",
        cwd="web-app",
        env=env,
    )
    ready(env["E2E_BASE_URL"])
    worker = start(
        [
            sys.executable,
            "-m",
            "services.agent_service.app.services.knowledge_worker",
            "--poll-interval",
            "0.5",
        ],
        "worker.log",
    )
    browser = subprocess.run(
        ["node", "tests/e2e/run-knowledge-documents.mjs"], env=env, timeout=210
    )
    assert browser.returncode == 0, "Browser acceptance failed; inspect browser-result.json"
    report["steps"].append("browser_upload_classify_review_worker_publish_student_search")
    client = httpx.Client(base_url="http://127.0.0.1:18207", timeout=60)
    login = client.post(
        "/user/users/login", json={"username": "documents-admin", "password": password}
    ).json()
    headers = {"Authorization": "Bearer " + login["access_token"]}

    def post(url, data=None):
        response = client.post("/agent" + url, json=data or {}, headers=headers)
        assert response.status_code < 300, response.text
        return response.json()

    def wait_task(task_id):
        for _ in range(180):
            response = client.get(f"/agent/knowledge-base/tasks/{task_id}", headers=headers).json()
            if response["status"] == "COMPLETED":
                return response
            assert response["status"] not in {"FAILED", "CANCELLED"}, response
            time.sleep(0.5)
        raise AssertionError("Publication task did not finish")

    versions = client.get("/agent/knowledge-base/versions", headers=headers).json()["items"]
    first = versions[0]
    original_cid = first["candidate_id"]
    post(f"/knowledge-base/candidates/{original_cid}/revision")
    edit = client.patch(
        f"/agent/knowledge-base/candidates/{original_cid}",
        headers=headers,
        json={
            "content": first["content"]
            + "\n\nREVISION_SECOND_MARKER is the revised teaching explanation."
        },
    )
    assert edit.status_code == 200
    post(f"/knowledge-base/candidates/{original_cid}/submit")
    post(
        f"/knowledge-base/candidates/{original_cid}/review",
        {"decision": "APPROVE", "notes": "isolated revised content"},
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: post(
                    f"/knowledge-base/candidates/{original_cid}/publish-task",
                    {"client_request_id": "revision-publication"},
                ),
                range(2),
            )
        )
    revision_task, duplicate = results
    assert duplicate["id"] == revision_task["id"]
    revision_result = wait_task(revision_task["id"])
    with SessionLocal() as db:
        assert db.query(KnowledgeVersion).filter_by(candidate_id=original_cid).count() == 2
        assert (
            db.query(KnowledgeVersion).filter_by(candidate_id=original_cid, is_active=True).count()
            == 1
        )
    restored = post(f"/knowledge-base/versions/{first['id']}/rollback")
    assert restored["retrieval_matches"] >= 1
    from services.agent_service.app.services.knowledge_base import KnowledgeBaseService

    old_source = first["corpus_path"].removeprefix("knowledge_base/corpus/")
    assert KnowledgeBaseService().search_indexed(
        "AURA_DOC_VECTOR_MARKER", filters={"source": old_source}, retrieval_mode="lexical"
    )
    report["steps"].append("revision_replaces_old_index_duplicate_request_and_rollback_verified")
    # Resource generation consumes real published context; only the LLM output
    # is a clearly labelled local stub, never a real-provider acceptance claim.
    from common.models.learning import Resource
    from common.schemas.agent import ResourceGenerationRequest
    from services.agent_service.app.services.knowledge_acquisition import acquire_context
    from services.agent_service.app.services.resource_generation import ResourceGenerationService

    with SessionLocal() as db:
        admin_id = db.query(User).filter_by(username="documents-admin").one().id
        context = acquire_context(
            db,
            actor_user_id=admin_id,
            subject="document_math",
            knowledge_point="向量谱线",
            allow_web=False,
        )
    assert context["retrieval_context"]["retrieved_chunks"]
    generator = ResourceGenerationService()
    captured = []

    def local_generation(variables, **kwargs):
        captured.append(variables["context_text"])
        return "# 向量谱线\n\n## 学习目标\n理解向量的大小与方向。\n\n## 知识讲解\n向量用来描述大小和方向，AURA_DOC_VECTOR_MARKER 是隔离资料的标记。\n\n## 示例讲解\n二维向量可以写成有序数对，例如 (1, 2)。\n\n## 课堂小结\n向量的含义取决于实际情境和坐标约定。\n\n## 学完后自测\n解释向量与标量的区别，并给出一个例子。"

    generator._invoke_llm = local_generation
    generated = generator.generate_courseware_with_plan(
        ResourceGenerationRequest(
            user_id=admin_id,
            subject="document_math",
            knowledge_point="向量谱线",
            resource_style="concise",
            performance_mode="fast",
            retrieval_context=context["retrieval_context"],
        )
    )
    assert any("AURA_DOC_VECTOR_MARKER" in text for text in captured)
    with SessionLocal() as db:
        resource = db.get(Resource, generated["id"])
        assert first["id"] in resource.knowledge_versions_json
    report["steps"].append(
        "real_published_context_to_stubbed_generation_and_persisted_version_reference"
    )
    report["generation_provider"] = "LOCAL_STUB_ONLY"
    worker.terminate()
    worker.wait(timeout=20)

    # New upload for real process death in the index->SQL gap.
    response = client.post(
        "/agent/knowledge-base/admin/documents/upload",
        files={
            "file": (
                "crash.md",
                b"# CRASH_DOC_MARKER\n\nCRASH_DOC_MARKER describes vector consistency and crash recovery in a controlled fixture.",
            )
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    doc_id = response.json()["id"]
    post(
        "/knowledge-base/admin/documents/classify",
        {"document_ids": [doc_id], "subject_id": subject_id, "point_ids": [point_id]},
    )
    candidate = post(f"/knowledge-base/admin/documents/{doc_id}/candidate")
    cid = candidate["id"]
    update = client.patch(
        f"/agent/knowledge-base/candidates/{cid}",
        headers=headers,
        json={
            "license_name": "INTERNAL_TEST_ONLY",
            "license_evidence_url": "https://example.org/license",
            "publication_allowed": True,
        },
    )
    assert update.status_code == 200
    post(f"/knowledge-base/candidates/{cid}/submit")
    post(
        f"/knowledge-base/candidates/{cid}/review",
        {"decision": "APPROVE", "notes": "isolated test only"},
    )
    task = post(
        f"/knowledge-base/candidates/{cid}/publish-task", {"client_request_id": "crash-publication"}
    )
    post(f"/knowledge-base/tasks/{task['id']}/cancel")
    task = post(
        f"/knowledge-base/candidates/{cid}/publish-task",
        {"client_request_id": "crash-publication-retry"},
    )
    crash = start(
        [sys.executable, "tests/e2e/knowledge_publication_crash_worker.py"], "crash-worker.log"
    )
    assert crash.wait(timeout=90) == 79
    with SessionLocal() as db:
        assert db.query(KnowledgeVersion).filter_by(candidate_id=cid).count() == 0
        queue = db.get(KnowledgeBuildTask, task["id"])
        assert queue.status == "RUNNING"
        queue.lease_expires_at = datetime.utcnow() - timedelta(seconds=1)
        db.commit()
    from services.agent_service.app.services.knowledge_base import KnowledgeBaseService

    before = KnowledgeBaseService().search_indexed(
        "CRASH_DOC_MARKER", filters={"subject": "document_math"}, retrieval_mode="lexical", top_k=20
    )
    assert not any(f"candidate_{cid}_" in row.get("source", "") for row in before)
    assert expire_interrupted_tasks() == 1
    time.sleep(3)
    recovery = start(
        [sys.executable, "-m", "services.agent_service.app.services.knowledge_worker", "--once"],
        "recovery-worker.log",
    )
    assert recovery.wait(timeout=90) == 0
    with SessionLocal() as db:
        queue = db.get(KnowledgeBuildTask, task["id"])
        assert queue.status == "COMPLETED", (queue.status, queue.error_code)
        assert queue.execution_attempt == 2
        assert db.query(KnowledgeVersion).filter_by(candidate_id=cid).count() == 1
    after = KnowledgeBaseService().search_indexed(
        "CRASH_DOC_MARKER", filters={"subject": "document_math"}, retrieval_mode="lexical", top_k=20
    )
    assert any(f"candidate_{cid}_" in row.get("source", "") for row in after)
    report["steps"].append("real_worker_hard_exit_orphan_hidden_and_attempt2_recovered")
    withdrawal = post(f"/knowledge-base/candidates/{cid}/withdraw")
    blocked = KnowledgeBaseService().search_indexed(
        "CRASH_DOC_MARKER", filters={"subject": "document_math"}, retrieval_mode="lexical", top_k=20
    )
    assert not any(f"candidate_{cid}_" in row.get("source", "") for row in blocked)
    cleanup = start(
        [sys.executable, "-m", "services.agent_service.app.services.knowledge_worker", "--once"],
        "withdraw-worker.log",
    )
    assert cleanup.wait(timeout=90) == 0
    report["steps"].append("withdrawal_blocks_cached_results_before_cleanup")
    report["passed"] = True
finally:
    (root / "runtime-result.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    for process in reversed(processes):
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
    server.should_exit = True
    if thread.is_alive():
        thread.join(timeout=10)
    for stream in streams:
        stream.close()

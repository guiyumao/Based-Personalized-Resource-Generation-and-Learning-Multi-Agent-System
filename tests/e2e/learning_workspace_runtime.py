"""Isolated real APIs/SQLite/browser; only generation/retrieval are controlled stubs."""

# ruff: noqa: E402
import json
import os
import secrets
import subprocess
import threading
import time
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

assert os.environ.get("NO_COST_GUARD_ACTIVE") == "1"
os.environ["EVALUATION_SERVICE_URL"] = "http://127.0.0.1:18316/evaluation"
from common.db.bootstrap import ensure_database_schema
from common.db.session import SessionLocal
from common.models.learning import (
    AnswerRecord,
    AssistantTask,
    ContextExercise,
    KnowledgePoint,
    LearningPath,
    Resource,
    StudyNote,
    SystemSubject,
    User,
    UserProfile,
)
from common.schemas.agent import ExerciseGenerationRequest
from common.security.auth import hash_password
from services.agent_service.app.main import app as agent_app
from services.agent_service.app.services import assistant_tasks
from services.agent_service.app.services.assistant_execution import ensure_write_allowed
from services.agent_service.app.services.chat_service import ChatService
from services.agent_service.app.services.exercise_generation import ExerciseGenerationService
from services.evaluation_service.app.main import app as evaluation_app
from services.resource_service.app.main import app as resource_app
from services.system_service.app.main import app as system_app
from services.teacher_service.app.main import app as teacher_app
from services.user_service.app.main import app as user_app

root = Path(os.environ["KNOWLEDGE_RUNTIME_ROOT"])
ensure_database_schema()
password = secrets.token_urlsafe(20)
with SessionLocal() as db:
    hashed = hash_password(password)
    learner = User(username="workspace-student", role="student", password_hash=hashed)
    other = User(username="workspace-other", role="student", password_hash=hashed)
    admin = User(username="workspace-admin", role="admin", password_hash=hashed)
    db.add_all([learner, other, admin])
    db.flush()
    user_id = learner.id
    db.add(UserProfile(user_id=learner.id, habits={"profile_setup_skipped": True}))
    subject = SystemSubject(name="计算机网络", code="network", description="Isolated fixture")
    db.add(subject)
    db.flush()
    point = KnowledgePoint(name="TCP", subject_id=subject.id)
    db.add(point)
    db.flush()
    point_id = point.id
    for index in [1, 2]:
        db.add(
            LearningPath(
                user_id=learner.id,
                status="active",
                path_data_json={
                    "user_id": learner.id,
                    "subject": subject.name,
                    "knowledge_point": f"TCP 计划{index}",
                    "path_revision": 0,
                    "stages": [
                        {
                            "stage_id": "s1",
                            "title": f"计划{index}目录",
                            "tasks": [
                                {
                                    "task_id": "t1",
                                    "title": f"阅读TCP课件{index}",
                                    "task_type": "courseware",
                                    "knowledge_point": "TCP",
                                    "objective": "理解可靠传输",
                                    "completed": False,
                                    "depends_on": [],
                                },
                                {
                                    "task_id": "t2",
                                    "title": f"完成TCP练习{index}",
                                    "task_type": "exercise",
                                    "knowledge_point": "TCP",
                                    "completed": False,
                                    "depends_on": [],
                                },
                            ],
                        }
                    ],
                },
            )
        )
    db.add(
        Resource(
            title="TCP版本课件",
            type="article",
            content="# TCP可靠传输\n\nWORKSPACE_SOURCE_TOKEN\n\n序列号与确认机制。",
            generated_for_user_id=learner.id,
            knowledge_point_id=point.id,
        )
    )
    db.add(
        Resource(
            title="其他账户私人课件",
            type="article",
            content="private",
            generated_for_user_id=other.id,
            knowledge_point_id=point.id,
        )
    )
    if os.getenv("LOCAL_ARTIFACT_TEST") == "1":
        db.add(Resource(title="TCP导图", type="mind_map", content="# TCP\n确认与重传", generated_for_user_id=learner.id, knowledge_point_id=point.id,
            structured_json=json.dumps({"structured":{"nodes":[{"id":"root","label":"TCP","parent_id":None},{"id":"n1","label":"确认","parent_id":"root"}]}})))
    db.commit()


def controlled_workflow(db, task, request):
    # Model workflow boundary stub; real task claim/lease, validation, exercise
    # persistence, bindings, grading and profile updates remain in production code.
    assert "Resource excerpt" in request.payload["reference_materials"]
    ensure_write_allowed(db)
    generated = [
        {
            "knowledge_point": "TCP",
            "question_type": "choice",
            "difficulty": "foundation",
            "prompt": f"TCP隔离练习{i + 1}：可靠传输依赖什么？",
            "options": ["A. 序列号与确认", "B. 不需要确认"],
            "answer": "A",
            "analysis": "TCP使用序列号和确认机制。",
        }
        for i in range(3)
    ]
    exercise_request = ExerciseGenerationRequest(
        user_id=task.user_id,
        knowledge_point="TCP",
        exercise_count=3,
        assistant_operation_key=f"workspace:{task.id}",
    )
    exercises = ExerciseGenerationService()._persist_exercises(
        db, exercise_request, generated, db.get(KnowledgePoint, point_id)
    )
    return {
        "status": "success",
        "outputs": {"exercise_generation_agent": {"exercise_set": {"exercises": exercises}}},
        "agent_calls": [],
        "selected_agents": ["exercise_generation_agent"],
    }


assistant_tasks._run_task_workflow = controlled_workflow
ChatService._search_knowledge_base = lambda *_: {
    "found": True,
    "articles": [],
    "context": "controlled retrieval",
}
ChatService._should_use_large_model = lambda *_: False


def controlled_answer(
    self,
    question,
    history,
    kb_result,
    learning_context="",
    teaching_mode="standard",
    attachment_context="",
):
    assert "WORKSPACE_SOURCE_TOKEN" in attachment_context
    return "隔离模型桩：当前TCP课件使用序列号与确认机制。", "controlled-test-stub"


ChatService._generate_with_small_model = controlled_answer

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:15196"],
    allow_methods=["*"],
    allow_headers=["*"],
)
for prefix, service in [
    ("user", user_app),
    ("evaluation", evaluation_app),
    ("agent", agent_app),
    ("resource", resource_app),
    ("teacher", teacher_app),
    ("system", system_app),
]:
    app.mount("/" + prefix, service)
server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=18316, log_level="warning"))
thread = threading.Thread(target=server.run, daemon=True)
thread.start()
env = dict(os.environ)
for name in ["USER", "EVALUATION", "AGENT", "RESOURCE", "TEACHER", "SYSTEM"]:
    env[f"VITE_{name}_API_BASE_URL"] = f"http://127.0.0.1:18316/{name.lower()}"
env.update(
    E2E_BASE_URL="http://127.0.0.1:15196",
    WORKSPACE_API="http://127.0.0.1:18316",
    WORKSPACE_PASSWORD=password,
    WORKSPACE_ARTIFACTS=str(root),
)
with (root / "vite.log").open("w", encoding="utf-8") as log:
    vite = subprocess.Popen(
        [
            "node",
            "node_modules/vite/bin/vite.js",
            "--host",
            "127.0.0.1",
            "--port",
            "15196",
            "--strictPort",
        ],
        cwd="web-app",
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    try:
        for _ in range(100):
            try:
                if server.started and httpx.get(env["E2E_BASE_URL"], timeout=1).status_code == 200:
                    break
            except Exception:
                pass
            time.sleep(0.2)
        else:
            raise RuntimeError("Isolated workspace runtime unavailable")
        result = subprocess.run(
            ["node", "tests/e2e/run-learning-workspace.mjs"], env=env, timeout=200
        )
        if result.returncode == 0:
            with SessionLocal() as db:
                assert db.query(StudyNote).filter_by(user_id=user_id).count() == 1
                assert db.query(AnswerRecord).filter_by(user_id=user_id).count() == 1
                assert db.query(ContextExercise).count() == 3
                assert (
                    db.query(AssistantTask).filter_by(user_id=user_id, status="SUCCEEDED").count()
                    == (4 if os.getenv("LOCAL_ARTIFACT_TEST") == "1" else 1)
                )
                note = db.query(StudyNote).filter_by(user_id=user_id).one()
                assert note.learning_context_id and note.source_resource_version
                (root / "db-evidence.json").write_text(
                    json.dumps(
                        {
                            "notes": 1,
                            "answer_records": 1,
                            "bound_exercises": 3,
                            "completed_tasks": 4 if os.getenv("LOCAL_ARTIFACT_TEST") == "1" else 1,
                            "note_resource_version": note.source_resource_version,
                            "real_model_calls": 0,
                        }
                    ),
                    encoding="utf-8",
                )
        raise SystemExit(result.returncode)
    finally:
        vite.terminate()
        vite.wait(timeout=20)
        server.should_exit = True
        thread.join(timeout=15)

"""No-cost isolated APIs, seeded with this run's real generated courseware."""
import json
import os
from pathlib import Path

from fastapi import FastAPI
from common.db.bootstrap import ensure_database_schema
from common.db.session import SessionLocal
from common.models.learning import User, LearningPath, Resource, KnowledgePoint, UserProfile
from common.learning_context import create_context
from common.resource_version import resource_version
from common.security.auth import create_access_token
from common.schemas.agent import ResourceGenerationRequest
from services.agent_service.app.services.resource_generation import ResourceGenerationService
from services.agent_service.app.main import app as agent
from services.user_service.app.main import app as user
from services.resource_service.app.main import app as resource
from services.evaluation_service.app.main import app as evaluation

assert os.getenv("NO_COST_GUARD_ACTIVE") == "1"
ensure_database_schema()
root = Path(os.environ["TEACHING_BROWSER_OUTPUT"])
contexts = []
with SessionLocal() as db:
    if not db.get(User, 2):
        db.add(User(id=2, username="isolated-second", password_hash="unused"))
    if not db.get(UserProfile, 1):
        db.add(UserProfile(user_id=1, mastery_json={}))
    db.commit()
    for row in db.query(Resource).filter(Resource.generation_status == "generated", Resource.knowledge_review_required.is_(False)).all():
        point = db.get(KnowledgePoint, row.knowledge_point_id)
        stored = json.loads(row.structured_json)
        # Backfill explicit practice membership for artefacts generated before
        # the exercise persistence patch; reuse actual model-produced questions.
        ResourceGenerationService()._persist_courseware_exercises(db, ResourceGenerationRequest(
            user_id=1, knowledge_point=point.name, subject=stored["subject"]), row)
        db.commit()
        path = LearningPath(user_id=1, status="active", path_data_json={"user_id": 1, "overview": "真实生成课件阅读验证", "estimated_days": 1, "subject": stored["subject"],
            "knowledge_point": point.name, "stages": [{"stage_id": "s1", "title": "学习", "description": "阅读与巩固", "tasks": [
                {"task_id": "t1", "title": point.name, "task_type": "courseware", "knowledge_point": point.name, "objective": "学习并完成自测", "estimated_minutes": 40, "difficulty": "foundation", "completed": False}]}]})
        db.add(path)
        db.commit()
        context = create_context(db, 1, client_request_id=f"teaching-browser-{row.id}", plan_id=path.id,
            module_id="s1", task_key="t1", resource_id=row.id, expected_resource_version=resource_version(row))
        contexts.append({"id": context.id, "topic": point.name, "resource_id": row.id, "plan_id": path.id,
                         "version": resource_version(row), "characters": len(row.content)})
    (root/"browser-fixture.json").write_text(json.dumps({"contexts": contexts,
        "token": create_access_token("1"), "other_token": create_access_token("2")}, ensure_ascii=False), encoding="utf-8")

app = FastAPI()
app.mount("/agent", agent)
app.mount("/user", user)
app.mount("/resource", resource)
app.mount("/evaluation", evaluation)

"""Authorized real model acceptance, four subjects, isolated persistence."""
import json
import os
from pathlib import Path

from common.db.bootstrap import ensure_database_schema
from common.db.session import SessionLocal
from common.models.learning import User, Resource, KnowledgePoint, SystemSubject
from common.performance import performance_trace
from common.schemas.agent import ResourceGenerationRequest
from services.agent_service.app.services.resource_generation import ResourceGenerationService
from services.agent_service.app.services.personalization import LearnerPersonalizationSnapshot
from services.agent_service.app.services.courseware_quality import report

assert os.getenv("NO_COST_GUARD_ACTIVE") == "1" and os.getenv("MODEL_USAGE_MODE") == "LIVE"
output = Path(os.environ["LIVE_OUTPUT"])
ensure_database_schema()
topics = [("冒泡排序", "算法"), ("TCP协议", "计算机网络"), ("链表", "数据结构"), ("一元二次方程求根公式", "数学")]
with SessionLocal() as db:
    if not db.get(User, 1):
        db.add(User(id=1, username="teaching-live-isolated", password_hash="unused"))
        for i, (topic, subject) in enumerate(topics, 1):
            db.add(SystemSubject(id=i, name=subject, code=f"live-{i}", description="isolated acceptance"))
            db.add(KnowledgePoint(id=i, name=topic, subject_id=i))
        db.commit()
results = []
for i, (topic, subject) in enumerate(topics, 1):
    try:
        with performance_trace(service_name="teaching-live", user_id=1, task_type="courseware") as trace:
            trace.set_context(deadline_seconds=1200, retry_budget=4)
            service = ResourceGenerationService()
            response = service.generate_courseware_with_plan(ResourceGenerationRequest(user_id=1,
                knowledge_point=topic, subject=subject, knowledge_point_id=str(i), performance_mode="fast",
                request_text=f"为初学者生成{topic}完整标准课件，强调严谨原理与完整案例。",
                assistant_operation_key=f"teaching-live-{i}"), snapshot=LearnerPersonalizationSnapshot(
                    learner_profile={"history_disabled": True}, mastery_score=None, recent_mistakes=[], answered_count=0, correct_rate=None))
        with SessionLocal() as db:
            saved = db.get(Resource, response["id"])
            assert saved.content == response["content"]
            data = json.loads(saved.structured_json)
            validation = report(data["chapters"], data["sources"])
            assert validation["status"] == "passed", validation
            assert len(data["chapters"]) == 9
            (output/f"courseware-{i}.md").write_text(saved.content, encoding="utf-8")
            (output/f"courseware-{i}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            results.append({"topic": topic, "resource_id": saved.id, "characters": len(saved.content), "quality": validation, "passed": True})
    except Exception as exc:
        results.append({"topic": topic, "passed": False, "error": str(exc)[:500]})
    (output/"business-result.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
assert all(row["passed"] for row in results), results

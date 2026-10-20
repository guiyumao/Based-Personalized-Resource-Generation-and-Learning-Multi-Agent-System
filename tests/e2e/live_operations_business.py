"""Real configured model services, persistence, contextual QA and evaluation."""
import asyncio
import json
import os
from pathlib import Path

from fastapi.testclient import TestClient
from common.db.bootstrap import ensure_database_schema
from common.db.session import SessionLocal, get_db
from common.dependencies import get_current_user
from common.learning_context import create_context
from common.models.learning import KnowledgePoint, LearningPath, Resource, SystemSubject, User
from common.models.operations import ModelCall
from common.performance import performance_trace
from common.resource_version import resource_version
from common.schemas.agent import ExerciseGenerationRequest, ResourceGenerationRequest
from services.agent_service.app.main import app
from services.agent_service.app.services.resource_generation import ResourceGenerationService
from services.agent_service.app.services.exercise_generation import ExerciseGenerationService
from services.evaluation_service.app.services.report_service import ReportService
from services.evaluation_service.app.schemas.report import PracticeSubmission

assert os.getenv("NO_COST_GUARD_ACTIVE")=="1" and os.getenv("MODEL_USAGE_MODE")=="LIVE"
output=Path(os.environ["LIVE_OUTPUT"])
ensure_database_schema()
with SessionLocal() as db:
    if db.get(User,1) is None:
        db.add(User(id=1,username="live-ops-isolated",password_hash="unused"))
        db.add(SystemSubject(id=1,name="计算机网络",code="network",description="Isolated live acceptance"))
        db.flush()
        db.add(KnowledgePoint(id=1,name="TCP可靠传输",subject_id=1))
        db.add(LearningPath(id=1,user_id=1,status="active",path_data_json={"subject":"计算机网络","stages":[{"stage_id":"s1","tasks":[{"task_id":"t1","knowledge_point":"TCP可靠传输"}]}]}))
        db.commit()
    previous=db.query(Resource).filter_by(assistant_operation_key="live-ops-resource").first()
    resource_id=previous.id if previous else None
if resource_id is None:
    with performance_trace(service_name="live-acceptance",user_id=1,task_type="courseware"):
        resource=ResourceGenerationService().generate_courseware_with_plan(ResourceGenerationRequest(user_id=1,knowledge_point="TCP可靠传输",
            resource_style="concise",preferred_word_count=350,performance_mode="fast",learner_profile={"history_disabled":True},
            request_text="生成350字TCP可靠传输课件，包含学习目标、知识讲解、示例、小结与自测。",assistant_operation_key="live-ops-resource"))
    resource_id=resource["id"]
with SessionLocal() as db:
    saved=db.get(Resource,resource_id)
    assert saved.generated_for_user_id==1 and saved.audit_status=="passed"
    (output/"courseware.md").write_text(saved.content,encoding="utf-8")
    context_id=create_context(db,1,client_request_id="live-ops-context",plan_id=1,module_id="s1",task_key="t1",resource_id=resource_id,
        expected_resource_version=resource_version(saved)).id
with performance_trace(service_name="live-acceptance",user_id=1,task_type="exercises"):
    exercises=ExerciseGenerationService().generate_exercises(ExerciseGenerationRequest(user_id=1,knowledge_point="TCP可靠传输",exercise_count=3,
        question_type_counts={"choice":3},performance_mode="fast",learner_profile={"history_disabled":True},
        assistant_operation_key="live-ops-exercises-real"))
assert exercises["audit_reason"]!="deterministic_fallback" and len(exercises["exercises"])==3,exercises
(output/"exercises.json").write_text(json.dumps(exercises,ensure_ascii=False,indent=2),encoding="utf-8")
app.dependency_overrides[get_current_user]=lambda:User(id=1,username="live-ops-isolated",password_hash="unused")
with performance_trace(service_name="live-acceptance",user_id=1,task_type="qa"):
    response=TestClient(app).post("/assistant/chat",json={"action":"qa","message":"根据当前课件，用100字解释确认号如何帮助发送端发现丢包。",
        "client_request_id":"live-ops-qa","learning_context_id":context_id,"use_learning_context":False})
assert response.status_code==200,response.text
(output/"qa.json").write_text(json.dumps(response.json(),ensure_ascii=False,indent=2),encoding="utf-8")
class Publisher:
    def publish(self,*_):
        pass
question=exercises["exercises"][0]
result=asyncio.run(ReportService(publisher=Publisher()).evaluate_practice(PracticeSubmission(user_id=1,exercise_id=question["exercise_id"],knowledge_point="TCP可靠传输",
    question_type="choice",user_answer=question["answer"],correct_answer="forged",analysis="",client_request_id="live-ops-answer")))
assert result.is_correct
with SessionLocal() as db:
    rows=db.query(ModelCall).all()
    assert 1<=len(rows)<=6 and all(row.mode=="LIVE" for row in rows)
    assert all(row.usage_status=="KNOWN" for row in rows)
    assert sum(row.output_tokens for row in rows)<=6000
    evidence={"passed":True,"resource_id":resource_id,"exercise_ids":[row["exercise_id"] for row in exercises["exercises"]],"qa_http":response.status_code,
        "grading_correct":True,"calls":[{"provider":row.provider,"model":row.model,"response_model":row.response_model,"input_tokens":row.input_tokens,"output_tokens":row.output_tokens,"feature":row.feature} for row in rows]}
    (output/"business-result.json").write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding="utf-8")

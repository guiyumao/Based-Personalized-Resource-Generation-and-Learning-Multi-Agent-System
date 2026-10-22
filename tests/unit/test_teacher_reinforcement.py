"""Real database/API reinforcement loop; provider calls are explicitly stubbed."""
import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from common.db.session import SessionLocal
from common.models.learning import (
    AnswerRecord,
    Assignment,
    Exercise,
    KnowledgePoint,
    Resource,
    StudyActivity,
    SystemSubject,
    User,
)
from common.models.teacher_support import ReinforcementAttempt, ReinforcementDraft
from common.security.auth import create_access_token
from services.teacher_service.app.main import app
from services.teacher_service.app.services import course_support, reinforcement_feedback


@pytest.fixture
def support(monkeypatch):
    suffix = uuid4().hex[:10]
    with SessionLocal() as db:
        users = [User(username=f"support-{suffix}-{i}", password_hash="disabled-test-login", role=role, is_active=True)
                 for i, role in enumerate(("teacher", "teacher", "student", "student"))]
        db.add_all(users)
        subject = SystemSubject(name=f"算法-{suffix}", description="教师补强测试学科")
        db.add(subject)
        db.flush()
        point = KnowledgePoint(name="二叉树遍历", subject_id=subject.id)
        other = KnowledgePoint(name="无关课程知识点", subject_id=subject.id)
        db.add_all([point, other])
        db.commit()
        ids = [u.id for u in users]
        subject_name, point_id, other_id = subject.name, point.id, other.id
    calls = {"generate": 0, "feedback": 0}

    def generate(context):
        calls["generate"] += 1
        return {"rationale": "围绕本课程知识点设计诊断或错题变式", "questions": [
            {"knowledge_point": "二叉树遍历", "question_type": "choice", "prompt": "二叉树中序遍历首先访问哪个部分？", "options": ["A.左子树", "B.根节点"], "answer": "A", "analysis": "中序遍历顺序是左子树、根节点、右子树。", "evidence_ids": []},
            {"knowledge_point": "二叉树遍历", "question_type": "short_answer", "prompt": "请解释中序遍历访问各节点的先后顺序。", "options": [], "answer": "左子树、根节点、右子树", "analysis": "递归先访问左子树，再访问根节点，最后访问右子树。", "evidence_ids": []},
        ]}, "test-provider"

    def feedback(context):
        calls["feedback"] += 1
        return {"grades": [{"question_index": 1, "score": 30, "comment": "把根节点放在左子树前，遍历顺序有误"}],
                "analysis": "两题都反映出对根节点访问时机的混淆。", "recommendations": ["让学生用三节点二叉树画出访问顺序"]}, "test-provider"
    monkeypatch.setattr(course_support, "invoke_model", generate)
    monkeypatch.setattr(reinforcement_feedback, "invoke_feedback", feedback)
    with TestClient(app) as client:
        def req(who, method, path, data=None, status=200, files=None):
            response = client.request(method, path, headers={"Authorization": "Bearer " + create_access_token(str(ids[who]))},
                                      **({"files": files} if files else {"json": data}))
            assert response.status_code == status, response.text
            return response.json().get("data")
        room = req(0, "POST", "/teacher/classes", {"name": "补强闭环班", "subject": subject_name, "join_mode": "open"})
        for who in (2, 3):
            req(who, "POST", f"/learning/classrooms/{room['id']}/join")
        yield req, ids, room, point_id, other_id, calls


def delivery(req, room, student_id=None):
    return req(0, "POST", f"/teacher/classes/{room['id']}/course-resources", {
        "request_id": uuid4().hex, "student_user_id": student_id, "title": "二叉树遍历讲义",
        "content": "中序遍历按左子树、根节点、右子树顺序访问。", "knowledge_points": ["二叉树遍历"],
    })


def draft_and_publish(req, ids, room):
    material = delivery(req, room, ids[2])
    draft = req(0, "POST", f"/teacher/classes/{room['id']}/reinforcements", {
        "request_id": uuid4().hex, "student_user_id": ids[2], "delivery_ids": [material["id"]], "question_count": 2,
    })
    assert draft["status"] == "ready"
    published = req(0, "POST", f"/teacher/reinforcements/{draft['id']}/publish", {"title": "定向补强作业"})
    return draft, published["assignment_id"]


def test_submit_immediate_solutions_mistakes_teacher_feedback_and_idempotence(support):
    req, ids, room, _, _, calls = support
    draft, assignment_id = draft_and_publish(req, ids, room)
    before = next(a for a in req(2, "GET", "/teacher/students/me/homework") if a["id"] == assignment_id)
    assert all("answer" not in q and "analysis" not in q for q in before["practice_questions"])
    assert all(a["id"] != assignment_id for a in req(3, "GET", "/teacher/students/me/homework"))
    req(3, "POST", f"/teacher/students/me/homework/{assignment_id}/submit", {"answers": ["B", "根左右"]}, status=403)
    req(3, "POST", f"/teacher/students/me/homework/{assignment_id}/attachments", files={"file": ("wrong.txt", b"forbidden", "text/plain")}, status=403)
    submission = req(2, "POST", f"/teacher/students/me/homework/{assignment_id}/submit", {"answers": ["B", "先访问根节点"], "time_spent": 45})
    assert submission["practice_result"]["results"][0]["reference_answer"] == "A"
    assert submission["practice_result"]["results"][0]["is_correct"] is False
    assert submission["practice_result"]["results"][1]["is_correct"] is None
    after = next(a for a in req(2, "GET", "/teacher/students/me/homework") if a["id"] == assignment_id)
    assert after["my_submission"]["status"] == "submitted"  # teacher has not reviewed
    assert all("answer" in q and "analysis" in q for q in after["practice_questions"])
    result = after["my_submission"]["practice_result"]
    assert result["status"] == "completed" and all(r["is_correct"] is False for r in result["results"])
    teacher = req(0, "GET", f"/teacher/classes/{room['id']}/reinforcement-attempts")
    assert teacher[0]["student_user_id"] == ids[2] and teacher[0]["analysis"]
    req(1, "GET", f"/teacher/classes/{room['id']}/reinforcement-attempts", status=403)
    req(1, "POST", f"/teacher/reinforcement-attempts/{result['id']}/analyze", status=403)
    repeated = req(2, "POST", f"/teacher/students/me/homework/{assignment_id}/submit", {"answers": ["B", "先访问根节点"]})
    assert repeated["id"] == submission["id"] and calls == {"generate": 1, "feedback": 1}
    req(2, "POST", f"/teacher/students/me/homework/{assignment_id}/submit", {"answers": ["A", "左根右"]}, status=409)
    from services.evaluation_service.app.services.report_service import ReportService
    notebook = asyncio.run(ReportService().get_mistake_notebook(ids[2]))
    assert {int(item.exercise_id) for item in notebook.items} == {r["exercise_id"] for r in result["results"]}
    assert not asyncio.run(ReportService().get_mistake_notebook(ids[3])).items
    with SessionLocal() as db:
        assert db.query(AnswerRecord).filter_by(user_id=ids[2]).count() == 2
        assert db.query(ReinforcementAttempt).filter_by(draft_id=draft["id"]).count() == 1
    published = req(0, "POST", f"/teacher/reinforcements/{draft['id']}/publish", {"title": "网络重试"})
    assert published["assignment_id"] == assignment_id


def test_model_failure_keeps_references_and_unknown_subjective_out_of_mistakes(support, monkeypatch):
    req, ids, room, _, _, _ = support
    _, assignment_id = draft_and_publish(req, ids, room)
    monkeypatch.setattr(reinforcement_feedback, "invoke_feedback", lambda _: (_ for _ in ()).throw(RuntimeError("provider unavailable")))
    req(2, "POST", f"/teacher/students/me/homework/{assignment_id}/submit", {"answers": ["A", "换一种表达的左根右"]})
    own = next(a for a in req(2, "GET", "/teacher/students/me/homework") if a["id"] == assignment_id)
    result = own["my_submission"]["practice_result"]
    assert result["status"] == "failed" and result["error"]
    assert result["results"][1]["is_correct"] is None
    assert own["practice_questions"][1]["answer"]
    from services.evaluation_service.app.services.report_service import ReportService
    assert not asyncio.run(ReportService().get_mistake_notebook(ids[2])).items
    monkeypatch.setattr(reinforcement_feedback, "invoke_feedback", lambda _: ({"grades": [{"question_index": 1, "score": 95, "comment": "语义正确"}], "analysis": "答案语义正确", "recommendations": []}, "test-provider"))
    req(0, "POST", f"/teacher/reinforcement-attempts/{result['id']}/analyze")
    assert req(0, "GET", f"/teacher/classes/{room['id']}/reinforcement-attempts")[0]["status"] == "completed"


def test_evidence_course_boundary_unknowns_and_overlapping_platform_time(support):
    req, ids, room, point_id, other_id, _ = support
    delivery(req, room)
    empty = req(0, "GET", f"/teacher/classes/{room['id']}/students/{ids[2]}/reinforcement-evidence")
    assert empty["correct_rate"] is None and empty["platform_study_seconds"] is None and empty["diagnostic_only"]
    now = datetime.now(UTC).replace(tzinfo=None)
    with SessionLocal() as db:
        for point in (point_id, other_id):
            ex = Exercise(knowledge_point_id=point, type="choice", content='{"prompt":"选择正确遍历顺序"}', answer="A", analysis="解析")
            db.add(ex)
            db.flush()
            db.add(AnswerRecord(user_id=ids[2], exercise_id=ex.id, user_answer="B", is_correct=False, time_spent=40))
        db.add_all([StudyActivity(user_id=ids[2], page="practice", started_at=now-timedelta(seconds=120), ended_at=now-timedelta(seconds=60)),
                    StudyActivity(user_id=ids[2], page="courseware", started_at=now-timedelta(seconds=90), ended_at=now-timedelta(seconds=30))])
        db.commit()
    facts = req(0, "GET", f"/teacher/classes/{room['id']}/students/{ids[2]}/reinforcement-evidence")
    assert facts["answer_count"] == facts["mistake_count"] == 1
    assert facts["platform_study_seconds"] == 90 and facts["course_answer_seconds"] == 40
    assert facts["study_time_scope"] == "platform_total_not_course_specific"
    assert facts["mistakes"][0]["knowledge_point"] == "二叉树遍历"


def test_resources_and_generation_are_course_target_and_owner_scoped(support):
    req, ids, room, point_id, _, calls = support
    material = delivery(req, room, ids[2])
    assert req(2, "GET", "/teacher/students/me/course-resources")[0]["id"] == material["id"]
    assert not req(3, "GET", "/teacher/students/me/course-resources")
    req(1, "GET", f"/teacher/classes/{room['id']}/resource-catalog", status=403)
    req(3, "POST", f"/teacher/classes/{room['id']}/reinforcements", {"request_id": uuid4().hex, "student_user_id": ids[2], "delivery_ids": [material["id"]]}, status=403)
    req(0, "POST", f"/teacher/classes/{room['id']}/reinforcements", {"request_id": uuid4().hex, "student_user_id": ids[3], "delivery_ids": [material["id"]]}, status=403)
    with SessionLocal() as db:
        private = Resource(title="其他学生私密课件", content="禁止外发", type="courseware", knowledge_point_id=point_id, generated_for_user_id=ids[3], generation_status="generated")
        db.add(private)
        db.commit()
        rid = private.id
    req(0, "POST", f"/teacher/classes/{room['id']}/course-resources", {"request_id": uuid4().hex, "resource_id": rid}, status=403)
    assert calls["generate"] == 0


def test_failed_generation_never_publishes_and_replayed_request_does_not_call_model_twice(support, monkeypatch):
    req, ids, room, _, _, calls = support
    material = delivery(req, room)
    payload = {"request_id": uuid4().hex, "student_user_id": ids[2], "delivery_ids": [material["id"]], "question_count": 2}
    first = req(0, "POST", f"/teacher/classes/{room['id']}/reinforcements", payload)
    assert req(0, "POST", f"/teacher/classes/{room['id']}/reinforcements", payload)["id"] == first["id"]
    assert calls["generate"] == 1
    monkeypatch.setattr(course_support, "invoke_model", lambda _: ({"questions": []}, "test-provider"))
    failed = req(0, "POST", f"/teacher/classes/{room['id']}/reinforcements", {**payload, "request_id": uuid4().hex})
    assert failed["status"] == "failed"
    req(0, "POST", f"/teacher/reinforcements/{failed['id']}/publish", {"title": "不得误发"}, status=409)
    with SessionLocal() as db:
        assert db.query(Assignment).filter_by(class_id=room["id"]).count() == 0


def test_active_analysis_lease_blocks_duplicate_and_recovers_after_expiry(support, monkeypatch):
    import time
    req, ids, room, _, _, calls = support
    _, assignment_id = draft_and_publish(req, ids, room)
    original = reinforcement_feedback.analyze_attempt
    monkeypatch.setattr(reinforcement_feedback, "analyze_attempt", lambda _: None)
    req(2, "POST", f"/teacher/students/me/homework/{assignment_id}/submit", {"answers": ["B", "先根后左再右"]})
    monkeypatch.setattr(reinforcement_feedback, "analyze_attempt", original)
    with SessionLocal() as db:
        attempt = db.query(ReinforcementAttempt).join(ReinforcementDraft, ReinforcementDraft.id == ReinforcementAttempt.draft_id).filter(ReinforcementDraft.assignment_id == assignment_id).one()
        attempt.status = "analyzing"
        attempt.analysis_token = f"{int(time.time()):010d}:active"
        aid = attempt.id
        db.commit()
    original(aid)
    assert calls["feedback"] == 0
    with SessionLocal() as db:
        db.get(ReinforcementAttempt, aid).analysis_token = "0000000000:stale"
        db.commit()
    original(aid)
    assert calls["feedback"] == 1


def test_feedback_parser_preserves_quotes_in_analysis_and_requires_valid_xml(monkeypatch):
    from types import SimpleNamespace

    from services.agent_service.app.services.llm_factory import LLMFactory
    monkeypatch.setattr(LLMFactory, "build_chat_model", lambda *args, **kwargs: SimpleNamespace(bind=lambda **kwargs: None, model_name="test"))
    response = '<feedback><grades><grade question_index="1" score="20"><comment><![CDATA[将"根"的时机写错]]></comment></grade></grades><analysis><![CDATA[混淆"前序"与"中序"，比较符号a<b也应完整保存。]]></analysis><recommendations><item><![CDATA[复习"左-根-右"]]></item></recommendations></feedback>'
    monkeypatch.setattr(reinforcement_feedback, "traced_invoke", lambda *args, **kwargs: SimpleNamespace(content=response))
    value, _ = reinforcement_feedback.invoke_feedback({})
    assert value["grades"][0]["score"] == 20 and '"根"' in value["grades"][0]["comment"]
    assert "a<b" in value["analysis"]
    monkeypatch.setattr(reinforcement_feedback, "traced_invoke", lambda *args, **kwargs: SimpleNamespace(content="<feedback>truncated"))
    import xml.etree.ElementTree as ET
    with pytest.raises(ET.ParseError):
        reinforcement_feedback.invoke_feedback({})

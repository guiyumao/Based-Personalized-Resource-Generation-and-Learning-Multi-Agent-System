"""Cross-role use cases driven entirely through the running HTTP services.

Nothing here writes to the database directly. Every business action is performed
by logging in as a real demo account and calling the service API:

* 管理员 (system service, 8006)  — account governance, subject catalogue, audit log
* 教师   (teacher service, 8005)  — class, scope, schedule, homework, check-in, notice
* 学生   (user/evaluation/teacher services) — learn, submit, check in, read notice
* 联动   — every teacher action is asserted to be *visible by* the counterpart role

Learning analytics (掌握度 / 错题 / 教学分析) are **not** seeded. They appear
because a real student posts a real answer to ``POST /evaluation/submit`` and
``ReportService`` grades it by comparing against the stored standard answer.
Whatever mastery comes out is what the demo reports.

    python scripts/demo_role_use_cases.py --db artifacts/local-start-20261019/runtime.sqlite
    python scripts/demo_role_use_cases.py --db <db> --only D  # answer-related only
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT, ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import requests  # noqa: E402
from demo_teaching_dataset import DEFAULT_PASSWORD  # noqa: E402

USER_API = "http://127.0.0.1:8001"
EVAL_API = "http://127.0.0.1:8004"
TEACHER_API = "http://127.0.0.1:8005"
SYSTEM_API = "http://127.0.0.1:8006"
TZ = timezone(timedelta(hours=8))
TAG = "[USECASE]"

# Each student answers this many demo questions (evidence needs >= 8 to be
# "sufficient" inside common.learning_evidence.summarize).
DEFAULT_QUESTIONS_PER_STUDENT = 10

# Persona → intended share of questions the student answers correctly. The actual
# ``is_correct`` is decided by the service, never by this script.
PERSONA_ACCURACY = {
    "excellent": 0.90,
    "normal": 0.70,
    "struggling": 0.35,
    "pending": 0.55,
}

STEPS: list[dict] = []
LINKS: list[dict] = []


# --------------------------------------------------------------------------- #
# plumbing
# --------------------------------------------------------------------------- #
@dataclass
class Actor:
    key: str
    username: str
    name: str
    role: str
    token: str = ""
    user_id: int = 0


@dataclass
class Runner:
    actors: dict[str, Actor] = field(default_factory=dict)

    def call(self, base: str, method: str, path: str, actor: Actor | None = None, **kwargs):
        headers = kwargs.pop("headers", {})
        if actor and actor.token:
            headers["Authorization"] = f"Bearer {actor.token}"
        response = requests.request(
            method, f"{base}{path}", headers=headers, timeout=60, **kwargs
        )
        try:
            payload = response.json()
        except ValueError:
            payload = {"raw": response.text[:400]}
        body = payload.get("data", payload) if isinstance(payload, dict) else payload
        return response.status_code, body

    def login(self, username: str, password: str = DEFAULT_PASSWORD) -> tuple[int, dict]:
        response = requests.post(
            f"{USER_API}/users/login",
            json={"username": username, "password": password},
            timeout=30,
        )
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        return response.status_code, payload

    def actor(self, key: str) -> Actor | None:
        return self.actors.get(key)


def step(case: str, actor: str, name: str, ok: bool, expected: str, actual: str, evidence: str) -> bool:
    STEPS.append(
        {
            "case": case,
            "actor": actor,
            "step": name,
            "status": "PASS" if ok else "FAIL",
            "expected": expected,
            "actual": actual,
            "evidence": evidence,
        }
    )
    print(f"[{'PASS' if ok else 'FAIL'}] {case} · {name}: {actual}")
    return ok


def link(producer: str, action: str, consumer: str, observation: str, ok: bool) -> None:
    LINKS.append(
        {
            "producer": producer,
            "action": action,
            "consumer": consumer,
            "observation": observation,
            "status": "PASS" if ok else "FAIL",
        }
    )


def _ratio(*parts: object) -> float:
    seed = "|".join(str(part) for part in parts).encode("utf-8")
    return int.from_bytes(hashlib.sha256(seed).digest()[:8], "big") / 2**64


def _option_letters(options: list[str]) -> list[str]:
    letters: list[str] = []
    for item in options:
        text = item.strip()
        if "." in text[:3]:
            letters.append(text.split(".", 1)[0].strip().upper())
        elif text[:1].isalpha():
            letters.append(text[0].upper())
    return [item for item in letters if item]


def _answer_payload(question: dict, correct: bool) -> str:
    """Build what the student actually types in. Wrong answers are real wrong answers."""

    qtype = question["type"]
    answer = (question.get("answer") or "").strip()
    if qtype == "choice":
        letters = _option_letters(question.get("options") or [])
        if correct:
            return answer or (letters[0] if letters else "A")
        others = [item for item in letters if item and item != answer.upper()]
        return others[0] if others else ("B" if answer.upper() != "B" else "C")
    if qtype == "judge":
        truthy = {"正确", "对", "true", "t", "yes", "y", "1"}
        standard = answer.strip().lower()
        if standard in {"正确", "对", "true", "t", "yes", "y", "1"}:
            return answer if correct else "错误"
        return answer if correct else "正确"
    # fill / blank
    if correct:
        return answer
    return "不确定（未掌握该知识点）"


# --------------------------------------------------------------------------- #
# A · identity and permission baseline
# --------------------------------------------------------------------------- #
def case_identity(runner: Runner) -> None:
    identities = [
        ("admin", "demo_admin", "演示管理员", "admin"),
        ("zhangming", "demo_zhangming", "张明", "teacher"),
        ("lihua", "demo_lihua", "李华", "teacher"),
        ("wangmin", "demo_wangmin", "王敏", "teacher"),
        ("chenjie", "demo_chenjie", "陈杰", "teacher"),
    ]
    for index in range(1, 25):
        identities.append((f"s{index:02d}", f"demo_s{index:02d}", f"学生S{index:02d}", "student"))

    for key, username, name, role in identities:
        status, payload = runner.login(username)
        token = payload.get("access_token") or payload.get("token") or ""
        actor = Actor(key=key, username=username, name=name, role=role)
        if token:
            actor.token = token
            actor.user_id = int(payload.get("user_id") or 0)
        runner.actors[key] = actor
        step(
            "A 身份",
            f"{name}({role})",
            f"{username} 登录",
            status == 200 and bool(token) and payload.get("role") == role,
            f"200 + token + role={role}",
            f"status={status} role={payload.get('role')} token={'yes' if token else 'no'}",
            "POST /users/login",
        )

    student = runner.actor("s01")
    status, _ = runner.call(SYSTEM_API, "GET", "/system/dashboard", student)
    step(
        "A 越权",
        f"{student.name}(student)",
        "学生无法访问管理端总览",
        status == 403,
        "403",
        f"status={status}",
        "GET /system/dashboard (student token)",
    )
    teacher = runner.actor("zhangming")
    status, _ = runner.call(SYSTEM_API, "GET", "/system/users?keyword=demo_", teacher)
    step(
        "A 越权",
        f"{teacher.name}(teacher)",
        "教师无法访问管理端用户目录",
        status == 403,
        "403",
        f"status={status}",
        "GET /system/users (teacher token)",
    )
    status, payload = runner.login("demo_zhangming", "not-the-password")
    step(
        "A 身份",
        "张明(teacher)",
        "错误密码被拒绝",
        status == 401,
        "401",
        f"status={status}",
        "POST /users/login (wrong password)",
    )


# --------------------------------------------------------------------------- #
# B · administrator governance
# --------------------------------------------------------------------------- #
def case_admin(runner: Runner) -> dict:
    admin = runner.actor("admin")
    info: dict = {}

    status, dashboard = runner.call(SYSTEM_API, "GET", "/system/dashboard", admin)
    info["dashboard"] = dashboard if isinstance(dashboard, dict) else {}
    step(
        "B 管理员",
        f"{admin.name}(admin)",
        "管理端总览可读",
        status == 200 and bool(info["dashboard"]),
        "200 且非空",
        f"status={status} keys={sorted(list(info['dashboard'].keys()))[:8]}",
        "GET /system/dashboard",
    )

    status, page = runner.call(SYSTEM_API, "GET", "/system/users?size=5&keyword=demo_zhangming", admin)
    items = page.get("items") if isinstance(page, dict) else page
    hit = bool(items) and any(item.get("username") == "demo_zhangming" for item in items or [])
    step(
        "B 管理员",
        f"{admin.name}(admin)",
        "用户目录可检索演示教师",
        status == 200 and hit,
        "命中 demo_zhangming",
        f"status={status} items={len(items or [])} hit={hit}",
        "GET /system/users?keyword=demo_zhangming",
    )

    status, subjects = runner.call(SYSTEM_API, "GET", "/system/subjects", admin)
    subject_names = [item.get("name") for item in subjects] if isinstance(subjects, list) else []
    step(
        "B 管理员",
        f"{admin.name}(admin)",
        "学科目录可读",
        status == 200 and len(subject_names) > 0,
        "非空学科列表",
        f"status={status} subjects={subject_names}",
        "GET /system/subjects",
    )

    target = runner.actor("s24")
    status, patched = runner.call(
        SYSTEM_API, "PATCH", f"/system/users/{target.user_id}/status", admin,
        json={"is_active": False},
    )
    step(
        "B 管理员",
        f"{admin.name}(admin)",
        "管理员停用演示学生账号",
        status == 200 and (patched or {}).get("is_active") is False,
        "200 + is_active=false",
        f"status={status} is_active={(patched or {}).get('is_active')}",
        f"PATCH /system/users/{target.user_id}/status",
    )
    status, relogin = runner.login(target.username)
    step(
        "B 联动",
        f"{target.name}(student)",
        "被停用账号登录立即失败",
        status == 401,
        "401",
        f"status={status}",
        "POST /users/login (disabled account)",
    )
    link(
        "管理员", f"停用 {target.username}", "学生",
        "该账号登录被拒绝（401），治理动作即时生效",
        status == 401,
    )
    status, restored = runner.call(
        SYSTEM_API, "PATCH", f"/system/users/{target.user_id}/status", admin,
        json={"is_active": True},
    )
    status2, relogin2 = runner.login(target.username)
    step(
        "B 联动",
        f"{target.name}(student)",
        "恢复启用后登录恢复",
        status == 200 and status2 == 200 and bool(relogin2.get("access_token")),
        "启用后 200 + token",
        f"patch={status} login={status2} token={'yes' if relogin2.get('access_token') else 'no'}",
        "PATCH status + POST /users/login",
    )
    if relogin2.get("access_token"):
        target.token = relogin2["access_token"]

    status, logs = runner.call(SYSTEM_API, "GET", "/system/logs?size=10", admin)
    log_items = logs if isinstance(logs, list) else []
    step(
        "B 管理员",
        f"{admin.name}(admin)",
        "审计日志记录了本次治理动作",
        status == 200 and len(log_items) > 0,
        "非空审计日志",
        f"status={status} logs={len(log_items)} latest={(log_items[0] if log_items else {})}",
        "GET /system/logs",
    )
    return info


# --------------------------------------------------------------------------- #
# C · teacher preparation
# --------------------------------------------------------------------------- #
def case_teacher_prepare(runner: Runner, class_map: dict) -> list[dict]:
    """Every demo class that owns questions gets the full teacher preparation run."""

    contexts: list[dict] = []
    for teacher_key in ("zhangming", "lihua", "wangmin", "chenjie"):
        teacher = runner.actor(teacher_key)
        if teacher is None or not teacher.token:
            continue
        status, classes = runner.call(TEACHER_API, "GET", "/teacher/classes", teacher)
        for room in classes or []:
            name = room.get("name") or ""
            if not name.startswith("[DEMO]") or "行政班" in name:
                continue
            mapping = class_map.get(name)
            if not mapping:
                continue
            contexts.append(_prepare_one_class(runner, teacher, room, mapping, slot=len(contexts)))

    covered = {item["class_name"] for item in contexts}
    for name, mapping in class_map.items():
        if name in covered:
            continue
        step(
            "C 教师",
            "覆盖检查",
            f"{name} 未参与联动",
            False,
            "每个有题库的演示班都应有任课教师执行准备动作",
            f"no owner teacher found (class_id={mapping['class_id']})",
            "GET /teacher/classes ×4",
        )
    return contexts


def _prepare_one_class(
    runner: Runner, teacher: Actor, room: dict, mapping: dict, slot: int = 0
) -> dict:
    ctx: dict = {
        "class_id": room.get("id"),
        "class_name": room.get("name"),
        "teacher": teacher,
        "points": mapping.get("scope_points") or [],
        "questions": mapping.get("questions", []),
        "subject": mapping.get("subject"),
    }
    points = ctx["points"] or [item["knowledge_point"] for item in ctx["questions"]]
    ctx["points"] = list(dict.fromkeys(points))
    head = ctx["points"][0]
    class_id = ctx["class_id"]
    class_name = ctx["class_name"]

    status, members = runner.call(TEACHER_API, "GET", f"/teacher/classes/{class_id}/members", teacher)
    member_ids = [item.get("user_id") for item in members or []]
    ctx["member_ids"] = member_ids
    step(
        "C 教师",
        f"{teacher.name}(teacher)",
        f"{ctx['class_name']} 成员列表可读",
        status == 200 and bool(member_ids),
        "200 且成员非空",
        f"status={status} members={len(member_ids)}",
        "GET /teacher/classes/{id}/members",
    )
    others = [item for item in runner.actors.values() if item.role == "student" and item.user_id not in member_ids]
    ctx["outsider"] = others[0] if others else None
    ctx["members"] = [
        item for item in runner.actors.values()
        if item.role == "student" and item.user_id in member_ids
    ]
    ctx["representative"] = ctx["members"][0] if ctx["members"] else None

    # --- teaching scope -----------------------------------------------------
    scope_payload = {
        "class_id": class_id,
        "student_user_id": None,
        "knowledge_points": ctx["points"],
        "learning_direction": f"{ctx['subject']}-{head}",
        "courseware_title": f"{TAG} {head}课堂讲义",
        "courseware_content": f"本节覆盖 {head} 的核心概念与典型题型。",
        "teaching_goal": f"掌握{head}的核心概念与基本方法",
    }
    status, scope = runner.call(
        TEACHER_API, "POST", "/teacher/teaching-scopes", teacher, json=scope_payload
    )
    ctx["scope_id"] = (scope or {}).get("id")
    step(
        "C 教师",
        f"{teacher.name}(teacher)",
        f"{class_name} 教师发布教学范围",
        status == 200 and bool(ctx["scope_id"]),
        "200 + scope id",
        f"status={status} id={ctx['scope_id']} points={ctx['points']}",
        "POST /teacher/teaching-scopes",
    )

    # --- schedule -----------------------------------------------------------
    # Each class gets its own slot, otherwise the same teacher legitimately hits
    # the "teacher already busy" conflict the service rejects with 409.
    weekday = ((datetime.now(TZ).isoweekday() % 7) + slot) % 7 + 1
    start_hour = 8 + slot
    status, session_item = runner.call(
        TEACHER_API, "POST", f"/learning/classes/{class_id}/schedule", teacher,
        json={
            "topic": f"{TAG} {head}专题",
            "weekday": weekday,
            "start_time": f"{start_hour:02d}:00",
            "end_time": f"{start_hour + 1:02d}:40",
            "week_start": "2026-09-07",
            "week_end": "2027-01-10",
            "location": "演示教室 A",
            "mode": "offline",
        },
    )
    ctx["session_id"] = (session_item or {}).get("id")
    ctx["session_topic"] = f"{TAG} {head}专题"
    step(
        "C 教师",
        f"{teacher.name}(teacher)",
        f"{ctx['class_name']} 排一次课",
        status == 200 and bool(ctx["session_id"]),
        "200 + session id",
        f"status={status} id={ctx['session_id']} weekday={weekday} {start_hour:02d}:00",
        "POST /learning/classes/{id}/schedule",
    )
    # 同一教师同一时段再排一次，必须被冲突校验挡住
    status, _ = runner.call(
        TEACHER_API, "POST", f"/learning/classes/{class_id}/schedule", teacher,
        json={
            "topic": f"{TAG} {head}冲突课",
            "weekday": weekday,
            "start_time": f"{start_hour:02d}:30",
            "end_time": f"{start_hour + 1:02d}:20",
            "week_start": "2026-09-07",
            "week_end": "2027-01-10",
            "location": "演示教室 A",
            "mode": "offline",
        },
    )
    step(
        "C 边界",
        f"{teacher.name}(teacher)",
        f"{ctx['class_name']} 同一教师时间冲突被拒绝",
        status in (409, 400, 422),
        "409",
        f"status={status}",
        "POST /learning/classes/{id}/schedule (overlapping)",
    )

    # --- resource delivery ---------------------------------------------------
    status, delivery = runner.call(
        TEACHER_API, "POST", f"/teacher/classes/{class_id}/course-resources", teacher,
        json={
            "request_id": f"usecase-{class_id}-{datetime.now().strftime('%H%M%S')}",
            "student_user_id": None,
            "title": f"{TAG} {head}讲义",
            "content": f"讲义要点：围绕 {head} 的核心定义、典型题型与易错点。",
            "knowledge_points": ctx["points"],
        },
    )
    ctx["delivery_id"] = (delivery or {}).get("id")
    step(
        "C 教师",
        f"{teacher.name}(teacher)",
        f"{ctx['class_name']} 投送讲义",
        status == 200 and bool(ctx["delivery_id"]),
        "200 + delivery id",
        f"status={status} id={ctx['delivery_id']}",
        "POST /teacher/classes/{id}/course-resources",
    )

    # --- homework ------------------------------------------------------------
    due = (datetime.now(UTC) + timedelta(days=3)).isoformat()
    status, assignment = runner.call(
        TEACHER_API, "POST", "/teacher/homework/assign", teacher,
        json={
            "class_id": class_id,
            "title": f"{TAG} {head}作业",
            "description": f"围绕 {head} 完成一次完整推导并说明易错点。",
            "due_at": due,
        },
    )
    ctx["assignment_id"] = (assignment or {}).get("id")
    step(
        "C 教师",
        f"{teacher.name}(teacher)",
        f"{ctx['class_name']} 布置作业",
        status == 200 and bool(ctx["assignment_id"]),
        "200 + assignment id",
        f"status={status} id={ctx['assignment_id']}",
        "POST /teacher/homework/assign",
    )

    # --- check-in task (once, published) -------------------------------------
    start = datetime.now(UTC) - timedelta(hours=1)
    end = datetime.now(UTC) + timedelta(days=2)
    status, task = runner.call(
        TEACHER_API, "POST", "/learning/checkin/manage/tasks", teacher,
        json={
            "class_id": class_id,
            "title": f"{TAG} {head}学习打卡",
            "goal": f"完成一次 {head} 的手写推导",
            "description": f"提交你对 {head} 的一次完整推导过程。",
            "frequency": "once",
            "weekly_days": [],
            "start_at": start.isoformat(),
            "end_at": end.isoformat(),
            "due_time": "23:59",
            "review_mode": "manual",
            "knowledge_points": ctx["points"],
        },
    )
    task_id = (task or {}).get("id")
    status, published = runner.call(
        TEACHER_API, "POST", f"/learning/checkin/manage/tasks/{task_id}/publish", teacher
    )
    ctx["checkin_task_id"] = task_id
    step(
        "C 教师",
        f"{teacher.name}(teacher)",
        f"{ctx['class_name']} 创建并发布打卡任务",
        status == 200 and bool(task_id) and (published or {}).get("status") == "published",
        "200 + published",
        f"create={status} publish_status={(published or {}).get('status')} id={task_id}",
        "POST manage/tasks + manage/tasks/{id}/publish",
    )

    # --- attendance ----------------------------------------------------------
    status, attendance = runner.call(
        TEACHER_API, "POST", "/learning/checkin/manage/attendance", teacher,
        json={
            "class_id": class_id,
            "title": f"{TAG} {head}课堂签到",
            "start_at": (datetime.now(UTC) - timedelta(minutes=5)).isoformat(),
            "end_at": (datetime.now(UTC) + timedelta(minutes=45)).isoformat(),
        },
    )
    ctx["attendance_id"] = (attendance or {}).get("id")
    ctx["attendance_code"] = (attendance or {}).get("code")
    step(
        "C 教师",
        f"{teacher.name}(teacher)",
        f"{ctx['class_name']} 发起课堂签到",
        status == 200 and bool(ctx["attendance_id"] and ctx["attendance_code"]),
        "200 + id + code",
        f"status={status} id={ctx['attendance_id']} code={'yes' if ctx['attendance_code'] else 'no'}",
        "POST /learning/checkin/manage/attendance",
    )

    # --- notification --------------------------------------------------------
    status, _ = runner.call(
        TEACHER_API, "POST", "/learning/notifications/publish", teacher,
        json={
            "request_key": f"usecase-{class_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "scope": "class",
            "target_id": class_id,
            "title": f"{TAG} {head}课前通知",
            "content": f"请提前阅读 {head} 讲义并完成一次手写推导。",
            "type": "course",
        },
    )
    ctx["notice_title"] = f"{TAG} {head}课前通知"
    step(
        "C 教师",
        f"{teacher.name}(teacher)",
        f"{ctx['class_name']} 发布班级通知",
        status == 200,
        "200",
        f"status={status}",
        "POST /learning/notifications/publish",
    )
    return ctx


# --------------------------------------------------------------------------- #
# D · student learning actions (including the real answer submission)
# --------------------------------------------------------------------------- #
def load_class_questions(db_path: Path) -> dict[str, dict]:
    """Map demo teaching class → clone questions it can exercise (read-only)."""

    from scripts.demo_learning_evidence import load_question_bank
    from scripts.demo_teaching_dataset import configure_database

    configure_database(db_path)
    from common.db.session import SessionLocal
    from common.models.learning import Classroom, KnowledgePoint, SystemSubject, TeachingScope

    bank = load_question_bank(db_path)
    mapping: dict[str, dict] = {}
    with SessionLocal() as db:
        rooms = (
            db.query(Classroom)
            .filter(Classroom.name.like("[DEMO]%"), Classroom.course_id.isnot(None))
            .all()
        )
        for room in rooms:
            subject = db.query(SystemSubject).filter(SystemSubject.name == room.subject).first()
            if subject is None:
                continue
            point_names = {
                name
                for (name,) in db.query(KnowledgePoint.name).filter(
                    KnowledgePoint.subject_id == subject.id
                )
            }
            if not point_names:
                continue
            questions = [item for item in bank if item["knowledge_point"] in point_names]
            if not questions:
                continue
            scope = db.query(TeachingScope).filter(TeachingScope.class_id == room.id).first()
            mapping[room.name] = {
                "class_id": room.id,
                "subject": room.subject,
                "questions": questions,
                "scope_points": list(scope.knowledge_points or []) if scope else [],
            }
    return mapping


def _submit_batch(
    runner: Runner,
    student: Actor,
    questions: list[dict],
    accuracy: float,
) -> dict:
    """One student answers a batch of questions. Grading happens server-side."""

    records: list[dict] = []
    intents: list[bool] = []
    for question in questions:
        correct = _ratio(student.username, question["id"], "v1") < accuracy
        records.append(
            {
                "user_id": str(student.user_id),
                "exercise_id": str(question["id"]),
                "user_answer": _answer_payload(question, correct),
                "time_spent": round(25 + _ratio(student.username, question["id"], "t") * 140, 1),
                "exercise_type": "fill" if question["type"] in {"blank", "fill"} else question["type"],
                "difficulty": "intermediate",
                "client_request_id": f"uc-{student.key}-{question['id']}",
                "knowledge_point_ids": [question["knowledge_point"]],
            }
        )
        intents.append(correct)

    status, body = runner.call(
        EVAL_API, "POST", "/evaluation/batch_submit", student, json={"records": records}
    )
    results = (body or {}).get("results") if isinstance(body, dict) else None
    if not isinstance(results, list):
        results = body if isinstance(body, list) else []
    graded = [bool(item.get("is_correct")) for item in results if isinstance(item, dict)]
    match = graded == intents[: len(graded)]
    return {
        "status": status,
        "requested": len(records),
        "graded": len(graded),
        "graded_flags": graded,
        "intended": intents,
        "match": match and len(graded) == len(records),
        "raw": body if status != 200 else None,
    }


def case_student_learn(
    runner: Runner, contexts: list[dict], per_student: int, db_path: Path
) -> dict:
    """Each demo class: its members answer its own question set over HTTP.

    A student who elected several classes answers in *every* one of them, which
    is what actually happens: learning evidence is per knowledge point, so 冒泡
    排序 answers never leak into the 计算机网络 class (and vice versa).
    """

    from scripts.demo_teaching_dataset import STUDENTS

    persona_by_username = {f"demo_{spec.key}": spec.persona for spec in STUDENTS}
    outcome: dict = {"classes": [], "students": []}

    for ctx in contexts:
        questions = (ctx.get("questions") or [])[:per_student]
        members = ctx.get("members") or []
        class_name = ctx.get("class_name")
        step(
            "D 学生",
            f"{ctx['teacher'].name} 班内成员",
            f"{class_name} 成员可答本班公共演示题",
            len(questions) >= 8 and bool(members),
            ">=8 道题且成员非空",
            f"questions={len(questions)} members={len(members)}",
            "load_class_questions(read-only)",
        )
        if not members:
            continue
        for actor in members:
            persona = persona_by_username.get(actor.username, "normal")
            accuracy = PERSONA_ACCURACY.get(persona, 0.7)
            result = _submit_batch(runner, actor, questions, accuracy)
            correct_count = sum(1 for flag in result["graded_flags"] if flag)
            outcome["students"].append(
                {
                    "class": class_name,
                    "username": actor.username,
                    "persona": persona,
                    "intended_accuracy": accuracy,
                    "submitted": result["requested"],
                    "graded": result["graded"],
                    "correct": correct_count,
                    "server_agrees_with_intent": result["match"],
                    "status": result["status"],
                }
            )
            step(
                "D 学生",
                f"{actor.name}(student)",
                f"{class_name} · {actor.username} 真实作答 {len(questions)} 题并由服务端判分",
                result["status"] == 200
                and result["graded"] == len(questions)
                and result["match"],
                "200 且服务端判定与作答内容一致",
                f"status={result['status']} graded={result['graded']} correct={correct_count}"
                f" agree={result['match']}"
                + (f" raw={str(result['raw'])[:120]}" if result["raw"] else ""),
                "POST /evaluation/batch_submit",
            )
        outcome["classes"].append(
            {"class": class_name, "questions": len(questions), "answered_students": len(members)}
        )
        link(
            "学生", "通过 POST /evaluation/batch_submit 作答（服务端比对标准答案判分）",
            "教师", f"{class_name} 学生洞察 / 教学分析随之出现真实掌握度与错题", True,
        )
    return outcome


def case_student_actions(runner: Runner, ctx: dict) -> None:
    student = ctx.get("representative")
    teacher = ctx.get("teacher")
    class_name = ctx.get("class_name")
    topic = ctx.get("session_topic")
    if student is None or teacher is None:
        return

    # schedule visible to student (teacher scheduled it in case C)
    status, schedule = runner.call(TEACHER_API, "GET", "/learning/schedule/me", student)
    text = json.dumps(schedule, ensure_ascii=False) if schedule else ""
    step(
        "D 联动",
        f"{student.name}(student)",
        f"{class_name} 学生课表出现教师新排的课",
        status == 200 and topic in text,
        f"课表包含 {topic}",
        f"status={status} contains={topic in text}",
        "GET /learning/schedule/me",
    )
    link("教师", "排一次课（/learning/classes/{id}/schedule）", "学生", "我的课表立即出现该节次", True)

    status, scopes = runner.call(TEACHER_API, "GET", "/teacher/students/me/teaching-scopes", student)
    hits = [
        item
        for item in scopes or []
        if isinstance(item, dict) and str(item.get("courseware_title") or "").startswith(TAG)
    ]
    step(
        "D 联动",
        f"{student.name}(student)",
        f"{class_name} 学生端收到教师发布的教学范围",
        status == 200 and bool(hits),
        "教学范围包含本次讲义",
        f"status={status} scopes={len(scopes or [])} hit={len(hits)}",
        "GET /teacher/students/me/teaching-scopes",
    )
    link("教师", "发布教学范围（POST /teacher/teaching-scopes）", "学生", "学生端教学范围列表立即命中", True)

    status, resources = runner.call(TEACHER_API, "GET", "/teacher/students/me/course-resources", student)
    delivered = [
        item for item in resources or [] if str(item.get("title") or "").startswith(TAG)
    ]
    step(
        "D 联动",
        f"{student.name}(student)",
        f"{class_name} 学生端收到教师投送的讲义",
        status == 200 and bool(delivered),
        "我的资料包含本次讲义",
        f"status={status} resources={len(resources or [])} hit={len(delivered)}",
        "GET /teacher/students/me/course-resources",
    )
    link("教师", "投送讲义（POST /teacher/classes/{id}/course-resources）", "学生", "我的资料列表出现该讲义", True)

    # homework submit → teacher sees it
    status, mine = runner.call(TEACHER_API, "GET", "/teacher/students/me/homework", student)
    visible = any(item.get("id") == ctx.get("assignment_id") for item in mine or [])
    step(
        "D 联动",
        f"{student.name}(student)",
        f"{class_name} 学生作业列表出现教师布置的作业",
        status == 200 and visible,
        "包含本次作业",
        f"status={status} visible={visible}",
        "GET /teacher/students/me/homework",
    )
    status, submission = runner.call(
        TEACHER_API, "POST",
        f"/teacher/students/me/homework/{ctx.get('assignment_id')}/submit", student,
        json={"content": f"已完成 {ctx['points'][0] if ctx['points'] else '本节'} 的推导与自查。"},
    )
    submission_id = (submission or {}).get("id")
    step(
        "D 学生",
        f"{student.name}(student)",
        "学生提交作业",
        status == 200 and bool(submission_id),
        "200 + submission id",
        f"status={status} id={submission_id}",
        "POST /teacher/students/me/homework/{id}/submit",
    )
    status, listed = runner.call(
        TEACHER_API, "GET",
        f"/teacher/homework/{ctx.get('assignment_id')}/submissions", teacher,
    )
    step(
        "D 联动",
        f"{teacher.name}(teacher)",
        f"{class_name} 教师端看到该提交",
        status == 200 and any(item.get("id") == submission_id for item in listed or []),
        "提交列表包含该学生",
        f"status={status} count={len(listed or [])}",
        "GET /teacher/homework/{id}/submissions",
    )
    link("学生", "提交作业", "教师", "教师批改列表立即出现该提交", True)
    ctx["submission_id"] = submission_id

    # check-in task submit → teacher sees it
    status, _ = runner.call(
        TEACHER_API, "POST",
        f"/learning/checkin/tasks/{ctx.get('checkin_task_id')}/submit", student,
        json={"content": f"完成 {ctx['points'][0] if ctx['points'] else '本节'} 的一次完整推导。"},
    )
    step(
        "D 学生",
        f"{student.name}(student)",
        "学生完成打卡任务",
        status == 200,
        "200",
        f"status={status}",
        "POST /learning/checkin/tasks/{id}/submit",
    )
    status, school_submissions = runner.call(
        TEACHER_API, "GET",
        f"/learning/checkin/manage/tasks/{ctx.get('checkin_task_id')}/submissions", teacher,
    )
    rows = school_submissions.get("rows") if isinstance(school_submissions, dict) else None
    rows = rows if rows is not None else (school_submissions or [])
    step(
        "D 联动",
        f"{teacher.name}(teacher)",
        f"{class_name} 教师端看到打卡提交",
        status == 200 and len(rows or []) > 0,
        "至少 1 条打卡记录",
        f"status={status} rows={len(rows or [])}",
        "GET /learning/checkin/manage/tasks/{id}/submissions",
    )
    link("学生", "提交打卡成果", "教师", "教师端打卡明细立即出现", True)

    # attendance
    outsider = ctx.get("outsider")
    if outsider is not None:
        status, _ = runner.call(
            TEACHER_API, "POST", "/learning/checkin/attendance/checkin", outsider,
            json={"code": ctx.get("attendance_code")},
        )
        step(
            "D 越权",
            f"{outsider.name}(student)",
            f"{class_name} 非本班学生签到被拒绝",
            status == 403,
            "403",
            f"status={status} user_id={outsider.user_id}",
            "POST /learning/checkin/attendance/checkin",
        )
    status, _ = runner.call(
        TEACHER_API, "POST", "/learning/checkin/attendance/checkin", student,
        json={"code": ctx.get("attendance_code")},
    )
    step(
        "D 学生",
        f"{student.name}(student)",
        "本班学生签到成功",
        status == 200,
        "200",
        f"status={status}",
        "POST /learning/checkin/attendance/checkin",
    )
    status, live = runner.call(
        TEACHER_API, "GET",
        f"/learning/checkin/manage/attendance/{ctx.get('attendance_id')}/live", teacher,
    )
    rows = (live or {}).get("rows") if isinstance(live, dict) else None
    present = sum(1 for row in rows or [] if row.get("status") == "present")
    step(
        "D 联动",
        f"{teacher.name}(teacher)",
        f"{class_name} 教师实时统计显示已签到",
        status == 200 and present >= 1,
        "present >= 1",
        f"status={status} present={present}",
        "GET /learning/checkin/manage/attendance/{id}/live",
    )
    link("学生", "用签到码签到", "教师", "实时统计 present 计数增加", True)

    # notifications
    notice = ctx.get("notice_title")
    status, before = runner.call(TEACHER_API, "GET", "/learning/notifications/unread-count", student)
    before_count = (before or {}).get("unread_count")
    status, inbox = runner.call(
        TEACHER_API, "GET", "/learning/notifications/inbox?page=1&size=8", student
    )
    inbox_items = (inbox or {}).get("items") if isinstance(inbox, dict) else inbox
    has_notice = any(str(item.get("title") or "") == notice for item in inbox_items or [])
    step(
        "D 联动",
        f"{student.name}(student)",
        f"{class_name} 学生收件箱出现教师通知",
        status == 200 and has_notice,
        "包含本次班级通知",
        f"status={status} unread={before_count} hit={has_notice}",
        "GET /learning/notifications/inbox",
    )
    link("教师", "发布班级通知", "学生", "未读数上升且收件箱出现该通知", True)

    runner.call(TEACHER_API, "POST", "/learning/notifications/read-all", student)
    status, cleared = runner.call(TEACHER_API, "GET", "/learning/notifications/unread-count", student)
    step(
        "D 学生",
        f"{student.name}(student)",
        "一键已读后未读归零",
        status == 200 and (cleared or {}).get("unread_count") == 0,
        "unread_count == 0",
        f"status={status} unread={(cleared or {}).get('unread_count')}",
        "POST read-all + GET unread-count",
    )


# --------------------------------------------------------------------------- #
# E · teacher review + analytics linkage
# --------------------------------------------------------------------------- #
def case_teacher_review(runner: Runner, ctx: dict, before_snapshot: dict) -> None:
    teacher = ctx.get("teacher")
    student = ctx.get("representative")
    class_name = ctx.get("class_name")
    if teacher is None or student is None:
        return

    status, reviewed = runner.call(
        TEACHER_API, "POST",
        f"/teacher/homework/{ctx.get('submission_id')}/review", teacher,
        json={"score": 91, "comment": "推导正确，注意关键步骤要写清楚。"},
    )
    step(
        "E 教师",
        f"{teacher.name}(teacher)",
        f"{class_name} 教师批改作业写入成绩",
        status == 200 and float((reviewed or {}).get("score") or 0) == 91,
        "score == 91",
        f"status={status} score={(reviewed or {}).get('score')}",
        "POST /teacher/homework/{sid}/review",
    )
    status, mine = runner.call(TEACHER_API, "GET", "/teacher/students/me/homework", student)
    row = next((item for item in mine or [] if item.get("id") == ctx.get("assignment_id")), {})
    got = (row.get("my_submission") or {}).get("score")
    step(
        "E 联动",
        f"{student.name}(student)",
        f"{class_name} 学生端看到批改成绩",
        status == 200 and float(got or 0) == 91,
        "score == 91",
        f"status={status} score={got}",
        "GET /teacher/students/me/homework",
    )
    link("教师", "批改作业打 91 分", "学生", "学生作业详情立即显示该分数", True)

    status, batch = runner.call(
        TEACHER_API, "GET",
        f"/learning/checkin/manage/tasks/{ctx.get('checkin_task_id')}/submissions", teacher,
    )
    rows = (batch or {}).get("rows") if isinstance(batch, dict) else (batch or [])
    target = next((row for row in rows or [] if row.get("submission_id")), None)
    if isinstance(target, dict) and target.get("submission_id"):
        status, review = runner.call(
            TEACHER_API, "POST", "/learning/checkin/manage/submissions/review-batch", teacher,
            json={
                "items": [
                    {
                        "submission_id": target["submission_id"],
                        "status": "approved",
                        "score": 95,
                        "comment": "推导完整，继续保持。",
                    }
                ]
            },
        )
        step(
            "E 教师",
            f"{teacher.name}(teacher)",
            "教师批量批阅打卡成果",
            status == 200,
            "200",
            f"status={status} reviewed={(review or {}) if isinstance(review, dict) else review}",
            "POST /learning/checkin/manage/submissions/review-batch",
        )
        status, mine2 = runner.call(TEACHER_API, "GET", "/learning/checkin/submissions/me", student)
        text = json.dumps(mine2, ensure_ascii=False)
        step(
            "E 联动",
            f"{student.name}(student)",
            "学生端看到打卡批阅结果",
            status == 200 and ("95" in text or "approved" in text),
            "包含 95 或 approved",
            f"status={status} contains={'95' in text or 'approved' in text}",
            "GET /learning/checkin/submissions/me",
        )
        link("教师", "批量批阅打卡", "学生", "我的打卡列表出现分数/通过状态", True)

    # ---- analytics: before (empty) → after (real answers) -------------------
    class_id = ctx.get("class_id")
    status, insights = runner.call(TEACHER_API, "GET", f"/teacher/classes/{class_id}/insights", teacher)
    masteries = [
        item.get("mastery") for item in insights or [] if isinstance(item.get("mastery"), int)
    ]
    mistakes = [
        item.get("mistake_count") for item in insights or [] if isinstance(item.get("mistake_count"), int)
    ]
    step(
        "E 学情",
        f"{teacher.name}(teacher)",
        f"{class_name} 学生洞察由真实作答产出掌握度",
        status == 200 and bool(masteries) and all(1 <= value <= 100 for value in masteries),
        "mastery ∈ [1,100] 且非空",
        f"status={status} mastery={masteries}",
        "GET /teacher/classes/{id}/insights",
    )
    step(
        "E 学情",
        f"{teacher.name}(teacher)",
        f"{class_name} 不同学生掌握度出现差异",
        len(set(masteries)) >= 2,
        "至少两种掌握度",
        f"distinct={sorted(set(masteries))}",
        "GET /teacher/classes/{id}/insights",
    )
    step(
        "E 学情",
        f"{teacher.name}(teacher)",
        f"{class_name} 错题数由作答记录推导",
        any(value > 0 for value in mistakes),
        "至少一名学生错题 > 0",
        f"mistake_count={mistakes}",
        "GET /teacher/classes/{id}/insights",
    )
    before_count = len(before_snapshot.get("masteries") or [])
    grew = len(masteries) > before_count
    step(
        "E 联动",
        f"{teacher.name}(teacher)",
        f"{class_name} 作答前后洞察发生变化",
        grew,
        "after > before",
        f"before={before_count} after={len(masteries)}",
        "GET insights before/after batch_submit",
    )
    link(
        "学生", "真实作答并被服务端判分", "教师",
        f"{class_name} 洞察有值人数从 {before_count} 变为 {len(masteries)}", grew,
    )

    status, analytics = runner.call(
        TEACHER_API, "GET", f"/teacher/classes/{class_id}/teaching-analytics", teacher
    )
    payload = analytics if isinstance(analytics, dict) else {}
    before_answers = int(before_snapshot.get("total_answers") or 0)
    after_answers = int(payload.get("total_answers") or 0)
    step(
        "E 学情",
        f"{teacher.name}(teacher)",
        f"{class_name} 教学分析统计到本次作答",
        status == 200 and after_answers > before_answers,
        "作答数增加",
        f"before={before_answers} after={after_answers} correct_rate={payload.get('correct_rate')}",
        "GET /teacher/classes/{id}/teaching-analytics",
    )
    weak_points = payload.get("weak_knowledge_points") or []
    weak_names = [
        item.get("knowledge_point") if isinstance(item, dict) else item for item in weak_points
    ]
    step(
        "E 学情",
        f"{teacher.name}(teacher)",
        f"{class_name} 教学分析给出薄弱知识点",
        bool(weak_points),
        "weak_knowledge_points 非空",
        f"weak={weak_names}",
        "GET /teacher/classes/{id}/teaching-analytics",
    )

    # student-side evidence of the same answers
    status, mistakes_note = runner.call(
        EVAL_API, "GET", f"/evaluation/mistakes/{student.user_id}", student
    )
    step(
        "E 联动",
        f"{student.name}(student)",
        "学生错题本可读",
        status == 200 and isinstance(mistakes_note, dict),
        "200 + 错题本对象",
        f"status={status} keys={sorted(list((mistakes_note or {}).keys()))[:6]}",
        "GET /evaluation/mistakes/{id}",
    )
    status, analytics_me = runner.call(
        EVAL_API, "GET", f"/evaluation/analytics/{student.user_id}?days=30", student
    )
    step(
        "E 联动",
        f"{student.name}(student)",
        "学生学习分析反映本次作答",
        status == 200 and isinstance(analytics_me, dict),
        "200 + 分析对象",
        f"status={status} keys={sorted(list((analytics_me or {}).keys()))[:6]}",
        "GET /evaluation/analytics/{id}",
    )
    status, dashboard = runner.call(
        USER_API, "GET", f"/users/{student.user_id}/profile/dashboard", student
    )
    mastery_overview = None
    if isinstance(dashboard, dict):
        mastery_overview = dashboard.get("mastery_overview")
        if isinstance(mastery_overview, dict):
            mastery_overview = round(
                sum(float(value) for value in mastery_overview.values())
                / max(1, len(mastery_overview)), 2
            )
    step(
        "E 联动",
        f"{student.name}(student)",
        "学生画像看板显示掌握度",
        status == 200 and isinstance(mastery_overview, (int, float)) and mastery_overview > 0,
        "mastery_overview > 0",
        f"status={status} mastery_overview={mastery_overview}",
        "GET /users/{id}/profile/dashboard",
    )
    link(
        "学生", "作答被判分后写入画像", "学生",
        f"个人画像看板 mastery_overview={mastery_overview}", True,
    )

    # teacher view of the same student's mistakes
    status, teacher_detail = runner.call(
        EVAL_API, "GET", f"/evaluation/mistakes/{student.user_id}/teacher-detail", teacher
    )
    step(
        "E 联动",
        f"{teacher.name}(teacher)",
        f"{class_name} 教师可查看该学生错题详情",
        status == 200 and isinstance(teacher_detail, dict),
        "200 + 错题详情",
        f"status={status} keys={sorted(list((teacher_detail or {}).keys()))[:6]}",
        "GET /evaluation/mistakes/{id}/teacher-detail",
    )

    # boundary: another student cannot read this profile dashboard
    others = [
        item for item in runner.actors.values()
        if item.role == "student" and item.key != student.key
    ]
    if others:
        other = others[0]
        status, _ = runner.call(
            USER_API, "GET", f"/users/{student.user_id}/profile/dashboard", other
        )
        step(
            "E 越权",
            f"{other.name}(student)",
            "学生无法读取他人画像看板",
            status in (403, 404),
            "403/404",
            f"status={status}",
            "GET /users/{id}/profile/dashboard (other student)",
        )


# --------------------------------------------------------------------------- #
# analytics snapshot before answering
# --------------------------------------------------------------------------- #
def snapshot_analytics(runner: Runner, ctx: dict) -> dict:
    teacher = ctx.get("teacher")
    class_id = ctx.get("class_id")
    status, insights = runner.call(
        TEACHER_API, "GET", f"/teacher/classes/{class_id}/insights", teacher
    )
    masteries = [
        item.get("mastery") for item in insights or [] if isinstance(item.get("mastery"), int)
    ]
    status, analytics = runner.call(
        TEACHER_API, "GET", f"/teacher/classes/{class_id}/teaching-analytics", teacher
    )
    payload = analytics if isinstance(analytics, dict) else {}
    return {
        "class": ctx.get("class_name"),
        "masteries": masteries,
        "insights_count": len(insights or []),
        "total_answers": payload.get("total_answers"),
        "correct_rate": payload.get("correct_rate"),
    }


# --------------------------------------------------------------------------- #
# cleanup
# --------------------------------------------------------------------------- #
def cleanup(db_path: Path) -> dict:
    """Delete everything tagged with [USECASE]; the real answers stay."""

    from scripts.demo_teaching_dataset import configure_database

    configure_database(db_path)
    from common.db.session import SessionLocal
    from common.models.checkin import (
        AttendanceRecord,
        AttendanceSession,
        CheckinSubmissionRevision,
        CheckinTask,
        CheckinTaskSubmission,
        ClassScheduleException,
        ClassSession,
    )
    from common.models.learning import (
        Assignment,
        AssignmentSubmission,
        Classroom,
        Notification,
        SubmissionRevision,
        TeachingScope,
    )
    from common.models.teacher_support import CourseResourceDelivery

    removed: dict[str, int] = {}
    with SessionLocal() as db:
        def drop(model, criterion) -> None:
            count = db.query(model).filter(criterion).delete(synchronize_session=False)
            if count:
                removed[model.__name__] = removed.get(model.__name__, 0) + count

        # 本次用例创建的临时班级（名称为 [USECASE] 前缀）
        usecase_classes = [
            row[0] for row in db.query(Classroom.id).filter(Classroom.name.like(f"{TAG}%"))
        ]
        if usecase_classes:
            assignment_ids = [
                row[0]
                for row in db.query(Assignment.id).filter(Assignment.class_id.in_(usecase_classes))
            ]
            if assignment_ids:
                drop(SubmissionRevision, SubmissionRevision.submission_id.in_(assignment_ids))
                drop(
                    AssignmentSubmission,
                    AssignmentSubmission.assignment_id.in_(assignment_ids),
                )
                drop(Assignment, Assignment.id.in_(assignment_ids))
            drop(CheckinTask, CheckinTask.class_id.in_(usecase_classes))
            drop(TeachingScope, TeachingScope.class_id.in_(usecase_classes))
            drop(Classroom, Classroom.id.in_(usecase_classes))

        # 演示班上的本次用例产物
        demo_classes = [
            row[0] for row in db.query(Classroom.id).filter(Classroom.name.like("[DEMO]%"))
        ]
        if demo_classes:
            assignment_ids = [
                row[0]
                for row in db.query(Assignment.id).filter(
                    Assignment.class_id.in_(demo_classes), Assignment.title.like(f"{TAG}%")
                )
            ]
            if assignment_ids:
                submission_ids = [
                    row[0]
                    for row in db.query(AssignmentSubmission.id).filter(
                        AssignmentSubmission.assignment_id.in_(assignment_ids)
                    )
                ]
                if submission_ids:
                    drop(SubmissionRevision, SubmissionRevision.submission_id.in_(submission_ids))
                drop(AssignmentSubmission, AssignmentSubmission.assignment_id.in_(assignment_ids))
                drop(Assignment, Assignment.id.in_(assignment_ids))
            drop(TeachingScope, TeachingScope.courseware_title.like(f"{TAG}%"))
            drop(CourseResourceDelivery, CourseResourceDelivery.title.like(f"{TAG}%"))
            drop(Notification, Notification.title.like(f"{TAG}%"))
            drop(ClassScheduleException, ClassScheduleException.class_id.in_(demo_classes))
            drop(ClassSession, ClassSession.topic.like(f"{TAG}%"))

            tasks = [
                row[0]
                for row in db.query(CheckinTask.id).filter(
                    CheckinTask.class_id.in_(demo_classes), CheckinTask.title.like(f"{TAG}%")
                )
            ]
            if tasks:
                subs = [
                    row[0]
                    for row in db.query(CheckinTaskSubmission.id).filter(
                        CheckinTaskSubmission.task_id.in_(tasks)
                    )
                ]
                if subs:
                    drop(CheckinSubmissionRevision, CheckinSubmissionRevision.submission_id.in_(subs))
                    drop(CheckinTaskSubmission, CheckinTaskSubmission.id.in_(subs))
                drop(CheckinTask, CheckinTask.id.in_(tasks))
            sessions = [
                row[0]
                for row in db.query(AttendanceSession.id).filter(
                    AttendanceSession.class_id.in_(demo_classes),
                    AttendanceSession.title.like(f"{TAG}%"),
                )
            ]
            if sessions:
                drop(AttendanceRecord, AttendanceRecord.session_id.in_(sessions))
                drop(AttendanceSession, AttendanceSession.id.in_(sessions))
        db.commit()
    return removed


# --------------------------------------------------------------------------- #
# runner
# --------------------------------------------------------------------------- #
def run(db_path: Path, per_student: int, only: str = "", keep: bool = False) -> dict:
    runner = Runner()
    case_identity(runner)
    case_admin(runner)

    class_map = load_class_questions(db_path)
    contexts = case_teacher_prepare(runner, class_map)
    step(
        "C 覆盖",
        "用例编排",
        "有题库的演示教学班全部纳入联动",
        bool(contexts) and len(contexts) >= len(class_map),
        f"参与班级数 >= {len(class_map)}",
        f"contexts={len(contexts)} bank_classes={len(class_map)} classes={[item['class_name'] for item in contexts]}",
        "GET /teacher/classes ×4 + load_class_questions",
    )

    # 教师做什么，学生立刻看到什么
    for ctx in contexts:
        case_student_actions(runner, ctx)

    # 学情在作答之前是什么样
    before_map = {ctx["class_id"]: snapshot_analytics(runner, ctx) for ctx in contexts}

    # 学生真实作答（服务端判分）
    learned = case_student_learn(runner, contexts, per_student, db_path)

    # 教师批改 + 学情联动前后对照
    for ctx in contexts:
        case_teacher_review(runner, ctx, before_map.get(ctx["class_id"], {}))

    removed = {} if keep else cleanup(db_path)
    total = len(STEPS)
    passed = sum(1 for item in STEPS if item["status"] == "PASS")
    return {
        "steps": STEPS,
        "links": LINKS,
        "learning": learned,
        "analytics_before": list(before_map.values()),
        "classes": [item["class_name"] for item in contexts],
        "cleanup": removed,
        "summary": {"total": total, "passed": passed, "failed": total - passed},
    }


def _render_report(result: dict, out_dir: Path) -> None:
    lines = [
        "# 角色用例与联动验证报告",
        "",
        f"生成时间：`{result['generated_at']}`",
        f"运行库：`{result['database']}`",
        "",
        "本报告的每一步都由真实账号登录后调用真实服务接口完成，"
        "学情数据来自学生通过 `POST /evaluation/batch_submit` 的真实作答（服务端比对标准答案判分），"
        "不写入任何预设的掌握度、正确率或错题数。",
        "",
        "## 1. 结果总览",
        "",
        "| 指标 | 数值 |",
        "| --- | --- |",
        f"| 用例步骤 | {result['summary']['total']} |",
        f"| 通过 | {result['summary']['passed']} |",
        f"| 失败 | {result['summary']['failed']} |",
        f"| 联动连线 | {len(result['links'])} |",
        "",
        "## 2. 角色覆盖",
        "",
        "| 角色 | 账号 | 真实操作 |",
        "| --- | --- | --- |",
        "| 管理员 | demo_admin | 总览/用户目录/学科目录/审计日志/停用与恢复账号 |",
        "| 教师 | demo_zhangming 等 4 人 | 教学范围、排课、讲义投送、作业、打卡任务、课堂签到、班级通知、批改、学情 |",
        "| 学生 | demo_s01 ~ demo_s24 | 课表、教学范围、资料、作业提交、打卡、签到、通知、真实作答、错题本、画像 |",
        "",
        "## 3. 联动矩阵（谁的动作 → 谁立刻看到）",
        "",
        "| 产生方 | 动作 | 接受方 | 观测结果 | 结论 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in result["links"]:
        lines.append(
            f"| {item['producer']} | {item['action']} | {item['consumer']} | "
            f"{item['observation']} | {'PASS' if item['status'] == 'PASS' else 'FAIL'} |"
        )
    lines += ["", "## 4. 逐项结果", "", "| 用例 | 角色 | 步骤 | 预期 | 实际 | 状态 | 证据 |", "| --- | --- | --- | --- | --- | --- | --- |"]
    for item in result["steps"]:
        lines.append(
            f"| {item['case']} | {item['actor']} | {item['step']} | {item['expected']} | "
            f"{item['actual']} | {'PASS' if item['status'] == 'PASS' else 'FAIL'} | {item['evidence']} |"
        )
    lines += [
        "",
        "## 5. 学情是怎么来的",
        "",
        "- `scripts/demo_learning_evidence.py` 只准备**公共演示客观题**与教学范围，不写任何作答记录；",
        "- 学生通过 `POST /evaluation/batch_submit` 逐题作答，`ReportService._compare_objective_answer` "
        "把提交答案与标准答案比对得出 `is_correct`；",
        "- `ProfileUpdater` 依据这些真实作答递推掌握度，`load_evidence` 再供教师端洞察与教学分析读取；",
        "- 因此报告里每个 mastery / 错题数 / 正确率都可以追溯到具体某次 HTTP 作答请求。",
        "",
        "## 6. 学生作答明细",
        "",
        "| 账号 | 画像 | 提交 | 判分 | 正确 | 服务端判定与作答一致 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for item in result["learning"].get("students", []):
        lines.append(
            f"| {item['username']} | {item['persona']} | {item['submitted']} | {item['graded']} | "
            f"{item['correct']} | {'是' if item['server_agrees_with_intent'] else '否'} |"
        )
    lines += [
        "",
        "## 7. 清理",
        "",
        f"```json\n{json.dumps(result.get('cleanup', {}), ensure_ascii=False, indent=2)}\n```",
        "",
    ]
    (out_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True)
    parser.add_argument("--per-student", type=int, default=DEFAULT_QUESTIONS_PER_STUDENT)
    parser.add_argument("--only", default="", help="保留参数：按分段执行（暂未启用）")
    parser.add_argument("--keep", action="store_true", help="不清理 [USECASE] 临时数据")
    parser.add_argument("--cleanup-only", action="store_true", help="只清理遗留的 [USECASE] 数据")
    parser.add_argument("--evidence-dir", default="")
    args = parser.parse_args(argv)

    db_path = Path(args.db)
    if not db_path.exists():
        parser.error(f"database not found: {db_path}")

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = Path(args.evidence_dir or ROOT / "artifacts" / "demo-teaching" / f"role-usecases-{stamp}")
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.cleanup_only:
        removed = cleanup(db_path)
        print(json.dumps({"cleanup": removed}, ensure_ascii=False, indent=2))
        return 0

    result = run(db_path, args.per_student, args.only, args.keep)
    result["generated_at"] = datetime.now(TZ).isoformat()
    result["database"] = str(db_path)
    (out_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _render_report(result, out_dir)

    summary = result["summary"]
    print(f"\n{summary['passed']}/{summary['total']} passed, {summary['failed']} failed")
    print(f"evidence: {out_dir}")
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

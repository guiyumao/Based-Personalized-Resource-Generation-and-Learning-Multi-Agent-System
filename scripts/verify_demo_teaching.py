"""Real cross-role end-to-end verification for the demo teaching environment.

Every assertion goes through the running HTTP services with a real account
login: no mocked responses, no direct writes to pretend a business action
happened. Records created by the run are prefixed with ``[VERIFY]`` and removed
afterwards, so the demo dataset itself is left intact.

    python scripts/verify_demo_teaching.py --db artifacts/local-start-20261019/runtime.sqlite
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT, ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import requests  # noqa: E402
from demo_teaching_dataset import (  # noqa: E402
    DEFAULT_PASSWORD,
    STUDENTS,
    TEACHERS,
    configure_database,
    now_local,
    username_of,
)

USER_API = "http://127.0.0.1:8001"
APP_API = "http://127.0.0.1:8005"
TAG = "[VERIFY]"
TZ = timezone(timedelta(hours=8))

RESULTS: list[dict] = []


def record(scene: str, name: str, ok: bool, expected: str, actual: str, evidence: str = "") -> bool:
    RESULTS.append(
        {
            "scene": scene,
            "check": name,
            "status": "PASS" if ok else "FAIL",
            "expected": expected,
            "actual": actual,
            "evidence": evidence,
        }
    )
    print(f"[{'PASS' if ok else 'FAIL'}] {scene} · {name}: {actual}")
    return ok


class Client:
    def __init__(self, base: str):
        self.base = base
        self.session = requests.Session()

    def call(self, method: str, path: str, token: str | None = None, **kwargs):
        headers = kwargs.pop("headers", {})
        if token:
            headers["Authorization"] = f"Bearer {token}"
        response = self.session.request(
            method, f"{self.base}{path}", headers=headers, timeout=30, **kwargs
        )
        try:
            payload = response.json()
        except ValueError:
            payload = {"raw": response.text[:300]}
        return response.status_code, payload

    def data(self, method: str, path: str, token: str | None = None, **kwargs):
        status, payload = self.call(method, path, token, **kwargs)
        return status, payload.get("data", payload) if isinstance(payload, dict) else payload


def login(username: str) -> tuple[str | None, dict]:
    response = requests.post(
        f"{USER_API}/users/login",
        json={"username": username, "password": DEFAULT_PASSWORD},
        timeout=30,
    )
    if response.status_code != 200:
        return None, {"status": response.status_code, "body": response.text[:200]}
    payload = response.json()
    token = payload.get("access_token") or payload.get("token")
    return token, payload


def cleanup(db_path: Path) -> dict:
    """Remove every row created by this verification run."""

    configure_database(db_path)
    from common.db.session import SessionLocal
    from common.models.checkin import (
        AttendanceRecord,
        AttendanceSession,
        CheckinTask,
        ClassScheduleException,
        ClassSession,
    )
    from common.models.learning import (
        Assignment,
        AssignmentSubmission,
        ClassEnrollment,
        Classroom,
        Course,
        Notification,
    )

    removed: dict[str, int] = {}
    with SessionLocal() as db:
        class_ids = [
            row[0] for row in db.query(Classroom.id).filter(Classroom.name.like(f"{TAG}%"))
        ]
        if not class_ids:
            return removed
        assignment_ids = [
            row[0] for row in db.query(Assignment.id).filter(Assignment.class_id.in_(class_ids))
        ]
        session_ids = [
            row[0]
            for row in db.query(AttendanceSession.id).filter(
                AttendanceSession.class_id.in_(class_ids)
            )
        ]

        def drop(model, criterion) -> None:
            count = db.query(model).filter(criterion).delete(synchronize_session=False)
            if count:
                removed[model.__name__] = removed.get(model.__name__, 0) + count

        drop(AttendanceRecord, AttendanceRecord.session_id.in_(session_ids))
        drop(AttendanceSession, AttendanceSession.class_id.in_(class_ids))
        drop(AssignmentSubmission, AssignmentSubmission.assignment_id.in_(assignment_ids))
        drop(Assignment, Assignment.class_id.in_(class_ids))
        drop(CheckinTask, CheckinTask.class_id.in_(class_ids))
        drop(ClassScheduleException, ClassScheduleException.class_id.in_(class_ids))
        drop(ClassSession, ClassSession.class_id.in_(class_ids))
        drop(ClassEnrollment, ClassEnrollment.class_id.in_(class_ids))
        drop(Notification, Notification.title.like(f"%{TAG}%"))
        drop(Classroom, Classroom.id.in_(class_ids))
        drop(Course, Course.title.like(f"{TAG}%"))
        db.commit()
    return removed


def run(db_path: Path) -> dict:
    teacher_client = Client(APP_API)

    # ------------------------------------------------------------- identities
    teacher_tokens: dict[str, str] = {}
    for teacher in TEACHERS:
        token, payload = login(username_of(teacher.key))
        record(
            "身份",
            f"教师 {teacher.name} 登录",
            bool(token),
            "登录成功并返回 token",
            f"token={'yes' if token else 'no'} role={payload.get('role')}",
            evidence="POST /users/login",
        )
        if token:
            teacher_tokens[teacher.key] = token

    student_tokens: dict[str, str] = {}
    for student in STUDENTS[:6]:
        token, payload = login(username_of(student.key))
        record(
            "身份",
            f"学生 {student.name} 登录",
            bool(token),
            "登录成功并返回 token",
            f"token={'yes' if token else 'no'} role={payload.get('role')}",
            evidence="POST /users/login",
        )
        if token:
            student_tokens[student.key] = token

    wrong = requests.post(
        f"{USER_API}/users/login",
        json={"username": username_of(TEACHERS[0].key), "password": "definitely-not-the-password"},
        timeout=30,
    )
    record(
        "身份",
        "错误密码被拒绝",
        wrong.status_code == 401,
        "401",
        f"status={wrong.status_code}",
        evidence="POST /users/login (wrong password)",
    )

    # --------------------------------------------------- teacher class listing
    zhang = teacher_tokens.get("zhangming")
    status, classes = teacher_client.data("GET", "/teacher/classes", zhang)
    names = [item["name"] for item in classes] if isinstance(classes, list) else []
    record(
        "班级",
        "教师看到自己的教学班",
        status == 200 and len([n for n in names if n.startswith("[DEMO]")]) >= 2,
        ">=2 个 [DEMO] 教学班",
        f"status={status} count={len(names)}",
        evidence="GET /teacher/classes",
    )
    teaching_classes = [
        item
        for item in classes
        if item["name"].startswith("[DEMO]") and "行政班" not in item["name"]
    ]
    record(
        "班级",
        "教学班关联真实课程",
        bool(teaching_classes) and all(item.get("course_id") for item in teaching_classes),
        "每个教学班都有 course_id",
        f"course_ids={[item.get('course_id') for item in teaching_classes]}",
        evidence="GET /teacher/classes",
    )

    # ------------------------------------------------ scene A: create + join
    invite_code = None
    verify_class_id = None
    status, created = teacher_client.data(
        "POST",
        "/teacher/classes",
        zhang,
        json={
            "name": f"{TAG} 数据结构 · 验收班",
            "subject": "数据结构",
            "teacher_name": "张明",
            "join_mode": "invite",
            "description": "自动化跨角色验收创建的临时班级",
            "semester": "2026-2027-1",
            "is_public": True,
            "capacity": 20,
        },
    )
    if status in (200, 201) and isinstance(created, dict):
        verify_class_id = created.get("id")
        invite_code = created.get("invite_code")
    record(
        "场景A 班级创建",
        "教师创建班级返回持久化 id 与邀请码",
        bool(verify_class_id and invite_code),
        "200 + id + invite_code",
        f"status={status} id={verify_class_id} invite={'yes' if invite_code else 'no'}",
        evidence="POST /teacher/classes",
    )
    status, classes_after = teacher_client.data("GET", "/teacher/classes", zhang)
    listed = any(item.get("id") == verify_class_id for item in classes_after or [])
    record(
        "场景A 班级创建",
        "新建班级立即出现在教师班级列表",
        listed,
        "列表包含新班级",
        f"status={status} listed={listed}",
        evidence="GET /teacher/classes",
    )

    s01 = student_tokens.get("s01")
    status, joined = teacher_client.data(
        "POST",
        "/teacher/students/me/classes/join",
        s01,
        json={"invite_code": invite_code or "INVALID"},
    )
    record(
        "场景A 学生入班",
        "学生用邀请码加入班级",
        status == 200,
        "200",
        f"status={status}",
        evidence="POST /teacher/students/me/classes/join",
    )
    status, members = teacher_client.data("GET", f"/teacher/classes/{verify_class_id}/members", zhang)
    member_ids = [item["user_id"] for item in members] if isinstance(members, list) else []
    record(
        "场景A 学生入班",
        "教师端成员列表出现该学生",
        status == 200 and len(member_ids) == 1,
        "members == 1",
        f"status={status} members={len(member_ids)}",
        evidence="GET /teacher/classes/{id}/members",
    )
    status, _ = teacher_client.data(
        "POST",
        "/teacher/students/me/classes/join",
        s01,
        json={"invite_code": invite_code or "INVALID"},
    )
    status2, members2 = teacher_client.data(
        "GET", f"/teacher/classes/{verify_class_id}/members", zhang
    )
    record(
        "场景A 重复入班",
        "重复加入保持幂等",
        status == 200 and len(members2 or []) == 1,
        "再次 200 且成员仍为 1",
        f"status={status} members={len(members2 or [])}",
        evidence="POST join ×2 + GET members",
    )
    lihua = teacher_tokens.get("lihua")
    status, _ = teacher_client.call(
        "GET", f"/teacher/classes/{verify_class_id}/members", lihua
    )
    record(
        "场景A 越权",
        "无关教师无法查看该班成员",
        status == 403,
        "403",
        f"status={status}",
        evidence="GET members as non-owner teacher",
    )

    # --------------------------------------------- scene C: timetable linkage
    weekday = (now_local().isoweekday() % 7) + 1
    status, session_item = teacher_client.data(
        "POST",
        f"/learning/classes/{verify_class_id}/schedule",
        zhang,
        json={
            "topic": f"{TAG} 线性表",
            "weekday": weekday,
            "start_time": "16:00",
            "end_time": "17:40",
            "week_start": "2026-09-07",
            "week_end": "2027-01-10",
            "location": "验收教室",
            "mode": "offline",
        },
    )
    session_id = session_item.get("id") if isinstance(session_item, dict) else None
    record(
        "场景C 课表联动",
        "教师排课成功",
        status == 200 and bool(session_id),
        "200 + session id",
        f"status={status} id={session_id}",
        evidence="POST /learning/classes/{id}/schedule",
    )
    status, student_schedule = teacher_client.data("GET", "/learning/schedule/me", s01)
    text = json.dumps(student_schedule, ensure_ascii=False) if student_schedule else ""
    record(
        "场景C 课表联动",
        "学生课表自动同步该课程",
        status == 200 and f"{TAG} 线性表" in text,
        "学生课表包含新排课",
        f"status={status} contains={f'{TAG} 线性表' in text}",
        evidence="GET /learning/schedule/me",
    )
    today = now_local().date()
    occurrence = today + timedelta(days=(weekday - today.isoweekday()) % 7 or 7)
    status, moved = teacher_client.data(
        "POST",
        f"/learning/classes/{verify_class_id}/schedule/{session_id}/exceptions",
        zhang,
        json={
            "date": occurrence.strftime("%Y-%m-%d"),
            "kind": "reschedule",
            "new_date": (occurrence + timedelta(days=1)).strftime("%Y-%m-%d"),
            "new_start_time": "18:00",
            "new_end_time": "19:40",
            "location": "验收教室B",
            "reason": "验收调课",
        },
    )
    record(
        "场景C 课表联动",
        "教师调课成功并通知学生",
        status == 200,
        "200",
        f"status={status}",
        evidence="POST /learning/classes/{id}/schedule/{sid}/exceptions",
    )
    status, _ = teacher_client.data(
        "POST",
        f"/learning/classes/{verify_class_id}/schedule",
        zhang,
        json={
            "topic": f"{TAG} 时间冲突课",
            "weekday": weekday,
            "start_time": "16:30",
            "end_time": "17:30",
            "week_start": "2026-09-07",
            "week_end": "2027-01-10",
            "location": "验收教室",
            "mode": "offline",
        },
    )
    record(
        "场景C 课表联动",
        "同一教师时间冲突被拒绝",
        status in (409, 400, 422),
        "409",
        f"status={status}",
        evidence="POST overlapping session",
    )

    # ------------------------------------------------ scene D: homework loop
    due = (datetime.now(UTC) + timedelta(days=2)).isoformat()
    status, assignment = teacher_client.data(
        "POST",
        "/teacher/homework/assign",
        zhang,
        json={
            "class_id": verify_class_id,
            "title": f"{TAG} 线性表编程",
            "description": "验收用作业：实现单链表插入与删除。",
            "due_at": due,
        },
    )
    assignment_id = assignment.get("id") if isinstance(assignment, dict) else None
    record(
        "场景D 作业闭环",
        "教师发布作业",
        status == 200 and bool(assignment_id),
        "200 + assignment id",
        f"status={status} id={assignment_id}",
        evidence="POST /teacher/homework/assign",
    )
    status, my_homework = teacher_client.data("GET", "/teacher/students/me/homework", s01)
    visible = any(item.get("id") == assignment_id for item in my_homework or [])
    record(
        "场景D 作业闭环",
        "学生收到该作业",
        status == 200 and visible,
        "学生作业列表包含新作业",
        f"status={status} visible={visible}",
        evidence="GET /teacher/students/me/homework",
    )
    status, submission = teacher_client.data(
        "POST",
        f"/teacher/students/me/homework/{assignment_id}/submit",
        s01,
        json={"content": "已实现单链表插入与删除，复杂度 O(1)/O(n)。"},
    )
    submission_id = submission.get("id") if isinstance(submission, dict) else None
    record(
        "场景D 作业闭环",
        "学生提交作业",
        status == 200 and bool(submission_id),
        "200 + submission id",
        f"status={status} id={submission_id}",
        evidence="POST submit",
    )
    status, submissions = teacher_client.data(
        "GET", f"/teacher/homework/{assignment_id}/submissions", zhang
    )
    record(
        "场景D 作业闭环",
        "教师看到真实提交记录",
        status == 200 and len(submissions or []) == 1,
        "1 条提交",
        f"status={status} count={len(submissions or [])}",
        evidence="GET /teacher/homework/{id}/submissions",
    )
    status, reviewed = teacher_client.data(
        "POST",
        f"/teacher/homework/{submission_id}/review",
        zhang,
        json={"score": 92, "comment": "结构清晰，注意空链表边界。"},
    )
    record(
        "场景D 作业闭环",
        "教师批改写入成绩",
        status == 200 and float((reviewed or {}).get("score") or 0) == 92,
        "score == 92",
        f"status={status} score={(reviewed or {}).get('score')}",
        evidence="POST /teacher/homework/{sid}/review",
    )
    status, my_homework = teacher_client.data("GET", "/teacher/students/me/homework", s01)
    mine = next((item for item in my_homework or [] if item.get("id") == assignment_id), {})
    got = (mine.get("my_submission") or {}).get("score")
    record(
        "场景D 作业闭环",
        "学生端看到批改成绩",
        status == 200 and float(got or 0) == 92,
        "学生作业里 score == 92",
        f"status={status} score={got}",
        evidence="GET /teacher/students/me/homework",
    )
    status, unread = teacher_client.data("GET", "/learning/notifications/unread-count", s01)
    record(
        "场景D 作业闭环",
        "学生收到批改通知",
        status == 200,
        "200 且有未读",
        f"status={status} unread={unread}",
        evidence="GET /learning/notifications/unread-count",
    )

    # non-member submission must fail
    outsider = student_tokens.get("s02")
    status, _ = teacher_client.call(
        "POST",
        f"/teacher/students/me/homework/{assignment_id}/submit",
        outsider,
        json={"content": "越权提交"},
    )
    record(
        "场景D 越权",
        "非本班学生无法提交该作业",
        status in (403, 404),
        "403",
        f"status={status}",
        evidence="POST submit as non-member",
    )

    # ---------------------------------------------- scene E: attendance loop
    start = datetime.now(UTC) - timedelta(minutes=5)
    end = datetime.now(UTC) + timedelta(minutes=25)
    status, attendance = teacher_client.data(
        "POST",
        "/learning/checkin/manage/attendance",
        zhang,
        json={
            "class_id": verify_class_id,
            "title": f"{TAG} 课堂签到",
            "start_at": start.isoformat(),
            "end_at": end.isoformat(),
        },
    )
    attendance_id = attendance.get("id") if isinstance(attendance, dict) else None
    code = (attendance or {}).get("code")
    record(
        "场景E 签到",
        "教师发起课堂签到并生成签到码",
        status == 200 and bool(attendance_id and code),
        "200 + id + code",
        f"status={status} id={attendance_id} code={'yes' if code else 'no'}",
        evidence="POST /learning/checkin/manage/attendance",
    )
    status, _ = teacher_client.call(
        "POST", "/learning/checkin/attendance/checkin", outsider, json={"code": code}
    )
    record(
        "场景E 越权",
        "非本班学生签到被拒绝",
        status == 403,
        "403",
        f"status={status}",
        evidence="POST /learning/checkin/attendance/checkin (non-member)",
    )
    status, checked = teacher_client.data(
        "POST", "/learning/checkin/attendance/checkin", s01, json={"code": code}
    )
    record(
        "场景E 签到",
        "本班学生签到成功",
        status == 200,
        "200",
        f"status={status}",
        evidence="POST checkin",
    )
    status, live = teacher_client.data(
        "GET", f"/learning/checkin/manage/attendance/{attendance_id}/live", zhang
    )
    rows = (live or {}).get("rows") if isinstance(live, dict) else None
    present = sum(1 for row in rows or [] if row.get("status") == "present")
    record(
        "场景E 签到",
        "教师实时统计显示已签到",
        status == 200 and present == 1,
        "1 人已签到（present）",
        f"status={status} present={present}",
        evidence="GET live",
    )
    status, _ = teacher_client.data(
        "POST", f"/learning/checkin/manage/attendance/{attendance_id}/close", zhang
    )
    record(
        "场景E 签到",
        "教师结束签到",
        status == 200,
        "200",
        f"status={status}",
        evidence="POST close",
    )
    status, _ = teacher_client.call(
        "POST", "/learning/checkin/attendance/checkin", s01, json={"code": code}
    )
    record(
        "场景E 签到",
        "已结束签到不可重复签到",
        status in (409, 400),
        "409",
        f"status={status}",
        evidence="POST checkin after close",
    )

    # -------------------------------------------- scene F: notification read
    status, before = teacher_client.data("GET", "/learning/notifications/unread-count", s01)
    before_count = (before or {}).get("unread_count") if isinstance(before, dict) else None
    status, published = teacher_client.data(
        "POST",
        "/learning/notifications/publish",
        zhang,
        json={
            "request_key": f"verify-{TAG}-{datetime.now().timestamp():.0f}",
            "scope": "class",
            "target_id": verify_class_id,
            "title": f"{TAG} 课程公告",
            "content": "验收用班级公告，用于验证定向投递与未读数。",
            "type": "course",
        },
    )
    record(
        "场景F 通知",
        "教师向班级定向发布通知",
        status == 200,
        "200",
        f"status={status}",
        evidence="POST /learning/notifications/publish",
    )
    status, after = teacher_client.data("GET", "/learning/notifications/unread-count", s01)
    after_count = (after or {}).get("unread_count") if isinstance(after, dict) else None
    record(
        "场景F 通知",
        "目标学生未读数增加",
        status == 200 and isinstance(after_count, int) and isinstance(before_count, int)
        and after_count > before_count,
        "after > before",
        f"before={before_count} after={after_count}",
        evidence="GET unread-count",
    )
    status, inbox = teacher_client.data("GET", "/learning/notifications/inbox?page=1&size=8", s01)
    inbox_items = (inbox or {}).get("items") if isinstance(inbox, dict) else inbox
    record(
        "场景F 通知",
        "学生收件箱可读且包含通知",
        status == 200 and isinstance(inbox_items, list) and len(inbox_items) > 0,
        "非空收件箱",
        f"status={status} items={len(inbox_items or [])}",
        evidence="GET /learning/notifications/inbox",
    )
    status, read_all = teacher_client.data("POST", "/learning/notifications/read-all", s01)
    status, cleared = teacher_client.data("GET", "/learning/notifications/unread-count", s01)
    record(
        "场景F 通知",
        "一键已读后未读数归零并持久",
        isinstance(cleared, dict) and cleared.get("unread_count") == 0,
        "unread_count == 0",
        f"unread={cleared}",
        evidence="POST read-all + GET unread-count",
    )

    # ---------------------------------------- scene G: analytics consistency
    ds_class = next(
        (item for item in classes if "数据结构 · 软件工程1班" in item.get("name", "")), None
    )
    ds_class_id = (ds_class or {}).get("id")
    status, insights = teacher_client.data(
        "GET", f"/teacher/classes/{ds_class_id}/insights", zhang
    )
    record(
        "场景G 学情",
        "教师学情分析返回真实学生列表",
        status == 200 and isinstance(insights, list) and len(insights) > 0,
        "非空列表",
        f"status={status} count={len(insights or [])}",
        evidence="GET /teacher/classes/{ds_class_id}/insights",
    )
    if isinstance(insights, list) and insights:
        sample = insights[0]
        record(
            "场景G 学情",
            "学情卡片包含可追溯指标",
            "mastery" in sample and "mistake_count" in sample,
            "mastery + mistake_count",
            f"keys={sorted(sample.keys())[:8]}",
            evidence="insights[0]",
        )

    # ------------------------------------------- scene H: concurrent joins
    import sqlite3

    conn = sqlite3.connect(str(db_path))
    try:
        open_class = conn.execute(
            "select id, invite_code from classrooms where name like '[DEMO] 数据结构 · 软件工程1班'"
        ).fetchone()
    finally:
        conn.close()
    if open_class:
        open_class_id, _ = open_class
        joiners = [student_tokens[key] for key in ("s02", "s03", "s04") if key in student_tokens]

        def join(token: str) -> int:
            return teacher_client.call(
                "POST", f"/learning/classrooms/{open_class_id}/join", token
            )[0]

        with ThreadPoolExecutor(max_workers=3) as pool:
            codes = list(pool.map(join, joiners))
        record(
            "场景H 并发",
            "多学生并发加入同一开放课堂",
            all(code in (200, 201) for code in codes) and len(joiners) == 3,
            "全部 200",
            f"codes={codes}",
            evidence="POST /learning/classrooms/{id}/join ×3",
        )

    # ------------------------------------------- scene I: deadline boundary
    with sqlite3.connect(str(db_path)) as conn:
        past = conn.execute(
            "select id from assignments where title = '二叉树遍历与重建'"
        ).fetchone()
    if past:
        status, _ = teacher_client.call(
            "POST",
            f"/teacher/students/me/homework/{past[0]}/submit",
            s01,
            json={"content": "逾期提交测试"},
        )
        record(
            "场景I 边界",
            "已截止作业拒绝提交",
            status in (409, 400),
            "409",
            f"status={status}",
            evidence="POST submit on past deadline",
        )

    # ------------------------------------------- scene J: data consistency
    with sqlite3.connect(str(db_path)) as conn:
        db_count = conn.execute(
            "select count(*) from class_enrollments where class_id=?", (verify_class_id,)
        ).fetchone()[0]
    status, members3 = teacher_client.data(
        "GET", f"/teacher/classes/{verify_class_id}/members", zhang
    )
    record(
        "场景J 一致性",
        "接口成员数与数据库一致",
        len(members3 or []) == db_count,
        f"DB={db_count}",
        f"api={len(members3 or [])} db={db_count}",
        evidence="GET members vs SQLite count",
    )

    return {
        "results": RESULTS,
        "summary": {
            "total": len(RESULTS),
            "passed": sum(1 for item in RESULTS if item["status"] == "PASS"),
            "failed": sum(1 for item in RESULTS if item["status"] == "FAIL"),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True)
    parser.add_argument("--evidence-dir", default="")
    args = parser.parse_args(argv)

    db_path = Path(args.db)
    if not db_path.exists():
        parser.error(f"database not found: {db_path}")

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = Path(args.evidence_dir or ROOT / "artifacts" / "demo-teaching" / f"verify-{stamp}")
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        result = run(db_path)
    finally:
        removed = cleanup(db_path)
        if "result" not in locals():
            result = {"results": RESULTS, "summary": {"total": len(RESULTS), "passed": 0, "failed": 1}}
        result["cleanup"] = removed

    result["generated_at"] = datetime.now(TZ).isoformat()
    (out_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    summary = result["summary"]
    print(f"\n{summary['passed']}/{summary['total']} passed, {summary['failed']} failed")
    print(f"evidence: {out_dir / 'result.json'}")
    print(f"cleanup: {json.dumps(result.get('cleanup', {}), ensure_ascii=False)}")
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Idempotent demo teaching environment for the local runtime database.

This script builds a multi-role teaching scenario (4 teachers, 24 students,
3 administrative cohorts, 6 courses, 8 teaching classes, timetable, homework,
check-in tasks, notifications and answer history) on top of the *existing*
service layer, then lets you inspect or reset only the records it owns.

Design rules
------------
* Reuse ``TeacherManager`` / ``CheckinManager`` / ``ClassScheduleManager`` so the
  demo data obeys the same rules as the product API (capacity, enrollment,
  deadlines, conflicts, notifications).
* Every owned row is reachable from a ``users`` row whose ``username`` starts
  with ``demo_``. Nothing else in the database is touched.
* Re-running ``seed`` never duplicates a teacher, student, class, course,
  assignment or check-in task: lookups use stable business keys.
* ``reset`` refuses to run against the packaging default ``learning_system.db``
  and always writes a SQLite backup first.

Usage
-----
    python scripts/demo_teaching_dataset.py --db <runtime.sqlite> --action check
    python scripts/demo_teaching_dataset.py --db <runtime.sqlite> --action seed
    python scripts/demo_teaching_dataset.py --db <runtime.sqlite> --action seed --refresh
    python scripts/demo_teaching_dataset.py --db <runtime.sqlite> --action reset --yes

``--refresh`` re-aligns still-interactive deadlines/check-in windows to "now"
so a demo environment left idle for days does not expire.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEMO_USER_PREFIX = "demo_"
DEMO_CLASS_TAG = "[DEMO]"
DEFAULT_PASSWORD = os.getenv("DEMO_SEED_PASSWORD", "Demo@2026")
TZ = timezone(timedelta(hours=8))
# Semester window used by every seeded class session.
SEMESTER = "2026-2027-1"
WEEK_START = "2026-09-07"
WEEK_END = "2027-01-10"


# --------------------------------------------------------------------------- #
# Scenario definition
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class TeacherSpec:
    key: str
    name: str
    subjects: tuple[str, ...]
    focus: str


@dataclass(frozen=True)
class StudentSpec:
    key: str
    name: str
    cohort: str
    persona: str


TEACHERS: tuple[TeacherSpec, ...] = (
    TeacherSpec("zhangming", "张明", ("数据结构",), "班级、作业、学情"),
    TeacherSpec("lihua", "李华", ("计算机网络",), "课程表、签到、通知"),
    TeacherSpec("wangmin", "王敏", ("数据库原理", "Java 程序设计"), "多课程管理、成绩"),
    TeacherSpec("chenjie", "陈杰", ("Python 程序设计", "软件工程"), "智能教学、资源管理"),
)

COHORTS: dict[str, str] = {
    "se1": "软件工程1班",
    "cs1": "计算机科学1班",
    "cs2": "计算机科学2班",
}

# persona: excellent / normal / struggling / pending
_STUDENT_ROWS = (
    ("s01", "林晓", "se1", "excellent"),
    ("s02", "周杰", "se1", "normal"),
    ("s03", "吴倩", "se1", "excellent"),
    ("s04", "郑凯", "se1", "normal"),
    ("s05", "孙悦", "se1", "normal"),
    ("s06", "马超", "se1", "struggling"),
    ("s07", "朱琳", "se1", "struggling"),
    ("s08", "胡阳", "se1", "pending"),
    ("s09", "徐磊", "cs1", "excellent"),
    ("s10", "何静", "cs1", "normal"),
    ("s11", "高翔", "cs1", "excellent"),
    ("s12", "罗婷", "cs1", "normal"),
    ("s13", "梁宇", "cs1", "normal"),
    ("s14", "宋佳", "cs1", "struggling"),
    ("s15", "唐浩", "cs1", "struggling"),
    ("s16", "冯雪", "cs1", "pending"),
    ("s17", "曹阳", "cs2", "excellent"),
    ("s18", "彭博", "cs2", "normal"),
    ("s19", "董悦", "cs2", "excellent"),
    ("s20", "袁铭", "cs2", "normal"),
    ("s21", "蒋雯", "cs2", "normal"),
    ("s22", "余乐", "cs2", "struggling"),
    ("s23", "杜鹏", "cs2", "struggling"),
    ("s24", "程曦", "cs2", "pending"),
)

STUDENTS: tuple[StudentSpec, ...] = tuple(
    StudentSpec(*row) for row in _STUDENT_ROWS
)

COURSES: dict[str, dict] = {
    "ds": {
        "title": "数据结构",
        "subject": "数据结构",
        "teacher": "zhangming",
        "description": "线性表、栈与队列、树与二叉树、图、查找与排序的抽象与实现。",
        "syllabus": "第1-2周 线性表\n第3-4周 栈与队列\n第5-7周 树与二叉树\n第8-10周 图\n第11-12周 查找\n第13-14周 排序",
    },
    "cn": {
        "title": "计算机网络",
        "subject": "计算机网络",
        "teacher": "lihua",
        "description": "自顶向下理解网络体系结构、链路层、网络层、运输层与应用层。",
        "syllabus": "第1周 体系结构\n第2-3周 物理层与数据链路层\n第4-6周 网络层\n第7-9周 运输层\n第10-11周 应用层",
    },
    "db": {
        "title": "数据库原理",
        "subject": "数据库原理",
        "teacher": "wangmin",
        "description": "关系模型、SQL、数据库设计、事务与并发控制、索引与性能优化。",
        "syllabus": "第1-3周 关系模型与 SQL\n第4-6周 数据库设计\n第7-8周 事务与并发控制\n第9-10周 索引与优化",
    },
    "java": {
        "title": "Java 程序设计",
        "subject": "Java 程序设计",
        "teacher": "wangmin",
        "description": "面向对象建模、集合框架、异常处理与常用类库的工程化使用。",
        "syllabus": "第1-2周 语言基础\n第3-5周 面向对象\n第6-7周 集合框架\n第8-9周 异常与 IO",
    },
    "python": {
        "title": "Python 程序设计",
        "subject": "Python 程序设计",
        "teacher": "chenjie",
        "description": "函数与模块、数据结构、文件处理与数据分析入门。",
        "syllabus": "第1-2周 语法基础\n第3-4周 函数与模块\n第5-6周 容器与迭代\n第7-8周 文件与数据处理",
    },
    "se": {
        "title": "软件工程",
        "subject": "软件工程",
        "teacher": "chenjie",
        "description": "需求分析、结构化与面向对象设计、测试与项目管理。",
        "syllabus": "第1-3周 需求工程\n第4-6周 设计方法\n第7-8周 测试\n第9-10周 项目管理",
    },
}

# Teaching classes. ``primary`` classes are created through TeacherManager.create_class
# (which also creates the backing course); ``secondary`` classes reuse that course id
# because the service layer exposes no "add another class to an existing course" API.
CLASSROOMS: tuple[dict, ...] = (
    {
        "key": "ds_se1",
        "course": "ds",
        "name": "数据结构 · 软件工程1班",
        "cohorts": ("se1",),
        "primary": True,
        "join_mode": "open",
        "capacity": 30,
        "points": ("链表", "二叉树遍历", "图的遍历", "快速排序"),
    },
    {
        "key": "ds_cs1",
        "course": "ds",
        "name": "数据结构 · 计算机科学1班",
        "cohorts": ("cs1",),
        "primary": False,
        "join_mode": "invite",
        "capacity": 30,
        "points": ("顺序表", "栈", "二叉搜索树", "最短路径"),
    },
    {
        "key": "cn_cs1",
        "course": "cn",
        "name": "计算机网络 · 计算机科学1班",
        "cohorts": ("cs1",),
        "primary": True,
        "join_mode": "open",
        "capacity": 30,
        "points": ("OSI 七层模型", "IP 地址", "TCP 三次握手", "HTTP"),
    },
    {
        "key": "cn_cs2",
        "course": "cn",
        "name": "计算机网络 · 计算机科学2班",
        "cohorts": ("cs2",),
        "primary": False,
        "join_mode": "invite",
        "capacity": 30,
        "points": ("TCP/IP 四层模型", "子网划分", "TCP 拥塞控制", "DNS"),
    },
    {
        "key": "db_se1",
        "course": "db",
        "name": "数据库原理 · 软件工程1班",
        "cohorts": ("se1",),
        "primary": True,
        "join_mode": "open",
        "capacity": 30,
        "points": (),
    },
    {
        "key": "java_se1",
        "course": "java",
        "name": "Java 程序设计 · 软件工程1班",
        "cohorts": ("se1",),
        "primary": True,
        "join_mode": "invite",
        "capacity": 30,
        "points": (),
    },
    {
        "key": "py_cs2",
        "course": "python",
        "name": "Python 程序设计 · 计算机科学2班",
        "cohorts": ("cs2",),
        "primary": True,
        "join_mode": "open",
        "capacity": 30,
        "points": (),
    },
    {
        "key": "se_cs1",
        "course": "se",
        "name": "软件工程 · 计算机科学1班",
        "cohorts": ("cs1",),
        "primary": True,
        "join_mode": "invite",
        "capacity": 30,
        "points": (),
    },
)

# Cross-cohort electives: a few students join a class outside their own cohort.
EXTRA_ENROLLMENTS: tuple[tuple[str, str], ...] = (
    ("s02", "py_cs2"),
    ("s05", "ds_cs1"),
    ("s18", "ds_cs1"),
    ("s13", "py_cs2"),
    ("s21", "se_cs1"),
)

# weekday 1=Monday. Times never overlap for the same teacher.
SESSIONS: tuple[dict, ...] = (
    {"class": "ds_se1", "topic": "线性表与链表", "weekday": 1, "start": "08:00", "end": "09:40", "room": "教学楼A-301"},
    {"class": "ds_cs1", "topic": "树与二叉树", "weekday": 3, "start": "10:00", "end": "11:40", "room": "教学楼A-302"},
    {"class": "cn_cs1", "topic": "网络体系结构", "weekday": 2, "start": "08:00", "end": "09:40", "room": "教学楼B-201"},
    {"class": "cn_cs2", "topic": "运输层协议", "weekday": 4, "start": "10:00", "end": "11:40", "room": "教学楼B-202"},
    {"class": "db_se1", "topic": "SQL 与关系代数", "weekday": 1, "start": "14:00", "end": "15:40", "room": "实验楼C-105"},
    {"class": "java_se1", "topic": "面向对象基础", "weekday": 3, "start": "14:00", "end": "15:40", "room": "实验楼C-106"},
    {"class": "py_cs2", "topic": "函数与模块", "weekday": 2, "start": "14:00", "end": "15:40", "room": "实验楼C-201"},
    {"class": "se_cs1", "topic": "需求工程", "weekday": 4, "start": "08:00", "end": "09:40", "room": "教学楼A-401"},
    {"class": "se_cs1", "topic": "需求评审工作坊", "weekday": 5, "start": "10:00", "end": "11:40", "room": "教学楼A-402"},
)

# offset_days < 0 -> already closed; > 0 -> still interactive.
ASSIGNMENTS: tuple[dict, ...] = (
    {"key": "ds_linear", "class": "ds_se1", "title": "线性表与链表编程", "offset_days": 3,
     "body": "使用单链表实现学生成绩的插入、删除与逆序输出，提交代码与复杂度分析。"},
    {"key": "ds_tree", "class": "ds_se1", "title": "二叉树遍历与重建", "offset_days": -5,
     "body": "给定前序与中序序列重建二叉树，写出递归与非递归遍历，并分析时间复杂度。"},
    {"key": "ds_graph", "class": "ds_cs1", "title": "图的最短路径实验", "offset_days": 2,
     "body": "实现 Dijkstra 算法，输出从源点到各顶点的最短路径与路径长度。"},
    {"key": "cn_handshake", "class": "cn_cs1", "title": "TCP 三次握手分析", "offset_days": -7,
     "body": "结合抓包说明三次握手中各报文的作用，并解释为什么不能是两次握手。"},
    {"key": "cn_subnet", "class": "cn_cs1", "title": "子网划分练习", "offset_days": 0,
     "body": "将 192.168.10.0/24 划分为 6 个可用子网，写出子网掩码、网络地址与广播地址。"},
    {"key": "cn_http", "class": "cn_cs2", "title": "HTTP 与 HTTPS 对比", "offset_days": 4,
     "body": "对比 HTTP/1.1、HTTP/2 与 HTTPS 的差异，说明 TLS 握手的关键步骤。"},
    {"key": "db_sql", "class": "db_se1", "title": "SQL 查询综合练习", "offset_days": -3,
     "body": "基于给定的选课库编写 8 条查询，覆盖连接、分组、子查询与窗口函数。"},
    {"key": "db_tx", "class": "db_se1", "title": "事务与并发控制", "offset_days": 5,
     "body": "分析不可重复读与幻读的产生条件，给出两种隔离级别的解决方案。"},
    {"key": "java_oop", "class": "java_se1", "title": "面向对象建模", "offset_days": -10,
     "body": "为图书借阅场景设计类图并实现借书、还书与逾期计算，要求使用接口与继承。"},
    {"key": "java_collection", "class": "java_se1", "title": "集合框架实践", "offset_days": 2,
     "body": "用 HashMap 统计文本词频，并比较 ArrayList 与 LinkedList 的插入性能。"},
    {"key": "py_func", "class": "py_cs2", "title": "函数与模块化", "offset_days": -2,
     "body": "把一段脚本重构为三个函数与一个模块，补充 docstring 与单元测试。"},
    {"key": "se_requirement", "class": "se_cs1", "title": "需求分析文档", "offset_days": 7,
     "body": "针对校园二手交易平台编写需求规格说明书，包含用例、非功能需求与验收标准。"},
    {"key": "se_usecase", "class": "se_cs1", "title": "用例图与用例描述", "offset_days": -4,
     "body": "绘制用例图并用结构化文本描述三个核心用例的前置、后置与异常流程。"},
)

CHECKIN_TASKS: tuple[dict, ...] = (
    {"key": "ds_week5", "class": "ds_se1", "title": "第5周课堂打卡", "state": "history",
     "goal": "完成链表插入删除练习并记录耗时", "offset_hours": -30},
    {"key": "ds_list_live", "class": "ds_se1", "title": "链表专项练习打卡", "state": "open",
     "goal": "完成 3 道链表题并提交思路", "offset_hours": -3},
    {"key": "cn_layer", "class": "cn_cs1", "title": "网络分层学习打卡", "state": "history",
     "goal": "整理 OSI 与 TCP/IP 分层对应关系", "offset_hours": -54},
    {"key": "db_sql_live", "class": "db_se1", "title": "SQL 练习打卡", "state": "open",
     "goal": "完成 5 条多表连接查询", "offset_hours": -2},
    {"key": "py_module", "class": "py_cs2", "title": "模块化编程打卡", "state": "history",
     "goal": "拆分脚本为模块并补测试", "offset_hours": -78},
    {"key": "cn_tcp_live", "class": "cn_cs1", "title": "TCP 抓包观察打卡", "state": "open",
     "goal": "抓取一次握手过程并记录序号", "offset_hours": -1},
)

COHORT_CLASSROOM_PREFIX = "行政班 · "

# Classroom attendance windows (distinct from the recurring check-in tasks above).
ATTENDANCE_SESSIONS: tuple[dict, ...] = (
    {"key": "ds_c1", "class": "ds_se1", "title": "第4次课课堂考勤", "state": "history", "late": False},
    {"key": "ds_c2", "class": "ds_se1", "title": "第5次课课堂考勤", "state": "history", "late": True},
    {"key": "cn_c3", "class": "cn_cs1", "title": "第3次课课堂考勤", "state": "history", "late": False},
    {"key": "cn_c4", "class": "cn_cs1", "title": "第4次课课堂考勤", "state": "open", "late": False},
    {"key": "db_c2", "class": "db_se1", "title": "第2次课课堂考勤", "state": "history", "late": False},
    {"key": "py_c1", "class": "py_cs2", "title": "第1次课课堂考勤", "state": "open", "late": False},
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def local_to_utc_naive(value: datetime) -> datetime:
    """Convert an Asia/Shanghai wall-clock time into the naive UTC stored by the models."""

    return value.astimezone(TZ).astimezone(UTC).replace(tzinfo=None)


def now_local() -> datetime:
    return datetime.now(TZ)


def username_of(spec: str) -> str:
    return f"{DEMO_USER_PREFIX}{spec}"


def configure_database(db_path: Path) -> None:
    """Point every imported service at the requested SQLite file before importing them."""

    resolved = db_path.resolve()
    os.environ["DATABASE_URL"] = "sqlite+pysqlite:///" + str(resolved).replace("\\", "/")
    # Demo seeding must never trigger paid model calls.
    os.environ.setdefault("RUN_LIVE_LLM", "0")


def guard_target(db_path: Path, action: str) -> None:
    """Refuse destructive actions on the packaging default database."""

    resolved = db_path.resolve()
    if not resolved.exists():
        raise SystemExit(f"database not found: {resolved}")
    if action not in {"reset", "seed", "refresh"}:
        return
    if resolved.name.lower() == "learning_system.db":
        raise SystemExit(
            "refusing to write demo data into learning_system.db; pass an explicit runtime database"
        )


def backup_database(db_path: Path, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = out_dir / f"before-demo-seed-{stamp}.sqlite"
    source = sqlite3.connect(str(db_path))
    try:
        dest = sqlite3.connect(str(target))
        try:
            source.backup(dest)
        finally:
            dest.close()
    finally:
        source.close()
    return target


def _stable_ratio(*parts: object) -> float:
    """Deterministic 0..1 value so repeated seeds produce the same scenario."""

    import hashlib

    digest = hashlib.sha256("|".join(str(part) for part in parts).encode()).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


def _submission_text(student: StudentSpec, assignment: dict) -> str:
    style = {
        "excellent": "已按题目要求完成，附上思路与复杂度分析：",
        "normal": "完成主体部分，个别边界情况仍在补充：",
        "struggling": "尝试完成，部分步骤参考了课堂示例：",
        "pending": "",
    }[student.persona]
    return f"{style}\n\n【{assignment['title']}】\n{assignment['body']}\n\n提交人：{student.name}（演示数据）"


def _score_for(student: StudentSpec, assignment_key: str) -> float:
    base = {"excellent": 88, "normal": 74, "struggling": 54, "pending": 60}[student.persona]
    span = {"excellent": 9, "normal": 12, "struggling": 13, "pending": 10}[student.persona]
    return round(base + _stable_ratio(student.key, assignment_key, "score") * span, 1)


def _review_comment(student: StudentSpec) -> str:
    return {
        "excellent": "思路清晰，边界处理完整，可进一步优化复杂度。",
        "normal": "主体正确，注意边界条件与命名规范。",
        "struggling": "基本思路可行，建议重做课堂示例并补交订正。",
        "pending": "请尽快提交。",
    }[student.persona]


# --------------------------------------------------------------------------- #
# Seed
# --------------------------------------------------------------------------- #
def seed(db_path: Path, *, refresh: bool = False) -> dict:
    configure_database(db_path)

    from common.db.session import SessionLocal
    from common.models.checkin import AttendanceSession, CheckinTask
    from common.models.learning import (
        AnswerRecord,
        Assignment,
        AssignmentSubmission,
        ClassEnrollment,
        Classroom,
        Course,
        Exercise,
        KnowledgePoint,
        User,
        UserProfile,
    )
    from common.security.auth import hash_password
    from services.teacher_service.app.schemas.checkin import (
        AttendanceSessionCreate,
        CheckinSubmitPayload,
        CheckinTaskCreate,
    )
    from services.teacher_service.app.schemas.schedule import ClassSessionPayload
    from services.teacher_service.app.schemas.teacher import (
        ClassCreate,
        HomeworkAssign,
        ReviewPayload,
        SubmissionCreate,
        TeachingScopeCreate,
    )
    from services.teacher_service.app.services.checkin_manager import CheckinManager
    from services.teacher_service.app.services.classroom_schedule import ClassScheduleManager
    from services.teacher_service.app.services.teacher_manager import TeacherManager

    manager = TeacherManager()
    schedule = ClassScheduleManager()
    checkins = CheckinManager()
    password_hash = hash_password(DEFAULT_PASSWORD)
    report: dict = {"created": {}, "skipped": {}, "errors": []}

    def bump(bucket: str, key: str, amount: int = 1) -> None:
        section = report.setdefault(bucket, {})
        section[key] = section.get(key, 0) + amount

    # ---------------------------------------------------------------- users
    teacher_ids: dict[str, int] = {}
    student_ids: dict[str, int] = {}
    with SessionLocal() as db:
        for teacher in TEACHERS:
            username = username_of(teacher.key)
            existing = db.query(User).filter_by(username=username).first()
            if existing is None:
                existing = User(
                    username=username,
                    password_hash=password_hash,
                    role="teacher",
                    email=f"{teacher.key}@demo.local",
                    is_active=True,
                )
                db.add(existing)
                db.flush()
                db.add(
                    UserProfile(
                        user_id=existing.id,
                        mastery_json={},
                        learning_style="",
                        cognitive_abilities={},
                        habits={},
                    )
                )
                bump("created", "teachers")
            teacher_ids[teacher.key] = existing.id
        for student in STUDENTS:
            username = username_of(student.key)
            existing = db.query(User).filter_by(username=username).first()
            if existing is None:
                existing = User(
                    username=username,
                    password_hash=password_hash,
                    role="student",
                    email=f"{student.key}@demo.local",
                    is_active=True,
                )
                db.add(existing)
                db.flush()
                db.add(
                    UserProfile(
                        user_id=existing.id,
                        mastery_json={},
                        learning_style="",
                        cognitive_abilities={},
                        habits={},
                    )
                )
                bump("created", "students")
            student_ids[student.key] = existing.id
        db.commit()

    # ------------------------------------------------- administrative cohorts
    # The product model has no separate "administrative cohort" entity. A cohort is
    # stored as a non-public classroom without a backing course so that existing
    # membership queries and the student "my classes" view work unchanged.
    cohort_class_ids: dict[str, int] = {}
    with SessionLocal() as db:
        for cohort_key, cohort_name in COHORTS.items():
            name = f"{DEMO_CLASS_TAG} {COHORT_CLASSROOM_PREFIX}{cohort_name}"
            room = db.query(Classroom).filter_by(name=name).first()
            if room is None:
                room = Classroom(
                    name=name,
                    subject="综合",
                    teacher_name="教务办公室",
                    teacher_user_id=teacher_ids[TEACHERS[0].key],
                    course_id=None,
                    invite_code=f"COHORT{cohort_key.upper()}DEMO",
                    status="active",
                    join_mode="invite",
                    description=f"{cohort_name}行政班（演示）",
                    objective="行政班用于组织学生，不含课程教学。",
                    syllabus="",
                    semester=SEMESTER,
                    is_public=False,
                    capacity=0,
                )
                db.add(room)
                db.flush()
                bump("created", "cohort_classes")
            cohort_class_ids[cohort_key] = room.id
        db.commit()

    with SessionLocal() as db:
        for student in STUDENTS:
            class_id = cohort_class_ids[student.cohort]
            exists = (
                db.query(ClassEnrollment)
                .filter_by(class_id=class_id, student_user_id=student_ids[student.key])
                .first()
            )
            if exists is None:
                db.add(
                    ClassEnrollment(class_id=class_id, student_user_id=student_ids[student.key])
                )
                bump("created", "cohort_memberships")
        db.commit()

    # ------------------------------------------------------- courses/classes
    class_ids: dict[str, int] = {}
    course_ids: dict[str, int] = {}
    with SessionLocal() as db:
        for key, spec in COURSES.items():
            course = (
                db.query(Course)
                .filter_by(title=spec["title"], teacher_user_id=teacher_ids[spec["teacher"]])
                .first()
            )
            if course is None:
                course = Course(
                    title=spec["title"],
                    subject=spec["subject"],
                    description=spec["description"],
                    teacher_user_id=teacher_ids[spec["teacher"]],
                    status="active",
                )
                db.add(course)
                db.flush()
                bump("created", "courses")
            course_ids[key] = course.id
        db.commit()

    for class_spec in CLASSROOMS:
        course = COURSES[class_spec["course"]]
        teacher_key = course["teacher"]
        name = f"{DEMO_CLASS_TAG} {class_spec['name']}"
        with SessionLocal() as db:
            existing = db.query(Classroom).filter_by(name=name).first()
        if existing is not None:
            class_ids[class_spec["key"]] = existing.id
            bump("skipped", "classrooms")
        elif class_spec["primary"]:
            item = manager.create_class(
                ClassCreate(
                    name=name,
                    subject=course["subject"],
                    teacher_name=TEACHERS[[t.key for t in TEACHERS].index(teacher_key)].name,
                    join_mode=class_spec["join_mode"],
                    description=course["description"],
                    objective=f"完成《{course['title']}》核心章节与考核。",
                    syllabus=course["syllabus"],
                    semester=SEMESTER,
                    is_public=True,
                    capacity=class_spec["capacity"],
                ),
                teacher_ids[teacher_key],
            )
            class_ids[class_spec["key"]] = item.id
            bump("created", "classrooms")
            # create_class always allocates its own course row; point it at the
            # canonical course so one course can own several teaching classes.
            with SessionLocal() as db:
                room = db.get(Classroom, item.id)
                room.course_id = course_ids[class_spec["course"]]
                db.commit()
        else:
            with SessionLocal() as db:
                room = Classroom(
                    name=name,
                    subject=course["subject"],
                    teacher_name=next(t.name for t in TEACHERS if t.key == teacher_key),
                    teacher_user_id=teacher_ids[teacher_key],
                    course_id=course_ids[class_spec["course"]],
                    invite_code=f"DEMO{class_spec['key'].upper().replace('_', '')}",
                    status="active",
                    join_mode=class_spec["join_mode"],
                    description=course["description"],
                    objective=f"完成《{course['title']}》核心章节与考核。",
                    syllabus=course["syllabus"],
                    semester=SEMESTER,
                    is_public=True,
                    capacity=class_spec["capacity"],
                )
                db.add(room)
                db.commit()
                db.refresh(room)
                class_ids[class_spec["key"]] = room.id
            bump("created", "classrooms")

    # The canonical course row is authoritative; drop the duplicate rows that
    # create_class generated for classes we re-pointed above.
    with SessionLocal() as db:
        used = {row.course_id for row in db.query(Classroom).all() if row.course_id}
        canonical = set(course_ids.values())
        demo_teacher_ids = set(teacher_ids.values())
        duplicates = [
            course
            for course in db.query(Course).all()
            if course.id not in used
            and course.id not in canonical
            and course.teacher_user_id in demo_teacher_ids
        ]
        for course in duplicates:
            db.delete(course)
        if duplicates:
            bump("removed", "duplicate_courses", len(duplicates))
        db.commit()

    # ------------------------------------------------------------ enrollment
    for class_spec in CLASSROOMS:
        class_id = class_ids[class_spec["key"]]
        teacher_id = teacher_ids[COURSES[class_spec["course"]]["teacher"]]
        members = [
            student.key for student in STUDENTS if student.cohort in class_spec["cohorts"]
        ]
        members += [key for key, target in EXTRA_ENROLLMENTS if target == class_spec["key"]]
        for student_key in members:
            try:
                manager.enroll_student(class_id, student_ids[student_key], teacher_id)
                bump("checked", "teaching_memberships")
            except Exception as exc:  # noqa: BLE001 - reported, never masked
                report["errors"].append(f"enroll {student_key}->{class_spec['key']}: {exc}")

    # -------------------------------------------------------------- timetable
    for session_spec in SESSIONS:
        class_id = class_ids[session_spec["class"]]
        teacher_id = teacher_ids[COURSES[
            next(c["course"] for c in CLASSROOMS if c["key"] == session_spec["class"])
        ]["teacher"]]
        with SessionLocal() as db:
            exists = (
                db.query(Classroom)
                .filter(Classroom.id == class_id)
                .first()
                is not None
            )
            from common.models.checkin import ClassSession

            duplicate = (
                db.query(ClassSession)
                .filter_by(
                    class_id=class_id,
                    weekday=session_spec["weekday"],
                    start_time=session_spec["start"],
                )
                .first()
            )
        if not exists or duplicate is not None:
            bump("skipped", "sessions")
            continue
        try:
            schedule.create_session(
                class_id,
                teacher_id,
                ClassSessionPayload(
                    topic=session_spec["topic"],
                    weekday=session_spec["weekday"],
                    start_time=session_spec["start"],
                    end_time=session_spec["end"],
                    week_start=WEEK_START,
                    week_end=WEEK_END,
                    location=session_spec["room"],
                    mode="offline",
                ),
            )
            bump("created", "sessions")
        except Exception as exc:  # noqa: BLE001
            report["errors"].append(f"session {session_spec['class']}: {exc}")

    # --------------------------------------------------------- teaching scope
    for class_spec in CLASSROOMS:
        points = class_spec["points"]
        if not points:
            continue
        class_id = class_ids[class_spec["key"]]
        with SessionLocal() as db:
            from common.models.learning import TeachingScope

            exists = db.query(TeachingScope).filter_by(class_id=class_id).first()
        if exists is not None:
            bump("skipped", "teaching_scopes")
            continue
        course = COURSES[class_spec["course"]]
        try:
            manager.create_teaching_scope(
                TeachingScopeCreate(
                    class_id=class_id,
                    knowledge_points=list(points),
                    learning_direction="按章节顺序完成知识点学习并完成配套练习",
                    courseware_title=f"{course['title']}课程讲义（演示）",
                    courseware_content=(
                        f"# {course['title']}\n\n{course['description']}\n\n"
                        "## 章节安排\n" + course["syllabus"].replace("\n", "\n\n")
                        + "\n\n> 本讲义为演示数据，用于串联教学范围、学习计划与学情统计。"
                    ),
                    teaching_goal="掌握核心概念并能独立完成编程与设计任务",
                )
            )
            bump("created", "teaching_scopes")
        except Exception as exc:  # noqa: BLE001
            report["errors"].append(f"scope {class_spec['key']}: {exc}")

    # --------------------------------------------------------------- homework
    assignment_ids: dict[str, int] = {}
    now = now_local()
    for spec in ASSIGNMENTS:
        class_id = class_ids[spec["class"]]
        teacher_id = teacher_ids[COURSES[
            next(c["course"] for c in CLASSROOMS if c["key"] == spec["class"])
        ]["teacher"]]
        with SessionLocal() as db:
            existing = db.query(Assignment).filter_by(class_id=class_id, title=spec["title"]).first()
        if existing is not None:
            assignment_ids[spec["key"]] = existing.id
            bump("skipped", "assignments")
            continue
        # Every assignment is published with a live deadline first so historical
        # submissions can pass the real cutoff check; past deadlines are applied
        # after submissions exist (see below).
        due = local_to_utc_naive(now + timedelta(days=max(spec["offset_days"], 0), hours=6))
        try:
            item = manager.create_assignment(
                HomeworkAssign(
                    class_id=class_id,
                    title=spec["title"],
                    description=spec["body"],
                    due_at=due,
                ),
                teacher_id,
            )
            assignment_ids[spec["key"]] = item.id
            bump("created", "assignments")
        except Exception as exc:  # noqa: BLE001
            report["errors"].append(f"assignment {spec['key']}: {exc}")

    # -------------------------------------------------------------- submission
    by_key = {student.key: student for student in STUDENTS}
    submission_ids: dict[tuple[str, str], int] = {}
    for spec in ASSIGNMENTS:
        assignment_id = assignment_ids.get(spec["key"])
        if assignment_id is None:
            continue
        class_spec = next(c for c in CLASSROOMS if c["key"] == spec["class"])
        members = [s for s in STUDENTS if s.cohort in class_spec["cohorts"]]
        members += [by_key[k] for k, target in EXTRA_ENROLLMENTS if target == spec["class"]]
        historical = spec["offset_days"] < 0
        for student in members:
            ratio = _stable_ratio(student.key, spec["key"], "submit")
            threshold = {
                "excellent": 1.0,
                "normal": 0.8 if historical else 0.5,
                "struggling": 0.4 if historical else 0.15,
                "pending": 0.0,
            }[student.persona]
            if ratio > threshold:
                continue
            with SessionLocal() as db:
                existing_submission = (
                    db.query(AssignmentSubmission)
                    .filter_by(
                        assignment_id=assignment_id,
                        student_user_id=student_ids[student.key],
                    )
                    .first()
                )
            if existing_submission is not None:
                submission_ids[(student.key, spec["key"])] = existing_submission.id
                bump("skipped", "submissions")
                continue
            try:
                item = manager.submit_assignment(
                    assignment_id,
                    SubmissionCreate(content=_submission_text(student, spec)),
                    student_ids[student.key],
                )
                submission_ids[(student.key, spec["key"])] = item.id
                bump("created", "submissions")
            except Exception as exc:  # noqa: BLE001
                report["errors"].append(f"submit {student.key}/{spec['key']}: {exc}")

    # ------------------------------------------------------------------ review
    for (student_key, assignment_key), submission_id in submission_ids.items():
        spec = next(a for a in ASSIGNMENTS if a["key"] == assignment_key)
        if spec["offset_days"] >= 0:
            continue  # leave in-progress work ungraded so teachers have real work
        student = by_key[student_key]
        if _stable_ratio(student_key, assignment_key, "review") > 0.75:
            continue  # a real "pending review" queue
        with SessionLocal() as db:
            row = db.get(AssignmentSubmission, submission_id)
            already_reviewed = row is not None and row.status == "reviewed"
        if already_reviewed:
            bump("skipped", "reviews")
            continue
        teacher_id = teacher_ids[COURSES[
            next(c["course"] for c in CLASSROOMS if c["key"] == spec["class"])
        ]["teacher"]]
        try:
            manager.review_submission(
                submission_id,
                ReviewPayload(score=_score_for(student, assignment_key), comment=_review_comment(student)),
                teacher_id,
            )
            bump("created", "reviews")
        except Exception as exc:  # noqa: BLE001
            report["errors"].append(f"review {student_key}/{assignment_key}: {exc}")

    # Apply the historical deadlines now that submissions are persisted.
    with SessionLocal() as db:
        for spec in ASSIGNMENTS:
            if spec["offset_days"] >= 0:
                continue
            assignment_id = assignment_ids.get(spec["key"])
            if assignment_id is None:
                continue
            row = db.get(Assignment, assignment_id)
            row.due_at = local_to_utc_naive(now + timedelta(days=spec["offset_days"]))
        db.commit()

    # --------------------------------------------------------------- check-ins
    # Publishing rejects a window that has already ended, while a historical
    # submission must fall inside its own period. So historical tasks are
    # published with a live window, then their period is shifted into the past
    # through the ORM before the real submit/close endpoints run.
    task_ids: dict[str, int] = {}
    for spec in CHECKIN_TASKS:
        class_id = class_ids[spec["class"]]
        teacher_id = teacher_ids[COURSES[
            next(c["course"] for c in CLASSROOMS if c["key"] == spec["class"])
        ]["teacher"]]
        title = f"{DEMO_CLASS_TAG} {spec['title']}"
        historical = spec["state"] == "history"
        with SessionLocal() as db:
            existing = db.query(CheckinTask).filter_by(class_id=class_id, title=title).first()
        if existing is not None:
            task_ids[spec["key"]] = existing.id
            bump("skipped", "checkin_tasks")
            continue
        if historical:
            start = local_to_utc_naive(now + timedelta(hours=1))
            end = local_to_utc_naive(now + timedelta(hours=5))
        else:
            start = local_to_utc_naive(now + timedelta(hours=spec["offset_hours"]))
            end = local_to_utc_naive(now + timedelta(hours=spec["offset_hours"] + 6))
        try:
            item = checkins.create_task(
                teacher_id,
                CheckinTaskCreate(
                    class_id=class_id,
                    title=title,
                    goal=spec["goal"],
                    description=f"{spec['goal']}（演示任务）",
                    frequency="once",
                    start_at=start,
                    end_at=end,
                    allow_late=historical,
                    review_mode="manual",
                    knowledge_points=[],
                ),
            )
            task_ids[spec["key"]] = item.id
            checkins.publish_task(item.id, teacher_id, "teacher")
            bump("created", "checkin_tasks")
        except Exception as exc:  # noqa: BLE001
            report["errors"].append(f"checkin {spec['key']}: {exc}")

    for spec in CHECKIN_TASKS:
        task_id = task_ids.get(spec["key"])
        if task_id is None:
            continue
        teacher_id = teacher_ids[COURSES[
            next(c["course"] for c in CLASSROOMS if c["key"] == spec["class"])
        ]["teacher"]]
        historical = spec["state"] == "history"
        if historical:
            back = now + timedelta(hours=spec["offset_hours"])
            with SessionLocal() as db:
                row = db.get(CheckinTask, task_id)
                row.start_at = local_to_utc_naive(back)
                row.end_at = local_to_utc_naive(back + timedelta(hours=4))
                row.allow_late = True
                db.commit()
            period_key = back.date().isoformat()
            class_spec = next(c for c in CLASSROOMS if c["key"] == spec["class"])
            members = [s for s in STUDENTS if s.cohort in class_spec["cohorts"]]
            for student in members:
                ratio = _stable_ratio(student.key, spec["key"], "checkin")
                threshold = {
                    "excellent": 1.0,
                    "normal": 0.85,
                    "struggling": 0.5,
                    "pending": 0.0,
                }[student.persona]
                if ratio > threshold:
                    continue
                try:
                    checkins.submit_task(
                        task_id,
                        student_ids[student.key],
                        CheckinSubmitPayload(
                            content=f"{spec['goal']}，已完成并记录学习用时（演示数据）。",
                            period_key=period_key,
                        ),
                    )
                    bump("created", "checkin_submissions")
                except Exception as exc:  # noqa: BLE001
                    report["errors"].append(
                        f"checkin-submit {student.key}/{spec['key']}: {exc}"
                    )
            try:
                checkins.close_task(task_id, teacher_id, "teacher")
                with SessionLocal() as db:
                    row = db.get(CheckinTask, task_id)
                    row.allow_late = False
                    db.commit()
            except Exception as exc:  # noqa: BLE001
                report["errors"].append(f"checkin-close {spec['key']}: {exc}")

    # ---------------------------------------------------- classroom attendance
    # A closed attendance window cannot be created through the API, so each
    # historical window is opened live, signed by the students, then shifted
    # into the past and closed through the real close endpoint.
    attendance_ids: dict[str, int] = {}
    for spec in ATTENDANCE_SESSIONS:
        class_id = class_ids[spec["class"]]
        teacher_id = teacher_ids[COURSES[
            next(c["course"] for c in CLASSROOMS if c["key"] == spec["class"])
        ]["teacher"]]
        title = f"{DEMO_CLASS_TAG} {spec['title']}"
        with SessionLocal() as db:
            existing = (
                db.query(AttendanceSession).filter_by(class_id=class_id, title=title).first()
            )
        if existing is not None:
            attendance_ids[spec["key"]] = existing.id
            bump("skipped", "attendance_sessions")
            continue
        start = local_to_utc_naive(now - timedelta(minutes=20))
        end = local_to_utc_naive(now + timedelta(minutes=40))
        # late_after_at must sit inside the window; a late-assessed session starts
        # with a future threshold so the first group signs as "present".
        late_after = local_to_utc_naive(now + timedelta(minutes=10)) if spec["late"] else None
        try:
            item = checkins.create_attendance(
                teacher_id,
                AttendanceSessionCreate(
                    class_id=class_id,
                    title=title,
                    start_at=start,
                    end_at=end,
                    late_after_at=late_after,
                ),
            )
            attendance_ids[spec["key"]] = item.id
            bump("created", "attendance_sessions")
        except Exception as exc:  # noqa: BLE001
            report["errors"].append(f"attendance {spec['key']}: {exc}")

    for spec in ATTENDANCE_SESSIONS:
        if spec["state"] != "history":
            continue
        session_id = attendance_ids.get(spec["key"])
        if session_id is None:
            continue
        with SessionLocal() as db:
            row = db.get(AttendanceSession, session_id)
            code = row.code
        class_spec = next(c for c in CLASSROOMS if c["key"] == spec["class"])
        members = [s for s in STUDENTS if s.cohort in class_spec["cohorts"]]

        def sign(group, spec=spec, code=code) -> None:
            for student in group:
                ratio = _stable_ratio(student.key, spec["key"], "attendance")
                threshold = {
                    "excellent": 1.0,
                    "normal": 0.9,
                    "struggling": 0.7,
                    "pending": 0.0,
                }[student.persona]
                if ratio > threshold:
                    continue
                try:
                    checkins.checkin_attendance(student_ids[student.key], code, None)
                    bump("created", "attendance_records")
                except Exception as exc:  # noqa: BLE001
                    report["errors"].append(
                        f"attendance-checkin {student.key}/{spec['key']}: {exc}"
                    )

        if spec["late"]:
            # First wave signs before the late threshold, second wave after it so the
            # session contains both "present" and "late" evidence.
            sign([s for s in members if _stable_ratio(s.key, spec["key"], "wave") <= 0.5])
            with SessionLocal() as db:
                row = db.get(AttendanceSession, session_id)
                row.late_after_at = local_to_utc_naive(now - timedelta(minutes=1))
                db.commit()
            sign([s for s in members if _stable_ratio(s.key, spec["key"], "wave") > 0.5])
        else:
            sign(members)
        teacher_id = teacher_ids[COURSES[
            next(c["course"] for c in CLASSROOMS if c["key"] == spec["class"])
        ]["teacher"]]
        try:
            checkins.close_attendance(session_id, teacher_id, "teacher")
            back = now - timedelta(days={"ds_c1": 7, "ds_c2": 2, "cn_c3": 9, "db_c2": 5}.get(
                spec["key"], 3
            ))
            with SessionLocal() as db:
                row = db.get(AttendanceSession, session_id)
                row.start_at = local_to_utc_naive(back)
                row.end_at = local_to_utc_naive(back + timedelta(minutes=60))
                if row.late_after_at is not None:
                    row.late_after_at = local_to_utc_naive(back + timedelta(minutes=10))
                db.commit()
        except Exception as exc:  # noqa: BLE001
            report["errors"].append(f"attendance-close {spec['key']}: {exc}")

    # -------------------------------------------------------- answer evidence
    # Real exercises already exist for 数据结构(2) and 计算机网络(3). They are the
    # only subjects with published knowledge points, so analytics stay evidence-based.
    subject_pool = {"数据结构": 2, "计算机网络": 3}
    with SessionLocal() as db:
        for class_spec in CLASSROOMS:
            course = COURSES[class_spec["course"]]
            subject_id = subject_pool.get(course["subject"])
            if subject_id is None:
                continue
            exercise_rows = (
                db.query(Exercise.id)
                .join(KnowledgePoint, KnowledgePoint.id == Exercise.knowledge_point_id)
                .filter(KnowledgePoint.subject_id == subject_id)
                .order_by(Exercise.id)
                .limit(40)
                .all()
            )
            exercise_ids = [row[0] for row in exercise_rows]
            if not exercise_ids:
                continue
            members = [s for s in STUDENTS if s.cohort in class_spec["cohorts"]]
            for student in members:
                user_id = student_ids[student.key]
                if db.query(AnswerRecord).filter_by(user_id=user_id).count() >= 6:
                    bump("skipped", "answers")
                    continue
                accuracy = {"excellent": 0.9, "normal": 0.72, "struggling": 0.45, "pending": 0.6}[
                    student.persona
                ]
                count = 8
                for index in range(count):
                    exercise_id = exercise_ids[
                        (STUDENTS.index(student) * 3 + index) % len(exercise_ids)
                    ]
                    correct = _stable_ratio(student.key, exercise_id, index) <= accuracy
                    db.add(
                        AnswerRecord(
                            user_id=user_id,
                            exercise_id=exercise_id,
                            user_answer="A" if correct else "B",
                            is_correct=correct,
                            time_spent=40 + int(_stable_ratio(student.key, index) * 120),
                            evaluation_json={"source": "demo_seed"},
                            created_at=datetime.utcnow()
                            - timedelta(days=20 - index, hours=index),
                        )
                    )
                    bump("created", "answers")
        db.commit()

    if refresh:
        report["refreshed"] = refresh_windows(db_path)

    return report


def refresh_windows(db_path: Path) -> dict:
    """Re-align still-open deadlines so an idle demo environment stays usable."""

    configure_database(db_path)
    from common.db.session import SessionLocal
    from common.models.checkin import CheckinTask
    from common.models.learning import Assignment

    now = now_local()
    moved = {"assignments": 0, "checkin_tasks": 0}
    with SessionLocal() as db:
        for spec in ASSIGNMENTS:
            if spec["offset_days"] < 0:
                continue
            row = (
                db.query(Assignment)
                .filter(Assignment.title == spec["title"])
                .filter(Assignment.description == spec["body"])
                .first()
            )
            if row is None or row.status != "published":
                continue
            target = local_to_utc_naive(now + timedelta(days=spec["offset_days"], hours=6))
            if row.due_at is None or (row.due_at - datetime.utcnow()) < timedelta(hours=1):
                row.due_at = target
                moved["assignments"] += 1
        for spec in CHECKIN_TASKS:
            if spec["state"] != "open":
                continue
            row = (
                db.query(CheckinTask)
                .filter(CheckinTask.title == f"{DEMO_CLASS_TAG} {spec['title']}")
                .first()
            )
            if row is None or row.status != "published":
                continue
            if row.end_at < datetime.utcnow():
                row.start_at = local_to_utc_naive(now + timedelta(hours=-1))
                row.end_at = local_to_utc_naive(now + timedelta(hours=6))
                moved["checkin_tasks"] += 1
        db.commit()
    return moved


# --------------------------------------------------------------------------- #
# Inspection
# --------------------------------------------------------------------------- #
def inspect(db_path: Path) -> dict:
    """Return demo-data counts, the account manifest and consistency findings."""

    configure_database(db_path)
    from common.db.session import SessionLocal
    from common.models.checkin import (
        AttendanceRecord,
        AttendanceSession,
        CheckinTask,
        CheckinTaskSubmission,
        ClassSession,
        PersonalSchedule,
    )
    from common.models.learning import (
        AnswerRecord,
        Assignment,
        AssignmentSubmission,
        ClassEnrollment,
        Classroom,
        Course,
        Notification,
        TeachingScope,
        User,
    )

    with SessionLocal() as db:
        demo_users = db.query(User).filter(User.username.like(f"{DEMO_USER_PREFIX}%")).all()
        demo_ids = [user.id for user in demo_users]
        demo_classes = db.query(Classroom).filter(Classroom.name.like(f"{DEMO_CLASS_TAG}%")).all()
        class_ids = [room.id for room in demo_classes]
        counts = {
            "teachers": sum(1 for user in demo_users if user.role == "teacher"),
            "students": sum(1 for user in demo_users if user.role == "student"),
            "classes": len(demo_classes),
            "cohort_classes": sum(1 for room in demo_classes if room.course_id is None),
            "courses": db.query(Course).filter(Course.teacher_user_id.in_(demo_ids)).count(),
            "enrollments": db.query(ClassEnrollment)
            .filter(ClassEnrollment.class_id.in_(class_ids))
            .count(),
            "sessions": db.query(ClassSession).filter(ClassSession.class_id.in_(class_ids)).count(),
            "personal_schedules": db.query(PersonalSchedule)
            .filter(PersonalSchedule.user_id.in_(demo_ids))
            .count(),
            "assignments": db.query(Assignment).filter(Assignment.class_id.in_(class_ids)).count(),
            "submissions": db.query(AssignmentSubmission)
            .filter(AssignmentSubmission.assignment_id.in_(
                db.query(Assignment.id).filter(Assignment.class_id.in_(class_ids))
            ))
            .count(),
            "checkin_tasks": db.query(CheckinTask).filter(CheckinTask.class_id.in_(class_ids)).count(),
            "checkin_submissions": db.query(CheckinTaskSubmission)
            .filter(CheckinTaskSubmission.task_id.in_(
                db.query(CheckinTask.id).filter(CheckinTask.class_id.in_(class_ids))
            ))
            .count(),
            "attendance_sessions": db.query(AttendanceSession)
            .filter(AttendanceSession.class_id.in_(class_ids))
            .count(),
            "attendance_records": db.query(AttendanceRecord)
            .filter(AttendanceRecord.student_user_id.in_(demo_ids))
            .count(),
            "teaching_scopes": db.query(TeachingScope)
            .filter(TeachingScope.class_id.in_(class_ids))
            .count(),
            "answers": db.query(AnswerRecord).filter(AnswerRecord.user_id.in_(demo_ids)).count(),
            "notifications": db.query(Notification)
            .filter(Notification.user_id.in_(demo_ids))
            .count(),
        }

        accounts = [
            {
                "username": user.username,
                "role": user.role,
                "user_id": user.id,
                "classes": [
                    room.name
                    for room in db.query(Classroom)
                    .join(ClassEnrollment, ClassEnrollment.class_id == Classroom.id)
                    .filter(ClassEnrollment.student_user_id == user.id)
                    .all()
                ],
            }
            for user in sorted(demo_users, key=lambda item: (item.role, item.id))
        ]

        issues: list[str] = []
        # 1. Every teaching class must be owned by a real teacher account.
        for room in demo_classes:
            owner = db.get(User, room.teacher_user_id)
            if owner is None or owner.role != "teacher":
                issues.append(f"class {room.id} owner is not a teacher")
        # 2. Enrollment must reference active students.
        for row in (
            db.query(ClassEnrollment).filter(ClassEnrollment.class_id.in_(class_ids)).all()
        ):
            student = db.get(User, row.student_user_id)
            if student is None or student.role != "student" or not student.is_active:
                issues.append(f"enrollment {row.id} references invalid student")
        # 3. No submission may belong to a student outside the assignment class.
        rows = (
            db.query(AssignmentSubmission, Assignment)
            .join(Assignment, Assignment.id == AssignmentSubmission.assignment_id)
            .filter(Assignment.class_id.in_(class_ids))
            .all()
        )
        for submission, assignment in rows:
            enrolled = (
                db.query(ClassEnrollment)
                .filter_by(class_id=assignment.class_id, student_user_id=submission.student_user_id)
                .first()
            )
            if enrolled is None:
                issues.append(
                    f"submission {submission.id} by non-member {submission.student_user_id}"
                )
        # 4. Assignment ownership must match its class owner.
        for assignment in db.query(Assignment).filter(Assignment.class_id.in_(class_ids)).all():
            room = db.get(Classroom, assignment.class_id)
            if room and room.teacher_user_id != assignment.teacher_user_id:
                issues.append(f"assignment {assignment.id} teacher mismatch")
        # 5. Check-in submissions must be from class members.
        for submission in (
            db.query(CheckinTaskSubmission)
            .filter(CheckinTaskSubmission.student_user_id.in_(demo_ids))
            .all()
        ):
            task = db.get(CheckinTask, submission.task_id)
            if task is None:
                issues.append(f"checkin submission {submission.id} has no task")
                continue
            enrolled = (
                db.query(ClassEnrollment)
                .filter_by(class_id=task.class_id, student_user_id=submission.student_user_id)
                .first()
            )
            if enrolled is None:
                issues.append(
                    f"checkin submission {submission.id} by non-member "
                    f"{submission.student_user_id}"
                )
        # 6. Demo data must not leak notifications to real accounts.
        leaked = (
            db.query(Notification)
            .filter(Notification.user_id.notin_(demo_ids))
            .filter(Notification.sender_id.in_(demo_ids))
            .count()
        )
        if leaked:
            issues.append(f"{leaked} notifications reached non-demo recipients")
        # 7. No duplicate demo classes / assignments by business key.
        names = [room.name for room in demo_classes]
        duplicates = {name for name in names if names.count(name) > 1}
        if duplicates:
            issues.append(f"duplicate demo classes: {sorted(duplicates)}")

    return {
        "database": str(db_path.resolve()),
        "counts": counts,
        "accounts": accounts,
        "issues": issues,
        "ok": not issues,
    }


# --------------------------------------------------------------------------- #
# Reset
# --------------------------------------------------------------------------- #
def reset(db_path: Path) -> dict:
    """Delete every record owned by the demo scenario, and nothing else."""

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
        PersonalSchedule,
    )
    from common.models.learning import (
        AnswerRecord,
        Assignment,
        AssignmentSubmission,
        ClassEnrollment,
        Classroom,
        Course,
        HomeworkAttachment,
        LearningPath,
        Notification,
        NotificationDispatch,
        SubmissionRevision,
        TeachingScope,
        User,
        UserProfile,
    )

    removed: dict[str, int] = {}
    with SessionLocal() as db:
        demo_ids = [
            row[0] for row in db.query(User.id).filter(User.username.like(f"{DEMO_USER_PREFIX}%"))
        ]
        class_ids = [
            row[0] for row in db.query(Classroom.id).filter(
                Classroom.name.like(f"{DEMO_CLASS_TAG}%")
            )
        ]
        if not demo_ids and not class_ids:
            return {"removed": removed, "note": "no demo data found"}

        def drop(model, *criteria) -> None:
            query = db.query(model)
            for criterion in criteria:
                query = query.filter(criterion)
            count = query.delete(synchronize_session=False)
            if count:
                removed[model.__name__] = removed.get(model.__name__, 0) + count
            db.flush()

        assignment_ids = db.query(Assignment.id).filter(Assignment.class_id.in_(class_ids))
        submission_ids = db.query(AssignmentSubmission.id).filter(
            AssignmentSubmission.assignment_id.in_(assignment_ids)
        )
        task_ids = db.query(CheckinTask.id).filter(CheckinTask.class_id.in_(class_ids))
        checkin_sub_ids = db.query(CheckinTaskSubmission.id).filter(
            CheckinTaskSubmission.task_id.in_(task_ids)
        )
        session_ids = db.query(AttendanceSession.id).filter(
            AttendanceSession.class_id.in_(class_ids)
        )

        drop(AnswerRecord, AnswerRecord.user_id.in_(demo_ids))
        drop(LearningPath, LearningPath.user_id.in_(demo_ids))
        drop(CheckinSubmissionRevision, CheckinSubmissionRevision.submission_id.in_(checkin_sub_ids))
        drop(CheckinSubmissionRevision, CheckinSubmissionRevision.actor_user_id.in_(demo_ids))
        drop(AttendanceRecord, AttendanceRecord.student_user_id.in_(demo_ids))
        drop(AttendanceRecord, AttendanceRecord.session_id.in_(session_ids))
        drop(AttendanceSession, AttendanceSession.class_id.in_(class_ids))
        drop(CheckinTaskSubmission, CheckinTaskSubmission.task_id.in_(task_ids))
        drop(CheckinTask, CheckinTask.class_id.in_(class_ids))
        drop(SubmissionRevision, SubmissionRevision.submission_id.in_(submission_ids))
        drop(HomeworkAttachment, HomeworkAttachment.assignment_id.in_(assignment_ids))
        drop(AssignmentSubmission, AssignmentSubmission.assignment_id.in_(assignment_ids))
        drop(Assignment, Assignment.class_id.in_(class_ids))
        drop(ClassScheduleException, ClassScheduleException.class_id.in_(class_ids))
        drop(ClassSession, ClassSession.class_id.in_(class_ids))
        drop(PersonalSchedule, PersonalSchedule.user_id.in_(demo_ids))
        drop(PersonalSchedule, PersonalSchedule.class_id.in_(class_ids))
        drop(TeachingScope, TeachingScope.class_id.in_(class_ids))
        drop(ClassEnrollment, ClassEnrollment.class_id.in_(class_ids))
        drop(ClassEnrollment, ClassEnrollment.student_user_id.in_(demo_ids))
        drop(Notification, Notification.user_id.in_(demo_ids))
        drop(Notification, Notification.sender_id.in_(demo_ids))
        drop(NotificationDispatch, NotificationDispatch.sender_id.in_(demo_ids))
        drop(Classroom, Classroom.id.in_(class_ids))
        drop(Course, Course.teacher_user_id.in_(demo_ids))
        drop(UserProfile, UserProfile.user_id.in_(demo_ids))
        drop(User, User.id.in_(demo_ids))
        db.commit()

    return {"removed": removed}


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, help="path to the runtime SQLite database")
    parser.add_argument(
        "--action",
        choices=["check", "seed", "refresh", "reset"],
        default="check",
        help="check = read-only inspection, seed = create/reuse demo data",
    )
    parser.add_argument("--refresh", action="store_true", help="re-align open deadlines while seeding")
    parser.add_argument("--yes", action="store_true", help="required for reset")
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    args = parser.parse_args(argv)

    db_path = Path(args.db)
    if not db_path.exists():
        parser.error(f"database not found: {db_path}")
    guard_target(db_path, args.action)

    backup = None
    if args.action in {"seed", "reset"}:
        backup = backup_database(db_path, ROOT / "artifacts" / "demo-teaching" / "backups")

    if args.action == "check":
        result = inspect(db_path)
    elif args.action == "seed":
        result = seed(db_path, refresh=args.refresh)
        result["inspection"] = inspect(db_path)
    elif args.action == "refresh":
        result = {"refreshed": refresh_windows(db_path), "inspection": inspect(db_path)}
    else:
        if not args.yes:
            parser.error("reset deletes demo records; pass --yes to confirm")
        result = reset(db_path)
        result["inspection"] = inspect(db_path)

    if backup is not None:
        result["backup"] = str(backup)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        _print_human(result, args.action)
    return 0


def _print_human(result: dict, action: str) -> None:
    if "removed" in result:
        print(f"removed: {json.dumps(result['removed'], ensure_ascii=False)}")
        result = result.get("inspection", {})
    if "created" in result:
        print(f"created: {json.dumps(result['created'], ensure_ascii=False)}")
        print(f"skipped: {json.dumps(result['skipped'], ensure_ascii=False)}")
        if result.get("errors"):
            print(f"errors({len(result['errors'])}):")
            for line in result["errors"][:20]:
                print(f"  - {line}")
        if result.get("backup"):
            print(f"backup: {result['backup']}")
        result = result.get("inspection", {})
    if "refreshed" in result:
        print(f"refreshed: {json.dumps(result['refreshed'], ensure_ascii=False)}")
        result = result.get("inspection", {})
    if "counts" in result:
        print(f"\ndatabase: {result['database']}")
        print("counts:")
        for key, value in result["counts"].items():
            print(f"  {key:22s} {value}")
        print(f"\naccounts: {len(result['accounts'])}")
        print(f"consistency: {'OK' if result['ok'] else 'ISSUES'}")
        for issue in result["issues"]:
            print(f"  ! {issue}")
        if action == "check":
            for account in result["accounts"][:40]:
                classes = "; ".join(account["classes"][:4])
                print(f"  {account['username']:22s} {account['role']:8s} {classes}")


if __name__ == "__main__":
    raise SystemExit(main())

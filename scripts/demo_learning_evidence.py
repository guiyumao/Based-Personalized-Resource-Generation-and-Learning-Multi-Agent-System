"""Prepare the demo question bank + teaching scope, nothing else.

This script deliberately does **not** write any answer records. Demo 学情 must be
produced by real students answering through ``POST /evaluation/submit`` where the
service compares ``user_answer`` against the stored standard answer. See
``scripts/demo_role_use_cases.py`` for the role-driven part.

Why this script exists at all
-----------------------------
The public question bank rows carry ``content.generated_for_user_id`` (they were
generated for a real user) and therefore every other learner's answer to them is
dropped by ``common.learning_evidence.load_evidence``. Cloning them **without**
that attribution gives the demo cohort a public, reusable question set.

Only objective question types are cloned — ``short_answer`` / ``code`` /
``programming`` are graded by an LLM, and the demonstration must stay at zero
model calls.

    python scripts/demo_learning_evidence.py --db artifacts/local-start-20261019/runtime.sqlite
    python scripts/demo_learning_evidence.py --db <db> --json --per-point 20
    python scripts/demo_learning_evidence.py --db <db> --reset
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEMO_CLASS_TAG = "[DEMO]"
CLONE_KEY_PREFIX = "demo-evidence-"
# Objective-only: these are graded by string comparison inside ReportService.
OBJECTIVE_TYPES = ("choice", "judge", "blank", "fill")
DEFAULT_PER_POINT = 20


@dataclass(frozen=True)
class DemoQuestion:
    """A public demo question the role use cases may answer over HTTP."""

    id: int
    knowledge_point: str
    type: str
    difficulty: int
    answer: str
    options: list[str]
    prompt: str


def build_question_bank(db_path: Path, per_point: int = DEFAULT_PER_POINT) -> dict:
    """Clone public objective questions (idempotent) and align teaching scopes.

    Returns a report with a flat ``questions`` list consumable by
    ``scripts/demo_role_use_cases.py``.
    """

    from scripts.demo_teaching_dataset import configure_database

    configure_database(db_path)

    from common.db.session import SessionLocal
    from common.models.learning import (
        Classroom,
        Exercise,
        KnowledgePoint,
        SystemSubject,
        TeachingScope,
    )

    report: dict = {
        "created_clones": 0,
        "updated_scopes": 0,
        "created_scopes": 0,
        "questions": [],
        "classes": [],
        "skipped": [],
    }

    with SessionLocal() as db:
        classrooms = (
            db.query(Classroom)
            .filter(Classroom.name.like(f"{DEMO_CLASS_TAG}%"), Classroom.course_id.isnot(None))
            .order_by(Classroom.id)
            .all()
        )
        clone_cache: dict[int, list[Exercise]] = {}

        for room in classrooms:
            subject = db.query(SystemSubject).filter(SystemSubject.name == room.subject).first()
            if subject is None:
                report["skipped"].append(
                    {"class": room.name, "reason": f"学科「{room.subject}」不在学科目录"}
                )
                continue
            points = (
                db.query(KnowledgePoint)
                .join(Exercise, Exercise.knowledge_point_id == KnowledgePoint.id)
                .filter(KnowledgePoint.subject_id == subject.id)
                .distinct()
                .order_by(KnowledgePoint.id)
                .all()
            )
            if not points:
                report["skipped"].append(
                    {
                        "class": room.name,
                        "reason": f"学科「{room.subject}」公共题库无可用题目，不伪造学情",
                    }
                )
                continue

            clones: list[Exercise] = []
            for point in points:
                cached = clone_cache.get(point.id)
                if cached is None:
                    cached = []
                    # Public rows first (no ownership), then attributed ones that we
                    # re-publish without ownership. Objective types only.
                    unattributed = (
                        db.query(Exercise)
                        .filter(
                            Exercise.knowledge_point_id == point.id,
                            Exercise.type.in_(OBJECTIVE_TYPES),
                        )
                        .filter(
                            (Exercise.content.is_(None))
                            | (~Exercise.content.like("%generated_for_user_id%"))
                        )
                        .order_by(Exercise.id)
                        .limit(per_point)
                        .all()
                    )
                    sources = list(unattributed)
                    if len(sources) < per_point:
                        extra = (
                            db.query(Exercise)
                            .filter(
                                Exercise.knowledge_point_id == point.id,
                                Exercise.type.in_(OBJECTIVE_TYPES),
                                Exercise.content.like("%generated_for_user_id%"),
                            )
                            .order_by(Exercise.id)
                            .limit(per_point - len(sources))
                            .all()
                        )
                        sources.extend(extra)
                    for source in sources:
                        key = f"{CLONE_KEY_PREFIX}{source.id}"
                        if source.assistant_operation_key == key:
                            cached.append(source)
                            continue
                        existing = (
                            db.query(Exercise).filter(Exercise.assistant_operation_key == key).first()
                        )
                        if existing is not None:
                            cached.append(existing)
                            continue
                        try:
                            payload = json.loads(source.content or "{}")
                        except (TypeError, ValueError):
                            payload = {}
                        if not isinstance(payload, dict):
                            payload = {}
                        payload.pop("generated_for_user_id", None)
                        payload["demo_clone_of"] = source.id
                        clone = Exercise(
                            knowledge_point_id=point.id,
                            type=source.type,
                            difficulty=source.difficulty or 1,
                            content=json.dumps(payload, ensure_ascii=False),
                            answer=source.answer,
                            analysis=source.analysis or "",
                            assistant_operation_key=key,
                        )
                        db.add(clone)
                        db.flush()
                        report["created_clones"] += 1
                        cached.append(clone)
                    clone_cache[point.id] = cached
                clones.extend(cached)

            point_names = [point.name for point in points]
            scopes = db.query(TeachingScope).filter(TeachingScope.class_id == room.id).all()
            if not scopes:
                scope = TeachingScope(
                    class_id=room.id,
                    student_user_id=None,
                    knowledge_points=list(point_names),
                    learning_direction=room.subject,
                    courseware_title=f"{room.subject}核心知识点",
                    courseware_content=(
                        f"本教学班的演示教学范围，覆盖公共题库中已发布的知识点："
                        f"{'、'.join(point_names)}。"
                    ),
                    teaching_goal=f"掌握{room.subject}的核心概念与基本方法",
                )
                db.add(scope)
                report["created_scopes"] += 1
                scopes = [scope]
            for scope in scopes:
                current = list(scope.knowledge_points or [])
                merged = current + [name for name in point_names if name not in current]
                if merged != current:
                    scope.knowledge_points = merged
                    report["updated_scopes"] += 1

            report["classes"].append(
                {
                    "class": room.name,
                    "class_id": room.id,
                    "subject": room.subject,
                    "points": point_names,
                    "questions": len(clones),
                }
            )

        db.commit()

        rows = (
            db.query(Exercise, KnowledgePoint)
            .join(KnowledgePoint, KnowledgePoint.id == Exercise.knowledge_point_id)
            .filter(Exercise.assistant_operation_key.like(f"{CLONE_KEY_PREFIX}%"))
            .order_by(KnowledgePoint.name, Exercise.id)
            .all()
        )
        for exercise, point in rows:
            try:
                payload = json.loads(exercise.content or "{}")
            except (TypeError, ValueError):
                payload = {}
            if not isinstance(payload, dict):
                payload = {}
            options = [str(item) for item in payload.get("options") or []]
            prompt = str(payload.get("prompt") or payload.get("exercise_content") or "")
            report["questions"].append(
                asdict(
                    DemoQuestion(
                        id=exercise.id,
                        knowledge_point=point.name,
                        type=exercise.type,
                        difficulty=int(exercise.difficulty or 1),
                        answer=str(exercise.answer or ""),
                        options=options,
                        prompt=prompt,
                    )
                )
            )

    return report


def load_question_bank(db_path: Path) -> list[dict]:
    """Read-only helper for the role use cases (question content is never written)."""

    from scripts.demo_teaching_dataset import configure_database

    configure_database(db_path)

    from common.db.session import SessionLocal
    from common.models.learning import Exercise, KnowledgePoint

    with SessionLocal() as db:
        rows = (
            db.query(Exercise, KnowledgePoint)
            .join(KnowledgePoint, KnowledgePoint.id == Exercise.knowledge_point_id)
            .filter(Exercise.assistant_operation_key.like(f"{CLONE_KEY_PREFIX}%"))
            .order_by(KnowledgePoint.name, Exercise.id)
            .all()
        )
        bank: list[dict] = []
        for exercise, point in rows:
            try:
                payload = json.loads(exercise.content or "{}")
            except (TypeError, ValueError):
                payload = {}
            if not isinstance(payload, dict):
                payload = {}
            bank.append(
                {
                    "id": exercise.id,
                    "knowledge_point": point.name,
                    "subject_name": None,
                    "type": exercise.type,
                    "difficulty": int(exercise.difficulty or 1),
                    "answer": str(exercise.answer or ""),
                    "options": [str(item) for item in payload.get("options") or []],
                    "prompt": str(payload.get("prompt") or ""),
                }
            )
    return bank


def reset_question_bank(db_path: Path) -> dict:
    """Remove demo questions *and every answer pointing at them*.

    This is the honest "back to zero" state: after a reset the demo classes have
    no 学情 at all until a real student answers through the API again.
    """

    from scripts.demo_teaching_dataset import configure_database

    configure_database(db_path)

    from common.db.session import SessionLocal
    from common.models.learning import AnswerRecord, Exercise

    removed: dict[str, int] = {}
    with SessionLocal() as db:
        clone_ids = [
            row[0]
            for row in db.query(Exercise.id).filter(
                Exercise.assistant_operation_key.like(f"{CLONE_KEY_PREFIX}%")
            )
        ]
        if not clone_ids:
            return removed
        removed["answer_records"] = (
            db.query(AnswerRecord)
            .filter(AnswerRecord.exercise_id.in_(clone_ids))
            .delete(synchronize_session=False)
        )
        removed["exercises"] = (
            db.query(Exercise).filter(Exercise.id.in_(clone_ids)).delete(synchronize_session=False)
        )
        db.commit()
    return removed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, help="指向运行时 SQLite 文件")
    parser.add_argument("--per-point", type=int, default=DEFAULT_PER_POINT)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--out", default="", help="把题目清单写入 JSON 文件")
    parser.add_argument("--reset", action="store_true", help="删除演示题库及其全部作答（回到零学情）")
    args = parser.parse_args(argv)

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"数据库不存在: {db_path}", file=sys.stderr)
        return 2

    if args.reset:
        removed = reset_question_bank(db_path)
        print(json.dumps({"reset": removed}, ensure_ascii=False, indent=2))
        return 0

    report = build_question_bank(db_path, args.per_point)
    if args.out:
        Path(args.out).write_text(
            json.dumps(report["questions"], ensure_ascii=False, indent=2), encoding="utf-8"
        )

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    print(f"新增演示题: {report['created_clones']}")
    print(f"更新教学范围: {report['updated_scopes']}  新建: {report['created_scopes']}")
    print(f"可用演示题总数: {len(report['questions'])}")
    for item in report["classes"]:
        print(f"  {item['class']}  知识点={item['points']}  题量={item['questions']}")
    if report["skipped"]:
        print("跳过（无题库，未伪造）:")
        for item in report["skipped"]:
            print(f"  {item['class']}: {item['reason']}")
    if args.out:
        print(f"题目清单: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

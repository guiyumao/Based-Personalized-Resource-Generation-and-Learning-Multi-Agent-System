"""Backup-first repair of derived profiles; never delete or guess raw answers.

Default is read-only audit. --apply adds only the membership table and rebuilds
derived profile JSON. It never stamps or migrates the unknown shared baseline.
Restore the backup only with all writers stopped, retaining the repaired file.
"""
import argparse
import json
import sqlite3
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from common.learning_evidence import EVIDENCE_VERSION, recompute_profile
from common.models.learning import (
    AnswerRecord,
    AssistantTask,
    ExerciseKnowledgePoint,
    LearningReport,
    UserProfile,
)


def repair(database, output, apply=False):
    database = database.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database.as_uri()+"?mode=ro", uri=True) as source:
        assert source.execute("pragma integrity_check").fetchone()[0] == "ok"
        before_answers = source.execute("select count(*) from answer_records").fetchone()[0]
        missing = source.execute("select distinct e.id,e.knowledge_point_id from exercises e join answer_records a on a.exercise_id=e.id left join knowledge_points k on k.id=e.knowledge_point_id where k.id is null").fetchall()
        running = source.execute("select count(*) from assistant_tasks where status in ('RUNNING','CANCEL_REQUESTED')").fetchone()[0]
        result = {"database": str(database), "mode": "apply" if apply else "read_only", "before_answers": before_answers,
                  "unclassified_exercises": [list(row) for row in missing], "running_tasks": running,
                  "policy": "exclude_missing_membership_no_text_inference", "evidence_version": EVIDENCE_VERSION}
        if apply:
            if running:
                raise RuntimeError("Active generation tasks exist; finish them before repairing derived data")
            backup = output/"before.sqlite"
            if backup.exists():
                raise RuntimeError("Backup already exists; choose a new repair output directory")
            with sqlite3.connect(backup) as destination:
                source.backup(destination)
                assert destination.execute("pragma integrity_check").fetchone()[0] == "ok"
            result["backup"] = str(backup.resolve())
    if apply:
        engine = create_engine("sqlite:///"+database.as_posix())
        ExerciseKnowledgePoint.__table__.create(engine, checkfirst=True)
        with Session(engine) as db:
            if db.query(AssistantTask).filter(AssistantTask.status.in_(["RUNNING", "CANCEL_REQUESTED"])).count():
                raise RuntimeError("Generation began during audit; no profile writes performed")
            changes = []
            for profile in db.query(UserProfile).all():
                old = profile.mastery_json or {}
                derived = recompute_profile(db, profile.user_id, profile)
                changes.append({"user_id": profile.user_id, "before_keys": list(old), "after_keys": list(derived)})
            stale_reports = 0
            for report in db.query(LearningReport).all():
                content = report.content_json or {}
                if content.get("evidence_version") != EVIDENCE_VERSION:
                    report.content_json = {**content, "stale": True, "stale_reason": "point_evidence_rules_updated"}
                    stale_reports += 1
            result["historical_reports_marked_stale"] = stale_reports
            assert db.query(AnswerRecord).count() == before_answers, "Concurrent raw-answer write; retry with fresh audit"
            db.commit()
            result.update(profiles_recomputed=len(changes), changes=changes, after_answers=db.query(AnswerRecord).count())
        engine.dispose()
    (output/"repair-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("mode", "before_answers", "running_tasks")}, ensure_ascii=False))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    repair(args.database, args.output, args.apply)

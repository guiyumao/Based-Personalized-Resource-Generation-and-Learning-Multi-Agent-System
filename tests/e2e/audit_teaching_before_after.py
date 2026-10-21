"""Run old Git implementation and repaired implementation on a backup copy."""
import json
import sqlite3
import subprocess
import sys
import types
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from common.models.learning import ExerciseKnowledgePoint
from services.agent_service.app.services.personalization import PersonalizationService

root = Path("artifacts/teaching-evidence-20261020")
source = (root/"shared-repair/before.sqlite").resolve()
target = root/"comparison.sqlite"
with sqlite3.connect(source.as_uri()+"?mode=ro", uri=True) as before, sqlite3.connect(target) as copy:
    before.backup(copy)
engine = create_engine("sqlite:///"+target.resolve().as_posix())
ExerciseKnowledgePoint.__table__.create(engine, checkfirst=True)
old_source = subprocess.check_output(["git", "show", "HEAD:services/agent_service/app/services/personalization.py"], encoding="utf-8")
module = types.ModuleType("teaching_old_personalization")
sys.modules[module.__name__] = module
exec(compile(old_source, "git:personalization.py", "exec"), module.__dict__)
with Session(engine) as db:
    previous = module.PersonalizationService(db).build_snapshot(6, "冒泡排序", {})
    repaired = PersonalizationService(db).build_snapshot(6, "冒泡排序", {}, point_id="459", subject="数据结构")
    result = {"source": "same_backup_database", "user_id": 6, "knowledge_point": "冒泡排序",
        "before": {"answered_count": previous.answered_count, "mastery": previous.mastery_score,
                   "mistake_exercise_ids": [r["exercise_id"] for r in previous.recent_mistakes]},
        "after": {"answered_count": repaired.answered_count, "mastery": repaired.mastery_score,
                  "mistake_exercise_ids": [r["exercise_id"] for r in repaired.recent_mistakes], "evidence": repaired.learner_profile["evidence"]}}
    assert result["before"]["answered_count"] > 0
    assert result["after"]["answered_count"] == 0 and result["after"]["mastery"] is None
    (root/"before-after.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))

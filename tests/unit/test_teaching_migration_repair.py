"""Actual SQLite migration roundtrip and backup-first repair acceptance."""
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from alembic.config import Config
from alembic.script import ScriptDirectory


def test_0032_roundtrip_preserves_accounts_and_raw_answers(tmp_path):
    database = tmp_path/"migration.sqlite"
    env = {**os.environ, "DATABASE_URL": "sqlite:///" + database.as_posix()}
    def migrate(target, direction="upgrade"):
        result = subprocess.run([sys.executable, "-m", "alembic", direction, target], env=env, capture_output=True, text=True, encoding="utf-8")
        assert result.returncode == 0, result.stderr[-3000:]
    migrate("head")
    with sqlite3.connect(database) as db:
        db.execute("insert into users(id,username,password_hash,role,is_active) values(1,'preserved','unused','student',1)")
        db.execute("insert into knowledge_points(id,name) values(1,'confirmed')")
        db.execute("insert into exercises(id,knowledge_point_id,type,content,answer) values(1,1,'choice','{}','B')")
        db.execute("insert into answer_records(id,user_id,exercise_id,user_answer,is_correct) values(1,1,1,'B',1)")
        db.execute("insert into exercise_knowledge_points(exercise_id,knowledge_point_id,weight,confirmed) values(1,1,1,1)")
        db.commit()
    migrate("20261020_0031", "downgrade")
    migrate("head")
    with sqlite3.connect(database) as db:
        assert db.execute("select username from users where id=1").fetchone()[0] == "preserved"
        assert db.execute("select count(*) from answer_records").fetchone()[0] == 1
        assert db.execute("select version_num from alembic_version").fetchone()[0] == ScriptDirectory.from_config(Config('alembic.ini')).get_current_head()
        assert db.execute("pragma integrity_check").fetchone()[0] == "ok"


def test_backup_first_repair_on_current_database_copy(tmp_path):
    source_path = Path("artifacts/local-start-20261019/runtime.sqlite").resolve()
    target_path = tmp_path/"repair.sqlite"
    with sqlite3.connect(source_path.as_uri()+"?mode=ro", uri=True) as source, sqlite3.connect(target_path) as target:
        source.backup(target)
    output = tmp_path/"repair-evidence"
    result = subprocess.run([sys.executable, "scripts/repair_learning_evidence.py", "--database", str(target_path),
        "--output", str(output), "--apply"], capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads((output/"repair-result.json").read_text(encoding="utf-8"))
    assert report["before_answers"] == report["after_answers"]
    assert Path(report["backup"]).is_file()
    assert report["profiles_recomputed"] > 0

"""Run only with run_no_cost_tests.py and an empty isolated runtime root."""
import json
import os
from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from alembic import command

assert os.environ.get("NO_COST_GUARD_ACTIVE") == "1"
root = Path(os.environ["KNOWLEDGE_RUNTIME_ROOT"])
assert not (root / "runtime.sqlite").exists(), "Migration drill requires a fresh empty database"
config = Config("alembic.ini")
command.upgrade(config, "20261020_0026")
engine = create_engine(os.environ["DATABASE_URL"])
with engine.begin() as connection:
    assert connection.scalar(text("select version_num from alembic_version")) == "20261020_0026"
    connection.execute(text("insert into users(id, username, password_hash, role, is_active) values (1, 'migration-fixture', 'unused', 'student', 1)"))
    connection.execute(text("insert into study_sessions(user_id,tab_id,sequence,revision,active,heartbeat_at) values (1,'fixture',1,0,1,'2026-10-20 00:00:00')"))
    connection.execute(text("insert into study_activities(user_id,started_at,ended_at,page) values (1,'2026-10-20 00:00:00','2026-10-20 00:00:15','exercise')"))
engine.dispose()
command.downgrade(config, "20261019_0025")
engine = create_engine(os.environ["DATABASE_URL"])
assert not inspect(engine).has_table("study_sessions")
assert not inspect(engine).has_table("study_activities")
with engine.connect() as connection:
    assert connection.scalar(text("select count(*) from users where username='migration-fixture'")) == 1
engine.dispose()
command.upgrade(config, "20261020_0026")
engine = create_engine(os.environ["DATABASE_URL"])
assert inspect(engine).has_table("study_sessions")
assert inspect(engine).has_table("study_activities")
with engine.connect() as connection:
    assert connection.scalar(text("select count(*) from users where username='migration-fixture'")) == 1
engine.dispose()
command.upgrade(config, "head")
engine = create_engine(os.environ["DATABASE_URL"])
with engine.connect() as connection:
    head = connection.scalar(text("select version_num from alembic_version"))
engine.dispose()
(root / "migration-result.json").write_text(json.dumps({"passed": True, "empty_to_head": head, "roundtrip": "0026 -> 0025 -> 0026", "users_preserved": True, "shared_db_touched": False}), encoding="utf-8")

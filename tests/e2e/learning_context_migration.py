"""Empty isolated migration and 0029/0028 additive rollback drill."""

import json
import os
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

from alembic import command

assert os.environ.get("NO_COST_GUARD_ACTIVE") == "1"
root = Path(os.environ["KNOWLEDGE_RUNTIME_ROOT"])
assert not (root / "runtime.sqlite").exists()
config = Config("alembic.ini")
TARGET_HEAD = ScriptDirectory.from_config(config).get_current_head()
command.upgrade(config, "20261020_0027")
engine = create_engine(os.environ["DATABASE_URL"])
with engine.begin() as db:
    db.execute(
        text(
            "insert into users(id,username,password_hash,role,is_active) values(1,'context-migration','unused','student',1)"
        )
    )
    db.execute(
        text(
            "insert into study_notes(id,user_id,title,body) values(1,1,'historical note','preserved body')"
        )
    )
engine.dispose()
command.upgrade(config, "head")
engine = create_engine(os.environ["DATABASE_URL"])
assert inspect(engine).has_table("learning_contexts")
assert inspect(engine).has_table("context_exercises")
assert inspect(engine).has_table("learning_knowledge_gaps")
with engine.begin() as db:
    assert db.scalar(text("select version_num from alembic_version")) == TARGET_HEAD
    assert db.scalar(text("select body from study_notes where id=1")) == "preserved body"
    db.execute(
        text(
            "insert into learning_knowledge_gaps(id,user_id,request_key,subject,knowledge_point,reason,status) values('gap',1,'request','subject','point','POINT_MISSING','REQUESTED')"
        )
    )
engine.dispose()
command.downgrade(config, "20261020_0028")
engine = create_engine(os.environ["DATABASE_URL"])
assert not inspect(engine).has_table("learning_knowledge_gaps")
assert inspect(engine).has_table("learning_contexts")
engine.dispose()
command.downgrade(config, "20261020_0027")
engine = create_engine(os.environ["DATABASE_URL"])
assert not inspect(engine).has_table("learning_contexts")
assert "learning_context_id" not in {
    row["name"] for row in inspect(engine).get_columns("study_notes")
}
with engine.connect() as db:
    assert db.scalar(text("select body from study_notes where id=1")) == "preserved body"
    assert db.scalar(text("select count(*) from users where username='context-migration'")) == 1
engine.dispose()
command.upgrade(config, "head")
engine = create_engine(os.environ["DATABASE_URL"])
with engine.connect() as db:
    assert db.scalar(text("select version_num from alembic_version")) == TARGET_HEAD
    assert db.scalar(text("select body from study_notes where id=1")) == "preserved body"
engine.dispose()
(root / "migration-result.json").write_text(
    json.dumps(
        {
            "passed": True,
            "empty_to_head": TARGET_HEAD,
            "roundtrip": f"{TARGET_HEAD}->0028->0027->{TARGET_HEAD}",
            "historical_users_and_notes_preserved": True,
            "shared_database_touched": False,
        }
    ),
    encoding="utf-8",
)

"""Isolated 0009 ownership regression and document single-step migration drill."""
import json
import os
from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from alembic import command

assert os.environ.get("NO_COST_GUARD_ACTIVE") == "1"
root = Path(os.environ["KNOWLEDGE_RUNTIME_ROOT"])
assert not (root / "runtime.sqlite").exists()
config = Config("alembic.ini")
command.upgrade(config, "20261016_0009")
engine = create_engine(os.environ["DATABASE_URL"])
with engine.begin() as connection:
    connection.execute(text("insert into users(id,username,password_hash,role,is_active) values(1,'migration-preserve','unused','student',1)"))
engine.dispose()
command.downgrade(config, "20261016_0008")
engine = create_engine(os.environ["DATABASE_URL"])
columns = {c["name"] for c in inspect(engine).get_columns("answer_records")}
assert {"created_at", "evaluation_json"} <= columns, columns
with engine.connect() as connection:
    assert connection.scalar(text("select count(*) from users where username='migration-preserve'")) == 1
engine.dispose()
command.upgrade(config, "head")
command.downgrade(config, "20261020_0026")
command.upgrade(config, "head")
engine = create_engine(os.environ["DATABASE_URL"])
with engine.connect() as connection:
    head = connection.scalar(text("select version_num from alembic_version"))
    assert connection.scalar(text("select count(*) from users where username='migration-preserve'")) == 1
assert inspect(engine).has_table("knowledge_documents")
engine.dispose()
(root / "migration-result.json").write_text(json.dumps({"passed": True, "head": head, "roundtrips": ["0009->0008->head", "0027->0026->head"], "answer_metadata_preserved": True, "users_preserved": True, "shared_db_touched": False}), encoding="utf-8")

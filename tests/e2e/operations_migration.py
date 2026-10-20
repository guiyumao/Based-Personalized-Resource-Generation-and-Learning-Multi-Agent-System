"""Additive schema drill, rollback and legacy-data retention in an isolated DB."""
import json
import os
from pathlib import Path
from alembic.config import Config
from alembic import command
from sqlalchemy import create_engine, inspect, text

assert os.environ.get("NO_COST_GUARD_ACTIVE")=="1"
root=Path(os.environ["KNOWLEDGE_RUNTIME_ROOT"])
assert not (root/"runtime.sqlite").exists()
config=Config("alembic.ini")
command.upgrade(config,"20261020_0029")
engine=create_engine(os.environ["DATABASE_URL"])
with engine.begin() as db:
    db.execute(text("insert into users(id,username,password_hash,role,is_active) values(1,'operations-migration','unused','student',1)"))
    db.execute(text("insert into study_notes(id,user_id,title,body) values(1,1,'legacy','preserve')"))
engine.dispose()
command.upgrade(config,"head")
engine=create_engine(os.environ["DATABASE_URL"])
for table in ("model_calls","worker_instances","task_attempts","resource_artifacts","resource_revisions"):
    assert inspect(engine).has_table(table)
with engine.connect() as db:
    assert db.scalar(text("select version_num from alembic_version"))=="20261020_0031"
engine.dispose()
command.downgrade(config,"20261020_0029")
engine=create_engine(os.environ["DATABASE_URL"])
assert not inspect(engine).has_table("model_calls")
with engine.connect() as db:
    assert db.scalar(text("select body from study_notes where id=1"))=="preserve"
engine.dispose()
command.upgrade(config,"head")
engine=create_engine(os.environ["DATABASE_URL"])
with engine.connect() as db:
    assert db.scalar(text("select count(*) from users where username='operations-migration'"))==1
engine.dispose()
(root/"migration-result.json").write_text(json.dumps({"passed":True,"head":"20261020_0031","roundtrip":"0029->0031->0029->0031","legacy_user_and_note_preserved":True,"shared_db_touched":False}),encoding="utf-8")

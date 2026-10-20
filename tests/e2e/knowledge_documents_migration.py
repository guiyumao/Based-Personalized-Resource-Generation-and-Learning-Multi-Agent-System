"""Empty isolated database migration and scoped round-trip; no shared writes."""
import json
import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

assert os.environ.get("NO_COST_GUARD_ACTIVE") == "1"
root = Path(os.environ["KNOWLEDGE_RUNTIME_ROOT"])
assert not (root / "runtime.sqlite").exists()
config = Config("alembic.ini")
command.upgrade(config, "head")
engine = create_engine(os.environ["DATABASE_URL"])
assert inspect(engine).has_table("knowledge_documents")
assert inspect(engine).has_table("knowledge_document_points")
with engine.begin() as connection:
    connection.execute(text("insert into users(id,username,password_hash,role,is_active) values(1,'document-migration','unused','admin',1)"))
engine.dispose()
command.downgrade(config, "20261020_0026")
engine = create_engine(os.environ["DATABASE_URL"])
assert not inspect(engine).has_table("knowledge_documents")
with engine.connect() as connection:
    assert connection.scalar(text("select count(*) from users where username='document-migration'")) == 1
engine.dispose()
command.upgrade(config, "head")
engine = create_engine(os.environ["DATABASE_URL"])
assert inspect(engine).has_table("knowledge_documents")
with engine.connect() as connection:
    head = connection.scalar(text("select version_num from alembic_version"))
    assert head == "20261020_0027"
engine.dispose()
(root / "migration-result.json").write_text(json.dumps({"passed": True, "empty_to_head": head, "roundtrip": "0027 -> 0026 -> 0027", "users_preserved": True, "shared_db_touched": False}), encoding="utf-8")

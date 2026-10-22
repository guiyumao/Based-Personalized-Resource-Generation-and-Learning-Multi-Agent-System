"""Exercise the formal migration chain, upgrade and rollback with historical data."""

from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from alembic import command
from common.config import get_settings

cfg = Config("alembic.ini")
engine = create_engine(get_settings().database_url)
command.upgrade(cfg, "20261021_0033")
with engine.begin() as db:
    db.execute(
        text(
            "INSERT INTO users (id,username,password_hash,role,is_active) VALUES (99001,'migration-notice','x','student',1)"
        )
    )
    db.execute(
        text(
            "INSERT INTO notifications (user_id,title,content,type,related_type,is_read) VALUES (99001,'历史消息','保留正文','system','',1)"
        )
    )
for version in ("head", "20261021_0033", "head"):
    command.upgrade(cfg, version) if version == "head" else command.downgrade(cfg, version)
    with engine.connect() as db:
        assert db.execute(
            text("SELECT title,content,is_read FROM notifications WHERE user_id=99001")
        ).one() == ("历史消息", "保留正文", 1)
assert {"sender_id", "event_key", "read_at"} <= {
    c["name"] for c in inspect(engine).get_columns("notifications")
}
print("PASS empty to 0033, 0033 -> 0034 -> 0033 -> 0034; historical inbox preserved")

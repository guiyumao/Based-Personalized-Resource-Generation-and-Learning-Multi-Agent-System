"""Isolated 0032/0033 round trip retaining old notes/cards/users."""
import json
import os
from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from alembic import command

assert os.getenv('NO_COST_GUARD_ACTIVE')=='1'
root=Path(os.environ['KNOWLEDGE_RUNTIME_ROOT'])
assert not (root/'runtime.sqlite').exists()
config=Config('alembic.ini')
command.upgrade(config,'20261020_0032')
engine=create_engine(os.environ['DATABASE_URL'])
with engine.begin() as db:
    db.execute(text("insert into users(id,username,password_hash,role,is_active) values(1,'study-migration','unused','student',1)"))
    db.execute(text("insert into study_notes(id,user_id,title,body) values(1,1,'old note','preserve me')"))
engine.dispose()
command.upgrade(config,'20261021_0033')
command.downgrade(config,'20261020_0032')
engine=create_engine(os.environ['DATABASE_URL'])
with engine.connect() as db:
    assert db.scalar(text('select body from study_notes where id=1'))=='preserve me'
    assert not inspect(engine).has_table('note_revisions')
engine.dispose()
command.upgrade(config,'20261021_0033')
engine=create_engine(os.environ['DATABASE_URL'])
with engine.connect() as db:
    assert db.scalar(text('select count(*) from users'))==1
    assert set(('note_revisions','card_knowledge_bindings','card_review_receipts')).issubset(inspect(engine).get_table_names())
engine.dispose()
(root/'result.json').write_text(json.dumps({'passed':True,'head':'20261021_0033','roundtrip':'0032->0033->0032->0033','old_note_and_user_preserved':True}),encoding='utf-8')

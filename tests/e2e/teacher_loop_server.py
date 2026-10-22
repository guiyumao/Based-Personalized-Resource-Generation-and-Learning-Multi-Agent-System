"""Production service apps sharing one isolated database; no mocked business APIs."""

import os

from fastapi import FastAPI

from common.db.base import Base
from common.db.session import SessionLocal, engine
from common.models.learning import User
from common.security.auth import hash_password
from services.agent_service.app.main import app as agent
from services.evaluation_service.app.main import app as evaluation
from services.teacher_service.app.main import app as teacher
from services.user_service.app.main import app as user

assert os.environ.get("NO_COST_GUARD_ACTIVE") == "1"
Base.metadata.create_all(engine)
with SessionLocal() as db:
    for name, role in [
        ("loop-teacher", "teacher"),
        ("loop-student", "student"),
        ("loop-other-teacher", "teacher"),
        ("loop-outsider", "student"),
    ]:
        if not db.query(User).filter_by(username=name).first():
            db.add(
                User(
                    username=name,
                    role=role,
                    password_hash=hash_password("Loop-test-123"),
                    is_active=True,
                )
            )
    db.commit()
app = FastAPI()
app.mount("/teacher-api", teacher)
app.mount("/user-api", user)
app.mount("/agent-api", agent)
app.mount("/evaluation-api", evaluation)

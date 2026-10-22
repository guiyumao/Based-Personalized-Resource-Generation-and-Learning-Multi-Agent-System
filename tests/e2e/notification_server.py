"""Isolated, provider-free server for real notification browser acceptance."""

import json
import os
from pathlib import Path

from fastapi import FastAPI

from common.db.base import Base
from common.db.session import SessionLocal, engine
from common.models.learning import User
from common.security.auth import create_access_token
from services.evaluation_service.app.main import app as evaluation
from services.teacher_service.app.main import app as teacher
from services.user_service.app.main import app as user

assert os.environ.get("NO_COST_GUARD_ACTIVE") == "1"
Base.metadata.create_all(engine)
with SessionLocal() as db:
    for uid, role in [(901, "admin"), (902, "teacher"), (903, "student"), (904, "student")]:
        db.add(
            User(
                id=uid,
                username=f"notification-{role}-{uid}",
                password_hash="browser-test",
                role=role,
                is_active=True,
            )
        )
    db.commit()
Path(os.environ["NOTIFICATION_OUTPUT"], "auth.json").write_text(
    json.dumps(
        {
            str(uid): {
                "token": create_access_token(str(uid)),
                "user": {"userId": uid, "username": f"notification-{role}-{uid}", "role": role},
            }
            for uid, role in [(901, "admin"), (902, "teacher"), (903, "student"), (904, "student")]
        }
    ),
    encoding="utf-8",
)
app = FastAPI()
app.mount("/teacher-api", teacher)
app.mount("/user-api", user)
app.mount("/evaluation-api", evaluation)

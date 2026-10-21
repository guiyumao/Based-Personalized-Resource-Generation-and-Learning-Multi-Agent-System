"""Read-only compatibility probe against the current runtime, with no model keys."""

import json
import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from common.models.learning import User
from services.evaluation_service.app.services.learning_insights import build_learning_insights
from services.user_service.app.api.routes.learning_portrait import snapshot

assert os.environ.get("NO_COST_GUARD_ACTIVE") == "1"
source = Path("artifacts/local-start-20261019/runtime.sqlite").resolve()
engine = create_engine("sqlite+pysqlite:///file:" + source.as_posix() + "?mode=ro&uri=true")
with Session(engine) as db:
    learner = db.query(User).filter_by(role="student", is_active=True).order_by(User.id).first()
    assert learner is not None
    analytics = build_learning_insights(db, learner.id)
    portrait = snapshot(db, learner.id)
    result = {
        "passed": True,
        "read_only": True,
        "learner_id": learner.id,
        "analytics_days": len(analytics["daily"]),
        "portrait_axes": len(portrait["axes"]),
        "models_called": 0,
        "schema_changed": False,
    }
engine.dispose()
Path(os.environ["KNOWLEDGE_RUNTIME_ROOT"], "read-probe.json").write_text(
    json.dumps(result), encoding="utf-8"
)

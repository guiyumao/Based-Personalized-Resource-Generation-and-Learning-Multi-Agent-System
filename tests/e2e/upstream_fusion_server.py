"""Isolated real APIs and persistence; only exercise model output is controlled."""

import json
import os
from pathlib import Path

from fastapi import FastAPI

from common.db.base import Base
from common.db.session import SessionLocal, engine
from common.models.learning import User
from common.security.auth import create_access_token
from services.agent_service.app.main import app as agent
from services.agent_service.app.services.exercise_generation import ExerciseGenerationService
from services.evaluation_service.app.main import app as evaluation
from services.teacher_service.app.main import app as teacher
from services.user_service.app.main import app as user

assert os.environ.get("NO_COST_GUARD_ACTIVE") == "1"
Base.metadata.create_all(engine)
with SessionLocal() as db:
    db.add_all(
        [
            User(id=903, username="fusion-student", password_hash="disabled", role="student"),
            User(id=904, username="fusion-other", password_hash="disabled", role="student"),
        ]
    )
    db.commit()


def controlled_model(self, request, *args):
    # Exact-count fixtures are reviewed/persisted by the unchanged real service.
    return {
        "summary": "受控模型输出，仅用于融合验收",
        "exercises": [
            {
                "exercise_id": i,
                "knowledge_point": request.knowledge_point,
                "question_type": "choice",
                "difficulty": "foundation",
                "prompt": f"TCP 在第 {i} 个例题中，初始序号为 {1000 + i * 100}，携带 {i} 字节数据，下一确认号为多少？",
                "options": [f"A. {1000 + i * 100 + i}", f"B. {1000 + i * 100}", "C. 0", "D. 1"],
                "answer": "A",
                "analysis": "TCP 确认号等于下一个期望接收的字节序号。",
            }
            for i in range(1, request.exercise_count + 1)
        ],
    }


ExerciseGenerationService._try_generate_with_llm = controlled_model
out = Path(os.environ["FUSION_BROWSER_OUTPUT"])
(out / "auth.json").write_text(
    json.dumps(
        {
            str(uid): {
                "token": create_access_token(str(uid)),
                "user": {
                    "userId": uid,
                    "username": "fusion-student" if uid == 903 else "fusion-other",
                    "role": "student",
                },
            }
            for uid in (903, 904)
        }
    ),
    encoding="utf-8",
)
app = FastAPI()
app.mount("/agent", agent)
app.mount("/user", user)
app.mount("/evaluation", evaluation)
app.mount("/teacher", teacher)

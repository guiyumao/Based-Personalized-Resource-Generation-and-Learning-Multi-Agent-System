"""Read-only teaching follow-up on a backup of the actual runtime DB; no providers."""
import json, os
from pathlib import Path
from fastapi import FastAPI
from common.security.auth import create_access_token
from services.agent_service.app.main import app as agent
from services.user_service.app.main import app as user
from services.resource_service.app.main import app as resource
from services.evaluation_service.app.main import app as evaluation
assert os.getenv("NO_COST_GUARD_ACTIVE") == "1"
Path(os.environ["TEACHING_BROWSER_OUTPUT"], "auth.json").write_text(json.dumps({"token":create_access_token("6")}),encoding="utf-8")
app=FastAPI()
app.mount("/agent",agent)
app.mount("/user",user)
app.mount("/resource",resource)
app.mount("/evaluation",evaluation)

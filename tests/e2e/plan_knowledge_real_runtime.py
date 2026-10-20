"""Reuse the document acceptance runtime and add a live publication-gate check."""

import json
import os
import runpy
import subprocess
from pathlib import Path

assert os.environ.get("NO_COST_GUARD_ACTIVE") == "1"
original_run = subprocess.run


def run_with_plan_check(args, *positional, **kwargs):
    result = original_run(args, *positional, **kwargs)
    if args == ["node", "tests/e2e/run-knowledge-documents.mjs"] and result.returncode == 0:
        import httpx

        env = kwargs["env"]
        client = httpx.Client(base_url=env["DOCS_API"], timeout=30)
        login = client.post(
            "/user/users/login",
            json={"username": "documents-student", "password": env["DOCS_PASSWORD"]},
        )
        assert login.status_code == 200
        headers = {"Authorization": "Bearer " + login.json()["access_token"]}
        response = client.post(
            "/agent/paths/preflight",
            headers=headers,
            json={"subject": "隔离文档数学", "knowledge_point": "向量谱线"},
        )
        assert response.status_code == 200, response.text
        assessment = response.json()
        assert assessment["ready"] is True, assessment
        assert assessment["published_versions"]
        assert assessment["retrieval_error"] is None
        (Path(os.environ["KNOWLEDGE_RUNTIME_ROOT"]) / "plan-knowledge-live-result.json").write_text(
            json.dumps(
                {
                    "passed": True,
                    "real_chroma": True,
                    "real_worker_publication": True,
                    "model_calls": 0,
                    "assessment": assessment,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        client.close()
    return result


subprocess.run = run_with_plan_check
try:
    runpy.run_path("tests/e2e/knowledge_documents_runtime.py", run_name="__main__")
finally:
    subprocess.run = original_run

"""Adversarial misconfiguration checks, sentinel values only, no paid service."""

from __future__ import annotations

import asyncio
import os
import socket
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("NO_COST_GUARD_ACTIVE") != "1", reason="use scripts/run_no_cost_tests.py"
)


def child(code: str, *, env=None, cwd=None):
    return subprocess.run(
        [sys.executable, "-c", code],
        env=env or dict(os.environ),
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15,
    )


def test_no_paid_api_without_authorization(tmp_path):
    (tmp_path / ".env").write_text(
        "DEEPSEEK_API_KEY=FAKE_DOTENV_SENTINEL\nDEEPSEEK_API_BASE=https://api.deepseek.com\n",
        encoding="utf-8",
    )
    environment = dict(os.environ)
    for name in ("DEEPSEEK_API_KEY", "OPENAI_API_KEY", "QWEN_API_KEY"):
        environment.pop(name, None)
    environment.update(RUN_LIVE_LLM="1", DEEPSEEK_LIVE_PAID_ACK="1", APP_LOAD_DOTENV="true")
    result = child(
        "import os;from common.config import get_settings; s=get_settings();assert s.deepseek_api_key=='no-cost-stub';assert os.environ['RUN_LIVE_LLM']=='0';assert os.environ['DEEPSEEK_LIVE_PAID_ACK']=='0';print('guarded')",
        env=environment,
        cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "guarded"


def test_dotenv_reload_cannot_read_credentials(tmp_path):
    path = tmp_path / ".env"
    path.write_text("DEEPSEEK_API_KEY=FAKE_READ_SENTINEL", encoding="utf-8")
    with pytest.raises(PermissionError, match="dotenv"):
        path.read_text(encoding="utf-8")


def test_dependency_dotenv_loader_does_not_read_local_file(tmp_path):
    import dotenv
    from dotenv.main import DotEnv

    path = tmp_path / ".env"
    path.write_text("DEEPSEEK_API_KEY=DEPENDENCY_SENTINEL", encoding="utf-8")
    assert dotenv.dotenv_values(path) == {}
    assert DotEnv(str(path)).dict() == {}


@pytest.mark.parametrize("host", ["api.deepseek.com", "198.18.0.215", "8.8.8.8", "203.0.113.1"])
def test_socket_cannot_connect_to_external_or_fake_ip(host):
    with pytest.raises(PermissionError, match="NO_COST_GUARD"):
        socket.create_connection((host, 443), timeout=0.2)


def test_undeclared_loopback_proxy_is_blocked():
    with pytest.raises(PermissionError, match="NO_COST_GUARD"):
        socket.create_connection(("127.0.0.1", 7890), timeout=0.2)


def test_python_child_must_inherit_guard():
    with pytest.raises(PermissionError, match="Python child"):
        child("print('unsafe')", env={"PATH": os.environ.get("PATH", "")})


def test_worker_child_and_import_cache_are_guarded():
    result = child(
        "import importlib,os;from common import config;importlib.reload(config);from services.agent_service.app.services import assistant_worker,knowledge_worker;assert os.getenv('NO_COST_GUARD_ACTIVE')=='1';assert config.get_settings().deepseek_api_key=='no-cost-stub';print('worker imports safe')"
    )
    assert result.returncode == 0, result.stderr


def test_sync_async_retry_and_gateway_are_blocked():
    for _ in range(3):
        with pytest.raises(PermissionError, match="NO_COST_GUARD"):
            httpx.get("https://example.com/custom-gateway", timeout=0.2)

    async def attempt():
        async with httpx.AsyncClient() as client:
            with pytest.raises(PermissionError, match="NO_COST_GUARD"):
                await client.get("https://api.deepseek.com/v1/chat/completions")

    asyncio.run(attempt())


def test_locally_declared_mock_receives_no_real_key(monkeypatch):
    seen = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append(self.headers.get("Authorization"))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        # The guard only declares the listener this test actually created.
        result = httpx.get(
            f"http://127.0.0.1:{server.server_port}",
            headers={"Authorization": "Bearer " + os.environ["DEEPSEEK_API_KEY"]},
            trust_env=False,
        )
        assert result.status_code == 200
        assert seen == ["Bearer no-cost-stub"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_invalid_guard_configuration_fails_closed():
    environment = dict(os.environ)
    environment["NO_COST_ALLOWED_PORTS"] = "not-a-port"
    result = child("print('MUST_NOT_EXECUTE')", env=environment)
    assert result.returncode == 78 and "MUST_NOT_EXECUTE" not in result.stdout

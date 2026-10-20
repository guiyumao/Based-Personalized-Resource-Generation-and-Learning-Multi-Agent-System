"""Self-test for the local DeepSeek recording/budget proxy (no external calls)."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from scripts.deepseek_ledger_proxy import create_proxy


class _UpstreamHandler(BaseHTTPRequestHandler):
    requests: list[dict] = []

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("content-length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        type(self).requests.append(body)
        data = json.dumps(
            {
                "id": "chatcmpl-upstream-stub",
                "object": "chat.completion",
                "model": "deepseek-chat",
                "choices": [
                    {"index": 0, "message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}
                ],
                "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10},
            }
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *_args) -> None:
        return


def _post(url: str, payload: dict) -> tuple[int, dict]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": "Bearer local-test-key"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return int(response.status), json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return int(exc.code), json.loads(exc.read())


@pytest.fixture
def servers(tmp_path):
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), _UpstreamHandler)
    upstream.daemon_threads = True
    upstream_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    upstream_thread.start()
    upstream_url = f"http://127.0.0.1:{upstream.server_address[1]}"
    ledger_path = tmp_path / "request-ledger.jsonl"

    proxy = create_proxy(
        upstream=upstream_url,
        ledger_path=str(ledger_path),
        max_attempts=1,
        scenario="proxy-self-test",
    )
    proxy_thread = threading.Thread(target=proxy.serve_forever, daemon=True)
    proxy_thread.start()
    proxy_url = f"http://127.0.0.1:{proxy.server_address[1]}"

    try:
        yield proxy_url, ledger_path
    finally:
        proxy.shutdown()
        proxy.server_close()
        upstream.shutdown()
        upstream.server_close()
        proxy_thread.join(timeout=2)
        upstream_thread.join(timeout=2)


def test_proxy_counts_one_outbound_attempt_and_blocks_the_next(servers) -> None:
    proxy_url, ledger_path = servers
    payload = {"model": "deepseek-chat", "messages": [{"role": "user", "content": "ping"}]}

    first_status, first_body = _post(f"{proxy_url}/v1/chat/completions", payload)
    second_status, second_body = _post(f"{proxy_url}/v1/chat/completions", payload)

    assert first_status == 200
    assert first_body["usage"]["total_tokens"] == 10
    assert second_status == 429
    assert second_body["error"]["type"] == "proxy_budget_exceeded"

    rows = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 2
    assert rows[0]["outbound"] is True and rows[0]["blocked"] is False
    assert rows[0]["status"] == 200
    assert rows[0]["request_model"] == "deepseek-chat"
    assert rows[0]["response_model"] == "deepseek-chat"
    assert rows[0]["usage"]["total_tokens"] == 10
    assert rows[1]["outbound"] is False and rows[1]["blocked"] is True
    assert rows[1]["status"] == 429
    assert "authorization" not in json.dumps(rows).lower()
